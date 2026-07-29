#!/usr/bin/env python3
"""Load and instantiate the plugin against a real Hermes source checkout."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    default = Path(__file__).resolve().parents[2] / "hermes-agent"
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--hermes-source",
        type=Path,
        default=default,
        help=f"Hermes Agent source checkout (default: {default})",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    source = args.hermes_source.expanduser().resolve()
    if not (source / "gateway" / "platform_registry.py").is_file():
        print(f"Not a Hermes source checkout: {source}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(source))

    from gateway.config import Platform, PlatformConfig
    from gateway.platform_registry import PlatformEntry, platform_registry
    from gateway.platforms.base import BasePlatformAdapter

    import adapter

    class Context:
        def register_platform(
            self,
            name,
            label,
            adapter_factory,
            check_fn,
            validate_config=None,
            required_env=None,
            install_hint="",
            **entry_kwargs,
        ):
            platform_registry.register(
                PlatformEntry(
                    name=name,
                    label=label,
                    adapter_factory=adapter_factory,
                    check_fn=check_fn,
                    validate_config=validate_config,
                    required_env=required_env or [],
                    install_hint=install_hint,
                    source="plugin",
                    plugin_name="yandex-messenger-platform",
                    **entry_kwargs,
                )
            )

    adapter.register(Context())
    entry = platform_registry.get(adapter.PLATFORM_NAME)
    assert entry is not None
    assert entry.source == "plugin"
    assert entry.allowed_users_env == "YANDEX_MESSENGER_ALLOWED_USERS"
    assert entry.standalone_sender_fn is adapter._standalone_send
    assert Platform(adapter.PLATFORM_NAME).value == adapter.PLATFORM_NAME

    instance = entry.adapter_factory(
        PlatformConfig(
            enabled=True,
            token="smoke-test-token",
            extra={"transport": "polling", "group_allowed_chats": []},
        )
    )
    assert isinstance(instance, BasePlatformAdapter)
    assert instance.platform is Platform(adapter.PLATFORM_NAME)
    assert instance.splits_long_messages
    print(
        "Hermes plugin smoke test passed:",
        adapter.PLATFORM_NAME,
        type(instance).__name__,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
