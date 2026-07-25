"""CostModel — 手续费模型。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostModel:
    """手续费模型。"""
    name: str = "default"
    fee_rate: float = 0.001  # 0.1% 单边
    min_fee: float = 0.0
    max_fee: float = float("inf")

    def calculate(self, quantity: float, price: float) -> float:
        """计算手续费。"""
        notional = abs(quantity * price)
        fee = notional * self.fee_rate
        return max(self.min_fee, min(fee, self.max_fee))


# 预定义费率模型
FEE_MODELS = {
    "default": CostModel(name="default", fee_rate=0.001),
    "zero": CostModel(name="zero", fee_rate=0.0),
    "F1_SpotNoBNB": CostModel(name="F1_SpotNoBNB", fee_rate=0.001),       # 现货不用 BNB 抵扣
    "F2_SpotBNB": CostModel(name="F2_SpotBNB", fee_rate=0.00075),          # 现货用 BNB 抵扣
    "F3_FutNoBNB": CostModel(name="F3_FutNoBNB", fee_rate=0.0004),         # 合约不用 BNB
    "F4_FutBNB": CostModel(name="F4_FutBNB", fee_rate=0.00018),            # 合约用 BNB
    "binance_spot": CostModel(name="binance_spot", fee_rate=0.001),
    "binance_futures_bnb": CostModel(name="binance_futures_bnb", fee_rate=0.00018),
    "binance_futures": CostModel(name="binance_futures", fee_rate=0.0004),
    "stock": CostModel(name="stock", fee_rate=0.0005, min_fee=5.0),  # 美股
}


def get_cost_model(name: str = "default") -> CostModel:
    """获取预定义费率模型。"""
    if name is None or name == "":
        return FEE_MODELS["default"]
    if name not in FEE_MODELS:
        # 尝试解析为自定义费率
        try:
            rate = float(name)
            return CostModel(name=f"custom_{rate}", fee_rate=rate)
        except (ValueError, TypeError):
            pass
        return FEE_MODELS["default"]
    return FEE_MODELS[name]


__all__ = ["CostModel", "FEE_MODELS", "get_cost_model"]
