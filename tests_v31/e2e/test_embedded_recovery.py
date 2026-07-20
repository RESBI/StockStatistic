import pandas as pd
from stockstat import StockStat


def test_completed_job_survives_local_runtime_restart(tmp_path):
    root = tmp_path / "runtime"
    first = StockStat.local(root)
    try:
        frame = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0, 5.0]})
        job = first.indicators.submit("ma", frame, window=2)
        job.wait(timeout=30)
        job_id = job.id
    finally:
        first.close()
    second = StockStat.local(root)
    try:
        assert second._control.status(job_id)["state"] == "succeeded"
        result = second._control.result(job_id)
        assert result["result_schema"] == "stockstat.result.indicator/1"
    finally:
        second.close()
