import os
import threading
import uuid

import pytest
from stockstat_dispatcher import DispatcherService, PostgresTaskStore

from .test_dispatcher import Snapshots, job_spec, worker


@pytest.mark.postgres
def test_two_dispatchers_claim_each_work_unit_once():
    url = os.environ.get("STOCKSTAT_V31_POSTGRES_URL")
    if not url:
        pytest.skip("STOCKSTAT_V31_POSTGRES_URL is not set")
    first = DispatcherService(PostgresTaskStore(url), Snapshots())
    second = DispatcherService(PostgresTaskStore(url), Snapshots())
    first.store.initialize()
    job_id = first.submit(job_spec(), f"ha-{uuid.uuid4().hex}")
    first_worker = worker(first)
    second_worker = worker(second)
    leases = []
    barrier = threading.Barrier(2)

    def claim(service, worker_info):
        barrier.wait()
        leases.extend(service.claim(*worker_info))

    threads = [
        threading.Thread(target=claim, args=(first, first_worker)),
        threading.Thread(target=claim, args=(second, second_worker)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(leases) == 1
    assert leases[0].work.job_id == job_id
