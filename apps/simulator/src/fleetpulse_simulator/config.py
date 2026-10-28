from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLEETPULSE_")

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    # The local broker allows anonymous clients; production gives each service a login.
    mqtt_username: str | None = None
    mqtt_password: SecretStr | None = None

    @property
    def mqtt_password_value(self) -> str | None:
        return self.mqtt_password.get_secret_value() if self.mqtt_password else None

    vessel_count: int = Field(default=5, ge=1, le=5)
    publish_interval_s: float = Field(default=1.0, gt=0)
    random_seed: int | None = None
