from __future__ import annotations

import importlib
import uuid
import warnings
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import pandas as pd
from stockstat_contracts import ComponentRef, StrategyRef

from .catalog import COMPONENTS
from .indicators import max_drawdown, sharpe
from .market import Universe


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"


@dataclass
class Order:
    instrument: str
    side: OrderSide | str
    qty: float
    order_type: OrderType | str = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: TimeInForce | str = TimeInForce.GTC
    tag: str = ""
    order_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    exit_reason: str = ""
    priority: int = 99

    def __post_init__(self):
        self.side = OrderSide(self.side)
        self.order_type = OrderType(self.order_type)
        self.time_in_force = TimeInForce(self.time_in_force)
        if self.qty <= 0:
            raise ValueError("order quantity must be positive")

    @property
    def symbol(self) -> str:
        return self.instrument

    @property
    def signed_qty(self) -> float:
        return self.qty if self.side is OrderSide.BUY else -self.qty


@dataclass
class Fill:
    order_id: str
    instrument: str
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
        self.side = OrderSide(self.side)

    @property
    def symbol(self) -> str:
        return self.instrument

    @property
    def signed_qty(self) -> float:
        return self.qty if self.side is OrderSide.BUY else -self.qty

    @property
    def net_cash_flow(self) -> float:
        direction = 1.0 if self.side is OrderSide.SELL else -1.0
        return direction * self.price * self.qty - self.commission - self.slippage_cost


class CostModel:
    def compute(self, order: Order, price: float, qty: float) -> tuple[float, float]:
        raise NotImplementedError


@dataclass
class PercentCost(CostModel):
    commission: float = 0.0003
    slippage: float = 0.0002

    def compute(self, order, price, qty):
        gross = price * qty
        return gross * self.commission, gross * self.slippage


@dataclass
class FixedCost(CostModel):
    fee: float = 5.0
    slippage: float = 0.0001

    def compute(self, order, price, qty):
        return self.fee, price * qty * self.slippage


@dataclass
class TieredCost(CostModel):
    tiers: list[tuple[float, float]] | None = None
    slippage: float = 0.0002

    def compute(self, order, price, qty):
        gross = price * qty
        tiers = self.tiers or [(0.0, 0.0005), (50_000.0, 0.0003), (250_000.0, 0.0002)]
        rate = tiers[0][1]
        for threshold, candidate in tiers:
            if gross >= threshold:
                rate = candidate
        return gross * rate, gross * self.slippage


@dataclass
class MinCost(CostModel):
    commission: float = 0.0003
    min_fee: float = 1.0
    slippage: float = 0.0002

    def compute(self, order, price, qty):
        gross = price * qty
        return max(gross * self.commission, self.min_fee), gross * self.slippage


@dataclass
class StampDutyCost(CostModel):
    commission: float = 0.0003
    stamp_duty: float = 0.001
    slippage: float = 0.0002

    def compute(self, order, price, qty):
        gross = price * qty
        commission = gross * self.commission
        if order.side is OrderSide.SELL:
            commission += gross * self.stamp_duty
        return commission, gross * self.slippage


class ZeroCost(CostModel):
    def compute(self, order, price, qty):
        return 0.0, 0.0


@dataclass
class MakerTakerCost(CostModel):
    maker_rate: float = 0.001
    taker_rate: float = 0.001
    slippage: float = 0.0001

    def compute(self, order, price, qty):
        gross = price * qty
        rate = self.maker_rate if order.order_type is OrderType.LIMIT else self.taker_rate
        return gross * rate, gross * self.slippage


@dataclass
class BinanceCost(CostModel):
    venue: str = "spot"
    bnb_discount: bool = False
    slippage: float = 0.0001

    def compute(self, order, price, qty):
        base = (
            {"maker": 0.001, "taker": 0.001}
            if self.venue == "spot"
            else {"maker": 0.0002, "taker": 0.0005}
        )
        if self.bnb_discount:
            discount = 0.25 if self.venue == "spot" else 0.10
            base = {name: rate * (1 - discount) for name, rate in base.items()}
        kind = "maker" if order.order_type is OrderType.LIMIT else "taker"
        gross = price * qty
        return gross * base[kind], gross * self.slippage


class FillModel:
    def fill_price(self, order: Order, current: pd.Series, upcoming: pd.Series | None):
        raise NotImplementedError


class NextOpenFill(FillModel):
    def fill_price(self, order, current, upcoming):
        return None if upcoming is None else float(upcoming.open)


class NextCloseFill(FillModel):
    def fill_price(self, order, current, upcoming):
        return None if upcoming is None else float(upcoming.close)


class ThisCloseFill(FillModel):
    def __init__(self, warn: bool = True):
        self.warn = warn
        self._warned = False

    def fill_price(self, order, current, upcoming):
        if self.warn and not self._warned:
            warnings.warn("fill.this_close can introduce lookahead", stacklevel=2)
            self._warned = True
        return float(current.close)


class VWAPFill(FillModel):
    def fill_price(self, order, current, upcoming):
        if upcoming is None:
            return None
        return float((upcoming.open + upcoming.high + upcoming.low + upcoming.close) / 4.0)


class WorstPriceFill(FillModel):
    def fill_price(self, order, current, upcoming):
        if upcoming is None:
            return None
        return float(upcoming.high if order.side is OrderSide.BUY else upcoming.low)


class IntrabarLimitFill(FillModel):
    def fill_price(self, order, current, upcoming):
        if upcoming is None:
            return None
        if order.order_type is OrderType.MARKET:
            return float(upcoming.open)
        if order.order_type is OrderType.LIMIT:
            touched = (
                upcoming.low <= order.limit_price
                if order.side is OrderSide.BUY
                else upcoming.high >= order.limit_price
            )
            return float(order.limit_price) if touched else None
        if order.order_type is OrderType.STOP:
            touched = (
                upcoming.high >= order.stop_price
                if order.side is OrderSide.BUY
                else upcoming.low <= order.stop_price
            )
            return float(order.stop_price) if touched else None
        if order.order_type is OrderType.STOP_LIMIT:
            stop_touched = (
                upcoming.high >= order.stop_price
                if order.side is OrderSide.BUY
                else upcoming.low <= order.stop_price
            )
            limit_touched = (
                upcoming.low <= order.limit_price
                if order.side is OrderSide.BUY
                else upcoming.high >= order.limit_price
            )
            return float(order.limit_price) if stop_touched and limit_touched else None
        return None


def _condition_matches(order: Order, price: float) -> bool:
    if order.order_type is OrderType.MARKET:
        return True
    if order.order_type is OrderType.LIMIT:
        return (
            price <= order.limit_price
            if order.side is OrderSide.BUY
            else price >= order.limit_price
        )
    if order.order_type is OrderType.STOP:
        return (
            price >= order.stop_price if order.side is OrderSide.BUY else price <= order.stop_price
        )
    return True


@dataclass
class Position:
    instrument: str
    qty: float = 0.0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0

    def apply(self, signed_qty: float, price: float) -> float:
        old_qty = self.qty
        new_qty = old_qty + signed_qty
        realized = 0.0
        if old_qty and ((old_qty > 0) != (signed_qty > 0)):
            closing = min(abs(signed_qty), abs(old_qty))
            realized = closing * (price - self.avg_cost) * (1 if old_qty > 0 else -1)
            self.realized_pnl += realized
        if new_qty == 0:
            self.avg_cost = 0.0
        elif old_qty == 0 or ((old_qty > 0) != (new_qty > 0)):
            self.avg_cost = price
        elif (old_qty > 0) == (signed_qty > 0):
            self.avg_cost = (old_qty * self.avg_cost + signed_qty * price) / new_qty
        self.qty = new_qty
        return realized


class Portfolio:
    def __init__(self, initial_cash: float, allow_short: bool):
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.allow_short = allow_short
        self.positions: dict[str, Position] = {}
        self.fills: list[Fill] = []
        self.realized_history: list[tuple[object, str, float]] = []
        self._equity: list[tuple[object, float, float, float]] = []

    def get_position(self, instrument: str) -> Position:
        return self.positions.setdefault(instrument, Position(instrument))

    def apply_fill(self, fill: Fill) -> None:
        position = self.get_position(fill.instrument)
        if not self.allow_short and position.qty + fill.signed_qty < -1e-9:
            raise RuntimeError("short selling is disabled")
        realized = position.apply(fill.signed_qty, fill.price)
        if abs(realized) > 1e-12:
            self.realized_history.append((fill.ts, fill.instrument, realized))
        self.cash += fill.net_cash_flow
        self.fills.append(fill)

    def mark(self, prices: dict[str, float], ts) -> None:
        market_value = sum(
            position.qty * prices.get(name, 0.0) for name, position in self.positions.items()
        )
        self._equity.append((ts, self.cash + market_value, self.cash, market_value))

    @property
    def equity_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            self._equity, columns=["ts", "equity", "cash", "market_value"]
        ).set_index("ts")


class Broker:
    def __init__(self, portfolio: Portfolio, cost_model: CostModel, fill_model: FillModel):
        self.portfolio = portfolio
        self.cost_model = cost_model
        self.fill_model = fill_model
        self._pending: dict[str, Order] = {}

    def submit(self, order: Order) -> str:
        self._pending[order.order_id] = order
        return order.order_id

    def process_bar(self, instrument, current, upcoming, ts) -> list[Fill]:
        fills = []
        remove = []
        for order_id, order in list(self._pending.items()):
            if order.instrument != instrument:
                continue
            price = self.fill_model.fill_price(order, current, upcoming)
            if price is None or not _condition_matches(order, price):
                continue
            commission, slippage = self.cost_model.compute(order, price, order.qty)
            fill = Fill(
                order.order_id,
                order.instrument,
                order.side,
                order.qty,
                price,
                commission,
                slippage,
                ts,
                order.tag,
                order.exit_reason,
            )
            self.portfolio.apply_fill(fill)
            fills.append(fill)
            remove.append(order_id)
        for order_id in remove:
            self._pending.pop(order_id, None)
        return fills


class History:
    def __init__(self):
        self._values = {}

    def __getitem__(self, name):
        return self._values[name]

    def __setitem__(self, name, value):
        self._values[name] = value

    def get(self, name, default=None):
        return self._values.get(name, default)


class DataFeed:
    _ORDER = ("1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w")

    def __init__(self, universe: Universe, primary_timeframe: str | None = None):
        self.universe = universe
        timeframes = {
            tf for instrument in universe.instruments for tf in universe.timeframes(instrument)
        }
        self.primary_timeframe = primary_timeframe or next(
            (tf for tf in self._ORDER if tf in timeframes), sorted(timeframes)[0]
        )
        self.primary_tf = self.primary_timeframe
        index = None
        for instrument in universe.instruments:
            tf = (
                self.primary_timeframe
                if self.primary_timeframe in universe.timeframes(instrument)
                else universe.timeframes(instrument)[0]
            )
            candidate = universe.frame(instrument, tf).index
            index = candidate if index is None else index.union(candidate)
        self.master_index = index.sort_values().unique()

    def bar_at(self, instrument, timeframe, ts):
        frame = self.universe.frame(instrument, timeframe)
        if ts not in frame.index:
            return None
        return frame.loc[ts]

    def get_slice(self, instrument, timeframe, ts, lookback=None):
        frame = self.universe.frame(instrument, timeframe)
        values = frame.loc[:ts]
        return values if lookback is None else values.iloc[-lookback:]

    def intrabar_slice(self, instrument, parent_timeframe, child_timeframe, ts):
        parent = self.universe.frame(instrument, parent_timeframe)
        child = self.universe.frame(instrument, child_timeframe)
        location = parent.index.get_loc(ts)
        end = (
            parent.index[location + 1]
            if location + 1 < len(parent)
            else ts + pd.Timedelta(parent_timeframe)
        )
        return child.loc[(child.index >= ts) & (child.index < end)]


class BacktestContext:
    def __init__(self, engine: BacktestEngine, now, current_bar):
        self._engine = engine
        self.now = now
        self.current_bar = current_bar
        self.history = engine.history

    @property
    def broker(self):
        return self._engine.broker

    @property
    def portfolio(self):
        return self._engine.portfolio

    @property
    def rng(self):
        return self._engine.rng

    def get(self, instrument, timeframe="1d", lookback=None):
        result = self._engine.data_feed.get_slice(instrument, timeframe, self.now, lookback)
        if self._engine.lookahead_audit and not result.empty and result.index.max() > self.now:
            raise RuntimeError("lookahead access rejected")
        return result

    def intrabar_submit(self, order: Order):
        if not self._engine.execution_model.is_intrabar:
            warnings.warn("intrabar order submitted to next-bar execution", stacklevel=2)
            return self.broker.submit(order)
        self._engine.intrabar_pending.append(order)
        return order.order_id

    def intrabar_submit_oco_mutual(self, first: Order, second: Order):
        self.intrabar_submit(first)
        self.intrabar_submit(second)
        self._engine.execution_model.register_mutual(first, second)
        return first.order_id, second.order_id


class Strategy:
    name = "base"

    def on_start(self, ctx):
        pass

    def on_bar(self, ctx):
        pass

    def on_fill(self, fill, ctx):
        pass

    def on_bar_close(self, ctx):
        pass

    def on_end(self, ctx):
        pass


class IntrabarMixin:
    def define_exits(self, entry_fill, ctx):
        return []


class ExecutionModel:
    is_intrabar = False


class NextBarExecution(ExecutionModel):
    pass


class IntrabarExecution(ExecutionModel):
    is_intrabar = True

    def __init__(self, intrabar_tf: str, parent_tf: str = "1d"):
        self.intrabar_tf = intrabar_tf
        self.parent_tf = parent_tf
        self._mutual: dict[str, str] = {}
        self._filler = IntrabarLimitFill()

    def register_mutual(self, first: Order, second: Order):
        self._mutual[first.order_id] = second.order_id
        self._mutual[second.order_id] = first.order_id

    def execute(self, engine: BacktestEngine, ctx, ts, orders: list[Order]):
        fills = []
        for instrument in engine.universe.instruments:
            timeframes = engine.universe.timeframes(instrument)
            if self.parent_tf not in timeframes or self.intrabar_tf not in timeframes:
                continue
            sub_bars = engine.data_feed.intrabar_slice(
                instrument, self.parent_tf, self.intrabar_tf, ts
            )
            candidates = []
            for order in sorted(
                (item for item in orders if item.instrument == instrument),
                key=lambda item: item.priority,
            ):
                for index, (sub_ts, bar) in enumerate(sub_bars.iterrows()):
                    price = self._filler.fill_price(order, bar, bar)
                    if price is not None:
                        candidates.append((index, sub_ts, order, price))
                        break
            candidate_ids = {candidate[2].order_id for candidate in candidates}
            cancelled = {
                order_id
                for order_id in candidate_ids
                if self._mutual.get(order_id) in candidate_ids
            }
            for index, sub_ts, order, price in sorted(
                candidates, key=lambda item: (item[0], item[2].priority)
            ):
                if order.order_id in cancelled:
                    continue
                commission, slippage = engine.cost_model.compute(order, price, order.qty)
                fill = Fill(
                    order.order_id,
                    instrument,
                    order.side,
                    order.qty,
                    price,
                    commission,
                    slippage,
                    ts,
                    order.tag,
                    order.exit_reason,
                    sub_ts,
                    index,
                )
                engine.portfolio.apply_fill(fill)
                fills.append(fill)
                exits = getattr(engine.strategy, "define_exits", lambda *_: [])(fill, ctx) or []
                remaining = sub_bars.iloc[index:]
                exit_fill = self._first_exit(engine, exits, remaining, ts)
                if exit_fill:
                    fills.append(exit_fill)
        return fills

    def _first_exit(self, engine, orders, bars, ts):
        close_orders = [
            order
            for order in orders
            if order.order_type is OrderType.MARKET and order.tag == "close"
        ]
        active = [order for order in orders if order not in close_orders]
        for index, (sub_ts, bar) in enumerate(bars.iterrows()):
            for order in sorted(active, key=lambda item: item.priority):
                price = self._filler.fill_price(order, bar, bar)
                if price is None:
                    continue
                commission, slippage = engine.cost_model.compute(order, price, order.qty)
                fill = Fill(
                    order.order_id,
                    order.instrument,
                    order.side,
                    order.qty,
                    price,
                    commission,
                    slippage,
                    ts,
                    order.tag,
                    order.exit_reason,
                    sub_ts,
                    index,
                )
                engine.portfolio.apply_fill(fill)
                return fill
        if close_orders and len(bars):
            order = close_orders[0]
            price = float(bars.iloc[-1].close)
            commission, slippage = engine.cost_model.compute(order, price, order.qty)
            fill = Fill(
                order.order_id,
                order.instrument,
                order.side,
                order.qty,
                price,
                commission,
                slippage,
                ts,
                order.tag,
                order.exit_reason,
                bars.index[-1],
                len(bars) - 1,
            )
            engine.portfolio.apply_fill(fill)
            return fill
        return None


def load_strategy(reference: StrategyRef) -> Strategy:
    if reference.kind not in {"builtin", "python_module", "python_package"}:
        raise ValueError(f"unsupported strategy kind: {reference.kind}")
    if not reference.entrypoint or ":" not in reference.entrypoint:
        raise ValueError("strategy entrypoint must be module:factory")
    module_name, factory_name = reference.entrypoint.split(":", 1)
    factory = getattr(importlib.import_module(module_name), factory_name)
    strategy = factory(reference.config)
    if not isinstance(strategy, Strategy):
        raise TypeError("strategy factory must return Strategy")
    return strategy


@dataclass
class BacktestResult:
    equity: pd.DataFrame
    fills: pd.DataFrame
    positions: pd.DataFrame
    metrics: dict[str, float]
    config: dict[str, object]
    realized_history: list[tuple[object, str, float]]
    benchmark: pd.Series | None = None

    @property
    def trades(self):
        return self.fills

    @property
    def equity_series(self):
        return self.equity["equity"]


class BacktestEngine:
    def __init__(
        self,
        data: Universe | dict[str, dict[str, pd.DataFrame]],
        strategy: Strategy,
        initial_cash: float = 1_000_000.0,
        cost_model: CostModel | None = None,
        fill_model: FillModel | None = None,
        benchmark: str | None = None,
        trade_on: str = "open",
        allow_short: bool = False,
        lookahead_audit: bool = True,
        seed: int = 0,
        periods_per_year: int | None = None,
        execution_model: ExecutionModel | None = None,
    ):
        self.universe = data if isinstance(data, Universe) else Universe(data)
        self.data_feed = DataFeed(self.universe)
        self.strategy = strategy
        self.portfolio = Portfolio(initial_cash, allow_short)
        self.cost_model = cost_model or PercentCost()
        self.fill_model = fill_model or NextOpenFill()
        self.broker = Broker(self.portfolio, self.cost_model, self.fill_model)
        self.benchmark = benchmark
        self.trade_on = trade_on
        self.lookahead_audit = lookahead_audit
        self.periods_per_year = periods_per_year or 252
        self.execution_model = execution_model or NextBarExecution()
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        self.history = History()
        self.intrabar_pending: list[Order] = []

    def _context(self, ts, current):
        return BacktestContext(self, ts, current)

    def run(self) -> BacktestResult:
        if self.execution_model.is_intrabar:
            timeline = self.universe.frame(
                self.universe.instruments[0], self.execution_model.parent_tf
            ).index
            timeframe = self.execution_model.parent_tf
        else:
            timeline = self.data_feed.master_index
            timeframe = self.data_feed.primary_timeframe
        all_fills = []
        if len(timeline):
            self.strategy.on_start(self._context(timeline[0], {}))
        for offset, ts in enumerate(timeline):
            current = {}
            prices = {}
            for instrument in self.universe.instruments:
                if timeframe not in self.universe.timeframes(instrument):
                    continue
                bar = self.data_feed.bar_at(instrument, timeframe, ts)
                if bar is not None:
                    current[instrument] = bar
                    prices[instrument] = float(bar.close)
            ctx = self._context(ts, current)
            if self.execution_model.is_intrabar:
                self.strategy.on_bar(ctx)
                fills = self.execution_model.execute(self, ctx, ts, self.intrabar_pending)
                self.intrabar_pending.clear()
            else:
                fills = []
                for instrument, bar in current.items():
                    previous = bar
                    if offset > 0:
                        candidate = self.data_feed.bar_at(
                            instrument, timeframe, timeline[offset - 1]
                        )
                        if candidate is not None:
                            previous = candidate
                    fills.extend(self.broker.process_bar(instrument, previous, bar, ts))
                self.strategy.on_bar(ctx)
            for fill in fills:
                all_fills.append(fill)
                self.strategy.on_fill(fill, ctx)
            self.portfolio.mark(prices, ts)
            self.strategy.on_bar_close(ctx)
        if len(timeline):
            self.strategy.on_end(self._context(timeline[-1], {}))
        equity = self.portfolio.equity_frame
        if equity.empty:
            equity = pd.DataFrame(
                {
                    "equity": [self.portfolio.initial_cash],
                    "cash": [self.portfolio.cash],
                    "market_value": [0.0],
                }
            )
        fill_rows = [
            {
                "order_id": fill.order_id,
                "instrument": fill.instrument,
                "side": fill.side.value,
                "qty": fill.qty,
                "price": fill.price,
                "commission": fill.commission,
                "slippage": fill.slippage_cost,
                "ts": fill.ts,
                "tag": fill.tag,
                "exit_reason": fill.exit_reason,
                "sub_bar_ts": fill.sub_bar_ts,
                "sub_bar_index": fill.sub_bar_index,
            }
            for fill in all_fills
        ]
        positions = pd.DataFrame(
            [
                {
                    "instrument": name,
                    "qty": position.qty,
                    "avg_cost": position.avg_cost,
                    "realized_pnl": position.realized_pnl,
                }
                for name, position in self.portfolio.positions.items()
            ],
            columns=["instrument", "qty", "avg_cost", "realized_pnl"],
        )
        fills_frame = pd.DataFrame(
            fill_rows,
            columns=[
                "order_id",
                "instrument",
                "side",
                "qty",
                "price",
                "commission",
                "slippage",
                "ts",
                "tag",
                "exit_reason",
                "sub_bar_ts",
                "sub_bar_index",
            ],
        )
        series = equity.equity
        periodic = series.pct_change(fill_method=None).dropna()
        metrics = {
            "total_return": float(series.iloc[-1] / series.iloc[0] - 1) if len(series) > 1 else 0.0,
            "sharpe": sharpe(periodic) if len(periodic) else 0.0,
            "max_drawdown": max_drawdown(series) if len(series) > 1 else 0.0,
            "num_fills": len(fill_rows),
            "num_trades": len(self.portfolio.realized_history),
        }
        return BacktestResult(
            equity=equity,
            fills=fills_frame,
            positions=positions,
            metrics=metrics,
            config={
                "initial_cash": self.portfolio.initial_cash,
                "allow_short": self.portfolio.allow_short,
                "seed": self.seed,
                "cost_model": type(self.cost_model).__name__,
                "fill_model": type(self.fill_model).__name__,
                "execution_model": type(self.execution_model).__name__,
            },
            realized_history=self.portfolio.realized_history,
        )


for component_id, factory in {
    "cost.percent": PercentCost,
    "cost.fixed": FixedCost,
    "cost.tiered": TieredCost,
    "cost.min": MinCost,
    "cost.stamp_duty": StampDutyCost,
    "cost.zero": ZeroCost,
    "cost.maker_taker": MakerTakerCost,
    "cost.binance": BinanceCost,
    "fill.next_open": NextOpenFill,
    "fill.next_close": NextCloseFill,
    "fill.this_close": ThisCloseFill,
    "fill.vwap": VWAPFill,
    "fill.worst_price": WorstPriceFill,
    "fill.intrabar_limit": IntrabarLimitFill,
    "fill.intrabar": IntrabarLimitFill,
    "execution.next_bar": NextBarExecution,
    "execution.intrabar": IntrabarExecution,
}.items():
    COMPONENTS.register(component_id, factory)


def component_from_ref(reference: ComponentRef):
    return COMPONENTS.create(reference.id, **reference.params)
