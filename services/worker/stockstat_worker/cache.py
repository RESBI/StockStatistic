from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path

from stockstat_contracts import ArtifactRef


class ArtifactCache:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, digest: str) -> Path:
        return self.root / digest[:2] / digest

    def resolve(self, reference: ArtifactRef, artifacts) -> Path:
        destination = self.path(reference.sha256)
        if destination.is_file() and _sha256(destination) == reference.sha256:
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(f".{uuid.uuid4().hex}.tmp")
        artifacts.copy_to(reference, temporary)
        if temporary.stat().st_size != reference.size_bytes:
            temporary.unlink(missing_ok=True)
            raise ValueError("artifact size mismatch")
        os.replace(temporary, destination)
        return destination

    def clear(self):
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
