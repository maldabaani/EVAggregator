# EV Charging Aggregator Platform

Monorepo for the EV charging aggregator: OCPI roaming, OCPP gateway, tariff/billing
engine, fleet management, driver app, and the DB/infra layer underneath.

See `docs/00_Engineering_Standards.md` for stack, testing, and API conventions
shared by every task in the backlog.

## Layout

```
backend/    FastAPI services, OCPP gateway, OCPI engine, billing, fleet — Python 3.12
portal/     Angular 17+ operator portal
mobile/     Flutter driver app
docs/       Engineering standards, architecture notes
```

## Backend quickstart

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# start Postgres/TimescaleDB, Redis, NATS
cd .. && docker compose up -d

cd backend
cp .env.example .env
alembic upgrade head
python -m evagg.scripts.audit_rls   # verifies every tenant table has an RLS policy
pytest tests/unit --cov=src/evagg
pytest tests/integration            # requires the docker-compose services above
uvicorn evagg.main:app --reload
```

## Portal quickstart

```bash
cd portal
npm install
npm test    # Karma + Jasmine; needs CHROME_BIN set if no system Chrome (see portal/README.md)
npm start
```

## Mobile quickstart

```bash
cd mobile
flutter pub get
flutter test
flutter run
```

## Status

All 6 epics / 23 backlog tasks are complete: OCPI roaming, OCPP gateway,
tariff/billing engine, multi-tenant fleet management, the DB/infra +
multi-tenancy foundation, and the Flutter driver app (live map, QR/autocharge/
Plug & Charge session start, live session tracking, and the analytics
dashboard).

Since the backlog was finished, the following hardening passed a real CI run
(GitHub Actions, not just local unit tests):

- **Payments**: `StripePaymentProvider`, a real httpx-based `PaymentProvider`
  adapter, alongside the interface-only stub. No live Stripe account is
  wired up (`stripe_api_key` is a dev-only placeholder); webhook-based charge
  confirmation is not implemented.
- **Plug & Charge**: validates real X.509 certificates (leaf signed by a
  trusted CA, validity window, injectable OCSP revocation check) instead of
  modeling the contract cert as a signed JWT.
- **Mobile map**: renders on `flutter_map` over OpenStreetMap tiles (no API
  key required) instead of a placeholder.
- **Integration tests**: `tests/integration/test_redis_real.py` and
  `test_nats_real.py` exercise the production Redis/NATS adapters against
  real (non-Docker) servers. TimescaleDB has no non-Docker install path and
  only runs for real in CI.

Getting the full stack through a real CI run for the first time (this
backlog was developed and reviewed in a sandbox where Docker/TimescaleDB
network access is blocked) surfaced seven bugs invisible to local testing —
all fixed, and **CI is now fully green** (backend-ci, mobile-ci, portal-ci)
on PR #1. See the Alembic migration history in `backend/alembic/versions/`
and `backend/tests/integration/` for detail:

1. `CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)` can't
   populate inside the transaction Alembic wraps every migration in.
2. TimescaleDB refuses to create a continuous aggregate on a hypertable that
   already has RLS enabled.
3. TimescaleDB refuses to enable RLS on a hypertable that already has
   compression turned on.
4. RLS and compression can't coexist on the same hypertable under *any*
   ordering — compression was dropped for `meter_value`/`status_log`
   entirely; storage growth on those two tables is bounded by the existing
   90-day retention policy instead.
5. The `evagg_app`/`evagg_superadmin` DB roles were created `NOLOGIN`, but
   they're the actual roles the app and the CI RLS-audit script connect as
   — fixed to `LOGIN` with a password matching the dev-only connection
   string defaults.
6. The new Redis/NATS integration tests imported `tests.integration.conftest`
   as an absolute package path, which only resolves under `python -m pytest`
   (cwd on `sys.path`) — CI's plain `pytest` invocation doesn't do that.
   Switched to the relative-import convention `tests/unit` already used.
7. An async integration test called Alembic's sync `command.upgrade`/
   `downgrade` directly; those run migrations via their own internal
   `asyncio.run(...)`, which fails from inside a test already running in
   pytest-asyncio's event loop. Fixed with `asyncio.to_thread(...)`.

## Known gaps (not yet addressed)

- **PSP**: no real Stripe account behind `StripePaymentProvider`, and no
  webhook handler for async charge confirmation.
- **Plug & Charge OCSP**: still an injectable in-memory fake, no live OCSP
  responder integration.
- **No true end-to-end system test**: DB/RLS, Redis, and NATS adapters are
  each verified against real services individually, but the app has never
  been run live against all of them at once and driven over real HTTP.
- **No observability, secrets manager, or deployment infra** (out of scope
  for this phase).
- **Portal (Angular)**: Task 4.4's "B2B corporate cost allocation dashboard"
  only got a backend service (`CostReportService`) — no Angular dashboard UI
  was ever built to display it, unlike Task 1.3 (partners) and Task 3.1
  (tariffs), which both have `portal/src/app/features/` components.

See PR #1 and the commit history for the full narrative.
