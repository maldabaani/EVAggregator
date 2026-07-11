# Engineering Standards — EV Charging Aggregator Platform

Applies to every task in this backlog. Reference this doc from each task instead of
repeating it.

## Stack assumptions

- **Backend services:** Python 3.12 + FastAPI (async), Pydantic v2 for schemas
- **OCPP Gateway:** Python asyncio + `websockets` / `python-ocpp` library, one process
  per shard behind a connection-hash load balancer
- **Event bus:** NATS JetStream (durable consumers, subject hierarchy
  `ocpp.{tenant_id}.{charger_id}.{event_type}`)
- **Presence:** Redis (key pattern `presence:{charger_id}` →
  `{status, last_seen, node_id}`, TTL-based expiry)
- **Data:** PostgreSQL 16 (relational), TimescaleDB extension (meter values/telemetry
  hypertables)
- **Operator Portal:** Angular 17+, standalone components
- **Driver App:** Flutter (confirmed)

## Branching & PR

- Trunk-based: `main` protected, feature branches `feat/<epic>-<task-id>-<slug>`
- PR requires: 1 approval, green CI (lint + unit + integration), no reduction in coverage
- Commit format: Conventional Commits (`feat:`, `fix:`, `test:`, `chore:`)

## Testing standards

- Unit test coverage target: ≥80% on new/changed lines (enforced in CI via
  `pytest --cov` / Angular `ng test --code-coverage`)
- Unit tests are isolated (mock DB/Redis/NATS/OCPP transport) — no network, no real
  sockets
- Integration tests live separately (`/tests/integration`) and run against
  docker-compose services (Postgres, Redis, NATS) in CI
- Test naming: `test_<unit>_<scenario>_<expected_result>`
- Every bug fix ships with a regression test reproducing it first

## API & schema conventions

- REST: nouns plural, versioned (`/api/v1/...`), errors as RFC 7807 problem+json
- All monetary values stored as integer minor units (fils/cents), never float
- All timestamps stored/transmitted UTC ISO 8601
- Every table: `id (uuid)`, `tenant_id`, `created_at`, `updated_at`; `tenant_id`
  indexed and enforced via Postgres RLS where feasible

## Definition of Done (applies to every task)

1. Code merged to `main` via reviewed PR, CI green
2. Unit tests written per the task's Unit Testing section, ≥80% coverage on touched code
3. API/interface changes reflected in OpenAPI spec or equivalent schema doc
4. Structured logging added at key state transitions (correlation id = tenant_id +
   session/charger id)
5. Acceptance criteria in the task verified manually or via integration test
6. No new linter/type-checker warnings

## Open decisions resolved for this build

- **Mobile framework:** Flutter (Epic 5)
- **PSP:** `PaymentProvider` interface built first with a stub/mock implementation;
  real PSP (Stripe/Telr/Checkout.com) to be wired in later without touching wallet/
  ledger logic
- **SSO:** SAML + generic OIDC support (not a single vendor)
- **Public API surface:** REST-first for v1; GraphQL deferred to a later Public API/
  Developer Surface project

## Repository layout

```
backend/    FastAPI services, OCPP gateway, OCPI engine, billing, fleet — Python 3.12
portal/     Angular 17+ operator portal
mobile/     Flutter driver app
docs/       Engineering standards, architecture notes, OpenAPI
```
