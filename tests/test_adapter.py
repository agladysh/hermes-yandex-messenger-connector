from __future__ import annotations

import sys
import types

import pytest

from tests.hermes_stubs import install

install()

from gateway.config import PlatformConfig  # noqa: E402
from gateway.platforms.base import MessageType  # noqa: E402

import adapter  # noqa: E402


class FakeClient:
    def __init__(self) -> None:
        self.calls = []
        self.next_id = 100

    async def json(self, path, **kwargs):
        self.next_id += 1
        self.calls.append((path, kwargs))
        return {"ok": True, "message_id": self.next_id}

    async def download_file(self, file_id, *, media_type):
        del file_id, media_type
        return b"%PDF-test"


def make_adapter(**extra):
    instance = adapter.YandexMessengerAdapter(
        PlatformConfig(token="test-token", extra=extra)
    )
    instance._client = FakeClient()
    instance._self = {
        "login": "hermes.bot@example.com",
        "display_name": "Hermes",
    }
    return instance


def test_target_parameters_are_explicit_and_backward_compatible():
    assert adapter._target_params("login:alice") == {"login": "alice"}
    assert adapter._target_params("chat:0/0/abc") == {"chat_id": "0/0/abc"}
    assert adapter._target_params("0/0/abc") == {"chat_id": "0/0/abc"}
    assert adapter._target_params("alice") == {"login": "alice"}


def test_webhook_requires_documented_updates_envelope():
    assert adapter._extract_webhook_updates({"updates": [{"update_id": 1}]}) == [
        {"update_id": 1}
    ]
    assert adapter._extract_webhook_updates({"update_id": 1}) is None
    assert adapter._extract_webhook_updates([{"update_id": 1}]) is None
    assert adapter._extract_webhook_updates({"updates": ["bad"]}) is None


def test_group_defaults_are_deny_by_chat_and_mention_gated():
    instance = make_adapter(
        group_allowed_chats=["0/0/allowed"],
        mention_aliases=["@hermes"],
    )
    assert not instance._chat_allows_message(
        "group", "chat:0/0/denied", "@hermes hello"
    )
    assert not instance._chat_allows_message(
        "group", "chat:0/0/allowed", "background conversation"
    )
    assert instance._chat_allows_message(
        "group", "chat:0/0/allowed", "@hermes hello"
    )
    assert instance._chat_allows_message(
        "group", "chat:0/0/allowed", "/status"
    )


@pytest.mark.asyncio
async def test_direct_and_group_updates_become_hermes_events():
    instance = make_adapter(
        group_allowed_chats=["0/0/team"],
        mention_aliases=["@hermes"],
    )
    await instance._process_update(
        {
            "update_id": 7,
            "message_id": 70,
            "timestamp": 1_700_000_000,
            "chat": {"type": "private"},
            "from": {
                "id": "guid-alice",
                "login": "alice",
                "display_name": "Alice",
                "robot": False,
            },
            "text": "hello",
        }
    )
    await instance._process_update(
        {
            "update_id": 8,
            "message_id": 80,
            "timestamp": 1_700_000_001,
            "chat": {"type": "group", "id": "0/0/team"},
            "from": {
                "id": "guid-bob",
                "login": "bob",
                "display_name": "Bob",
                "robot": False,
            },
            "text": "@hermes summarize this",
        }
    )

    assert [event.text for event in instance.events] == [
        "hello",
        "summarize this",
    ]
    assert instance.events[0].source.chat_id == "login:alice"
    assert instance.events[0].source.user_id == "alice"
    assert instance.events[1].source.chat_id == "chat:0/0/team"
    assert instance.events[1].source.chat_type == "group"


@pytest.mark.asyncio
async def test_send_chunks_and_routes_group_target():
    instance = make_adapter()
    content = "x" * (adapter.SAFE_TEXT_LIMIT + 10)
    result = await instance.send("chat:0/0/team", content)

    assert result.success
    assert len(instance._client.calls) == 2
    first_payload = instance._client.calls[0][1]["payload"]
    second_payload = instance._client.calls[1][1]["payload"]
    assert first_payload["chat_id"] == "0/0/team"
    assert len(first_payload["text"]) == adapter.SAFE_TEXT_LIMIT
    assert first_payload["payload_id"] != second_payload["payload_id"]


@pytest.mark.asyncio
async def test_suggest_button_uses_documented_server_action_shape():
    instance = make_adapter()
    result = await instance.send_clarify(
        "login:alice",
        "Which environment?",
        ["staging", "production"],
        "clarify-1",
        "session-1",
    )

    assert result.success
    payload = instance._client.calls[-1][1]["payload"]
    directive = payload["suggest_buttons"]["buttons"][0][0]["directives"][0]
    assert directive["type"] == "server_action"
    assert directive["name"] == "hermes_gateway_action"
    assert isinstance(directive["payload"], dict)
    assert "session-1" not in str(directive["payload"])


@pytest.mark.asyncio
async def test_server_action_requires_auth_and_resolves_server_side_state():
    resolved = []
    approval_module = types.ModuleType("tools.approval")
    approval_module.resolve_gateway_approval = (
        lambda session_key, choice: resolved.append((session_key, choice)) or 1
    )
    tools_module = types.ModuleType("tools")
    tools_module.approval = approval_module
    sys.modules["tools"] = tools_module
    sys.modules["tools.approval"] = approval_module

    instance = make_adapter()
    instance._authorization_check = lambda user_id, chat_type, chat_id: user_id == "alice"
    await instance.send_exec_approval(
        "login:alice", "echo safe", "session-secret"
    )
    action_id = next(iter(instance._actions))
    update = {
        "update_id": 9,
        "message_id": 90,
        "timestamp": 1_700_000_002,
        "chat": {"type": "private"},
        "from": {
            "id": "guid-alice",
            "login": "alice",
            "display_name": "Alice",
            "robot": False,
        },
        "bot_request": {
            "server_action": {
                "name": "hermes_gateway_action",
                "payload": {"action_id": action_id, "choice": "once"},
            }
        },
    }
    await instance._process_update(update)

    assert resolved == [("session-secret", "once")]
    assert action_id not in instance._actions
    assert instance.typing_resumed == ["login:alice"]


@pytest.mark.asyncio
async def test_group_server_action_still_requires_chat_allowlist():
    resolved = []
    approval_module = types.ModuleType("tools.approval")
    approval_module.resolve_gateway_approval = (
        lambda session_key, choice: resolved.append((session_key, choice)) or 1
    )
    tools_module = types.ModuleType("tools")
    tools_module.approval = approval_module
    sys.modules["tools"] = tools_module
    sys.modules["tools.approval"] = approval_module

    instance = make_adapter(group_allowed_chats=["0/0/allowed"])
    instance._authorization_check = lambda user_id, chat_type, chat_id: True
    await instance.send_exec_approval(
        "chat:0/0/allowed", "echo safe", "session-secret"
    )
    action_id = next(iter(instance._actions))
    await instance._process_update(
        {
            "update_id": 10,
            "message_id": 100,
            "timestamp": 1_700_000_003,
            "chat": {"type": "group", "id": "0/0/denied"},
            "from": {
                "id": "guid-alice",
                "login": "alice",
                "display_name": "Alice",
                "robot": False,
            },
            "bot_request": {
                "server_action": {
                    "name": "hermes_gateway_action",
                    "payload": {"action_id": action_id, "choice": "once"},
                }
            },
        }
    )

    assert resolved == []
    assert action_id in instance._actions


def test_message_type_prefers_commands_then_media():
    assert adapter._message_type("/status", []) is MessageType.COMMAND
    assert (
        adapter._message_type("", [MessageType.PHOTO.value])
        is MessageType.PHOTO
    )
