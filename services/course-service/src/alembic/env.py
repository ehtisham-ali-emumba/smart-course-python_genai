import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

# Add src to path for local alembic runs (Docker sets PYTHONPATH)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from config import settings
from core.database import Base

# Import ALL models so they register with Base.metadata
from models import Certificate, Course, Enrollment, Progress  # noqa: F401

# Alembic Config object
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate
target_metadata = Base.metadata

# Course-service owns only these tables; exclude user-service tables from autogenerate
COURSE_SERVICE_TABLES = {"courses", "enrollments", "certificates", "progress", "alembic_version_course"}


def include_object(object, name, type_, reflected, compare_to):
    """Exclude tables from other services (user-service) from autogenerate."""
    if type_ == "table" and name not in COURSE_SERVICE_TABLES:
        return False
    return True


def get_url() -> str:
    """Build the async database URL from app settings."""
    return settings.DATABASE_URL.replace(
        "postgresql://", "postgresql+asyncpg://"
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version_course",  # Separate from user-service
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations using a synchronous connection callback."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table="alembic_version_course",  # Separate from user-service
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_async_engine(get_url())

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
