# ADR-003: Gate shared chats twice

- Status: accepted
- Date: 2026-07-29

## Context

Yandex sends every message from every chat where the bot is a subscriber,
member, or administrator. Hermes agents can hold private context and use
powerful tools. Organization membership alone is too broad an authorization
boundary.

## Decision

Require both:

1. the Hermes per-user authorization policy; and
2. an adapter-owned group chat allowlist.

Allowed groups then apply an activation mode. Default to textual mention for
groups and off for channels. Interactive button callbacks are authorized again
at click time.

## Consequences

- Adding the bot to a chat does not automatically expose Hermes.
- `group_allow_all` and `YANDEX_MESSENGER_ALLOW_ALL_USERS` are explicit,
  separately visible escape hatches.
- Mention detection is heuristic because Yandex does not publish structured
  mention metadata.
- Operators should use separate Hermes profiles/agents when groups require
  different data or tool boundaries.
