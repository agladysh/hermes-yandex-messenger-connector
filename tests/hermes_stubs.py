"""Minimal Hermes API stubs for dependency-light connector unit tests.

These are not a replacement for the real plugin-loader smoke test documented
in ``docs/testing.md``. They keep protocol and routing tests runnable without
installing the full Hermes inference stack.
"""

from __future__ import annotations

import os
import sys
import tempfile
import types
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


def install() -> None:
    gateway = types.ModuleType("gateway")
    config = types.ModuleType("gateway.config")
    platforms = types.ModuleType("gateway.platforms")
    base = types.ModuleType("gateway.platforms.base")
    constants = types.ModuleType("hermes_constants")

    class Platform:
        def __init__(self, value: str) -> None:
            self.value = value

    @dataclass
    class PlatformConfig:
        enabled: bool = True
        token: str | None = None
        extra: dict[str, Any] = field(default_factory=dict)

    class MessageType(Enum):
        TEXT = "text"
        PHOTO = "photo"
        DOCUMENT = "document"
        COMMAND = "command"

    @dataclass
    class SendResult:
        success: bool
        message_id: str | None = None
        error: str | None = None
        raw_response: Any = None
        retryable: bool = False
        retry_after: float | None = None
        continuation_message_ids: tuple = ()

    @dataclass
    class MessageEvent:
        text: str
        message_type: MessageType = MessageType.TEXT
        source: Any = None
        raw_message: Any = None
        message_id: str | None = None
        platform_update_id: int | None = None
        media_urls: list[str] = field(default_factory=list)
        media_types: list[str] = field(default_factory=list)
        reply_to_message_id: str | None = None
        metadata: dict[str, Any] = field(default_factory=dict)
        timestamp: datetime = field(default_factory=datetime.now)

    class BasePlatformAdapter:
        splits_long_messages = False

        def __init__(self, cfg: PlatformConfig, platform: Platform) -> None:
            self.config = cfg
            self.platform = platform
            self.events: list[MessageEvent] = []
            self._authorization_check = None
            self.typing_resumed: list[str] = []

        @property
        def name(self) -> str:
            return self.platform.value

        @staticmethod
        def truncate_message(content: str, max_length: int = 4096) -> list[str]:
            return [
                content[index : index + max_length]
                for index in range(0, len(content), max_length)
            ] or [""]

        @staticmethod
        def validate_media_delivery_path(path: str) -> str | None:
            resolved = Path(path).resolve()
            return str(resolved) if resolved.is_file() else None

        def build_source(self, **kwargs):
            return types.SimpleNamespace(platform=self.platform, **kwargs)

        async def handle_message(self, event: MessageEvent) -> None:
            self.events.append(event)

        def format_message(self, content: str) -> str:
            return content

        def _is_sender_authorized(self, user_id, chat_type=None, chat_id=None):
            if self._authorization_check is None:
                return None
            return bool(self._authorization_check(user_id, chat_type, chat_id))

        def resume_typing_for_chat(self, chat_id: str) -> None:
            self.typing_resumed.append(chat_id)

        def _mark_connected(self) -> None:
            pass

        def _mark_disconnected(self) -> None:
            pass

        def _set_fatal_error(self, *args, **kwargs) -> None:
            pass

        def _acquire_platform_lock(self, *args, **kwargs) -> bool:
            return True

        def _release_platform_lock(self) -> None:
            pass

    def _cache(prefix: str, data: bytes, suffix: str) -> str:
        target = Path(tempfile.gettempdir()) / f"{prefix}-{len(data)}{suffix}"
        target.write_bytes(data)
        return str(target)

    config.Platform = Platform
    config.PlatformConfig = PlatformConfig
    base.BasePlatformAdapter = BasePlatformAdapter
    base.MessageEvent = MessageEvent
    base.MessageType = MessageType
    base.SendResult = SendResult
    base.cache_document_from_bytes = (
        lambda data, filename: _cache("yandex-document", data, Path(filename).suffix)
    )
    base.cache_image_from_bytes = lambda data: _cache("yandex-image", data, ".jpg")
    base.get_inbound_media_max_bytes = lambda: 128 * 1024 * 1024
    base.validate_inbound_media_size = (
        lambda size, **kwargs: (
            None
            if size <= kwargs.get("max_bytes", 128 * 1024 * 1024)
            else (_ for _ in ()).throw(ValueError("too large"))
        )
    )
    constants.get_hermes_home = lambda: Path(
        os.environ.get("TEST_HERMES_HOME", tempfile.gettempdir())
    )

    sys.modules["gateway"] = gateway
    sys.modules["gateway.config"] = config
    sys.modules["gateway.platforms"] = platforms
    sys.modules["gateway.platforms.base"] = base
    sys.modules["hermes_constants"] = constants
