import os
import uuid

import pytest
from stockstat_dispatcher import DispatcherService, PostgresTaskStore

from .test_dispatcher import Snapshots, job_spec, worker


@pytest.mark.postgres
def test_postgres_dispatcher_store_round_trip():
    url = os.environ.get("STOCKSTAT_V31_POSTGRES_URL")
    if not url:
        pytest.skip("STOCKSTAT_V31_POSTGRES_URL is not set")
    store = PostgresTaskStore(url)
    store.initialize()
    dispatcher = DispatcherService(store, Snapshots())
    run_id = uuid.uuid4().hex
    job_id = dispatcher.submit(job_spec(), f"p4-postgres-dispatcher-{run_id}")
    worker_id, session_id, capabilities = worker(dispatcher)
    lease = dispatcher.claim(worker_id, session_id, capabilities)[0]
    dispatcher.start(lease.attempt_id, lease.lease_token, session_id)
    dispatcher.complete(
        lease.attempt_id,
        lease.lease_token,
        session_id,
        f"p4-postgres-complete-{run_id}",
        {
            "result_schema": "stockstat.result.indicator/1",
            "summary": {"store": "postgres"},
            "artifacts": {},
        },
    )
    assert dispatcher.get_status(job_id)["state"] == "succeeded"
