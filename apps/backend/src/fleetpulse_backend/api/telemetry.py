import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Self

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import AwareDatetime, BaseModel, ValidationError, model_validator

from fleetpulse_backend.api.deps import current_user
from fleetpulse_backend.api.problems import problem_responses
from fleetpulse_backend.db.models import Vessel
from fleetpulse_backend.db.session import SessionDep
from fleetpulse_backend.metrics import Metric
from fleetpulse_backend.telemetry import MAX_RANGE, TelemetryStore, TelemetryUnavailableError
from fleetpulse_contracts import TelemetryMessage

router = APIRouter(
    prefix="/api/v1/vessels/{vessel_id}/telemetry",
    tags=["telemetry"],
    dependencies=[Depends(current_user)],
    responses=problem_responses(401, 404, 503),
)

DEFAULT_RANGE = timedelta(hours=1)


def get_store(request: Request) -> TelemetryStore:
    store: TelemetryStore = request.app.state.telemetry
    return store


StoreDep = Annotated[TelemetryStore, Depends(get_store)]


async def vessel_identifier(vessel_id: uuid.UUID, session: SessionDep) -> str:
    """Telemetry is stored under the vessel's MQTT identifier, not its database id."""
    vessel = await session.get(Vessel, vessel_id)
    if vessel is None:
        raise HTTPException(404, "Vessel not found")
    return vessel.identifier


IdentifierDep = Annotated[str, Depends(vessel_identifier)]


class HistoryQuery(BaseModel):
    metric: Metric
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def _valid_range(self) -> Self:
        if self.end <= self.start:
            raise ValueError("'to' must be after 'from'")
        if self.end - self.start > MAX_RANGE:
            raise ValueError("the time range can be at most 72 hours")
        return self


def history_query(
    metric: Metric,
    start: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    end: Annotated[AwareDatetime | None, Query(alias="to")] = None,
) -> HistoryQuery:
    end = end or datetime.now(UTC)
    try:
        return HistoryQuery(metric=metric, start=start or end - DEFAULT_RANGE, end=end)
    except ValidationError as error:
        # Report it like any other invalid query parameter: 422 Problem Details.
        raise RequestValidationError(
            [{**e, "loc": ("query", *e["loc"])} for e in error.errors(include_url=False)]
        ) from error


class HistoryBucket(BaseModel):
    time: datetime
    avg: float
    min: float
    max: float


class MetricSummary(BaseModel):
    avg: float
    min: float
    max: float
    count: int


class TelemetryHistory(BaseModel):
    metric: Metric
    start: datetime
    end: datetime
    bucket_seconds: int
    buckets: list[HistoryBucket]
    summary: MetricSummary | None


@router.get("/latest")
async def latest_telemetry(identifier: IdentifierDep, store: StoreDep) -> TelemetryMessage:
    """The most recent reading from the last 24 hours."""
    try:
        reading = await store.latest(identifier)
    except TelemetryUnavailableError as error:
        raise HTTPException(503, "Telemetry store unavailable") from error
    if reading is None:
        raise HTTPException(404, "No recent telemetry for this vessel")
    return reading


@router.get("/history", responses=problem_responses(422))
async def telemetry_history(
    identifier: IdentifierDep,
    store: StoreDep,
    query: Annotated[HistoryQuery, Depends(history_query)],
) -> TelemetryHistory:
    """One metric over time, in buckets sized to give at most a few hundred points.

    Defaults to the last hour. Ranges are limited to 72 hours.
    """
    try:
        step, buckets, summary = await store.history(
            identifier, query.metric, query.start, query.end
        )
    except TelemetryUnavailableError as error:
        raise HTTPException(503, "Telemetry store unavailable") from error
    return TelemetryHistory(
        metric=query.metric,
        start=query.start,
        end=query.end,
        bucket_seconds=step,
        buckets=[HistoryBucket(**vars(bucket)) for bucket in buckets],
        summary=MetricSummary(**vars(summary)) if summary else None,
    )
