from datetime import UTC, datetime, timedelta

import pytest
from stockstat_contracts import (
    ArtifactRef,
    DatasetInput,
    DatasetSelector,
    DatasetSnapshotManifest,
    InstrumentRef,
    JobSpec,
    OperationSpec,
    SourcePolicy,
    new_id,
)
from stockstat_contracts.time import utc_now
from stockstat_dispatcher import DispatcherService, SQLiteTaskStore, StaleAttemptError


class Snapshots:
    def __init__(self):
        self.reference = ArtifactRef(
            artifact_id=new_id(),
            kind="market_data_snapshot",
            media_type="application/vnd.apache.arrow.stream",
            codec="arrow-ipc-stream",
            size_bytes=10,
            sha256="a" * 64,
            schema_ref="stockstat.market.ohlcv/1",
            locator="artifact://sha256/" + "a" * 64,
        )

    def resolve(self, binding):
        return DatasetSnapshotManifest(
            dataset_snapshot_id=new_id(),
            selector_digest="b" * 64,
            resolved_instruments=binding.dataset.instruments,
            timeframe=binding.dataset.timeframe,
            resolved_start=binding.dataset.start,
            resolved_end=binding.dataset.end,
            row_count=10,
            schema_ref="stockstat.market.ohlcv/1",
            artifact=self.reference,
            created_at=utc_now(),
            sha256=self.reference.sha256,
        )


def job_spec():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    instrument = InstrumentRef(asset_class="crypto", symbol="PAXG/USDT", venue="binance")
    return JobSpec(
        name="MA",
        operation=OperationSpec(
            capability_id="finance.indicator.compute",
            capability_version="1.0",
            parameters={"indicator": "ma", "arguments": {"window": 5}},
            result_schema="stockstat.result.indicator/1",
        ),
        inputs=(
            DatasetInput(
                name="market_data",
                dataset=DatasetSelector(
                    instruments=(instrument,),
                    timeframe="1h",
                    start=start,
                    end=start + timedelta(days=1),
                    source_policy=SourcePolicy(mode="exact", source="synthetic"),
                ),
            ),
        ),
    )


def service(tmp_path):
    store = SQLiteTaskStore(tmp_path / "tasks.db")
    store.initialize()
    return DispatcherService(store, Snapshots())


def worker(service):
    worker_id, session_id = new_id(), new_id()
    capabilities = [
        {
            "capability_id": "finance.indicator.compute",
            "versions": ["1.0"],
            "executor_roles": ["execute", "reduce"],
        }
    ]
    service.register_worker(
        worker_id,
        session_id,
        capabilities,
        {
            "cpu_cores": 2,
            "memory_bytes": 2 * 1024**3,
            "scratch_bytes": 10 * 1024**3,
            "gpu": {"count": 0, "memory_bytes": 0},
        },
    )
    return worker_id, session_id, capabilities


def test_submit_is_idempotent_and_persists_events(tmp_path):
    dispatcher = service(tmp_path)
    first = dispatcher.submit(job_spec(), "same-key")
    second = dispatcher.submit(job_spec(), "same-key")
    assert first == second
    assert dispatcher.get_status(first)["state"] == "queued"
    assert [event["event_type"] for event in dispatcher.events(first)] == [
        "job.accepted",
        "job.queued",
    ]


def test_lease_complete_and_restart_recovery(tmp_path):
    dispatcher = service(tmp_path)
    job_id = dispatcher.submit(job_spec(), "complete-key")
    worker_id, session_id, capabilities = worker(dispatcher)
    lease = dispatcher.claim(worker_id, session_id, capabilities)[0]
    dispatcher.start(lease.attempt_id, lease.lease_token, session_id)
    dispatcher.complete(
        lease.attempt_id,
        lease.lease_token,
        session_id,
        new_id(),
        {
            "result_schema": "stockstat.result.indicator/1",
            "summary": {"indicator": "ma"},
            "artifacts": {},
        },
    )
    restarted = DispatcherService(dispatcher.store, Snapshots())
    assert restarted.get_status(job_id)["state"] == "succeeded"
    assert restarted.result(job_id)["summary"]["indicator"] == "ma"


def test_expired_attempt_is_fenced_and_retried(tmp_path):
    dispatcher = service(tmp_path)
    dispatcher.submit(job_spec(), "retry-key")
    worker_id, session_id, capabilities = worker(dispatcher)
    first = dispatcher.claim(worker_id, session_id, capabilities, lease_ttl_seconds=0.01)[0]
    import time

    time.sleep(0.03)
    assert dispatcher.reap_expired() == 1
    second = dispatcher.claim(worker_id, session_id, capabilities)[0]
    assert second.lease_generation == first.lease_generation + 1
    with pytest.raises(StaleAttemptError):
        dispatcher.complete(
            first.attempt_id,
            first.lease_token,
            session_id,
            new_id(),
            {"result_schema": "stockstat.result.indicator/1", "artifacts": {}},
        )
