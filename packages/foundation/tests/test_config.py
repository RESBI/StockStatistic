"""test_config.py — 环境变量 / 配置文件 / 默认值 (12 项)。"""
from __future__ import annotations

import json
import os

import pytest

from stockstat_foundation.config import Config


class TestConfigDefaults:
    def test_defaults(self):
        c = Config()
        assert c.client_mode == "online"
        assert c.default_backend == "local"
        assert c.database_url == "sqlite:///stockstat.db"
        assert c.dispatcher_queue == "memory"
        assert c.protocol_version == "1.0"
        assert c.default_encoding == "json"
        assert c.transport_timeout == 30

    def test_to_dict(self):
        c = Config(database_url="postgresql://x")
        d = c.to_dict()
        assert d["database_url"] == "postgresql://x"
        assert "client_mode" in d


class TestConfigFromEnv:
    def test_from_env_picks_up_env(self, monkeypatch):
        monkeypatch.setenv("STOCKSTAT_DATABASE_URL", "postgresql://test/test")
        monkeypatch.setenv("STOCKSTAT_DISPATCHER_ENABLED", "true")
        monkeypatch.setenv("STOCKSTAT_DISPATCHER_QUEUE", "redis")
        monkeypatch.setenv("STOCKSTAT_DEFAULT_BACKEND", "remote")
        monkeypatch.setenv("STOCKSTAT_WORKER_CONCURRENCY", "8")
        c = Config.from_env()
        assert c.database_url == "postgresql://test/test"
        assert c.dispatcher_enabled is True
        assert c.dispatcher_queue == "redis"
        assert c.default_backend == "remote"
        assert c.worker_concurrency == 8

    def test_from_env_bool_variants(self, monkeypatch):
        for v in ["1", "true", "True", "yes", "on"]:
            monkeypatch.setenv("STOCKSTAT_ADMIN_ENABLED", v)
            assert Config.from_env().admin_enabled is True, f"failed for {v}"
        for v in ["0", "false", "no", "off", ""]:
            monkeypatch.setenv("STOCKSTAT_ADMIN_ENABLED", v)
            assert Config.from_env().admin_enabled is False, f"failed for {v}"

    def test_from_env_defaults_when_unset(self, monkeypatch):
        for k in ["STOCKSTAT_DATABASE_URL", "STOCKSTAT_DISPATCHER_ENABLED"]:
            monkeypatch.delenv(k, raising=False)
        c = Config.from_env()
        assert c.database_url == "sqlite:///stockstat.db"
        assert c.dispatcher_enabled is False


class TestConfigFromFile:
    def test_from_json_file(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text(json.dumps({
            "database_url": "postgresql://from/file",
            "admin_enabled": True,
            "worker_concurrency": 4,
            "unknown_field": "ignored",
        }))
        c = Config.from_file(str(p))
        assert c.database_url == "postgresql://from/file"
        assert c.admin_enabled is True
        assert c.worker_concurrency == 4


class TestConfigCopy:
    def test_copy_with_overrides(self):
        c = Config()
        c2 = c.copy(database_url="x", admin_enabled=True)
        assert c2.database_url == "x"
        assert c2.admin_enabled is True
        # original not modified
        assert c.database_url == "sqlite:///stockstat.db"

    def test_worker_concurrency_zero_becomes_none(self, monkeypatch):
        monkeypatch.setenv("STOCKSTAT_WORKER_CONCURRENCY", "0")
        c = Config.from_env()
        assert c.worker_concurrency is None
