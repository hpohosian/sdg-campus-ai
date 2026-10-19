from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from settings import settings

# ---------------------------------------------------------------------------
# Two databases, two engines. Never mix them up:
#
#   chat   -> OUR PostgreSQL (sessions, messages, translations). Read + write.
#             Schema is managed by Alembic (see api/alembic).
#   moodle -> Moodle's MariaDB (mdl_* tables). READ ONLY: course texts, PDFs,
#             enrolments. This connection disappears once the backend no
#             longer reads from Moodle directly.
# ---------------------------------------------------------------------------

chat_engine = create_engine(settings.CHAT_DATABASE_URL, pool_pre_ping=True)
moodle_engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

ChatSessionLocal = sessionmaker(
    bind=chat_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=True,
)

MoodleSessionLocal = sessionmaker(
    bind=moodle_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=True,
)


def get_db():
    """FastAPI dependency: session for the CHAT database (PostgreSQL)."""
    db = ChatSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_moodle_db():
    """FastAPI dependency: READ-ONLY session for Moodle's database."""
    db = MoodleSessionLocal()
    try:
        yield db
    finally:
        db.close()
