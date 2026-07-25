"""StorageApp — FastAPI 应用工厂。"""
from __future__ import annotations

from typing import Optional

from stockstat_foundation import Config

from .storage.orm import OrmSession, create_engine_from_url
from .storage.backend import StorageBackendImpl
from .storage.cache import QueryCache
from .api.ohlcv import create_ohlcv_router
from .api.symbols import create_symbols_router
from .api.health import create_health_router
from .api.ingest import create_ingest_router
from .adapters import ADAPTERS
from .normalizer import Normalizer
from .scheduler.collector import ScheduledCollector


class StorageApp:
    """Storage FastAPI 应用工厂。"""

    @staticmethod
    def create(config: Optional[Config] = None,
               *,
               dispatcher_plugin_mount: Optional[callable] = None,
               dispatcher_state_getter: Optional[callable] = None) -> "FastAPI":
        """创建 FastAPI 应用。

        Args:
            config: Foundation Config（可选，默认从环境变量加载）
            dispatcher_plugin_mount: 可选，挂载 Dispatcher 插件的回调
            dispatcher_state_getter: 可选，返回 Dispatcher 状态的回调（Admin 用）
        """
        from fastapi import FastAPI
        config = config or Config.from_env()

        app = FastAPI(
            title="StockStat Storage",
            version="3.1.0",
            description="StockStat V3.1 存储端",
        )

        # 数据库引擎
        engine = create_engine_from_url(config.database_url)
        orm_session = OrmSession(engine)
        orm_session.create_all()
        backend = StorageBackendImpl(orm_session)
        cache = QueryCache()

        app.state.config = config
        app.state.storage_backend = backend
        app.state.orm_session = orm_session
        app.state.query_cache = cache
        app.state.normalizer = Normalizer()

        # 路由
        app.include_router(create_ohlcv_router(backend))
        app.include_router(create_symbols_router(backend))
        app.include_router(create_health_router(backend))
        app.include_router(create_ingest_router(backend))

        # 可选：Dispatcher 插件
        if dispatcher_plugin_mount is not None:
            dispatcher_plugin_mount(app, storage_backend=backend)

        # 可选：Admin 面板
        if config.admin_enabled:
            from .plugins.admin.router import create_admin_router
            app.include_router(create_admin_router(backend, dispatcher_state_getter))

        # 可选：定时采集
        if config.scheduler_enabled:
            collector = ScheduledCollector(backend, ADAPTERS)
            app.state.collector = collector
            # 不自动启动，由 CLI 显式启动

        return app


__all__ = ["StorageApp"]
