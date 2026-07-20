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


def launch(code, arguments, cwd):
    return subprocess.Popen(
        [sys.executable, "-c", code, *arguments],
        cwd=cwd,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


def wait_ready(url):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=0.5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise TimeoutError(url)


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_authenticated_network_stack(tmp_path):
    storage_port, dispatcher_port = free_port(), free_port()
    storage_url = f"http://127.0.0.1:{storage_port}"
    dispatcher_url = f"http://127.0.0.1:{dispatcher_port}"
    storage = launch(
        "from stockstat_storage.cli import main; main()",
        [
            "--database-url",
            f"sqlite:///{tmp_path / 'market.db'}",
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--api-token",
            "client=data,artifacts",
            "--internal-token",
            "worker-secret",
            "--port",
            str(storage_port),
        ],
        tmp_path,
    )
    dispatcher = worker = None
    try:
        wait_ready(f"{storage_url}/health/ready")
        dispatcher = launch(
            "from stockstat_dispatcher.cli import main; main()",
            [
                "--database-url",
                f"sqlite:///{tmp_path / 'tasks.db'}",
                "--storage-url",
                storage_url,
                "--api-token",
                "client=jobs,cluster",
                "--internal-token",
                "worker-secret",
                "--port",
                str(dispatcher_port),
            ],
            tmp_path,
        )
        wait_ready(f"{dispatcher_url}/health/ready")
        worker = launch(
            "from stockstat_worker.cli import main; main()",
            [
                "--dispatcher-url",
                dispatcher_url,
                "--storage-url",
                storage_url,
                "--internal-token",
                "worker-secret",
                "--root",
                str(tmp_path / "worker"),
            ],
            tmp_path,
        )
        headers = {"Authorization": "Bearer client"}
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            response = httpx.get(f"{dispatcher_url}/v31/cluster", headers=headers)
            if response.json()["workers"]:
                break
            time.sleep(0.1)
        else:
            raise TimeoutError("worker registration")
        assert httpx.get(f"{dispatcher_url}/v31/cluster").status_code == 403
        session = StockStat.connect(dispatcher_url, storage_url=storage_url, token="client")
        try:
            session.data.ingest(
                "PAXG/USDT",
                source="synthetic",
                venue="synthetic",
                asset_class="crypto",
                timeframe="1h",
                start="2024-01-01",
                end="2024-01-02",
            )
            selector = session.data.selector(
                "PAXG/USDT",
                venue="synthetic",
                asset_class="crypto",
                timeframe="1h",
                start="2024-01-01",
                end="2024-01-02",
            )
            result = (
                session.indicators.submit("ma", selector, window=3).wait(timeout=60).as_indicator()
            )
            assert len(result.as_series()) == 24
        finally:
            session.close()
    finally:
        stop(worker)
        stop(dispatcher)
        stop(storage)
