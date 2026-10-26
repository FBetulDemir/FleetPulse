"""Demo data: vessels and one user per role.

Safe to run repeatedly: existing rows are updated, not duplicated.
"""

import asyncio
import logging

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse_backend.auth.passwords import hash_password
from fleetpulse_backend.config import Settings
from fleetpulse_backend.db.models import Role, User, Vessel, VesselType
from fleetpulse_backend.db.session import create_engine, create_sessionmaker

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
        (1, "Älvskutt", VesselType.FERRY, 24.0),
        (2, "Styrsö Express", VesselType.FERRY, 32.5),
        (3, "Vinga Pilot", VesselType.PILOT, 16.8),
        (4, "Hönö Runner", VesselType.WORKBOAT, 19.2),
        (5, "Donsö Surveyor", VesselType.RESEARCH, 14.5),
    ]
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
    logger.info("seeded %d vessels and %d demo users", len(DEMO_VESSELS), len(DEMO_DISPLAY_NAMES))


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
