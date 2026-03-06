"""Provisioning helpers for Axon's two-tier storage layout."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from axon import __version__
from axon.core.storage.kuzu_backend import KuzuBackend
from axon.core.storage.runtime import GraphScope, StorageRuntime


@dataclass(frozen=True)
class ProvisionResult:
    """Summary of a provisioning run."""

    repo_path: Path
    local_path: Path
    shared_path: Path
    indexed: bool
    local_meta_path: Path
    shared_meta_path: Path


def provision_repo(repo_path: Path) -> ProvisionResult:
    """Create the local overlay and shared canonical scaffolding for *repo_path*."""
    runtime = StorageRuntime(repo_path)
    repo_path = repo_path.resolve()
    axon_dir = repo_path / ".axon"
    shared_dir = axon_dir / "shared"
    manifests_dir = shared_dir / "manifests"

    axon_dir.mkdir(parents=True, exist_ok=True)
    shared_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    local_path = runtime.location_for(GraphScope.LOCAL_OVERLAY).path
    shared_path = runtime.location_for(GraphScope.SHARED_CANONICAL).path

    indexed = local_path.exists()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    shared_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize the shared canonical store schema so scoped reads can open it.
    shared_storage = KuzuBackend()
    shared_storage.initialize(shared_path)
    shared_storage.close()

    now = _now()
    local_meta_path = axon_dir / "meta.json"
    shared_meta_path = shared_dir / "meta.json"
    manifest_path = manifests_dir / "active.json"

    local_meta = _load_json(local_meta_path)
    local_meta.update(
        {
            "version": __version__,
            "name": repo_path.name,
            "path": str(repo_path),
            "repo_id": repo_path.name,
            "provisioned_at": local_meta.get("provisioned_at", now),
            "scopes": {
                "local_overlay": {
                    "backend": "kuzu",
                    "path": str(local_path),
                    "ready": True,
                    "indexed": indexed,
                },
                "shared_canonical": {
                    "backend": "kuzu",
                    "path": str(shared_path),
                    "ready": True,
                    "indexed": False,
                },
            },
        }
    )
    _write_json(local_meta_path, local_meta)

    shared_meta = _load_json(shared_meta_path)
    shared_meta.update(
        {
            "version": __version__,
            "name": repo_path.name,
            "path": str(repo_path),
            "repo_id": repo_path.name,
            "scope": GraphScope.SHARED_CANONICAL.value,
            "backend": "kuzu",
            "initialized_at": shared_meta.get("initialized_at", now),
            "active_snapshot": shared_meta.get("active_snapshot"),
            "last_published_at": shared_meta.get("last_published_at"),
            "snapshot_count": int(shared_meta.get("snapshot_count", 0)),
        }
    )
    _write_json(shared_meta_path, shared_meta)

    manifest = _load_json(manifest_path)
    manifest.update(
        {
            "repo_id": repo_path.name,
            "scope": GraphScope.SHARED_CANONICAL.value,
            "backend": "kuzu",
            "storage_path": str(shared_path),
            "active_snapshot": manifest.get("active_snapshot"),
            "generated_at": now,
        }
    )
    _write_json(manifest_path, manifest)

    return ProvisionResult(
        repo_path=repo_path,
        local_path=local_path,
        shared_path=shared_path,
        indexed=indexed,
        local_meta_path=local_meta_path,
        shared_meta_path=shared_meta_path,
    )


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
