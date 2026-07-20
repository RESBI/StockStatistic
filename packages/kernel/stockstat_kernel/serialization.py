from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc

from .backtest import BacktestResult


@dataclass(frozen=True)
class SerializedOutput:
    manifest: dict
    files: dict[str, Path]


def write_arrow(table: pa.Table, path: Path) -> None:
    with path.open("wb") as stream:
        with ipc.new_stream(stream, table.schema) as writer:
            writer.write_table(table)


def serialize_backtest(result: BacktestResult, output_dir: Path) -> SerializedOutput:
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "equity": output_dir / "equity.arrow",
        "fills": output_dir / "fills.arrow",
        "positions": output_dir / "positions.arrow",
    }
    write_arrow(
        pa.Table.from_pandas(result.equity.reset_index(), preserve_index=False), files["equity"]
    )
    write_arrow(pa.Table.from_pandas(result.fills, preserve_index=False), files["fills"])
    write_arrow(pa.Table.from_pandas(result.positions, preserve_index=False), files["positions"])
    manifest = {
        "result_schema": "stockstat.result.backtest/1",
        "metrics": result.metrics,
        "config": result.config,
        "artifacts": {},
    }
    for name, path in files.items():
        data = path.read_bytes()
        manifest["artifacts"][name] = {
            "file": path.name,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "schema_ref": f"stockstat.backtest.{name}/1",
        }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8"
    )
    return SerializedOutput(manifest, files)
