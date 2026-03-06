"""Tests for scoped storage runtime helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from axon.core.storage.runtime import GraphScope, StorageRuntime, parse_scope


class TestParseScope:
    def test_defaults_to_local_overlay(self) -> None:
        assert parse_scope(None) is GraphScope.LOCAL_OVERLAY

    def test_accepts_string(self) -> None:
        assert parse_scope("shared_canonical") is GraphScope.SHARED_CANONICAL

    def test_rejects_unknown_value(self) -> None:
        with pytest.raises(ValueError):
            parse_scope("nope")


class TestStorageRuntime:
    def test_local_scope_uses_repo_default(self, tmp_path: Path) -> None:
        runtime = StorageRuntime(tmp_path)
        location = runtime.location_for(GraphScope.LOCAL_OVERLAY)
        assert location.path == tmp_path / ".axon" / "kuzu"

    def test_shared_scope_uses_repo_default(self, tmp_path: Path) -> None:
        runtime = StorageRuntime(tmp_path)
        location = runtime.location_for(GraphScope.SHARED_CANONICAL)
        assert location.path == tmp_path / ".axon" / "shared" / "kuzu"

    def test_relative_env_override_is_repo_relative(self, tmp_path: Path) -> None:
        runtime = StorageRuntime(tmp_path)
        with patch.dict("os.environ", {"AXON_SHARED_DB_PATH": ".shared/db"}, clear=False):
            location = runtime.location_for(GraphScope.SHARED_CANONICAL)
        assert location.path == tmp_path / ".shared" / "db"
