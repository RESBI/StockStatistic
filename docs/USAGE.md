# StockStat V3.1 Usage Guide

> **Version**: v3.1
> **Test baseline**: 882 tests passed + 1 skipped
> **Related**: [README.md](../README.md) | [DESIGN.md](../DESIGN.md)

---

## Table of Contents

1. [Environment Setup](#1-environment-setup)
2. [Data Ingestion and Storage](#2-data-ingestion-and-storage)
3. [Computing Indicators](#3-computing-indicators)
4. [Backtesting](#4-backtesting)
5. [Batch Backtest and Grid Search](#5-batch-backtest-and-grid-search)
6. [Statistical Analysis](#6-statistical-analysis)
7. [Signal Processing](#7-signal-processing)
8. [Nonlinear Dynamics](#8-nonlinear-dynamics)
9. [Grey Systems](#9-grey-systems)
10. [Machine Learning](#10-machine-learning)
11. [Portfolio Risk Management](#11-portfolio-risk-management)
12. [DSL Strategy Expressions](#12-dsl-strategy-expressions)
13. [Visualization](#13-visualization)
14. [Result Export](#14-result-export)
15. [CLI](#15-cli)
16. [Distributed Computing](#16-distributed-computing)
17. [Deployment Scenarios](#17-deployment-scenarios)
18. [PostgreSQL Configuration](#18-postgresql-configuration)
19. [REST API Reference](#19-rest-api-reference)
20. [Environment Variables](#20-environment-variables)

---

## 1. Environment Setup

### 1.1 Installation

V3.1 uses multi-package publishing. The five module packages can be installed independently or all at once. The most common approach is editable installation (`-e` editable mode), so code changes take effect immediately:

```bash
# Option 1: install all five modules independently (recommended for contributors)
pip install -e packages/foundation
pip install -e packages/storage
pip install -e packages/compute
pip install -e packages/invocation
pip install -e packages/dispatcher

# Option 2: user install (entry package only; pulls in necessary deps)
pip install -e packages/invocation
```

Installation order does not affect the final result — pip resolves dependencies automatically. However, installing Foundation first is recommended since the other four packages depend on it.

### 1.2 Optional Dependencies

V3.1 makes heavy dependencies optional; core functionality runs under minimal dependencies. Enable extras as needed:

```bash
pip install -e packages/storage[postgres]     # PostgreSQL driver (psycopg2)
pip install -e packages/compute[ml]           # scikit-learn + xgboost (machine learning)
pip install -e packages/compute[signal]       # PyWavelets (wavelet transform)
pip install -e packages/compute[nonlinear]    # nolds (nonlinear analysis enhancement)
pip install -e packages/foundation[redis]     # Redis transport (cross-process persistent queue)
pip install -e packages/foundation[msgpack]   # Msgpack codec (compact binary)
pip install matplotlib                         # visualization (ChartSpec rendering)
```

> **Graceful degradation**: When optional dependencies are missing, the affected features do not crash the program — they automatically fall back to alternative implementations or raise a clear `ImportError` with installation instructions. For example:
> - Without PyWavelets, the `wavelet` handler falls back to a self-implemented Morlet CWT.
> - Without redis, `RedisTransport` / `RedisTaskQueue` raise `ImportError` suggesting `pip install stockstat-dispatcher[redis]`.
> - Without yfinance, the corresponding tests are skipped (1 skipped).

### 1.3 Verify Installation

After installation, run the following code to confirm all packages loaded correctly and all 38 handlers are registered:

```python
import stockstat_foundation, stockstat_compute, stockstat_backend
import stockstat_dispatcher, stockstat
print("All V3.1 packages OK")
print("Foundation:", stockstat_foundation.__version__)
print("Handlers:", len(stockstat_compute.ALL_TASK_TYPES))  # 38
```

If the output shows `Handlers: 38`, all handler sub-packages in the Compute module have been correctly imported and registered.

---

## 2. Data Ingestion and Storage

Data is the starting point of quantitative research. V3.1's Storage module provides OHLCV data persistence, querying, and ingestion, supporting both SQLite (development) and PostgreSQL (production).

### 2.1 Starting the Storage Service

Storage is a FastAPI service started via CLI. It defaults to SQLite (WAL mode) with zero configuration:

```bash
# SQLite (default, zero-config)
stockstat-backend serve --host 0.0.0.0 --port 8000

# PostgreSQL (production)
STOCKSTAT_DATABASE_URL=postgresql://user:pwd@host:5432/stockstat \
stockstat-backend serve --host 0.0.0.0 --port 8000
```

After starting, visit `http://localhost:8000/docs` for Swagger docs, or `http://localhost:8000/health` for health status.

### 2.2 Ingesting Data

V3.1 provides 3 data source adapters. The most convenient way is via the Client's `ingest` method:

```python
from stockstat import StockStatClient

client = StockStatClient(storage_url="http://localhost:8000")

# Option 1: ingest from Binance
from stockstat_backend import BinanceAdapter
adapter = BinanceAdapter()
df = adapter.fetch_ohlcv("BTCUSDT", "1d")
rows = client.ingest("BTC/USDT", "1d", df)
print(f"Wrote {rows} rows")

# Option 2: ingest from synthetic source (dev/test, no network needed)
from stockstat_backend import SyntheticAdapter
adapter = SyntheticAdapter(seed=42)
df = adapter.fetch_ohlcv("TEST/USDT", "1d")
client.ingest("TEST/USDT", "1d", df)

# Option 3: write a DataFrame directly
import pandas as pd
df = pd.DataFrame({
    "timestamp": pd.date_range("2024-01-01", periods=100, freq="D"),
    "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...,
})
client.ingest("CUSTOM", "1d", df)
```

`ingest(symbol, timeframe, data)` returns the number of rows written. Data is automatically deduplicated (composite primary key `(symbol, timeframe, timestamp)`).

### 2.3 Querying Data

```python
# Query OHLCV for a single symbol
df = client.ohlcv("BTC/USDT", timeframe="1d", start="2024-01-01")
print(df.head())
#                           open     high     low    close    volume
# timestamp
# 2024-01-01  42000.0  42500.0  41800.0  42300.0  1500.0
# ...

# List all symbols in the database
symbols = client.list_symbols()
print(symbols)  # ["BTC/USDT", "TEST/USDT", ...]
```

`ohlcv()` returns a pandas DataFrame with columns `timestamp` / `open` / `high` / `low` / `close` / `volume`. DataClient has a built-in in-process cache; repeated queries with the same parameters do not hit Storage again.

### 2.4 CLI Data Commands

```bash
# Ingest from a data source
stockstat data ingest --symbol BTC/USDT --source binance

# Query data (shows first 20 rows by default)
stockstat data fetch BTC/USDT --timeframe 1d

# List all symbols
stockstat data list
```

`stockstat-backend` also provides a standalone data CLI:

```bash
stockstat-backend ingest --symbol BTC/USDT --source binance
stockstat-backend list-symbols
stockstat-backend init-db          # initialize database tables
```

---

## 3. Computing Indicators

V3.1 includes 40+ technical indicators, accessed via `client.compute.*`. Under the local backend they return immediately; under the remote backend they automatically build an `indicator` TaskSpec for submission. All indicators accept pandas Series or DataFrame and return Series or DataFrame.

### 3.1 Trend Indicators

Trend indicators measure the directionality of prices. The example below shows the common moving-average family and MACD:

```python
# Simple Moving Average (SMA)
sma = client.compute.ma(data.close, window=20)

# Exponential Moving Average (EMA — faster weight decay, more sensitive to recent prices)
ema = client.compute.ema(data.close, window=12)

# Weighted Moving Average (WMA — linear weights)
wma = client.compute.wma(data.close, window=20)

# Double Exponential Moving Average (DEMA — reduces lag)
dema = client.compute.dema(data.close, window=20)

# Triple Exponential Moving Average (TEMA — further reduces lag)
tema = client.compute.tema(data.close, window=20)

# Hull Moving Average (HMA — smooth and low-lag)
hma = client.compute.hma(data.close, window=20)

# MACD — returns DataFrame with macd / signal / histogram columns
macd_df = client.compute.macd(data.close, fast=12, slow=26, signal=9)
print(macd_df.tail())
#                    macd    signal  histogram
# 2024-04-26  120.5  80.3      40.2
```

Also available: `adx` (Average Directional Index, trend strength), `dpo` (Detrended Price Oscillator), `trix` (Triple Smoothed MA).

![Close + MA + Bollinger](../docs/images/indicators_bollinger.png)

### 3.2 Oscillator Indicators

Oscillators measure overbought/oversold conditions, typically fluctuating within a fixed range:

```python
# RSI (Relative Strength Index, 0–100; >70 overbought, <30 oversold)
rsi = client.compute.rsi(data.close, window=14)

# KD Stochastic — returns DataFrame with k / d columns
kd_df = client.compute.kd(data.high, data.low, data.close, k_window=9, d_window=3)

# Williams %R (-100–0; near 0 is overbought)
wr = client.compute.williams_r(data.high, data.low, data.close, window=14)

# CCI (Commodity Channel Index; >100 overbought, <-100 oversold)
cci = client.compute.cci(data.high, data.low, data.close, window=20)
```

![RSI overbought/oversold](../docs/images/indicators_rsi.png)

### 3.3 Volatility Indicators

Volatility indicators measure price dispersion:

```python
# Bollinger Bands — returns DataFrame with upper / middle / lower / bandwidth
bb = client.compute.bollinger(data.close, window=20, std=2.0)

# ATR (Average True Range — measures volatility magnitude)
atr = client.compute.atr(data.high, data.low, data.close, window=14)

# Keltner Channel (ATR-based channel)
keltner = client.compute.keltner(data.high, data.low, data.close, window=20, mult=1.5)

# Donchian Channel (high/low channel)
donchian = client.compute.donchian(data.high, data.low, window=20)

# Rolling standard deviation
stddev = client.compute.stddev(data.close, window=20)
```

### 3.4 Statistical Indicators

Statistical indicators are based on rolling-window statistics:

```python
# Rolling correlation
corr = client.compute.rolling_corr(x, y, window=20)

# Rolling Beta (asset sensitivity to market)
beta = client.compute.rolling_beta(asset, market, window=20)

# Rolling Z-Score (standardization)
zsc = client.compute.zscore(data.close, window=20)

# Rolling percentile
pct = client.compute.percentile(data.close, window=20)
```

### 3.5 Nonlinear Indicators

Nonlinear indicators measure the complexity and determinism of a time series:

```python
# Hurst exponent (R/S method) — H≈0.5 random walk, H>0.5 persistence, H<0.5 anti-persistence
hurst = client.compute.hurst_rs(data.close)

# Sample entropy — higher is more complex
sampen = client.compute.sample_entropy(data.close[:100], m=2)

# Permutation entropy — measures regularity
permen = client.compute.permutation_entropy(data.close[:100], m=4, tau=1)
```

![MACD histogram](../docs/images/indicators_macd.png)

---

## 4. Backtesting

Backtesting is the core of quantitative research. V3.1's BacktestEngine is an event-driven, bar-by-bar engine supporting custom strategies, multiple fee models, fill models, and execution models.

### 4.1 Basic Backtest

The simplest backtest — a buy-and-hold strategy. A strategy is a function receiving `(i, bar, data, ctx)` that returns a `Signal` or `None`:

```python
from stockstat import StockStatClient
from stockstat_compute import Signal

client = StockStatClient()

def buy_and_hold(i, bar, data, ctx):
    """Buy on the first bar, then hold."""
    if i == 0:
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy")
    return None

result = client.backtest(data, buy_and_hold, initial_cash=10000)
print(result.summary())
# BacktestResult: total_return=105.79%, sharpe=0.627, max_drawdown=-27.84%
```

`result` is a `BacktestResult` object containing:
- `metrics`: `BacktestMetrics` (18 metrics)
- `equity_curve`: equity curve DataFrame
- `trades`: trade list
- `summary()`: human-readable summary text

### 4.2 MA Crossover Strategy

The classic moving-average crossover — buy when the short MA crosses above the long MA, sell when it crosses below:

```python
def ma_cross(i, bar, data, ctx):
    if i < 20:
        return None
    ma5 = data["close"].iloc[i-5:i+1].mean()
    ma20 = data["close"].iloc[i-20:i+1].mean()
    prev_ma5 = data["close"].iloc[i-6:i].mean()
    prev_ma20 = data["close"].iloc[i-21:i].mean()
    if prev_ma5 <= prev_ma20 and ma5 > ma20:
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy")
    if prev_ma5 >= prev_ma20 and ma5 < ma20:
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="sell")
    return None

result = client.backtest(data, ma_cross, initial_cash=10000,
                         cost_model="F1_SpotNoBNB")
```

You can also use the `StrategyBase` class for stateful strategies:

```python
from stockstat_compute import StrategyBase

class MaCross(StrategyBase):
    name = "ma_cross"
    def __init__(self, short=5, long=20):
        self.short = short
        self.long = long
    def on_bar(self, i, bar, data, ctx):
        if i < self.long:
            return None
        s = data["close"].iloc[i-self.short:i+1].mean()
        l = data["close"].iloc[i-self.long:i+1].mean()
        ps = data["close"].iloc[i-self.short-1:i].mean()
        pl = data["close"].iloc[i-self.long-1:i].mean()
        if ps <= pl and s > l:
            return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy")
        if ps >= pl and s < l:
            return Signal(timestamp=bar["timestamp"], symbol="TEST", side="sell")
        return None

result = client.backtest(data, MaCross(short=5, long=20), initial_cash=10000)
```

![Backtest equity curve + drawdown](../docs/images/backtest_equity_drawdown.png)

### 4.3 Fee Models

V3.1 includes 10 predefined fee models covering mainstream trading scenarios:

| Name | Rate | Description |
|------|------|-------------|
| `default` | 0.1% | Default rate |
| `zero` | 0% | No fee (baseline comparison) |
| `F1_SpotNoBNB` | 0.1% | Binance spot without BNB discount |
| `F2_SpotBNB` | 0.075% | Binance spot with BNB discount |
| `F3_FutNoBNB` | 0.04% | Binance futures without BNB |
| `F4_FutBNB` | 0.018% | Binance futures with BNB |
| `binance_spot` | 0.1% | Binance spot (same as F1) |
| `binance_futures_bnb` | 0.018% | Binance futures BNB (same as F4) |
| `binance_futures` | 0.04% | Binance futures (same as F3) |
| `stock` | 0.05% | US stocks (min $5) |

```python
# Use a predefined fee
result = client.backtest(data, strategy, cost_model="F4_FutBNB")

# Use a custom fee (pass a numeric string)
result = client.backtest(data, strategy, cost_model="0.0008")  # 0.08%
```

### 4.4 Fill Models

Fill models determine at what price an order is filled. V3.1 provides 5 models, all supporting `slippage_bps` (slippage in basis points):

| Name | Fill price | Use case |
|------|------------|----------|
| `next_open` | Next bar's open | Default, closest to real trading |
| `this_close` | Current bar's close | Signal = fill |
| `next_close` | Next bar's close | Delayed fill |
| `intrabar_fill` | Next bar's (H+L+C)/3 | Approximate VWAP |
| `signal_price` | Signal price | Limit order |

```python
result = client.backtest(data, strategy,
                         fill_model="next_open",
                         cost_model="F1_SpotNoBNB")
```

### 4.5 Execution Models

Execution models determine when an order triggers:

| Name | Behavior |
|------|----------|
| `next_bar` | Triggers on next bar (default) |
| `intrabar` | Triggers within the bar |

```python
result = client.backtest(data, strategy, execution_model="intrabar")
```

### 4.6 Async Backtest

For long-running backtests, use async mode — submit and get a `TaskRef` immediately, then `wait()` when you need the result:

```python
# Async submit
task = client.backtest(data, strategy, async_submit=True)
print(task.id, task.status)  # UUID + "pending"

# ... do other things ...

# Block for result (up to 3600 seconds)
result = task.wait(timeout=3600)
```

`TaskRef` also supports `result()` (non-blocking), `ready()` (check completion), `cancel()` (cancel task), `stream_results()` (stream partial results).

---

## 5. Batch Backtest and Grid Search

### 5.1 Batch Backtest (Strategy × Fee)

Batch backtest runs multiple strategies with multiple fee models simultaneously, returning a summary DataFrame. Ideal for comparing strategy performance across different fees:

```python
strategies = {
    "buy_hold": buy_and_hold,
    "ma_cross_5_20": lambda i, b, d, c: ma_cross(i, b, d, c, 5, 20),
    "ma_cross_3_10": lambda i, b, d, c: ma_cross(i, b, d, c, 3, 10),
}
df = client.batch_backtest(
    data, strategies,
    fee_models=["F1_SpotNoBNB", "F2_SpotBNB", "F3_FutNoBNB", "F4_FutBNB"],
    initial_cash=10000,
)
print(df[["strategy", "fee_model", "sharpe", "max_drawdown"]])
#        strategy        fee_model   sharpe  max_drawdown
# 0    buy_hold      F1_SpotNoBNB    0.627        -0.278
# 1    buy_hold      F2_SpotBNB      0.631        -0.276
# ...
```

In distributed mode, `batch_backtest` is sharded by `param_wise` strategy — each Worker runs a subset of strategy×fee combinations, and `merge_results` concatenates the final DataFrame.

![Batch backtest Sharpe comparison](../docs/images/backtest_batch_sharpe.png)

### 5.2 Grid Search

Grid search exhausts all parameter combinations to find optimal parameters. `grid_search` accepts a `StrategyBase` subclass and a parameter grid, returning a DataFrame sorted by the metric:

```python
df = client.grid_search(
    data, MaCross,
    param_grid={"short": [3, 5, 8, 10], "long": [20, 30, 40, 50]},
    metric="sharpe",    # sort metric
    maximize=True,      # descending (find max Sharpe)
    initial_cash=10000,
)
print(df.head())
#    short  long    sharpe  total_return  max_drawdown
# 0      5    20     0.812        0.452        -0.184
# 1      3    20     0.768        0.398        -0.201
# ...
```

The parameter grid's Cartesian product is 4×4=16 combinations. In distributed mode, sharded by `param_wise` — each Worker runs a subset.

### 5.3 Monte Carlo Simulation

Monte Carlo evaluates a strategy's statistical robustness by randomly resampling the return sequence:

```python
from stockstat_compute import MonteCarloEngine

engine = MonteCarloEngine(data, buy_and_hold, initial_cash=10000,
                          n_simulations=1000, seed=42)
summary = engine.summary()
print(f"Mean return: {summary['mean_return']:.2%}")
print(f"5th percentile: {summary['p5_return']:.2%}")
print(f"Prob(loss): {summary['prob_loss']:.1%}")
```

In distributed mode, `monte_carlo` is sharded by `param_wise` — 1000 simulations are split across N Workers, each running a portion with a different seed, then merging statistics.

### 5.4 Walk-Forward Validation

Walk-Forward simulates a rolling train-test window to evaluate out-of-sample stability:

```python
from stockstat_compute import WalkForward

wf = WalkForward(data, buy_and_hold,
                 train_window=252,   # training window (~1 year daily)
                 test_window=63,     # test window (~3 months daily)
                 step=63,            # rolling step
                 initial_cash=10000)
df = wf.run()
print(df[["window", "total_return", "sharpe"]])
#    window  total_return  sharpe
# 0       1        0.052    0.42
# 1       2       -0.018   -0.15
# ...
```

---

## 6. Statistical Analysis

8 statistical test handlers (Tier 2), covering common classical statistical inference scenarios. Called via `client.compute.*` convenience methods or `client.compute._submit_sync(task_type, **params)`.

### 6.1 Correlation Analysis

Computes the correlation coefficient and confidence interval between two series. Supports Pearson (linear), Spearman (rank), and Kendall (rank) methods:

```python
result = client.compute.correlation(x, y, method="pearson")
# {"method": "pearson", "r": 0.612, "p_value": 0.0001,
#  "n": 100, "ci_lower": 0.52, "ci_upper": 0.69}
```

The confidence interval is computed via Fisher z-transformation. `r` near 1 indicates strong positive correlation, near -1 strong negative; `p_value < 0.05` indicates statistical significance.

![Correlation scatter](../docs/images/stats_correlation.png)

### 6.2 Hypothesis Testing

Unified hypothesis testing interface; select test type via the `test` parameter:

```python
# Chi-square independence test (2×2 contingency table)
result = client.compute.hypothesis_test(
    data={"table": [[10, 20], [30, 40]]},
    test="chi2_independence",
)
# {"statistic": 1.33, "p_value": 0.248, "cramers_v": 0.058}

# One-sample t-test (test whether mean equals popmean)
result = client.compute.hypothesis_test(data=x, test="t_test", popmean=0)
```

### 6.3 Bootstrap Confidence Interval

Estimates confidence intervals for a statistic via resampling, without distributional assumptions:

```python
result = client.compute._submit_sync("bootstrap", n_resamples=1000)
# {"estimate": 0.002, "ci_lower": -0.001, "ci_upper": 0.005, "se": 0.0015}
```

### 6.4 Permutation Test

Non-parametric test that builds a null distribution by randomly shuffling labels:

```python
result = client.compute._submit_sync("permutation_test",
                                      x=group_a, y=group_b, n_permutations=1000)
# {"observed_stat": 0.5, "p_value": 0.032, "null_distribution": [...]}
```

### 6.5 Chow Test

Tests whether a structural breakpoint exists between two time periods:

```python
result = client.compute._submit_sync("chow_test",
    data={"x": x_series, "y": y_series, "split_point": 50})
# {"statistic": 4.21, "p_value": 0.007, "has_breakpoint": True}
```

### 6.6 Survival Analysis

Analyzes "time-to-event" data, estimating the survival function:

```python
result = client.compute._submit_sync("survival_analysis",
    data={"duration": durations, "event": events})
# {"survival_curve": {...}, "median_survival": 12.5}
```

### 6.7 Empirical CDF

```python
result = client.compute._submit_sync("ecdf", data=sample)
# {"x": [...], "y": [...], "n": 100}
```

### 6.8 Multiple Testing Correction

Corrects multiple p-values to control family-wise error rate or false discovery rate:

```python
result = client.compute._submit_sync("multiple_testing",
    p_values=[0.001, 0.01, 0.04, 0.5],
    method="bh_fdr")  # Benjamini-Hochberg FDR
# DataFrame: index / p_value / adjusted_p / reject
```

Supports `bonferroni` (family-wise error rate) and `bh_fdr` (false discovery rate).

---

## 7. Signal Processing

5 signal processing handlers (Tier 3), covering frequency-domain and time-frequency analysis.

### 7.1 Spectral Analysis

Estimates the power spectral density (PSD) of a signal. Supports Welch's method (segmented averaging) and periodogram:

```python
result = client.compute.spectral_analysis(signal, method="welch", nperseg=256)
# {"frequencies": [...], "psd": [...], "peak_freq": 10.0}
```

`peak_freq` is the frequency component with the highest PSD, reflecting the signal's dominant period.

![Welch PSD](../docs/images/signal_spectral.png)

### 7.2 Wavelet Transform

Continuous wavelet transform (CWT), generating a time-frequency heatmap. Falls back to a self-implemented Morlet CWT when PyWavelets is not installed:

```python
result = client.compute._submit_sync("wavelet",
    signal=signal, method="cwt",
    scales=list(range(1, 25)))
# {"coefficients": [...], "power": [...], "scales": [...]}
```

![Wavelet time-frequency heatmap](../docs/images/signal_wavelet.png)

### 7.3 Spectral Entropy

Measures the signal's complexity in the frequency domain. Range 0–1; higher is more complex (approaching white noise), lower is more regular (single frequency):

```python
result = client.compute._submit_sync("spectral_entropy", signal=signal)
# {"spectral_entropy": 0.72}
```

### 7.4 Cross-Spectrum

Analyzes the frequency-domain relationship between two signals, including coherence and phase:

```python
result = client.compute._submit_sync("cross_spectrum",
    data={"x": signal_a, "y": signal_b})
# {"coherence": [...], "phase": [...]}
```

### 7.5 Filter Design

```python
result = client.compute._submit_sync("filter_design",
    data=signal, filter_type="lowpass", cutoff=0.1)
# {"filtered": [...], "coefficients": {...}}
```

---

## 8. Nonlinear Dynamics

7 nonlinear handlers (Tier 4), for analyzing nonlinear characteristics of time series.

### 8.1 Transfer Entropy

Measures the directed information flow between two time series. The difference between `te_forward` (X→Y) and `te_backward` (Y→X), `net_te`, indicates the net information transfer direction:

```python
result = client.compute.transfer_entropy(x=btc_returns, y=eth_returns, k=1, l=1)
# {"te_forward": 0.045, "te_backward": 0.012, "net_te": 0.033,
#  "p_value": 0.03, "significant": True}
```

`significant=True` means the transfer entropy is statistically significant (based on a permutation test).

### 8.2 Hurst Exponent

Measures the long-term memory of a time series. Supports DFA (Detrended Fluctuation Analysis) and R/S methods:

```python
result = client.compute.hurst_exponent(data, method="dfa")
# {"hurst": 0.52, "fit_r2": 0.98}
```

Interpretation: H ≈ 0.5 random walk, H > 0.5 persistence (trend continuation), H < 0.5 anti-persistence (mean reversion). `fit_r2` is the R² of the log-log fit.

![Hurst DFA fit](../docs/images/nonlinear_hurst.png)

### 8.3 Mutual Information

Measures the amount of information shared between two variables (nonlinear counterpart of correlation):

```python
result = client.compute.mutual_information(x, y, estimator="binning")
# {"mutual_information": 0.35}
```

Supports `binning` (histogram) and `knn` (k-nearest neighbor) estimators.

### 8.4 Sample Entropy / Permutation Entropy

Measures the complexity and regularity of a sequence:

```python
# Sample entropy — higher is more complex
sampen = client.compute.sample_entropy(signal, m=2)

# Permutation entropy — based on permutation patterns; higher is more random
permen = client.compute.permutation_entropy(signal, m=4, tau=1)
```

### 8.5 Recurrence Quantification Analysis

Recurrence Plot (RP) and its quantitative analysis. The RP visualizes recurrence patterns of trajectories in phase space:

```python
# Recurrence plot
result = client.compute._submit_sync("recurrence_plot", data=signal, m=3, tau=1)
# {"matrix": [[0,1,0,...], [1,0,1,...], ...]}

# Recurrence quantification analysis
result = client.compute._submit_sync("rqa", data=signal, m=3, tau=1)
# {"RR": 0.12, "DET": 0.85, "LAM": 0.78, "ENTR": 2.3}
```

- `RR` (Recurrence Rate): proportion of recurrence points.
- `DET` (Determinism): proportion of recurrence points forming diagonal lines; higher is more deterministic.
- `LAM` (Laminarity): proportion forming vertical lines; reflects state trapping.
- `ENTR` (Entropy): Shannon entropy of diagonal line lengths.

![Recurrence plot](../docs/images/nonlinear_recurrence.png)

---

## 9. Grey Systems

3 grey system handlers (Tier 5), suitable for prediction and decision-making with small samples and poor information.

### 9.1 Grey Relation Analysis

Measures the degree of relation between a reference sequence and multiple comparison sequences; used for factor influence analysis:

```python
result = client.compute._submit_sync("grey_relation",
    data={"reference": ref_series, "sequences": [seq1, seq2, seq3]},
    rho=0.5)  # resolution coefficient, typically 0.5
# {"relation_degrees": [0.85, 0.62, 0.43], "rank": [0, 1, 2]}
```

`rank` is sorted by relation degree in descending order; `relation_degrees[0]` corresponds to the most related sequence.

### 9.2 GM(1,1) Grey Prediction

First-order single-variable grey model, suitable for short-term, data-scarce prediction:

```python
result = client.compute._submit_sync("gm11_predict", data=sequence, n_ahead=3)
# {"predicted": [10.2, 10.8, 11.5], "mape": 2.1}
```

`mape` is the Mean Absolute Percentage Error, measuring fit accuracy.

### 9.3 Grey Clustering

```python
result = client.compute._submit_sync("grey_cluster",
    data={"samples": samples, "indicators": indicators},
    n_clusters=3)
# {"labels": [...], "whitening_weights": [...]}
```

---

## 10. Machine Learning

7 ML handlers (Tier 6), wrapping scikit-learn-style training and prediction. Requires `pip install -e packages/compute[ml]`.

### 10.1 Train + Predict

Training returns a `model_ref` (cloudpickle-encoded model reference); pass `model_ref` when predicting:

```python
# Train
result = client.compute._submit_sync("ml_train",
    data={"X": X_train, "y": y_train},
    model_type="random_forest")
model_ref = result["model_ref"]  # "cloudpickle:base64..."

# Predict
predictions = client.compute._submit_sync("ml_predict",
    data=X_test, model_ref=model_ref)
```

Supported `model_type`: `random_forest` / `gradient_boosting` / `logistic` / `svm` / `xgboost` (requires xgboost installed).

### 10.2 Feature Importance

```python
result = client.compute._submit_sync("feature_importance",
    data={"X": X, "y": y}, model_ref=model_ref)
# {"importances": [0.3, 0.1, 0.25, ...], "feature_names": [...]}
```

### 10.3 Clustering

Unsupervised clustering; returns labels, centroids, and silhouette score:

```python
result = client.compute._submit_sync("clustering",
    data=X, method="kmeans", n_clusters=3)
# {"labels": [...], "centroids": [...], "silhouette": 0.65}
```

Supports `kmeans` / `dbscan` / `hierarchical`. `silhouette` is the silhouette coefficient (-1–1; higher is better).

![K-Means clustering](../docs/images/ml_clustering.png)

### 10.4 Dimensionality Reduction

```python
result = client.compute._submit_sync("dimension_reduction",
    data=X, method="pca", n_components=2)
# {"transformed": [...], "explained_variance": [0.7, 0.15]}
```

Supports `pca` (Principal Component Analysis) and `tsne` (t-SNE nonlinear reduction). `explained_variance` is the variance explained by each component.

![PCA reduction](../docs/images/ml_pca.png)

### 10.5 Walk-Forward Cross-Validation

Time-series cross-validation, avoiding future-information leakage:

```python
result = client.compute._submit_sync("walkforward_cv",
    data={"X": X, "y": y}, n_folds=5)
# {"fold_scores": [0.72, 0.68, 0.75, 0.70, 0.73], "mean": 0.716, "std": 0.024}
```

### 10.6 Classification Metrics

```python
result = client.compute._submit_sync("classification_metrics",
    data={"y_true": y_true, "y_pred": y_pred})
# {"accuracy": 0.85, "precision": 0.82, "recall": 0.78, "f1": 0.80,
#  "confusion_matrix": [[40, 5], [10, 45]]}
```

---

## 11. Portfolio Risk Management

2 portfolio risk handlers (Tier 7).

### 11.1 Risk Metrics

Computes risk metrics for a return series:

```python
result = client.compute._submit_sync("risk_metrics",
    data=returns, confidence=0.95)
# {"var": -0.03, "cvar": -0.045, "max_drawdown": -0.28,
#  "sharpe": 1.2, "sortino": 1.5, "calmar": 0.8}
```

- `VaR` (Value at Risk): max daily loss at 95% confidence.
- `CVaR` (Conditional VaR): average loss beyond VaR.
- `max_drawdown`: maximum drawdown.
- `sharpe` / `sortino` / `calmar`: risk-adjusted return metrics.

### 11.2 Regime Detection

Identifies different market regimes (e.g., bull/bear/ranging) in a price series:

```python
result = client.compute._submit_sync("regime_detection",
    data=prices, method="change_point", n_regimes=2)
# {"labels": [...], "regime_stats": {0: {"mean": 0.002, "vol": 0.01},
#                                    1: {"mean": -0.001, "vol": 0.02}}}
```

Supports `change_point` (change-point detection) and `hmm` (Hidden Markov Model).

---

## 12. DSL Strategy Expressions

The DSL engine lets you invoke common strategies with concise expression strings, avoiding boilerplate strategy-function code:

```python
# Buy and hold
result = client.run_dsl("buy_and_hold()", data=data)

# MA crossover (with parameters)
result = client.run_dsl("ma_cross(short=5, long=20)", data=data)
```

The DSL parser supports `func_name(arg1, arg2, key=value)` form; parameters can be numbers, strings, identifiers, and nested calls. `buy_and_hold` and `ma_cross` are built-in strategies; unknown function names are tried as indicator calls:

```python
# Compute RSI indicator
rsi = client.run_dsl("rsi(window=14)", data=data)
```

---

## 13. Visualization

V3.1 provides both declarative charts and convenience plotting functions.

### 13.1 Declarative Charts (ChartSpec + MatplotlibRenderer)

```python
from stockstat import ChartSpec, MatplotlibRenderer

# Build chart spec
spec = ChartSpec(
    title="BTC Price",
    chart_type="line",
    data=data[["close"]],
)

# Render to PNG bytes
png_bytes = MatplotlibRenderer().render(spec)

# Save to file
with open("chart.png", "wb") as f:
    f.write(png_bytes)
```

Without matplotlib installed, `NullRenderer` provides a no-op implementation that doesn't error but produces no image.

### 13.2 Backtest Charts

```python
from stockstat.plot import plot_equity_curve, plot_drawdown

# Equity curve
equity_png = plot_equity_curve(result.equity_curve)

# Drawdown chart
drawdown_png = plot_drawdown(result.equity_curve)
```

---

## 14. Result Export

`ResultSerializer` supports multiple export formats, suitable for writing to files or integrating with other systems:

```python
from stockstat import ResultSerializer

# JSON (for web interaction)
json_str = ResultSerializer.to_json(result.metrics.to_dict())

# CSV (for tabular analysis)
csv_str = ResultSerializer.to_csv(df)

# Arrow (columnar binary, for large data)
arrow_bytes = ResultSerializer.to_arrow(df)

# Parquet (file-level columnar storage)
parquet_bytes = ResultSerializer.to_parquet(df)

# Save to file (auto-infers format from extension)
ResultSerializer.save(df, "output.csv", format="csv")
ResultSerializer.save(df, "output.arrow", format="arrow")
ResultSerializer.save(df, "output.parquet", format="parquet")
```

---

## 15. CLI

V3.1 provides three CLI groups, corresponding to the user entry, storage, and compute modules.

### 15.1 stockstat (User Entry)

```bash
# Data management
stockstat data fetch BTC/USDT --timeframe 1d [--start 2024-01-01] [--limit 20]
stockstat data list
stockstat data ingest --symbol BTC/USDT --source binance

# Compute indicators
stockstat compute indicator ma --symbol BTC/USDT --window 20
stockstat compute list-handlers    # list 38 task_types

# Task management
stockstat task status <task_id>

# Cluster
stockstat cluster info

# Config
stockstat config       # show current config
stockstat version      # show version

# Service (convenience entry, equivalent to stockstat-backend serve)
stockstat serve --host 0.0.0.0 --port 8000
```

### 15.2 stockstat-backend (Storage)

```bash
stockstat-backend serve --host 0.0.0.0 --port 8000 [--database-url ...] [--admin]
stockstat-backend init-db [--database-url ...]
stockstat-backend ingest --symbol BTC/USDT --source binance [--timeframe 1d]
stockstat-backend list-symbols [--database-url ...]
```

### 15.3 stockstat-dispatcher (Dispatch)

```bash
stockstat-dispatcher serve \
    --storage-url http://localhost:8000 \
    --listen 0.0.0.0:9000 \
    [--queue-backend memory|redis] \
    [--redis-url redis://localhost:6379] \
    [--alias dispatch-primary]

stockstat-dispatcher cluster --dispatcher-url http://localhost:9000
```

### 15.4 stockstat-compute (Compute)

```bash
# Start Worker
stockstat-compute worker \
    --dispatcher-url http://localhost:9000 \
    --concurrency 8 \
    --alias compute-node-1 \
    --label gpu=true \
    --capabilities backtest,grid_search \
    --preemptable

# List all handlers
stockstat-compute list-handlers

# Show hardware info
stockstat-compute hardware
```

`--label key=value` can be specified multiple times for Worker label filtering. `--capabilities` is comma-separated, limiting the task_types the Worker supports (if not specified, supports all 38).

---

## 16. Distributed Computing

### 16.1 Three ComputeBackends

| Backend | Class | Scenario | Behavior |
|---------|-------|----------|----------|
| Local | `LocalComputeBackend` | Single-machine (Scenario A/B/C) | Background thread; `wait()` blocks |
| Remote | `RemoteComputeBackend` | Distributed (Scenario D/E/F) | HTTP submit to Dispatcher; `TaskRef.wait()` polls |
| Auto | `AutoComputeBackend` | Hybrid | Heavy → remote, light → local; falls back to local when remote unreachable |

Switching backends only requires changing Client constructor parameters; calling code is identical.

### 16.2 Explicit Async Submission

```python
from stockstat_foundation import ComputeSpec, DataSpec, DispatchSpec

task = client.compute.remote("grid_search", data=data,
    compute_spec=ComputeSpec(
        task_type="grid_search",
        param_grid={"short": [3, 5, 8], "long": [10, 20, 30]},
        metric="sharpe",
    ))
print(task.id, task.status)  # UUID + "pending"

# Poll status
info = task.info
print(info.progress)  # 0.0 ~ 1.0

# Block for result
result = task.wait(timeout=3600)
```

`remote()` returns a `TaskRef` with methods `id` / `status` / `info` / `ready()` / `wait()` / `result()` / `cancel()` / `stream_results()`.

### 16.3 Transparent Local/Remote Switching

The same API works identically in single-machine and distributed modes:

```python
# Local
client_local = StockStatClient()
result_local = client_local.backtest(data, strategy)

# Remote (same API, only constructor changes)
from stockstat_compute.backend.remote import RemoteComputeBackend
client_remote = StockStatClient(
    compute_backend=RemoteComputeBackend("http://dispatcher:9000"),
)
result_remote = client_remote.backtest(data, strategy)

# Results match (precision 1e-10)
```

### 16.4 AutoComputeBackend Routing Rules

```python
from stockstat_compute.backend.auto import AutoComputeBackend
from stockstat_compute import LocalComputeBackend
from stockstat_compute.backend.remote import RemoteComputeBackend

auto = AutoComputeBackend(
    local=LocalComputeBackend(client=client, data_client=data_client),
    remote=RemoteComputeBackend(dispatcher_url="http://dispatcher:9000"),
)

client = StockStatClient(compute_backend=auto)
# grid_search → remote (HEAVY_TYPES)
# indicator(ma) → local (light)
```

`HEAVY_TYPES` = `{grid_search, batch_backtest, monte_carlo, bootstrap, permutation_test, walkforward, walkforward_cv, ml_train, deep_learning}`. Additionally, inline data exceeding `local_threshold_mb` (default 1MB) also goes remote.

---

## 17. Deployment Scenarios

### Scenario A: Single-Machine Full-Stack

The simplest deployment — all computation in-process, no services needed:

```python
client = StockStatClient()  # default LocalComputeBackend
result = client.backtest(data, strategy)
```

### Scenario B: Storage Split

Storage deployed standalone; Client computes locally. Suitable for shared team data:

```bash
# Storage service
stockstat-backend serve --host 0.0.0.0 --port 8000
```

```python
client = StockStatClient(storage_url="http://storage-host:8000")
data = client.ohlcv("BTC/USDT", "1d")
result = client.backtest(data, strategy)  # local compute
```

### Scenario C: Offline

No-network environment; data ingested locally; local compute:

```bash
stockstat-backend ingest --symbol BTC/USDT --source synthetic
```

```python
client = StockStatClient(storage_url="http://localhost:8000")
```

### Scenario D: Dispatcher + Worker

Storage and Dispatcher co-located; Workers remote. Suitable for small clusters:

```bash
# Terminal 1: Storage + Dispatcher
stockstat-backend serve --port 8000
stockstat-dispatcher serve --storage-url http://localhost:8000 --listen 0.0.0.0:9000

# Terminal 2: Worker
stockstat-compute worker --dispatcher-url http://localhost:9000 --concurrency 8
```

### Scenario E: Standalone Dispatcher Cluster

Storage, Dispatcher, and Worker each independently deployed. Suitable for production clusters:

```bash
# Storage
stockstat-backend serve --port 8000

# Dispatcher (standalone)
stockstat-dispatcher serve --listen 0.0.0.0:9000

# Worker ×N (can deploy to multiple machines)
stockstat-compute worker --dispatcher-url http://dispatcher:9000 --concurrency 8
```

### Scenario F: Multi-Level Dispatcher

Parent Dispatcher + child Dispatchers, forming a tree-shaped scheduling topology. Suitable for large-scale clusters:

```bash
# Parent Dispatcher
stockstat-dispatcher serve --listen 0.0.0.0:9000 --alias dispatch-primary

# Child Dispatcher (registers with parent)
stockstat-dispatcher serve --listen 0.0.0.0:9001 \
    --alias dispatch-child-1 --parent-url http://primary:9000

# Worker (connects to child Dispatcher)
stockstat-compute worker --dispatcher-url http://child-1:9001
```

---

## 18. PostgreSQL Configuration

PostgreSQL is recommended for production. V3.1 abstracts the database via SQLAlchemy ORM; switching only requires changing the connection URL:

```bash
# Environment variable
export STOCKSTAT_DATABASE_URL=postgresql://stockstat:stockstat123@192.168.0.114:5432/stockstat

# Start
stockstat-backend serve --host 0.0.0.0 --port 8000
```

Verify the connection:

```python
from stockstat_backend import OrmSession, StorageBackendImpl, create_engine_from_url

engine = create_engine_from_url("postgresql://stockstat:stockstat123@192.168.0.114:5432/stockstat")
orm = OrmSession(engine)
orm.create_all()  # create tables (first time)
backend = StorageBackendImpl(orm)

# Write
backend.ingest_ohlcv("BTC/USDT", "1d", df)

# Query
result = backend.fetch_ohlcv(["BTC/USDT"], "1d")
```

Requires the PostgreSQL driver: `pip install -e packages/storage[postgres]`.

---

## 19. REST API Reference

### 19.1 Storage REST API

| Endpoint | Method | Parameters | Description |
|----------|--------|------------|-------------|
| `/api/v1/ohlcv` | GET | `symbol` (comma-separated multi-symbol) / `timeframe` / `start` / `end` / `source` / `format` (arrow/json) | Query OHLCV; returns Arrow IPC binary by default |
| `/api/v1/ohlcv` | POST | Header: `X-Symbol` / `X-Timeframe`; Body: Arrow IPC or JSON | Write OHLCV |
| `/api/v1/ohlcv/stats` | GET | — | OHLCV data statistics |
| `/api/v1/symbols` | GET | — | Symbol list |
| `/api/v1/ingest` | POST | `symbol` / `timeframe` / `source` | Ingest from data source |
| `/health` | GET | — | Health check |

Example (curl):

```bash
# Query OHLCV (JSON format)
curl "http://localhost:8000/api/v1/ohlcv?symbol=BTC/USDT&timeframe=1d&format=json"

# Write OHLCV (JSON)
curl -X POST http://localhost:8000/api/v1/ohlcv \
    -H "Content-Type: application/json" \
    -H "X-Symbol: BTC/USDT" \
    -H "X-Timeframe: 1d" \
    -d '[{"timestamp":"2024-01-01","open":42000,"high":42500,"low":41800,"close":42300,"volume":1500}]'
```

### 19.2 Dispatcher REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/dispatch/submit` | POST | Submit task (Body: TaskSpec JSON) |
| `/dispatch/status/{task_id}` | GET | Query task status |
| `/dispatch/result/{task_id}` | GET | Get result (base64 cloudpickle) |
| `/dispatch/cancel/{task_id}` | POST | Cancel task |
| `/dispatch/cluster` | GET | Cluster topology (`?include_offline=true&include_hardware=true`) |
| `/dispatch/autoscaler` | GET | Autoscaler metrics |
| `/dispatch/tasks/history` | GET | Task history (`?limit=100&state=completed`) |
| `/dispatch/register` | POST | Worker registration |
| `/dispatch/heartbeat` | POST | Worker heartbeat |
| `/dispatch/unregister/{worker_id}` | POST | Worker deregistration |
| `/dispatch/assign` | POST | Worker pulls task |
| `/dispatch/complete` | POST | Worker returns result |
| `/dispatch/fail` | POST | Worker returns failure |
| `/dispatch/partial` | POST | Worker streaming partial result |

Example (Python httpx):

```python
import httpx, json
from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec, DispatchSpec

# Submit task
spec = TaskSpec(
    task_id="task-001",
    data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
    compute_spec=ComputeSpec(task_type="backtest", initial_cash=10000),
    dispatch_spec=DispatchSpec(timeout=3600),
)
resp = httpx.post("http://localhost:9000/dispatch/submit",
                   json=spec.to_dict())
print(resp.json())  # {"task_id": "task-001", "status": "pending", "n_slices": 1}

# Query status
resp = httpx.get("http://localhost:9000/dispatch/status/task-001")
print(resp.json())  # {"state": "completed", "progress": 1.0, ...}

# Get result
import base64
from stockstat_foundation import CloudpickleCodec
resp = httpx.get("http://localhost:9000/dispatch/result/task-001")
result_bytes = base64.b64decode(resp.json()["result"])
result = CloudpickleCodec().decode(result_bytes)
```

---

## 20. Environment Variables

V3.1 manages configuration centrally via the `Config` class, with 18 environment variables. All variables are prefixed with `STOCKSTAT_`; use `stockstat config` to view current values:

| Variable | Default | Description |
|----------|---------|-------------|
| `STOCKSTAT_CLIENT_MODE` | `online` | Client mode |
| `STOCKSTAT_DEFAULT_BACKEND` | `local` | Default compute backend (local/remote/auto) |
| `STOCKSTAT_STORAGE_URL` | — | Storage service URL |
| `STOCKSTAT_DATABASE_URL` | `sqlite:///stockstat.db` | Database connection URL |
| `STOCKSTAT_DISPATCHER_URL` | — | Dispatcher service URL |
| `STOCKSTAT_DISPATCHER_ENABLED` | `false` | Enable Dispatcher |
| `STOCKSTAT_DISPATCHER_QUEUE` | `memory` | Queue backend (memory/redis) |
| `STOCKSTAT_DISPATCHER_CACHE_DIR` | — | Dispatcher data cache directory |
| `STOCKSTAT_DISPATCHER_CACHE_SIZE_MB` | `512` | Dispatcher cache size limit (MB) |
| `STOCKSTAT_REDIS_URL` | — | Redis connection URL |
| `STOCKSTAT_ADMIN_ENABLED` | `false` | Enable Admin panel |
| `STOCKSTAT_SCHEDULER_ENABLED` | `false` | Enable scheduled collection |
| `STOCKSTAT_WORKER_CONCURRENCY` | CPU cores | Worker concurrency |
| `STOCKSTAT_WORKER_ALIAS` | hostname-pid | Worker alias |
| `STOCKSTAT_WORKER_PREEMPTABLE` | `false` | Worker supports preemption |
| `STOCKSTAT_TRANSPORT_TIMEOUT` | `30` | Transport timeout (seconds) |
| `STOCKSTAT_PROTOCOL_VERSION` | `1.0` | Protocol version |
| `STOCKSTAT_DEFAULT_ENCODING` | `json` | Default encoding (json/msgpack) |

Can also be loaded from JSON / TOML config files: `Config.from_file("config.json")`.

---

*V3.1 Usage Guide — based on code implementation. In case of discrepancy, the source code prevails.*
