from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from .base import ContractModel
from .market import InstrumentRef


class ArtifactLineage(ContractModel):
    job_id: str | None = None
    work_unit_id: str | None = None
    attempt_id: str | None = None
    input_artifact_digests: tuple[str, ...] = ()
    ingest_batch_ids: tuple[str, ...] = ()


class ArtifactRef(ContractModel):
    artifact_id: str
    kind: str
    media_type: str
    codec: str
    size_bytes: int = Field(ge=0)
    sha256: str
    schema_ref: str
    locator: str
    compression: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.removeprefix("sha256:").lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("sha256 must be 64 hexadecimal characters")
        return normalized


class DatasetSnapshotManifest(ContractModel):
    dataset_snapshot_id: str
    selector_digest: str
    resolved_instruments: tuple[InstrumentRef, ...]
    timeframe: str
    resolved_start: datetime
    resolved_end: datetime
    row_count: int = Field(ge=0)
    schema_ref: str
    artifact: ArtifactRef
    source_versions: tuple[str, ...] = ()
    ingest_batch_ids: tuple[str, ...] = ()
    created_at: datetime
    sha256: str
