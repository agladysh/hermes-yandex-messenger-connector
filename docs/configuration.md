# Setup and configuration

This guide assumes one Hermes Agent installation and one Yandex Messenger bot.
Hermes profiles are supported: keep each profile's token, configuration, state,
and allowlists in that profile's active `HERMES_HOME`.

This connector is limited to employees of the bot's own Yandex 360
organization. Arbitrary consumer users and organization guests cannot use it;
federated-organization bot access is undocumented and unsupported. Read
[Yandex product and audience boundaries](yandex-product-boundaries.md) before
provisioning an organization or inviting users.

If an assistant is guiding a person through setup, use the
[agent-guided human setup runbook](agent-setup-guide.md). It defines who handles
each step, keeps the bot token out of chat, and includes acceptance and rollback
checkpoints.

## 1. Create the Yandex bot

1. Sign in as a Yandex 360 organization administrator at
   [admin.yandex.ru](https://admin.yandex.ru/).
2. Open **Bots in Yandex Messenger**.
3. Create the bot, choose its name/avatar, and save the generated OAuth token
   immediately.
4. If the token is lost, reissue it and replace the old value in Hermes. Yandex
   revokes the previous token.

Yandex documents bot support only for particular paid Yandex 360 Business
plans, and bots interact only with employees of their organization. The free
consumer Messenger client does not provide the documented organization-bot
token used by this connector. Plan names are changing across Yandex locales,
so confirm that the live plan comparison explicitly includes the Messenger bot
platform instead of buying by a plan name copied from this guide. See the
[official bot administration guide](https://yandex.ru/support/yandex-360/business/admin/en/messenger/bot-platform)
and [official plan comparison](https://yandex.com/support/yandex-360/business/purchase/en/plans/payment-plans).

Do not use a guest invitation as a cheaper substitute for an employee seat:
Yandex explicitly says guests cannot use organization bots. A personal Yandex
account may instead be invited as an organization employee without connecting
a mail domain, but it then belongs to the paid employee population.

## 2. Install and enable the plugin

From a GitHub repository:

```bash
hermes plugins install agladysh/hermes-yandex-messenger-connector --enable
```

Hermes clones the plugin under `$HERMES_HOME/plugins/`. For a local checkout,
symlink or copy the whole repository so `plugin.yaml`, `__init__.py`, and
`adapter.py` remain at the plugin root.

Confirm discovery:

```bash
hermes plugins list
hermes gateway status
```

The manifest plugin ID is `yandex-messenger-platform`; the gateway platform key
is `yandex_messenger`.

## 3. Configure secrets and authorization

Put these in the active profile's `.env`:

```dotenv
YANDEX_MESSENGER_TOKEN=the-one-time-oauth-token
YANDEX_MESSENGER_ALLOWED_USERS=alice@example.org,bob@example.org
YANDEX_MESSENGER_ALLOW_ALL_USERS=false
```

Hermes' gateway authorization layer consumes the two authorization variables.
The adapter uses the sender's documented Yandex `login` as the stable,
operator-readable user ID. The raw Yandex GUID is retained in event metadata
as `yandex_sender_id`.

`YANDEX_MESSENGER_ALLOW_ALL_USERS=true` is suitable only for a deliberately
open development bot. Organization membership limits reach; it does not
replace least-privilege authorization.

Optional detached-delivery default:

```dotenv
YANDEX_MESSENGER_HOME_CHANNEL=login:alice@example.org
```

Targets are intentionally explicit:

| Form | Meaning |
|---|---|
| `login:alice@example.org` | Direct message by Yandex login |
| `chat:0/0/<uuid>` | Group chat or channel by Yandex chat ID |

Bare values still work for compatibility: a value containing `/` is a chat ID;
anything else is a login. New configuration should always use a prefix.

## 4. Configure the platform

Add this to the active profile's `config.yaml`:

```yaml
gateway:
  platforms:
    yandex_messenger:
      enabled: true
      gateway_restart_notification: false
      typing_indicator: true
      extra:
        transport: polling
        poll_interval_seconds: 1.0
        poll_limit: 100
        group_allowed_chats: []
        group_allow_all: false
        group_mode: mention
        channel_mode: off
        mention_aliases: []
```

### Option reference

| Key | Default | Meaning |
|---|---:|---|
| `transport` | `polling` | `polling` or `webhook`; Yandex makes them mutually exclusive |
| `poll_interval_seconds` | `1.0` | Delay after an empty polling response; clamped to 0.2–30 seconds |
| `poll_limit` | `100` | Updates per request; clamped to Yandex's 1–1000 range |
| `group_allowed_chats` | `[]` | Exact Yandex chat IDs allowed to reach Hermes |
| `group_allow_all` | `false` | Disable the chat-ID allowlist; high risk |
| `group_mode` | `mention` | Group activation: `off`, `commands`, `mention`, or `all` |
| `channel_mode` | `off` | Channel activation with the same mode values |
| `mention_aliases` | `[]` | Extra textual spellings recognized as addressing the bot |
| `webhook.host` | `127.0.0.1` | Local HTTP bind address |
| `webhook.port` | `8767` | Local HTTP bind port |
| `webhook.path` | `/yandex-messenger/webhook` | Non-secret base path |
| `webhook.public_url` | empty | Public HTTPS origin, without the secret path |
| `webhook.manage_registration` | `false` | Allow the adapter to change Yandex's `webhook_url` |

Unknown group/channel modes fail closed: the adapter ignores the message.

### Group activation behavior

- `off`: ignore all ordinary messages.
- `commands`: accept only messages beginning with `/`.
- `mention`: accept slash commands or messages containing the bot login/a
  configured alias, then remove the first textual address from the prompt.
- `all`: send every message in an allowed chat to Hermes.

Yandex documents `@` mentions in the user interface, but its Bot API `Update`
type has no structured mention collection. `mention` is therefore a documented
text heuristic. Use `all` for a dedicated Hermes chat, or `commands` when false
positives are unacceptable.

Channels default to `off`. A channel update can identify the sender as a
channel ID rather than an employee login, which is insufficient for the normal
human user allowlist.

## 5. Add direct and group conversations

For direct messages, an allowed employee opens the bot and sends a message.

For an existing group, add the bot through the chat's participant-management
UI, then copy the group ID into `group_allowed_chats`. The ID is the value after
`https://yandex.ru/chat/#/chats/` in the web client's address bar; decode `%2F`
to `/`.

The official Bot API also offers `POST /chats/create/`. A bot-created group
automatically makes the bot an administrator:

```bash
python3 scripts/yandex_probe.py create-chat \
  --name "Hermes team room" \
  --member alice@example.org \
  --member bob@example.org
```

Copy the returned `chat_id` into `group_allowed_chats`.

## 6. Optional webhook mode

Polling is recommended. If webhook ingress is operationally necessary:

1. Generate at least 32 random bytes and store them in
   `YANDEX_MESSENGER_WEBHOOK_SECRET`.
2. Put a TLS reverse proxy in front of the local bind.
3. Route only
   `/yandex-messenger/webhook/<secret>` to the connector.
4. Set `transport: webhook` and `webhook.public_url`.
5. Leave `manage_registration: false` until ingress is verified, then set the
   webhook in the Yandex admin UI or explicitly opt into managed registration.

Example:

```yaml
gateway:
  platforms:
    yandex_messenger:
      enabled: true
      extra:
        transport: webhook
        group_allowed_chats:
          - "0/0/example"
        group_mode: mention
        webhook:
          host: 127.0.0.1
          port: 8767
          path: /yandex-messenger/webhook
          public_url: https://messenger-bot.example.org
          manage_registration: true
```

The effective URL becomes:

```text
https://messenger-bot.example.org/yandex-messenger/webhook/<secret>
```

Yandex's official webhook documentation does not describe a request signature
or verification header. Treat the secret path as a compensating control, keep
the bind private, and enforce TLS/rate limits at the reverse proxy.
