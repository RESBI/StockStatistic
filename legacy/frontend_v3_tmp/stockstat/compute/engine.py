from __future__ import annotations

from typing import Optional

import pandas as pd

from ..indicators import trend, oscillator, volatility, statistics
from ..indicators import nonlinear as _nonlinear
from .registry import register, call_indicator, list_indicators


class ComputeEngine:
    def __init__(self, client):
        self._client = client

    def ma(self, data: pd.Series, window: int = 20) -> pd.Series:
        return trend.ma(data, window)

    def ema(self, data: pd.Series, window: int = 12) -> pd.Series:
        return trend.ema(data, window)

    def macd(self, data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        return trend.macd(data, fast, slow, signal)

    def rsi(self, data: pd.Series, window: int = 14) -> pd.Series:
        return oscillator.rsi(data, window)

    def kdj(self, high: pd.Series, low: pd.Series, close: pd.Series, window: int = 9):
        return oscillator.kdj(high, low, close, window)

    def std(self, data: pd.Series, window: int = 20) -> pd.Series:
        return volatility.std(data, window)

    def atr(self, high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
        return volatility.atr(high, low, close, window)

    def bollinger(self, data: pd.Series, window: int = 20, k: float = 2.0):
        return volatility.bollinger(data, window, k)

    def corr(self, x: pd.Series, y: pd.Series) -> float:
        return statistics.corr(x, y)

    def beta(self, asset: pd.Series, benchmark: pd.Series, window: int = 60) -> pd.Series:
        return statistics.beta(asset, benchmark, window)

    def sharpe(self, returns: pd.Series, risk_free: float = 0.02, annualize: bool = True) -> float:
        return statistics.sharpe(returns, risk_free, annualize)

    def max_drawdown(self, close: pd.Series) -> float:
        return statistics.max_drawdown(close)

    def var(self, returns: pd.Series, confidence: float = 0.95) -> float:
        return statistics.var_historical(returns, confidence)

    def returns(self, data: pd.Series) -> pd.Series:
        return statistics.returns(data)

    def log_returns(self, data: pd.Series) -> pd.Series:
        return statistics.log_returns(data)

    # ── Signal processing & nonlinear dynamics ──

    def wavelet_decompose(self, signal, scales=None, wavelet: str = "morl"):
        r"""Continuous Wavelet Transform (Eq. 4.1).

        Returns ``(coef, scales)`` where *coef* has shape
        ``(len(scales), len(signal))``.
        """
        return _nonlinear.wavelet_decompose(signal, scales, wavelet)

    def spectral_entropy(self, signal, fs: float = 1.0, nperseg: int | None = None) -> float:
        r"""Spectral entropy in nats (Eq. 5.2)."""
        return _nonlinear.spectral_entropy(signal, fs, nperseg)

    def grey_relation(self, x0, xi, rho: float = 0.5) -> float:
        r"""Grey relational degree in [0, 1] (Eq. 6.1–6.2)."""
        return _nonlinear.grey_relation(x0, xi, rho)

    def gm11_predict(self, sequence) -> float:
        r"""GM(1,1) one-step-ahead forecast (Eq. 6.4–6.5)."""
        return _nonlinear.gm11_predict(sequence)

    def transfer_entropy(self, x, y, k: int = 1, n_bins: int = 4) -> float:
        r"""Transfer entropy T_{x→y} in bits (Eq. 7.2)."""
        return _nonlinear.transfer_entropy(x, y, k, n_bins)

    def hurst_dfa(self, signal) -> float:
        r"""Hurst exponent via DFA (≈0.5 random, >0.5 persistent)."""
        return _nonlinear.hurst_dfa(signal)

    def sample_entropy(self, signal, m: int = 2, r: float | None = None) -> float:
        r"""Sample entropy (Eq. 7.3)."""
        return _nonlinear.sample_entropy(signal, m, r)

    def permutation_entropy(self, signal, m: int = 3, tau: int = 1) -> float:
        r"""Permutation entropy in bits (Eq. 7.4)."""
        return _nonlinear.permutation_entropy(signal, m, tau)

    # ── Signal processing & nonlinear dynamics — PlotSpec factories ──

    def wavelet_scalogram(self, coef, scales, title: str = "CWT Scalogram",
                          cmap: str = "jet"):
        r"""Build a PlotSpec for a CWT scalogram heatmap.

        Parameters
        ----------
        coef : ndarray, shape (len(scales), n)
            Wavelet coefficients from :meth:`wavelet_decompose`.
        scales : array-like
            The scales used.
        """
        return _nonlinear.wavelet_scalogram_spec(coef, scales, title, cmap)

    def dfa_fit(self, signal, title: str = "DFA — Hurst Exponent"):
        r"""Build a log-log DFA fit PlotSpec.

        Renders fluctuation vs window size with Hurst exponent annotation.
        """
        return _nonlinear.dfa_fit_spec(signal, title)

    def psd_plot(self, signal, fs: float = 1.0, nperseg: int | None = None,
                 title: str = "Power Spectral Density"):
        r"""Build a log-log PSD PlotSpec (Welch method)."""
        return _nonlinear.psd_spec(signal, fs, nperseg, title)

    def register(self, name: str, func=None, category: str = "custom"):
        if func is not None:
            register(name, func, category)
            return func
        def decorator(f):
            register(name, f, category)
            return f
        return decorator

    def call(self, name: str, **kwargs):
        return call_indicator(name, **kwargs)

    def list_indicators(self) -> list[dict]:
        return list_indicators()

    # ── V3: remote compute offload entry points ──────────────

    def remote(self, task_type: str, *, data_spec=None, compute_spec=None,
               dispatch_spec=None, **kwargs):
        """V3 explicit async submit — returns a :class:`TaskRef`.

        Builds a :class:`TaskSpec` and submits it to the client's
        :class:`ComputeBackend`. The caller gets back a ``TaskRef``
        immediately and can ``wait()`` / ``result()`` / ``cancel()``.

        Args:
            task_type: ``"indicator"`` / ``"backtest"`` / ``"grid_search"``
                / ``"batch_backtest"`` / ``"monte_carlo"`` / ``"custom"``
            data_spec: optional :class:`DataSpec`; if None, build from
                ``symbols`` / ``timeframe`` / ``start`` / ``end`` kwargs
            compute_spec: optional :class:`ComputeSpec`; if None, build
                from ``task_type`` and remaining kwargs
            dispatch_spec: optional :class:`DispatchSpec`; defaults to
                ``DispatchSpec()``

        Returns:
            :class:`TaskRef`

        Example::

            task = client.compute.remote(
                "grid_search",
                symbols=["BTC/USDT"], timeframe="1d", start="2024-01-01",
                strategy_ref="cloudpickle:...",
                param_grid={"short": [3, 5, 8], "long": [10, 20, 30]},
                metric="sharpe",
            )
            result = task.wait(timeout=3600)
        """
        from .._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
        )

        # Resolve data_spec
        if data_spec is None:
            ds = DataSpec(
                symbols=kwargs.pop("symbols", []),
                timeframe=kwargs.pop("timeframe", "1d"),
                start=kwargs.pop("start", None),
                end=kwargs.pop("end", None),
                source=kwargs.pop("source", None),
            )
        else:
            ds = data_spec

        # Resolve compute_spec
        if compute_spec is None:
            # Extract known ComputeSpec fields from kwargs
            known_fields = {
                "strategy_ref", "strategy_codec", "initial_cash",
                "cost_model", "fill_model", "execution_model",
                "benchmark", "trade_on", "allow_short", "periods_per_year",
                "param_grid", "metric", "maximize",
                "strategies", "fee_models",
                "n_simulations", "seed",
            }
            cs_kwargs = {k: v for k, v in kwargs.items() if k in known_fields}
            extra_params = {k: v for k, v in kwargs.items() if k not in known_fields}
            # Combine: extra_params go into params, but indicator 'method'/'kwargs'
            # also go into params
            if "method" in extra_params:
                cs_kwargs.setdefault("params", {})["method"] = extra_params.pop("method")
            if "kwargs" in extra_params:
                cs_kwargs.setdefault("params", {})["kwargs"] = extra_params.pop("kwargs")
            # Merge remaining extras into params
            if extra_params:
                cs_kwargs.setdefault("params", {}).update(extra_params)
            cs = ComputeSpec(task_type=task_type, **cs_kwargs)
        else:
            cs = compute_spec

        # Resolve dispatch_spec
        if dispatch_spec is None:
            dispatch_spec = DispatchSpec()

        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=ds,
            compute_spec=cs,
            dispatch_spec=dispatch_spec,
        )

        # Submit to the client's compute_backend
        backend = self._get_compute_backend()
        return backend.submit(spec)

    def cluster_info(self, **kwargs) -> dict:
        """V3: query the compute cluster topology.

        Returns a dict with ``dispatcher`` / ``workers`` / ``stats``
        sub-keys. For LocalComputeBackend, returns a single in-process
        worker.
        """
        backend = self._get_compute_backend()
        return backend.cluster_info(**kwargs)

    def _get_compute_backend(self):
        """Resolve the ComputeBackend from the bound client.

        If no client is bound (e.g. ``ComputeEngine(client=None)`` in
        a Worker), construct a default LocalComputeBackend on demand.
        """
        if self._client is not None and hasattr(self._client, "compute_backend"):
            return self._client.compute_backend
        # Fallback: create a LocalComputeBackend with no data access
        from .._core.compute import LocalComputeBackend
        return LocalComputeBackend(client=self._client)
