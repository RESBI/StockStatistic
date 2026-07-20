import os

from stockstat_kernel.backtest import Strategy


class CrashStrategy(Strategy):
    def on_bar(self, ctx):
        os._exit(17)


def build_strategy(config):
    return CrashStrategy()
