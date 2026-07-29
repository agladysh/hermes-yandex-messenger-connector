#!/usr/bin/env python3
"""Dependency-free diagnostic client for the Yandex Messenger Bot API.

This script deliberately stays separate from the Hermes adapter. It is useful
before installation: verify a token, list visible chats, inspect the next
unacknowledged update, send a smoke-test message, or create a bot-administered
group chat.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_BASE = "https://botapi.messenger.yandex.net/bot/v1"


def request(
    token: str,
    path: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    url = f"{API_BASE}/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = None
    headers = {"Authorization": f"OAuth {token}"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        detail = raw.decode("utf-8", errors="replace")
        raise RuntimeError(f"Yandex API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Yandex API connection failed: {exc.reason}") from exc
    return json.loads(raw) if raw else {"ok": True}


def target(value: str) -> dict[str, str]:
    if value.startswith("login:"):
        return {"login": value[6:]}
    if value.startswith("chat:"):
        return {"chat_id": value[5:]}
    raise ValueError("Target must start with login: or chat:")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--token-env",
        default="YANDEX_MESSENGER_TOKEN",
        help="environment variable containing the OAuth token",
    )
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("self", help="show bot identity and webhook state")

    chats = sub.add_parser("chats", help="list chats visible to the bot")
    chats.add_argument("--limit", type=int, default=100)
    chats.add_argument("--offset", default="")

    updates = sub.add_parser(
        "peek-updates",
        help="read updates at offset 0 without advancing/deleting any positive IDs",
    )
    updates.add_argument("--limit", type=int, default=10)

    send = sub.add_parser("send", help="send a mutation smoke test")
    send.add_argument("--target", required=True, help="login:<login> or chat:<id>")
    send.add_argument("--text", required=True)

    create = sub.add_parser(
        "create-chat",
        help="create a group chat; the bot becomes an administrator",
    )
    create.add_argument("--name", required=True)
    create.add_argument("--description", default="")
    create.add_argument("--member", action="append", default=[])
    return result


def main() -> int:
    args = parser().parse_args()
    token = os.getenv(args.token_env, "").strip()
    if not token:
        print(f"{args.token_env} is empty", file=sys.stderr)
        return 2
    try:
        if args.command == "self":
            result = request(token, "self/get")
        elif args.command == "chats":
            params = {"limit": max(1, min(args.limit, 1000))}
            if args.offset:
                params["offset"] = args.offset
            result = request(token, "chats/get/", params=params)
        elif args.command == "peek-updates":
            result = request(
                token,
                "messages/getUpdates/",
                params={"offset": 0, "limit": max(1, min(args.limit, 1000))},
            )
        elif args.command == "send":
            result = request(
                token,
                "messages/sendText/",
                method="POST",
                payload={**target(args.target), "text": args.text},
            )
        else:
            result = request(
                token,
                "chats/create/",
                method="POST",
                payload={
                    "name": args.name,
                    "description": args.description,
                    "members": [{"login": login} for login in args.member],
                    "channel": False,
                },
            )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
