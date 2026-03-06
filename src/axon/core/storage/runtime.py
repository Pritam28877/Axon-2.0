"""Runtime helpers for selecting local and shared graph storage."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from axon.core.storage.base import StorageBackend
from axon.core.storage.kuzu_backend import KuzuBackend


class GraphScope(str, Enum):
    """Logical graph scopes exposed to CLI and MCP callers."""

    LOCAL_OVERLAY = "local_overlay"
    SHARED_CANONICAL = "shared_canonical"


@dataclass(frozen=True)
class StorageLocation:
    """Filesystem location for a graph scope."""

    scope: GraphScope
    path: Path

    @property
    def exists(self) -> bool:
        return self.path.exists()


class StorageRuntime:
    """Resolve and open storage backends for graph scopes."""

    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path.resolve()

    def location_for(self, scope: GraphScope) -> StorageLocation:
        """Resolve the storage path for *scope* using env overrides first."""
        if scope is GraphScope.LOCAL_OVERLAY:
            override = os.getenv("AXON_DB_PATH")
            default_path = self.repo_path / ".axon" / "kuzu"
        else:
            override = os.getenv("AXON_SHARED_DB_PATH") or os.getenv("AXON_CANONICAL_DB_PATH")
            default_path = self.repo_path / ".axon" / "shared" / "kuzu"

        path = Path(override).expanduser() if override else default_path
        if not path.is_absolute():
            path = (self.repo_path / path).resolve()

        return StorageLocation(scope=scope, path=path)

    def open_storage(
        self,
        scope: GraphScope = GraphScope.LOCAL_OVERLAY,
        *,
        read_only: bool = True,
    ) -> StorageBackend:
        """Open a storage backend for *scope*.

        Only Kuzu is wired today; the runtime layer keeps the call sites
        backend-agnostic so Ladybug can be added later without rewriting CLI/MCP.
        """
        location = self.location_for(scope)
        backend = KuzuBackend()
        backend.initialize(location.path, read_only=read_only)
        return backend


def parse_scope(value: str | GraphScope | None) -> GraphScope:
    """Parse a user-facing scope string into :class:`GraphScope`."""
    if isinstance(value, GraphScope):
        return value
    if value is None:
        return GraphScope.LOCAL_OVERLAY

    normalized = value.strip().lower()
    for scope in GraphScope:
        if scope.value == normalized:
            return scope

    valid = ", ".join(scope.value for scope in GraphScope)
    raise ValueError(f"Unknown graph scope '{value}'. Expected one of: {valid}.")

