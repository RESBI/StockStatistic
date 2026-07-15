"""
Usage guide verification script — all examples tested locally.
Run: python docs/verify_usage.py
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "frontend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ["STOCKSTAT_PROXY_ENABLED"] = "true"
os.environ["STOCKSTAT_PROXY_TYPE"] = "http"
os.environ["STOCKSTAT_PROXY_URL"] = "http://127.0.0.1:8889"
os.environ["DATABASE_URL"] = "sqlite:///test_usage.db"

from fastapi.testclient import TestClient
from stockstat_backend.app import create_app
from stockstat_backend.storage.database import reset_engine, get_engine
from stockstat_backend.models.ohlcv import Base
from stockstat_backend.config import settings
from stockstat import StockStatClient
import pandas as pd
import numpy as np


def main():
    settings.reload()
    reset_engine()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app = create_app()

    with TestClient(app) as http_client:
        client = StockStatClient(http_client=http_client)

        print("=" * 70)
        print("StockStat Usage Guide Verification")
        print("=" * 70)

        # ── Example 1: Ingest data ──
        print("\n--- Example 1: Ingest data ---")
        r = client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")
        print(f"Ingest AAPL: {r}")
        assert r["ingested"] > 200

        r = client.ingest("BTC/USDT", source="binance", start="2024-01-01", end="2024-12-31")
        print(f"Ingest BTC/USDT: {r}")
        assert r["ingested"] > 300

        r = client.ingest("ETH/USDT", source="binance", start="2024-01-01", end="2024-12-31")
        r = client.ingest("^GSPC", source="yfinance", start="2023-01-01", end="2024-12-31")
        r = client.ingest("PAXG/USDT", source="binance", start="2022-01-01", end="2024-12-31")

        # ── Example 2: Query OHLCV ──
        print("\n--- Example 2: Query OHLCV ---")
        data = client.ohlcv("AAPL", start="2024-01-01", timeframe="1d", limit=5)
        print(data)
        assert len(data) == 5
        assert "close" in data.columns

        # ── Example 3: MA / EMA ──
        print("\n--- Example 3: Moving Averages ---")
        ma20 = client.compute.ma(data.close, window=5)
        print(f"MA(5) last 3:\n{ma20.tail(3)}")
        assert ma20.isna().sum() == 4

        ema12 = client.compute.ema(data.close, window=3)
        print(f"EMA(3): {ema12.tolist()}")
        assert ema12.isna().sum() == 0

        # ── Example 4: RSI ──
        print("\n--- Example 4: RSI ---")
        btc = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
        rsi = client.compute.rsi(btc.close, window=14)
        print(f"RSI(14) last 5:\n{rsi.tail(5).round(2)}")
        assert rsi.dropna().between(0, 100).all()
        overbought = (rsi > 70).sum()
        oversold = (rsi < 30).sum()
        print(f"Overbought days: {overbought}, Oversold days: {oversold}")

        # ── Example 5: MACD ──
        print("\n--- Example 5: MACD ---")
        macd_line, signal_line, hist = client.compute.macd(btc.close)
        print(f"MACD last: {macd_line.iloc[-1]:.2f}")
        print(f"Signal last: {signal_line.iloc[-1]:.2f}")
        print(f"Histogram last: {hist.iloc[-1]:.2f}")
        assert len(macd_line) == len(btc)

        # ── Example 6: Bollinger Bands ──
        print("\n--- Example 6: Bollinger Bands ---")
        upper, mid, lower = client.compute.bollinger(btc.close, window=20, k=2.0)
        print(f"Upper last: {upper.iloc[-1]:.2f}")
        print(f"Mid last:   {mid.iloc[-1]:.2f}")
        print(f"Lower last: {lower.iloc[-1]:.2f}")
        valid = upper.dropna().index
        assert (upper.loc[valid] >= mid.loc[valid]).all()
        assert (mid.loc[valid] >= lower.loc[valid]).all()

        # ── Example 7: Beta ──
        print("\n--- Example 7: Beta ---")
        stock = client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")
        market = client.ohlcv("^GSPC", start="2023-01-01", timeframe="1d")
        beta = client.compute.beta(
            stock.close.pct_change(), market.close.pct_change(), window=60
        )
        print(f"Beta(60d) mean: {beta.dropna().mean():.4f}")
        assert 0.5 < beta.dropna().mean() < 2.0

        # ── Example 8: Sharpe Ratio ──
        print("\n--- Example 8: Sharpe Ratio ---")
        rets = client.compute.returns(btc.close).dropna()
        sharpe = client.compute.sharpe(rets, risk_free=0.02, annualize=True)
        print(f"BTC Sharpe (annualized): {sharpe:.4f}")
        assert -5 < sharpe < 10

        # ── Example 9: Max Drawdown ──
        print("\n--- Example 9: Max Drawdown ---")
        dd = client.compute.max_drawdown(btc.close)
        print(f"BTC Max Drawdown: {dd:.4f} ({dd*100:.2f}%)")
        assert -1.0 <= dd <= 0

        # ── Example 10: Correlation ──
        print("\n--- Example 10: Cross-Asset Correlation ---")
        eth = client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")
        corr = btc.close.pct_change().corr(eth.close.pct_change())
        print(f"BTC/ETH daily return correlation: {corr:.4f}")
        assert corr > 0.6

        # ── Example 11: DSL ──
        print("\n--- Example 11: DSL Query ---")
        result = client.run_dsl('''
            SELECT close, ma(close, 20) AS ma20
            FROM ohlcv("AAPL", "1d", "2024-01-01", "2024-12-31")
            LIMIT 5
        ''')
        print(result)
        assert "close" in result.columns
        assert "ma20" in result.columns
        assert len(result) == 5

        # ── Example 12: Custom indicator ──
        print("\n--- Example 12: Custom Indicator ---")
        @client.compute.register("volatility_regime", category="custom")
        def volatility_regime(data, window=20, high_threshold=0.04):
            ret = data.close.pct_change()
            vol = ret.rolling(window).std()
            regime = vol.apply(lambda v: "high" if v > high_threshold else "low")
            return {"regime": regime, "volatility": vol}

        result = client.compute.call("volatility_regime", data=btc)
        high_vol_days = (result["regime"] == "high").sum()
        low_vol_days = (result["regime"] == "low").sum()
        print(f"High volatility days: {high_vol_days}")
        print(f"Low volatility days: {low_vol_days}")

        # ── Example 13: PAXG Weekend Directional Extreme ──
        print("\n--- Example 13: PAXG Weekend Directional Extreme ---")
        from scipy import stats
        paxg = client.ohlcv("PAXG/USDT", start="2022-01-01", timeframe="1d")
        df = paxg.copy()
        df["weekday"] = df.index.weekday
        fridays = df[df.weekday == 4][["close"]]
        sundays = df[df.weekday == 6][["close"]]
        mondays = df[df.weekday == 0][["open", "high", "low", "close"]]

        pairs = []
        for mon_date, mon_row in mondays.iterrows():
            prev_fri = fridays.loc[:mon_date].tail(1)
            prev_sun = sundays.loc[:mon_date].tail(1)
            if len(prev_fri) > 0 and len(prev_sun) > 0:
                fri_c = prev_fri["close"].iloc[0]
                sun_c = prev_sun["close"].iloc[0]
                weekend_ret = (sun_c - fri_c) / fri_c
                mon_open = mon_row["open"]
                max_gain = (mon_row["high"] - mon_open) / mon_open
                max_loss = (mon_row["low"] - mon_open) / mon_open
                # Select by weekend direction: up → high, down → low
                monday_move = max_gain if weekend_ret > 0 else max_loss
                pairs.append({"weekend_return": weekend_ret, "monday_move": monday_move})

        result_df = pd.DataFrame(pairs)
        pearson = result_df["weekend_return"].corr(result_df["monday_move"])
        t_stat, p_value = stats.pearsonr(result_df["weekend_return"], result_df["monday_move"])
        up = result_df[result_df["weekend_return"] > 0]
        dn = result_df[result_df["weekend_return"] < 0]
        print(f"Samples: {len(result_df)}")
        print(f"Pearson correlation: {pearson:.4f}")
        print(f"p-value: {p_value:.6f}")
        print(f"Significant (p<0.05): {p_value < 0.05}")
        print(f"Weekend Up  (n={len(up)}): avg (High-Open)/Open = {up['monday_move'].mean()*100:.4f}%")
        print(f"Weekend Dn  (n={len(dn)}): avg (Low-Open)/Open  = {dn['monday_move'].mean()*100:.4f}%")
        assert len(result_df) > 50
        assert -1 <= pearson <= 1

        # ── Example 14: Visualization ──
        print("\n--- Example 14: Visualization ---")
        spec = client.plot.spec(
            title="BTC Close + Bollinger",
            series=[
                {"name": "close", "data": btc.close, "kind": "line"},
                {"name": "ma20", "data": btc.close.rolling(20).mean(), "kind": "line", "color": "red"},
            ],
        )
        renderer = client.plot.get_renderer("matplotlib")
        assert renderer.available()
        fig = renderer.render(spec)
        assert fig is not None
        renderer.savefig(os.path.join(os.path.dirname(__file__), "images", "usage_btc.png"))
        print("Saved usage_btc.png")

        print("\n" + "=" * 70)
        print("ALL USAGE EXAMPLES PASSED")
        print("=" * 70)

    Base.metadata.drop_all(engine)
    if os.path.exists("test_usage.db"):
        os.remove("test_usage.db")


if __name__ == "__main__":
    main()
