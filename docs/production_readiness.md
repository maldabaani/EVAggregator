# Production readiness

This is the authoritative list of what stands between the current app and a
real production launch. It supersedes the old "Known gaps" section that used
to live in the README — that section only covered 4 items; this one covers
everything found while wiring the app into something actually runnable.

## How to read this

The app runs in one of two modes, set via `EVAGG_APP_MODE`:

- **`testing`** (the default): every external, third-party integration
  (Stripe, Electricity Maps, OCSP, OCPI partner push) is wired to an
  in-process mock. No account, API key, or third-party network access is
  needed for any of them — this is what "ready to run and click around
  today" means.
- **`production`**: swaps those same four integrations for their real HTTP
  adapters, and `evagg.composition.validate_production_config()` raises at
  startup if any of their settings are still a dev-only placeholder.

Persistence is a separate, second axis: `EVAGG_PERSISTENCE_BACKEND`
(`memory` default / `supabase`) — see item 1.

## 1. Persistence — largely closed for the OCPP core + billing, open elsewhere

`EVAGG_PERSISTENCE_BACKEND` (`memory` default / `supabase`) is now a second,
independent axis alongside `EVAGG_APP_MODE`. `supabase` backs these stores
with real PostgREST calls against a Supabase project instead of an
in-process dict (`evagg.persistence`):

- OCPP core: `ChargerRegistry`, `ConnectorStore`, `TransactionRepository`,
  `CredentialVerifier`, `MeterValueSink` (`evagg.persistence.supabase_ocpp`).
- Billing: `TariffStore`, `WalletLedgerStore`
  (`evagg.persistence.supabase_billing`).

**Not verified against a real Supabase project** — this session's sandbox
blocks all of `*.supabase.co` on every port (confirmed for both `:5432` and
`:443`), so every one of these is unit-tested against an in-memory PostgREST
simulator (`tests/unit/persistence/fake_postgrest.py`) instead of a live
call. `docs/supabase/schema.sql` (the schema these repositories expect) IS
verified — it creates all 24 tables cleanly against a real local Postgres —
but the `anon`-role grants at the bottom can only be checked by inspection,
since `anon` doesn't exist outside a Supabase project.

Building this surfaced a real schema gap, now fixed: `charger` had no column
for the OCPP charge-point identity string every handler uses (WS path
segment / Basic Auth username) — only the internal UUID primary key. Added
as `charger.charge_point_id` (migration `406b95a84228`).

Tenant isolation for the Supabase backend is enforced at the **application**
layer (every repository call includes an explicit `tenant_id=eq.<id>`
filter), not via Postgres RLS — PostgREST authenticates as the `anon` role
per the publishable API key, which doesn't carry the session-level
`app.current_tenant` GUC the SQLAlchemy path's RLS policies key off. Real
defense-in-depth here would need per-user JWTs (Supabase Auth) and RLS
policies keyed on JWT claims instead — not built.

**Still only in-memory, either backend:** cost-report rollups, OCPI
locations/partners/reconciliation. Building real repositories for these —
Supabase-backed or SQLAlchemy — is the next-biggest remaining item. The seam
is already there (every service takes its store as a constructor argument);
it just needs an implementation wired in `evagg.composition.build_services()`.

A SQLAlchemy-backed path (real Postgres via `asyncpg`, not PostgREST) was
never built either — `persistence_backend` only has `memory`/`supabase`
today. That would be the natural third option for a deployment that runs
its own Postgres rather than using Supabase.

## 2. External integrations — real adapters exist, pending real credentials

| Integration | `testing` mode | `production` mode | What's pending |
|---|---|---|---|
| Stripe payments | `StubPaymentProvider` (in-memory) | `StripePaymentProvider` (real HTTP, Payment Intents API) + `/billing/stripe/webhook` (real signature verification) | A real Stripe account; `stripe_api_key`/`stripe_webhook_secret` |
| Electricity Maps (carbon) | `MockCarbonProvider` (deterministic, no key) | `ElectricityMapsClient` (real HTTP) | A real API key; `electricity_maps_api_key` |
| Plug & Charge OCSP | `InMemoryOcspChecker` | `HttpOcspChecker` (real RFC 6960 OCSP request/response) | A live OEM/CA OCSP responder URL; never integration-tested against a real one |
| OCPI partner push | `InMemoryPartnerPushClient`/`InMemorySessionPushClient` | `HttpPartnerPushClient`/`HttpSessionPushClient` (real HTTP `PATCH`) | Real partner base URLs/tokens — and a per-partner endpoint store (today there's one shared `ocpi_partner_push_base_url`, not a lookup keyed on the partner from OCPI credentials negotiation) |

## 3. OCPP / OCPI event-bus wiring not yet automatic

`LocationSyncService` and `SessionSyncService` exist, are unit-tested, and
have real push-client implementations (see above) — but nothing subscribes
them to the live NATS event bus yet. Today they'd need to be invoked
manually; wiring a durable JetStream consumer that calls them on every
`status_notification`/`meter_values` event is a smaller follow-up.

Similarly, the charging-session-start REST endpoints
(`/charging/session/start/*`) resolve *who* is charging and *how they pay*,
but don't yet dispatch the outbound OCPP `RemoteStartTransaction` command to
the connected charge point — that's Task 2.3's command engine, reachable
once a charger is connected over `evagg.ocpp_gateway.ws_app`, not yet
chained onto this endpoint's result.

## 4. Observability

As of this pass: structured JSON logging, a real `/healthz` that pings
Postgres/Redis/NATS (not a hardcoded `{"status": "ok"}`), and a Prometheus
`/metrics` endpoint are all wired in both apps. What's still missing:

- No error-tracking SaaS (Sentry, etc.) — would need an account/DSN.
- No distributed tracing (OpenTelemetry) — request flows across
  `backend-main`/`backend-edge`/the OCPP WS connection aren't correlated.
- No alerting on the metrics that now exist (they're scraped-and-forgotten
  until something consumes them).

## 5. Deployment / infrastructure

`backend/Dockerfile`, `portal/Dockerfile`, and an extended
`docker-compose.yml` (adding `migrate`/`backend-main`/`backend-edge`/`portal`
services) now exist and validate with `docker compose config`. Not yet
built/run in this sandbox (no Docker daemon here) — verify with
`docker compose up --build` on a machine that has one.

Still pending, and deliberately not attempted without knowing the target:

- No Kubernetes manifests, Helm chart, or Terraform — these depend on which
  cloud/platform this actually launches on.
- No CD pipeline — CI (`backend-ci`/`mobile-ci`/`portal-ci`) still only
  lints/tests/builds; nothing deploys anywhere.
- No secrets manager integration (Vault, AWS Secrets Manager, etc.) — every
  secret-shaped setting is still a plain environment variable with a
  dev-only default.

## 6. TimescaleDB

Alembic's hypertable/continuous-aggregate/retention migrations now detect
whether the `timescaledb` extension is actually installed
(`pg_available_extensions`) and fall back to a plain Postgres table + a
plain (non-continuously-refreshed) view with the same name and shape if it
isn't — this is what let `alembic upgrade head` run in this sandbox at all
(TimescaleDB's package repo returns a 403 on the actual `InRelease` file
here, despite the marketing page responding 200). Docker-based environments
(`docker-compose.yml`'s `timescale/timescaledb:latest-pg16` image) still get
the real hypertable path. This is not a difference between `app_mode`s —
it's a difference between "does this Postgres have the extension," checked
at migration time, independent of testing vs. production.

Supabase doesn't offer the `timescaledb` extension at all, so
`docs/supabase/schema.sql` bakes in the same plain-table/plain-view fallback
permanently for that path, rather than detecting it at runtime.

## 7. Other hygiene

- **API versioning**: none of the REST APIs carry a version in the path or a
  header (`/admin/tariffs`, not `/v1/admin/tariffs`). Fine for a single
  deployed version; will need a scheme before the first breaking change ships
  to an already-integrated OCPI partner or mobile app version in the wild.
- **Dependency pinning**: `backend/pyproject.toml` now pins exact versions
  (was `>=` lower bounds only). `portal/package-lock.json` and
  `mobile/pubspec.lock` already pinned exact resolved versions — no change
  needed there.
- **No full end-to-end test**: Postgres+RLS, Redis, and NATS each have real
  integration tests individually; nothing runs the whole app against all
  three at once over real HTTP in CI (this session did that manually against
  a native install — see the smoke-test transcript in the PR/commit history
  — but it isn't an automated test).
- **LICENSE**: none chosen yet — this is a business decision, not made here.
- **CHANGELOG.md / CONTRIBUTING.md**: added this pass.
- **Backup/restore runbook**: added this pass, see
  `docs/runbooks/backup_restore.md`.
