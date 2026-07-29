# Project and documentation governance

## Maintained contract

The connector has four documentation layers:

| Layer | Authority |
|---|---|
| `docs/agent-setup-guide.md` | Complete agent-guided installation, secret handling, acceptance, and rollback procedure |
| `llms.txt` | Concise model-facing orientation and links to canonical material |
| `after-install.md` | Immediate guidance rendered by the Hermes installer |
| `README.md` | Human project overview and documentation map |

`llms.txt` is an index and distilled safety contract, not a second full
runbook. When it conflicts with the setup guide, fix both in one change and
treat the setup guide as authoritative during the repair.

## Evergreen triggers

The author or agent making any of these changes must review and, when affected,
update `llms.txt`, `after-install.md`, the setup guide, and their links in the
same commit:

- repository name, visibility, license, or installation identifier;
- plugin ID, platform key, version, or required/optional environment fields;
- token-entry, secret-custody, authorization, or reporting policy;
- polling/webhook, direct/group/channel, or allow-all defaults;
- managed-host paths, executable locations, dashboard workflow, or restart
  behavior;
- minimum/pinned Hermes compatibility or validation status;
- renamed, added, removed, or superseded canonical documentation;
- a live experiment that changes an operational recommendation.

The merging maintainer owns this review. Additionally, review `llms.txt` at
every tagged release even when none of the triggers appears obvious.

## Automated guard

`make docs` runs a dependency-free structural check. It verifies the required
`llms.txt` shape, safety/install facts, canonical local targets behind its
public links, and discoverability from README and this governance file.
`make check` includes this gate.

The guard catches broken structure and known drift classes; it cannot decide
whether prose still reflects runtime behavior. That remains a release-review
responsibility.

## Change evidence

Operational claims must distinguish:

- source/contract inspection;
- automated connector and Hermes compatibility tests;
- managed-host canaries;
- real Yandex tenant acceptance.

Do not promote the connector from experimental merely because installation
succeeds. Record immutable connector and Hermes revisions for compatibility
or live-acceptance evidence.

## Publication

Keep `llms.txt` at the repository root. If a dedicated documentation site is
published, serve the same reviewed file at `/llms.txt` and keep its links
publicly fetchable. The convention is advisory and does not replace README,
search indexes, access control, or crawler policy.
