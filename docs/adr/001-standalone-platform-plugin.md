# ADR-001: Use a standalone Hermes platform plugin

- Status: accepted
- Date: 2026-07-29

## Context

Hermes needs a transport adapter for an external messaging product. Hermes has
native `BasePlatformAdapter` and plugin registry contracts. Its repository
policy directs third-party product integrations to standalone plugin
repositories rather than core patches.

MCP is a tool/resource protocol, not the gateway's conversation/session
transport. A sidecar relay would duplicate identity, authorization, session,
media, approval, and cron behavior already supplied by the platform adapter
contract.

## Decision

Ship this repository as a `kind: platform` plugin with a dynamic
`yandex_messenger` platform registration. Do not modify Hermes core and do not
introduce an MCP or browser-automation bridge.

## Consequences

- Installation and upgrades are independent of Hermes releases.
- Hermes profile routing, authorization, commands, session handling, and
  detached delivery remain native.
- Compatibility must be tested against explicit Hermes commits.
- The repository owns its own release/security lifecycle.
