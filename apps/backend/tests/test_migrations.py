import asyncio
from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from fleetpulse_backend.db.migrate import downgrade, upgrade
from fleetpulse_backend.db.models import Base


def schema_differences(database_url: str) -> list[Any]:
    def compare(connection: Connection) -> list[Any]:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        return list(compare_metadata(context, Base.metadata))

    async def run() -> list[Any]:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            differences = await connection.run_sync(compare)
        await engine.dispose()
        return differences

    return asyncio.run(run())


def test_migrations_match_the_models(database_url: str) -> None:
    # Fails when a model changes without a migration.
    assert schema_differences(database_url) == []


def test_migrations_downgrade_and_upgrade_cleanly(database_url: str) -> None:
    downgrade(database_url, "base")
    upgrade(database_url)

    assert schema_differences(database_url) == []
