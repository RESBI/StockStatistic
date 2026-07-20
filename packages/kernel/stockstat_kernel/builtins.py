from __future__ import annotations

from .backtest import Order, Strategy


class BuyAndHold(Strategy):
    def __init__(self, instrument: str, quantity: float = 1.0):
        self.instrument = instrument
        self.quantity = quantity
        self.submitted = False

    def on_bar(self, ctx):
        if not self.submitted:
            ctx.broker.submit(Order(self.instrument, "buy", self.quantity, tag="entry"))
            self.submitted = True


class MovingAverageCross(Strategy):
    def __init__(
        self,
        instrument: str,
        timeframe: str = "1d",
        short: int = 5,
        long: int = 20,
        quantity: float = 1.0,
    ):
        self.instrument = instrument
        self.timeframe = timeframe
        self.short = short
        self.long = long
        self.quantity = quantity

    def on_bar(self, ctx):
        frame = ctx.get(self.instrument, self.timeframe, lookback=self.long + 1)
        if len(frame) < self.long:
            return
        short_value = frame.close.iloc[-self.short :].mean()
        long_value = frame.close.iloc[-self.long :].mean()
        position = ctx.portfolio.get_position(self.instrument)
        if short_value > long_value and position.qty <= 0:
            if position.qty < 0:
                ctx.broker.submit(Order(self.instrument, "buy", abs(position.qty), tag="cover"))
            ctx.broker.submit(Order(self.instrument, "buy", self.quantity, tag="entry"))
        elif short_value < long_value and position.qty > 0:
            ctx.broker.submit(Order(self.instrument, "sell", position.qty, tag="exit"))


def buy_and_hold(config):
    return BuyAndHold(**config)


def moving_average_cross(config):
    return MovingAverageCross(**config)
