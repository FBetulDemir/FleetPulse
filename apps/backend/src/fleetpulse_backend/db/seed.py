"""Demo data: vessels and one user per role.

Safe to run repeatedly: existing rows are updated, not duplicated.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse_backend.auth.passwords import hash_password
from fleetpulse_backend.config import Settings
from fleetpulse_backend.db.models import (
    AlertRule,
    ComparisonOperator,
    Role,
    User,
    Vessel,
    VesselType,
)
from fleetpulse_backend.db.session import create_engine, create_sessionmaker
from fleetpulse_backend.metrics import Metric
from fleetpulse_contracts.alerts import AlertSeverity

logger = logging.getLogger("fleetpulse.seed")

# Identifiers match the simulator's devices.
DEMO_VESSELS = [
    {
        "identifier": f"vessel-{number:03d}",
        "name": name,
        "vessel_type": vessel_type,
        "length_m": length_m,
    }
    for number, name, vessel_type, length_m in [
        (1, "Ã„lvskutt", VesselType.FERRY, 24.0),
        (2, "StyrsÃ¶ Express", VesselType.FERRY, 32.5),
        (3, "Vinga Pilot", VesselType.PILOT, 16.8),
        (4, "HÃ¶nÃ¶ Runner", VesselType.WORKBOAT, 19.2),
        (5, "DonsÃ¶ Surveyor", VesselType.RESEARCH, 14.5),
    ]
]


# Fleet-wide alert rules: (name, metric, operator, threshold, severity).
DEFAULT_RULES = [
    ("Low battery", Metric.BATTERY_PERCENT, ComparisonOperator.BELOW, 20.0, AlertSeverity.WARNING),
    (
        "Battery critical",
        Metric.BATTERY_PERCENT,
        ComparisonOperator.BELOW,
        10.0,
        AlertSeverity.CRITICAL,
    ),
    (
        "High motor temperature",
        Metric.MOTOR_TEMPERATURE_C,
        ComparisonOperator.ABOVE,
        70.0,
        AlertSeverity.CRITICAL,
    ),
    ("Unusual speed", Metric.SPEED_KNOTS, ComparisonOperator.ABOVE, 12.0, AlertSeverity.WARNING),
]

DEMO_DISPLAY_NAMES = {
    Role.ADMIN: "Demo Admin",
    Role.OPERATOR: "Demo Operator",
    Role.VIEWER: "Demo Viewer",
}


def demo_email(role: Role) -> str:
    # example.com is reserved for documentation, so these can never be real addresses.
    return f"demo-{role.value}@example.com"


async def seed(sessionmaker: async_sessionmaker[AsyncSession], demo_password: str) -> None:
    vessels = insert(Vessel).values(DEMO_VESSELS)
    vessels = vessels.on_conflict_do_update(
        index_elements=[Vessel.identifier],
        set_={
            "name": vessels.excluded.name,
            "vessel_type": vessels.excluded.vessel_type,
            "length_m": vessels.excluded.length_m,
            "is_active": True,
        },
    )
    users = insert(User).values(
        [
            {
                "email": demo_email(role),
                "display_name": display_name,
                "role": role,
                "password_hash": hash_password(demo_password),
            }
            for role, display_name in DEMO_DISPLAY_NAMES.items()
        ]
    )
    users = users.on_conflict_do_update(
        index_elements=[User.email],
        set_={
            "display_name": users.excluded.display_name,
            "role": users.excluded.role,
            "password_hash": users.excluded.password_hash,
            "is_active": True,
        },
    )
    async with sessionmaker() as session, session.begin():
        await session.execute(vessels)
        await session.execute(users)
        # Rules have no natural unique key; add the fleet-wide ones that are missing by name.
        existing = set(
            await session.scalars(select(AlertRule.name).where(AlertRule.vessel_id.is_(None)))
        )
        session.add_all(
            AlertRule(
                name=name,
                metric=metric,
                operator=operator,
                threshold=threshold,
                severity=severity,
            )
            for name, metric, operator, threshold, severity in DEFAULT_RULES
            if name not in existing
        )
    logger.info(
        "seeded %d vessels, %d demo users and %d alert rules",
        len(DEMO_VESSELS),
        len(DEMO_DISPLAY_NAMES),
        len(DEFAULT_RULES),
    )


async def main() -> None:
    settings = Settings()
    engine = create_engine(settings.database_url)
    try:
        await seed(create_sessionmaker(engine), settings.demo_password.get_secret_value())
    finally:
        await engine.dispose()


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(main())
