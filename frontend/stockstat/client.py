from __future__ import annotations

from typing import Optional

import pandas as pd

from .config import Config
from .data_access.ohlcv import DataClient
from .compute.engine import ComputeEngine
from .plot.base import PlotSpec, get_renderer
from .dsl.evaluator import Evaluator as DSLEvaluator


def _build_dsl_engine(client: "StockStatClient"):
    """Build a v2.0 DslEngine backed by the PluginRegistry.

    Returns None if the v2.0 layer is unavailable (e.g. backend not
    installed), in which case the caller falls back to the v1.7
    Evaluator.
    """
    try:
        from ._core.plugin import PluginRegistry
        from ._domain.indicators import register_default_indicators
        from ._api.dsl import DslEngine

        reg = PluginRegistry()
        register_default_indicators(reg)
        return DslEngine(reg, client=client._data_client)
    except Exception:
        return None


class PlotAPI:
    def spec(self, title: str = "", **kwargs) -> PlotSpec:
        s = PlotSpec(title=title, x_label=kwargs.get("x_label", ""),
                     y_label=kwargs.get("y_label", ""))
        for series_def in kwargs.get("series", []):
            s.add_series(**series_def)
        return s

    def get_renderer(self, name: Optional[str] = None):
        return get_renderer(name)

    def render(self, spec: PlotSpec, name: Optional[str] = None):
        renderer = self.get_renderer(name)
        return renderer.render(spec)


class StockStatClient:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        api_key: str = "",
        timeout: int = 30,
        cache_enabled: bool = True,
        use_https: bool = False,
        config: Optional[Config] = None,
        http_client=None,
        compute_backend: Optional[Any] = None,
    ):
        if config:
            self._config = config
        else:
            self._config = Config(
                host=host, port=port, api_key=api_key,
                timeout=timeout, cache_enabled=cache_enabled,
                use_https=use_https,
            )
        self._data_client = DataClient(self._config, http_client=http_client)
        self._compute = ComputeEngine(self)
        self._plot = PlotAPI()
        self._dsl = DSLEvaluator(client=self._data_client)
        # v2.0 DSL engine (auto-reflection from PluginRegistry); falls back to v1.7
        self._dsl_v2 = _build_dsl_engine(self)
        # V3: optional ComputeBackend (defaults to LocalComputeBackend)
        # When None, behavior is identical to v2.1 (direct BacktestEngine call)
        self._compute_backend = compute_backend

    @classmethod
    def from_env(cls) -> "StockStatClient":
        return cls(config=Config.from_env())

    @classmethod
    def from_dict(cls, d: dict) -> "StockStatClient":
        return cls(config=Config.from_dict(d))

    def ohlcv(
        self,
        symbol: str,
        source: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timeframe: str = "1d",
        limit: Optional[int] = None,
        order: Optional[str] = None,
    ) -> pd.DataFrame:
        return self._data_client.ohlcv(
            symbol=symbol, source=source, start=start, end=end,
            timeframe=timeframe, limit=limit, order=order,
        )

    def ohlcv_batch(
        self,
        symbols: list[str],
        source: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timeframe: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        return self._data_client.ohlcv_batch(
            symbols=symbols, source=source, start=start, end=end,
            timeframe=timeframe,
        )

    def ingest(
        self,
        symbol: str,
        source: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timeframe: str = "1d",
    ) -> dict:
        return self._data_client.ingest(
            symbol=symbol, source=source, start=start, end=end,
            timeframe=timeframe,
        )

    def symbols(self, asset_type: Optional[str] = None) -> list[dict]:
        return self._data_client.symbols(asset_type)

    def sources(self) -> list[dict]:
        return self._data_client.sources()

    def health(self) -> bool:
        return self._data_client.health()

    @property
    def compute(self) -> ComputeEngine:
        return self._compute

    @property
    def plot(self) -> PlotAPI:
        return self._plot

    @property
    def compute_backend(self):
        """V3 ComputeBackend (LocalComputeBackend by default, lazily created)."""
        if self._compute_backend is None:
            from ._core.compute import LocalComputeBackend
            self._compute_backend = LocalComputeBackend(
                client=self, data_client=self._data_client, mode="online",
            )
        return self._compute_backend

    def backtest(self, data, strategy, **kwargs):
        """Convenience wrapper to run a backtest using this client's ComputeEngine.

        ``data`` may be a dict ``{symbol: {timeframe: df}}`` or a ``Universe``.
        ``strategy`` is a ``Strategy`` instance or ``@strategy``-decorated function.
        Keyword args are forwarded to ``BacktestEngine``.

        V3: When ``async_submit=True`` is passed and a ComputeBackend is
        configured, returns a :class:`TaskRef` instead of blocking. The
        default (no ``async_submit``) preserves v2.1 synchronous behavior.
        """
        async_submit = kwargs.pop("async_submit", False)

        # If user explicitly injected a non-local backend, route through it
        if self._compute_backend is not None and not _is_local_backend(self._compute_backend):
            spec = _build_backtest_task_spec(data, strategy, kwargs)
            task_ref = self._compute_backend.submit(spec)
            if async_submit:
                return task_ref
            return task_ref.wait(timeout=kwargs.get("timeout", 3600))

        # Default path: identical to v2.1 (direct BacktestEngine call)
        from .backtest import BacktestEngine
        kwargs.setdefault("compute_engine", self._compute)
        engine = BacktestEngine(data=data, strategy=strategy, **kwargs)
        return engine.run()

    def run_dsl(self, dsl_string: str) -> pd.DataFrame:
        # Prefer v2.0 DslEngine (auto-reflection from PluginRegistry);
        # fall back to v1.7 Evaluator if v2.0 layer unavailable.
        if self._dsl_v2 is not None:
            return self._dsl_v2.eval(dsl_string)
        return self._dsl.eval(dsl_string)


# ── V3 helpers ─────────────────────────────────────────────────


def _is_local_backend(backend) -> bool:
    """Check whether a backend is a LocalComputeBackend instance."""
    try:
        from ._core.compute import LocalComputeBackend
        return isinstance(backend, LocalComputeBackend)
    except Exception:
        return False


def _build_backtest_task_spec(data, strategy, kwargs) -> "TaskSpec":
    """Build a TaskSpec for a backtest submission.

    Encodes the strategy via cloudpickle and translates kwargs into
    ComputeSpec fields.
    """
    import base64
    from ._core.contracts.task import (
        TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
    )
    from ._core.codec import CloudpickleCodec

    # Encode strategy
    try:
        strategy_bytes = CloudpickleCodec().encode(strategy)
        strategy_ref = "cloudpickle:" + base64.b64encode(strategy_bytes).decode("ascii")
    except Exception:
        # Fallback: cannot serialize — let the remote side fail explicitly
        strategy_ref = None

    # Extract data_spec from data dict
    symbols = []
    timeframe = "1d"
    if isinstance(data, dict):
        for sym, tfs in data.items():
            symbols.append(sym)
            if isinstance(tfs, dict) and len(tfs) > 0:
                timeframe = list(tfs.keys())[0]
            break  # only first symbol for data_spec

    # Map common backtest kwargs to ComputeSpec fields
    cs = ComputeSpec(
        task_type="backtest",
        strategy_ref=strategy_ref,
        initial_cash=kwargs.get("initial_cash", 1_000_000.0),
        benchmark=kwargs.get("benchmark"),
        trade_on=kwargs.get("trade_on", "open"),
        allow_short=kwargs.get("allow_short", False),
        periods_per_year=kwargs.get("periods_per_year"),
    )
    # cost_model / fill_model: encode as registered name if it's a string,
    # otherwise None (caller must register custom models on Worker side)
    cm = kwargs.get("cost_model")
    if isinstance(cm, str):
        cs.cost_model = cm
    fm = kwargs.get("fill_model")
    if isinstance(fm, str):
        cs.fill_model = fm
    em = kwargs.get("execution_model")
    if isinstance(em, str):
        cs.execution_model = em

    return TaskSpec(
        task_id=new_task_id(),
        data_spec=DataSpec(symbols=symbols, timeframe=timeframe),
        compute_spec=cs,
        dispatch_spec=DispatchSpec(timeout=kwargs.get("timeout", 3600)),
    )


# Re-export Any for type hint in __init__ signature
from typing import Any  # noqa: E402
