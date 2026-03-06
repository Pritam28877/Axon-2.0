"""MCP server for Axon — exposes code intelligence tools over stdio transport.

Registers seven tools and three resources that give AI agents and MCP clients
access to the Axon knowledge graph.  The server lazily initialises a
:class:`KuzuBackend` from the ``.axon/kuzu`` directory in the current
working directory.

Usage::

    # MCP server only
    axon mcp

    # MCP server with live file watching (recommended)
    axon serve --watch
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

from axon.core.storage.base import StorageBackend
from axon.core.storage.runtime import GraphScope, StorageRuntime, parse_scope
from axon.mcp.resources import get_dead_code_list, get_overview, get_schema
from axon.mcp.tools import (
    handle_context,
    handle_cypher,
    handle_dead_code,
    handle_detect_changes,
    handle_impact,
    handle_list_repos,
    handle_query,
)

logger = logging.getLogger(__name__)

server = Server("axon")

_storage: StorageBackend | None = None
_shared_storage: StorageBackend | None = None
_lock: asyncio.Lock | None = None
_runtime: StorageRuntime | None = None


def set_storage(storage: StorageBackend) -> None:
    """Inject a pre-initialised storage backend (e.g. from ``axon serve --watch``)."""
    global _storage  # noqa: PLW0603
    _storage = storage


def set_runtime(runtime: StorageRuntime) -> None:
    """Inject runtime path resolution for scoped storage."""
    global _runtime  # noqa: PLW0603
    _runtime = runtime


def set_lock(lock: asyncio.Lock) -> None:
    """Inject a shared lock for coordinating storage access with the file watcher."""
    global _lock  # noqa: PLW0603
    _lock = lock


def _get_runtime() -> StorageRuntime:
    """Return the configured runtime, defaulting to the current working directory."""
    global _runtime  # noqa: PLW0603
    if _runtime is None:
        _runtime = StorageRuntime(Path.cwd())
    return _runtime


def _get_storage(scope: GraphScope = GraphScope.LOCAL_OVERLAY) -> StorageBackend:
    """Lazily initialise and return the storage backend for *scope*.

    Looks for a ``.axon/kuzu`` directory in the current working directory.
    If it exists, the backend is initialised from that path.  Otherwise a
    bare (uninitialised) backend is returned so that tools can still be
    called without crashing.
    """
    global _storage  # noqa: PLW0603
    runtime = _get_runtime()
    location = runtime.location_for(scope)

    global _shared_storage  # noqa: PLW0603

    if scope is GraphScope.LOCAL_OVERLAY and _storage is not None:
        return _storage
    if scope is GraphScope.SHARED_CANONICAL and _shared_storage is not None:
        return _shared_storage

    if location.exists:
        storage = runtime.open_storage(scope, read_only=True)
        if scope is GraphScope.LOCAL_OVERLAY:
            _storage = storage
        else:
            _shared_storage = storage
        logger.info("Initialised %s storage (read-only) from %s", scope.value, location.path)
        return storage

    logger.warning("No %s storage directory found at %s", scope.value, location.path)
    raise FileNotFoundError(f"No {scope.value} storage found at {location.path}")

TOOLS: list[Tool] = [
    Tool(
        name="axon_list_repos",
        description="List all indexed repositories with their stats.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="axon_query",
        description=(
            "Search the knowledge graph using hybrid (keyword + vector) search. "
            "Returns ranked symbols matching the query."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query text.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default 20).",
                    "default": 20,
                },
                "scope": {
                    "type": "string",
                    "description": "Graph scope: local_overlay or shared_canonical.",
                    "default": GraphScope.LOCAL_OVERLAY.value,
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="axon_context",
        description=(
            "Get a 360-degree view of a symbol: callers, callees, type references, "
            "and community membership."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Name of the symbol to look up.",
                },
                "scope": {
                    "type": "string",
                    "description": "Graph scope: local_overlay or shared_canonical.",
                    "default": GraphScope.LOCAL_OVERLAY.value,
                },
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="axon_impact",
        description=(
            "Blast radius analysis: find all symbols affected by changing a given symbol."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Name of the symbol to analyse.",
                },
                "depth": {
                    "type": "integer",
                    "description": "Maximum traversal depth (default 3).",
                    "default": 3,
                },
                "scope": {
                    "type": "string",
                    "description": "Graph scope: local_overlay or shared_canonical.",
                    "default": GraphScope.LOCAL_OVERLAY.value,
                },
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="axon_dead_code",
        description="List all symbols detected as dead (unreachable) code.",
        inputSchema={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": "Graph scope: local_overlay or shared_canonical.",
                    "default": GraphScope.LOCAL_OVERLAY.value,
                },
            },
        },
    ),
    Tool(
        name="axon_detect_changes",
        description=(
            "Parse a git diff and map changed files/lines to affected symbols "
            "in the knowledge graph."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "diff": {
                    "type": "string",
                    "description": "Raw git diff output.",
                },
                "scope": {
                    "type": "string",
                    "description": "Graph scope: local_overlay or shared_canonical.",
                    "default": GraphScope.LOCAL_OVERLAY.value,
                },
            },
            "required": ["diff"],
        },
    ),
    Tool(
        name="axon_cypher",
        description="Execute a raw Cypher query against the knowledge graph.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Cypher query string.",
                },
                "scope": {
                    "type": "string",
                    "description": "Graph scope: local_overlay or shared_canonical.",
                    "default": GraphScope.LOCAL_OVERLAY.value,
                },
            },
            "required": ["query"],
        },
    ),
]

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return the list of available Axon tools."""
    return TOOLS

def _dispatch_tool(name: str, arguments: dict, storage: StorageBackend) -> str:
    """Synchronous tool dispatch — called directly or via ``asyncio.to_thread``."""
    if name == "axon_list_repos":
        return handle_list_repos()
    elif name == "axon_query":
        return handle_query(storage, arguments.get("query", ""), limit=arguments.get("limit", 20))
    elif name == "axon_context":
        return handle_context(storage, arguments.get("symbol", ""))
    elif name == "axon_impact":
        return handle_impact(storage, arguments.get("symbol", ""), depth=arguments.get("depth", 3))
    elif name == "axon_dead_code":
        return handle_dead_code(storage)
    elif name == "axon_detect_changes":
        return handle_detect_changes(storage, arguments.get("diff", ""))
    elif name == "axon_cypher":
        return handle_cypher(storage, arguments.get("query", ""))
    else:
        return f"Unknown tool: {name}"


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch a tool call to the appropriate handler."""
    try:
        scope = parse_scope(arguments.get("scope"))
        storage = _get_storage(scope)
    except ValueError as exc:
        return [TextContent(type="text", text=str(exc))]
    except FileNotFoundError as exc:
        return [TextContent(type="text", text=str(exc))]

    if _lock is not None:
        async with _lock:
            result = await asyncio.to_thread(_dispatch_tool, name, arguments, storage)
    else:
        result = _dispatch_tool(name, arguments, storage)

    return [TextContent(type="text", text=result)]

@server.list_resources()
async def list_resources() -> list[Resource]:
    """Return the list of available Axon resources."""
    return [
        Resource(
            uri="axon://overview",
            name="Codebase Overview",
            description="High-level statistics about the indexed codebase.",
            mimeType="text/plain",
        ),
        Resource(
            uri="axon://dead-code",
            name="Dead Code Report",
            description="List of all symbols flagged as unreachable.",
            mimeType="text/plain",
        ),
        Resource(
            uri="axon://schema",
            name="Graph Schema",
            description="Description of the Axon knowledge graph schema.",
            mimeType="text/plain",
        ),
    ]

def _dispatch_resource(uri_str: str, storage: StorageBackend) -> str:
    """Synchronous resource dispatch."""
    if uri_str == "axon://overview":
        return get_overview(storage)
    if uri_str == "axon://dead-code":
        return get_dead_code_list(storage)
    if uri_str == "axon://schema":
        return get_schema()
    return f"Unknown resource: {uri_str}"


@server.read_resource()
async def read_resource(uri) -> str:
    """Read the contents of an Axon resource."""
    try:
        storage = _get_storage()
    except FileNotFoundError as exc:
        return str(exc)
    uri_str = str(uri)

    if _lock is not None:
        async with _lock:
            return await asyncio.to_thread(_dispatch_resource, uri_str, storage)
    return _dispatch_resource(uri_str, storage)

async def main() -> None:
    """Run the Axon MCP server over stdio transport."""
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
