from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel
from stockstat_contracts import (
    DatasetSelector,
    InstrumentRef,
    token_has_scope,
    token_matches,
    token_principal,
)

from .artifacts import ArtifactService, LocalBlobStore
from .ingestion import IngestionService, SyntheticSource
from .repository import PostgresStorageRepository, SQLiteStorageRepository
from .snapshots import SnapshotService


class IngestRequest(BaseModel):
    instrument: InstrumentRef
    source: str = "synthetic"
    timeframe: str
    start: datetime
    end: datetime


def create_app(
    database_url: str,
    artifact_root: str | Path,
    *,
    token_scopes: dict[str, frozenset[str]] | None = None,
    internal_token: str | None = None,
    max_upload_bytes: int = 3 * 1024**3,
    blob_store=None,
) -> FastAPI:
    if database_url.startswith("postgresql://"):
        repository = PostgresStorageRepository(database_url)
    else:
        repository = SQLiteStorageRepository(database_url.removeprefix("sqlite:///"))
    repository.initialize()
    root = Path(artifact_root)
    artifacts = ArtifactService(repository, blob_store or LocalBlobStore(root), root / "uploads")
    snapshots = SnapshotService(repository, artifacts)
    ingestion = IngestionService(repository, {"synthetic": SyntheticSource()})

    app = FastAPI(title="StockStat Storage", version="3.1.0")
    app.state.repository = repository
    app.state.artifacts = artifacts
    app.state.snapshots = snapshots
    app.state.ingestion = ingestion

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        scope = _storage_scope(request.url.path)
        authorization = request.headers.get("authorization")
        if scope == "internal":
            if not token_matches(authorization, internal_token):
                return JSONResponse({"detail": "INVALID_WORKLOAD_TOKEN"}, status_code=401)
        elif scope == "artifacts":
            secured = bool(internal_token or token_scopes)
            internal = bool(internal_token) and token_matches(authorization, internal_token)
            client = bool(token_scopes) and token_has_scope(
                authorization, "artifacts", token_scopes
            )
            if secured and not (internal or client):
                return JSONResponse({"detail": "MISSING_SCOPE:artifacts"}, status_code=403)
        elif scope and not token_has_scope(authorization, scope, token_scopes):
            return JSONResponse({"detail": f"MISSING_SCOPE:{scope}"}, status_code=403)
        return await call_next(request)

    @app.get("/v31/meta")
    def meta():
        return {
            "service": "storage",
            "service_version": "3.1.0",
            "protocol_versions": ["3.1"],
            "artifact_media_types": ["application/vnd.apache.arrow.stream"],
        }

    @app.get("/health/live")
    def live():
        return {"status": "live"}

    @app.get("/health/ready")
    def ready():
        try:
            repository.artifact_digests()
            return {"status": "ready"}
        except Exception as exc:
            raise HTTPException(status_code=503, detail="STORAGE_UNAVAILABLE") from exc

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics():
        return (
            "# TYPE stockstat_storage_repository_queries_total counter\n"
            f"stockstat_storage_repository_queries_total {repository.query_count}\n"
            "# TYPE stockstat_storage_artifacts gauge\n"
            f"stockstat_storage_artifacts {len(repository.artifact_digests())}\n"
        )

    @app.get("/v31/artifacts/{artifact_id}/presign")
    def presign_artifact(
        request: Request,
        artifact_id: str,
        method: str = "get",
        expires_seconds: int = 300,
    ):
        reference = repository.get_artifact(artifact_id)
        if reference is None:
            raise HTTPException(status_code=404, detail="ARTIFACT_NOT_FOUND")
        _authorize_artifact(request, repository, artifact_id, token_scopes, internal_token)
        if method not in {"get", "put"}:
            raise HTTPException(status_code=400, detail="INVALID_PRESIGN_METHOD")
        try:
            url = artifacts.presign(reference, method, expires_seconds)
        except NotImplementedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "url": url,
            "method": method,
            "expires_seconds": min(expires_seconds, 3600),
        }

    @app.post("/v31/artifacts/reconcile")
    def reconcile_artifacts(payload: dict):
        orphaned = artifacts.reconcile_orphans(delete=bool(payload.get("delete")))
        return {"orphaned": orphaned, "count": len(orphaned)}

    @app.post("/v31/data/ingest")
    def ingest(request: IngestRequest):
        return ingestion.ingest(
            request.instrument,
            request.source,
            request.timeframe,
            request.start,
            request.end,
        ).__dict__

    @app.post("/internal/v31/snapshots")
    def create_snapshot(selector: DatasetSelector):
        try:
            return snapshots.create(selector).model_dump(mode="json")
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/internal/v31/artifacts/{artifact_id}")
    def artifact_metadata(request: Request, artifact_id: str):
        reference = repository.get_artifact(artifact_id)
        if reference is None:
            raise HTTPException(status_code=404, detail="ARTIFACT_NOT_FOUND")
        _authorize_artifact(request, repository, artifact_id, token_scopes, internal_token)
        return reference.model_dump(mode="json")

    @app.get("/internal/v31/artifacts/{artifact_id}/content")
    def artifact_content(request: Request, artifact_id: str):
        reference = repository.get_artifact(artifact_id)
        if reference is None:
            raise HTTPException(status_code=404, detail="ARTIFACT_NOT_FOUND")
        _authorize_artifact(request, repository, artifact_id, token_scopes, internal_token)
        return StreamingResponse(
            artifacts.iter_bytes(reference),
            media_type=reference.media_type,
            headers={
                "Content-Length": str(reference.size_bytes),
                "Digest": f"sha-256={reference.sha256}",
            },
        )

    @app.post("/internal/v31/artifacts")
    async def upload_artifact(
        request: Request,
        x_artifact_kind: str = Header(default="uploaded_dataframe"),
        x_artifact_codec: str = Header(default="raw"),
        x_artifact_schema: str = Header(default="stockstat.table/1"),
        x_artifact_sha256: str | None = Header(default=None),
        x_artifact_owner: str | None = Header(default=None),
    ):
        import tempfile

        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temporary:
                temporary_path = Path(temporary.name)
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > max_upload_bytes:
                        raise HTTPException(status_code=413, detail="ARTIFACT_TOO_LARGE")
                    temporary.write(chunk)
            reference = artifacts.commit_file(
                temporary_path,
                kind=x_artifact_kind,
                media_type=request.headers.get("content-type", "application/octet-stream"),
                codec=x_artifact_codec,
                schema_ref=x_artifact_schema,
                expected_sha256=x_artifact_sha256,
                metadata={
                    "owner": x_artifact_owner
                    or token_principal(request.headers.get("authorization"), token_scopes)
                },
            )
            return reference.model_dump(mode="json")
        finally:
            if temporary_path:
                temporary_path.unlink(missing_ok=True)

    return app


def _storage_scope(path: str) -> str | None:
    if path.startswith("/internal/v31/snapshots"):
        return "internal"
    if path.startswith("/internal/v31/artifacts"):
        return "artifacts"
    if path.startswith(("/health/", "/metrics")) or path == "/v31/meta":
        return None
    if path.startswith("/v31/data"):
        return "data"
    if path.startswith("/v31/artifacts"):
        return "artifacts"
    return None


def _authorize_artifact(request, repository, artifact_id, token_scopes, internal_token):
    if internal_token and token_matches(request.headers.get("authorization"), internal_token):
        return
    metadata = repository.get_artifact_metadata(artifact_id) or {}
    owner = metadata.get("owner")
    principal = token_principal(request.headers.get("authorization"), token_scopes)
    if owner and owner != principal:
        raise HTTPException(status_code=404, detail="ARTIFACT_NOT_FOUND")
