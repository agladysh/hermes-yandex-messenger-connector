# Agent-guided human setup runbook

This runbook is for an assistant—AI or human—guiding an operator through a
Hermes ↔ Yandex Messenger deployment. It is deliberately conversational:
automate the dull and reversible work, stop for the few human-only actions, and
never make the human understand the whole connector before they can use it.

The default outcome is intentionally narrow:

- one existing Hermes profile;
- one Yandex 360 organization bot;
- polling, with no public ingress;
- an explicit employee-login allowlist;
- direct messages first;
- optionally one allowlisted group in `commands` mode;
- channels, `group_allow_all`, and webhooks disabled.

Use [configuration.md](configuration.md) as the complete option reference and
[operations.md](operations.md) after deployment. This document owns the guided
conversation and checkpoints.

## Rules for the assisting agent

1. **Never ask the human to paste a token into chat.** The bot OAuth token must
   be entered in a local masked terminal prompt, the authenticated dashboard's
   password-style Keys/Channels field, or a trusted secret manager.
2. **Never print or read the token back.** Do not run `env`, dump `.env`, add
   shell tracing, include the token on a command line, or copy it into a setup
   report.
3. **Resolve the Hermes profile before changing anything.** Every install,
   config, gateway, state, and log operation must refer to the same profile.
4. **Do not invent identifiers.** Employee logins come from the human or a
   verified Yandex update; group IDs come from Yandex Messenger.
5. **Use polling unless the human already operates suitable HTTPS ingress.**
   Webhook mode is not a shortcut.
6. **Start closed.** Use explicit allowed users, no allowed groups, and
   `group_allow_all: false`.
7. **Separate installation success from product success.** The task is done
   only after a real employee can chat with the agent and every requested group
   gate has been tested.
8. **Do not weaken the Hermes profile to make messaging work.** Model, tool,
   memory, and filesystem authority are separate decisions.
9. **Make a backup before editing existing configuration.** Preserve comments
   and unrelated settings.
10. **Report secrets only as `present`, `missing`, or `rotated`.**
11. **Own progress through acceptance.** Code, documentation, installation,
    and canaries are intermediate checkpoints. When only the human can proceed,
    request one smallest human-only action, explain why, specify the safe
    non-secret response, and resume agent-side work immediately when it arrives.

If the environment cannot provide a private terminal prompt or an authenticated
dashboard secret field, pause and ask the human to configure the token directly
on the host. This pauses only secret entry: continue any unrelated preparation
and verification. Do not accept the secret through the conversation as a
workaround.

## Division of work

| Assisting agent can do | Human must do |
|---|---|
| Inspect Hermes/profile/Git readiness | Choose the intended Hermes identity and audience |
| Verify public-repository access | Sign in to Yandex 360 administration |
| Install and enable the plugin | Create the bot and securely capture its token |
| Edit non-secret connector configuration | Enter the token at a local masked prompt |
| Restart and inspect the gateway | Open the bot and send real test messages |
| Diagnose logs without message bodies/secrets | Add the bot to an existing group in Yandex UI |
| Record redacted acceptance results | Approve the allowed employees and group behavior |

The assisting agent may drive a browser only if the human explicitly authorizes
it and can take over for authentication, token display, or other sensitive
steps. Never take or retain a screenshot of the token.

### Suggested opening message

> I can handle the host checks, plugin installation, configuration, restart,
> and diagnosis. I need you for Yandex administrator login, the one-time bot
> token, and real chat tests. Never paste the token into this conversation;
> when we reach it, I will hand you a masked local terminal prompt. First,
> which Hermes profile should this bot use, who may chat with it, and do you
> need direct messages only or one group too?

## Phase 1 — Establish the deployment contract

Ask these questions, preferably one short group at a time:

1. Which existing Hermes profile should answer Yandex messages?
2. Is this bot a personal assistant or a team-role agent?
3. Which exact Yandex employee logins may use it?
4. Do we need only direct messages now, or one group as well?
5. If a group is needed, is it:
   - a dedicated Hermes room, where `all` may be appropriate; or
   - a shared room, where `commands` is recommended?
6. Does the profile contain anything that must not be exposed to every allowed
   participant?

Do **not** ask whether the human wants polling or webhook unless they already
operate public HTTPS ingress. Select polling and explain:

> We will start without opening an inbound web endpoint. We can revisit
> webhooks later if there is an operational reason.

Write down a redacted worksheet:

```yaml
target_profile: "<profile name>"
bot_role: "personal | team-role"
transport: polling
allowed_users:
  - "<employee login>"
direct_messages: true
groups:
  - chat_id: "<unknown until Yandex supplies it>"
    mode: "commands | all"
channels: false
token: "human enters locally; never recorded here"
```

Stop and clarify if the requested group mixes people who should not share the
profile's memory or tool authority. A group allowlist controls ingress; it does
not make private agent state safe to share.

## Phase 2 — Preflight the host

Run read-only checks first:

```bash
command -v hermes
command -v git
command -v gh
hermes --version
hermes profile list
```

Then resolve the selected profile explicitly:

```bash
TARGET_PROFILE="<chosen profile>"
hermes profile show "$TARGET_PROFILE"
hermes -p "$TARGET_PROFILE" gateway status
```

Do not silently create a new profile. If separation is needed, propose it and
let the human approve:

```bash
hermes profile create yandex-team --clone-from "<source profile>"
```

Confirm that the chosen profile already has a working model/provider. This
connector transports messages; it does not configure inference.

### GitHub access

The connector repository is public. Check outbound Git/GitHub access:

```bash
git ls-remote \
  https://github.com/agladysh/hermes-yandex-messenger-connector.git HEAD
```

No GitHub credential is required. Do not add a token or SSH key to a managed
host for this install.

## Phase 3 — Human creates the Yandex bot

Tell the human:

> Please sign in to the Yandex 360 organization admin console, open **Bots in
> Yandex Messenger**, and create the bot. Choose a name that makes its role and
> audience obvious. When Yandex shows the OAuth token, do not paste it here.
> Keep the page open or place the token in your approved password manager. Tell
> me only when the token is ready.

Use the official administration page:

<https://admin.yandex.ru/>

The organization must have a Yandex 360 Business plan that supports bots. The
bot can interact only with employees of its organization. If the token is lost,
the administrator must reissue it; reissue revokes the previous token.

Record only:

```text
bot created: yes
token captured securely: yes
organization: <human-confirmed name, no secret>
```

## Phase 4 — Install the plugin and hand over for secret entry

Install into the selected profile:

```bash
hermes -p "$TARGET_PROFILE" plugins install \
  agladysh/hermes-yandex-messenger-connector --enable
```

The installer should prompt for `YANDEX_MESSENGER_TOKEN`. Hand the terminal to
the human for this masked prompt. The assisting agent must not observe, echo,
or transcribe the value.

If the prompt is skipped or the token was entered somewhere unsafe:

1. stop;
2. remove the exposed value from the unsafe location;
3. have the Yandex administrator reissue the token;
4. enter the replacement locally.

Confirm plugin discovery without revealing environment values:

```bash
hermes -p "$TARGET_PROFILE" plugins list
```

Expected identities:

```text
plugin ID: yandex-messenger-platform
platform key: yandex_messenger
```

Do not reinstall with `--force` merely because setup is incomplete; that can
replace the plugin checkout without fixing profile configuration.

### Hosted dashboard-only installation

Use this path when Hermes is running in Nous-hosted/container mode and the human
has only the web panels. Hosted Hermes uses `/opt/data` as its durable
`HERMES_HOME`; do not stage the plugin under `/tmp`, because container restarts
may discard it.

Managed-host evidence from 2026-07-29: one bounded CLI experiment on Hermes
`v0.19.0` successfully installed and enabled manifest version `0.1.1` at
`/opt/data/plugins/yandex-messenger-platform`. A blank response to the token
prompt left `YANDEX_MESSENGER_TOKEN` empty. The experiment did not capture the
installed Git SHA or test restart persistence, gateway/dashboard loading, or
Yandex. Treat the path and staged secret workflow as observed, but do not
treat installation as acceptance.

First look for **Plugins**, **Files**, **Keys** (or **API Keys**), **Config**,
and **System** in the Hermes dashboard. Their presence identifies a recent
dashboard with the required management APIs. If **Plugins** or Config's
**YAML** mode is absent, record the Hermes version from **Status** and update
the hosted image before continuing.

The Plugins page can clone the public repository without credentials. Prefer
installing `agladysh/hermes-yandex-messenger-connector` there. Its Git process
is deliberately non-interactive, so a failure is a useful signal that the
managed host denies Git, outbound GitHub access, or durable plugin writes.

If managed-host policy blocks the Plugins installer, use the durable Files page
instead:

1. Open **Files** at `/opt/data`.
2. Create `plugins`, then `plugins/yandex-messenger-platform`.
3. From a trusted local checkout of this repository, upload these three files
   into that directory:
   - `plugin.yaml`
   - `__init__.py`
   - `adapter.py`
4. Open **Plugins** and refresh the page. Confirm that
   `yandex-messenger-platform` appears, then click **Enable**. The dashboard
   plugin “rescan” control is for browser extensions; a browser refresh is
   sufficient for the installed-agent-plugin list.

This minimal upload is intentional: those are the complete runtime files.
Documentation, tests, probes, and Git metadata are not required by the hosted
adapter. The tradeoff is that the Plugins page cannot use **Git pull** to update
this uploaded copy; upload replacement runtime files for a future release.

Set credentials without sending them through agent chat:

1. Open **Keys** / **API Keys**.
2. Under **Custom keys**, add `YANDEX_MESSENGER_TOKEN`; the human enters the
   value directly in the dashboard and saves it.
3. Add `YANDEX_MESSENGER_ALLOWED_USERS` with the approved comma-separated
   employee logins.
4. Add `YANDEX_MESSENGER_ALLOW_ALL_USERS` with the literal value `false`.

The current dashboard learns the token as a required channel field from the
running plugin, but it does not import optional environment-field metadata from
user-installed platform manifests until a dashboard-process restart. Using
Custom keys is therefore the deterministic first-install path. After the
dashboard process restarts, **Channels → Yandex Messenger** may expose the
token directly; leaving a configured field blank preserves its existing value.

Open **Config**, switch to **YAML**, and merge—never replace—the following
entries. Preserve every pre-existing item in `plugins.enabled`:

```yaml
plugins:
  enabled:
    # ...keep every existing enabled plugin...
    - yandex-messenger-platform

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
      group_mode: commands
      channel_mode: off
      mention_aliases: []
```

The top-level `platforms` form is used here because that is where the dashboard
enable/disable control writes. Current Hermes also accepts
`gateway.platforms`, but mixing both shapes makes browser-managed configuration
harder to audit.

Finally:

1. In the hosting control panel, restart the Hermes instance/container if that
   action is available. This makes the long-lived dashboard process discover
   the newly uploaded Python plugin.
2. In **System → Gateway**, click **Restart gateway**. A new gateway process
   discovers the plugin even if an outer instance restart is unavailable.
3. Inspect **Status** and recent **Logs** for `yandex_messenger`; never reveal
   or export the environment while diagnosing.
4. Continue with the real direct-message acceptance test in Phase 6.

If Yandex does not yet appear on **Channels** but the gateway log reports it as
connected, the connector is running and only the dashboard's in-process
platform catalog is stale. Restart the hosted instance; do not reinstall or
weaken authorization.

## Phase 5 — Configure the safe direct-message baseline

Non-secret policy belongs in the selected profile's `config.yaml`. First
identify the path from `hermes profile show`, then back it up. Use a
timestamped sibling backup or the operator's normal configuration versioning;
never overwrite an existing backup.

Add or merge this block without replacing unrelated `gateway` or `platforms`
settings:

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
        group_mode: commands
        channel_mode: off
        mention_aliases: []
```

Then run Hermes' platform setup menu and choose **Yandex Messenger**:

```bash
hermes -p "$TARGET_PROFILE" gateway setup
```

At the token prompt, the human should press Enter to keep the token captured
during installation, or enter it locally if it is still missing. At the next
prompt, enter the human-approved employee logins as a comma-separated list.
The connector's setup flow writes those values to the selected profile's
`.env` and explicitly resets `YANDEX_MESSENGER_ALLOW_ALL_USERS=false`.

Do not set allow-all to bypass a typo or authentication failure. If the setup
menu is unavailable in an older Hermes revision, the human should use a trusted
local editor to set only these two lines in that profile's `.env`:

```dotenv
YANDEX_MESSENGER_ALLOWED_USERS=alice@example.org,bob@example.org
YANDEX_MESSENGER_ALLOW_ALL_USERS=false
```

The assisting agent should not read or print the rest of `.env`, because it
contains the bot token and possibly unrelated credentials.

Review the resulting YAML structurally. Required facts:

- `gateway.platforms.yandex_messenger.enabled` is `true`;
- transport is `polling`;
- `group_allowed_chats` is empty;
- `group_allow_all` is `false`;
- `channel_mode` is `off`;
- no OAuth token appears in `config.yaml`.

## Phase 6 — Start and prove direct messages

Restart the selected profile's gateway:

```bash
hermes -p "$TARGET_PROFILE" gateway restart
hermes -p "$TARGET_PROFILE" gateway status
hermes -p "$TARGET_PROFILE" status
```

If startup fails, inspect only the relevant recent gateway logs. Do not dump the
whole environment or entire long-lived logs into chat.

Ask an allowed employee to:

1. open Yandex Messenger;
2. find/open the bot;
3. send `/status`;
4. send `Reply with exactly: yandex direct OK`;
5. optionally send one harmless small image or text file.

Record:

```yaml
direct_acceptance:
  allowed_login: "<login>"
  status_reply: "pass | fail"
  normal_reply: "pass | fail"
  media: "pass | fail | not-tested"
  tested_at: "<timestamp>"
```

Then test one denied identity if a suitable employee is available. A denied
user must not get an agent response. Do not weaken the allowlist to make this
test convenient.

If direct messages fail, use the troubleshooting sequence in
[operations.md](operations.md). Do not proceed to groups until direct-message
identity, response delivery, and restart behavior pass.

## Phase 7 — Add one group

Skip this phase when the requested outcome is direct messages only.

Ask the human to add the bot to the intended Yandex group using participant
management. Obtain the exact chat ID from the Yandex web client URL:

```text
https://yandex.ru/chat/#/chats/<encoded-chat-id>
```

URL-decode `%2F` to `/`. Do not guess the ID from the group name.

Alternative: from a trusted local shell with the profile token already made
available to the process, the diagnostic client can list bot-visible chats:

```bash
python3 scripts/yandex_probe.py chats
```

Do not copy the token onto that command line. Do not run diagnostic update
polling while the gateway is consuming updates.

Merge the exact ID into the allowlist:

```yaml
gateway:
  platforms:
    yandex_messenger:
      extra:
        group_allowed_chats:
          - "0/0/the-real-chat-id"
        group_allow_all: false
        group_mode: commands
```

Restart the gateway. Test in this order:

1. `/status` in the allowed group receives a response.
2. Ordinary text without `/` receives no response in `commands` mode.
3. A different, unlisted group receives no response.
4. An unauthorized employee's button click or command is rejected.
5. Two participants do not receive private direct-message context.

For a dedicated room, the human may approve `group_mode: all` after the above
passes. For textual activation, use `mention` and add the exact visible bot
spelling to `mention_aliases`; explain that Yandex's published Update schema
does not provide structured mention entities, so this is a text heuristic.

Keep channels off unless channel identity and authorization have been designed
separately.

## Phase 8 — Optional scheduled delivery

Only configure this when the human asked for proactive/cron delivery. Select
one explicit target:

```bash
hermes -p "$TARGET_PROFILE" config set \
  --force \
  YANDEX_MESSENGER_HOME_CHANNEL \
  "login:alice@example.org"
```

or:

```bash
hermes -p "$TARGET_PROFILE" config set \
  --force \
  YANDEX_MESSENGER_HOME_CHANNEL \
  "chat:0/0/the-real-chat-id"
```

This is a plugin-defined top-level setting, hence the explicit `--force` on
Hermes versions that warn about unknown extension keys. If an older deployment
already defines the same variable in `.env`, update or remove that local value
so it cannot override the new target.

The target must already be accepted for the profile. Test one harmless manual
delivery before attaching important schedules.

## Phase 9 — Webhook exception path

Do not enter this phase simply to make the architecture look more
production-like. Polling is the default because it requires no public ingress
and its acknowledgement state is profile-local.

Webhook mode requires all of:

- a stable public HTTPS origin;
- TLS and rate limiting at a reverse proxy;
- a private/loopback connector bind;
- an environment-only random URL secret of at least 32 URL-safe characters;
- an operator who accepts that the connector acknowledges before agent work is
  durably queued;
- duplicate and restart-loss tests.

The human must enter `YANDEX_MESSENGER_WEBHOOK_SECRET` through a local secret
prompt/store. Never transmit it through chat. Follow the full configuration and
operations sections before switching transport. Polling and webhook mode cannot
consume updates simultaneously.

## Definition of done

The assisting agent may say setup is complete only when:

- the selected profile is recorded;
- public-repository install and plugin enablement are confirmed;
- token presence is confirmed without disclosure;
- gateway startup succeeds;
- one allowed direct-message conversation succeeds;
- one denied-user check is recorded or explicitly deferred;
- every requested group is exactly allowlisted and tested;
- an unlisted group is ignored;
- channels and webhook remain off unless separately accepted;
- restart preserves completed polling progress;
- rollback/token-reissue instructions were handed to the operator.

Use this final report shape:

```yaml
connector: yandex_messenger
profile: "<profile>"
plugin_version: "0.1.1"
transport: polling
token: present-and-redacted
allowed_users_count: 2
allowed_groups:
  - chat_id: "redacted-stable-suffix-or-full-id-per-operator-policy"
    mode: commands
direct_test: pass
denied_user_test: pass | deferred
group_test: pass | not-requested
media_test: pass | deferred
restart_test: pass
live_validated_at: "<timestamp>"
remaining_risks:
  - "<only real unresolved items>"
```

Do not include message bodies, tokens, full log dumps, or unrelated profile
state in the report.

## Rollback and emergency stop

For an ordinary rollback:

```bash
hermes -p "$TARGET_PROFILE" plugins disable yandex-messenger-platform
hermes -p "$TARGET_PROFILE" gateway restart
```

Then restore the pre-change `config.yaml` backup if needed.

For a suspected token leak:

1. disable/stop the connector;
2. have the Yandex administrator reissue the token immediately;
3. remove the old token from the profile and any accidental transcript/log;
4. enter the replacement locally;
5. restart and repeat direct-message acceptance;
6. document where the leak occurred without recording the leaked value.

If webhook mode was active, also clear the Yandex webhook registration before
retiring the endpoint.
