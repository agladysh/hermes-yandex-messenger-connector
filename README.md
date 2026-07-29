# Hermes ↔ Yandex Messenger

A native [Hermes Agent](https://github.com/NousResearch/hermes-agent) platform
plugin for Yandex Messenger in Yandex 360 for Business.

> **Experimental:** no end-to-end Yandex tenant test has been run. The code is
> contract-tested and has been installed on managed Hermes `v0.19.0`, but no
> real bot token, Bot API request, employee message, or group exchange has been
> exercised. Installation is not acceptance.

It lets employees chat with Hermes in direct messages and allows Hermes to
participate safely in selected group chats. It uses the official Yandex
Messenger Bot API—no browser automation, message scraping, MCP bridge, or
Hermes core fork.

This is an internal-organization connector. Yandex documents that bots interact
only with employees of their own organization, forbids bot direct messages to
outside users, and says organization guests cannot use bots. It is not a bot
for arbitrary free/consumer Messenger accounts. See
[Yandex product and audience boundaries](docs/yandex-product-boundaries.md).

## Implemented and contract-tested

- Direct messages and group chats through the normal Hermes gateway/session
  pipeline
- Polling with an atomic, profile-local update offset (recommended default)
- Optional webhook server with a secret URL path
- Per-user Hermes allowlists plus a separate group-chat allowlist
- Group activation modes: `off`, slash `commands`, textual `mention`, or `all`
- Smart splitting below Yandex's 6000-character limit
- Native typing indicators, inbound/outbound files, and images
- Native Yandex SuggestButtons for command approvals, slash confirmations, and
  clarification choices
- Replies and best-effort thread routing when Yandex supplies thread metadata
- Detached/cron delivery through the Hermes platform registry
- Cross-profile token locking using Hermes' own gateway lock

Current limitations are documented in [Architecture](docs/architecture.md) and
[Operations](docs/operations.md). Most importantly, Yandex's documented Update
schema does not expose structured mention or inbound thread fields.

## Quick start

Prerequisites:

- A qualifying **paid** Yandex 360 for Business plan and organization-admin
  access; the free consumer Messenger does not provide the documented bot
  provisioning used here
- A current Hermes Agent installation with messaging dependencies
- A Yandex Messenger bot OAuth token

Create the bot in `admin.yandex.ru` under **Bots in Yandex Messenger**. Save the
token immediately: Yandex shows it once and stores no retrievable copy.

Install from the public GitHub repository:

```bash
hermes plugins install agladysh/hermes-yandex-messenger-connector --enable
```

For local development, place or symlink this repository at:

```text
$HERMES_HOME/plugins/yandex-messenger-platform/
```

Add the secret and authorization policy to the active Hermes profile's `.env`:

```dotenv
YANDEX_MESSENGER_TOKEN=replace-me
YANDEX_MESSENGER_ALLOWED_USERS=alice@example.org,bob@example.org
YANDEX_MESSENGER_ALLOW_ALL_USERS=false
```

Copy the `yandex_messenger` block from
[`examples/config.yaml`](examples/config.yaml) into the active profile's
`config.yaml`. Start with direct messages only; add a group ID to
`group_allowed_chats` after verifying it.

Then restart the gateway:

```bash
hermes gateway restart
hermes status
```

The diagnostic client can verify the token without starting Hermes:

```bash
python3 scripts/yandex_probe.py self
python3 scripts/yandex_probe.py chats
python3 scripts/yandex_probe.py peek-updates
```

`peek-updates` uses offset `0`, which does not delete positive update IDs.
Do not run a second polling consumer alongside Hermes.

## Documentation map

- [LLM/agent orientation](llms.txt)
- [Project and documentation governance](GOVERNANCE.md)
- [Setup and configuration](docs/configuration.md)
- [Agent-guided human setup runbook](docs/agent-setup-guide.md)
- [Yandex product, tenancy, audience, and validation boundaries](docs/yandex-product-boundaries.md)
- [Operations and troubleshooting](docs/operations.md)
- [Architecture and security boundaries](docs/architecture.md)
- [Research trace and primary sources](docs/research.md)
- [Testing and release gates](docs/testing.md)
- [Security policy](SECURITY.md)
- [Architecture decisions](docs/adr/)

## License

[MIT](LICENSE)

## Development

```bash
uv sync --cache-dir .uv-cache --group dev
make check
```

Unit tests use narrow Hermes interface stubs, so they do not pull the full
inference stack. The release gate also includes a plugin-loader smoke test
against the pinned Hermes checkout; see [Testing](docs/testing.md).
