"""Alert events, published by the worker (created, resolved) and the API (acknowledged)."""

import uuid
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict


class AlertType(StrEnum):
    THRESHOLD = "threshold"
    OFFLINE = "offline"
    INVALID_TELEMETRY = "invalid_telemetry"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    vessel_id: str
    """The vessel's MQTT identifier, e.g. "vessel-001"."""
    alert_type: AlertType
    severity: AlertSeverity
    status: AlertStatus
    message: str
    value: float | None = None
    triggered_at: AwareDatetime
    acknowledged_at: AwareDatetime | None = None
    resolved_at: AwareDatetime | None = None


class AlertEvent(BaseModel):
    """Payload of `fleetpulse/v1/alerts`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    event: Literal["created", "acknowledged", "resolved"]
    alert: AlertMessage
