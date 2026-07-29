# Security

## Supported versions

Until the first tagged release, only the latest commit on the default branch is
supported. Every release should record the Hermes commit used for its
compatibility gate.

## Reporting

Report vulnerabilities privately through the repository's GitHub Security
Advisory page or to the repository owner. Do not include a live Yandex OAuth
token, webhook secret, message content, employee identifiers, or attachments
in a public issue. Rotate any credential that may have been disclosed.

## Security model

The connector treats four controls as independent:

1. Yandex 360 organization/tenant membership;
2. Yandex chat membership;
3. connector group-chat allowlisting and activation mode;
4. Hermes per-user authorization and profile/tool policy.

No one control replaces the others.

### Secrets

- Store `YANDEX_MESSENGER_TOKEN` and
  `YANDEX_MESSENGER_WEBHOOK_SECRET` in the active profile's `.env` or an
  external secret injector.
- Never put secrets in `config.yaml`, Git, command-line arguments, chat, or
  logs.
- Yandex shows a newly created bot token once. Reissue rotates/revokes it.
- Hermes' scoped lock hashes the token identity before persisting lock names.

### Polling

Polling is the recommended transport because it exposes no inbound listener.
Only one consumer may use a bot. The connector locks local consumers and
persists the destructive Yandex offset in profile-local state.

### Webhooks

As of 2026-07-29, the official webhook contract documents no HMAC signature or
verification header. Webhook deployments must:

- use a high-entropy secret path;
- terminate TLS at a trusted reverse proxy;
- keep the adapter listener private;
- restrict methods, body sizes, request rates, and upstream routes;
- never log the full request path;
- accept the documented post-ack crash-loss tradeoff or add a durable queue.

The secret path is a compensating control inferred from the missing signature
mechanism, not cryptographic proof that Yandex originated a request.

### Shared chats and prompt injection

Every allowed participant can supply untrusted text/files to the agent.
Mentions control activation, not trust. Use:

- explicit user allowlists;
- exact group IDs;
- least-privilege Hermes tools;
- separate profiles/bots for separate data domains;
- human approvals for sensitive commands;
- `commands` mode when passive group text must never enter agent context.

The connector re-authorizes native button clicks and stores resolver state
server-side so a crafted callback cannot name an arbitrary Hermes session.

### Attachments

Inbound media is streamed with Hermes' configured size limit, validated/cached
through Hermes helpers, and treated as untrusted content. Outbound paths pass
Hermes' media-delivery path validation. Malware scanning and data-loss
prevention remain deployment responsibilities.

## Known security limitations

- Textual mention detection can have false positives/negatives because Yandex
  publishes no structured mention field.
- Immediate webhook acknowledgement leaves an in-process crash window.
- Channel updates may not carry an employee login; channels default off.
- This code has not been live-tested without tenant credentials; follow the
  release gates before production use.
