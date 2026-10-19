from sqlalchemy.orm import declarative_base

# ONE shared Base for all chat tables (sessions, messages, message translations).
# Alembic reads Base.metadata to know the target schema, so every model must
# import this Base instead of creating its own declarative_base().
Base = declarative_base()
