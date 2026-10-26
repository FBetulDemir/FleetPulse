import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import aliased

from fleetpulse_backend.alerts.store import to_message
from fleetpulse_backend.api.deps import CurrentUser, current_user, require_role
from fleetpulse_backend.api.events import Publisher
from fleetpulse_backend.api.problems import problem_responses
from fleetpulse_backend.db.models import Alert, AlertRule, ComparisonOperator, Role, User, Vessel
from fleetpulse_backend.db.session import SessionDep
from fleetpulse_backend.metrics import Metric
from fleetpulse_contracts.alerts import (
    AlertEvent,
    AlertSeverity,
    AlertStatus,
    AlertType,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["alerts"],
    dependencies=[Depends(current_user)],
    responses=problem_responses(401),
)


class AlertOut(BaseModel):
    id: uuid.UUID
    vessel_id: uuid.UUID
    vessel_identifier: str
    vessel_name: str
    alert_type: AlertType
    severity: AlertSeverity
    status: AlertStatus
    message: str
    value: float | None
    triggered_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    """Display name of the user who acknowledged the alert."""
    resolved_at: datetime | None


class AlertPage(BaseModel):
    items: list[AlertOut]
    total: int
    limit: int
    offset: int


class AlertRuleOut(BaseModel):
    id: uuid.UUID
    name: str
    vessel_id: uuid.UUID | None
    metric: Metric
    operator: ComparisonOperator
    threshold: float
    severity: AlertSeverity
    enabled: bool


AcknowledgedBy = aliased(User)

StatusFilter = Literal["open", "active", "acknowledged", "resolved"]


def alerts_query() -> Select[Alert, Vessel, str]:
    # display_name is None at runtime when nobody has acknowledged the alert (outer join).
    return (
        select(Alert, Vessel, AcknowledgedBy.display_name)
        .join(Vessel, Vessel.id == Alert.vessel_id)
        .outerjoin(AcknowledgedBy, AcknowledgedBy.id == Alert.acknowledged_by)
    )


def to_out(alert: Alert, vessel: Vessel, acknowledged_by: str | None) -> AlertOut:
    return AlertOut(
        id=alert.id,
        vessel_id=vessel.id,
        vessel_identifier=vessel.identifier,
        vessel_name=vessel.name,
        alert_type=alert.alert_type,
        severity=alert.severity,
        status=alert.status,
        message=alert.message,
        value=alert.value,
        triggered_at=alert.triggered_at,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=acknowledged_by,
        resolved_at=alert.resolved_at,
    )


def get_publisher(request: Request) -> Publisher:
    publisher: Publisher = request.app.state.publisher
    return publisher


@router.get("/alerts", responses=problem_responses(422))
async def list_alerts(
    session: SessionDep,
    status: Annotated[
        StatusFilter | None, Query(description="'open' means active or acknowledged")
    ] = None,
    severity: AlertSeverity | None = None,
    vessel_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AlertPage:
    """Newest first."""
    statement = alerts_query()
    if status == "open":
        statement = statement.where(Alert.status != AlertStatus.RESOLVED)
    elif status is not None:
        statement = statement.where(Alert.status == AlertStatus(status))
    if severity is not None:
        statement = statement.where(Alert.severity == severity)
    if vessel_id is not None:
        statement = statement.where(Alert.vessel_id == vessel_id)

    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = await session.execute(
        statement.order_by(Alert.triggered_at.desc(), Alert.id).limit(limit).offset(offset)
    )
    return AlertPage(
        items=[to_out(*row) for row in rows],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/alerts/{alert_id}", responses=problem_responses(404, 422))
async def get_alert(alert_id: uuid.UUID, session: SessionDep) -> AlertOut:
    row = (await session.execute(alerts_query().where(Alert.id == alert_id))).first()
    if row is None:
        raise HTTPException(404, "Alert not found")
    return to_out(*row)


@router.post(
    "/alerts/{alert_id}/acknowledge",
    dependencies=[require_role(Role.OPERATOR, Role.ADMIN)],
    responses=problem_responses(403, 404, 409, 422),
)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    publisher: Annotated[Publisher, Depends(get_publisher)],
) -> AlertOut:
    """Marks an alert as seen. Repeating it is harmless; resolved alerts cannot be
    acknowledged."""
    # The row lock serialises concurrent acknowledgements and the worker's resolve.
    alert = await session.scalar(select(Alert).where(Alert.id == alert_id).with_for_update())
    if alert is None:
        raise HTTPException(404, "Alert not found")
    if alert.status is AlertStatus.RESOLVED:
        raise HTTPException(409, "The alert is already resolved")
    if alert.status is AlertStatus.ACTIVE:
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now(UTC)
        alert.acknowledged_by = user.id
        await session.commit()
        vessel = await session.get(Vessel, alert.vessel_id)
        assert vessel is not None
        await publisher.publish_alert(
            AlertEvent(event="acknowledged", alert=to_message(alert, vessel.identifier))
        )
    return await get_alert(alert_id, session)


@router.get("/alert-rules")
async def list_alert_rules(session: SessionDep) -> list[AlertRuleOut]:
    rules = await session.scalars(select(AlertRule).order_by(AlertRule.name))
    return [AlertRuleOut.model_validate(rule, from_attributes=True) for rule in rules]
