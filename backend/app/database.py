"""Database engine + session helpers (SQLModel over SQLite by default)."""
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy import text

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)

# Columns added after the initial schema. `create_all` never ALTERs existing
# tables, so for a dev SQLite file we add them by hand to avoid wiping heard.db.
_SQLITE_ADDED_COLUMNS = {
    "user": [("backboard_assistant_id", "VARCHAR")],
    "speech": [("backboard_thread_id", "VARCHAR")],
    "realtimesegment": [("feedback_json", "VARCHAR DEFAULT '{}'")],
}


def _sqlite_add_missing_columns() -> None:
    """Lightweight forward-only migration for the dev SQLite database."""
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        for table, columns in _SQLITE_ADDED_COLUMNS.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if not existing:
                continue  # table freshly created by create_all with all columns
            for name, ddl in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def init_db() -> None:
    """Create tables. Import models so they register on SQLModel.metadata."""
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _sqlite_add_missing_columns()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
