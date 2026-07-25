"""ComputeAPI — client.compute 实现。"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from stockstat_foundation import (
    TaskSpec, DataSpec, ComputeSpec, DispatchSpec,
    TaskRef, ComputeBackend, cloudpickle_dumps,
)


class ComputeAPI:
    """统一计算入口。

    - client.compute.ma(...)         # 本地轻量指标（即时返回）
    - client.compute.remote(...)     # 远程任务提交（返回 TaskRef）
    - client.compute.cluster_info()  # 集群拓扑
    """

    def __init__(self, client, data_client, compute_backend: ComputeBackend):
        self._client = client
        self._data_client = data_client
        self._backend = compute_backend

    # ── 本地轻量指标 ──

    def ma(self, data, window: int = 20) -> Any:
        return self._dispatch_indicator("ma", data, window=window)

    def ema(self, data, window: int = 12) -> Any:
        return self._dispatch_indicator("ema", data, window=window)

    def rsi(self, data, window: int = 14) -> Any:
        return self._dispatch_indicator("rsi", data, window=window)

    def macd(self, data, fast: int = 12, slow: int = 26, signal: int = 9) -> Any:
        return self._dispatch_indicator("macd", data, fast=fast, slow=slow, signal=signal)

    def bollinger(self, data, window: int = 20, std: float = 2.0) -> Any:
        return self._dispatch_indicator("bollinger", data, window=window, std=std)

    def atr(self, high, low, close, window: int = 14) -> Any:
        return self._dispatch_indicator("atr", high, low, close, window=window)

    def wma(self, data, window: int = 20) -> Any:
        return self._dispatch_indicator("wma", data, window=window)

    def dema(self, data, window: int = 20) -> Any:
        return self._dispatch_indicator("dema", data, window=window)

    def tema(self, data, window: int = 20) -> Any:
        return self._dispatch_indicator("tema", data, window=window)

    def hma(self, data, window: int = 20) -> Any:
        return self._dispatch_indicator("hma", data, window=window)

    def adx(self, high, low, close, window: int = 14) -> Any:
        return self._dispatch_indicator("adx", high, low, close, window=window)

    def kd(self, high, low, close, k_window: int = 9, d_window: int = 3) -> Any:
        return self._dispatch_indicator("kd", high, low, close, k_window=k_window, d_window=d_window)

    def cci(self, high, low, close, window: int = 20) -> Any:
        return self._dispatch_indicator("cci", high, low, close, window=window)

    def williams_r(self, high, low, close, window: int = 14) -> Any:
        return self._dispatch_indicator("williams_r", high, low, close, window=window)

    def donchian(self, high, low, window: int = 20) -> Any:
        return self._dispatch_indicator("donchian", high, low, window=window)

    def keltner(self, high, low, close, window: int = 20, mult: float = 1.5) -> Any:
        return self._dispatch_indicator("keltner", high, low, close, window=window, mult=mult)

    def stddev(self, data, window: int = 20) -> Any:
        return self._dispatch_indicator("stddev", data, window=window)

    def zscore(self, data, window: int = 20) -> Any:
        return self._dispatch_indicator("zscore", data, window=window)

    def rolling_corr(self, x, y, window: int = 20) -> Any:
        return self._dispatch_indicator("rolling_corr", x, y, window=window)

    def rolling_beta(self, asset, market, window: int = 20) -> Any:
        return self._dispatch_indicator("rolling_beta", asset, market, window=window)

    def hurst_rs(self, data) -> Any:
        return self._dispatch_indicator("hurst_rs", data)

    def sample_entropy(self, data, m: int = 2, r: float = None) -> Any:
        return self._dispatch_indicator("sample_entropy", data, m=m, r=r)

    def permutation_entropy(self, data, m: int = 4, tau: int = 1) -> Any:
        return self._dispatch_indicator("permutation_entropy", data, m=m, tau=tau)

    def _dispatch_indicator(self, name: str, *args, **params) -> Any:
        """本地后端直接计算；远程后端提交 indicator task。"""
        # 检查是否是本地后端（有 compute_indicator 方法）
        if hasattr(self._backend, "compute_indicator"):
            # 本地路径：直接用 ComputeEngine（支持多参数指标如 atr/adx/kd）
            from stockstat_compute import ComputeEngine
            engine = ComputeEngine()
            method = getattr(engine, name, None)
            if method is not None:
                return method(*args, **params)
            # fallback 到 registry
            func = engine.registry.get(name)
            return func(*args, **params)
        # 远程路径：构建 TaskSpec 提交
        # 把位置参数也放入 params（用 _arg_N 作为 key）
        inline_params = {}
        for i, arg in enumerate(args):
            inline_params[f"_arg_{i}"] = arg
        inline_params.update(params)
        inline_params["_inline_data"] = args[0] if args else None
        spec = TaskSpec(
            task_id=str(uuid.uuid4()),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"indicator_name": name, **inline_params},
            ),
        )
        task_ref = self._backend.submit(spec)
        return task_ref.wait()

    # ── 显式异步提交 ──

    def remote(
        self,
        task_type: str,
        *,
        data_spec: Optional[DataSpec] = None,
        compute_spec: Optional[ComputeSpec] = None,
        dispatch_spec: Optional[DispatchSpec] = None,
        data: Any = None,
        **kwargs,
    ) -> TaskRef:
        """显式异步提交 — 返回 TaskRef。"""
        cs = compute_spec or ComputeSpec(task_type=task_type)
        if data is not None:
            cs.params["_inline_data"] = data
        # 合并额外 kwargs 到 params
        for k, v in kwargs.items():
            if hasattr(cs, k) and getattr(cs, k) is None:
                setattr(cs, k, v)
            else:
                cs.params[k] = v
        spec = TaskSpec(
            task_id=str(uuid.uuid4()),
            data_spec=data_spec or DataSpec(symbols=[]),
            compute_spec=cs,
            dispatch_spec=dispatch_spec or DispatchSpec(),
            trace_id=str(uuid.uuid4()),
            created_by="StockStatClient",
        )
        return self._backend.submit(spec)

    # ── 统计/信号等高级任务的便捷方法（同步等待）──

    def correlation(self, x, y, method: str = "pearson") -> Any:
        return self._submit_sync("correlation", x=x, y=y, method=method)

    def hypothesis_test(self, data, test: str, **params) -> Any:
        return self._submit_sync("hypothesis_test", data=data, test=test, **params)

    def spectral_analysis(self, signal_data, method: str = "welch", **params) -> Any:
        return self._submit_sync("spectral_analysis", signal=signal_data, method=method, **params)

    def transfer_entropy(self, x, y, k: int = 1, l: int = 1, **params) -> Any:
        return self._submit_sync("transfer_entropy", x=x, y=y, k=k, l=l, **params)

    def mutual_information(self, x, y, **params) -> Any:
        return self._submit_sync("mutual_information", x=x, y=y, **params)

    def hurst_exponent(self, data, method: str = "dfa") -> Any:
        return self._submit_sync("hurst_exponent", data=data, method=method)

    def _submit_sync(self, task_type: str, **params) -> Any:
        """统计类任务便捷提交（同步等待结果）。"""
        spec = TaskSpec(
            task_id=str(uuid.uuid4()),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type=task_type, params=params),
        )
        task_ref = self._backend.submit(spec)
        return task_ref.wait()

    # ── 集群信息 ──

    def cluster_info(self, **kwargs) -> dict:
        return self._backend.cluster_info(**kwargs)

    # ── TaskSpec 构建辅助 ──

    def build_backtest_task_spec(self, data, strategy, **kwargs) -> TaskSpec:
        """构建 backtest TaskSpec。"""
        async_submit = kwargs.pop("async_submit", False)
        timeout = kwargs.pop("timeout", 3600)
        data_spec = DataSpec(symbols=kwargs.pop("symbols", []))
        cs_params = {}
        if data is not None:
            cs_params["_inline_data"] = data
        cs_params["strategy_name"] = kwargs.pop("strategy_name", "backtest")
        return TaskSpec(
            task_id=str(uuid.uuid4()),
            data_spec=data_spec,
            compute_spec=ComputeSpec(
                task_type="backtest",
                strategy_ref=f"cloudpickle:{cloudpickle_dumps(strategy)}",
                initial_cash=kwargs.get("initial_cash", 1_000_000.0),
                cost_model=kwargs.get("cost_model"),
                fill_model=kwargs.get("fill_model"),
                execution_model=kwargs.get("execution_model"),
                benchmark=kwargs.get("benchmark"),
                trade_on=kwargs.get("trade_on", "open"),
                allow_short=kwargs.get("allow_short", False),
                periods_per_year=kwargs.get("periods_per_year"),
                params=cs_params,
            ),
            dispatch_spec=DispatchSpec(timeout=timeout),
            trace_id=str(uuid.uuid4()),
            created_by="StockStatClient",
        )


__all__ = ["ComputeAPI"]
