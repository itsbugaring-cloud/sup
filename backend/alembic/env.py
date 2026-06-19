"""
alembic/env.py
──────────────────────────────────────────────────────────────────────────────
Alembic environment configuration.

- Uses synchronous psycopg2 DSN for migration execution (Alembic requirement).
- Imports all SQLAlchemy models so autogenerate can detect schema changes.
- Reads DATABASE_URL from app settings (via .env) — no hardcoded credentials.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the app package importable from the alembic directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import settings (reads from .env automatically)
from app.core.config import settings  # noqa: E402

# Import Base — all models MUST be imported here for autogenerate to work.
# As new models are added in Phase 2, import them below.
from app.models.base import Base  # noqa: E402

# Import ALL models so Alembic autogenerate can detect schema changes.
# Adding a new model? Import it here.
from app.models import (  # noqa: F401
    Supplier,
    SupplierDocument,
    AuditLog,
)

# Alembic Config object — provides access to values in alembic.ini
config = context.config

# Override sqlalchemy.url from settings (reads from .env)
# Using SYNC DSN (psycopg2) as Alembic requires synchronous connections
config.set_main_option("sqlalchemy.url", settings.db.DATABASE_URL_SYNC)

# Set up Python logging from alembic.ini config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata


def include_object(object, name, type_, reflected, compare_to):
    """
    Filter function to control which objects Alembic autogenerates for.

    Excludes:
    - Views (type_ == "table" but reflected == True with no compare_to)
    - Any table prefixed with "pg_" (Postgres internal tables)
    """
    if type_ == "table" and name.startswith("pg_"):
        return False
    return True


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    Calls to context.execute() emit SQL to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,              # Detect column type changes
        compare_server_default=True,    # Detect default value changes
        render_as_batch=False,          # Not needed for PostgreSQL
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Use NullPool for migrations — no connection reuse
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
