# StockStat V3.1 Usage

## Embedded

```python
from stockstat import StockStat

ss = StockStat.local(".stockstat-v31")
try:
    ss.data.ingest(
        "PAXG/USDT",
        source="synthetic",
        venue="synthetic",
        asset_class="crypto",
        timeframe="1d",
        start="2024-01-01",
        end="2024-06-01",
    )
    data = ss.data.selector(
        "PAXG/USDT",
        source="synthetic",
        venue="synthetic",
        asset_class="crypto",
        timeframe="1d",
        start="2024-01-01",
        end="2024-06-01",
    )
    ma20 = ss.indicators.ma(data, window=20)
finally:
    ss.close()
```

## Backtest

```python
strategy = ss.strategies.builtin(
    "ma-cross",
    "stockstat_kernel.builtins:moving_average_cross",
    {
        "instrument": "crypto:synthetic:PAXG/USDT",
        "timeframe": "1d",
        "short": 5,
        "long": 20,
        "quantity": 1.0,
    },
)
result = ss.backtests.run(data, strategy, initial_cash=10_000)
print(result.metrics)
print(result.equity.tail())
```

## Experiments

```python
from stockstat_contracts import BacktestParameters

base = BacktestParameters(strategy=strategy, initial_cash=10_000)
search = ss.experiments.grid_search(
    data,
    base_backtest=base,
    parameter_space={"short": [3, 5, 8], "long": [15, 20, 30]},
).wait().as_table()
print(search.summary)
print(search.table.head())

simulation = ss.simulations.bootstrap(
    data, base_backtest=base, n_samples=1_000, shards=4, random_seed=42
).wait().as_table()

walk_forward = ss.validation.walk_forward(
    data,
    base_backtest=base,
    windows=[
        {"start": "2024-01-01T00:00:00Z", "end": "2024-03-01T00:00:00Z"},
        {"start": "2024-03-01T00:00:00Z", "end": "2024-06-01T00:00:00Z"},
    ],
).wait().as_table()
```

## Network

```powershell
stockstat-storage --database-url sqlite:///market.db --artifact-root .stockstat-v31/artifacts
stockstat-dispatcher --database-url sqlite:///tasks.db --storage-url http://127.0.0.1:8101
stockstat-worker --dispatcher-url http://127.0.0.1:8100 --storage-url http://127.0.0.1:8101
```

```python
ss = StockStat.connect(
    "http://127.0.0.1:8100",
    storage_url="http://127.0.0.1:8101",
    token="client-token",
)
```

## DSL And Migration

```python
query = ss.dsl.compile(
    "SELECT close, ma(close, 20) AS ma20 "
    "FROM ohlcv('PAXG/USDT','1d','2024-01-01','2024-06-01')"
)
```

```powershell
stockstat migrate-scan old_project
stockstat strategy-package strategy.py strategy:build strategy.zip
stockstat strategy-verify strategy.zip --trusted-key PUBLIC_KEY_HEX
```

See `DEPLOYMENT.md` and `OPERATIONS.md` for production configuration.
