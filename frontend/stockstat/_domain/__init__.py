"""StockStat v2.0 — Domain layer (Layer 1).

Financial-domain logic built on top of :mod:`stockstat._core`. This
package provides:

* Domain models (OHLCV, Symbol, Quote, Trade)
* Data-source adapter plugins (registered to PluginRegistry)
* Indicator plugins (registered to PluginRegistry)
* Backtest component plugins (Cost/Fill/Execution models)
* Scheduler

The actual computation code remains in the top-level ``indicators/``,
``backtest/``, ``dsl/`` packages (the v1.7 compatibility layer). The
``_domain`` layer provides the plugin protocol wrappers and registration
that bridge v1.7 code to the v2.0 plugin registry.
"""
from . import models, sources, indicators, backtest, scheduler

__all__ = ["models", "sources", "indicators", "backtest", "scheduler"]
