"""Demo data. Safe to run repeatedly: existing vessels are updated, not duplicated."""

import asyncio
import logging

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse_backend.config import Settings
from fleetpulse_backend.db.models import Vessel, VesselType
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


async def seed(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    statement = insert(Vessel).values(DEMO_VESSELS)
    statement = statement.on_conflict_do_update(
        index_elements=[Vessel.identifier],
        set_={
            "name": statement.excluded.name,
            "vessel_type": statement.excluded.vessel_type,
            "length_m": statement.excluded.length_m,
            "is_active": True,
        },
    )
    async with sessionmaker() as session, session.begin():
        await session.execute(statement)
    logger.info("seeded %d vessels", len(DEMO_VESSELS))


async def main() -> None:
    engine = create_engine(Settings().database_url)
    try:
        await seed(create_sessionmaker(engine))
    finally:
        await engine.dispose()


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(main())
