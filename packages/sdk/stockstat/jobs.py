from __future__ import annotations

import time

TERMINAL_STATES = {"succeeded", "failed", "cancelled", "expired"}


class JobHandle:
    def __init__(self, session, job_id: str):
        self.session = session
        self.id = job_id

    def status(self):
        return self.session._control.status(self.id)

    def wait(self, timeout: float | None = None, poll_interval: float = 0.05):
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            status = self.status()
            if status["state"] in TERMINAL_STATES:
                if status["state"] == "succeeded":
                    return JobResult(self.session, self.session._control.result(self.id))
                raise RuntimeError(f"job {self.id} ended as {status['state']}: {status['error']}")
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for job {self.id}")
            time.sleep(poll_interval)

    def result(self):
        return JobResult(self.session, self.session._control.result(self.id))

    def events(self, after=0):
        return self.session._control.events(self.id, after)

    def cancel(self, reason=""):
        return self.session._control.cancel(self.id, reason)


class JobResult:
    def __init__(self, session, manifest):
        self.session = session
        self.manifest = manifest

    @property
    def summary(self):
        return self.manifest.get("summary", {})

    def as_indicator(self):
        return IndicatorResult(self.session, self.manifest)

    def as_backtest(self):
        return BacktestResultView(self.session, self.manifest)

    def as_table(self):
        return TableResult(self.session, self.manifest)


class IndicatorResult(JobResult):
    @property
    def values(self):
        return self._table("values")

    def as_series(self):
        table = self.values
        columns = [column for column in table.columns if column != "ts"]
        if len(columns) != 1:
            raise ValueError("indicator result has multiple outputs")
        series = table.set_index("ts")[columns[0]]
        return series

    def _table(self, name):
        return self.session._read_table(self.manifest["artifacts"][name])


class BacktestResultView(JobResult):
    @property
    def metrics(self):
        return self.summary.get("metrics", self.summary)

    @property
    def equity(self):
        return self.session._read_table(self.manifest["artifacts"]["equity"])

    @property
    def fills(self):
        return self.session._read_table(self.manifest["artifacts"]["fills"])

    @property
    def positions(self):
        return self.session._read_table(self.manifest["artifacts"]["positions"])


class TableResult(JobResult):
    @property
    def table(self):
        if not self.manifest["artifacts"]:
            return None
        name = next(iter(self.manifest["artifacts"]))
        return self.session._read_table(self.manifest["artifacts"][name])
