from stockstat.dsl import DSLCompiler
from stockstat.migration import report
from stockstat.strategy_package import package_module, verify_package


def test_dsl_compiles_selector_and_indicators():
    query = DSLCompiler().compile(
        "SELECT close, ma(close, 20) AS ma20, rsi(close, 14) AS rsi "
        "FROM ohlcv('PAXG/USDT','1d','2024-01-01','2024-02-01') LIMIT 30"
    )
    assert query.selector.instruments[0].symbol == "PAXG/USDT"
    assert [item["name"] for item in query.indicators] == ["ma", "rsi"]
    assert query.limit == 30


def test_migration_scanner_reports_legacy_and_dynamic_strategy(tmp_path):
    source = tmp_path / "legacy.py"
    source.write_text(
        "client = StockStatClient()\nstrategy = lambda ctx: None\nclient.run_dsl('x')\n",
        encoding="utf-8",
    )
    payload = report(source)
    codes = {finding["code"] for finding in payload["findings"]}
    assert "LEGACY_STOCKSTATCLIENT" in codes
    assert "STRATEGY_LAMBDA" in codes
    assert "LEGACY_ATTRIBUTE_RUN_DSL" in codes


def test_strategy_package_sign_and_tamper_detection(tmp_path):
    module = tmp_path / "strategy.py"
    module.write_text("def build(config):\n    return config\n", encoding="utf-8")
    package = tmp_path / "strategy.zip"
    manifest = package_module(module, "strategy:build", package)
    assert verify_package(package)["sha256"] == manifest["sha256"]
