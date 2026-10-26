"""Demo controls: make a simulated vessel act out a failure, so its alert appears live."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from fleetpulse_backend.api.deps import CurrentUser, SettingsDep, current_user, require_role
from fleetpulse_backend.api.events import Publisher
from fleetpulse_backend.api.problems import problem_responses
from fleetpulse_backend.api.rate_limit import RateLimiter
from fleetpulse_backend.api.relay import MessagingUnavailableError
from fleetpulse_backend.db.models import Role, Vessel
from fleetpulse_backend.db.session import SessionDep
from fleetpulse_contracts.commands import CommandMessage, Scenario

router = APIRouter(
    prefix="/api/v1/demo",
    tags=["demo"],
    dependencies=[Depends(current_user)],
    responses=problem_responses(401),
)

# Per user: generous for someone exploring, but stops a script hammering the button.
SCENARIO_LIMIT = 10
SCENARIO_WINDOW_S = 60.0


class ScenarioRequest(BaseModel):
    vessel_id: uuid.UUID
    scenario: Scenario


class ScenarioAccepted(BaseModel):
    vessel_id: uuid.UUID
    scenario: Scenario


def get_publisher(request: Request) -> Publisher:
    publisher: Publisher = request.app.state.publisher
    return publisher


def get_scenario_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.scenario_limiter
    return limiter


@router.post(
    "/scenarios",
    status_code=202,
    dependencies=[require_role(Role.OPERATOR, Role.ADMIN)],
    responses=problem_responses(403, 404, 422, 429, 503),
)
async def trigger_scenario(
    body: ScenarioRequest,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    publisher: Annotated[Publisher, Depends(get_publisher)],
    limiter: Annotated[RateLimiter, Depends(get_scenario_limiter)],
) -> ScenarioAccepted:
    """Sends the scenario to the vessel's device. 202: the effect shows up in the live
    data and alerts within seconds, not in this response."""
    if not settings.demo_mode:
        raise HTTPException(404, "Demo controls are not enabled")
    vessel = await session.get(Vessel, body.vessel_id)
    if vessel is None or not vessel.is_active:
        raise HTTPException(404, "Vessel not found")
    if not limiter.allow(str(user.id)):
        raise HTTPException(
            429, "Too many scenarios, try again in a minute", headers={"Retry-After": "60"}
        )
    try:
        await publisher.send_command(vessel.identifier, CommandMessage(scenario=body.scenario))
    except MessagingUnavailableError as error:
        raise HTTPException(503, "The vessel could not be reached") from error
    return ScenarioAccepted(vessel_id=vessel.id, scenario=body.scenario)
