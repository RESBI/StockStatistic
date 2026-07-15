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
