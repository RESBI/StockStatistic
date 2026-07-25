from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    symbol: str
    side: OrderSide | str
    qty: float
    order_type: OrderType | str = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: TimeInForce | str = TimeInForce.GTC
    tag: str = ""
    order_id: str = field(default="", repr=False)
    exit_reason: str = ""
    priority: int = 99  # 0 = highest; 99 = default (lowest)

    def __post_init__(self):
        if isinstance(self.side, str):
            self.side = OrderSide(self.side)
        if isinstance(self.order_type, str):
            self.order_type = OrderType(self.order_type)
        if isinstance(self.time_in_force, str):
            self.time_in_force = TimeInForce(self.time_in_force)
        if not self.order_id:
            import uuid
            self.order_id = uuid.uuid4().hex[:12]

    @property
    def signed_qty(self) -> float:
        return self.qty if self.side == OrderSide.BUY else -self.qty


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: OrderSide | str
    qty: float
    price: float
    commission: float = 0.0
    slippage_cost: float = 0.0
    ts: object = None
    tag: str = ""
    exit_reason: str = ""
    sub_bar_ts: object = None
    sub_bar_index: int = -1

    def __post_init__(self):
        if isinstance(self.side, str):
            self.side = OrderSide(self.side)

    @property
    def signed_qty(self) -> float:
        return self.qty if self.side == OrderSide.BUY else -self.qty

    @property
    def gross_value(self) -> float:
        return self.price * self.qty

    @property
    def net_value(self) -> float:
        """Signed cash flow into the account (positive = cash in, negative = cash out)."""
        sign = 1.0 if self.side == OrderSide.SELL else -1.0
        return sign * self.gross_value - self.commission - self.slippage_cost
