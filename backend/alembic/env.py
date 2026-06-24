"""Alembic migration environment for TradingJournalAnalyzer.

Reads the database URL from the project's Settings (app.config.settings)
so all configuration stays in one place (.env file).

Usage:
    # Generate a migration after model changes:
    alembic revision --autogenerate -m "description"

    # Apply migrations:
    alembic upgrade head

    # Roll back one migration:
    alembic downgrade -1
"""

from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config, pool
from alembic import context

# Allow alembic to import from the backend project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import settings
from app.database import Base as target_metadata

# noinspection PyUnresolvedReferences
import app.models  # ensure all models are registered on Base.metadata

config = context.config

# Use project settings for the database URL instead of hardcoding in alembic.ini
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata.metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
