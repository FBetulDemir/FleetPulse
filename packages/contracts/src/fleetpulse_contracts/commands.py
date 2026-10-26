"""Commands sent to a vessel's device on `fleetpulse/v1/vessels/{vessel_id}/commands`."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Scenario(StrEnum):
    """Demo failures the simulator can act out. Each ends by itself after a while."""

    OVERHEAT = "overheat"
    BATTERY_DRAIN = "battery_drain"
    GO_OFFLINE = "go_offline"
    INVALID_DATA = "invalid_data"
    RESET = "reset"


class CommandMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    scenario: Scenario
