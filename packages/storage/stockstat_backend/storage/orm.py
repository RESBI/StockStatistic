"""SQLAlchemy ORM 封装。"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine as sa_create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session


def create_engine_from_url(database_url: str, **kwargs) -> Engine:
    """从 URL 创建 SQLAlchemy engine，自动处理 SQLite 配置。"""
    if database_url.startswith("sqlite"):
        kwargs.setdefault("connect_args", {})["check_same_thread"] = False
        engine = sa_create_engine(database_url, **kwargs)
        set_sqlite_wal(engine)
    else:
        engine = sa_create_engine(database_url, **kwargs)
    return engine


def set_sqlite_wal(engine: Engine) -> None:
    """启用 SQLite WAL 模式提升并发读。"""
    if not engine.url.drivername.startswith("sqlite"):
        return

    @event.listens_for(engine, "connect")
    def _set_wal(dbapi_conn, conn_record):
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


class OrmSession:
    """SQLAlchemy session 工厂封装。"""

    def __init__(self, engine: Engine):
        self._engine = engine
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    @property
    def engine(self) -> Engine:
        return self._engine

    @property
    def session_factory(self):
        return self._session_factory

    def create_session(self) -> Session:
        return self._session_factory()

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """事务上下文管理器 — 自动 commit/rollback/close。"""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_all(self) -> None:
        """创建所有表。"""
        from ..models.ohlcv import Base
        Base.metadata.create_all(self._engine)

    def drop_all(self) -> None:
        """删除所有表（测试用）。"""
        from ..models.ohlcv import Base
        Base.metadata.drop_all(self._engine)


__all__ = ["create_engine_from_url", "set_sqlite_wal", "OrmSession"]
