from __future__ import annotations

from typing import Protocol

from stockstat_contracts import JobSpec


class ControlChannel(Protocol):
    def submit(self, spec: JobSpec, idempotency_key: str) -> str: ...
    def status(self, job_id: str) -> dict: ...
    def result(self, job_id: str) -> dict: ...
    def events(self, job_id: str, after: int = 0) -> list[dict]: ...
    def cancel(self, job_id: str, reason: str = "") -> str: ...


class EmbeddedControlChannel:
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    def submit(self, spec, idempotency_key):
        return self.dispatcher.submit(spec, idempotency_key)

    def status(self, job_id):
        return self.dispatcher.get_status(job_id)

    def result(self, job_id):
        return self.dispatcher.result(job_id)

    def events(self, job_id, after=0):
        return self.dispatcher.events(job_id, after)

    def cancel(self, job_id, reason=""):
        return self.dispatcher.cancel(job_id, reason)
