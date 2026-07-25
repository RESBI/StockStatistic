from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from .orders import Order, Fill


class CostModel(ABC):
    """Abstract base for transaction cost models."""

    @abstractmethod
    def compute(self, order: Order, fill_price: float, fill_qty: float) -> tuple[float, float]:
        """Return (commission, slippage_cost) for a fill."""
        ...


@dataclass
class PercentCost(CostModel):
    """Percentage commission + percentage slippage (in bps-like fraction)."""
    commission: float = 0.0003
    slippage: float = 0.0002

    def compute(self, order: Order, fill_price: float, fill_qty: float) -> tuple[float, float]:
        gross = fill_price * fill_qty
        comm = gross * self.commission
        slip = gross * self.slippage
        return comm, slip


@dataclass
class FixedCost(CostModel):
    """Fixed fee per fill plus optional percentage slippage."""
    fee: float = 5.0
    slippage: float = 0.0001

    def compute(self, order: Order, fill_price: float, fill_qty: float) -> tuple[float, float]:
        gross = fill_price * fill_qty
        return self.fee, gross * self.slippage


@dataclass
class TieredCost(CostModel):
    """Tiered commission by gross trade value."""
    tiers: list[tuple[float, float]] = None  # [(threshold, rate), ...] sorted asc
    slippage: float = 0.0002

    def __post_init__(self):
        if self.tiers is None:
            self.tiers = [(0.0, 0.0005), (50_000.0, 0.0003), (250_000.0, 0.0002)]

    def compute(self, order: Order, fill_price: float, fill_qty: float) -> tuple[float, float]:
        gross = fill_price * fill_qty
        rate = self.tiers[0][1]
        for threshold, r in self.tiers:
            if gross >= threshold:
                rate = r
        return gross * rate, gross * self.slippage


@dataclass
class MinCost(CostModel):
    """Percentage with a minimum fee floor."""
    commission: float = 0.0003
    min_fee: float = 1.0
    slippage: float = 0.0002

    def compute(self, order: Order, fill_price: float, fill_qty: float) -> tuple[float, float]:
        gross = fill_price * fill_qty
        return max(gross * self.commission, self.min_fee), gross * self.slippage


@dataclass
class StampDutyCost(CostModel):
    """Equity-style: commission on both sides, stamp duty on sell side only."""
    commission: float = 0.0003
    stamp_duty: float = 0.001
    slippage: float = 0.0002

    def compute(self, order: Order, fill_price: float, fill_qty: float) -> tuple[float, float]:
        from .orders import OrderSide
        gross = fill_price * fill_qty
        comm = gross * self.commission
        if order.side == OrderSide.SELL:
            comm += gross * self.stamp_duty
        return comm, gross * self.slippage


@dataclass
class ZeroCost(CostModel):
    def compute(self, order: Order, fill_price: float, fill_qty: float) -> tuple[float, float]:
        return 0.0, 0.0


@dataclass
class MakerTakerCost(CostModel):
    """Maker/Taker differentiated commission.

    LIMIT orders use maker_rate (passive, provides liquidity).
    MARKET/STOP orders use taker_rate (aggressive, takes liquidity).
    """
    maker_rate: float = 0.001
    taker_rate: float = 0.001
    slippage: float = 0.0001

    def compute(self, order: Order, fill_price: float, fill_qty: float) -> tuple[float, float]:
        from .orders import OrderType
        gross = fill_price * fill_qty
        is_maker = order.order_type == OrderType.LIMIT
        rate = self.maker_rate if is_maker else self.taker_rate
        comm = gross * rate
        slip = gross * self.slippage
        return comm, slip


@dataclass
class BinanceCost(CostModel):
    """Binance exchange fee model with BNB discount support.

    Spot:    maker 0.100% / taker 0.100%  (BNB: 0.075% / 0.075%, -25%)
    Futures: maker 0.020% / taker 0.050%  (BNB: 0.018% / 0.045%, -10%)
    """
    venue: str = "spot"
    bnb_discount: bool = False
    slippage: float = 0.0001

    _SPOT_RATES = {"maker": 0.001, "taker": 0.001}
    _FUT_RATES = {"maker": 0.0002, "taker": 0.0005}
    _SPOT_DISCOUNT = 0.25
    _FUT_DISCOUNT = 0.10

    @property
    def _rates(self) -> dict:
        base = self._SPOT_RATES if self.venue == "spot" else self._FUT_RATES
        if not self.bnb_discount:
            return base
        discount = self._SPOT_DISCOUNT if self.venue == "spot" else self._FUT_DISCOUNT
        return {k: v * (1 - discount) for k, v in base.items()}

    def compute(self, order: Order, fill_price: float, fill_qty: float) -> tuple[float, float]:
        from .orders import OrderType
        gross = fill_price * fill_qty
        is_maker = order.order_type == OrderType.LIMIT
        rate = self._rates["maker"] if is_maker else self._rates["taker"]
        comm = gross * rate
        slip = gross * self.slippage
        return comm, slip


BINANCE_SPOT = BinanceCost(venue="spot", bnb_discount=False)
BINANCE_SPOT_BNB = BinanceCost(venue="spot", bnb_discount=True)
BINANCE_FUTURES = BinanceCost(venue="futures", bnb_discount=False)
BINANCE_FUTURES_BNB = BinanceCost(venue="futures", bnb_discount=True)
