from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central runtime configuration, loaded from environment variables.

    Secrets (PSP API keys, IdP certs, etc.) are referenced by name here but
    resolved via a secrets manager at deploy time, never committed in plaintext.

    `app_mode` is the seam between "runs today with mocks" and "needs real
    credentials to launch": `testing` wires every external integration
    (payments, carbon intensity, OCSP, OCPI partner push) to an in-process
    mock so the whole app runs with zero third-party accounts. `production`
    wires the real adapters and fails fast at startup (see
    `evagg.composition.validate_production_config`) if any of them are still
    holding a placeholder value — it does not silently fall back to a mock.
    """

    model_config = SettingsConfigDict(env_prefix="EVAGG_", env_file=".env", extra="ignore")

    app_mode: Literal["testing", "production"] = "testing"

    database_url: str = "postgresql+asyncpg://evagg_app:evagg_app@localhost:5432/evagg"
    # Admin/superuser DSN used only by Alembic to run migrations (CREATE ROLE,
    # ENABLE ROW LEVEL SECURITY, etc. all require privileges `evagg_app` must
    # not have). Matches the docker-compose bootstrap superuser in dev.
    migration_database_url: str = "postgresql+asyncpg://evagg:evagg@localhost:5432/evagg"
    # Separate DSN bound to the BYPASSRLS role — never the standard app pool.
    # Credentials resolved via secrets manager at deploy time, not committed
    # in plaintext (see engineering standards).
    superadmin_database_url: str = "postgresql+asyncpg://evagg_superadmin:evagg_superadmin@localhost:5432/evagg"
    timescale_url: str = "postgresql+asyncpg://evagg_app:evagg_app@localhost:5432/evagg"
    redis_url: str = "redis://localhost:6379/0"
    nats_url: str = "nats://localhost:4222"

    # Resolved via secrets manager at deploy time; this default is dev-only.
    jwt_signing_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl_seconds: int = 15 * 60
    jwt_refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60

    # HMAC secret the gateway uses to sign the trusted X-Tenant-Id header it
    # forwards to internal services (Task 6.3) — resolved via secrets manager.
    gateway_trust_secret: str = "dev-only-insecure-secret-change-me"

    # Where the gateway's dev-mode request forwarder (evagg.gateway.
    # dev_forwarder) sends everything it signs — evagg.main in the
    # docker-compose network. Task 6.3 never built the actual forwarding
    # half of "signs and forwards to internal services", only OAuth token
    # issuance; this setting exists for that forwarder, not for production
    # use (a real deployment's gateway would sit behind a proper ingress,
    # not this dev-only reverse proxy).
    internal_services_base_url: str = "http://backend-main:8000"

    rate_limit_requests_per_window: int = 100
    rate_limit_window_seconds: int = 60

    heartbeat_default_interval_seconds: int = 300
    command_response_timeout_seconds: int = 30

    carbon_intensity_cache_ttl_seconds: int = 15 * 60

    # Resolved via secrets manager at deploy time; this default is dev-only
    # and only works against Stripe's test mode. Unused in app_mode=testing
    # (MockPaymentProvider is wired instead) — pending a real value for launch.
    stripe_api_key: str = "sk_test_dev_only_replace_me"
    stripe_base_url: str = "https://api.stripe.com/v1"
    # HMAC secret Stripe signs webhook payloads with (the `whsec_...` value
    # from the Stripe dashboard's webhook endpoint config). The testing-mode
    # default matches what `MockPaymentProvider`'s simulated webhook signs
    # with, so the same verification code path is exercised in both modes.
    stripe_webhook_secret: str = "whsec_dev_only_replace_me"

    # Resolved via secrets manager at deploy time. Unused in app_mode=testing
    # (MockCarbonProvider is wired instead) — pending a real value for launch.
    electricity_maps_api_key: str = "dev_only_replace_me"
    electricity_maps_base_url: str = "https://api.electricitymap.org/v3"

    # Live OCSP responder for Plug & Charge certificate revocation checks.
    # Unused in app_mode=testing (InMemoryOcspChecker is wired instead) —
    # pending the real CA/responder URL for launch.
    ocsp_responder_url: str = "https://ocsp.example.com"

    # Base URL + bearer token this CPO uses to push location/session updates
    # to roaming partners (Task 1.2's `PartnerPushClient`/`SessionPushClient`).
    # Unused in app_mode=testing (the in-memory push clients are wired
    # instead) — pending real partner endpoints/credentials for launch. Real
    # OCPI deployments negotiate a per-partner token via the credentials
    # module (Task 1.1); this is only the transport-level default used until
    # that per-partner store is consulted.
    ocpi_partner_push_base_url: str = "https://partner.example.com/ocpi"
    ocpi_partner_push_token: str = "dev_only_replace_me"

    # This CPO's own OCPI party identity — every OCPI object we publish
    # (Locations, Tariffs, ...) is namespaced under it. Bilateral roaming
    # only (Task 1.3's chosen topology): one party identity is enough, since
    # there's no hub relaying our catalog to parties we've never negotiated
    # credentials with directly.
    ocpi_party_id: str = "EVG"
    ocpi_country_code: str = "US"

    # `memory`: every domain store (tariffs, wallet, OCPP chargers/
    # transactions/connectors/credentials/meter-values) is in-process and
    # lost on restart — the default, and the only thing most of this app has
    # ever run against. `supabase`: those same stores are backed by
    # PostgREST calls against a Supabase project (evagg.persistence) instead
    # of SQLAlchemy — see docs/supabase/schema.sql for the schema those
    # calls expect, and its header for why this couldn't be verified against
    # a real project from this session. Orthogonal to `app_mode`: this picks
    # where domain data lives, `app_mode` picks how external integrations
    # (Stripe, carbon, OCSP, OCPI push) are wired.
    persistence_backend: Literal["memory", "supabase"] = "memory"
    supabase_url: str = "https://project.supabase.co"
    supabase_api_key: str = "dev_only_replace_me"


settings = Settings()
