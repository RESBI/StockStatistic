from __future__ import annotations

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from ..config import settings
from ..models.ohlcv import Base

_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        connect_args = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        engine = create_engine(
            settings.database_url,
            connect_args=connect_args,
            echo=False,
            future=True,
        )
        # Create tables before caching engine, so that if create_all
        # fails (e.g. connection error), the next call retries.
        Base.metadata.create_all(engine)
        _engine = engine
        _SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def get_session() -> Session:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine():
    global _engine, _SessionLocal
    _engine = None
    _SessionLocal = None
