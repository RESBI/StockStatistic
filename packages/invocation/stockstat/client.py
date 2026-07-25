"""StockStatClient — V3.1 用户入口（重构，纯调用者）。"""
from __future__ import annotations

from typing import Any, Optional

from stockstat_foundation import (
    ComputeBackend, TaskRef, TaskSpec, DataSpec, ComputeSpec, DispatchSpec,
    Config, cloudpickle_dumps,
)

from .data_access import DataClient
from .compute_api import ComputeAPI


class StockStatClient:
    """StockStat V3.1 用户入口。

    职责：
    - 数据访问（ohlcv / ingest / list_symbols）
    - 计算提交（backtest / compute / remote）
    - 结果消费（wait / result / stream）

    不含：
    - BacktestEngine / ComputeEngine（在 Compute 模块）
    - 任务调度（在 Dispatcher 模块）
    - 数据持久化（在 Storage 模块）

    用法：
        # 默认本地后端（单机全栈）
        client = StockStatClient()
        result = client.backtest(data, strategy)

        # 远程后端（分布式）
        client = StockStatClient(
            storage_url="http://storage:8000",
            compute_backend=RemoteComputeBackend("http://dispatcher:9000"),
        )
        task = client.compute.remote("grid_search", ...)
        result = task.wait()
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        *,
        storage_url: Optional[str] = None,
        compute_backend: Optional[ComputeBackend] = None,
        config: Optional[Config] = None,
        http_client=None,
        cache_enabled: bool = True,
        use_https: bool = False,
        timeout: int = 30,
    ):
        self._config = config or Config.from_env()
        if storage_url:
            self._storage_url = storage_url.rstrip("/")
        elif self._config.storage_url:
            self._storage_url = self._config.storage_url.rstrip("/")
        else:
            scheme = "https" if use_https else "http"
            self._storage_url = f"{scheme}://{host}:{port}"

        # DataClient（HTTP 访问 Storage）
        self._data_client = DataClient(
            base_url=self._storage_url,
            http_client=http_client,
            timeout=timeout,
            cache_enabled=cache_enabled,
        )

        # ComputeBackend（默认 LocalComputeBackend）
        if compute_backend is None:
            compute_backend = self._build_default_backend()
        self._compute_backend = compute_backend

        # ComputeAPI
        self._compute_api = ComputeAPI(
            client=self,
            data_client=self._data_client,
            compute_backend=self._compute_backend,
        )

    def _build_default_backend(self) -> ComputeBackend:
        """根据 config.default_backend 选择后端。"""
        backend_type = self._config.default_backend
        if backend_type == "local":
            from stockstat_compute import LocalComputeBackend
            return LocalComputeBackend(client=self, data_client=self._data_client)
        elif backend_type == "remote":
            # RemoteComputeBackend 在 P6 实现，这里延迟导入
            try:
                from stockstat_compute.backend.remote import RemoteComputeBackend
                url = self._config.dispatcher_url or self._storage_url
                return RemoteComputeBackend(dispatcher_url=url)
            except ImportError:
                from stockstat_compute import LocalComputeBackend
                return LocalComputeBackend(client=self, data_client=self._data_client)
        elif backend_type == "auto":
            try:
                from stockstat_compute.backend.auto import AutoComputeBackend
                from stockstat_compute import LocalComputeBackend
                local = LocalComputeBackend(client=self, data_client=self._data_client)
                from stockstat_compute.backend.remote import RemoteComputeBackend
                remote = RemoteComputeBackend(
                    dispatcher_url=self._config.dispatcher_url or self._storage_url)
                return AutoComputeBackend(local=local, remote=remote)
            except ImportError:
                from stockstat_compute import LocalComputeBackend
                return LocalComputeBackend(client=self, data_client=self._data_client)
        else:
            from stockstat_compute import LocalComputeBackend
            return LocalComputeBackend(client=self, data_client=self._data_client)

    # ── 数据访问（透传 DataClient）──

    @property
    def data(self) -> DataClient:
        return self._data_client

    def ohlcv(self, symbol: str, timeframe: str = "1d",
              start: Optional[str] = None, end: Optional[str] = None,
              source: Optional[str] = None) -> Any:
        """查询 OHLCV 数据。"""
        return self._data_client.ohlcv(symbol, timeframe, start, end, source)

    def ingest(self, symbol: str, timeframe: str, data: Any) -> int:
        """写入 OHLCV 数据。"""
        return self._data_client.ingest(symbol, timeframe, data)

    def list_symbols(self) -> list:
        return self._data_client.list_symbols()

    # ── 计算访问 ──

    @property
    def compute(self) -> ComputeAPI:
        return self._compute_api

    @property
    def compute_backend(self) -> ComputeBackend:
        return self._compute_backend

    @property
    def config(self) -> Config:
        return self._config

    def backtest(self, data, strategy, **kwargs) -> Any:
        """透明模式回测 — 默认同步阻塞，返回 BacktestResult。

        若 async_submit=True，返回 TaskRef。
        """
        async_submit = kwargs.pop("async_submit", False)
        timeout = kwargs.get("timeout", 3600)
        spec = self._compute_api.build_backtest_task_spec(
            data=data, strategy=strategy, **kwargs)
        task_ref = self._compute_backend.submit(spec)
        if async_submit:
            return task_ref
        return task_ref.wait(timeout=timeout)

    def grid_search(self, data, strategy_cls, param_grid: dict,
                    *, metric: str = "sharpe", maximize: bool = True,
                    **kwargs) -> Any:
        """参数网格搜索（便捷方法，同步等待）。"""
        cs_params = {"_inline_data": data}
        if hasattr(strategy_cls, "__name__"):
            cs_params["strategy_name"] = strategy_cls.__name__
        spec = TaskSpec(
            task_id=str(__import__("uuid").uuid4()),
            data_spec=DataSpec(symbols=kwargs.pop("symbols", [])),
            compute_spec=ComputeSpec(
                task_type="grid_search",
                strategy_ref=f"cloudpickle:{cloudpickle_dumps(strategy_cls)}",
                param_grid=param_grid,
                metric=metric,
                maximize=maximize,
                initial_cash=kwargs.get("initial_cash", 1_000_000.0),
                cost_model=kwargs.get("cost_model"),
                fill_model=kwargs.get("fill_model"),
                trade_on=kwargs.get("trade_on", "open"),
                allow_short=kwargs.get("allow_short", False),
                periods_per_year=kwargs.get("periods_per_year"),
                params=cs_params,
            ),
            dispatch_spec=DispatchSpec(timeout=kwargs.get("timeout", 3600)),
            trace_id=str(__import__("uuid").uuid4()),
            created_by="StockStatClient",
        )
        task_ref = self._compute_backend.submit(spec)
        return task_ref.wait(timeout=kwargs.get("timeout", 3600))

    def batch_backtest(self, data, strategies: dict, fee_models: list = None,
                       **kwargs) -> Any:
        """批量策略回测（便捷方法，同步等待）。"""
        cs_params = {"_inline_data": data}
        spec = TaskSpec(
            task_id=str(__import__("uuid").uuid4()),
            data_spec=DataSpec(symbols=kwargs.pop("symbols", [])),
            compute_spec=ComputeSpec(
                task_type="batch_backtest",
                strategies={name: f"cloudpickle:{cloudpickle_dumps(s)}"
                            for name, s in strategies.items()},
                fee_models=fee_models or ["default"],
                initial_cash=kwargs.get("initial_cash", 1_000_000.0),
                fill_model=kwargs.get("fill_model"),
                trade_on=kwargs.get("trade_on", "open"),
                allow_short=kwargs.get("allow_short", False),
                periods_per_year=kwargs.get("periods_per_year"),
                params=cs_params,
            ),
            dispatch_spec=DispatchSpec(timeout=kwargs.get("timeout", 3600)),
            trace_id=str(__import__("uuid").uuid4()),
            created_by="StockStatClient",
        )
        task_ref = self._compute_backend.submit(spec)
        return task_ref.wait(timeout=kwargs.get("timeout", 3600))

    def run_dsl(self, expression: str, data=None, **kwargs) -> Any:
        """执行 DSL 表达式。"""
        from .dsl import DslEngine
        engine = DslEngine(client=self)
        return engine.evaluate(expression, data=data, **kwargs)

    # ── 集群信息 ──

    def cluster_info(self, **kwargs) -> dict:
        return self._compute_backend.cluster_info(**kwargs)


__all__ = ["StockStatClient"]
