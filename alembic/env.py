import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text, create_engine

from app.core.config import settings
from app.db.session import Base

# Import all models so Alembic sees them in metadata
from app.models.user import User  # noqa: F401
from app.models.route import Route  # noqa: F401
from app.models.location import Location  # noqa: F401
from app.models.time_entry import TimeEntry  # noqa: F401
from app.models.booking import Booking  # noqa: F401
from app.models.passenger import Passenger  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.pilot import PilotAssignment  # noqa: F401
from app.models.email_log import EmailLog  # noqa: F401
from app.models.slot_rule import SlotRule  # noqa: F401


def ensure_alembic_version_table(connection) -> None:
    # Alembic defaults alembic_version.version_num to VARCHAR(32), but our revision ids are longer.
    # Pre-create / widen the column to avoid migration failures.
    connection.execute(
        text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(64) NOT NULL);")
    )
    try:
        connection.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64);"))
    except Exception:
        # Ignore if already correct or DB doesn't support in this context
        pass


# Alembic Config object
config = context.config

# ✅ Force sqlalchemy.url from real runtime DATABASE_URL
db_url = getattr(settings, "DATABASE_URL", None) or os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL is not set (check .env / app.core.config.settings)")

config.set_main_option("sqlalchemy.url", db_url)

# Logging config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = config.get_main_option("sqlalchemy.url")

    # Use create_engine with url from config (from DATABASE_URL env)
    # Do NOT use engine_from_config here because alembic.ini has:
    # sqlalchemy.url = %(DATABASE_URL)s
    # which will NOT expand from env vars.
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        # Do not run any DDL before configure(); otherwise the connection is already in a
        # transaction and Alembic's begin_transaction() returns nullcontext() and never commits.
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            ensure_alembic_version_table(connection)  # widen version_num before run_migrations
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
