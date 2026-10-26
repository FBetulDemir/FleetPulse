"""PostgreSQL storage for the alert engine."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse_backend.alerts.engine import AlertKey, NewAlert, Rule
from fleetpulse_backend.db.models import Alert, AlertRule, Vessel
from fleetpulse_contracts.alerts import AlertMessage, AlertStatus


def to_message(alert: Alert, vessel_id: str) -> AlertMessage:
    return AlertMessage(
        id=alert.id,
        vessel_id=vessel_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        status=alert.status,
        message=alert.message,
        value=alert.value,
        triggered_at=alert.triggered_at,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
    )


class AlertStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def load_rules(self) -> list[Rule]:
        async with self._sessionmaker() as session:
            rows = await session.scalars(select(AlertRule).where(AlertRule.enabled))
            return [
                Rule(
                    id=r.id,
                    name=r.name,
                    vessel_uuid=r.vessel_id,
                    metric=r.metric,
                    operator=r.operator,
                    threshold=r.threshold,
                    severity=r.severity,
                )
                for r in rows
            ]

    async def load_vessels(self) -> dict[str, uuid.UUID]:
        """Active vessels by MQTT identifier."""
        async with self._sessionmaker() as session:
            rows = await session.execute(
                select(Vessel.identifier, Vessel.id).where(Vessel.is_active)
            )
            return {identifier: vessel_id for identifier, vessel_id in rows}

    async def load_open(self) -> set[AlertKey]:
        async with self._sessionmaker() as session:
            rows = await session.execute(
                select(Alert.vessel_id, Alert.alert_type, Alert.alert_rule_id).where(
                    Alert.status != AlertStatus.RESOLVED
                )
            )
            return {AlertKey(v, t, r) for v, t, r in rows}

    async def open(self, alert: NewAlert) -> AlertMessage | None:
        statement = (
            insert(Alert)
            .values(
                vessel_id=alert.key.vessel_uuid,
                alert_type=alert.key.alert_type,
                alert_rule_id=alert.key.rule_id,
                severity=alert.severity,
                status=AlertStatus.ACTIVE,
                message=alert.message,
                value=alert.value,
                triggered_at=alert.at,
            )
            # The partial unique index allows one open alert per key. If another one is
            # already open, insert nothing instead of failing.
            .on_conflict_do_nothing()
            .returning(Alert)
        )
        async with self._sessionmaker() as session, session.begin():
            stored = await session.scalar(statement)
            return to_message(stored, alert.vessel_id) if stored else None

    async def resolve(self, key: AlertKey, vessel_id: str, at: datetime) -> AlertMessage | None:
        statement = (
            update(Alert)
            .where(
                Alert.vessel_id == key.vessel_uuid,
                Alert.alert_type == key.alert_type,
                Alert.alert_rule_id.is_not_distinct_from(key.rule_id),
                Alert.status != AlertStatus.RESOLVED,
            )
            .values(status=AlertStatus.RESOLVED, resolved_at=at)
            .returning(Alert)
        )
        async with self._sessionmaker() as session, session.begin():
            resolved = await session.scalar(statement)
            return to_message(resolved, vessel_id) if resolved else None
