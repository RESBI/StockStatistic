"""test_messages.py — 消息类型常量 / TYPE_TO_PATH / 分组 (10 项)。"""
from __future__ import annotations

from stockstat_foundation.protocol import messages


class TestMessageConstants:
    def test_control_types_count(self):
        assert len(messages.CONTROL_TYPES) == 11

    def test_dispatch_types_count(self):
        assert len(messages.DISPATCH_TYPES) == 12

    def test_data_types_count(self):
        assert len(messages.DATA_TYPES) == 3

    def test_discovery_types_count(self):
        assert len(messages.DISCOVERY_TYPES) == 2

    def test_all_types_total(self):
        assert len(messages.ALL_TYPES) == 28


class TestTypeToPath:
    def test_submit_path(self):
        assert messages.TYPE_TO_PATH[messages.TASK_SUBMIT] == "/dispatch/submit"

    def test_data_fetch_path_maps_to_ohlcv(self):
        assert messages.TYPE_TO_PATH[messages.DATA_FETCH] == "/api/v1/ohlcv"

    def test_dispatch_assign_path(self):
        assert messages.TYPE_TO_PATH[messages.DISPATCH_ASSIGN] == "/dispatch/assign"

    def test_all_paths_unique(self):
        paths = list(messages.TYPE_TO_PATH.values())
        assert len(paths) == len(set(paths))


class TestHelpers:
    def test_is_control(self):
        assert messages.is_control(messages.TASK_SUBMIT)
        assert not messages.is_control(messages.DISPATCH_ASSIGN)

    def test_is_dispatch(self):
        assert messages.is_dispatch(messages.DISPATCH_REGISTER)
        assert not messages.is_dispatch(messages.TASK_SUBMIT)
