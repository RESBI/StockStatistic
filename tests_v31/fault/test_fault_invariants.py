from datetime import UTC, datetime, timedelta

import pytest
from stockstat_contracts import (
    ArtifactRef,
    DatasetInput,
    DatasetSelector,
    DatasetSnapshotManifest,
    ExecutionPolicy,
    InstrumentRef,
    JobSpec,
    OperationSpec,
    RetryBackoff,
    SourcePolicy,
    new_id,
)
from stockstat_contracts.time import utc_now
from stockstat_dispatcher import DispatcherService, SQLiteTaskStore, StaleAttemptError


class Snapshots:
    def resolve(self, binding):
        reference = ArtifactRef(
            artifact_id=new_id(),
            kind="market_data_snapshot",
            media_type="application/vnd.apache.arrow.stream",
            codec="arrow-ipc-stream",
            size_bytes=1,
            sha256="a" * 64,
            schema_ref="stockstat.market.ohlcv/1",
            locator="artifact://sha256/" + "a" * 64,
        )
        return DatasetSnapshotManifest(
            dataset_snapshot_id=new_id(),
            selector_digest="b" * 64,
            resolved_instruments=binding.dataset.instruments,
            timeframe=binding.dataset.timeframe,
            resolved_start=binding.dataset.start,
            resolved_end=binding.dataset.end,
            row_count=1,
            schema_ref="stockstat.market.ohlcv/1",
            artifact=reference,
            created_at=utc_now(),
            sha256=reference.sha256,
        )


def spec(max_attempts=2):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return JobSpec(
        name="fault",
        operation=OperationSpec(
            capability_id="finance.indicator.compute",
            parameters={"indicator": "ma", "arguments": {"window": 2}},
            result_schema="stockstat.result.indicator/1",
        ),
        inputs=(
            DatasetInput(
                name="input",
                dataset=DatasetSelector(
                    instruments=(
                        InstrumentRef(asset_class="crypto", symbol="PAXG/USDT", venue="binance"),
                    ),
                    timeframe="1h",
                    start=start,
                    end=start + timedelta(days=1),
                    source_policy=SourcePolicy(mode="exact", source="synthetic"),
                ),
            ),
        ),
        execution=ExecutionPolicy(
            max_attempts=max_attempts,
            retry_backoff=RetryBackoff(initial_seconds=0),
        ),
    )


def setup(tmp_path, max_attempts=2):
    store = SQLiteTaskStore(tmp_path / "tasks.db")
    store.initialize()
    service = DispatcherService(store, Snapshots())
    job_id = service.submit(spec(max_attempts), new_id())
    worker_id, session_id = new_id(), new_id()
    capabilities = [
        {
            "capability_id": "finance.indicator.compute",
            "versions": ["1.0"],
            "executor_roles": ["execute"],
        }
    ]
    service.register_worker(
        worker_id,
        session_id,
        capabilities,
        {
            "cpu_cores": 1,
            "memory_bytes": 2 * 1024**3,
            "scratch_bytes": 10 * 1024**3,
            "gpu": {"count": 0, "memory_bytes": 0},
        },
    )
    return service, job_id, worker_id, session_id, capabilities


def test_terminal_attempt_cannot_be_replayed_with_new_completion_id(tmp_path):
    service, job_id, worker_id, session_id, capabilities = setup(tmp_path)
    lease = service.claim(worker_id, session_id, capabilities)[0]
    service.complete(
        lease.attempt_id,
        lease.lease_token,
        session_id,
        new_id(),
        {"result_schema": "stockstat.result.indicator/1", "summary": {}, "artifacts": {}},
    )
    with pytest.raises(StaleAttemptError, match="ATTEMPT_TERMINAL"):
        service.complete(
            lease.attempt_id,
            lease.lease_token,
            session_id,
            new_id(),
            {"result_schema": "stockstat.result.indicator/1", "summary": {}, "artifacts": {}},
        )
    assert service.get_status(job_id)["state"] == "succeeded"


def test_lease_expiry_stops_at_retry_budget(tmp_path):
    service, job_id, worker_id, session_id, capabilities = setup(tmp_path, max_attempts=1)
    service.claim(worker_id, session_id, capabilities, lease_ttl_seconds=0.01)
    import time

    time.sleep(0.03)
    assert service.reap_expired() == 1
    status = service.get_status(job_id)
    assert status["state"] == "failed"
    assert status["error"]["code"] == "LEASE_EXPIRED"


def test_draining_worker_cannot_claim_new_work(tmp_path):
    service, _, worker_id, session_id, capabilities = setup(tmp_path)
    service.set_worker_state(worker_id, "draining")
    assert service.claim(worker_id, session_id, capabilities) == []
