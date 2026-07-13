# syntax=docker/dockerfile:1
# Runs either evagg.main:app (internal tenant-scoped services) or
# evagg.edge_app:app (OCPI + OCPP WebSocket) — pick the module via the
# APP_MODULE build arg / environment override in docker-compose.yml, since
# both live in the same package and need the same dependencies.
FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

# A cache mount (not --no-cache-dir) so a flaky-network retry doesn't
# re-download every wheel from scratch; --timeout/--retries ride out a
# slow/interrupted connection to PyPI instead of failing the whole build
# on one dropped read.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 100 --retries 5 .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

ARG APP_MODULE=evagg.main:app
ENV APP_MODULE=${APP_MODULE}

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD curl -f http://localhost:8000/healthz || exit 1

CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host 0.0.0.0 --port 8000"]
