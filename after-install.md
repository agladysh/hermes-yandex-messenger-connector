# Yandex Messenger connector installed

Do not paste the bot OAuth token into an AI chat, ticket, or shared terminal
transcript. If the installer still needs it, the human operator should enter it
locally at the masked prompt.

The token must come from a bot in a qualifying paid Yandex 360 for Business
organization. A free consumer Messenger account cannot provision the
documented Bot API token used by this connector.

Bots are employee-only: Yandex forbids direct bot messages to outsiders and
says organization guests cannot use bots. Read
`docs/yandex-product-boundaries.md` before choosing the audience.

Next:

1. Open `docs/agent-setup-guide.md`.
2. Select the intended Hermes profile.
3. Configure an explicit employee allowlist.
4. Start with polling, direct messages, and no groups.
5. Restart the gateway and have an allowed employee send `/status`.
6. Add one group only after direct-message acceptance passes.

The connector is not ready merely because the plugin loads. No end-to-end
Yandex tenant test had been run when this version was published. Record a real
employee direct-message test and, if enabled, a group allowlist/activation
test.
