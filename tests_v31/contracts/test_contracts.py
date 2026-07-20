from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from stockstat_contracts import (
    ArtifactRef,
    ControlMessage,
    DatasetSelector,
    InstrumentRef,
    JobSpec,
    OperationSpec,
    canonical_digest,
    canonical_json,
    new_id,
    parse_id,
)


def test_uuid7_round_trip_and_sorting():
    first = new_id()
    second = new_id()
    assert parse_id(first) == first
    assert first < second


def test_canonical_json_is_order_independent():
    left = {"b": 2, "a": {"z": 1, "x": 0}}
    right = {"a": {"x": 0, "z": 1}, "b": 2}
    assert canonical_json(left) == canonical_json(right)
    assert canonical_digest(left) == canonical_digest(right)


def test_canonical_json_rejects_non_finite_numbers():
    with pytest.raises(ValueError):
        canonical_json({"value": float("nan")})


def test_selector_normalizes_utc_and_validates_half_open_range():
    selector = DatasetSelector(
        instruments=(InstrumentRef(asset_class="crypto", symbol="PAXG/USDT", venue="binance"),),
        timeframe="1H",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 2, 1, tzinfo=UTC),
    )
    assert selector.timeframe == "1h"
    assert selector.start.tzinfo is UTC
    with pytest.raises(ValidationError):
        DatasetSelector(
            instruments=selector.instruments,
            timeframe="1h",
            start=selector.end,
            end=selector.end,
        )


def test_input_union_and_control_message_round_trip():
    spec = JobSpec(
        name="MA",
        operation=OperationSpec(
            capability_id="finance.indicator.compute",
            parameters={"indicator": "ma", "window": 20},
        ),
    )
    message = ControlMessage(
        message_type="job.submit",
        content_schema="stockstat.job.submit/1",
        content=spec.model_dump(mode="json"),
    )
    restored = ControlMessage.model_validate_json(message.model_dump_json())
    assert restored.content["operation"]["capability_id"] == "finance.indicator.compute"


def test_artifact_digest_validation():
    ref = ArtifactRef(
        artifact_id=new_id(),
        kind="work_result",
        media_type="application/octet-stream",
        codec="raw",
        size_bytes=3,
        sha256="a" * 64,
        schema_ref="test/1",
        locator="artifact://sha256/" + "a" * 64,
    )
    assert ref.sha256 == "a" * 64
    with pytest.raises(ValidationError):
        ArtifactRef.model_validate({**ref.model_dump(), "sha256": "bad"})


def test_control_message_rejects_naive_time():
    with pytest.raises(ValidationError):
        ControlMessage(
            message_type="job.submit",
            sent_at=datetime.now(),
            content_schema="stockstat.job.submit/1",
            content={},
        )
