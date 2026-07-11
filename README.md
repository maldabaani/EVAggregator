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

Epics 1-4 and 6 complete (OCPI roaming, OCPP gateway, tariff/billing engine,
fleet management, DB/infra + multi-tenancy). Epic 5 (Flutter driver app) is
in progress — live map discovery (Task 5.1) is done. See the task tracker /
commit history for detail on each task.
