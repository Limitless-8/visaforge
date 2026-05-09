"""
db/database.py
--------------
SQLAlchemy engine + session factory.

One engine per process (Streamlit re-runs scripts but keeps process).
Uses SQLite by default; DATABASE_URL can switch to Postgres seamlessly.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings
from utils.logger import get_logger

log = get_logger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        connect_args = {}
        url = settings.DATABASE_URL
        if url.startswith("sqlite"):
            # SQLite + Streamlit's threading: need check_same_thread=False.
            connect_args = {"check_same_thread": False}
        _engine = create_engine(
            url,
            echo=False,
            future=True,
            connect_args=connect_args,
        )
        log.info("Database engine initialised: %s", url)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context-managed DB session with commit/rollback."""
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
