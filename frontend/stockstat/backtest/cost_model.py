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
