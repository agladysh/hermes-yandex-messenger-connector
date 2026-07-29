# Yandex product, tenancy, and audience boundaries

Research checked: 2026-07-29

## Bottom line

This connector targets the official Yandex Messenger Bot API for an internal
Yandex 360 for Business organization. It is not a consumer-Messenger bot.

The supported deployment boundary is:

```text
qualifying paid Yandex 360 organization
  └─ organization administrator creates bot and receives token
       └─ bot communicates with employees of that same organization
```

The free consumer Messenger client does not provide the documented bot
provisioning used here. A qualifying paid Yandex 360 for Business plan is
required. Yandex's current plan names differ by locale and product generation;
the durable purchase criterion is that the live plan comparison explicitly
includes the **Messenger bot platform**.

## Audience matrix

| Principal | Documented bot access | Connector position |
|---|---|---|
| Employee of the bot's own organization | Yes | Supported after explicit Hermes user authorization |
| Personal `@yandex.ru` account invited as an organization employee | Yes, once it joins as an employee | Supported after explicit authorization; it is an employee/paid seat, not an external consumer |
| Arbitrary consumer/external Messenger user | No documented path | Unsupported |
| Organization guest | Explicitly cannot use organization bots | Unsupported |
| Employee of a federated Yandex 360 organization | Human cross-company chat is documented; bot use is not | Unsupported pending explicit vendor confirmation or live evidence |
| Public-link participant outside the organization | Bot-created chats still restrict participants to the bot's organization | Unsupported |

## Primary evidence

Yandex's [bot administration guide](https://yandex.ru/support/yandex-360/business/admin/en/messenger/bot-platform)
states that:

- an organization administrator creates and manages the bot;
- bot availability is tied to qualifying Yandex 360 for Business plans;
- bots interact only with company employees; and
- the bot token is generated in the organization admin console.

The [send-text Bot API contract](https://yandex.ru/dev/messenger/doc/ru/api-requests/message-send-text)
explicitly prohibits a bot from sending a private message to a user outside its
organization. It also requires the bot to be a member or administrator of a
target group chat.

The [chat-creation contract](https://yandex.ru/dev/messenger/doc/ru/api-requests/chat-create)
states that a bot may create a chat or channel only with participants from its
own organization, and that the resulting chat belongs to that organization.
The optional `public` invitation-link flag does not remove the separately
stated organization-participant restriction.

Yandex allows organizations to invite outside people as
[guests](https://yandex.ru/support/yandex-360/business/messenger/ru/chat/guests),
but its guest capability table explicitly says guests cannot use organization
bots. Guest access therefore does not provide a free external-bot audience.

Yandex also documents
[federations](https://yandex.ru/support/yandex-360/business/admin/en/external-contacts/federations)
for human chat across connected organizations. That documentation does not
grant federated employees access to another organization's bots. The general
same-organization Bot API restrictions still apply, so this project does not
claim federation support without further evidence.

An organization can invite an existing personal Yandex account as an
[employee without connecting a mail domain](https://yandex.com/support/yandex-360/business/admin/en/users).
That changes the account's role for this purpose: it becomes an organization
employee, and Yandex's
[cost formula](https://yandex.com/support/yandex-360/business/purchase/en/plans/calculate-price)
bills the plan by organization employee count. It is not a bypass for
arbitrary consumer access.

## Connector enforcement

Yandex owns the primary organization and bot-visibility boundary. The
connector adds independent controls:

1. `YANDEX_MESSENGER_ALLOWED_USERS` / Hermes sender authorization;
2. an exact group-chat allowlist;
3. group activation mode; and
4. the selected Hermes profile's tool and memory policy.

Those controls can narrow Yandex's audience; they cannot widen it. Setting
`YANDEX_MESSENGER_ALLOW_ALL_USERS=true` does not make external or guest access
supported.

The published Update sender shape provides a login and ID but no documented
organization identifier that the connector can independently compare with the
bot's organization. The implementation therefore relies on Yandex to enforce
organization membership and applies its own explicit login/chat authorization
after delivery. Any observed cross-organization update would be a material
contract surprise and must fail the deployment review until characterized.

## End-to-end status

**No end-to-end Yandex tenant test has been run.**

Completed evidence:

- source and official-contract research;
- ten connector unit tests;
- Hermes plugin/registry compatibility smoke test;
- public plugin installation and enablement on managed Hermes `v0.19.0`.

Not completed:

- no real bot token has been configured;
- no `self/get` Bot API request has authenticated a test bot;
- no polling or webhook update has been received;
- no employee direct message has reached Hermes or received a reply;
- no group, guest, external-user, or federation behavior has been exercised;
- no rate-limit, media, restart, offset, or token-rotation behavior has been
  tested against Yandex.

Installation success is not product acceptance. Until the live acceptance
matrix in [testing.md](testing.md) is recorded, describe the connector as
**experimental, contract-tested, and not end-to-end validated**.

## Revalidation triggers

Recheck this boundary when Yandex changes:

- qualifying plan names or bot-platform availability;
- the “employees only” statement;
- direct-message organization restrictions;
- guest bot permissions;
- federation bot permissions;
- Bot API sender fields or organization identity;
- public-chat membership rules; or
- consumer bot/OAuth provisioning.
