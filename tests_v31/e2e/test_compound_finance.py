from stockstat import StockStat
from stockstat_contracts import BacktestParameters, ComponentRef


def setup(tmp_path):
    session = StockStat.local(tmp_path / "runtime")
    session.data.ingest(
        "PAXG/USDT",
        source="synthetic",
        venue="synthetic",
        asset_class="crypto",
        timeframe="1d",
        start="2024-01-01",
        end="2024-06-01",
    )
    selector = session.data.selector(
        "PAXG/USDT",
        venue="synthetic",
        asset_class="crypto",
        timeframe="1d",
        start="2024-01-01",
        end="2024-06-01",
    )
    strategy = session.strategies.builtin(
        "ma-cross",
        "stockstat_kernel.builtins:moving_average_cross",
        {
            "instrument": "crypto:synthetic:PAXG/USDT",
            "timeframe": "1d",
            "short": 3,
            "long": 12,
            "quantity": 1.0,
        },
    )
    base = BacktestParameters(
        strategy=strategy,
        initial_cash=10_000,
        allow_short=False,
        cost_model=ComponentRef(id="cost.zero"),
    )
    return session, selector, base


def test_search_fanout_and_reducer(tmp_path):
    session, selector, base = setup(tmp_path)
    try:
        result = (
            session.experiments.grid_search(
                selector,
                base_backtest=base,
                parameter_space={"short": [2, 3], "long": [8, 12]},
                objective={"metric": "total_return", "direction": "maximize"},
                batch_size=2,
            )
            .wait(timeout=90)
            .as_table()
        )
        assert result.summary["total_trials"] == 4
        assert len(result.table) == 4
        assert result.table.objective.is_monotonic_decreasing
    finally:
        session.close()


def test_simulation_shards_are_deterministic_and_complete(tmp_path):
    session, selector, base = setup(tmp_path)
    try:
        first = (
            session.simulations.bootstrap(
                selector,
                base_backtest=base,
                n_samples=12,
                shards=3,
                random_seed=42,
            )
            .wait(timeout=90)
            .as_table()
        )
        second = (
            session.simulations.bootstrap(
                selector,
                base_backtest=base,
                n_samples=12,
                shards=4,
                random_seed=42,
            )
            .wait(timeout=90)
            .as_table()
        )
        assert list(first.table.simulation_index) == list(range(12))
        assert list(first.table.total_return) == list(second.table.total_return)
    finally:
        session.close()
