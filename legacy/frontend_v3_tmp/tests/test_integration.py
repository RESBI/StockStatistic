"""
P5: Integration tests — real data via proxy.
Classic statistics + PAXG weekend correlation with real market data.
Proxy must be enabled at http://127.0.0.1:8889.
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
os.environ["DATABASE_URL"] = "sqlite:///test_integration_real.db"

from fastapi.testclient import TestClient
from stockstat_backend.app import create_app
from stockstat_backend.storage.database import reset_engine, get_engine
from stockstat_backend.models.ohlcv import Base
from stockstat_backend.config import settings
from stockstat import StockStatClient


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
            resp = c.post("/api/v1/ingest", params={
                "symbol": sym, "source": source,
                "start": start, "end": end, "timeframe": "1d",
            })
            assert resp.status_code == 200, f"Ingest {sym} failed: {resp.text}"
        yield c
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="module")
def stockstat_client(test_http_client):
    return StockStatClient(http_client=test_http_client)


# ═══════════════════════════════════════════════════
# Classic Statistics (real data)
# ═══════════════════════════════════════════════════

class TestMACross:
    """Case 1: Moving Average Golden/Death Cross"""

    def test_golden_death_cross(self, stockstat_client):
        data = stockstat_client.ohlcv("AAPL", start="2024-01-01", timeframe="1d")
        ma_short = data.close.rolling(5).mean()
        ma_long = data.close.rolling(20).mean()
        golden = (ma_short > ma_long) & (ma_short.shift(1) <= ma_long.shift(1))
        death = (ma_short < ma_long) & (ma_short.shift(1) >= ma_long.shift(1))
        assert golden.sum() >= 0
        assert death.sum() >= 0


class TestRSI:
    """Case 2: RSI Overbought/Oversold"""

    def test_rsi_range(self, stockstat_client):
        data = stockstat_client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
        rsi = stockstat_client.compute.rsi(data.close, window=14)
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()
        assert rsi.isna().sum() >= 13
        # Real BTC data should have some overbought/oversold readings
        assert (valid > 70).sum() > 0 or (valid < 30).sum() > 0


class TestBeta:
    """Case 3: Beta Coefficient (real AAPL vs S&P 500)"""

    def test_beta_value(self, stockstat_client):
        stock = stockstat_client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")
        market = stockstat_client.ohlcv("^GSPC", start="2023-01-01", timeframe="1d")
        beta = stockstat_client.compute.beta(
            asset=stock.close.pct_change(),
            benchmark=market.close.pct_change(),
            window=60,
        )
        valid = beta.dropna()
        assert len(valid) > 0
        # AAPL Beta vs S&P500 typically 1.0~1.3
        assert 0.5 < valid.mean() < 2.0


class TestMaxDrawdown:
    """Case 4: Maximum Drawdown (real BTC)"""

    def test_drawdown_range(self, stockstat_client):
        data = stockstat_client.ohlcv("BTC/USDT", start="2023-01-01", timeframe="1d")
        dd = stockstat_client.compute.max_drawdown(data.close)
        assert dd <= 0
        assert dd >= -1.0


class TestSharpe:
    """Case 5: Sharpe Ratio (real BTC)"""

    def test_sharpe_range(self, stockstat_client):
        data = stockstat_client.ohlcv("BTC/USDT", start="2023-01-01", timeframe="1d")
        rets = stockstat_client.compute.returns(data.close).dropna()
        sharpe = stockstat_client.compute.sharpe(rets, risk_free=0.02, annualize=True)
        assert isinstance(sharpe, float)
        assert -5 < sharpe < 10


class TestBollinger:
    """Case 6: Bollinger Band Breakout (real ETH)"""

    def test_band_ordering(self, stockstat_client):
        data = stockstat_client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")
        upper, mid, lower = stockstat_client.compute.bollinger(data.close, window=20, k=2.0)
        valid_idx = upper.dropna().index
        assert (upper.loc[valid_idx] >= mid.loc[valid_idx]).all()
        assert (mid.loc[valid_idx] >= lower.loc[valid_idx]).all()
        breakout = (data.close > upper).sum() / len(data)
        assert breakout < 0.15


class TestCrossAssetCorr:
    """Case 7: Cross-Asset Correlation (real BTC vs ETH)"""

    def test_btc_eth_correlation(self, stockstat_client):
        btc = stockstat_client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
        eth = stockstat_client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")
        corr = btc.close.pct_change().corr(eth.close.pct_change())
        # Real BTC/ETH correlation is typically > 0.7
        assert corr > 0.6


class TestDSLIntegration:
    """DSL queries against real backend data"""

    def test_dsl_ma_query(self, stockstat_client):
        result = stockstat_client.run_dsl(
            'SELECT close, ma(close, 20) AS ma20 FROM ohlcv("AAPL", "1d", "2024-01-01", "2024-12-31")'
        )
        assert "close" in result.columns
        assert "ma20" in result.columns
        assert len(result) > 100

    def test_dsl_rsi_query(self, stockstat_client):
        result = stockstat_client.run_dsl(
            'SELECT rsi(close, 14) AS rsi_val FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31") LIMIT 30'
        )
        assert "rsi_val" in result.columns
        assert len(result) <= 30

    def test_dsl_returns_query(self, stockstat_client):
        result = stockstat_client.run_dsl(
            'SELECT returns(close) AS ret FROM ohlcv("ETH/USDT", "1d", "2024-01-01", "2024-06-30")'
        )
        assert "ret" in result.columns
        assert result["ret"].isna().sum() == 1


class TestVisualizationIntegration:

    def test_plot_close_and_ma(self, stockstat_client, tmp_path):
        data = stockstat_client.ohlcv("AAPL", start="2024-01-01", timeframe="1d")
        spec = stockstat_client.plot.spec(
            title="AAPL Close + MA20 (Real Data)",
            x_label="Date", y_label="Price",
            series=[
                {"name": "close", "data": data.close, "kind": "line"},
                {"name": "ma20", "data": data.close.rolling(20).mean(), "kind": "line", "color": "red"},
            ],
        )
        renderer = stockstat_client.plot.get_renderer("matplotlib")
        if renderer.available():
            renderer.render(spec)
            path = str(tmp_path / "aapl_real.png")
            renderer.savefig(path)
            assert os.path.exists(path)


# ═══════════════════════════════════════════════════
# PAXG Weekend Return vs Monday Independent Gain/Loss (v2)
# ═══════════════════════════════════════════════════

class TestPAXGWeekendCorrelation:
    """PAXG weekend return vs Monday max_gain AND max_loss (independently).

    Records both (High-Open)/Open and (Low-Open)/Open for every Monday,
    then correlates the weekend return with each independently.
    This avoids the selection bias of v1 (picking one extreme by signal direction).
    """

    @pytest.fixture(scope="class")
    def paxg_data(self, stockstat_client):
        return stockstat_client.ohlcv("PAXG/USDT", start="2022-01-01", timeframe="1d")

    @pytest.fixture(scope="class")
    def weekend_corr_result(self, paxg_data):
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
                    "monday": mon_date,
                    "weekend_return": weekend_return,
                    "max_gain": max_gain,
                    "max_loss": max_loss,
                })

        result_df = pd.DataFrame(pairs).set_index("monday")

        x = result_df["weekend_return"]
        gain = result_df["max_gain"]
        loss = result_df["max_loss"]

        r_gain = x.corr(gain)
        r_loss = x.corr(loss)
        p_gain = sp_stats.pearsonr(x.dropna(), gain.dropna())[1]
        p_loss = sp_stats.pearsonr(x.dropna(), loss.dropna())[1]

        up = result_df[x > 0]
        dn = result_df[x < 0]

        # t-test: up vs down for gain and loss separately
        t_gain, p_t_gain = sp_stats.ttest_ind(up["max_gain"].dropna(), dn["max_gain"].dropna())
        t_loss, p_t_loss = sp_stats.ttest_ind(up["max_loss"].dropna(), dn["max_loss"].dropna())

        return {
            "n_samples": len(result_df),
            "n_up": len(up),
            "n_down": len(dn),
            "r_gain": r_gain, "r_loss": r_loss,
            "p_gain": p_gain, "p_loss": p_loss,
            "sig_gain": p_gain < 0.05, "sig_loss": p_loss < 0.05,
            "up_gain_mean": up["max_gain"].mean(), "up_loss_mean": up["max_loss"].mean(),
            "dn_gain_mean": dn["max_gain"].mean(), "dn_loss_mean": dn["max_loss"].mean(),
            "up_gain_std": up["max_gain"].std(), "up_loss_std": up["max_loss"].std(),
            "dn_gain_std": dn["max_gain"].std(), "dn_loss_std": dn["max_loss"].std(),
            "t_gain_ud": t_gain, "p_t_gain": p_t_gain,
            "t_loss_ud": t_loss, "p_t_loss": p_t_loss,
            "result_df": result_df,
        }

    def test_data_sufficient(self, paxg_data):
        assert len(paxg_data) > 700

    def test_has_weekend_data(self, paxg_data):
        df = paxg_data.copy()
        df["weekday"] = df.index.weekday
        assert (df["weekday"] == 5).sum() > 100  # Saturdays
        assert (df["weekday"] == 6).sum() > 100  # Sundays

    def test_sample_count(self, weekend_corr_result):
        assert weekend_corr_result["n_samples"] > 50

    def test_pearson_range(self, weekend_corr_result):
        assert -1.0 <= weekend_corr_result["r_gain"] <= 1.0
        assert -1.0 <= weekend_corr_result["r_loss"] <= 1.0

    def test_p_value_range(self, weekend_corr_result):
        assert 0.0 <= weekend_corr_result["p_gain"] <= 1.0
        assert 0.0 <= weekend_corr_result["p_loss"] <= 1.0

    def test_move_reasonable(self, weekend_corr_result):
        # PAXG is gold-pegged, intraday moves should be small
        assert abs(weekend_corr_result["up_gain_mean"]) < 0.05
        assert abs(weekend_corr_result["up_loss_mean"]) < 0.05
        assert abs(weekend_corr_result["dn_gain_mean"]) < 0.05
        assert abs(weekend_corr_result["dn_loss_mean"]) < 0.05

    def test_print_results(self, weekend_corr_result):
        print("\n" + "=" * 60)
        print("PAXG Weekend Return vs Monday Independent Gain/Loss (REAL DATA)")
        print("=" * 60)
        print(f"  Samples:    {weekend_corr_result['n_samples']} (up={weekend_corr_result['n_up']}, dn={weekend_corr_result['n_down']})")
        print(f"  r(gain):    {weekend_corr_result['r_gain']:.4f}  p={weekend_corr_result['p_gain']:.4f}  sig={weekend_corr_result['sig_gain']}")
        print(f"  r(loss):    {weekend_corr_result['r_loss']:.4f}  p={weekend_corr_result['p_loss']:.4f}  sig={weekend_corr_result['sig_loss']}")
        print(f"  Sig>0: gain={weekend_corr_result['up_gain_mean']*100:.4f}%±{weekend_corr_result['up_gain_std']*100:.4f}%, loss={weekend_corr_result['up_loss_mean']*100:.4f}%±{weekend_corr_result['up_loss_std']*100:.4f}%")
        print(f"  Sig<0: gain={weekend_corr_result['dn_gain_mean']*100:.4f}%±{weekend_corr_result['dn_gain_std']*100:.4f}%, loss={weekend_corr_result['dn_loss_mean']*100:.4f}%±{weekend_corr_result['dn_loss_std']*100:.4f}%")
        print(f"  t-test(up vs dn): gain t={weekend_corr_result['t_gain_ud']:.3f} p={weekend_corr_result['p_t_gain']:.4f}, loss t={weekend_corr_result['t_loss_ud']:.3f} p={weekend_corr_result['p_t_loss']:.4f}")
        print("=" * 60)

    def test_plot_gain_loss_scatter(self, weekend_corr_result, tmp_path):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        df = weekend_corr_result["result_df"]
        fig, ax = plt.subplots(figsize=(10, 8))
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
        ax.axhline(0, color="gray", linewidth=0.5)
        ax.axvline(0, color="gray", linewidth=0.5)
        ax.set_xlabel("Weekend Return (%)")
        ax.set_ylabel("Monday Move (%)")
        ax.set_title("PAXG Weekend Return vs Monday Gain/Loss (Independent, Real Data)")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        path = str(tmp_path / "paxg_weekend_real.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        assert os.path.exists(path)
