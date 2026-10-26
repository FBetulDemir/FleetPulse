import contextlib
import time
import urllib.request
from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer

from fleetpulse_backend.api.app import create_app
from fleetpulse_backend.auth.passwords import hash_password
from fleetpulse_backend.config import Settings
from fleetpulse_backend.db.migrate import upgrade
from fleetpulse_backend.db.models import Role, User

Sessionmaker = async_sessionmaker[AsyncSession]

PASSWORD = "correct horse battery staple"
# Hashing is deliberately slow; hash once for all test users.
PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture(scope="session")
def influx_url() -> Iterator[str]:
    """A real InfluxDB 3 Core in a throwaway container (in-memory, no auth)."""
    container = DockerContainer("influxdb:3-core").with_exposed_ports(8181)
    container.with_command("influxdb3 serve --node-id test --object-store memory --without-auth")
    with container:
        url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(8181)}"
        deadline = time.monotonic() + 60
        while True:
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).close()
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        yield url


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

    def add_user(self, role: Role, email: str | None = None, is_active: bool = True) -> str:
        email = email or f"{role.value}@example.com"

        async def insert(sessionmaker: Sessionmaker) -> None:
            async with sessionmaker() as session, session.begin():
                session.add(
                    User(
                        email=email,
                        password_hash=PASSWORD_HASH,
                        display_name=role.value.title(),
                        role=role,
                        is_active=is_active,
                    )
                )

        self.run(insert)
        return email

    def login_as(self, role: Role) -> None:
        email = self.add_user(role)
        response = self.client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text


async def _empty_tables(sessionmaker: Sessionmaker) -> None:
    async with sessionmaker() as session, session.begin():
        await session.execute(text("TRUNCATE vessels, users, refresh_tokens"))


@contextlib.contextmanager
def make_db_client(database_url: str, **settings: Any) -> Iterator[DbClient]:
    app = create_app(Settings(database_url=database_url, **settings), relay=False)
    with TestClient(app) as client:
        db = DbClient(client)
        db.run(_empty_tables)
        yield db


@pytest.fixture
def db_client(database_url: str) -> Iterator[DbClient]:
    with make_db_client(database_url) as db:
        yield db
