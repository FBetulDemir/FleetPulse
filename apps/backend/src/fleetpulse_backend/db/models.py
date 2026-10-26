import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Enum, MetaData, Numeric, String, func, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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
