from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration shared by the API and the worker, read from FLEETPULSE_* variables."""

    model_config = SettingsConfigDict(env_prefix="FLEETPULSE_")

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
