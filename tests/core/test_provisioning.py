"""Tests for two-tier provisioning helpers."""

from __future__ import annotations

import json
from pathlib import Path

from axon.core.storage.provisioning import provision_repo


class TestProvisionRepo:
    def test_creates_metadata_files(self, tmp_path: Path) -> None:
        result = provision_repo(tmp_path)

        assert result.local_meta_path.exists()
        assert result.shared_meta_path.exists()
        assert (tmp_path / ".axon" / "shared" / "manifests" / "active.json").exists()

        local_meta = json.loads(result.local_meta_path.read_text(encoding="utf-8"))
        shared_meta = json.loads(result.shared_meta_path.read_text(encoding="utf-8"))

        assert local_meta["scopes"]["local_overlay"]["ready"] is True
        assert local_meta["scopes"]["shared_canonical"]["ready"] is True
        assert shared_meta["scope"] == "shared_canonical"
