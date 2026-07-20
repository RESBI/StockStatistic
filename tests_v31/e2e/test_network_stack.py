from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

import httpx
from stockstat import StockStat


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_ready(url, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=0.5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise TimeoutError(f"service did not become ready: {url}")


def launch(code, arguments, cwd):
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.Popen(
        [sys.executable, "-c", code, *arguments],
        cwd=cwd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_real_process_network_stack(tmp_path):
    storage_port = free_port()
    dispatcher_port = free_port()
    storage_url = f"http://127.0.0.1:{storage_port}"
    dispatcher_url = f"http://127.0.0.1:{dispatcher_port}"
    storage = launch(
        "from stockstat_storage.cli import main; main()",
        [
            "--database-url",
            f"sqlite:///{tmp_path / 'market.db'}",
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--port",
            str(storage_port),
        ],
        tmp_path,
    )
    dispatcher = worker = None
    try:
        wait_ready(f"{storage_url}/v31/meta")
        dispatcher = launch(
            "from stockstat_dispatcher.cli import main; main()",
            [
                "--database-url",
                f"sqlite:///{tmp_path / 'tasks.db'}",
                "--storage-url",
                storage_url,
                "--port",
                str(dispatcher_port),
            ],
            tmp_path,
        )
        wait_ready(f"{dispatcher_url}/v31/meta")
        worker = launch(
            "from stockstat_worker.cli import main; main()",
            [
                "--dispatcher-url",
                dispatcher_url,
                "--storage-url",
                storage_url,
                "--root",
                str(tmp_path / "worker"),
            ],
            tmp_path,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            cluster = httpx.get(f"{dispatcher_url}/v31/cluster", timeout=1).json()
            if cluster["workers"]:
                break
            time.sleep(0.1)
        else:
            raise TimeoutError("worker did not register")

        session = StockStat.connect(dispatcher_url, storage_url=storage_url)
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
            result = job.wait(timeout=60).as_indicator()
            assert len(result.as_series()) == 48
            assert job.events()[-1]["event_type"] == "job.succeeded"
        finally:
            session.close()
    finally:
        if worker:
            stop(worker)
        if dispatcher:
            stop(dispatcher)
        stop(storage)
