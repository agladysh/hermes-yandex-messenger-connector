# Testing and release gates

## Current verification layers

### Dependency-light unit tests

The test suite supplies only the narrow Hermes interfaces the adapter consumes.
It covers routing, group gates, Update normalization, text chunking, current
SuggestButtons shape, authorization of callbacks, and server-side action state.

```bash
uv sync --cache-dir .uv-cache --group dev
uv run --cache-dir .uv-cache pytest -q
```

### Static checks

```bash
uv run --cache-dir .uv-cache ruff check .
python3 -m py_compile adapter.py __init__.py scripts/yandex_probe.py
make docs
```

`make docs` enforces the governed `llms.txt` structure, required safety and
installation facts, canonical link targets, and discovery from README.

### Hermes compatibility smoke test

The implementation was researched against Hermes Agent commit:

```text
b6729ba90552f11ac1064c3c7dcb7ef20361ef8c
```

Before release, install the plugin into a disposable `HERMES_HOME` using that
checkout's own environment, then verify:

1. plugin discovery reports `yandex-messenger-platform`;
2. the registry has a `yandex_messenger` `PlatformEntry`;
3. `Platform("yandex_messenger")` resolves after registration;
4. the adapter factory accepts a `PlatformConfig`;
5. config loading preserves the nested `extra` settings;
6. the standalone sender has the expected cron signature.
7. the bot-token manifest entry is marked for masked input on both supported
   setup metadata paths.

The source-level contract smoke test is:

```bash
uv run --cache-dir .uv-cache --with pyyaml --with requests \
  python scripts/hermes_smoke.py \
  --hermes-source ../hermes-agent
```

The full Hermes suite is not modified by this standalone repository. If a
future connector change requires a Hermes core change, run Hermes' mandated
`scripts/run_tests.sh` there and record both results.

## Live tenant acceptance test

No automated test should consume a production bot token. Use a dedicated
Yandex 360 test organization/profile and complete this matrix:

| Area | Acceptance |
|---|---|
| Identity | `self/get` returns expected bot login/org; no token in output logs |
| Direct auth | allowed employee works; disallowed employee is rejected/paired |
| Outside-org direct | a consumer/external login cannot start or receive a bot DM |
| Guest boundary | an invited guest cannot use the organization bot |
| Group allowlist | unlisted chat ignored; listed chat accepted |
| Activation | `commands`, `mention`, and `all` match documented behavior |
| Sessions | two DMs and two group users route as configured |
| Output | text, >6000 text, formatting, reply, typing |
| Media | inbound image/file and outbound image/file within size limits |
| Controls | approval allow/deny, slash confirm, clarify choice/other |
| Restart | polling offset prevents completed-update replay |
| Lock | second local gateway with same token fails safely |
| Retry | simulated `429`/`5xx` yields retry/backoff without token leakage |
| Cron | `YANDEX_MESSENGER_HOME_CHANNEL` receives detached delivery |
| Webhook, if used | exact envelope, duplicates, latency, secret path, restart |

If federation use is desired, add a separate test with an employee of a
federated organization. Do not infer bot access from Yandex's documentation of
human cross-company chat.

Record date, Yandex tenant type/plan, Hermes SHA, connector SHA, Python version,
transport, and redacted results in the release notes.

## Failure injection

Recommended pre-production cases:

- corrupt offset JSON;
- read-only/unavailable state directory;
- invalid and revoked token;
- bot configured with a webhook while polling starts;
- network loss during a poll and during send;
- duplicate webhook `update_id`;
- malformed webhook JSON and oversized body;
- attachment with false/missing `Content-Length`;
- unauthorized and expired button callback;
- gateway restart between webhook acknowledgement and task completion.

The last case should be documented as expected loss until a durable webhook
inbox is implemented.

## Verification status

At repository bootstrap:

- syntax compilation: performed;
- primary-source schema comparison: performed;
- dependency-backed unit tests: passing (`10 passed`);
- Hermes source-contract smoke test: passing against the pinned checkout;
- full installed-Hermes gateway smoke test: pending a full runtime profile;
- live Yandex tenant test: pending credentials and a test organization.

Therefore, **no end-to-end Yandex tenant test has been run**. No public claim
should imply that the connector has authenticated a real bot, received an
employee message, replied to a direct chat, or participated in a Yandex group.

Do not represent the connector as production-validated until all applicable
gates above are recorded.
