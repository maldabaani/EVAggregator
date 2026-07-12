from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central runtime configuration, loaded from environment variables.

    Secrets (PSP API keys, IdP certs, etc.) are referenced by name here but
    resolved via a secrets manager at deploy time, never committed in plaintext.
    """

    model_config = SettingsConfigDict(env_prefix="EVAGG_", env_file=".env", extra="ignore")

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

    rate_limit_requests_per_window: int = 100
    rate_limit_window_seconds: int = 60

    heartbeat_default_interval_seconds: int = 300
    command_response_timeout_seconds: int = 30

    carbon_intensity_cache_ttl_seconds: int = 15 * 60

    # Resolved via secrets manager at deploy time; this default is dev-only
    # and only works against Stripe's test mode.
    stripe_api_key: str = "sk_test_dev_only_replace_me"
    stripe_base_url: str = "https://api.stripe.com/v1"


settings = Settings()
