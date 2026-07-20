from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from stockstat_contracts import DatasetSelector, InstrumentRef, SourcePolicy


@dataclass(frozen=True)
class CompiledQuery:
    selector: DatasetSelector
    fields: tuple[str, ...]
    indicators: tuple[dict, ...]
    limit: int | None


class DSLCompiler:
    _QUERY = re.compile(
        r"SELECT\s+(?P<select>.+?)\s+FROM\s+ohlcv\(\s*"
        r"(?P<symbol>['\"][^'\"]+['\"])\s*,\s*"
        r"(?P<timeframe>['\"][^'\"]+['\"])\s*,\s*"
        r"(?P<start>['\"][^'\"]+['\"])\s*,\s*"
        r"(?P<end>['\"][^'\"]+['\"])\s*\)"
        r"(?:\s+LIMIT\s+(?P<limit>\d+))?\s*$",
        re.IGNORECASE | re.DOTALL,
    )
    _INDICATOR = re.compile(
        r"(?P<name>[A-Za-z_]\w*)\((?P<args>[^)]*)\)"
        r"(?:\s+AS\s+(?P<alias>[A-Za-z_]\w*))?",
        re.IGNORECASE,
    )

    def compile(
        self, source: str, *, venue="synthetic", asset_class="synthetic", data_source="synthetic"
    ) -> CompiledQuery:
        match = self._QUERY.match(source.strip())
        if not match:
            raise ValueError("DSL syntax error: expected SELECT ... FROM ohlcv(...) [LIMIT n]")
        fields = []
        indicators = []
        for item in _split_commas(match.group("select")):
            indicator = self._INDICATOR.fullmatch(item.strip())
            if not indicator:
                fields.append(item.strip())
                continue
            arguments = [part.strip() for part in _split_commas(indicator.group("args"))]
            column = arguments.pop(0)
            values = [_literal(value) for value in arguments]
            indicators.append(
                {
                    "name": indicator.group("name").lower(),
                    "column": column,
                    "arguments": values,
                    "alias": indicator.group("alias") or indicator.group("name").lower(),
                }
            )
        selector = DatasetSelector(
            instruments=(
                InstrumentRef(
                    asset_class=asset_class,
                    symbol=_literal(match.group("symbol")),
                    venue=venue,
                ),
            ),
            timeframe=_literal(match.group("timeframe")),
            start=_utc_datetime(match.group("start")),
            end=_utc_datetime(match.group("end")),
            source_policy=SourcePolicy(mode="exact", source=data_source),
        )
        return CompiledQuery(
            selector=selector,
            fields=tuple(fields),
            indicators=tuple(indicators),
            limit=int(match.group("limit")) if match.group("limit") else None,
        )


def _split_commas(value: str):
    result, current, depth = [], [], 0
    for character in value:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        if character == "," and depth == 0:
            result.append("".join(current))
            current = []
        else:
            current.append(character)
    if current:
        result.append("".join(current))
    return result


def _literal(value: str):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _utc_datetime(value: str):
    parsed = datetime.fromisoformat(str(_literal(value)).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
