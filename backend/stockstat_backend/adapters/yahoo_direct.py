from __future__ import annotations

import time
from typing import Optional

import pandas as pd
import requests

from .base import DataSourceAdapter


class YahooDirectAdapter(DataSourceAdapter):
    """Direct Yahoo Finance API adapter (bypasses yfinance cookie/crumb issues)."""

    name = "yfinance"
    source_type = "stock"

    _INTERVAL_MAP = {
        "1m": "1m",
        "2m": "2m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "60m": "60m",
        "90m": "90m",
        "1h": "60m",
        "1d": "1d",
        "5d": "5d",
        "1wk": "1wk",
        "1w": "1wk",
        "1mo": "1mo",
        "3mo": "3mo",
    }

    _BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    def __init__(self, proxy: dict | None = None):
        self._proxies = proxy
        self._session = requests.Session()
        self._session.headers.update(self._HEADERS)
        if proxy:
            self._session.proxies.update(proxy)

    def fetch_ohlcv(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        interval = self._INTERVAL_MAP.get(timeframe, "1d")

        period1 = 0
        period2 = int(time.time())
        if start:
            period1 = int(pd.Timestamp(start, tz="UTC").timestamp())
        if end:
            period2 = int(pd.Timestamp(end, tz="UTC").timestamp())

        url = f"{self._BASE_URL}/{symbol}"
        params = {
            "period1": period1,
            "period2": period2,
            "interval": interval,
            "events": "div,split",
        }

        resp = self._session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            raise RuntimeError(f"Yahoo API rate limited for {symbol}")
        resp.raise_for_status()

        data = resp.json()
        result = data.get("chart", {}).get("result")
        if not result:
            return pd.DataFrame()

        quote = result[0]
        timestamps = quote.get("timestamp", [])
        indicators = quote.get("indicators", {}).get("quote", [{}])[0]

        df = pd.DataFrame({
            "open": indicators.get("open"),
            "high": indicators.get("high"),
            "low": indicators.get("low"),
            "close": indicators.get("close"),
            "volume": indicators.get("volume"),
        }, index=pd.to_datetime(timestamps, unit="s", utc=True))
        df.index.name = "ts"

        df = df.dropna(subset=["open", "high", "low", "close"])
        return df

    def supports(self, symbol: str) -> bool:
        return "/" not in symbol

    def fetch_symbols(self) -> list[dict]:
        """Return a curated catalog of popular Yahoo Finance symbols.

        Yahoo Finance has no public "list all symbols" API (unlike crypto
        exchanges' /exchangeInfo). This curated list covers major US indices,
        Dow 30, popular tech stocks, leading ETFs, global indices, and key
        commodities/FX pairs. Users can also download any valid ticker via
        the manual-input box in the admin UI.
        """
        catalog = [
            # ── Major US Indices ──
            ("^GSPC", "index", "S&P 500 Index"),
            ("^DJI", "index", "Dow Jones Industrial Average"),
            ("^IXIC", "index", "NASDAQ Composite"),
            ("^RUT", "index", "Russell 2000"),
            ("^VIX", "index", "CBOE Volatility Index"),
            ("^NYA", "index", "NYSE Composite"),

            # ── Dow 30 Components ──
            ("AAPL", "stock", "Apple Inc."),
            ("MSFT", "stock", "Microsoft Corporation"),
            ("JPM", "stock", "JPMorgan Chase & Co."),
            ("V", "stock", "Visa Inc."),
            ("UNH", "stock", "UnitedHealth Group"),
            ("HD", "stock", "The Home Depot, Inc."),
            ("MA", "stock", "Mastercard Incorporated"),
            ("PG", "stock", "Procter & Gamble Company"),
            ("DIS", "stock", "The Walt Disney Company"),
            ("MRK", "stock", "Merck & Co., Inc."),
            ("KO", "stock", "The Coca-Cola Company"),
            ("PEP", "stock", "PepsiCo, Inc."),
            ("INTC", "stock", "Intel Corporation"),
            ("CSCO", "stock", "Cisco Systems, Inc."),
            ("WMT", "stock", "Walmart Inc."),
            ("BA", "stock", "The Boeing Company"),
            ("IBM", "stock", "International Business Machines"),
            ("CAT", "stock", "Caterpillar Inc."),
            ("CVX", "stock", "Chevron Corporation"),
            ("XOM", "stock", "Exxon Mobil Corporation"),
            ("NKE", "stock", "NIKE, Inc."),
            ("MCD", "stock", "McDonald's Corporation"),
            ("GS", "stock", "Goldman Sachs Group, Inc."),
            ("AXP", "stock", "American Express Company"),
            ("MMM", "stock", "3M Company"),
            ("WBA", "stock", "Walgreens Boots Alliance"),

            # ── Popular Tech & Growth Stocks ──
            ("GOOGL", "stock", "Alphabet Inc. (Class A)"),
            ("GOOG", "stock", "Alphabet Inc. (Class C)"),
            ("AMZN", "stock", "Amazon.com, Inc."),
            ("META", "stock", "Meta Platforms, Inc."),
            ("TSLA", "stock", "Tesla, Inc."),
            ("NVDA", "stock", "NVIDIA Corporation"),
            ("AMD", "stock", "Advanced Micro Devices, Inc."),
            ("NFLX", "stock", "Netflix, Inc."),
            ("ADBE", "stock", "Adobe Inc."),
            ("CRM", "stock", "Salesforce, Inc."),
            ("ORCL", "stock", "Oracle Corporation"),
            ("BABA", "stock", "Alibaba Group Holding"),
            ("JD", "stock", "JD.com, Inc."),
            ("PDD", "stock", "PDD Holdings Inc."),

            # ── Leading ETFs ──
            ("SPY", "etf", "SPDR S&P 500 ETF Trust"),
            ("QQQ", "etf", "Invesco QQQ Trust (Nasdaq 100)"),
            ("IWM", "etf", "iShares Russell 2000 ETF"),
            ("DIA", "etf", "SPDR Dow Jones Industrial Average ETF"),
            ("VTI", "etf", "Vanguard Total Stock Market ETF"),
            ("VOO", "etf", "Vanguard S&P 500 ETF"),
            ("VEA", "etf", "Vanguard Developed Markets ETF"),
            ("VWO", "etf", "Vanguard Emerging Markets ETF"),
            ("EEM", "etf", "iShares MSCI Emerging Markets ETF"),
            ("EFA", "etf", "iShares MSCI EAFE ETF"),
            ("GLD", "etf", "SPDR Gold Shares"),
            ("SLV", "etf", "iShares Silver Trust"),
            ("TLT", "etf", "iShares 20+ Year Treasury Bond ETF"),
            ("HYG", "etf", "iShares iBoxx High Yield Corp Bond ETF"),
            ("XLF", "etf", "Financial Select Sector SPDR"),
            ("XLK", "etf", "Technology Select Sector SPDR"),
            ("XLE", "etf", "Energy Select Sector SPDR"),
            ("XLV", "etf", "Health Care Select Sector SPDR"),
            ("ARKK", "etf", "ARK Innovation ETF"),

            # ── Major Global Indices ──
            ("^N225", "index", "Nikkei 225 (Japan)"),
            ("^HSI", "index", "Hang Seng Index (Hong Kong)"),
            ("^FCHI", "index", "CAC 40 (France)"),
            ("^GDAXI", "index", "DAX Performance (Germany)"),
            ("^FTSE", "index", "FTSE 100 (UK)"),
            ("^BSESN", "index", "S&P BSE SENSEX (India)"),
            ("000001.SS", "index", "Shanghai Composite (China)"),
            ("^STOXX50E", "index", "Euro Stoxx 50"),
            ("^AXJO", "index", "S&P/ASX 200 (Australia)"),
            ("^GSPTSE", "index", "S&P/TSX Composite (Canada)"),

            # ── Commodities & FX ──
            ("GC=F", "commodity", "Gold Futures"),
            ("SI=F", "commodity", "Silver Futures"),
            ("CL=F", "commodity", "Crude Oil WTI Futures"),
            ("NG=F", "commodity", "Natural Gas Futures"),
            ("HG=F", "commodity", "Copper Futures"),
            ("PL=F", "commodity", "Platinum Futures"),
            ("USDCNY=X", "fx", "USD/CNY Exchange Rate"),
            ("USDKRW=X", "fx", "USD/KRW Exchange Rate"),
            ("EURUSD=X", "fx", "EUR/USD Exchange Rate"),
            ("USDJPY=X", "fx", "USD/JPY Exchange Rate"),
        ]

        return [
            {
                "unified_symbol": sym,
                "base_asset": sym,
                "quote_asset": "USD",
                "asset_type": asset_type,
                "description": desc,
            }
            for sym, asset_type, desc in catalog
        ]

    def health_check(self) -> bool:
        try:
            resp = self._session.get(
                f"{self._BASE_URL}/AAPL",
                params={"period1": int(time.time()) - 86400, "period2": int(time.time()), "interval": "1d"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def probe_range(self, symbol: str, timeframe: str = "1d") -> tuple[str | None, str | None]:
        """Probe Yahoo Finance for the actual earliest and latest available bar timestamps.

        Returns (earliest_iso, latest_iso); either may be None on failure.
        """
        interval = self._INTERVAL_MAP.get(timeframe, "1d")
        now = int(time.time())
        earliest = None
        latest = None
        try:
            # Query a wide range to find the first available bar
            url = f"{self._BASE_URL}/{symbol}"
            params = {
                "period1": 0,
                "period2": now,
                "interval": interval,
                "events": "div,split",
            }
            resp = self._session.get(url, params=params, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("chart", {}).get("result")
                if result:
                    timestamps = result[0].get("timestamp", [])
                    if timestamps:
                        earliest = pd.Timestamp(timestamps[0], unit="s", tz="UTC").isoformat()
                        latest = pd.Timestamp(timestamps[-1], unit="s", tz="UTC").isoformat()
        except Exception:
            pass
        return earliest, latest
