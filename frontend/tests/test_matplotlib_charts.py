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
# PAXG Weekend Return vs Monday Directional Extreme
# ═══════════════════════════════════════════════════

class TestPAXGWeekendChart:
    """PAXG weekend return (x-axis) vs Monday directional extreme (y-axis).

    Monday extreme selected by WEEKEND direction:
      - Weekend UP  (return > 0): monday_move = (High - Open) / Open  (max upside from open)
      - Weekend DOWN (return < 0): monday_move = (Low  - Open) / Open  (max downside from open, negative)

    Hypothesis: if weekend is up, does Monday spike higher? If weekend is down, does Monday dip lower?
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

                # Select by weekend direction: up → high, down → low
                if weekend_return > 0:
                    monday_move = max_gain
                else:
                    monday_move = max_loss

                pairs.append({
                    "weekend_return": weekend_return,
                    "max_gain": max_gain,
                    "max_loss": max_loss,
                    "monday_move": monday_move,
                    "weekend_up": weekend_return > 0,
                })

        return pd.DataFrame(pairs)

    def test_chart_weekend_vs_monday_scatter(self, weekend_pairs):
        """Chart 8: Weekend return (x) vs Monday directional extreme (y)"""
        df = weekend_pairs.dropna()
        pearson_corr = df["weekend_return"].corr(df["monday_move"])
        t_stat, p_value = sp_stats.pearsonr(df["weekend_return"], df["monday_move"])

        fig, ax = plt.subplots(figsize=(10, 8))

        # Red = weekend up (measuring high), blue = weekend down (measuring low)
        colors = ["#e74c3c" if w else "#3498db" for w in df["weekend_up"]]
        ax.scatter(df["weekend_return"] * 100, df["monday_move"] * 100,
                    c=colors, alpha=0.5, s=25, edgecolors="white", linewidth=0.3)

        x_vals = np.linspace(df["weekend_return"].min() * 100, df["weekend_return"].max() * 100, 100)
        coeffs = np.polyfit(df["weekend_return"] * 100, df["monday_move"] * 100, 1)
        ax.plot(x_vals, coeffs[0] * x_vals + coeffs[1], color="black", linewidth=2,
                label=f"Regression (slope={coeffs[0]:.3f})")

        ax.axhline(0, color="gray", linewidth=0.8)
        ax.axvline(0, color="gray", linewidth=0.8)

        ax.set_title("PAXG Weekend Return vs Monday Directional Extreme (2022-2024, Real Data)",
                      fontsize=13, fontweight="bold")
        ax.set_xlabel("Weekend Return (%)  [Friday close → Sunday close]", fontsize=11)
        ax.set_ylabel("Monday Move (%)  [up→(H-O)/O, down→(L-O)/O]", fontsize=11)

        textstr = (f"Samples: {len(df)}\n"
                    f"Pearson r: {pearson_corr:.4f}\n"
                    f"p-value: {p_value:.6f}\n"
                    f"Significant: {'Yes' if p_value < 0.05 else 'No'}\n"
                    f"Red = weekend up → (High-Open)/Open\n"
                    f"Blue = weekend down → (Low-Open)/Open")
        props = dict(boxstyle="round", facecolor="wheat", alpha=0.8)
        ax.text(0.05, 0.95, textstr, transform=ax.transAxes, fontsize=10,
                verticalalignment="top", bbox=props)

        ax.legend(loc="lower right")
        ax.grid(True, alpha=0.3)

        path = _savefig(fig, "paxg_weekend_scatter.png")
        assert os.path.exists(path)

    def test_chart_weekend_directional(self, weekend_pairs):
        """Chart 9: Bar — avg monday_move by weekend direction + comparison"""
        df = weekend_pairs.dropna()

        up_grp = df[df["weekend_return"] > 0]
        down_grp = df[df["weekend_return"] < 0]

        # For weekend-up group: avg of (High-Open)/Open
        up_move = up_grp["monday_move"].mean() * 100
        # For weekend-down group: avg of (Low-Open)/Open
        down_move = down_grp["monday_move"].mean() * 100

        up_n = len(up_grp)
        down_n = len(down_grp)

        fig, ax = plt.subplots(figsize=(8, 6))

        categories = [f"Weekend Up\n(n={up_n})\n(High-Open)/Open",
                       f"Weekend Down\n(n={down_n})\n(Low-Open)/Open"]
        values = [up_move, down_move]
        colors = ["#e74c3c", "#3498db"]

        bars = ax.bar(categories, values, color=colors, alpha=0.7, edgecolor="black", width=0.5)

        for bar, val in zip(bars, values):
            y_pos = bar.get_height() + 0.02 if val >= 0 else bar.get_height() - 0.04
            ax.text(bar.get_x() + bar.get_width() / 2, y_pos,
                    f"{val:.4f}%", ha="center", fontsize=12, fontweight="bold")

        ax.set_title("PAXG Monday Directional Extreme by Weekend Direction",
                      fontsize=13, fontweight="bold")
        ax.set_ylabel("Monday Move (%)")
        ax.axhline(0, color="black", linewidth=0.5)
        ax.grid(True, alpha=0.3, axis="y")

        path = _savefig(fig, "paxg_directional.png")
        assert os.path.exists(path)

    def test_chart_rolling_correlation(self, weekend_pairs):
        """Chart 10: 52-week rolling correlation over time"""
        df = weekend_pairs.dropna()
        rolling = df["weekend_return"].rolling(52).corr(df["monday_move"])

        fig, ax = plt.subplots(figsize=(14, 5))
        ax.plot(rolling.index, rolling, color="darkgreen", linewidth=1.5)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.axhline(rolling.mean(), color="red", linestyle="--", alpha=0.7,
                    label=f"Mean: {rolling.mean():.3f}")
        ax.fill_between(rolling.index, rolling, 0, where=rolling >= 0, alpha=0.15, color="green")
        ax.fill_between(rolling.index, rolling, 0, where=rolling < 0, alpha=0.15, color="red")
        ax.set_title("PAXG Weekend Return vs Monday Directional Extreme — 52-Week Rolling Correlation",
                      fontsize=13, fontweight="bold")
        ax.set_xlabel("Date")
        ax.set_ylabel("Rolling Correlation")
        ax.set_ylim(-1, 1)
        ax.legend()
        ax.grid(True, alpha=0.3)

        path = _savefig(fig, "paxg_rolling_corr.png")
        assert os.path.exists(path)
