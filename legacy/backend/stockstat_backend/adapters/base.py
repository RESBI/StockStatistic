from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd


class DataSourceAdapter(ABC):
    name: str = "base"
    source_type: str = "unknown"

    @abstractmethod
    def fetch_ohlcv(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        ...

    def fetch_symbols(self) -> list[dict]:
        return []

    def supports(self, symbol: str) -> bool:
        return True

    def health_check(self) -> bool:
        return True

    def probe_range(self, symbol: str, timeframe: str = "1d") -> tuple[str | None, str | None]:
        """Probe the source for the actual earliest and latest available bar timestamps.

        Returns (earliest_iso, latest_iso); either may be None if unknown.
        Default implementation returns (None, None); subclasses should override.
        """
        return None, None
