# Research trace

Research date: 2026-07-29
Local timezone: Europe/Moscow

This document records the evidence used to select the architecture and map the
wire protocol. Yandex facts come from first-party Yandex documentation. Hermes
facts come from the exact local source revision named below.

## Local source baseline

Hermes Agent:

```text
path: /Users/agladysh/projects/hermes-agent
commit: b6729ba90552f11ac1064c3c7dcb7ef20361ef8c
branch: main
remote: git@github.com:NousResearch/hermes-agent.git
```

The following upstream surfaces were inspected:

- repository `AGENTS.md` and third-party integration policy;
- `gateway/platforms/ADDING_A_PLATFORM.md`;
- `website/docs/developer-guide/adding-platform-adapters.md`;
- `gateway/platforms/base.py`;
- `gateway/config.py`;
- `gateway/platform_registry.py`;
- `hermes_cli/plugins.py` and `hermes_cli/plugins_cmd.py`;
- bundled IRC, LINE, Telegram, Slack, WhatsApp Cloud, Matrix, and Feishu
  platform adapters;
- plugin-platform interface tests.

The baseline specifically establishes that third-party product integrations
belong in standalone plugin repositories, dynamic platforms register through
`ctx.register_platform`, and `BasePlatformAdapter` is the native conversation
transport.

## Primary source catalog

All web sources below were accessed 2026-07-29.

| ID | Source | Used for |
|---|---|---|
| YM-01 | [Bots in Yandex Messenger](https://yandex.ru/support/yandex-360/business/admin/en/messenger/bot-platform) | Eligible plans, admin creation, employee-only scope, one-time token, token reissue, admin webhook UI |
| YM-02 | [Bot API overview](https://yandex.ru/dev/messenger/doc/ru/) | Official API status and OAuth model |
| YM-03 | [Get bot information](https://yandex.ru/dev/messenger/doc/ru/api-requests/bot-info) | `self/get`, identity, organization and webhook fields |
| YM-04 | [Updates overview](https://yandex.ru/dev/messenger/doc/ru/api-requests/update) | Polling/webhook exclusivity |
| YM-05 | [Polling updates](https://yandex.ru/dev/messenger/doc/ru/api-requests/update-polling) | Endpoint, offset deletion, limits, Update examples, attachments |
| YM-06 | [Webhook updates](https://yandex.ru/dev/messenger/doc/ru/api-requests/update-webhook) | Envelope, registration/clear, at-least-once/order/timeouts/retries/retention |
| YM-07 | [Data types](https://yandex.ru/dev/messenger/doc/ru/data-types) | Chat/Sender/Update, BotRequest, SuggestButtons, directives, deprecations |
| YM-08 | [Send text](https://yandex.ru/dev/messenger/doc/ru/api-requests/message-send-text) | Targets, 6000 limit, dedupe payload, reply/thread, buttons, restrictions |
| YM-09 | [Send typing](https://yandex.ru/dev/messenger/doc/ru/api-requests/message-send-typing) | Exact-one target and three-second timeout |
| YM-10 | [Send file](https://yandex.ru/dev/messenger/doc/ru/api-requests/message-send-file) | Multipart document contract and image quota statement |
| YM-11 | [Send image](https://yandex.ru/dev/messenger/doc/ru/api-requests/message-send-image) | Multipart image contract |
| YM-12 | [Get file](https://yandex.ru/dev/messenger/doc/ru/api-requests/message-get-file) | Authenticated download stream |
| YM-13 | [Text formatting](https://yandex.ru/dev/messenger/doc/ru/formatting) | Supported Markdown-like syntax |
| YM-14 | [List chats](https://yandex.ru/dev/messenger/doc/ru/api-requests/chat-list) | Operator discovery of bot-visible chats |
| YM-15 | [Create chat/channel](https://yandex.ru/dev/messenger/doc/ru/api-requests/chat-create) | Bot-created groups, membership, bot becomes admin |
| YM-16 | [Manage chats/channels](https://yandex.ru/support/yandex-360/business/messenger/ru/chat/administration-of-chats-and-channels) | Group versus channel behavior and UI participant administration |
| YM-17 | [Mentions](https://yandex.ru/support/yandex-360/business/messenger/ru/chat/mentions) | User-interface `@` behavior |
| YM-18 | [Yandex 360 Business plans](https://yandex.com/support/yandex-360/business/purchase/en/plans/payment-plans) | Per-employee paid plans; Messenger is present at the base tier shown there, while bot-platform automation is listed only in a higher tier |
| YM-19 | [Yandex Messenger guests](https://yandex.ru/support/yandex-360/business/messenger/ru/chat/guests) | Guests may join selected work chats but explicitly cannot use organization bots |
| YM-20 | [Yandex 360 employees](https://yandex.com/support/yandex-360/business/admin/en/users) | Personal Yandex accounts may join as employees without a mail domain |
| YM-21 | [Yandex 360 federations](https://yandex.ru/support/yandex-360/business/admin/en/external-contacts/federations) | Human cross-company contacts and chats; no documented bot permission |
| YM-22 | [Yandex 360 cost calculation](https://yandex.com/support/yandex-360/business/purchase/en/plans/calculate-price) | Plan cost is calculated from the number of employees added to the organization |

Hermes source references:

| ID | Source | Used for |
|---|---|---|
| HA-01 | [Adding a platform adapter at pinned commit](https://github.com/NousResearch/hermes-agent/blob/b6729ba90552f11ac1064c3c7dcb7ef20361ef8c/gateway/platforms/ADDING_A_PLATFORM.md) | Public adapter/plugin contract |
| HA-02 | [Base adapter at pinned commit](https://github.com/NousResearch/hermes-agent/blob/b6729ba90552f11ac1064c3c7dcb7ef20361ef8c/gateway/platforms/base.py) | Event, send, media, authorization, lock, sessions |
| HA-03 | [Platform registry at pinned commit](https://github.com/NousResearch/hermes-agent/blob/b6729ba90552f11ac1064c3c7dcb7ef20361ef8c/gateway/platform_registry.py) | Dynamic platform metadata and detached sender |
| HA-04 | [Plugin developer guide at pinned commit](https://github.com/NousResearch/hermes-agent/blob/b6729ba90552f11ac1064c3c7dcb7ef20361ef8c/website/docs/developer-guide/plugins/index.md) | Standalone third-party plugin policy |

## Evidence-to-decision matrix

| Evidence | Interpretation | Implementation |
|---|---|---|
| HA-01/03/04 | Platform plugin is Hermes' native third-party seam | standalone `kind: platform`; no core/MCP changes |
| YM-04/05/06 | Update transports are exclusive | explicit `transport`; connect-time conflict check |
| YM-05 | Positive polling offset deletes earlier updates | atomic profile-local offset; one token lock |
| YM-06 | Webhook read timeout is one second | validate/schedule/ack immediately |
| YM-06 | At-least-once webhook | bounded `update_id` dedupe |
| YM-06/07 | No published signature field/header | polling default; webhook secret path as inferred mitigation |
| YM-07 | Private chat ID is not meaningful | `login:<sender-login>` direct route |
| YM-07 | Channel sender may lack login | channels default off |
| YM-05/07 | Bot receives every joined-chat message; no mention field | separate chat allowlist and textual activation modes |
| YM-08 | text ≤6000 and `payload_id` dedupes | code-aware 5900 chunks and UUID payload IDs |
| YM-09 + HA-02 | typing lasts three seconds; Hermes refreshes | native `sendTyping` |
| YM-07 | old inline keyboard is deprecated | current SuggestButtons/server_action |
| YM-10/11/12 + HA-02 | binary media and authenticated downloads | bounded cache helpers and multipart uploads |
| YM-01/08/15 | organization/private membership constraints | configuration and operations prerequisites |
| YM-01/18 | Free consumer Messenger and base chat access do not imply Bot API provisioning | require a paid organization plan whose live feature list includes the bot platform |
| YM-01/08 | Bots are employee-only; direct sends outside the bot organization are prohibited | reject arbitrary-consumer/external audience as unsupported |
| YM-15 | Bot-created chats contain only the bot organization's participants | public invite flag does not establish an external bot audience |
| YM-19 | Guests cannot use organization bots | guest access is not a free bot-user tier |
| YM-20/22 | Personal accounts can be invited as organization employees | supported path for an existing account, with employee billing and membership |
| YM-21 | Federations document cross-company human chat but not bot use | federation bot access remains unsupported and requires separate evidence |

## Explicit inferences and unresolved points

These are not presented as documented Yandex guarantees:

1. **Webhook authenticity mitigation.** Because YM-06 documents no request
   signature, an unguessable URL path is used. Absence from documentation does
   not prove no undocumented header exists.
2. **Mention matching.** YM-17 documents UI mentions, while YM-07's Update has
   no mention entities. Text matching is a compatibility heuristic.
3. **Inbound threads.** Outbound methods document `thread_id`, while YM-07's
   Update does not. The adapter accepts a future/extra field best-effort.
4. **Existing-chat bot UI.** Generic participant administration is documented;
   tenant UI availability/search behavior for bot accounts should be confirmed
   during live acceptance. Bot-created groups via YM-15 are the documented API
   path.
5. **Webhook durability.** Immediate `2xx` meets the deadline but acknowledges
   before agent processing completes. A durable queue is future work.
6. **Commercial boundary.** Yandex markets Messenger access separately from
   its organization bot platform. YM-01 places bot creation in qualifying paid
   Yandex 360 Business plans and limits bots to organization employees; YM-18
   separately shows ordinary Messenger in a lower tier. No official
   consumer/free bot-registration path was found. Plan names differ between
   current locale and product-generation pages, so capability—not a copied
   name—is the stable prerequisite.
7. **Non-employee boundary.** YM-08 explicitly rejects direct bot messages to
   users outside the bot organization, YM-15 restricts bot-created chats to
   organization participants, and YM-19 says guests cannot use organization
   bots. This supports a firm employee-only product claim.
8. **Federation ambiguity.** YM-21 grants employees cross-company human chat
   within a federation but does not mention bots. The general same-organization
   bot restriction is not overridden, so federation bot support is not
   claimed.

## Tooling trace

The requested local fetch tooling was checked:

- `/Users/agladysh/projects/thai` was not present.
- `/Users/agladysh/projects/share-fetch` is specialized for DeepSeek shared
  conversations, not general documentation extraction.
- `/Users/agladysh/projects/webeye` is a headless Chromium screenshot/layout
  diagnostic tool, useful for visual inspection but not superior for this
  text-first API reference.

The research therefore used direct first-party Yandex documentation retrieval.
No third-party blog or unofficial SDK was used as protocol authority.

## Managed-host experiment trace

On 2026-07-29, an operator-preserved experiment against Nous-managed Hermes
`v0.19.0` first established `/opt/data` write/cleanup, the Hermes CLI at
`/opt/hermes/.venv/bin/hermes`, Git `2.47.3`, and public GitHub access. A second
bounded phase installed and enabled plugin `yandex-messenger-platform` version
`0.1.1` from this public repository at
`/opt/data/plugins/yandex-messenger-platform`. Blank input skipped the token,
leaving its generated environment field empty.

This is executed host evidence, not live Yandex acceptance. The report did not
capture the exact installed connector commit, and it did not test restart
persistence, gateway/dashboard loading, token configuration, or any Bot API
behavior.

## End-to-end evidence status

No end-to-end Yandex tenant test has been run. As of 2026-07-29, the project
has never configured a real Yandex bot token, authenticated `self/get`, polled
an update, received an employee message, sent a reply, joined a live group, or
tested guest/federation behavior. All wire and audience behavior remains based
on official contracts until the live matrix in [testing.md](testing.md) is
executed and preserved.

## Revalidation triggers

Recheck the primary sources and adapter whenever:

- Yandex adds a webhook signature;
- the Update type gains mention/thread/reaction fields;
- Yandex changes plan availability, organization scope, quotas, or limits;
- Hermes changes `BasePlatformAdapter`, `PlatformEntry`, plugin discovery, or
  callback resolver signatures;
- the pinned Hermes compatibility commit advances for a release.
