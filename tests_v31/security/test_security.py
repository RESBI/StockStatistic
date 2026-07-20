import ast
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from stockstat.strategy_package import package_module, verify_package
from stockstat_contracts import parse_token_rules, token_principal
from stockstat_dispatcher.app import create_app as create_dispatcher_app
from stockstat_storage.app import create_app as create_storage_app

ROOT = Path(__file__).resolve().parents[2]


def test_public_and_internal_tokens_are_scope_isolated(tmp_path):
    storage = TestClient(
        create_storage_app(
            f"sqlite:///{tmp_path / 'market.db'}",
            tmp_path / "artifacts",
            token_scopes=parse_token_rules(["client=data,artifacts"]),
            internal_token="worker-secret",
        )
    )
    assert storage.get("/v31/meta").status_code == 200
    assert storage.post("/v31/data/ingest", json={}).status_code == 403
    assert (
        storage.post(
            "/v31/data/ingest",
            json={},
            headers={"Authorization": "Bearer client"},
        ).status_code
        == 422
    )
    assert storage.post("/internal/v31/snapshots", json={}).status_code == 401
    assert (
        storage.post(
            "/internal/v31/snapshots",
            json={},
            headers={"Authorization": "Bearer client"},
        ).status_code
        == 401
    )
    assert (
        storage.post(
            "/internal/v31/snapshots",
            json={},
            headers={"Authorization": "Bearer worker-secret"},
        ).status_code
        == 422
    )


def test_dispatcher_scopes_and_workload_token(tmp_path):
    app = create_dispatcher_app(
        f"sqlite:///{tmp_path / 'tasks.db'}",
        "http://storage.invalid",
        token_scopes=parse_token_rules(["client=jobs", "admin=cluster"]),
        internal_token="worker-secret",
    )
    client = TestClient(app)
    assert client.get("/health/ready").status_code == 200
    assert client.get("/v31/cluster").status_code == 403
    assert client.get("/v31/cluster", headers={"Authorization": "Bearer admin"}).status_code == 200
    assert client.post("/internal/v31/work/claim", json={}).status_code == 401
    assert (
        client.post(
            "/internal/v31/work/claim",
            json={},
            headers={"Authorization": "Bearer client"},
        ).status_code
        == 401
    )


def test_tenant_cannot_read_another_tenants_job(tmp_path):
    app = create_dispatcher_app(
        f"sqlite:///{tmp_path / 'tasks.db'}",
        "http://storage.invalid",
        token_scopes=parse_token_rules(["alice=jobs", "bob=jobs"]),
    )
    service = app.state.dispatcher
    from stockstat_contracts import JobSpec, OperationSpec

    job_id = service.submit(
        JobSpec(
            name="tenant",
            operation=OperationSpec(
                capability_id="finance.indicator.compute",
                parameters={"indicator": "ma", "arguments": {"window": 2}},
            ),
        ),
        "same-key",
        principal=token_principal("Bearer alice", parse_token_rules(["alice=jobs"])),
    )
    client = TestClient(app)
    assert (
        client.get(f"/v31/jobs/{job_id}", headers={"Authorization": "Bearer alice"}).status_code
        == 200
    )
    assert (
        client.get(f"/v31/jobs/{job_id}", headers={"Authorization": "Bearer bob"}).status_code
        == 404
    )


def test_artifact_acl_hides_cross_tenant_content(tmp_path):
    rules = parse_token_rules(["alice=artifacts", "bob=artifacts"])
    app = create_storage_app(
        f"sqlite:///{tmp_path / 'market.db'}",
        tmp_path / "artifacts",
        token_scopes=rules,
    )
    source = tmp_path / "payload.bin"
    source.write_bytes(b"tenant-data")
    reference = app.state.artifacts.commit_file(
        source,
        kind="test",
        media_type="application/octet-stream",
        codec="raw",
        schema_ref="test/1",
        metadata={"owner": token_principal("Bearer alice", rules)},
    )
    client = TestClient(app)
    path = f"/internal/v31/artifacts/{reference.artifact_id}/content"
    assert client.get(path, headers={"Authorization": "Bearer alice"}).content == b"tenant-data"
    assert client.get(path, headers={"Authorization": "Bearer bob"}).status_code == 404


def test_strategy_package_tamper_and_zip_slip_are_rejected(tmp_path):
    module = tmp_path / "strategy.py"
    module.write_text("def build(config):\n    return config\n", encoding="utf-8")
    package = tmp_path / "strategy.zip"
    packaged = package_module(module, "strategy:build", package)
    with pytest.raises(ValueError, match="not trusted"):
        verify_package(package, trusted_public_keys=["00" * 32])
    scanned = []
    verify_package(
        package,
        trusted_public_keys=[packaged["public_key"]],
        scanner=lambda manifest, source: scanned.append((manifest["entrypoint"], source)),
    )
    assert scanned[0][0] == "strategy:build"
    with zipfile.ZipFile(package) as archive:
        manifest = archive.read("stockstat-strategy.json")
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(tampered, "w") as archive:
        archive.writestr("strategy.py", b"def build(config):\n    return {}\n")
        archive.writestr("stockstat-strategy.json", manifest)
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_package(tampered)
    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../escape.py", b"pass")
        archive.writestr("stockstat-strategy.json", json.dumps({}))
    with pytest.raises(ValueError, match="unsafe path"):
        verify_package(unsafe)


def test_v31_network_code_has_no_pickle_or_legacy_imports():
    violations = []
    roots = [
        ROOT / "packages",
        ROOT / "services",
        ROOT / "working" / "PAXG-Weekend-Monday-Law-v5-v31",
    ]
    banned_imports = {"pickle", "cloudpickle", "stockstat_backend", "stockstat_compute"}
    for root in roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name.split(".", 1)[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = {node.module.split(".", 1)[0]}
                else:
                    continue
                if names & banned_imports:
                    violations.append(str(path.relative_to(ROOT)))
    assert not violations
