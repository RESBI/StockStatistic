from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from .artifacts import ArtifactRef
from .base import ContractModel


class ExecutorRole(StrEnum):
    EXECUTE = "execute"
    REDUCE = "reduce"


class StageState(StrEnum):
    BLOCKED = "blocked"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkState(StrEnum):
    BLOCKED = "blocked"
    READY = "ready"
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"
    CANCELLED = "cancelled"


class AttemptState(StrEnum):
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    STALE = "stale"


class GpuResource(ContractModel):
    count: int = Field(default=0, ge=0)
    memory_bytes: int = Field(default=0, ge=0)


class ResourceSpec(ContractModel):
    cpu_cores: float = Field(default=1.0, gt=0)
    memory_bytes: int = Field(default=536_870_912, ge=0)
    gpu: GpuResource = GpuResource()
    scratch_bytes: int = Field(default=0, ge=0)
    labels: dict[str, str] = Field(default_factory=dict)
    exclusive: bool = False


class PartitionSpec(ContractModel):
    index: int = Field(default=0, ge=0)
    count: int = Field(default=1, ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkUnitSpec(ContractModel):
    work_unit_id: str
    job_id: str
    stage_id: str
    capability_id: str
    capability_version: str
    executor_role: ExecutorRole = ExecutorRole.EXECUTE
    parameters: dict[str, Any] = Field(default_factory=dict)
    inputs: tuple[ArtifactRef, ...] = ()
    partition: PartitionSpec = PartitionSpec()
    resources: ResourceSpec = ResourceSpec()
    random_seed: int = 0
    deadline_at: datetime | None = None
    output_schema: str
    metadata: dict[str, str] = Field(default_factory=dict)


class WorkLease(ContractModel):
    worker_id: str
    worker_session_id: str
    attempt_id: str
    lease_generation: int = Field(ge=1)
    lease_token: str
    lease_expires_at: datetime
    renew_after_seconds: float = Field(gt=0)
    work: WorkUnitSpec
