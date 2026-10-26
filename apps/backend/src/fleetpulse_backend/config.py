from datetime import timedelta
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_JWT_SECRET = "development-only-secret-do-not-use-in-production"


class Settings(BaseSettings):
    """Configuration shared by the API and the worker, read from FLEETPULSE_* variables."""

    model_config = SettingsConfigDict(env_prefix="FLEETPULSE_")

    environment: Literal["development", "production"] = "development"

    database_url: str = "postgresql+asyncpg://fleetpulse:fleetpulse@localhost:5432/fleetpulse"

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883

    influx_url: str = "http://localhost:8181"
    influx_database: str = "fleetpulse"
    # Local InfluxDB runs without authentication, but the client always sends a token,
    # so development uses this placeholder. Production sets a real token.
    influx_token: str = "local-dev"

    worker_batch_size: int = Field(default=500, gt=0)
    worker_flush_interval_s: float = Field(default=1.0, gt=0)
    worker_max_buffered_points: int = Field(default=50_000, gt=0)

    jwt_secret: SecretStr = SecretStr(DEVELOPMENT_JWT_SECRET)
    access_token_ttl: timedelta = timedelta(minutes=15)
    refresh_token_ttl: timedelta = timedelta(days=7)

    # Demo mode enables one-click login as a demo user of each role.
    demo_mode: bool = False
    demo_password: SecretStr = SecretStr("fleetpulse-demo")

    @property
    def cookie_secure(self) -> bool:
        """Secure cookies are only sent over HTTPS, which local development does not use."""
        return self.environment == "production"

    @model_validator(mode="after")
    def _require_real_secret_in_production(self) -> Self:
        secret = self.jwt_secret.get_secret_value()
        if self.environment == "production" and (
            secret == DEVELOPMENT_JWT_SECRET or len(secret) < 32
        ):
            raise ValueError("FLEETPULSE_JWT_SECRET must be set to 32+ random characters")
        return self
