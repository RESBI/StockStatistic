import time

import pytest
from stockstat_contracts import JobSpec, OperationSpec
from stockstat_dispatcher import DispatcherService, SQLiteTaskStore


class NoSnapshots:
    def resolve(self, _):
        raise AssertionError("no dataset input expected")


@pytest.mark.performance
def test_sqlite_submit_status_baseline(tmp_path):
    store = SQLiteTaskStore(tmp_path / "tasks.db")
    store.initialize()
    service = DispatcherService(store, NoSnapshots())
    spec = JobSpec(
        name="capacity",
        operation=OperationSpec(
            capability_id="finance.indicator.compute",
            parameters={"indicator": "ma", "arguments": {"window": 2}},
        ),
    )
    started = time.perf_counter()
    job_ids = [service.submit(spec, f"capacity-{index}") for index in range(100)]
    submit_seconds = time.perf_counter() - started
    started = time.perf_counter()
    for job_id in job_ids:
        assert service.get_status(job_id)["state"] == "queued"
    status_seconds = time.perf_counter() - started
    assert submit_seconds < 5
    assert status_seconds < 2
    metrics = service.autoscaling_metrics()
    assert metrics["queued_work_units"] == 100
    assert "stockstat_dispatcher_queued_work_units 100" in service.prometheus_metrics()
