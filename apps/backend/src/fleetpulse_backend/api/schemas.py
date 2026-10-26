"""Messages the browser sends over the WebSocket."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from fleetpulse_backend.api.hub import FLEET_CHANNEL, vessel_channel
from fleetpulse_contracts.telemetry import Identifier


class SubscriptionMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["subscribe", "unsubscribe"]
    channel: Literal["fleet", "vessel"]
    vessel_id: Identifier | None = None

    @model_validator(mode="after")
    def _vessel_id_matches_channel(self) -> Self:
        if (self.channel == "vessel") != (self.vessel_id is not None):
            raise ValueError("vessel_id is required for the vessel channel and only for it")
        return self

    @property
    def channel_key(self) -> str:
        if self.vessel_id is None:
            return FLEET_CHANNEL
        return vessel_channel(self.vessel_id)
