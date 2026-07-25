"""生成所有演示图表的主脚本。

运行：python tests/generate_all_plots.py
输出：docs/images/*.png
"""
from __future__ import annotations

import os
import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["foundation", "storage", "compute", "invocation", "dispatcher"]:
    sys.path.insert(0, os.path.join(_ROOT, "packages", pkg))

IMG_DIR = os.path.join(_ROOT, "docs", "images")
os.makedirs(IMG_DIR, exist_ok=True)


def make_ohlcv(n=500, seed=42, start_price=100):
    """生成合成 OHLCV 数据。"""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0008, 0.02, n)
    close = start_price * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    open_ = close * (1 + rng.normal(0, 0.003, n))
    volume = rng.integers(10000, 500000, n).astype(float)
    ts = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "timestamp": ts, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


def plot_indicators():
    """图1：收盘价 + MA + 布林带。"""
    from stockstat_compute.indicators import ma, ema, bollinger
    df = make_ohlcv(300)
    close = df["close"]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(df["timestamp"], close, label="Close", color="black", linewidth=0.8)
    ax.plot(df["timestamp"], ma(close, 20), label="MA20", color="blue")
    ax.plot(df["timestamp"], ema(close, 12), label="EMA12", color="orange")
    bb = bollinger(close, 20, 2.0)
    ax.fill_between(df["timestamp"], bb["upper"], bb["lower"], alpha=0.15, color="green", label="Bollinger Band")
    ax.plot(df["timestamp"], bb["upper"], color="green", linewidth=0.5, linestyle="--")
    ax.plot(df["timestamp"], bb["lower"], color="green", linewidth=0.5, linestyle="--")
    ax.set_title("Close Price + MA + Bollinger Bands", fontsize=13)
    ax.set_xlabel("Date")
    ax.set_ylabel("Price")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "indicators_bollinger.png"), dpi=120)
    plt.close(fig)
    print("  [OK] indicators_bollinger.png")


def plot_rsi():
    """图2：RSI 超买超卖。"""
    from stockstat_compute.indicators import rsi
    df = make_ohlcv(300)
    r = rsi(df["close"], 14)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6), gridspec_kw={"height_ratios": [2, 1]}, sharex=True)
    ax1.plot(df["timestamp"], df["close"], color="black", linewidth=0.8)
    ax1.set_title("Close Price", fontsize=13)
    ax1.set_ylabel("Price")
    ax1.grid(True, alpha=0.3)
    ax2.plot(df["timestamp"], r, color="purple", linewidth=1)
    ax2.axhline(70, color="red", linestyle="--", linewidth=0.8, label="Overbought (70)")
    ax2.axhline(30, color="green", linestyle="--", linewidth=0.8, label="Oversold (30)")
    ax2.fill_between(df["timestamp"], 70, 100, alpha=0.1, color="red")
    ax2.fill_between(df["timestamp"], 0, 30, alpha=0.1, color="green")
    ax2.set_title("RSI(14)", fontsize=13)
    ax2.set_ylabel("RSI")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left")
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "indicators_rsi.png"), dpi=120)
    plt.close(fig)
    print("  [OK] indicators_rsi.png")


def plot_macd():
    """图3：MACD。"""
    from stockstat_compute.indicators import macd
    df = make_ohlcv(300)
    m = macd(df["close"], 12, 26, 9)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6), gridspec_kw={"height_ratios": [2, 1]}, sharex=True)
    ax1.plot(df["timestamp"], df["close"], color="black", linewidth=0.8)
    ax1.set_title("Close Price", fontsize=13)
    ax1.set_ylabel("Price")
    ax1.grid(True, alpha=0.3)
    colors = ["red" if h > 0 else "green" for h in m["histogram"]]
    ax2.bar(df["timestamp"], m["histogram"], color=colors, width=1, alpha=0.6)
    ax2.plot(df["timestamp"], m["macd"], label="MACD", color="blue", linewidth=1)
    ax2.plot(df["timestamp"], m["signal"], label="Signal", color="orange", linewidth=1)
    ax2.set_title("MACD(12,26,9)", fontsize=13)
    ax2.set_ylabel("MACD")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left")
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "indicators_macd.png"), dpi=120)
    plt.close(fig)
    print("  [OK] indicators_macd.png")


def plot_backtest_equity():
    """图4：回测资金曲线 + 回撤。"""
    from stockstat_compute import BacktestEngine, Signal
    df = make_ohlcv(500)

    def ma_cross(i, bar, data, ctx):
        if i < 25:
            return None
        s = data["close"].iloc[i-5:i+1].mean()
        l = data["close"].iloc[i-20:i+1].mean()
        ps = data["close"].iloc[i-6:i].mean()
        pl = data["close"].iloc[i-21:i].mean()
        if ps <= pl and s > l:
            return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy", strength=0.9)
        if ps >= pl and s < l:
            return Signal(timestamp=bar["timestamp"], symbol="TEST", side="sell", strength=0.9)
        return None

    engine = BacktestEngine(
        data=df, strategy=ma_cross, initial_cash=10000,
        cost_model="F1_SpotNoBNB", symbol="TEST", timeframe="1d",
        strategy_name="ma_cross_5_20",
    )
    result = engine.run()
    eq = result.equity_curve

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    ax1.plot(eq.index, eq["equity"], color="blue", linewidth=1.2, label="Equity")
    ax1.axhline(10000, color="gray", linestyle="--", linewidth=0.8, label="Initial Cash")
    ax1.set_title("Backtest Equity Curve (MA Cross 5/20)", fontsize=13)
    ax1.set_ylabel("Equity ($)")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)

    ax2.fill_between(eq.index, eq["drawdown"] * 100, 0, color="red", alpha=0.4)
    ax2.set_title("Drawdown", fontsize=13)
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("Date")
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "backtest_equity_drawdown.png"), dpi=120)
    plt.close(fig)
    print("  [OK] backtest_equity_drawdown.png")
    return result


def plot_correlation_scatter():
    """图5：相关性散点图。"""
    from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec
    from stockstat_compute.handlers import dispatch
    rng = np.random.default_rng(42)
    n = 300
    x = rng.normal(0, 1, n)
    y = 0.6 * x + rng.normal(0, 0.8, n)
    spec = TaskSpec(
        task_id="corr-demo", data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type="correlation",
                                 params={"x": x.tolist(), "y": y.tolist(), "method": "pearson"}),
    )
    result = dispatch(spec, {"x": x, "y": y})
    r = result["r"]
    p = result["p_value"]
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(x, y, alpha=0.5, s=20, color="steelblue")
    z = np.polyfit(x, y, 1)
    xs = np.linspace(x.min(), x.max(), 100)
    ax.plot(xs, np.polyval(z, xs), color="red", linewidth=2,
            label="r={:.3f} (p={:.4f})".format(r, p))
    ax.set_title("Correlation Analysis (Pearson)", fontsize=13)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "stats_correlation.png"), dpi=120)
    plt.close(fig)
    print("  [OK] stats_correlation.png")


def plot_spectral():
    """图6：频谱分析。"""
    from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec
    from stockstat_compute.handlers import dispatch
    fs = 100
    t = np.arange(500) / fs
    signal = np.sin(2 * np.pi * 10 * t) + 0.5 * np.sin(2 * np.pi * 25 * t) + np.random.default_rng(42).normal(0, 0.3, 500)
    spec = TaskSpec(
        task_id="spec-demo", data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type="spectral_analysis",
                                 params={"method": "welch", "nperseg": 128}),
    )
    result = dispatch(spec, signal)
    freqs = result["frequencies"]
    psd = result["psd"]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.semilogy(freqs, psd, color="darkgreen", linewidth=1)
    ax.set_title("Spectral Analysis (Welch PSD) — 10Hz + 25Hz", fontsize=13)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Power Spectral Density")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "signal_spectral.png"), dpi=120)
    plt.close(fig)
    print("  [OK] signal_spectral.png")


def plot_wavelet():
    """图7：小波时频热力图。"""
    from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec
    from stockstat_compute.handlers import dispatch
    t = np.arange(500) / 100
    signal = np.sin(2 * np.pi * 10 * t)
    signal[250:] = np.sin(2 * np.pi * 25 * t[250:])
    scales = list(range(1, 40))
    spec = TaskSpec(
        task_id="wavelet-demo", data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type="wavelet",
                                 params={"method": "cwt", "scales": scales}),
    )
    result = dispatch(spec, signal)
    power = np.array(result["power"])
    fig, ax = plt.subplots(figsize=(12, 5))
    im = ax.imshow(power, aspect="auto", cmap="viridis",
                   extent=[0, len(signal), scales[-1], scales[0]])
    ax.set_title("Wavelet CWT Scalogram — Frequency Change at t=250", fontsize=13)
    ax.set_xlabel("Time")
    ax.set_ylabel("Scale")
    fig.colorbar(im, ax=ax, label="Power")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "signal_wavelet.png"), dpi=120)
    plt.close(fig)
    print("  [OK] signal_wavelet.png")


def plot_hurst():
    """图8：Hurst DFA 拟合。"""
    from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec
    from stockstat_compute.handlers import dispatch
    rng = np.random.default_rng(42)
    x = np.cumsum(rng.normal(0, 1, 5000))
    spec = TaskSpec(
        task_id="hurst-demo", data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type="hurst_exponent", params={"method": "dfa"}),
    )
    result = dispatch(spec, x)
    log_n = result["log_n"]
    log_f = result["log_F"]
    hurst = result["hurst"]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(log_n, log_f, color="steelblue", s=30, zorder=3)
    coeffs = np.polyfit(log_n, log_f, 1)
    xs = np.linspace(log_n[0], log_n[-1], 50)
    ax.plot(xs, np.polyval(coeffs, xs), color="red", linewidth=2,
            label="Hurst = {:.3f} (R²={:.3f})".format(hurst, result["fit_r2"]))
    ax.set_title("Hurst Exponent (DFA Method)", fontsize=13)
    ax.set_xlabel("log(n)")
    ax.set_ylabel("log(F(n))")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "nonlinear_hurst.png"), dpi=120)
    plt.close(fig)
    print("  [OK] nonlinear_hurst.png")


def plot_clustering():
    """图9：聚类分析。"""
    from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec
    from stockstat_compute.handlers import dispatch
    rng = np.random.default_rng(42)
    X = np.vstack([
        rng.normal(0, 1, (50, 2)),
        rng.normal(5, 1, (50, 2)),
        rng.normal(-3, 1, (50, 2)),
    ])
    spec = TaskSpec(
        task_id="cluster-demo", data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type="clustering",
                                 params={"method": "kmeans", "n_clusters": 3}),
    )
    result = dispatch(spec, X)
    labels = np.array(result["labels"])
    fig, ax = plt.subplots(figsize=(7, 6))
    colors = ["#e41a1c", "#377eb8", "#4daf4a"]
    for k in range(3):
        mask = labels == k
        ax.scatter(X[mask, 0], X[mask, 1], c=colors[k], s=25, alpha=0.7, label="Cluster {}".format(k))
    ax.set_title("K-Means Clustering (k=3, silhouette={:.3f})".format(result.get("silhouette", 0)), fontsize=13)
    ax.set_xlabel("Feature 1")
    ax.set_ylabel("Feature 2")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "ml_clustering.png"), dpi=120)
    plt.close(fig)
    print("  [OK] ml_clustering.png")


def plot_pca():
    """图10：PCA 降维。"""
    from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec
    from stockstat_compute.handlers import dispatch
    rng = np.random.default_rng(42)
    X = rng.normal(0, 1, (200, 5))
    X[:, 0] = X[:, 0] * 3 + 2  # 第一主成分方向
    spec = TaskSpec(
        task_id="pca-demo", data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type="dimension_reduction",
                                 params={"method": "pca", "n_components": 2}),
    )
    result = dispatch(spec, X)
    transformed = np.array(result["transformed"])
    ev = result["explained_variance"]
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(transformed[:, 0], transformed[:, 1], c="steelblue", s=20, alpha=0.6)
    ax.set_title("PCA 2D Projection (PC1={:.1%}, PC2={:.1%})".format(ev[0], ev[1]), fontsize=13)
    ax.set_xlabel("Principal Component 1")
    ax.set_ylabel("Principal Component 2")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "ml_pca.png"), dpi=120)
    plt.close(fig)
    print("  [OK] ml_pca.png")


def plot_batch_backtest():
    """图11：批量回测 Sharpe 对比。"""
    from stockstat import StockStatClient
    df = make_ohlcv(200)

    def strat_buy(i, bar, data, ctx):
        if i == 0:
            from stockstat_compute import Signal
            return Signal(timestamp=bar["timestamp"], symbol="T", side="buy")
        return None

    def strat_sell(i, bar, data, ctx):
        if i == 0:
            from stockstat_compute import Signal
            return Signal(timestamp=bar["timestamp"], symbol="T", side="sell")
        return None

    def strat_hold(i, bar, data, ctx):
        return None

    client = StockStatClient()
    result = client.batch_backtest(
        df,
        strategies={"buy_hold": strat_buy, "sell_first": strat_sell, "do_nothing": strat_hold},
        fee_models=["F1_SpotNoBNB", "F2_SpotBNB", "F3_FutNoBNB", "F4_FutBNB"],
        initial_cash=10000,
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    pivot = result.pivot(index="strategy", columns="fee_model", values="sharpe")
    pivot.plot(kind="bar", ax=ax, width=0.7)
    ax.set_title("Batch Backtest: 3 Strategies x 4 Fee Models (Sharpe)", fontsize=13)
    ax.set_xlabel("Strategy")
    ax.set_ylabel("Sharpe Ratio")
    ax.legend(title="Fee Model", loc="upper right")
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "backtest_batch_sharpe.png"), dpi=120)
    plt.close(fig)
    print("  [OK] backtest_batch_sharpe.png")


def plot_rqa():
    """图12：递归图。"""
    from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec
    from stockstat_compute.handlers import dispatch
    t = np.linspace(0, 20, 200)
    signal = np.sin(t) + 0.3 * np.sin(3 * t)
    spec = TaskSpec(
        task_id="rqa-demo", data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type="recurrence_plot",
                                 params={"m": 3, "tau": 2}),
    )
    result = dispatch(spec, signal)
    R = np.array(result["recurrence_plot"])
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.imshow(R, cmap="binary", origin="lower")
    ax.set_title("Recurrence Plot (m=3, tau=2)", fontsize=13)
    ax.set_xlabel("Time")
    ax.set_ylabel("Time")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "nonlinear_recurrence.png"), dpi=120)
    plt.close(fig)
    print("  [OK] nonlinear_recurrence.png")


def main():
    print("=" * 50)
    print("Generating demo plots...")
    print("=" * 50)
    plot_indicators()
    plot_rsi()
    plot_macd()
    plot_backtest_equity()
    plot_correlation_scatter()
    plot_spectral()
    plot_wavelet()
    plot_hurst()
    plot_clustering()
    plot_pca()
    plot_batch_backtest()
    plot_rqa()
    print("=" * 50)
    print("All plots generated in docs/images/")
    print("Total: {} files".format(len(os.listdir(IMG_DIR))))


if __name__ == "__main__":
    main()
