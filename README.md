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

## Status

Foundation (Epic 6 relational schema + TimescaleDB hypertables, Epic 4's
multi-tenancy RLS framework) is in place. See the task tracker / commit history
for progress across the remaining epics (OCPI, OCPP gateway, billing, fleet,
driver app).
