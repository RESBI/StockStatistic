from __future__ import annotations

import shutil
import threading
from pathlib import Path

import psutil
from stockstat_contracts import ArtifactRef, new_id

from .cache import ArtifactCache
from .execution import ProcessSupervisor

DEFAULT_CAPABILITIES = [
    {
        "capability_id": "finance.indicator.compute",
        "versions": ["1.0"],
        "executor_roles": ["execute", "reduce"],
    },
    {
        "capability_id": "finance.timeseries.analyze",
        "versions": ["1.0"],
        "executor_roles": ["execute", "reduce"],
    },
    {"capability_id": "finance.backtest.run", "versions": ["1.0"], "executor_roles": ["execute"]},
    {
        "capability_id": "finance.experiment.search",
        "versions": ["1.0"],
        "executor_roles": ["execute", "reduce"],
    },
    {
        "capability_id": "finance.experiment.batch",
        "versions": ["1.0"],
        "executor_roles": ["execute", "reduce"],
    },
    {
        "capability_id": "finance.simulation.resample",
        "versions": ["1.0"],
        "executor_roles": ["execute", "reduce"],
    },
    {
        "capability_id": "finance.validation.walk_forward",
        "versions": ["1.0"],
        "executor_roles": ["execute", "reduce"],
    },
]


class WorkerAgent:
    def __init__(
        self,
        dispatcher,
        artifacts,
        root: str | Path,
        worker_id: str | None = None,
        capabilities=None,
    ):
        self.dispatcher = dispatcher
        self.artifacts = artifacts
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.worker_id = worker_id or self._load_identity()
        self.session_id = new_id()
        self.capabilities = capabilities or DEFAULT_CAPABILITIES
        self.cache = ArtifactCache(self.root / "cache")
        self.supervisor = ProcessSupervisor(self.root / "scratch")
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _load_identity(self):
        identity_path = self.root / "worker-id"
        if identity_path.exists():
            return identity_path.read_text(encoding="ascii").strip()
        worker_id = new_id()
        identity_path.write_text(worker_id, encoding="ascii")
        return worker_id

    def resources(self):
        return {
            "cpu_cores": psutil.cpu_count(logical=True) or 1,
            "memory_bytes": psutil.virtual_memory().total,
            "scratch_bytes": shutil.disk_usage(self.root).free,
        }

    def start(self):
        self.dispatcher.register_worker(
            self.worker_id, self.session_id, self.capabilities, self.resources()
        )
        self._thread = threading.Thread(target=self.run, name="stockstat-worker", daemon=True)
        self._thread.start()
        return self

    def run(self):
        while not self._stop.is_set():
            leases = self.dispatcher.claim(
                self.worker_id,
                self.session_id,
                self.capabilities,
                max_items=1,
                wait_seconds=0.2,
            )
            if not leases:
                continue
            self.execute(leases[0])

    def execute(self, lease):
        renew_stop = threading.Event()
        renew_thread = threading.Thread(
            target=self._renew_lease,
            args=(lease, renew_stop),
            name=f"stockstat-renew-{lease.attempt_id}",
            daemon=True,
        )
        try:
            self.dispatcher.start(lease.attempt_id, lease.lease_token, self.session_id)
            renew_thread.start()
            input_paths = [
                self.cache.resolve(reference, self.artifacts) for reference in lease.work.inputs
            ]
            result = self.supervisor.execute(lease, input_paths)
            if not result.success:
                self.dispatcher.fail(
                    lease.attempt_id,
                    lease.lease_token,
                    self.session_id,
                    new_id(),
                    result.error,
                )
                return
            references: dict[str, ArtifactRef] = {}
            for name, path_text in (result.files or {}).items():
                path = Path(path_text)
                references[name] = self.artifacts.commit_file(
                    path,
                    kind="work_result",
                    media_type="application/vnd.apache.arrow.stream",
                    codec="arrow-ipc-stream",
                    schema_ref=f"stockstat.result.{name}/1",
                    metadata={
                        "job_id": lease.work.job_id,
                        "work_unit_id": lease.work.work_unit_id,
                        "attempt_id": lease.attempt_id,
                        **(
                            {"owner": lease.work.metadata["owner"]}
                            if lease.work.metadata.get("owner")
                            else {}
                        ),
                    },
                )
            manifest = dict(result.manifest or {})
            manifest["artifacts"] = {
                name: reference.model_dump(mode="json") for name, reference in references.items()
            }
            manifest.setdefault(
                "summary",
                {
                    key: value
                    for key, value in manifest.items()
                    if key not in {"artifacts", "result_schema"}
                },
            )
            self.dispatcher.complete(
                lease.attempt_id,
                lease.lease_token,
                self.session_id,
                new_id(),
                manifest,
            )
            for path_text in (result.files or {}).values():
                path = Path(path_text)
                shutil.rmtree(path.parent.parent, ignore_errors=True)
        except Exception as exc:
            try:
                self.dispatcher.fail(
                    lease.attempt_id,
                    lease.lease_token,
                    self.session_id,
                    new_id(),
                    {
                        "code": "WORKER_FAILURE",
                        "category": "infrastructure",
                        "message": str(exc),
                        "retryable": True,
                    },
                )
            except Exception:
                pass
        finally:
            renew_stop.set()
            if renew_thread.is_alive():
                renew_thread.join(timeout=2)

    def _renew_lease(self, lease, stop):
        interval = max(0.1, float(lease.renew_after_seconds))
        while not stop.wait(interval):
            try:
                response = self.dispatcher.renew(
                    lease.attempt_id,
                    lease.lease_token,
                    self.session_id,
                    lease_ttl_seconds=max(3, int(interval * 3)),
                )
                if response.get("action") == "cancel":
                    return
            except Exception:
                return

    def stop(self, timeout=10):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
