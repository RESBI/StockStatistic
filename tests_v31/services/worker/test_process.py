from stockstat import StockStat


def test_embedded_indicator_runs_through_job_and_spawn_worker(tmp_path):
    session = StockStat.local(tmp_path / "runtime")
    try:
        session.data.ingest(
            "PAXG/USDT",
            source="synthetic",
            venue="synthetic",
            asset_class="crypto",
            timeframe="1h",
            start="2024-01-01",
            end="2024-01-03",
        )
        selector = session.data.selector(
            "PAXG/USDT",
            venue="synthetic",
            asset_class="crypto",
            timeframe="1h",
            start="2024-01-01",
            end="2024-01-03",
        )
        job = session.indicators.submit("ma", selector, window=5)
        result = job.wait(timeout=30).as_indicator()
        assert len(result.as_series()) == 48
        events = [event["event_type"] for event in job.events()]
        assert events[0:2] == ["job.accepted", "job.queued"]
        assert "work.leased" in events
        assert events[-1] == "job.succeeded"
    finally:
        session.close()


def test_embedded_backtest_loads_strategy_ref_in_child(tmp_path):
    session = StockStat.local(tmp_path / "runtime")
    try:
        session.data.ingest(
            "PAXG/USDT",
            source="synthetic",
            venue="synthetic",
            asset_class="crypto",
            timeframe="1d",
            start="2024-01-01",
            end="2024-03-01",
        )
        selector = session.data.selector(
            "PAXG/USDT",
            venue="synthetic",
            asset_class="crypto",
            timeframe="1d",
            start="2024-01-01",
            end="2024-03-01",
        )
        instrument_key = "crypto:synthetic:PAXG/USDT"
        strategy = session.strategies.builtin(
            "buy-and-hold",
            "stockstat_kernel.builtins:buy_and_hold",
            {"instrument": instrument_key, "quantity": 1.0},
        )
        result = session.backtests.run(selector, strategy, initial_cash=10_000, random_seed=7)
        assert result.metrics["num_fills"] == 1
        assert len(result.equity) == 60
        assert list(result.fills.instrument) == [instrument_key]
    finally:
        session.close()
