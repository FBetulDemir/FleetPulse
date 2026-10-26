"""Runs database migrations. Used by the `fleetpulse-migrate` command and by tests."""

import logging

from alembic import command
from alembic.config import Config

from fleetpulse_backend.config import Settings


def alembic_config(database_url: str) -> Config:
    config = Config()
    # Migrations ship inside the package, so they are available in the Docker image.
    config.set_main_option("script_location", "fleetpulse_backend:migrations")
    # Alembic's config treats % as interpolation; escape it in passwords.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def upgrade(database_url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(database_url), revision)


def downgrade(database_url: str, revision: str) -> None:
    command.downgrade(alembic_config(database_url), revision)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    upgrade(Settings().database_url)
