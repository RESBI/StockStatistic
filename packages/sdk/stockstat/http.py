from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
from stockstat_contracts import ArtifactRef, JobSpec


class HttpControlChannel:
    def __init__(self, base_url: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=30.0)

    def submit(self, spec: JobSpec, idempotency_key: str) -> str:
        response = self.client.post(
            "/v31/jobs",
            json=spec.model_dump(mode="json"),
            headers={"Idempotency-Key": idempotency_key},
        )
        response.raise_for_status()
        return response.json()["job_id"]

    def status(self, job_id):
        response = self.client.get(f"/v31/jobs/{job_id}")
        response.raise_for_status()
        return response.json()

    def result(self, job_id):
        response = self.client.get(f"/v31/jobs/{job_id}/result")
        response.raise_for_status()
        return response.json()

    def events(self, job_id, after=0):
        response = self.client.get(f"/v31/jobs/{job_id}/events.json", params={"after": after})
        response.raise_for_status()
        return response.json()["events"]

    def cancel(self, job_id, reason=""):
        response = self.client.post(f"/v31/jobs/{job_id}/cancel", json={"reason": reason})
        response.raise_for_status()
        return response.json()["state"]

    def close(self):
        self.client.close()


class HttpArtifactClient:
    def __init__(self, base_url: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=120.0)

    def commit_file(self, path, *, kind, media_type, codec, schema_ref, metadata=None, **_):
        digest = _sha256(Path(path))
        headers = {
            "Content-Type": media_type,
            "X-Artifact-Kind": kind,
            "X-Artifact-Codec": codec,
            "X-Artifact-Schema": schema_ref,
            "X-Artifact-Sha256": digest,
        }
        if metadata and metadata.get("owner"):
            headers["X-Artifact-Owner"] = metadata["owner"]
        with Path(path).open("rb") as stream:
            response = self.client.post("/internal/v31/artifacts", headers=headers, content=stream)
        response.raise_for_status()
        return ArtifactRef.model_validate(response.json())

    def read(self, reference: ArtifactRef) -> bytes:
        response = self.client.get(f"/internal/v31/artifacts/{reference.artifact_id}/content")
        response.raise_for_status()
        data = response.content
        if (
            len(data) != reference.size_bytes
            or hashlib.sha256(data).hexdigest() != reference.sha256
        ):
            raise ValueError("artifact integrity check failed")
        return data

    def copy_to(self, reference: ArtifactRef, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with self.client.stream(
            "GET", f"/internal/v31/artifacts/{reference.artifact_id}/content"
        ) as response:
            response.raise_for_status()
            with destination.open("wb") as target:
                for chunk in response.iter_bytes():
                    target.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
        if size != reference.size_bytes or digest.hexdigest() != reference.sha256:
            destination.unlink(missing_ok=True)
            raise ValueError("artifact integrity check failed")

    def ingest(self, instrument, source, timeframe, start, end):
        response = self.client.post(
            "/v31/data/ingest",
            json={
                "instrument": instrument.model_dump(mode="json"),
                "source": source,
                "timeframe": timeframe,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )
        response.raise_for_status()
        return response.json()

    def close(self):
        self.client.close()


def _sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
