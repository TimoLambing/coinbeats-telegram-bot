# alembic/env.py

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv

# Import your SQLAlchemy "Base" and engine from your code
# and import your models so Alembic sees them for autogenerate
from database import Base, engine
from models import User  # Or other models if you have them

# This Alembic Config object provides access to values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# We want Alembic to autogenerate changes by comparing our models' metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    In offline mode, we configure the context with just a URL
    (no Engine). By skipping engine creation, we don't even need
    a DBAPI to be installed.
    """
    # Load environment variables from .env
    load_dotenv()

    # Grab database URL from the environment
    url = os.getenv("DATABASE_URL")

    if not url:
        raise RuntimeError("DATABASE_URL is not set; cannot run Alembic offline.")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,  # So Alembic detects column type changes
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario, we create an Engine from our existing 'database.py' code
    (i.e., the already-imported 'engine'), then associate a connection with the context.
    """
    connectable = engine  # Use the engine you imported from 'database.py'

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True  # So Alembic checks for type diffs
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
