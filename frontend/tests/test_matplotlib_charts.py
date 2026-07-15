"""
Matplotlib visualization tests — classic statistical charts + PAXG weekend scatter.
Generates fixed-output PNGs to docs/images/ for README embedding.
Requires proxy enabled at http://127.0.0.1:8889 for real data.
"""
import os
import sys

import pytest
import pandas as pd
import numpy as np
from scipy import stats as sp_stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

os.environ["STOCKSTAT_PROXY_ENABLED"] = "true"
os.environ["STOCKSTAT_PROXY_TYPE"] = "http"
os.environ["STOCKSTAT_PROXY_URL"] = "http://127.0.0.1:8889"
os.environ["DATABASE_URL"] = "sqlite:///test_matplotlib.db"

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from fastapi.testclient import TestClient
from stockstat_backend.app import create_app
from stockstat_backend.storage.database import reset_engine, get_engine
from stockstat_backend.models.ohlcv import Base
from stockstat_backend.config import settings
from stockstat import StockStatClient

IMAGES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "images")
os.makedirs(IMAGES_DIR, exist_ok=True)


@pytest.fixture(scope="module")
def test_http_client():
    settings.reload()
    reset_engine()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app = create_app()
    with TestClient(app) as c:
        symbols = [
            ("AAPL", "yfinance", "2023-01-01", "2024-12-31"),
            ("^GSPC", "yfinance", "2023-01-01", "2024-12-31"),
            ("BTC/USDT", "binance", "2023-01-01", "2024-12-31"),
            ("ETH/USDT", "binance", "2024-01-01", "2024-12-31"),
            ("PAXG/USDT", "binance", "2022-01-01", "2024-12-31"),
        ]
        for sym, source, start, end in symbols:
            c.post("/api/v1/ingest", params={
                "symbol": sym, "source": source,
                "start": start, "end": end, "timeframe": "1d",
            })
        yield c
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="module")
def stockstat_client(test_http_client):
    return StockStatClient(http_client=test_http_client)


def _savefig(fig, name):
    path = os.path.join(IMAGES_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


# ═══════════════════════════════════════════════════
# Classic Statistical Charts
# ═══════════════════════════════════════════════════

class TestClassicCharts:
    """Classic statistical visualization tests with real data."""

    def test_chart_close_with_ma_bollinger(self, stockstat_client):
        """Chart 1: Close price + MA20 + Bollinger Bands"""
        data = stockstat_client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
        upper, mid, lower = stockstat_client.compute.bollinger(data.close, 20, 2.0)
        ma20 = stockstat_client.compute.ma(data.close, 20)

        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(data.index, data.close, label="Close", color="black", linewidth=1)
        ax.plot(data.index, ma20, label="MA20", color="blue", linewidth=1)
        ax.fill_between(data.index, lower, upper, alpha=0.15, label="Bollinger Band", color="blue")
        ax.plot(data.index, upper, color="blue", linewidth=0.5, linestyle="--")
        ax.plot(data.index, lower, color="blue", linewidth=0.5, linestyle="--")
        ax.set_title("BTC/USDT Close + MA20 + Bollinger Bands (2024)")
        ax.set_xlabel("Date")
        ax.set_ylabel("Price (USDT)")
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)
        path = _savefig(fig, "btc_bollinger.png")
        assert os.path.exists(path)

    def test_chart_rsi(self, stockstat_client):
        """Chart 2: RSI with overbought/oversold zones"""
        data = stockstat_client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
        rsi = stockstat_client.compute.rsi(data.close, 14)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [2, 1]})
        ax1.plot(data.index, data.close, color="black", linewidth=1)
        ax1.set_title("BTC/USDT Close Price (2024)")
        ax1.set_ylabel("Price (USDT)")
        ax1.grid(True, alpha=0.3)

        ax2.plot(rsi.index, rsi, color="purple", linewidth=1)
        ax2.axhline(70, color="red", linestyle="--", alpha=0.5, label="Overbought (70)")
        ax2.axhline(30, color="green", linestyle="--", alpha=0.5, label="Oversold (30)")
        ax2.fill_between(rsi.index, 70, 100, alpha=0.1, color="red")
        ax2.fill_between(rsi.index, 0, 30, alpha=0.1, color="green")
        ax2.set_title("RSI (14)")
        ax2.set_ylabel("RSI")
        ax2.set_ylim(0, 100)
        ax2.legend(loc="upper left")
        ax2.grid(True, alpha=0.3)

        fig.tight_layout()
        path = _savefig(fig, "btc_rsi.png")
        assert os.path.exists(path)

    def test_chart_macd(self, stockstat_client):
        """Chart 3: MACD histogram + signal line"""
        data = stockstat_client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")
        macd_line, signal_line, hist = stockstat_client.compute.macd(data.close)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [2, 1]})
        ax1.plot(data.index, data.close, color="black", linewidth=1)
        ax1.set_title("ETH/USDT Close Price (2024)")
        ax1.set_ylabel("Price (USDT)")
        ax1.grid(True, alpha=0.3)

        ax2.plot(macd_line.index, macd_line, label="MACD", color="blue", linewidth=1)
        ax2.plot(signal_line.index, signal_line, label="Signal", color="orange", linewidth=1)
        colors = ["red" if h >= 0 else "green" for h in hist]
        ax2.bar(hist.index, hist, color=colors, alpha=0.5, width=1)
        ax2.axhline(0, color="black", linewidth=0.5)
        ax2.set_title("MACD (12, 26, 9)")
        ax2.set_ylabel("MACD")
        ax2.legend(loc="upper left")
        ax2.grid(True, alpha=0.3)

        fig.tight_layout()
        path = _savefig(fig, "eth_macd.png")
        assert os.path.exists(path)

    def test_chart_drawdown(self, stockstat_client):
        """Chart 4: Drawdown chart for BTC"""
        data = stockstat_client.ohlcv("BTC/USDT", start="2023-01-01", timeframe="1d")
        cumret = data.close / data.close.iloc[0]
        running_max = cumret.cummax()
        drawdown = (cumret - running_max) / running_max * 100

        fig, ax = plt.subplots(figsize=(14, 5))
        ax.fill_between(drawdown.index, drawdown, 0, color="red", alpha=0.4)
        ax.plot(drawdown.index, drawdown, color="darkred", linewidth=1)
        ax.set_title("BTC/USDT Drawdown (2023-2024)")
        ax.set_xlabel("Date")
        ax.set_ylabel("Drawdown (%)")
        ax.grid(True, alpha=0.3)

        max_dd = drawdown.min()
        ax.annotate(f"Max DD: {max_dd:.1f}%",
                     xy=(drawdown.idxmin(), max_dd),
                     xytext=(drawdown.idxmin(), max_dd * 0.5),
                     arrowprops=dict(arrowstyle="->", color="black"),
                     fontsize=12, fontweight="bold")

        path = _savefig(fig, "btc_drawdown.png")
        assert os.path.exists(path)

    def test_chart_beta_scatter(self, stockstat_client):
        """Chart 5: Beta scatter — AAPL returns vs S&P 500 returns"""
        stock = stockstat_client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")
        market = stockstat_client.ohlcv("^GSPC", start="2023-01-01", timeframe="1d")

        stock_ret = stock.close.pct_change().dropna()
        market_ret = market.close.pct_change().dropna()

        aligned = pd.concat([stock_ret, market_ret], axis=1, keys=["stock", "market"]).dropna()

        beta = stockstat_client.compute.beta(stock_ret, market_ret, window=60)
        beta_mean = beta.dropna().mean()

        fig, ax = plt.subplots(figsize=(8, 8))
        ax.scatter(aligned["market"], aligned["stock"], alpha=0.3, s=10, color="steelblue")
        x = np.linspace(aligned["market"].min(), aligned["market"].max(), 100)
        coeffs = np.polyfit(aligned["market"], aligned["stock"], 1)
        ax.plot(x, coeffs[0] * x + coeffs[1], color="red", linewidth=2,
                label=f"Beta = {coeffs[0]:.3f}")
        ax.set_title("AAPL vs S&P 500 Daily Returns (2023-2024)")
        ax.set_xlabel("S&P 500 Daily Return")
        ax.set_ylabel("AAPL Daily Return")
        ax.legend(fontsize=12)
        ax.grid(True, alpha=0.3)

        path = _savefig(fig, "aapl_beta_scatter.png")
        assert os.path.exists(path)

    def test_chart_btc_eth_correlation(self, stockstat_client):
        """Chart 6: BTC vs ETH rolling correlation"""
        btc = stockstat_client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
        eth = stockstat_client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")

        btc_ret = btc.close.pct_change()
        eth_ret = eth.close.pct_change()

        aligned = pd.concat([btc_ret, eth_ret], axis=1, keys=["btc", "eth"]).dropna()
        rolling_corr = aligned["btc"].rolling(30).corr(aligned["eth"])

        fig, ax = plt.subplots(figsize=(14, 5))
        ax.plot(rolling_corr.index, rolling_corr, color="darkgreen", linewidth=1.5)
        ax.axhline(rolling_corr.mean(), color="red", linestyle="--", alpha=0.7,
                    label=f"Mean: {rolling_corr.mean():.3f}")
        ax.set_title("BTC vs ETH 30-day Rolling Correlation (2024)")
        ax.set_xlabel("Date")
        ax.set_ylabel("Correlation")
        ax.set_ylim(-1, 1)
        ax.legend()
        ax.grid(True, alpha=0.3)

        path = _savefig(fig, "btc_eth_corr.png")
        assert os.path.exists(path)

    def test_chart_price_comparison(self, stockstat_client):
        """Chart 7: Normalized price comparison BTC vs ETH vs PAXG"""
        btc = stockstat_client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
        eth = stockstat_client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")
        paxg = stockstat_client.ohlcv("PAXG/USDT", start="2024-01-01", timeframe="1d")

        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(btc.index, btc.close / btc.close.iloc[0] * 100, label="BTC/USDT", color="orange")
        ax.plot(eth.index, eth.close / eth.close.iloc[0] * 100, label="ETH/USDT", color="blue")
        ax.plot(paxg.index, paxg.close / paxg.close.iloc[0] * 100, label="PAXG/USDT", color="gold")
        ax.axhline(100, color="black", linewidth=0.5, alpha=0.5)
        ax.set_title("Normalized Price Comparison (Base=100, 2024)")
        ax.set_xlabel("Date")
        ax.set_ylabel("Normalized Price")
        ax.legend()
        ax.grid(True, alpha=0.3)

        path = _savefig(fig, "price_comparison.png")
        assert os.path.exists(path)


# ═══════════════════════════════════════════════════
# PAXG Weekend Return vs Monday Independent Gain/Loss (v2)
# ═══════════════════════════════════════════════════

class TestPAXGWeekendChart:
    """PAXG weekend return vs Monday max_gain AND max_loss (independently).

    Records both (High-Open)/Open and (Low-Open)/Open for every Monday,
    then correlates the weekend return with each independently.
    This avoids the selection bias of picking one extreme by signal direction.
    """

    @pytest.fixture(scope="class")
    def paxg_data(self, stockstat_client):
        return stockstat_client.ohlcv("PAXG/USDT", start="2022-01-01", timeframe="1d")

    @pytest.fixture(scope="class")
    def weekend_pairs(self, paxg_data):
        df = paxg_data.copy()
        df["weekday"] = df.index.weekday

        fridays = df[df["weekday"] == 4][["close"]].rename(columns={"close": "fri_close"})
        sundays = df[df["weekday"] == 6][["close"]].rename(columns={"close": "sun_close"})
        mondays = df[df["weekday"] == 0][["open", "high", "low", "close"]].copy()

        pairs = []
        for mon_date, mon_row in mondays.iterrows():
            prev_fri = fridays.loc[:mon_date].tail(1)
            prev_sun = sundays.loc[:mon_date].tail(1)
            if len(prev_fri) > 0 and len(prev_sun) > 0:
                fri_close = prev_fri["fri_close"].iloc[0]
                sun_close = prev_sun["sun_close"].iloc[0]
                weekend_return = (sun_close - fri_close) / fri_close

                mon_open = mon_row["open"]
                max_gain = (mon_row["high"] - mon_open) / mon_open
                max_loss = (mon_row["low"] - mon_open) / mon_open

                pairs.append({
                    "weekend_return": weekend_return,
                    "max_gain": max_gain,
                    "max_loss": max_loss,
                })

        return pd.DataFrame(pairs)

    def test_chart_gain_loss_scatter(self, weekend_pairs):
        """Chart 8: Weekend return (x) vs Monday gain & loss (y), both plotted independently"""
        df = weekend_pairs.dropna()
        r_gain = df["weekend_return"].corr(df["max_gain"])
        r_loss = df["weekend_return"].corr(df["max_loss"])
        p_gain = sp_stats.pearsonr(df["weekend_return"], df["max_gain"])[1]
        p_loss = sp_stats.pearsonr(df["weekend_return"], df["max_loss"])[1]

        fig, ax = plt.subplots(figsize=(12, 8))

        up = df["weekend_return"] > 0
        dn = df["weekend_return"] < 0

        ax.scatter(df.loc[up, "weekend_return"] * 100, df.loc[up, "max_gain"] * 100,
                   c="#e74c3c", alpha=0.4, s=20, label="Sig>0 → Gain (H-O)/O", edgecolors="white", linewidth=0.2)
        ax.scatter(df.loc[up, "weekend_return"] * 100, df.loc[up, "max_loss"] * 100,
                   c="#f39c12", alpha=0.4, s=20, label="Sig>0 → Loss (L-O)/O", edgecolors="white", linewidth=0.2, marker="^")
        ax.scatter(df.loc[dn, "weekend_return"] * 100, df.loc[dn, "max_gain"] * 100,
                   c="#2980b9", alpha=0.4, s=20, label="Sig<0 → Gain (H-O)/O", edgecolors="white", linewidth=0.2, marker="s")
        ax.scatter(df.loc[dn, "weekend_return"] * 100, df.loc[dn, "max_loss"] * 100,
                   c="#8e44ad", alpha=0.4, s=20, label="Sig<0 → Loss (L-O)/O", edgecolors="white", linewidth=0.2, marker="v")

        # Regression lines for gain and loss
        for y, color, ls in [(df["max_gain"] * 100, "red", "-"), (df["max_loss"] * 100, "blue", "--")]:
            valid = ~df["weekend_return"].isna() & ~y.isna()
            if valid.sum() > 2:
                coeffs = np.polyfit(df.loc[valid, "weekend_return"] * 100, y[valid], 1)
                x_line = np.linspace(df["weekend_return"].min() * 100, df["weekend_return"].max() * 100, 100)
                ax.plot(x_line, coeffs[0] * x_line + coeffs[1], color=color, linewidth=1.5, linestyle=ls, alpha=0.7)

        ax.axhline(0, color="gray", linewidth=0.8)
        ax.axvline(0, color="gray", linewidth=0.8)

        ax.set_title("PAXG Weekend Return vs Monday Gain/Loss (Independent, Real Data)",
                      fontsize=13, fontweight="bold")
        ax.set_xlabel("Weekend Return (%)  [Friday close → Sunday close]", fontsize=11)
        ax.set_ylabel("Monday Move (%)", fontsize=11)

        textstr = (f"Samples: {len(df)}\n"
                    f"r(gain) = {r_gain:.4f}, p = {p_gain:.4f}\n"
                    f"r(loss) = {r_loss:.4f}, p = {p_loss:.4f}")
        props = dict(boxstyle="round", facecolor="wheat", alpha=0.8)
        ax.text(0.05, 0.95, textstr, transform=ax.transAxes, fontsize=10,
                verticalalignment="top", bbox=props)

        ax.legend(loc="lower right", fontsize=9)
        ax.grid(True, alpha=0.3)

        path = _savefig(fig, "paxg_weekend_scatter.png")
        assert os.path.exists(path)

    def test_chart_gain_histogram_by_direction(self, weekend_pairs):
        """Chart 9: Histograms — Monday max_gain & max_loss distributions by weekend direction"""
        df = weekend_pairs.dropna()
        up = df[df["weekend_return"] > 0]
        dn = df[df["weekend_return"] < 0]

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        for i, (mask, label) in enumerate([(df["weekend_return"] > 0, "Weekend Up"),
                                            (df["weekend_return"] < 0, "Weekend Down")]):
            gains = df.loc[mask, "max_gain"] * 100
            losses = df.loc[mask, "max_loss"] * 100
            n = mask.sum()

            bins = np.linspace(min(gains.min(), losses.min()) - 0.5,
                               max(gains.max(), losses.max()) + 0.5, 40)

            ax = axes[i][0]
            ax.hist(gains, bins=bins, alpha=0.6, color="#e74c3c",
                    label=f"Gain (mean={gains.mean():.4f}%)", edgecolor="black")
            ax.hist(losses, bins=bins, alpha=0.6, color="#3498db",
                    label=f"Loss (mean={losses.mean():.4f}%)", edgecolor="black")
            ax.axvline(gains.mean(), color="#e74c3c", linestyle="--", linewidth=2)
            ax.axvline(losses.mean(), color="#3498db", linestyle="--", linewidth=2)
            ax.set_title(f"{label} (n={n}) — Monday Gain & Loss Distribution", fontsize=12, fontweight="bold")
            ax.set_xlabel("Move (%)")
            ax.set_ylabel("Count")
            ax.legend()
            ax.grid(True, alpha=0.3)

            ax = axes[i][1]
            spread = gains - losses
            ax.hist(spread, bins=30, alpha=0.7, color="#2ecc71", edgecolor="black")
            ax.axvline(spread.mean(), color="black", linestyle="--", linewidth=2,
                       label=f"Mean={spread.mean():.4f}%")
            ax.set_title(f"{label} — Intraday Range (Gain - Loss) Distribution", fontsize=12, fontweight="bold")
            ax.set_xlabel("Range (%)")
            ax.set_ylabel("Count")
            ax.legend()
            ax.grid(True, alpha=0.3)

        fig.suptitle("PAXG Monday Gain/Loss Distribution by Weekend Direction (Real Data)",
                      fontsize=14, fontweight="bold", y=1.01)
        fig.tight_layout()
        path = _savefig(fig, "paxg_directional.png")
        assert os.path.exists(path)

    def test_chart_weekend_return_histogram(self, weekend_pairs):
        """Chart 10: Histogram — weekend return distribution with gain/loss overlay"""
        df = weekend_pairs.dropna()
        up = df[df["weekend_return"] > 0]
        dn = df[df["weekend_return"] < 0]

        fig, ax = plt.subplots(figsize=(12, 7))

        bins = np.linspace(df["weekend_return"].min() * 100,
                           df["weekend_return"].max() * 100, 40)

        ax.hist(up["weekend_return"] * 100, bins=bins, alpha=0.6, color="#e74c3c",
                label=f"Weekend Up (n={len(up)}, mean gain={up['max_gain'].mean()*100:.4f}%)",
                edgecolor="black")
        ax.hist(dn["weekend_return"] * 100, bins=bins, alpha=0.6, color="#3498db",
                label=f"Weekend Down (n={len(dn)}, mean loss={dn['max_loss'].mean()*100:.4f}%)",
                edgecolor="black")

        ax.axvline(0, color="black", linewidth=1)
        ax.axvline(up["weekend_return"].mean() * 100, color="#e74c3c", linestyle="--", linewidth=2,
                   label=f"Up mean={up['weekend_return'].mean()*100:.4f}%")
        ax.axvline(dn["weekend_return"].mean() * 100, color="#3498db", linestyle="--", linewidth=2,
                   label=f"Dn mean={dn['weekend_return'].mean()*100:.4f}%")

        ax.set_title("PAXG Weekend Return Distribution (Real Data)", fontsize=13, fontweight="bold")
        ax.set_xlabel("Weekend Return (%)  [Friday close → Sunday close]")
        ax.set_ylabel("Count")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)

        path = _savefig(fig, "paxg_weekend_hist.png")
        assert os.path.exists(path)
