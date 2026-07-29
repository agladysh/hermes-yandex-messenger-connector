#!/usr/bin/env python3
"""Check the governed public documentation and llms.txt orientation."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_PREFIX = (
    "https://raw.githubusercontent.com/"
    "agladysh/hermes-yandex-messenger-connector/main/"
)
TREE_PREFIX = (
    "https://github.com/"
    "agladysh/hermes-yandex-messenger-connector/tree/main/"
)

REQUIRED_LOCAL_TARGETS = (
    "docs/agent-setup-guide.md",
    "docs/configuration.md",
    "docs/operations.md",
    "SECURITY.md",
    "plugin.yaml",
    "adapter.py",
    "docs/architecture.md",
    "docs/testing.md",
    "docs/research.md",
    "LICENSE",
)

REQUIRED_FACTS = (
    "agladysh/hermes-yandex-messenger-connector",
    "YANDEX_MESSENGER_ALLOW_ALL_USERS=false",
    "/opt/hermes/.venv/bin/hermes",
    "/opt/data",
    "/opt/data/plugins/yandex-messenger-platform",
    "Never request, accept, print, or read back a Yandex OAuth token",
    "Installation is not acceptance",
    "Keep the deployment goal active through real acceptance",
    "free consumer Yandex Messenger is not sufficient",
)

LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^)]+)\)")


def main() -> int:
    errors: list[str] = []
    llms_path = ROOT / "llms.txt"
    llms = llms_path.read_text(encoding="utf-8")

    lines = llms.splitlines()
    if not lines or lines[0] != "# Hermes Yandex Messenger Connector":
        errors.append("llms.txt must start with the canonical H1")

    first_content = next((line for line in lines[1:] if line.strip()), "")
    if not first_content.startswith("> "):
        errors.append("llms.txt must place its summary blockquote after the H1")

    for fact in REQUIRED_FACTS:
        if fact not in llms:
            errors.append(f"llms.txt is missing governed fact: {fact}")

    for relative in REQUIRED_LOCAL_TARGETS:
        target = ROOT / relative
        if not target.exists():
            errors.append(f"canonical documentation target is missing: {relative}")
        expected_url = f"{RAW_PREFIX}{relative}"
        if expected_url not in llms:
            errors.append(f"llms.txt does not link canonical target: {relative}")

    for url in LINK_RE.findall(llms):
        if url.startswith(RAW_PREFIX):
            relative = url.removeprefix(RAW_PREFIX)
            if not (ROOT / relative).exists():
                errors.append(f"llms.txt raw link has no local target: {relative}")
        elif url.startswith(TREE_PREFIX):
            relative = url.removeprefix(TREE_PREFIX)
            if not (ROOT / relative).exists():
                errors.append(f"llms.txt tree link has no local target: {relative}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "[LLM/agent orientation](llms.txt)" not in readme:
        errors.append("README.md must link llms.txt")
    if "[Project and documentation governance](GOVERNANCE.md)" not in readme:
        errors.append("README.md must link GOVERNANCE.md")

    governance = (ROOT / "GOVERNANCE.md").read_text(encoding="utf-8")
    governance_flat = " ".join(governance.split())
    for required in (
        "llms.txt",
        "make docs",
        "make check",
        "Evergreen triggers",
        "Progress ownership",
        "smallest concrete action",
        "nothing is required from you",
    ):
        if required not in governance_flat:
            errors.append(f"GOVERNANCE.md is missing required contract: {required}")

    if errors:
        print("documentation governance check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "documentation governance check passed:",
        f"{len(REQUIRED_LOCAL_TARGETS)} canonical targets,",
        f"{len(REQUIRED_FACTS)} governed facts",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
