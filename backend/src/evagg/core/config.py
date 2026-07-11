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

    jwt_access_token_ttl_seconds: int = 15 * 60
    jwt_refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60

    heartbeat_default_interval_seconds: int = 300
    command_response_timeout_seconds: int = 30

    carbon_intensity_cache_ttl_seconds: int = 15 * 60


settings = Settings()
