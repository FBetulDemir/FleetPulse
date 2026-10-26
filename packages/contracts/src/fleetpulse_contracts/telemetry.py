"""Messages that vessels publish over MQTT.

Validation limits describe what is physically plausible for a sensor, not what is
normal. A speed of 40 knots is valid (and may raise an alert); 400 knots is a
broken sensor and the message is rejected.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")]


class NavigationStatus(StrEnum):
    DOCKED = "docked"
    UNDERWAY = "underway"
    ANCHORED = "anchored"


class ConnectionState(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"


class _Message(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TelemetryMessage(_Message):
    """Payload of `fleetpulse/v1/vessels/{vessel_id}/telemetry`."""

    schema_version: Literal[1] = 1
    vessel_id: Identifier
    device_id: Identifier
    timestamp: AwareDatetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    speed_knots: float = Field(ge=0, le=60)
    course_degrees: float = Field(ge=0, lt=360)
    battery_percent: float = Field(ge=0, le=100)
    battery_voltage: float = Field(ge=0, le=60)
    motor_temperature_c: float = Field(ge=-40, le=200)
    ambient_temperature_c: float = Field(ge=-60, le=60)
    status: NavigationStatus

    @field_validator("timestamp")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class StatusMessage(_Message):
    """Payload of `fleetpulse/v1/vessels/{vessel_id}/status`.

    Published retained when a device connects, and registered as the device's MQTT
    Last Will so the broker publishes the offline state if the connection drops.
    The Last Will is fixed at connect time, so an offline message may have no timestamp.
    """

    schema_version: Literal[1] = 1
    vessel_id: Identifier
    device_id: Identifier
    state: ConnectionState
    timestamp: AwareDatetime | None = None
