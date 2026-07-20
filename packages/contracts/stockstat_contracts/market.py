from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, model_validator

from .base import ContractModel
from .time import normalize_utc

_TIMEFRAME = re.compile(r"^[1-9][0-9]*(s|m|h|d|w)$")


def _validate_timeframe(value: str) -> str:
    normalized = value.strip().lower()
    if not _TIMEFRAME.fullmatch(normalized):
        raise ValueError("timeframe must look like 1m, 1h, or 1d")
    return normalized


Timeframe = Annotated[str, AfterValidator(_validate_timeframe)]


class InstrumentRef(ContractModel):
    asset_class: str = "unknown"
    symbol: str = Field(min_length=1)
    venue: str = "unknown"
    currency: str | None = None

    @property
    def key(self) -> str:
        return f"{self.asset_class}:{self.venue}:{self.symbol}"


class TimeRange(ContractModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_range(self) -> TimeRange:
        start = normalize_utc(self.start)
        end = normalize_utc(self.end)
        if start >= end:
            raise ValueError("time range must satisfy start < end")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        return self


class SourcePolicy(ContractModel):
    mode: Literal["exact", "preferred", "any"] = "any"
    source: str | None = None


class DatasetSelector(ContractModel):
    instruments: tuple[InstrumentRef, ...]
    timeframe: Timeframe
    start: datetime
    end: datetime
    fields: tuple[str, ...] = ("open", "high", "low", "close", "volume")
    source_policy: SourcePolicy = SourcePolicy()
    adjustment: str = "raw"
    calendar: str = "24x7"
    as_of: datetime | None = None
    snapshot_policy: Literal["pin_on_submit", "existing"] = "pin_on_submit"

    @model_validator(mode="after")
    def validate_selector(self) -> DatasetSelector:
        if not self.instruments:
            raise ValueError("at least one instrument is required")
        time_range = TimeRange(start=self.start, end=self.end)
        object.__setattr__(self, "start", time_range.start)
        object.__setattr__(self, "end", time_range.end)
        if self.as_of is not None:
            object.__setattr__(self, "as_of", normalize_utc(self.as_of))
        return self
