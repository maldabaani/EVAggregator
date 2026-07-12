# Contributing

## Stack, testing, and API conventions

See `docs/00_Engineering_Standards.md` first — it covers the conventions
every task in this backlog followed (RLS/tenancy rules, testing patterns,
API shape). This file only covers the mechanics of running and submitting
changes.

## Setup

Each app has its own quickstart in the root `README.md`. In short:

```bash
# backend
cd backend && python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# portal
cd portal && npm install

# mobile
cd mobile && flutter pub get
```

## Running the whole stack locally

```bash
docker compose up --build
```

Brings up Postgres+TimescaleDB, Redis, NATS, runs migrations once, then
starts both backend apps (`backend-main` on :8000, `backend-edge` on :8090)
and the portal (:4200) — all in `EVAGG_APP_MODE=testing`, so nothing needs a
real Stripe/Electricity Maps/OCSP/OCPI account. See
`docs/production_readiness.md` for exactly what's mocked and what a real
launch would still need.

## Before opening a PR

```bash
cd backend && pytest tests/unit --cov=src/evagg && ruff check . && mypy src
cd portal && npm test
cd mobile && flutter test
```

CI (`.github/workflows/*.yml`) runs the same checks plus the integration
suite against real Postgres/Redis/NATS — it's the final gate, not a
formality; a change that only passes locally with mocks can still fail
there (see `docs/production_readiness.md`'s TimescaleDB note for why).

## Commit / PR conventions

- Keep commits scoped to one logical change; the existing history (`git log
  --oneline`) is one task or one fix per commit.
- Reference the backlog task number in the commit subject where relevant
  (e.g. `Task 3.3: ...`).
- Every new store/service should follow the existing pattern: a `Protocol`
  interface, an `InMemory*` implementation for tests and `app_mode=testing`,
  and — where a real backing service is needed — a real implementation
  wired in `evagg.composition`.
