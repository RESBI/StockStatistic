import numpy as np
import pandas as pd
from stockstat_kernel.catalog import INDICATORS


def series():
    return pd.Series(np.linspace(100.0, 130.0, 128))


def test_indicator_catalog_contains_exact_v31_migration_set():
    expected = {
        "ma",
        "ema",
        "macd",
        "rsi",
        "kdj",
        "std",
        "atr",
        "bollinger",
        "corr",
        "beta",
        "sharpe",
        "max_drawdown",
        "var",
        "returns",
        "log_returns",
        "wavelet_decompose",
        "spectral_entropy",
        "grey_relation",
        "gm11_predict",
        "transfer_entropy",
        "hurst_dfa",
        "sample_entropy",
        "permutation_entropy",
    }
    assert {item.id for item in INDICATORS.list()} == expected


def test_ma_ema_and_bollinger_semantics():
    values = series()
    pd.testing.assert_series_equal(
        INDICATORS.compute("ma", values, window=5), values.rolling(5).mean()
    )
    pd.testing.assert_series_equal(
        INDICATORS.compute("ema", values, window=5), values.ewm(span=5, adjust=False).mean()
    )
    upper, middle, lower = INDICATORS.compute("bollinger", values, window=5, k=2.0)
    pd.testing.assert_series_equal(middle, values.rolling(5).mean())
    assert (upper.dropna() >= middle.dropna()).all()
    assert (lower.dropna() <= middle.dropna()).all()


def test_rng_independent_timeseries_functions_are_deterministic():
    values = np.sin(np.linspace(0, 20, 128))
    first = INDICATORS.compute("permutation_entropy", values)
    second = INDICATORS.compute("permutation_entropy", values)
    assert first == second
