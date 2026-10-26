from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from fleetpulse_backend.api.app import create_app
from fleetpulse_backend.config import Settings
from fleetpulse_backend.db.migrate import upgrade

Sessionmaker = async_sessionmaker[AsyncSession]


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """A real PostgreSQL in a throwaway container, migrated to the latest schema."""
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        upgrade(url)
        yield url


class DbClient:
    """A TestClient plus a way to run database code on the app's event loop."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.sessionmaker: Sessionmaker = client.app.state.sessionmaker  # type: ignore[attr-defined]

    def run(self, operation: Callable[[Sessionmaker], Awaitable[Any]]) -> Any:
        assert self.client.portal is not None
        return self.client.portal.call(operation, self.sessionmaker)


async def _empty_tables(sessionmaker: Sessionmaker) -> None:
    async with sessionmaker() as session, session.begin():
        await session.execute(text("TRUNCATE vessels"))


@pytest.fixture
def db_client(database_url: str) -> Iterator[DbClient]:
    app = create_app(Settings(database_url=database_url), relay=False)
    with TestClient(app) as client:
        db = DbClient(client)
        db.run(_empty_tables)
        yield db
