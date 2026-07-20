from __future__ import annotations

import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    column: int
    code: str
    message: str
    replacement: str | None
    automatic: bool


class MigrationScanner(ast.NodeVisitor):
    def __init__(self, path: Path):
        self.path = path
        self.findings = []

    def visit_Name(self, node):
        replacements = {
            "StockStatClient": "StockStat.connect",
            "V2Client": "StockStat.local",
            "TaskRef": "JobHandle",
            "MemoryStorage": "StockStat.local",
            "SQLStorage": "StockStat.local",
        }
        if node.id in replacements:
            self._add(
                node,
                f"LEGACY_{node.id.upper()}",
                f"legacy API {node.id}",
                replacements[node.id],
                True,
            )
        self.generic_visit(node)

    def visit_Attribute(self, node):
        names = {
            "remote": "use a typed namespace submit() method",
            "run_dsl": "use ss.dsl.compile/execute",
            "render": "use V3.1 result PlotSpec renderer",
        }
        if node.attr in names:
            self._add(
                node,
                f"LEGACY_ATTRIBUTE_{node.attr.upper()}",
                names[node.attr],
                None,
                False,
            )
        self.generic_visit(node)

    def visit_Lambda(self, node):
        self._add(
            node,
            "STRATEGY_LAMBDA",
            "remote strategies must be importable module factories",
            None,
            False,
        )
        self.generic_visit(node)

    def _add(self, node, code, message, replacement, automatic):
        self.findings.append(
            Finding(
                str(self.path),
                node.lineno,
                node.col_offset,
                code,
                message,
                replacement,
                automatic,
            )
        )


def scan(path: str | Path):
    root = Path(path)
    files = [root] if root.is_file() else sorted(root.rglob("*.py"))
    findings = []
    for source in files:
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (SyntaxError, UnicodeDecodeError) as exc:
            findings.append(
                Finding(
                    str(source),
                    getattr(exc, "lineno", 0) or 0,
                    getattr(exc, "offset", 0) or 0,
                    "PARSE_ERROR",
                    str(exc),
                    None,
                    False,
                )
            )
            continue
        scanner = MigrationScanner(source)
        scanner.visit(tree)
        findings.extend(scanner.findings)
    return findings


def report(path: str | Path):
    findings = scan(path)
    return {
        "path": str(path),
        "finding_count": len(findings),
        "findings": [asdict(finding) for finding in findings],
    }


def write_report(path, output):
    payload = report(path)
    Path(output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
