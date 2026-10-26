import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    String,
    func,
    text,
    true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from fleetpulse_backend.metrics import Metric
from fleetpulse_contracts.alerts import AlertSeverity, AlertStatus, AlertType

# Explicit constraint names, so migrations can reference (and later drop) them reliably.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class VesselType(StrEnum):
    FERRY = "ferry"
    PILOT = "pilot"
    RESEARCH = "research"
    WORKBOAT = "workboat"


class Vessel(Base):
    __tablename__ = "vessels"
    __table_args__ = (CheckConstraint("length_m > 0", name="length_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # The id the vessel's device uses on MQTT, e.g. "vessel-001".
    identifier: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    # Stored as text with a CHECK constraint rather than a native Postgres enum,
    # which is easier to extend in a migration.
    vessel_type: Mapped[VesselType] = mapped_column(
        Enum(
            VesselType,
            name="vessel_type",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    length_m: Mapped[float] = mapped_column(Numeric(5, 1, asdecimal=False))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Role(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Stored lowercased by the API, so the unique constraint is case-insensitive in effect.
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[Role] = mapped_column(
        Enum(
            Role,
            name="user_role",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RefreshToken(Base):
    """A long-lived login session. Only a hash of the token is stored.

    Each refresh replaces the token with a new one in the same family. Presenting a
    token that was already replaced means it was stolen or replayed, so the whole
    family is revoked and the user must log in again.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def _str_enum(enum: type[StrEnum], name: str) -> Enum:
    """Text column with a CHECK constraint (easier to extend than a native enum)."""
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


class ComparisonOperator(StrEnum):
    ABOVE = "above"
    BELOW = "below"


class AlertRule(Base):
    """A threshold on one metric, for one vessel or (vessel_id null) the whole fleet."""

    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    vessel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vessels.id", ondelete="CASCADE"), index=True
    )
    metric: Mapped[Metric] = mapped_column(_str_enum(Metric, "alert_metric"))
    operator: Mapped[ComparisonOperator] = mapped_column(
        _str_enum(ComparisonOperator, "alert_operator")
    )
    threshold: Mapped[float]
    severity: Mapped[AlertSeverity] = mapped_column(_str_enum(AlertSeverity, "alert_severity"))
    enabled: Mapped[bool] = mapped_column(default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        # At most one open (not resolved) alert per vessel, type and rule. This is what
        # stops a value that stays above a threshold from creating an alert every second.
        # NULLS NOT DISTINCT (PostgreSQL 15+) makes it apply to rule-less alerts too.
        Index(
            "uq_alerts_one_open",
            "vessel_id",
            "alert_type",
            "alert_rule_id",
            unique=True,
            postgresql_where=text("status <> 'resolved'"),
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_alerts_triggered_at", "triggered_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    vessel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vessels.id", ondelete="CASCADE"))
    alert_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="SET NULL")
    )
    alert_type: Mapped[AlertType] = mapped_column(_str_enum(AlertType, "alert_type"))
    severity: Mapped[AlertSeverity] = mapped_column(_str_enum(AlertSeverity, "alert_severity"))
    status: Mapped[AlertStatus] = mapped_column(_str_enum(AlertStatus, "alert_status"))
    message: Mapped[str] = mapped_column(String(200))
    value: Mapped[float | None]
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
