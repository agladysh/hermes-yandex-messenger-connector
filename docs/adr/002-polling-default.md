# ADR-002: Make polling the default transport

- Status: accepted
- Date: 2026-07-29

## Context

Yandex offers mutually exclusive polling and webhook delivery. Polling needs no
public ingress. Webhooks have a one-second read deadline and at-least-once
delivery, but the published contract does not document request signing.

## Decision

Use polling by default with one consumer, a profile-local atomic offset, and
retry backoff. Keep webhook mode optional for operators who already have
hardened HTTPS ingress.

## Consequences

- The common deployment has no inbound attack surface.
- Polling adds low steady API traffic and up to the configured interval of idle
  latency.
- Webhook operators must use a secret path and reverse-proxy controls.
- The current immediate webhook acknowledgement has a small crash-loss window
  that is explicitly documented.
