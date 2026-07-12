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

## Run the whole stack

```bash
docker compose up --build
```

Brings up Postgres+TimescaleDB, Redis, NATS, runs migrations, then starts
both backend apps and the portal — `backend-main` (tenant-scoped services:
tariffs, wallet, carbon, cost reports, charging-session start) on `:8000`,
`backend-edge` (OCPI + the OCPP WebSocket) on `:8090`, portal on `:4200`.
Everything runs in `EVAGG_APP_MODE=testing` by default: every external
integration (Stripe, Electricity Maps, OCSP, OCPI partner push) is an
in-process mock, so nothing needs a third-party account to click around.
Set `EVAGG_APP_MODE=production` to swap in the real adapters — see
`docs/production_readiness.md` for exactly what that still needs.

## Backend quickstart (without Docker)

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Postgres, Redis, NATS installed locally (apt/brew) rather than Docker —
# TimescaleDB's own extension is optional: migrations detect its absence
# and fall back to a plain table/view automatically.
cp .env.example .env
alembic upgrade head
python -m evagg.scripts.audit_rls   # verifies every tenant table has an RLS policy
pytest tests/unit --cov=src/evagg
pytest tests/integration            # skips whatever real service isn't reachable

uvicorn evagg.main:app --reload --port 8000       # tenant-scoped services
uvicorn evagg.edge_app:app --reload --port 8090   # OCPI + OCPP WebSocket
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

## Cost allocation dashboard (Task 4.4, completed)

Task 4.4 originally shipped a backend-only service (`CostReportService`) with
no Angular UI to display it — unlike Task 1.3 (partners) and Task 3.1
(tariffs), which both have real `portal/src/app/features/` components. This
is now closed:

- **Backend**: `GET /admin/teams/{team_id}/cost-report` and
  `.../cost-report/csv`, the first endpoints ever exposing
  `CostReportService`.
- **Portal**: `features/cost-dashboard` — stat tiles (sessions, energy,
  total cost, avg. cost/session), a driver/site group-by toggle, a ranked
  table with per-row cost-share meters, an incomplete-rollup-data warning
  banner, and CSV export. Built to the palette/mark specs in the `dataviz`
  design-system reference (`--accent`/`--track` meter fill, status-warning
  banner styling), not ad hoc colors.

## Testing vs. production mode

Every previous stage built well-tested services and routers but never
assembled them into a single running app — `evagg.main`/`evagg.gateway.app`
mounted no business routes at all, and the OCPP WebSocket transport didn't
exist. That's now done: `evagg.composition` wires everything into
`evagg.main:app` and `evagg.edge_app:app`, real health checks
(Postgres/Redis/NATS)/structured logging/Prometheus metrics were added, and
Stripe/Electricity Maps/OCSP/OCPI now each have both a real HTTP adapter and
an in-process mock, selected by `EVAGG_APP_MODE`.

**`docs/production_readiness.md` is now the authoritative gap list** —
it replaces the old inline "Known gaps" section here.

Persistence is a second, independent axis, `EVAGG_PERSISTENCE_BACKEND`:
`memory` (default) keeps every domain store in-process; `supabase` backs
the OCPP core (chargers/connectors/transactions/credentials/meter-values)
and billing (tariffs/wallet) with real PostgREST calls against a Supabase
project instead — see `docs/supabase/schema.sql` (paste into the Supabase
SQL Editor once to set up the schema) and set `EVAGG_SUPABASE_URL`/
`EVAGG_SUPABASE_API_KEY`. Cost rollups and OCPI locations/partners are
still in-memory either way — the largest remaining item before a real
launch, bigger than any one external integration.

See PR #1, `CHANGELOG.md`, and the commit history for the full narrative.
