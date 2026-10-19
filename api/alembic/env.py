import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# Make "settings", "db", ... importable no matter where alembic is started from.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from settings import settings  # noqa: E402
from db.base import Base  # noqa: E402

# Import every model so that it registers itself on Base.metadata.
import db.models.session  # noqa: E402,F401
import db.models.message  # noqa: E402,F401
import db.models.message_translation  # noqa: E402,F401

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: don't silence the app's own loggers.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of connecting (alembic upgrade head --sql)."""
    context.configure(
        url=settings.CHAT_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(settings.CHAT_DATABASE_URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
