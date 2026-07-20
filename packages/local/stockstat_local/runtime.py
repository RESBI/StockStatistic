from __future__ import annotations

import threading
from pathlib import Path

from stockstat.channels import EmbeddedControlChannel
from stockstat.session import StockStat
from stockstat_dispatcher import DispatcherService, SQLiteTaskStore
from stockstat_storage.artifacts import ArtifactService, LocalBlobStore
from stockstat_storage.ingestion import IngestionService, SyntheticSource
from stockstat_storage.repository import SQLiteStorageRepository
from stockstat_storage.snapshots import SnapshotService
from stockstat_worker import WorkerAgent


class LocalSnapshotCoordinator:
    def __init__(self, service):
        self.service = service

    def resolve(self, binding):
        return self.service.create(binding.dataset)


class LocalRuntime:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.repository = SQLiteStorageRepository(self.root / "market.db")
        self.repository.initialize()
        self.artifacts = ArtifactService(
            self.repository,
            LocalBlobStore(self.root / "artifacts"),
            self.root / "uploads",
        )
        self.snapshots = SnapshotService(self.repository, self.artifacts)
        self.ingestion = IngestionService(self.repository, {"synthetic": SyntheticSource()})
        self.task_store = SQLiteTaskStore(self.root / "tasks.db")
        self.task_store.initialize()
        self.dispatcher = DispatcherService(
            self.task_store, LocalSnapshotCoordinator(self.snapshots)
        )
        self.worker = WorkerAgent(self.dispatcher, self.artifacts, self.root / "worker")
        self.session = StockStat(EmbeddedControlChannel(self.dispatcher), self.artifacts, self)
        self._stop = threading.Event()
        self._reaper: threading.Thread | None = None

    def start(self):
        self.worker.start()
        self._reaper = threading.Thread(
            target=self._reap_loop, name="stockstat-lease-reaper", daemon=True
        )
        self._reaper.start()
        return self

    def close(self):
        self._stop.set()
        self.worker.stop()
        if self._reaper:
            self._reaper.join(timeout=2)

    def _reap_loop(self):
        while not self._stop.wait(1):
            self.dispatcher.reap_expired()
