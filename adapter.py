"""Native Yandex Messenger Bot API adapter for Hermes Agent.

The adapter is intentionally a standalone Hermes platform plugin. Polling is
the default transport because it requires no public ingress. Webhook mode is
available for installations that can expose a fast HTTPS endpoint; Yandex does
not document a request-signature header, so that mode requires an unguessable
secret URL path and should sit behind a TLS reverse proxy.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import mimetypes
import os
import random
import re
import secrets
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import aiohttp
except ImportError:  # pragma: no cover - surfaced by check_requirements/connect
    aiohttp = None  # type: ignore[assignment]

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    cache_document_from_bytes,
    cache_image_from_bytes,
    get_inbound_media_max_bytes,
    validate_inbound_media_size,
)
from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

PLATFORM_NAME = "yandex_messenger"
API_BASE = "https://botapi.messenger.yandex.net/bot/v1"
TEXT_LIMIT = 6000
SAFE_TEXT_LIMIT = 5900
POLL_LIMIT = 100
WEBHOOK_BODY_LIMIT = 1024 * 1024
ACTION_TTL_SECONDS = 3600
ACTION_CACHE_SIZE = 1000
UPDATE_DEDUPE_SIZE = 5000


class YandexAPIError(RuntimeError):
    """A sanitized Yandex Bot API failure."""

    def __init__(
        self,
        message: str,
        *,
        status: int = 0,
        retryable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.retry_after = retry_after


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, Iterable):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _valid_webhook_secret(value: str) -> bool:
    return len(value) >= 32 and re.fullmatch(r"[A-Za-z0-9_-]+", value) is not None


def _extra(config: PlatformConfig) -> dict[str, Any]:
    value = getattr(config, "extra", None)
    return value if isinstance(value, dict) else {}


def _token_for(config: PlatformConfig) -> str:
    return (
        os.getenv("YANDEX_MESSENGER_TOKEN")
        or getattr(config, "token", None)
        or _extra(config).get("token")
        or ""
    ).strip()


def _target_params(target: str) -> dict[str, str]:
    """Turn a stable Hermes target into Bot API routing parameters.

    Explicit ``login:`` and ``chat:`` prefixes are preferred. Bare values
    containing a slash are treated as Yandex chat IDs; other bare values are
    retained as login targets for backward compatibility.
    """

    raw = str(target or "").strip()
    if raw.startswith("login:"):
        return {"login": raw[6:]}
    if raw.startswith("chat:"):
        return {"chat_id": raw[5:]}
    if "/" in raw:
        return {"chat_id": raw}
    return {"login": raw}


def _thread_id(metadata: dict[str, Any] | None) -> int | None:
    if not metadata:
        return None
    value = metadata.get("thread_id")
    if value is None:
        value = metadata.get("message_thread_id")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.debug("Ignoring non-numeric Yandex thread_id: %r", value)
        return None


def _safe_api_detail(value: Any, token: str) -> str:
    text = str(value or "request failed").replace("\r", " ").replace("\n", " ")
    if token:
        text = text.replace(token, "<redacted>")
    return text[:500]


class YandexMessengerClient:
    """Small aiohttp client for the documented Bot API surface."""

    def __init__(self, token: str, session: aiohttp.ClientSession) -> None:
        self._token = token
        self._session = session

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"OAuth {self._token}"}

    async def json(
        self,
        path: str,
        *,
        method: str = "POST",
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        data: Any = None,
        allow_empty: bool = False,
    ) -> dict[str, Any]:
        url = f"{API_BASE}/{path.lstrip('/')}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self.headers,
                params=params,
                json=payload,
                data=data,
            ) as response:
                retry_after = _retry_after(response.headers.get("Retry-After"))
                raw = await response.read()
                body: dict[str, Any] = {}
                invalid_json = False
                if raw:
                    try:
                        decoded = json.loads(raw.decode("utf-8"))
                        if isinstance(decoded, dict):
                            body = decoded
                        else:
                            invalid_json = True
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        invalid_json = True
                if response.status >= 400:
                    detail = _safe_api_detail(
                        body.get("description")
                        or body.get("message")
                        or body.get("error")
                        or f"HTTP {response.status}",
                        self._token,
                    )
                    raise YandexAPIError(
                        f"Yandex Bot API rejected the request: {detail}",
                        status=response.status,
                        retryable=response.status in {408, 425, 429}
                        or response.status >= 500,
                        retry_after=retry_after,
                    )
                if invalid_json:
                    raise YandexAPIError(
                        "Yandex Bot API returned invalid JSON",
                        status=response.status,
                        retryable=True,
                    )
                if not raw and allow_empty:
                    return {"ok": True}
                if body.get("ok") is False:
                    detail = _safe_api_detail(
                        body.get("description")
                        or body.get("message")
                        or "request failed",
                        self._token,
                    )
                    raise YandexAPIError(
                        f"Yandex Bot API rejected the request: {detail}",
                        status=response.status,
                        retryable=False,
                    )
                if not raw and not allow_empty:
                    raise YandexAPIError(
                        "Yandex Bot API returned an empty response",
                        status=response.status,
                        retryable=True,
                    )
                return body
        except asyncio.CancelledError:
            raise
        except YandexAPIError:
            raise
        except (TimeoutError, aiohttp.ClientError) as exc:
            raise YandexAPIError(
                f"Yandex Bot API network error: {type(exc).__name__}",
                retryable=True,
            ) from exc

    async def download_file(self, file_id: str, *, media_type: str) -> bytes:
        url = f"{API_BASE}/messages/getFile/"
        max_bytes = get_inbound_media_max_bytes()
        try:
            async with self._session.get(
                url,
                headers=self.headers,
                params={"file_id": file_id},
            ) as response:
                if response.status >= 400:
                    raise YandexAPIError(
                        f"Yandex getFile failed with HTTP {response.status}",
                        status=response.status,
                        retryable=response.status in {408, 425, 429}
                        or response.status >= 500,
                    )
                declared = response.headers.get("Content-Length")
                if declared:
                    try:
                        declared_size = int(declared)
                    except (TypeError, ValueError):
                        declared_size = None
                    if declared_size is not None:
                        validate_inbound_media_size(
                            declared_size, media_type=media_type, max_bytes=max_bytes
                        )
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.content.iter_chunked(64 * 1024):
                    total += len(chunk)
                    validate_inbound_media_size(
                        total, media_type=media_type, max_bytes=max_bytes
                    )
                    chunks.append(chunk)
                data = b"".join(chunks)
                if "json" in response.headers.get("Content-Type", "").lower():
                    try:
                        error_body = json.loads(data.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        error_body = {}
                    if isinstance(error_body, dict) and error_body.get("ok") is False:
                        detail = _safe_api_detail(
                            error_body.get("description") or "download failed",
                            self._token,
                        )
                        raise YandexAPIError(
                            f"Yandex getFile rejected the request: {detail}",
                            status=response.status,
                            retryable=False,
                        )
                return data
        except asyncio.CancelledError:
            raise
        except (YandexAPIError, ValueError):
            raise
        except (TimeoutError, aiohttp.ClientError) as exc:
            raise YandexAPIError(
                f"Yandex getFile network error: {type(exc).__name__}",
                retryable=True,
            ) from exc


def _retry_after(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def _extract_webhook_updates(payload: Any) -> list[dict[str, Any]] | None:
    """Validate Yandex's documented getUpdates-compatible webhook envelope."""

    if not isinstance(payload, dict):
        return None
    updates = payload.get("updates")
    if not isinstance(updates, list):
        return None
    if not all(isinstance(item, dict) for item in updates):
        return None
    return updates


@dataclass
class PendingAction:
    kind: str
    session_key: str
    prompt_id: str
    choices: dict[str, str]
    created_at: float


class YandexMessengerAdapter(BasePlatformAdapter):
    """Hermes gateway adapter backed by Yandex Messenger Bot API."""

    splits_long_messages = True

    def __init__(self, config: PlatformConfig) -> None:
        super().__init__(config, Platform(PLATFORM_NAME))
        extra = _extra(config)
        webhook = extra.get("webhook")
        webhook = webhook if isinstance(webhook, dict) else {}

        self.token = _token_for(config)
        self.transport = str(extra.get("transport", "polling")).strip().lower()
        self.poll_interval = _bounded_float(
            extra.get("poll_interval_seconds", 1.0), 1.0, 0.2, 30.0
        )
        self.poll_limit = _bounded_int(
            extra.get("poll_limit", POLL_LIMIT), POLL_LIMIT, 1, 1000
        )
        self.group_mode = str(extra.get("group_mode", "mention")).strip().lower()
        self.channel_mode = str(extra.get("channel_mode", "off")).strip().lower()
        self.group_allowed_chats = set(_as_list(extra.get("group_allowed_chats")))
        self.group_allow_all = _as_bool(extra.get("group_allow_all"), False)
        self.mention_aliases = _as_list(extra.get("mention_aliases"))

        self.webhook_host = str(webhook.get("host", "127.0.0.1")).strip()
        self.webhook_port = _bounded_int(webhook.get("port", 8767), 8767, 1, 65535)
        self.webhook_path = str(
            webhook.get("path", "/yandex-messenger/webhook")
        ).strip()
        self.webhook_public_url = str(webhook.get("public_url", "")).strip()
        self.webhook_manage_registration = _as_bool(
            webhook.get("manage_registration"), False
        )
        self.webhook_secret = os.getenv("YANDEX_MESSENGER_WEBHOOK_SECRET", "").strip()

        self._session: aiohttp.ClientSession | None = None
        self._client: YandexMessengerClient | None = None
        self._poll_task: asyncio.Task | None = None
        self._update_tasks: set[asyncio.Task] = set()
        self._web_app = None
        self._web_runner = None
        self._web_site = None
        self._self: dict[str, Any] = {}
        self._chat_cache: dict[str, dict[str, Any]] = {}
        self._actions: OrderedDict[str, PendingAction] = OrderedDict()
        self._seen_updates: OrderedDict[int, float] = OrderedDict()
        self._offset_path = (
            get_hermes_home() / "state" / "yandex_messenger_offset.json"
        )

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        del is_reconnect
        if aiohttp is None:
            self._set_fatal_error(
                "missing_dep",
                "aiohttp is required for the Yandex Messenger adapter",
                retryable=False,
            )
            return False
        if not self.token:
            self._set_fatal_error(
                "missing_token",
                "YANDEX_MESSENGER_TOKEN is not configured",
                retryable=False,
            )
            return False
        if self.transport not in {"polling", "webhook"}:
            self._set_fatal_error(
                "bad_transport",
                "Yandex transport must be 'polling' or 'webhook'",
                retryable=False,
            )
            return False
        if not self._acquire_platform_lock(
            PLATFORM_NAME, self.token, "Yandex Messenger bot token"
        ):
            return False

        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=30)
        self._session = aiohttp.ClientSession(timeout=timeout)
        self._client = YandexMessengerClient(self.token, self._session)
        try:
            self._self = await self._client.json("self/get", method="GET")
            current_webhook = str(self._self.get("webhook_url") or "")
            if self.transport == "polling":
                if current_webhook:
                    if self.webhook_manage_registration:
                        await self._client.json(
                            "self/update/",
                            payload={"webhook_url": None},
                        )
                    else:
                        raise YandexAPIError(
                            "This bot already has a webhook. Polling and webhooks "
                            "are mutually exclusive; clear it in Yandex or enable "
                            "webhook.manage_registration."
                        )
                self._poll_task = asyncio.create_task(
                    self._poll_loop(), name="yandex-messenger-poll"
                )
            else:
                await self._start_webhook()
                if self.webhook_manage_registration:
                    desired = self._effective_webhook_url()
                    if not desired.startswith("https://"):
                        raise YandexAPIError(
                            "Managed webhook registration requires an HTTPS public_url"
                        )
                    if current_webhook != desired:
                        await self._client.json(
                            "self/update/",
                            payload={"webhook_url": desired},
                        )
            self._mark_connected()
            logger.info(
                "[%s] Connected as %s using %s",
                self.name,
                self._self.get("login") or self._self.get("display_name") or "bot",
                self.transport,
            )
            if self.group_mode == "mention" and not self._mention_tokens():
                logger.warning(
                    "[%s] group_mode=mention but no bot login/mention_aliases "
                    "are available; only slash commands will trigger",
                    self.name,
                )
            return True
        except Exception as exc:
            await self._close_transport()
            self._release_platform_lock()
            retryable = bool(getattr(exc, "retryable", False))
            self._set_fatal_error(
                "connect_failed",
                str(exc),
                retryable=retryable,
            )
            return False

    async def disconnect(self) -> None:
        self._mark_disconnected()
        await self._close_transport()
        self._release_platform_lock()

    async def _close_transport(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            await asyncio.gather(self._poll_task, return_exceptions=True)
            self._poll_task = None
        for task in list(self._update_tasks):
            task.cancel()
        if self._update_tasks:
            await asyncio.gather(*self._update_tasks, return_exceptions=True)
        self._update_tasks.clear()
        if self._web_site is not None:
            with contextlib.suppress(Exception):
                await self._web_site.stop()
            self._web_site = None
        if self._web_runner is not None:
            with contextlib.suppress(Exception):
                await self._web_runner.cleanup()
            self._web_runner = None
        self._web_app = None
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._client = None

    async def _start_webhook(self) -> None:
        from aiohttp import web

        if not _valid_webhook_secret(self.webhook_secret):
            raise YandexAPIError(
                "Webhook mode requires a URL-safe "
                "YANDEX_MESSENGER_WEBHOOK_SECRET of at least 32 characters"
            )
        secret_path = self._secret_webhook_path()
        self._web_app = web.Application(client_max_size=WEBHOOK_BODY_LIMIT)
        self._web_app.router.add_post(secret_path, self._handle_webhook)
        self._web_app.router.add_get("/healthz", self._handle_health)
        self._web_runner = web.AppRunner(self._web_app)
        await self._web_runner.setup()
        self._web_site = web.TCPSite(
            self._web_runner, self.webhook_host, self.webhook_port
        )
        try:
            await self._web_site.start()
        except OSError as exc:
            raise YandexAPIError(
                f"Could not bind webhook on {self.webhook_host}:"
                f"{self.webhook_port}: {exc}",
                retryable=True,
            ) from exc

    def _secret_webhook_path(self) -> str:
        base = "/" + self.webhook_path.strip("/")
        return f"{base}/{self.webhook_secret}"

    def _effective_webhook_url(self) -> str:
        return (
            self.webhook_public_url.rstrip("/")
            + "/"
            + self._secret_webhook_path().lstrip("/")
        )

    async def _handle_health(self, request):
        del request
        from aiohttp import web

        return web.json_response({"ok": True, "platform": PLATFORM_NAME})

    async def _handle_webhook(self, request):
        from aiohttp import web

        try:
            payload = await request.json()
        except (json.JSONDecodeError, ValueError):
            return web.json_response({"ok": False}, status=400)
        updates = _extract_webhook_updates(payload)
        if updates is None:
            return web.json_response({"ok": False}, status=400)

        # Yandex's read deadline is one second. Schedule in-process handling
        # and acknowledge immediately. Yandex retries non-final HTTP
        # responses, but processing after this 2xx remains an in-process task.
        for update in updates:
            update_id = _update_id(update)
            if update_id is not None and not self._remember_update(update_id):
                continue
            task = asyncio.create_task(
                self._process_update(update), name=f"yandex-update-{update_id}"
            )
            self._update_tasks.add(task)
            task.add_done_callback(self._update_tasks.discard)
            task.add_done_callback(self._log_update_failure)
        return web.json_response({"ok": True})

    @staticmethod
    def _log_update_failure(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Yandex webhook update failed", exc_info=exc)

    def _remember_update(self, update_id: int) -> bool:
        if update_id in self._seen_updates:
            self._seen_updates.move_to_end(update_id)
            return False
        self._seen_updates[update_id] = time.monotonic()
        while len(self._seen_updates) > UPDATE_DEDUPE_SIZE:
            self._seen_updates.popitem(last=False)
        return True

    async def _poll_loop(self) -> None:
        offset = await asyncio.to_thread(self._read_offset)
        failures = 0
        while True:
            try:
                assert self._client is not None
                body = await self._client.json(
                    "messages/getUpdates/",
                    method="GET",
                    params={"offset": offset, "limit": self.poll_limit},
                )
                updates = body.get("updates")
                if updates is None:
                    updates = body.get("result", [])
                if not isinstance(updates, list):
                    updates = []
                for update in updates:
                    if not isinstance(update, dict):
                        continue
                    await self._process_update(update)
                    update_id = _update_id(update)
                    if update_id is not None:
                        offset = max(offset, update_id + 1)
                        await asyncio.to_thread(self._write_offset, offset)
                failures = 0
                if not updates:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failures += 1
                delay = min(60.0, (2 ** min(failures, 6)) + random.random())
                requested = getattr(exc, "retry_after", None)
                if requested is not None:
                    delay = max(delay, float(requested))
                logger.warning(
                    "[%s] Polling failed (%s); retrying in %.1fs",
                    self.name,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

    def _read_offset(self) -> int:
        try:
            data = json.loads(self._offset_path.read_text(encoding="utf-8"))
            stored_bot_id = str(data.get("bot_id") or "")
            current_bot_id = str(self._self.get("id") or "")
            if stored_bot_id and current_bot_id and stored_bot_id != current_bot_id:
                logger.warning(
                    "[%s] Ignoring update offset written for a different bot",
                    self.name,
                )
                return 0
            return max(0, int(data.get("next_offset", 0)))
        except FileNotFoundError:
            return 0
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            logger.warning(
                "[%s] Ignoring corrupt update offset at %s",
                self.name,
                self._offset_path,
            )
            return 0

    def _write_offset(self, offset: int) -> None:
        self._offset_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._offset_path.with_name(
            f".{self._offset_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )
        temporary.write_text(
            json.dumps(
                {
                    "bot_id": _string_or_none(self._self.get("id")),
                    "next_offset": int(offset),
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self._offset_path)

    async def _process_update(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            message = update
        bot_request = message.get("bot_request") or update.get("bot_request")
        bot_request = bot_request if isinstance(bot_request, dict) else {}
        server_action = bot_request.get("server_action")
        if isinstance(server_action, dict):
            await self._process_server_action(update, message, server_action)
            return

        sender = message.get("from") or update.get("from") or {}
        if not isinstance(sender, dict) or _as_bool(sender.get("robot"), False):
            return
        chat = message.get("chat") or update.get("chat") or {}
        if not isinstance(chat, dict):
            chat = {}
        chat_type = _normalize_chat_type(chat.get("type"))
        chat_id = self._inbound_chat_id(chat_type, chat, sender)
        text = str(message.get("text") or "")
        if not self._chat_allows_message(chat_type, chat_id, text):
            return
        text = self._strip_mention(text) if chat_type != "dm" else text

        media_urls, media_types = await self._download_attachments(message)
        if not text and media_urls:
            text = "[Attachment]"
        if not text and not media_urls:
            return

        sender_login = str(sender.get("login") or sender.get("id") or "")
        sender_name = str(sender.get("display_name") or sender_login)
        message_id = str(message.get("message_id") or update.get("message_id") or "")
        thread = message.get("thread_id") or update.get("thread_id")
        chat_name = str(chat.get("name") or chat.get("title") or chat_id)
        self._chat_cache[chat_id] = {
            "name": chat_name,
            "type": chat_type,
            "raw": dict(chat),
        }
        source = self.build_source(
            chat_id=chat_id,
            chat_name=chat_name,
            chat_type=chat_type,
            user_id=sender_login,
            user_id_alt=str(sender.get("id") or "") or None,
            user_name=sender_name,
            thread_id=str(thread) if thread not in (None, "") else None,
            message_id=message_id or None,
        )
        event = MessageEvent(
            text=text,
            message_type=_message_type(text, media_types),
            source=source,
            raw_message=update,
            message_id=message_id or None,
            platform_update_id=_update_id(update),
            media_urls=media_urls,
            media_types=media_types,
            reply_to_message_id=_string_or_none(message.get("reply_message_id")),
            metadata={
                "yandex_sender_id": _string_or_none(sender.get("id")),
                "yandex_sender_login": _string_or_none(sender.get("login")),
                "thread_id": _string_or_none(thread),
            },
            timestamp=_timestamp(message.get("timestamp") or update.get("timestamp")),
        )
        await self.handle_message(event)

    def _inbound_chat_id(
        self, chat_type: str, chat: dict[str, Any], sender: dict[str, Any]
    ) -> str:
        if chat_type == "dm":
            identity = sender.get("login") or sender.get("id")
            return f"login:{identity}"
        return f"chat:{chat.get('id')}"

    def _chat_allows_message(
        self, chat_type: str, chat_id: str, text: str
    ) -> bool:
        if chat_type == "dm":
            return True
        bare_chat_id = chat_id[5:] if chat_id.startswith("chat:") else chat_id
        if not self.group_allow_all and bare_chat_id not in self.group_allowed_chats:
            return False
        mode = self.channel_mode if chat_type == "channel" else self.group_mode
        if mode == "off":
            return False
        if mode == "all":
            return True
        is_command = text.lstrip().startswith("/")
        if mode == "commands":
            return is_command
        if mode == "mention":
            return is_command or self._contains_mention(text)
        return False

    def _mention_tokens(self) -> list[str]:
        values = list(self.mention_aliases)
        login = str(self._self.get("login") or "").strip()
        if login:
            values.append(f"@{login}")
            if "@" in login:
                short = login.split("@", 1)[0]
                values.append(f"@{short}")
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized.casefold() not in seen:
                seen.add(normalized.casefold())
                result.append(normalized)
        return sorted(result, key=len, reverse=True)

    def _contains_mention(self, text: str) -> bool:
        folded = text.casefold()
        return any(token.casefold() in folded for token in self._mention_tokens())

    def _strip_mention(self, text: str) -> str:
        result = text
        for token in self._mention_tokens():
            result = re.sub(re.escape(token), "", result, count=1, flags=re.I)
        return result.strip(" \t,:—-")

    async def _download_attachments(
        self, message: dict[str, Any]
    ) -> tuple[list[str], list[str]]:
        if self._client is None:
            return [], []
        urls: list[str] = []
        types: list[str] = []
        images = message.get("images") or []
        if images and isinstance(images, list):
            image_groups = images if any(isinstance(i, list) for i in images) else [images]
            for group in image_groups:
                if not isinstance(group, list):
                    continue
                variants = [item for item in group if isinstance(item, dict)]
                if not variants:
                    continue
                best = max(
                    variants,
                    key=lambda item: int(item.get("width") or 0)
                    * int(item.get("height") or 0),
                )
                file_id = best.get("file_id") or best.get("id")
                if not file_id:
                    continue
                try:
                    data = await self._client.download_file(
                        str(file_id), media_type="image"
                    )
                    urls.append(cache_image_from_bytes(data))
                    types.append(MessageType.PHOTO.value)
                except Exception as exc:
                    logger.warning("[%s] Could not download image: %s", self.name, exc)

        files = message.get("files")
        if files is None:
            single_file = message.get("file")
            files = [single_file] if isinstance(single_file, dict) else []
        if isinstance(files, dict):
            files = [files]
        if isinstance(files, list):
            for attachment in files:
                if not isinstance(attachment, dict):
                    continue
                file_id = attachment.get("file_id") or attachment.get("id")
                if not file_id:
                    continue
                filename = str(attachment.get("name") or "document")
                try:
                    declared = attachment.get("size")
                    if declared is not None:
                        validate_inbound_media_size(
                            int(declared), media_type="document"
                        )
                    data = await self._client.download_file(
                        str(file_id), media_type="document"
                    )
                    urls.append(cache_document_from_bytes(data, filename))
                    types.append(MessageType.DOCUMENT.value)
                except Exception as exc:
                    logger.warning("[%s] Could not download file: %s", self.name, exc)
        return urls, types

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> SendResult:
        del kwargs
        if self._client is None:
            return SendResult(success=False, error="Not connected")
        chunks = self.truncate_message(
            self.format_message(content or ""), max_length=SAFE_TEXT_LIMIT
        )
        message_ids: list[str] = []
        for index, chunk in enumerate(chunks):
            result = await self._send_text(
                chat_id,
                chunk,
                reply_to=reply_to if index == 0 else None,
                metadata=metadata,
            )
            if not result.success:
                if message_ids:
                    result.retryable = False
                    result.error = (
                        f"Partial delivery ({len(message_ids)}/{len(chunks)} chunks): "
                        f"{result.error or 'send failed'}"
                    )
                    result.raw_response = {
                        "partial_delivery": True,
                        "delivered_message_ids": list(message_ids),
                        "failed_chunk": index,
                    }
                return result
            if result.message_id:
                message_ids.append(result.message_id)
        return SendResult(
            success=True,
            message_id=message_ids[-1] if message_ids else None,
            continuation_message_ids=tuple(message_ids[:-1]),
        )

    async def _send_text(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
        suggest_buttons: dict[str, Any] | None = None,
    ) -> SendResult:
        if self._client is None:
            return SendResult(success=False, error="Not connected")
        payload: dict[str, Any] = {
            **_target_params(chat_id),
            "text": content[:TEXT_LIMIT],
            "payload_id": uuid.uuid4().hex,
        }
        if reply_to:
            try:
                payload["reply_message_id"] = int(reply_to)
            except (TypeError, ValueError):
                logger.debug("Ignoring non-numeric reply message id: %r", reply_to)
        thread = _thread_id(metadata)
        if thread is not None:
            payload["thread_id"] = thread
        if suggest_buttons:
            payload["suggest_buttons"] = suggest_buttons
        try:
            body = await self._client.json("messages/sendText/", payload=payload)
            return SendResult(
                success=True,
                message_id=_string_or_none(body.get("message_id")),
                raw_response=body,
            )
        except YandexAPIError as exc:
            return SendResult(
                success=False,
                error=str(exc),
                retryable=exc.retryable,
                retry_after=exc.retry_after,
            )

    async def send_typing(
        self, chat_id: str, metadata: dict[str, Any] | None = None
    ) -> None:
        if self._client is None:
            return
        payload: dict[str, Any] = _target_params(chat_id)
        thread = _thread_id(metadata)
        if thread is not None:
            payload["thread_id"] = thread
        try:
            await self._client.json(
                "messages/sendTyping/", payload=payload, allow_empty=True
            )
        except Exception:
            logger.debug("[%s] sendTyping failed", self.name, exc_info=True)

    async def send_image_file(
        self,
        chat_id: str,
        image_path: str,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> SendResult:
        del kwargs
        result = await self._send_upload(
            "messages/sendImage/",
            "image",
            chat_id,
            image_path,
            reply_to=reply_to,
            metadata=metadata,
        )
        if result.success and caption:
            await self._send_upload_caption(result, chat_id, caption, metadata)
        return result

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        caption: str | None = None,
        file_name: str | None = None,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> SendResult:
        del kwargs
        result = await self._send_upload(
            "messages/sendFile/",
            "document",
            chat_id,
            file_path,
            upload_name=file_name,
            reply_to=reply_to,
            metadata=metadata,
        )
        if result.success and caption:
            await self._send_upload_caption(result, chat_id, caption, metadata)
        return result

    async def _send_upload_caption(
        self,
        upload_result: SendResult,
        chat_id: str,
        caption: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        caption_result = await self.send(chat_id, caption, metadata=metadata)
        if caption_result.success:
            return
        logger.warning(
            "[%s] Attachment uploaded but caption failed: %s",
            self.name,
            caption_result.error,
        )
        raw = (
            dict(upload_result.raw_response)
            if isinstance(upload_result.raw_response, dict)
            else {}
        )
        raw["caption_error"] = caption_result.error or "caption send failed"
        upload_result.raw_response = raw

    async def _send_upload(
        self,
        endpoint: str,
        field: str,
        chat_id: str,
        file_path: str,
        *,
        upload_name: str | None = None,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        if self._client is None or aiohttp is None:
            return SendResult(success=False, error="Not connected")
        safe_path = self.validate_media_delivery_path(file_path)
        if not safe_path:
            return SendResult(success=False, error="Unsafe or missing media path")
        path = Path(safe_path)
        mime = mimetypes.guess_type(upload_name or path.name)[0]
        try:
            with path.open("rb") as file_handle:
                form = aiohttp.FormData()
                for key, value in _target_params(chat_id).items():
                    form.add_field(key, value)
                if reply_to:
                    form.add_field("reply_message_id", str(reply_to))
                thread = _thread_id(metadata)
                if thread is not None:
                    form.add_field("thread_id", str(thread))
                form.add_field(
                    field,
                    file_handle,
                    filename=upload_name or path.name,
                    content_type=mime or "application/octet-stream",
                )
                body = await self._client.json(endpoint, data=form)
            return SendResult(
                success=True,
                message_id=_string_or_none(body.get("message_id")),
                raw_response=body,
            )
        except YandexAPIError as exc:
            return SendResult(
                success=False,
                error=str(exc),
                retryable=exc.retryable,
                retry_after=exc.retry_after,
            )

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        cached = self._chat_cache.get(chat_id)
        if cached:
            return dict(cached)
        target = _target_params(chat_id)
        return {
            "name": next(iter(target.values()), chat_id),
            "type": "group" if "chat_id" in target else "dm",
        }

    async def send_exec_approval(
        self,
        chat_id: str,
        command: str,
        session_key: str,
        description: str = "dangerous command",
        metadata: dict[str, Any] | None = None,
        allow_permanent: bool = True,
        allow_session: bool = True,
        smart_denied: bool = False,
    ) -> SendResult:
        choices = {"once": "✅ Allow once"}
        if not smart_denied and allow_session:
            choices["session"] = "✅ Allow for session"
        if not smart_denied and allow_permanent:
            choices["always"] = "🔒 Always allow"
        choices["deny"] = "❌ Deny"
        preview = command if len(command) <= 4000 else command[:4000] + "…"
        text = (
            "⚠️ **Command approval required**\n\n"
            f"```\n{preview}\n```\n\nReason: {description}"
        )
        return await self._send_action_prompt(
            chat_id,
            text,
            kind="approval",
            session_key=session_key,
            prompt_id="",
            choices=choices,
            metadata=metadata,
        )

    async def send_slash_confirm(
        self,
        chat_id: str,
        title: str,
        message: str,
        session_key: str,
        confirm_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        return await self._send_action_prompt(
            chat_id,
            f"**{title}**\n\n{message}",
            kind="slash_confirm",
            session_key=session_key,
            prompt_id=confirm_id,
            choices={
                "once": "✅ Approve once",
                "always": "🔒 Always approve",
                "cancel": "❌ Cancel",
            },
            metadata=metadata,
        )

    async def send_clarify(
        self,
        chat_id: str,
        question: str,
        choices: list | None,
        clarify_id: str,
        session_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        if not choices:
            from tools.clarify_gateway import mark_awaiting_text

            mark_awaiting_text(clarify_id)
            return await self.send(chat_id, f"❓ {question}", metadata=metadata)
        mapped = {f"choice_{index}": str(choice) for index, choice in enumerate(choices)}
        mapped["other"] = "✏️ Other"
        return await self._send_action_prompt(
            chat_id,
            f"❓ {question}",
            kind="clarify",
            session_key=session_key,
            prompt_id=clarify_id,
            choices=mapped,
            metadata=metadata,
        )

    async def _send_action_prompt(
        self,
        chat_id: str,
        text: str,
        *,
        kind: str,
        session_key: str,
        prompt_id: str,
        choices: dict[str, str],
        metadata: dict[str, Any] | None,
    ) -> SendResult:
        action_id = secrets.token_urlsafe(12)
        action = PendingAction(
            kind=kind,
            session_key=session_key,
            prompt_id=prompt_id,
            choices=dict(choices),
            created_at=time.monotonic(),
        )
        buttons = []
        for index, (choice, label) in enumerate(choices.items()):
            payload = {"action_id": action_id, "choice": choice}
            buttons.append(
                {
                    "id": f"{action_id}-{index}",
                    "title": label[:255],
                    "directives": [
                        {
                            "type": "server_action",
                            "name": "hermes_gateway_action",
                            "payload": payload,
                        }
                    ],
                }
            )
        suggest_buttons = {
            "layout": "true",
            "persist": False,
            "buttons": [buttons[index : index + 2] for index in range(0, len(buttons), 2)],
        }
        result = await self._send_text(
            chat_id,
            text,
            metadata=metadata,
            suggest_buttons=suggest_buttons,
        )
        if result.success:
            self._prune_actions()
            self._actions[action_id] = action
        return result

    async def _process_server_action(
        self,
        update: dict[str, Any],
        message: dict[str, Any],
        server_action: dict[str, Any],
    ) -> None:
        if server_action.get("name") != "hermes_gateway_action":
            return
        payload = server_action.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return
        if not isinstance(payload, dict):
            return
        action_id = str(payload.get("action_id") or "")
        choice = str(payload.get("choice") or "")
        self._prune_actions()
        action = self._actions.get(action_id)
        if action is None or choice not in action.choices:
            return

        sender = message.get("from") or update.get("from") or {}
        chat = message.get("chat") or update.get("chat") or {}
        if not isinstance(sender, dict) or not isinstance(chat, dict):
            return
        chat_type = _normalize_chat_type(chat.get("type"))
        chat_id = self._inbound_chat_id(chat_type, chat, sender)
        if not self._chat_allows_interaction(chat_type, chat_id):
            return
        sender_id = str(sender.get("login") or sender.get("id") or "")
        if self._is_sender_authorized(sender_id, chat_type, chat_id) is not True:
            logger.warning(
                "[%s] Rejected interactive action from unauthorized user %s",
                self.name,
                sender_id,
            )
            return

        self._actions.pop(action_id, None)
        label = action.choices[choice]
        if action.kind == "approval":
            from tools.approval import resolve_gateway_approval

            resolved = resolve_gateway_approval(action.session_key, choice)
            if resolved:
                self.resume_typing_for_chat(chat_id)
            else:
                label = "⌛ Approval expired or was already resolved"
        elif action.kind == "slash_confirm":
            from tools import slash_confirm as slash_confirm_gateway

            result_text = await slash_confirm_gateway.resolve(
                action.session_key, action.prompt_id, choice
            )
            if result_text:
                await self.send(chat_id, result_text)
        elif action.kind == "clarify":
            from tools.clarify_gateway import (
                mark_awaiting_text,
                resolve_gateway_clarify,
            )

            if choice == "other":
                mark_awaiting_text(action.prompt_id)
                label = "Type your answer in your next message."
            else:
                if not resolve_gateway_clarify(action.prompt_id, label):
                    label = "⌛ Prompt expired or was already resolved"
        await self.send(chat_id, f"Selected: {label}")

    def _chat_allows_interaction(self, chat_type: str, chat_id: str) -> bool:
        if chat_type == "dm":
            return True
        bare_chat_id = chat_id[5:] if chat_id.startswith("chat:") else chat_id
        if not self.group_allow_all and bare_chat_id not in self.group_allowed_chats:
            return False
        mode = self.channel_mode if chat_type == "channel" else self.group_mode
        return mode != "off"

    def _prune_actions(self) -> None:
        cutoff = time.monotonic() - ACTION_TTL_SECONDS
        for action_id, action in list(self._actions.items()):
            if action.created_at < cutoff:
                self._actions.pop(action_id, None)
        while len(self._actions) >= ACTION_CACHE_SIZE:
            self._actions.popitem(last=False)


def _update_id(update: dict[str, Any]) -> int | None:
    value = update.get("update_id")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _normalize_chat_type(value: Any) -> str:
    normalized = str(value or "private").strip().lower()
    if normalized in {"private", "dm", "direct"}:
        return "dm"
    if normalized == "channel":
        return "channel"
    return "group"


def _string_or_none(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _timestamp(value: Any) -> datetime:
    try:
        raw = float(value)
        if raw > 10_000_000_000:
            raw /= 1000
        return datetime.fromtimestamp(raw, tz=UTC)
    except (TypeError, ValueError, OSError):
        return datetime.now(UTC)


def _message_type(text: str, media_types: list[str]) -> MessageType:
    if text.lstrip().startswith("/"):
        return MessageType.COMMAND
    if MessageType.PHOTO.value in media_types:
        return MessageType.PHOTO
    if MessageType.DOCUMENT.value in media_types:
        return MessageType.DOCUMENT
    return MessageType.TEXT


def check_requirements() -> bool:
    return aiohttp is not None


def validate_config(config: PlatformConfig) -> bool:
    extra = _extra(config)
    transport = str(extra.get("transport", "polling")).strip().lower()
    if not _token_for(config) or transport not in {"polling", "webhook"}:
        return False
    if transport == "webhook":
        return _valid_webhook_secret(
            os.getenv("YANDEX_MESSENGER_WEBHOOK_SECRET", "").strip()
        )
    return True


def is_connected(config: PlatformConfig) -> bool:
    return validate_config(config)


def _env_enablement() -> dict[str, Any] | None:
    if not os.getenv("YANDEX_MESSENGER_TOKEN"):
        return None
    return {}


async def _standalone_send(
    pconfig: PlatformConfig,
    chat_id: str,
    message: str,
    *,
    thread_id: str | None = None,
    media_files: list[str] | None = None,
    force_document: bool = False,
) -> dict[str, Any]:
    if aiohttp is None:
        return {"error": "aiohttp is not installed"}
    token = _token_for(pconfig)
    if not token or not chat_id:
        return {"error": "Missing Yandex Messenger token or chat target"}
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        client = YandexMessengerClient(token, session)
        metadata = {"thread_id": thread_id} if thread_id else None
        last_message_id: str | None = None
        try:
            for chunk in BasePlatformAdapter.truncate_message(
                message or "", max_length=SAFE_TEXT_LIMIT
            ):
                payload: dict[str, Any] = {
                    **_target_params(chat_id),
                    "text": chunk,
                    "payload_id": uuid.uuid4().hex,
                }
                thread = _thread_id(metadata)
                if thread is not None:
                    payload["thread_id"] = thread
                body = await client.json("messages/sendText/", payload=payload)
                last_message_id = _string_or_none(body.get("message_id"))
            for raw_path in media_files or []:
                path = Path(raw_path)
                if not path.is_file():
                    continue
                image = not force_document and (
                    mimetypes.guess_type(path.name)[0] or ""
                ).startswith("image/")
                field = "image" if image else "document"
                endpoint = (
                    "messages/sendImage/" if image else "messages/sendFile/"
                )
                with path.open("rb") as file_handle:
                    form = aiohttp.FormData()
                    for key, value in _target_params(chat_id).items():
                        form.add_field(key, value)
                    if thread_id:
                        form.add_field("thread_id", str(thread_id))
                    form.add_field(
                        field,
                        file_handle,
                        filename=path.name,
                        content_type=mimetypes.guess_type(path.name)[0]
                        or "application/octet-stream",
                    )
                    body = await client.json(endpoint, data=form)
                last_message_id = _string_or_none(body.get("message_id"))
            return {"success": True, "message_id": last_message_id}
        except Exception as exc:
            return {"error": str(exc)}


def interactive_setup() -> None:
    print()
    print("Yandex Messenger setup")
    print("----------------------")
    print("Create a bot in the Yandex 360 Business admin console, copy its")
    print("one-time OAuth token, then configure the user allowlist.")
    print()
    try:
        from hermes_cli.config import get_env_var, set_env_var
        from hermes_cli.secret_prompt import masked_secret_prompt
    except ImportError:
        print("Set YANDEX_MESSENGER_TOKEN and allowed-user variables manually.")
        return

    existing = get_env_var("YANDEX_MESSENGER_TOKEN")
    suffix = " [keep current]" if existing else ""
    try:
        value = masked_secret_prompt(f"Bot OAuth token{suffix}: ")
        if value:
            set_env_var("YANDEX_MESSENGER_TOKEN", value)
        allowed = input("Allowed Yandex logins (comma-separated): ").strip()
        if allowed:
            set_env_var("YANDEX_MESSENGER_ALLOWED_USERS", allowed)
    except (EOFError, KeyboardInterrupt):
        print()


def register(ctx) -> None:
    """Register this repo as a Hermes platform plugin."""

    ctx.register_platform(
        name=PLATFORM_NAME,
        label="Yandex Messenger",
        adapter_factory=lambda cfg: YandexMessengerAdapter(cfg),
        check_fn=check_requirements,
        validate_config=validate_config,
        is_connected=is_connected,
        required_env=["YANDEX_MESSENGER_TOKEN"],
        install_hint="aiohttp is included in the Hermes messaging dependencies",
        setup_fn=interactive_setup,
        env_enablement_fn=_env_enablement,
        cron_deliver_env_var="YANDEX_MESSENGER_HOME_CHANNEL",
        standalone_sender_fn=_standalone_send,
        allowed_users_env="YANDEX_MESSENGER_ALLOWED_USERS",
        allow_all_env="YANDEX_MESSENGER_ALLOW_ALL_USERS",
        max_message_length=SAFE_TEXT_LIMIT,
        emoji="🟨",
        pii_safe=False,
        allow_update_command=True,
        platform_hint=(
            "You are chatting via Yandex Messenger. It supports Markdown-like "
            "bold, italic, links, inline code, and fenced code blocks. Messages "
            "are limited to 6000 characters and are split automatically. Bots "
            "can only interact with employees in the configured Yandex 360 "
            "organization. In shared chats, address participants by name and "
            "avoid exposing secrets or private-session context."
        ),
    )
