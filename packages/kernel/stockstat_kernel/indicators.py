from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from itertools import permutations

import numpy as np
import pandas as pd
from scipy.signal import welch
from scipy.stats import linregress


def ma(data: pd.Series, window: int = 20) -> pd.Series:
    return data.rolling(window=window).mean()


def ema(data: pd.Series, window: int = 12) -> pd.Series:
    return data.ewm(span=window, adjust=False).mean()


def macd(data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    fast_line = ema(data, fast)
    slow_line = ema(data, slow)
    line = fast_line - slow_line
    signal_line = ema(line, signal)
    return line, signal_line, line - signal_line


def rsi(data: pd.Series, window: int = 14) -> pd.Series:
    delta = data.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def kdj(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 9):
    lowest = low.rolling(window).min()
    highest = high.rolling(window).max()
    rsv = (close - lowest) / (highest - lowest) * 100.0
    k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d = k.ewm(alpha=1 / 3, adjust=False).mean()
    return k, d, 3.0 * k - 2.0 * d


def std(data: pd.Series, window: int = 20) -> pd.Series:
    return data.rolling(window).std()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    previous = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous).abs(), (low - previous).abs()], axis=1
    ).max(axis=1)
    return true_range.rolling(window).mean()


def bollinger(data: pd.Series, window: int = 20, k: float = 2.0):
    middle = ma(data, window)
    sigma = std(data, window)
    return middle + k * sigma, middle, middle - k * sigma


def corr(x: pd.Series, y: pd.Series) -> float:
    aligned = pd.concat([x, y], axis=1, keys=["x", "y"]).dropna()
    return float("nan") if len(aligned) < 3 else float(aligned["x"].corr(aligned["y"]))


def beta(asset: pd.Series, benchmark: pd.Series, window: int = 60) -> pd.Series:
    aligned = pd.concat([asset, benchmark], axis=1, keys=["asset", "benchmark"]).dropna()
    return (
        aligned.asset.rolling(window).cov(aligned.benchmark)
        / aligned.benchmark.rolling(window).var()
    )


def sharpe(returns: pd.Series, risk_free: float = 0.02, annualize: bool = True) -> float:
    periods = 252 if annualize else 1
    excess = returns - risk_free / periods
    deviation = excess.std()
    return 0.0 if deviation == 0 else float(excess.mean() / deviation * np.sqrt(periods))


def max_drawdown(close: pd.Series) -> float:
    cumulative = close / close.iloc[0]
    drawdown = (cumulative - cumulative.cummax()) / cumulative.cummax()
    return float(drawdown.min())


def var(returns: pd.Series, confidence: float = 0.95) -> float:
    return float(np.percentile(returns.dropna(), (1 - confidence) * 100))


def returns(data: pd.Series) -> pd.Series:
    return data.pct_change(fill_method=None)


def log_returns(data: pd.Series) -> pd.Series:
    return np.log(data / data.shift(1))


def wavelet_decompose(signal: Iterable[float], scales=None, wavelet: str = "morl"):
    x = np.asarray(signal, dtype=float)
    if len(x) < 4:
        raise ValueError("signal must have at least 4 points")
    if scales is None:
        scales = np.arange(1, max(2, len(x) // 2 + 1))
    scales = np.asarray(scales, dtype=float)
    try:
        import pywt
    except ImportError as exc:
        raise RuntimeError("PyWavelets is required for wavelet_decompose@1.0") from exc
    coefficients, _ = pywt.cwt(x, scales, wavelet, sampling_period=1.0)
    return coefficients, scales


def spectral_entropy(signal: Iterable[float], fs: float = 1.0, nperseg: int | None = None) -> float:
    x = np.asarray(signal, dtype=float)
    if len(x) < 4:
        return 0.0
    size = min(nperseg or 256, len(x))
    _, power = welch(x, fs=fs, nperseg=size)
    probabilities = power / (power.sum() + 1e-30)
    probabilities = probabilities[probabilities > 0]
    return float(-np.sum(probabilities * np.log(probabilities)))


def grey_relation(x0, xi, rho: float = 0.5) -> float:
    left = np.asarray(x0, dtype=float)
    right = np.asarray(xi, dtype=float)
    if left.shape != right.shape:
        raise ValueError("x0 and xi must have the same shape")
    if len(left) == 0:
        return 0.0
    distance = np.abs(left / (left[0] + 1e-30) - right / (right[0] + 1e-30))
    maximum = distance.max()
    if maximum < 1e-15:
        return 1.0
    coefficient = (distance.min() + rho * maximum) / (distance + rho * maximum + 1e-30)
    return float(coefficient.mean())


def gm11_predict(sequence) -> float:
    x = np.asarray(sequence, dtype=float).ravel()
    if len(x) < 4:
        return float(x[-1])
    accumulated = np.cumsum(x)
    matrix = np.column_stack([-0.5 * (accumulated[1:] + accumulated[:-1]), np.ones(len(x) - 1)])
    try:
        a, b = np.linalg.lstsq(matrix, x[1:].reshape(-1, 1), rcond=None)[0].flatten()
    except np.linalg.LinAlgError:
        return float(x[-1])
    if abs(a) < 1e-12:
        return float(x[-1])
    current = (x[0] - b / a) * np.exp(-a * len(x)) + b / a
    previous = (x[0] - b / a) * np.exp(-a * (len(x) - 1)) + b / a
    return float(current - previous)


def transfer_entropy(x, y, k: int = 1, n_bins: int = 4) -> float:
    left = np.asarray(x, dtype=float)
    right = np.asarray(y, dtype=float)
    if len(left) != len(right) or len(left) <= k + 2:
        return 0.0
    future = right[k + 1 :]
    right_past = right[k:-1]
    left_past = left[k:-1]
    if len(future) < 5:
        return 0.0

    def quantile_bins(values):
        if len(np.unique(values)) < n_bins:
            return np.zeros(len(values), dtype=int)
        edges = np.quantile(values, np.linspace(0, 1, n_bins + 1))
        edges[-1] += 1e-12
        return np.digitize(values, edges[1:-1])

    def entropy(labels):
        counts = Counter(labels)
        total = sum(counts.values())
        return -sum(value / total * np.log2(value / total) for value in counts.values())

    def conditional_entropy(values, conditions):
        groups = defaultdict(list)
        for value, condition in zip(values, conditions, strict=True):
            groups[condition].append(value)
        return sum(len(group) / len(values) * entropy(group) for group in groups.values())

    yf = quantile_bins(future)
    yp = quantile_bins(right_past)
    xp = quantile_bins(left_past)
    combined = yp * (n_bins + 1) + xp
    return float(max(0.0, conditional_entropy(yf, yp) - conditional_entropy(yf, combined)))


def hurst_dfa(signal) -> float:
    x = np.asarray(signal, dtype=float)
    if len(x) < 16:
        return 0.5
    integrated = np.cumsum(x - x.mean())
    sizes = np.unique(np.logspace(np.log2(4), np.log2(len(x) // 4), 20, base=2, dtype=int))
    sizes = sizes[sizes >= 4]
    fluctuation = []
    used = []
    for size in sizes:
        segments = len(integrated) // size
        if segments < 1:
            continue
        local = []
        for segment in range(segments):
            values = integrated[segment * size : (segment + 1) * size]
            time = np.arange(size)
            fit = np.polyfit(time, values, 1)
            local.append(np.sqrt(np.mean((values - np.polyval(fit, time)) ** 2)))
        fluctuation.append(np.mean(local))
        used.append(size)
    if len(fluctuation) < 4 or np.any(np.asarray(fluctuation) <= 0):
        return 0.5
    return float(linregress(np.log2(used), np.log2(fluctuation)).slope)


def sample_entropy(signal, m: int = 2, r: float | None = None) -> float:
    x = np.asarray(signal, dtype=float)
    tolerance = 0.2 * np.std(x) if r is None else r
    if len(x) < m + 2 or tolerance == 0:
        return 0.0

    def count(length):
        templates = np.array([x[index : index + length] for index in range(len(x) - length + 1)])
        matches = 0
        for first in range(len(templates)):
            for second in range(first + 1, len(templates)):
                if np.max(np.abs(templates[first] - templates[second])) < tolerance:
                    matches += 1
        return matches

    before = count(m)
    after = count(m + 1)
    return 0.0 if before == 0 or after == 0 else float(-np.log(after / before))


def permutation_entropy(signal, m: int = 3, tau: int = 1) -> float:
    x = np.asarray(signal, dtype=float)
    if len(x) < m * tau:
        return 0.0
    counts = {pattern: 0 for pattern in permutations(range(m))}
    for index in range(len(x) - (m - 1) * tau):
        window = [x[index + offset * tau] for offset in range(m)]
        counts[tuple(np.argsort(window))] += 1
    total = sum(counts.values())
    probabilities = np.array([count / total for count in counts.values() if count > 0])
    return 0.0 if total == 0 else float(-np.sum(probabilities * np.log2(probabilities)))
