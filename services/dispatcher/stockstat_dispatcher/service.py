from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta

from stockstat_contracts import (
    ArtifactRef,
    AttemptState,
    JobResultManifest,
    JobSpec,
    JobState,
    WorkLease,
    WorkState,
    WorkUnitSpec,
    canonical_digest,
    new_id,
)
from stockstat_contracts.time import format_utc, utc_now

from .planners import DEFAULT_PLANNERS, PlannerRegistry
from .store import TaskStore, decode, encode, now_text


class StaleAttemptError(RuntimeError):
    pass


class IdempotencyConflictError(RuntimeError):
    pass


class DispatcherService:
    def __init__(self, store: TaskStore, snapshots, planners: PlannerRegistry | None = None):
        self.store = store
        self.snapshots = snapshots
        self.planners = planners or DEFAULT_PLANNERS
        self._condition = threading.Condition(store.lock)

    def submit(self, spec: JobSpec, idempotency_key: str, principal: str | None = None) -> str:
        if principal:
            spec = spec.model_copy(update={"tags": {**spec.tags, "stockstat.principal": principal}})
            idempotency_key = f"{principal}:{idempotency_key}"
        digest = canonical_digest(spec)
        with self.store.transaction() as tx:
            existing = tx.fetchone(
                "SELECT request_digest, job_id FROM idempotency_keys WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            if existing:
                if existing["request_digest"] != digest:
                    raise IdempotencyConflictError("IDEMPOTENCY_CONFLICT")
                return existing["job_id"]
            job_id = new_id()
            created_at = now_text()
            tx.execute(
                """INSERT INTO jobs (
                    job_id, spec_json, spec_digest, state, revision, priority,
                    max_attempts, created_at, deadline_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    spec.model_dump_json(),
                    digest,
                    JobState.PLANNING.value,
                    1,
                    spec.execution.priority,
                    spec.execution.max_attempts,
                    created_at,
                    format_utc(spec.execution.deadline_at) if spec.execution.deadline_at else None,
                ),
            )
            tx.execute(
                """INSERT INTO idempotency_keys
                    (idempotency_key, request_digest, job_id, created_at)
                    VALUES (?, ?, ?, ?)""",
                (idempotency_key, digest, job_id, created_at),
            )
            self._append_event(tx, job_id, "job.accepted", {"state": "planning"})
        try:
            plan = self.planners.get(
                spec.operation.capability_id, spec.operation.capability_version
            ).plan(job_id, spec, self.snapshots)
            with self.store.transaction() as tx:
                for stage in plan.stages:
                    tx.execute(
                        """INSERT INTO stages
                            (stage_id, job_id, name, position, state)
                            VALUES (?, ?, ?, ?, ?)""",
                        (stage.stage_id, job_id, stage.name, stage.position, "ready"),
                    )
                    for work in stage.work_units:
                        metadata = dict(work.metadata)
                        if principal:
                            metadata["owner"] = principal
                        work = work.model_copy(update={"metadata": metadata})
                        tx.execute(
                            """INSERT INTO work_units (
                                work_unit_id, job_id, stage_id, state, capability_id,
                                capability_version, executor_role, work_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                work.work_unit_id,
                                job_id,
                                stage.stage_id,
                                (
                                    WorkState.READY.value
                                    if stage.position == 0
                                    else WorkState.BLOCKED.value
                                ),
                                work.capability_id,
                                work.capability_version,
                                work.executor_role.value,
                                work.model_dump_json(),
                            ),
                        )
                tx.execute(
                    "UPDATE jobs SET state = ?, revision = revision + 1 WHERE job_id = ?",
                    (JobState.QUEUED.value, job_id),
                )
                self._append_event(tx, job_id, "job.queued", {"plan_digest": plan.digest})
        except Exception as exc:
            with self.store.transaction() as tx:
                tx.execute(
                    """UPDATE jobs SET state = ?, revision = revision + 1,
                       finished_at = ?, error_json = ? WHERE job_id = ?""",
                    (JobState.FAILED.value, now_text(), encode({"message": str(exc)}), job_id),
                )
                self._append_event(tx, job_id, "job.failed", {"message": str(exc)})
            raise
        with self._condition:
            self._condition.notify_all()
        return job_id

    def register_worker(self, worker_id, session_id, capabilities, resources):
        with self.store.transaction() as tx:
            tx.execute(
                """INSERT INTO workers (
                    worker_id, current_session_id, state, capabilities_json,
                    resources_json, last_heartbeat_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    current_session_id=excluded.current_session_id,
                    state=excluded.state,
                    capabilities_json=excluded.capabilities_json,
                    resources_json=excluded.resources_json,
                    last_heartbeat_at=excluded.last_heartbeat_at""",
                (
                    worker_id,
                    session_id,
                    "ready",
                    encode(capabilities),
                    encode(resources),
                    now_text(),
                ),
            )

    def claim(
        self, worker_id, session_id, capabilities, max_items=1, lease_ttl_seconds=60, wait_seconds=0
    ):
        deadline = time.monotonic() + wait_seconds
        while True:
            leases = self._claim_now(
                worker_id, session_id, capabilities, max_items, lease_ttl_seconds
            )
            if leases or wait_seconds <= 0 or time.monotonic() >= deadline:
                return leases
            with self._condition:
                self._condition.wait(timeout=min(0.25, max(0, deadline - time.monotonic())))

    def _claim_now(self, worker_id, session_id, capabilities, max_items, lease_ttl_seconds):
        supported = {
            (item["capability_id"], version, role)
            for item in capabilities
            for version in item["versions"]
            for role in item.get("executor_roles", ("execute",))
        }
        leases = []
        with self.store.transaction() as tx:
            worker = tx.fetchone(
                """SELECT current_session_id, state, resources_json
                   FROM workers WHERE worker_id = ?""",
                (worker_id,),
            )
            if not worker or worker["current_session_id"] != session_id:
                raise StaleAttemptError("WORKER_SESSION_STALE")
            if worker["state"] != "ready":
                return []
            tx.execute(
                "UPDATE workers SET last_heartbeat_at = ? WHERE worker_id = ?",
                (now_text(), worker_id),
            )
            worker_resources = decode(worker["resources_json"])
            rows = tx.fetchall(
                """SELECT w.*, j.priority FROM work_units w JOIN jobs j
                   ON j.job_id = w.job_id
                   WHERE w.state = ? AND (w.not_before IS NULL OR w.not_before <= ?)
                   AND j.state IN (?, ?)
                   ORDER BY j.priority DESC, w.work_unit_id ASC""",
                (WorkState.READY.value, now_text(), JobState.QUEUED.value, JobState.RUNNING.value),
            )
            for row in rows:
                if len(leases) >= max_items:
                    break
                if (
                    row["capability_id"],
                    row["capability_version"],
                    row["executor_role"],
                ) not in supported:
                    continue
                work_spec = _stored_model(WorkUnitSpec, row["work_json"])
                if not _resources_fit(work_spec.resources, worker_resources):
                    continue
                attempt_id = new_id()
                token = secrets.token_urlsafe(32)
                token_hash = _token_hash(token)
                generation = int(row["attempt_generation"]) + 1
                expires_at = utc_now() + timedelta(seconds=lease_ttl_seconds)
                updated = tx.execute(
                    """UPDATE work_units SET state = ?, attempt_generation = ?,
                       current_attempt_id = ? WHERE work_unit_id = ? AND state = ?""",
                    (
                        WorkState.LEASED.value,
                        generation,
                        attempt_id,
                        row["work_unit_id"],
                        WorkState.READY.value,
                    ),
                )
                if updated != 1:
                    continue
                tx.execute(
                    """INSERT INTO attempts (
                        attempt_id, work_unit_id, generation, worker_id,
                        worker_session_id, token_hash, state, lease_expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        attempt_id,
                        row["work_unit_id"],
                        generation,
                        worker_id,
                        session_id,
                        token_hash,
                        AttemptState.LEASED.value,
                        format_utc(expires_at),
                    ),
                )
                tx.execute(
                    """UPDATE jobs SET state = ?, revision = revision + 1,
                       started_at = COALESCE(started_at, ?) WHERE job_id = ?""",
                    (JobState.RUNNING.value, now_text(), row["job_id"]),
                )
                self._append_event(
                    tx,
                    row["job_id"],
                    "work.leased",
                    {"work_unit_id": row["work_unit_id"], "attempt_id": attempt_id},
                )
                leases.append(
                    WorkLease(
                        worker_id=worker_id,
                        worker_session_id=session_id,
                        attempt_id=attempt_id,
                        lease_generation=generation,
                        lease_token=token,
                        lease_expires_at=expires_at,
                        renew_after_seconds=max(1, lease_ttl_seconds / 3),
                        work=work_spec,
                    )
                )
        return leases

    def start(self, attempt_id, token, worker_session_id):
        with self.store.transaction() as tx:
            attempt, work = self._current_attempt(tx, attempt_id, token, worker_session_id)
            if attempt["state"] == AttemptState.RUNNING.value:
                return
            tx.execute(
                "UPDATE attempts SET state = ?, started_at = ? WHERE attempt_id = ?",
                (AttemptState.RUNNING.value, now_text(), attempt_id),
            )
            tx.execute(
                "UPDATE work_units SET state = ? WHERE work_unit_id = ?",
                (WorkState.RUNNING.value, work["work_unit_id"]),
            )
            self._append_event(tx, work["job_id"], "work.started", {"attempt_id": attempt_id})

    def renew(self, attempt_id, token, worker_session_id, lease_ttl_seconds=60, progress=None):
        with self.store.transaction() as tx:
            attempt, work = self._current_attempt(tx, attempt_id, token, worker_session_id)
            expires_at = utc_now() + timedelta(seconds=lease_ttl_seconds)
            tx.execute(
                "UPDATE attempts SET lease_expires_at = ? WHERE attempt_id = ?",
                (format_utc(expires_at), attempt_id),
            )
            tx.execute(
                """UPDATE workers SET last_heartbeat_at = ?
                   WHERE worker_id = ? AND current_session_id = ?""",
                (now_text(), attempt["worker_id"], worker_session_id),
            )
            job = tx.fetchone("SELECT state FROM jobs WHERE job_id = ?", (work["job_id"],))
            action = "cancel" if job["state"] == JobState.CANCELLING.value else "continue"
            if progress:
                self._append_event(tx, work["job_id"], "job.progress", progress)
            return {"lease_expires_at": expires_at, "action": action}

    def complete(self, attempt_id, token, worker_session_id, completion_id, result):
        with self.store.transaction() as tx:
            duplicate = tx.fetchone(
                "SELECT attempt_id FROM attempts WHERE completion_id = ?", (completion_id,)
            )
            if duplicate:
                return self.status_for_attempt(duplicate["attempt_id"])
            _, work = self._current_attempt(tx, attempt_id, token, worker_session_id)
            tx.execute(
                """UPDATE attempts SET state = ?, finished_at = ?, completion_id = ?,
                   result_json = ? WHERE attempt_id = ?""",
                (
                    AttemptState.SUCCEEDED.value,
                    now_text(),
                    completion_id,
                    encode(result),
                    attempt_id,
                ),
            )
            tx.execute(
                "UPDATE work_units SET state = ?, result_json = ? WHERE work_unit_id = ?",
                (WorkState.SUCCEEDED.value, encode(result), work["work_unit_id"]),
            )
            self._append_event(tx, work["job_id"], "work.succeeded", {"attempt_id": attempt_id})
            self._unlock_reducers(tx, work["job_id"])
            pending = tx.fetchone(
                """SELECT COUNT(*) count FROM work_units
                   WHERE job_id = ? AND state != ?""",
                (work["job_id"], WorkState.SUCCEEDED.value),
            )["count"]
            if pending == 0:
                spec_row = tx.fetchone(
                    "SELECT spec_json FROM jobs WHERE job_id = ?", (work["job_id"],)
                )
                spec = _stored_model(JobSpec, spec_row["spec_json"])
                manifest = JobResultManifest(
                    job_id=work["job_id"],
                    capability_id=spec.operation.capability_id,
                    capability_version=spec.operation.capability_version,
                    result_schema=result["result_schema"],
                    created_at=utc_now(),
                    summary=result.get("summary", {}),
                    artifacts=result.get("artifacts", {}),
                    reproducibility=result.get("reproducibility", {}),
                    warnings=tuple(result.get("warnings", ())),
                )
                tx.execute(
                    """UPDATE jobs SET state = ?, revision = revision + 1,
                       finished_at = ?, result_json = ? WHERE job_id = ?""",
                    (
                        JobState.SUCCEEDED.value,
                        now_text(),
                        manifest.model_dump_json(),
                        work["job_id"],
                    ),
                )
                self._append_event(
                    tx, work["job_id"], "job.succeeded", {"result_schema": manifest.result_schema}
                )
        return {"accepted": True, "job_state": self.get_status(work["job_id"])["state"]}

    def _unlock_reducers(self, tx, job_id):
        blocked = tx.fetchall(
            """SELECT w.*, s.position FROM work_units w JOIN stages s
               ON s.stage_id = w.stage_id
               WHERE w.job_id = ? AND w.state = ? AND w.executor_role = ?
               ORDER BY s.position""",
            (job_id, WorkState.BLOCKED.value, "reduce"),
        )
        for reducer in blocked:
            incomplete = tx.fetchone(
                """SELECT COUNT(*) count FROM work_units w JOIN stages s
                   ON s.stage_id = w.stage_id
                   WHERE w.job_id = ? AND s.position < ? AND w.state != ?""",
                (job_id, reducer["position"], WorkState.SUCCEEDED.value),
            )["count"]
            if incomplete:
                continue
            upstream = tx.fetchall(
                """SELECT w.result_json FROM work_units w JOIN stages s
                   ON s.stage_id = w.stage_id
                   WHERE w.job_id = ? AND s.position < ?
                   ORDER BY s.position, w.work_unit_id""",
                (job_id, reducer["position"]),
            )
            references = []
            for row in upstream:
                result = decode(row["result_json"]) or {}
                for reference in result.get("artifacts", {}).values():
                    references.append(ArtifactRef.model_validate(reference))
            work = _stored_model(WorkUnitSpec, reducer["work_json"])
            work = work.model_copy(update={"inputs": tuple(references)})
            tx.execute(
                """UPDATE work_units SET state = ?, work_json = ?
                   WHERE work_unit_id = ? AND state = ?""",
                (
                    WorkState.READY.value,
                    work.model_dump_json(),
                    reducer["work_unit_id"],
                    WorkState.BLOCKED.value,
                ),
            )
            self._append_event(
                tx,
                job_id,
                "stage.completed",
                {"unlocked_reducer": reducer["work_unit_id"]},
            )

    def fail(self, attempt_id, token, worker_session_id, failure_id, error):
        with self.store.transaction() as tx:
            duplicate = tx.fetchone(
                "SELECT attempt_id FROM attempts WHERE failure_id = ?", (failure_id,)
            )
            if duplicate:
                return self.status_for_attempt(duplicate["attempt_id"])
            attempt, work = self._current_attempt(tx, attempt_id, token, worker_session_id)
            spec = _stored_model(
                JobSpec,
                tx.fetchone("SELECT spec_json FROM jobs WHERE job_id = ?", (work["job_id"],))[
                    "spec_json"
                ],
            )
            retryable = bool(error.get("retryable"))
            retryable = retryable and int(attempt["generation"]) < spec.execution.max_attempts
            tx.execute(
                """UPDATE attempts SET state = ?, finished_at = ?, failure_id = ?,
                   error_json = ? WHERE attempt_id = ?""",
                (AttemptState.FAILED.value, now_text(), failure_id, encode(error), attempt_id),
            )
            if retryable:
                delay = min(
                    spec.execution.retry_backoff.max_seconds,
                    spec.execution.retry_backoff.initial_seconds
                    * spec.execution.retry_backoff.factor ** (int(attempt["generation"]) - 1),
                )
                not_before = utc_now() + timedelta(seconds=delay)
                tx.execute(
                    """UPDATE work_units SET state = ?, current_attempt_id = NULL,
                       not_before = ?, error_json = ? WHERE work_unit_id = ?""",
                    (
                        WorkState.READY.value,
                        format_utc(not_before),
                        encode(error),
                        work["work_unit_id"],
                    ),
                )
                self._append_event(
                    tx, work["job_id"], "work.retry_scheduled", {"attempt_id": attempt_id}
                )
            else:
                tx.execute(
                    """UPDATE work_units SET state = ?, error_json = ?
                       WHERE work_unit_id = ?""",
                    (WorkState.FAILED_TERMINAL.value, encode(error), work["work_unit_id"]),
                )
                tx.execute(
                    """UPDATE jobs SET state = ?, revision = revision + 1,
                       finished_at = ?, error_json = ? WHERE job_id = ?""",
                    (JobState.FAILED.value, now_text(), encode(error), work["job_id"]),
                )
                self._append_event(tx, work["job_id"], "job.failed", error)
        with self._condition:
            self._condition.notify_all()
        return {"retry_scheduled": retryable}

    def cancel(self, job_id, reason="", principal: str | None = None):
        with self.store.transaction() as tx:
            job = tx.fetchone("SELECT state, spec_json FROM jobs WHERE job_id = ?", (job_id,))
            if not job:
                raise LookupError("JOB_NOT_FOUND")
            self._authorize_job(job["spec_json"], principal)
            if job["state"] in {
                state.value
                for state in (
                    JobState.SUCCEEDED,
                    JobState.FAILED,
                    JobState.CANCELLED,
                    JobState.EXPIRED,
                )
            }:
                return job["state"]
            tx.execute(
                "UPDATE jobs SET state = ?, revision = revision + 1 WHERE job_id = ?",
                (JobState.CANCELLING.value, job_id),
            )
            tx.execute(
                "UPDATE work_units SET state = ? WHERE job_id = ? AND state IN (?, ?)",
                (WorkState.CANCELLED.value, job_id, WorkState.READY.value, WorkState.BLOCKED.value),
            )
            active = tx.fetchone(
                "SELECT COUNT(*) count FROM work_units WHERE job_id = ? AND state IN (?, ?)",
                (job_id, WorkState.LEASED.value, WorkState.RUNNING.value),
            )["count"]
            if active == 0:
                tx.execute(
                    """UPDATE jobs SET state = ?, revision = revision + 1,
                       finished_at = ? WHERE job_id = ?""",
                    (JobState.CANCELLED.value, now_text(), job_id),
                )
            self._append_event(tx, job_id, "job.cancelled", {"reason": reason})
        return self.get_status(job_id)["state"]

    def reap_expired(self):
        count = 0
        with self.store.transaction() as tx:
            attempts = tx.fetchall(
                """SELECT a.*, w.job_id, j.max_attempts FROM attempts a
                   JOIN work_units w ON w.work_unit_id = a.work_unit_id
                   JOIN jobs j ON j.job_id = w.job_id
                   WHERE a.state IN (?, ?) AND a.lease_expires_at < ?""",
                (AttemptState.LEASED.value, AttemptState.RUNNING.value, now_text()),
            )
            for attempt in attempts:
                work = tx.fetchone(
                    "SELECT current_attempt_id FROM work_units WHERE work_unit_id = ?",
                    (attempt["work_unit_id"],),
                )
                if work["current_attempt_id"] != attempt["attempt_id"]:
                    continue
                updated = tx.execute(
                    """UPDATE attempts SET state = ?, finished_at = ?
                       WHERE attempt_id = ? AND state IN (?, ?)""",
                    (
                        AttemptState.EXPIRED.value,
                        now_text(),
                        attempt["attempt_id"],
                        AttemptState.LEASED.value,
                        AttemptState.RUNNING.value,
                    ),
                )
                if updated != 1:
                    continue
                if int(attempt["generation"]) >= int(attempt["max_attempts"]):
                    error = {
                        "code": "LEASE_EXPIRED",
                        "category": "infrastructure",
                        "message": "attempt lease expired and retry budget is exhausted",
                        "retryable": False,
                    }
                    tx.execute(
                        """UPDATE work_units SET state = ?, error_json = ?
                           WHERE work_unit_id = ? AND current_attempt_id = ?""",
                        (
                            WorkState.FAILED_TERMINAL.value,
                            encode(error),
                            attempt["work_unit_id"],
                            attempt["attempt_id"],
                        ),
                    )
                    tx.execute(
                        """UPDATE jobs SET state = ?, revision = revision + 1,
                           finished_at = ?, error_json = ? WHERE job_id = ?""",
                        (JobState.FAILED.value, now_text(), encode(error), attempt["job_id"]),
                    )
                    self._append_event(tx, attempt["job_id"], "job.failed", error)
                else:
                    tx.execute(
                        """UPDATE work_units SET state = ?, current_attempt_id = NULL,
                           not_before = ? WHERE work_unit_id = ? AND current_attempt_id = ?""",
                        (
                            WorkState.READY.value,
                            now_text(),
                            attempt["work_unit_id"],
                            attempt["attempt_id"],
                        ),
                    )
                    self._append_event(
                        tx,
                        attempt["job_id"],
                        "work.retry_scheduled",
                        {"reason": "lease_expired"},
                    )
                count += 1
        if count:
            with self._condition:
                self._condition.notify_all()
        return count

    def get_status(self, job_id, principal: str | None = None):
        row = self.store.fetchone("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        if not row:
            raise LookupError("JOB_NOT_FOUND")
        self._authorize_job(row["spec_json"], principal)
        total = self.store.fetchone(
            "SELECT COUNT(*) count FROM work_units WHERE job_id = ?", (job_id,)
        )["count"]
        completed = self.store.fetchone(
            "SELECT COUNT(*) count FROM work_units WHERE job_id = ? AND state = ?",
            (job_id, WorkState.SUCCEEDED.value),
        )["count"]
        return {
            "job_id": job_id,
            "state": row["state"],
            "revision": row["revision"],
            "progress": completed / total if total else 0.0,
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "error": decode(row["error_json"]),
            "result": decode(row["result_json"]),
        }

    def result(self, job_id, principal: str | None = None):
        status = self.get_status(job_id, principal=principal)
        if status["state"] != JobState.SUCCEEDED.value:
            raise RuntimeError("JOB_RESULT_NOT_READY")
        return status["result"]

    def events(self, job_id, after=0, principal: str | None = None):
        row = self.store.fetchone("SELECT spec_json FROM jobs WHERE job_id = ?", (job_id,))
        if not row:
            raise LookupError("JOB_NOT_FOUND")
        self._authorize_job(row["spec_json"], principal)
        return [
            {
                **decode(row["payload_json"]),
                "sequence": row["sequence"],
                "event_type": row["event_type"],
                "occurred_at": row["occurred_at"],
            }
            for row in self.store.fetchall(
                """SELECT sequence, event_type, occurred_at, payload_json
                   FROM job_events WHERE job_id = ? AND sequence > ?
                   ORDER BY sequence""",
                (job_id, after),
            )
        ]

    def status_for_attempt(self, attempt_id):
        row = self.store.fetchone(
            "SELECT state, result_json, error_json FROM attempts WHERE attempt_id = ?",
            (attempt_id,),
        )
        return {
            "attempt_state": row["state"],
            "result": decode(row["result_json"]),
            "error": decode(row["error_json"]),
        }

    def set_worker_state(self, worker_id: str, state: str):
        if state not in {"ready", "draining", "offline"}:
            raise ValueError("invalid worker state")
        if (
            self.store.execute(
                "UPDATE workers SET state = ?, last_heartbeat_at = ? WHERE worker_id = ?",
                (state, now_text(), worker_id),
            )
            != 1
        ):
            raise LookupError("WORKER_NOT_FOUND")

    def autoscaling_metrics(self):
        queued = self.store.fetchone(
            "SELECT COUNT(*) count FROM work_units WHERE state = ?", (WorkState.READY.value,)
        )["count"]
        active = self.store.fetchone(
            "SELECT COUNT(*) count FROM work_units WHERE state IN (?, ?)",
            (WorkState.LEASED.value, WorkState.RUNNING.value),
        )["count"]
        ready_workers = self.store.fetchone(
            "SELECT COUNT(*) count FROM workers WHERE state = ?", ("ready",)
        )["count"]
        oldest = self.store.fetchone(
            """SELECT MIN(j.created_at) oldest FROM work_units w JOIN jobs j
               ON j.job_id = w.job_id WHERE w.state = ?""",
            (WorkState.READY.value,),
        )["oldest"]
        wait = 0.0
        if oldest:
            wait = max(
                0.0,
                (
                    datetime.now(UTC) - datetime.fromisoformat(str(oldest).replace("Z", "+00:00"))
                ).total_seconds(),
            )
        return {
            "queued_work_units": int(queued),
            "active_work_units": int(active),
            "ready_workers": int(ready_workers),
            "oldest_queue_wait_seconds": wait,
            "scale_up_recommended": bool(queued > max(1, ready_workers * 2) and wait >= 5),
        }

    def prometheus_metrics(self):
        values = self.autoscaling_metrics()
        lines = [
            "# TYPE stockstat_dispatcher_queued_work_units gauge",
            f"stockstat_dispatcher_queued_work_units {values['queued_work_units']}",
            "# TYPE stockstat_dispatcher_active_work_units gauge",
            f"stockstat_dispatcher_active_work_units {values['active_work_units']}",
            "# TYPE stockstat_dispatcher_ready_workers gauge",
            f"stockstat_dispatcher_ready_workers {values['ready_workers']}",
            "# TYPE stockstat_dispatcher_oldest_queue_wait_seconds gauge",
            f"stockstat_dispatcher_oldest_queue_wait_seconds "
            f"{values['oldest_queue_wait_seconds']:.6f}",
        ]
        for row in self.store.fetchall("SELECT state, COUNT(*) count FROM jobs GROUP BY state"):
            lines.append(f'stockstat_dispatcher_jobs{{state="{row["state"]}"}} {row["count"]}')
        return "\n".join(lines) + "\n"

    def _current_attempt(self, tx, attempt_id, token, worker_session_id):
        attempt = tx.fetchone("SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,))
        if not attempt or not hmac.compare_digest(attempt["token_hash"], _token_hash(token)):
            raise StaleAttemptError("STALE_ATTEMPT")
        if attempt["worker_session_id"] != worker_session_id:
            raise StaleAttemptError("WORKER_SESSION_STALE")
        if attempt["state"] not in {
            AttemptState.LEASED.value,
            AttemptState.RUNNING.value,
        }:
            raise StaleAttemptError("ATTEMPT_TERMINAL")
        work = tx.fetchone(
            "SELECT * FROM work_units WHERE work_unit_id = ?", (attempt["work_unit_id"],)
        )
        if work["current_attempt_id"] != attempt_id:
            raise StaleAttemptError("STALE_ATTEMPT")
        if datetime.fromisoformat(
            str(attempt["lease_expires_at"]).replace("Z", "+00:00")
        ) < datetime.now(UTC):
            raise StaleAttemptError("LEASE_EXPIRED")
        return attempt, work

    @staticmethod
    def _authorize_job(spec_json, principal):
        owner = _stored_model(JobSpec, spec_json).tags.get("stockstat.principal")
        if owner and principal is not None and owner != principal:
            raise LookupError("JOB_NOT_FOUND")

    def _append_event(self, tx, job_id, event_type, payload):
        tx.execute("UPDATE jobs SET revision = revision WHERE job_id = ?", (job_id,))
        current = tx.fetchone(
            "SELECT COALESCE(MAX(sequence), 0) sequence FROM job_events WHERE job_id = ?",
            (job_id,),
        )
        sequence = int(current["sequence"]) + 1
        tx.execute(
            """INSERT INTO job_events
                (job_id, sequence, event_type, occurred_at, payload_json)
                VALUES (?, ?, ?, ?, ?)""",
            (job_id, sequence, event_type, now_text(), encode(payload)),
        )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _stored_model(model_type, value):
    if isinstance(value, (str, bytes, bytearray)):
        return model_type.model_validate_json(value)
    return model_type.model_validate(value)


def _resources_fit(required, available):
    gpu = available.get("gpu", {})
    return (
        float(required.cpu_cores) <= float(available.get("cpu_cores", 0))
        and int(required.memory_bytes) <= int(available.get("memory_bytes", 0))
        and int(required.scratch_bytes) <= int(available.get("scratch_bytes", 0))
        and int(required.gpu.count) <= int(gpu.get("count", 0))
        and int(required.gpu.memory_bytes) <= int(gpu.get("memory_bytes", 0))
    )
