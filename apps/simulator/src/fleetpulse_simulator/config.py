from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLEETPULSE_")

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    vessel_count: int = Field(default=5, ge=1, le=5)
    publish_interval_s: float = Field(default=1.0, gt=0)
    random_seed: int | None = None
