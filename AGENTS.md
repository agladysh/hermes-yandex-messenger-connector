# Repository agent instructions

This repository is a public, MIT-licensed Hermes Agent platform plugin. Preserve
it as an independently installable plugin; do not solve connector work by
patching a user's Hermes checkout.

Before changing setup, configuration, security, compatibility, or release
behavior, read:

1. `llms.txt`
2. `GOVERNANCE.md`
3. `docs/agent-setup-guide.md`
4. the specific implementation or reference document being changed

`docs/agent-setup-guide.md` is the full setup authority. `llms.txt` is its
concise public orientation layer. Update `llms.txt` in the same change whenever
an install identifier, managed-host path, required environment variable,
security invariant, safe default, compatibility statement, or canonical
documentation link changes. If a triggering change does not require an
`llms.txt` edit, explain why in the commit or review record.

Never commit or request a real Yandex token, webhook secret, tenant transcript,
employee identifier set, `.env`, or hosted profile state. Examples must remain
synthetic.

Run `make check` before committing. Preserve unrelated and pre-existing
worktree changes.
