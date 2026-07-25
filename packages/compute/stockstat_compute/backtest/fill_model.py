"""FillModel — 成交模型（决定成交价）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class FillModel:
    """成交模型 — 决定订单以何价成交。"""
    name: str = "next_open"
    slippage_bps: float = 0.0  # 基点

    def get_fill_price(self, i: int, data: pd.DataFrame,
                       side: str, signal_price: Optional[float] = None) -> float:
        """返回成交价。"""
        n = len(data)
        if self.name == "next_open":
            # 下一根 K 线的 open
            if i + 1 < n:
                price = data.iloc[i + 1]["open"]
            else:
                price = data.iloc[i]["close"]
        elif self.name == "this_close":
            price = data.iloc[i]["close"]
        elif self.name == "next_close":
            if i + 1 < n:
                price = data.iloc[i + 1]["close"]
            else:
                price = data.iloc[i]["close"]
        elif self.name == "intrabar_fill":
            # 简化：用下一根的 vwap（近似 (high+low+close)/3）
            if i + 1 < n:
                row = data.iloc[i + 1]
                price = (row["high"] + row["low"] + row["close"]) / 3
            else:
                price = data.iloc[i]["close"]
        elif self.name == "signal_price":
            price = signal_price if signal_price is not None else data.iloc[i]["close"]
        else:
            price = data.iloc[i]["close"]

        # 滑点：买入加价，卖出减价
        slip = self.slippage_bps * 0.0001 * price
        if side == "buy":
            return price + slip
        elif side == "sell":
            return price - slip
        return price


FILL_MODELS = {
    "next_open": FillModel(name="next_open"),
    "this_close": FillModel(name="this_close"),
    "next_close": FillModel(name="next_close"),
    "intrabar_fill": FillModel(name="intrabar_fill"),
    "signal_price": FillModel(name="signal_price"),
    "market": FillModel(name="next_open"),  # alias
    "limit": FillModel(name="signal_price"),  # alias
}


def get_fill_model(name: str = "next_open") -> FillModel:
    if name is None or name == "":
        return FILL_MODELS["next_open"]
    return FILL_MODELS.get(name, FILL_MODELS["next_open"])


__all__ = ["FillModel", "FILL_MODELS", "get_fill_model"]
