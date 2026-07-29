# Operations

## Preflight

Verify the Yandex credential before involving Hermes:

```bash
python3 scripts/yandex_probe.py self
```

A healthy response includes `ok`, the bot `id`, `login`, `display_name`,
organization IDs, and `webhook_url`.

Check these invariants:

- The returned organization is the intended Yandex 360 organization.
- `webhook_url` is empty/null for polling mode.
- `webhook_url` exactly matches the secret effective URL for webhook mode.
- The token is present only in the active Hermes profile's `.env` or external
  secret injection, never in `config.yaml` or repository files.

## First deployment sequence

1. Start with `transport: polling`, `group_allowed_chats: []`, and explicit
   `YANDEX_MESSENGER_ALLOWED_USERS`.
2. Restart Hermes and send `/status` in a direct chat.
3. Verify that an unlisted employee is paired/rejected according to the Hermes
   gateway policy.
4. Create or join one dedicated group.
5. Get its ID with the web address bar or:

   ```bash
   python3 scripts/yandex_probe.py chats
   ```

6. Add that exact ID to `group_allowed_chats`.
7. Start with `group_mode: commands`; test `/status`.
8. Move to `mention` or `all` only after confirming the chat's intended trust
   boundary.
9. Test file input, file output, an approval prompt, and a gateway restart.

Do not run `yandex_probe.py peek-updates` repeatedly while the gateway is
polling. Offset zero does not delete updates, but a second reader makes
diagnosis confusing. Never run another consumer with a positive offset against
the same bot.

## Group-chat operating model

The safest pattern is one Hermes profile per materially different trust zone:

- a private/operator profile with broad tools and private knowledge;
- a team-chat profile with narrowly scoped tools and group-appropriate memory;
- separate bot tokens when failure or data domains must be isolated.

Hermes profile routing can further route chats, but a route changes the agent
runtime—it does not change what the Yandex bot can receive. Keep the connector's
group allowlist as the first chat-level boundary.

`group_sessions_per_user` is a Hermes setting. Keeping its default creates
separate conversational state per participant in a group; disabling it creates
a shared session for the room. Choose intentionally and document it in the
deployment's privacy model.

## Polling state and recovery

The connector persists:

```text
$HERMES_HOME/state/yandex_messenger_offset.json
```

Example:

```json
{
  "bot_id": "103ecea2-e303-478d-91a7-b6d423ace527",
  "next_offset": 1571242,
  "updated_at": "2026-07-29T12:00:00+00:00"
}
```

Yandex erases pending updates with IDs lower than the `offset` in a
`getUpdates` request. Therefore:

- back up the file before manual changes;
- stop the gateway before changing it;
- never copy the offset between bot tokens or Hermes profiles;
- decreasing/removing it can replay any still-retained updates;
- increasing it can permanently skip pending updates.

The adapter writes through a temporary file and atomic rename. A corrupt file
fails to offset zero and logs a warning.

## Token rotation

Yandex token reissue revokes the old token.

1. Stop the gateway or prepare a short outage.
2. Reissue and securely capture the token in the Yandex admin console.
3. Replace `YANDEX_MESSENGER_TOKEN` in the active Hermes secret source.
4. Restart the gateway.
5. Run `scripts/yandex_probe.py self` in an environment holding the new token.
6. Revoke/remove any stale copies from deployment secret stores.

Do not paste a token into issue reports, chat messages, shell history, or
diagnostic output. API exceptions intentionally omit the authorization header.

## Webhook operations

Polling and webhooks cannot be active together.

Before switching to webhook:

- expose only HTTPS publicly;
- keep the connector bind on loopback or a private interface;
- use the secret URL path;
- cap request bodies and rate-limit at the proxy;
- configure proxy upstream timeouts below Yandex's one-second read deadline;
- monitor `5xx`, latency, restarts, and callback processing errors.

The connector's health endpoint is local and unsecret:

```text
GET /healthz
```

Do not expose it unless the proxy needs it.

When `webhook.manage_registration=true`, connect updates Yandex's webhook URL
if it differs. Disconnect deliberately does not clear it: clearing on every
restart creates an avoidable race. Switch back to polling by enabling managed
registration for the polling start (which sends `webhook_url: null`) or clear
the URL in the Yandex admin UI first.

## Observability

Useful log events:

- connected bot login and selected transport;
- polling failure and bounded retry delay;
- corrupt offset warning;
- group mention configuration warning;
- rejected unauthorized button callback;
- attachment download failure;
- webhook update task failure;
- token-lock conflict with another gateway process.

The connector does not log message bodies, OAuth tokens, action payload
secrets, or downloaded attachment bytes.

Recommended external checks:

- `hermes status` reports Yandex Messenger as configured;
- the gateway process is live;
- polling error rate/retry delay stays low;
- webhook response latency stays below one second if enabled;
- the state offset advances when messages arrive;
- token rotation date and responsible owner are recorded.

## Troubleshooting

### Platform is missing

- Confirm the installed directory contains `plugin.yaml` and `__init__.py` at
  its root.
- Run `hermes plugins list`.
- Enable `yandex-messenger-platform`.
- Verify the Hermes checkout is recent enough to support plugin platforms.

### Missing or invalid token

- Run `scripts/yandex_probe.py self`.
- Confirm the secret is in the active profile, not another `HERMES_HOME`.
- A reissued token invalidates the previous one immediately.

### Polling receives nothing

- Check `self` reports no webhook URL.
- Confirm only one gateway uses the token; the token lock prevents local
  duplicates, not consumers on other hosts.
- Confirm the bot is a member/admin/subscriber of the chat.
- Inspect the stored offset and Yandex chat visibility.

### Direct message is rejected

- Use the full login for non-`yandex.ru` domains.
- Add the login to `YANDEX_MESSENGER_ALLOWED_USERS`.
- Check the employee and bot belong to the same organization and privacy
  settings permit the conversation.

### Group message is ignored

- Use the decoded exact group ID without the `chat:` prefix in
  `group_allowed_chats`.
- Confirm `group_allow_all` is not being relied on accidentally.
- Check `group_mode`.
- In `mention` mode, add the exact visible address to `mention_aliases`.
- Try `/status`, which is accepted in `commands` and `mention` modes.

### Channel message is ignored

`channel_mode` defaults to `off`. Channel events can identify the posting
channel rather than a human login, so enabling agent interaction there requires
a separate authorization decision. Use group chats for conversational agents.

### Buttons do nothing

- The clicking user must pass the current Hermes authorization policy.
- Actions expire after one hour and do not survive a gateway restart.
- An approval may already have timed out/resolved.
- Text fallback commands remain available.

### Files fail

- Yandex may enforce tenant/privacy limits.
- Inbound payloads are bounded by Hermes'
  `gateway.max_inbound_media_bytes` (128 MiB by default).
- Yandex documents a monthly 3 GB bot image-send limit.
- Check the generated file is inside a Hermes-approved delivery path.

### Thread replies fall back to the main chat

This is expected when inbound updates lack a documented `thread_id`. Outbound
thread routing works only when Hermes metadata already contains a numeric root
message ID.
