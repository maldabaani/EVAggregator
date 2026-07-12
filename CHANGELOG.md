# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## Unreleased

### Added

- `EVAGG_APP_MODE` (`testing` / `production`) — the whole app now runs with
  in-process mocks for every external integration (Stripe, Electricity
  Maps, OCSP, OCPI partner push) in `testing` mode, no third-party accounts
  needed.
- `evagg.composition` — the composition root wiring every previously
  standalone service/router into two real, runnable apps
  (`evagg.main:app`, `evagg.edge_app:app`).
- Real OCPP-J WebSocket transport (`evagg.ocpp_gateway.ws_app`) —
  BootNotification/Heartbeat/Authorize/StartTransaction/MeterValues/
  StatusNotification/StopTransaction now work over an actual WebSocket
  connection, exercised end-to-end for the first time.
- `/billing/stripe/webhook` — real `Stripe-Signature` HMAC verification and
  async payment confirmation, the piece `StripePaymentProvider` was
  missing.
- `HttpOcspChecker` (real RFC 6960 OCSP client), `HttpPartnerPushClient`/
  `HttpSessionPushClient` (real OCPI partner push) — the `production`-mode
  counterparts to their existing in-memory/mock testing-mode defaults.
- `/charging/session/start/{qr,autocharge,plug-and-charge}` — the first
  HTTP entry point onto `SessionStartService`.
- Real `/healthz` (pings Postgres/Redis/NATS), structured JSON logging,
  Prometheus `/metrics` — none of which existed before.
- `backend/Dockerfile`, `portal/Dockerfile`, extended `docker-compose.yml`
  (migration job + backend-main + backend-edge + portal services).
- `docs/production_readiness.md`, `docs/runbooks/backup_restore.md`.

### Changed

- Alembic's TimescaleDB migrations now detect whether the extension is
  actually installed and fall back to a plain Postgres table/view if not,
  rather than hard-failing `alembic upgrade head` on any machine without it.
- `OcspChecker.is_revoked` now takes the cert + issuer (real OCSP needs
  issuer-name-hash + issuer-key-hash + serial, not just a serial number).
- `backend/pyproject.toml` dependencies pinned to exact versions.

## 2026-07-11 — Post-backlog hardening

- Real Stripe-shaped PSP HTTP adapter, real X.509 Plug & Charge validation,
  real `flutter_map` map SDK, Docker-free Redis/NATS integration tests.
- Seven CI-only bugs found and fixed getting the full stack through a real
  CI run for the first time (TimescaleDB transaction/RLS/compression
  ordering conflicts, NOLOGIN roles, pytest import path, asyncio-in-asyncio).
- Task 4.4's missing portal UI (cost-allocation dashboard) built.

## 2026-07-11 — Initial backlog

- All 6 epics / 23 backlog tasks: OCPI roaming, OCPP gateway, tariff/billing
  engine, multi-tenant fleet management, the DB/RLS foundation, and the
  Flutter driver app.
