# Yandex Messenger connector installed

Do not paste the bot OAuth token into an AI chat, ticket, or shared terminal
transcript. If the installer still needs it, the human operator should enter it
locally at the masked prompt.

Next:

1. Open `docs/agent-setup-guide.md`.
2. Select the intended Hermes profile.
3. Configure an explicit employee allowlist.
4. Start with polling, direct messages, and no groups.
5. Restart the gateway and have an allowed employee send `/status`.
6. Add one group only after direct-message acceptance passes.

The connector is not ready merely because the plugin loads. Record a real
direct-message test and, if enabled, a group allowlist/activation test.
