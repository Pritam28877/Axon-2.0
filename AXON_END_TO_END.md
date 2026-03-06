# Axon End-to-End

## 1. What Axon Is

Axon is a local code intelligence engine that turns a source repository into a queryable knowledge graph.

Instead of treating code as plain text, Axon parses supported source files, extracts structural entities such as files, functions, classes, methods, imports, calls, inheritance, and type references, and stores that structure in a graph database.

That graph is then exposed through:

- a CLI for developers
- an MCP server for coding agents
- search and graph traversal primitives for impact analysis and code understanding

At a high level, Axon answers questions like:

- what symbols exist in this repo
- where is a symbol defined
- what calls this function
- what does this class depend on
- what code is dead
- what parts of the system are clustered together
- what execution flows exist through the codebase


## 2. Core Goal

The core Axon workflow is:

1. Walk a repository.
2. Parse supported source files.
3. Build an in-memory knowledge graph.
4. Persist that graph into local storage.
5. Expose that graph to users and agents through CLI and MCP tools.

In the current codebase, Axon is primarily a local-first code graph engine.

With the recent additions in this branch, it also now has the foundation for a two-tier storage layout:

- `local_overlay`: the local mutable graph for current repo work
- `shared_canonical`: a second graph location intended for merge-only or published canonical state

The two-tier model is scaffolded now. Full merge-only publication and snapshot lifecycle are not implemented yet.


## 3. Main Runtime Pieces

The main runtime pieces in this repo are:

- [src/axon/cli/main.py](/e:/ailocaly/axon/src/axon/cli/main.py)
- [src/axon/mcp/server.py](/e:/ailocaly/axon/src/axon/mcp/server.py)
- [src/axon/core/ingestion/pipeline.py](/e:/ailocaly/axon/src/axon/core/ingestion/pipeline.py)
- [src/axon/core/storage/kuzu_backend.py](/e:/ailocaly/axon/src/axon/core/storage/kuzu_backend.py)
- [src/axon/core/storage/runtime.py](/e:/ailocaly/axon/src/axon/core/storage/runtime.py)
- [src/axon/core/storage/provisioning.py](/e:/ailocaly/axon/src/axon/core/storage/provisioning.py)
- [src/axon/mcp/tools.py](/e:/ailocaly/axon/src/axon/mcp/tools.py)
- [src/axon/mcp/resources.py](/e:/ailocaly/axon/src/axon/mcp/resources.py)

These map cleanly to:

- ingestion
- graph modeling
- persistence
- query execution
- interactive access
- two-tier storage provisioning


## 4. End-to-End Flow

### 4.1 Normal indexing flow

The normal indexing path is:

1. User runs `axon analyze <repo>`.
2. Axon walks the repository and filters supported files.
3. Axon runs the ingestion pipeline.
4. Axon builds an in-memory `KnowledgeGraph`.
5. Axon bulk-loads that graph into KuzuDB.
6. Axon writes repo metadata to `.axon/meta.json`.
7. CLI and MCP tools query the resulting graph.

### 4.2 Query flow

The normal query path is:

1. User or agent invokes a CLI command or MCP tool.
2. Axon resolves the storage scope.
3. Axon opens the graph backend.
4. Axon executes search or traversal against the graph.
5. Axon formats human-readable output.

### 4.3 Two-tier provisioning flow

The new provisioning path is:

1. User runs `axon provision <repo>`.
2. Axon creates the `.axon` directory structure.
3. Axon provisions:
   - local overlay path
   - shared canonical path
   - shared manifest path
4. Axon initializes the shared canonical Kuzu store so it is queryable.
5. Axon writes metadata describing both scopes.
6. Optionally, Axon runs a full local index immediately.


## 5. Repository Walking and File Discovery

Axon starts by walking the repository.

Key files involved:

- [src/axon/core/ingestion/walker.py](/e:/ailocaly/axon/src/axon/core/ingestion/walker.py)
- [src/axon/config/ignore.py](/e:/ailocaly/axon/src/axon/config/ignore.py)
- [src/axon/config/languages.py](/e:/ailocaly/axon/src/axon/config/languages.py)

What happens:

- `.gitignore` is loaded
- ignored paths are skipped
- unsupported file extensions are skipped
- supported files are read into `FileEntry` records

Language support is extension-driven. Current language detection comes from [languages.py](/e:/ailocaly/axon/src/axon/config/languages.py), which maps file extensions to language names and Tree-sitter configs.

Current supported language families include:

- Python
- TypeScript
- JavaScript
- Go
- Rust
- Java
- C++


## 6. Parsing and Structural Extraction

Once files are collected, Axon runs the ingestion pipeline in [pipeline.py](/e:/ailocaly/axon/src/axon/core/ingestion/pipeline.py).

The pipeline is multi-phase.

### 6.1 Structure phase

[src/axon/core/ingestion/structure.py](/e:/ailocaly/axon/src/axon/core/ingestion/structure.py)

This creates file and folder nodes and their containment edges.

This gives Axon a structural skeleton of the repo before code-level parsing begins.

### 6.2 Parsing phase

[src/axon/core/ingestion/parser_phase.py](/e:/ailocaly/axon/src/axon/core/ingestion/parser_phase.py)

This uses language-specific parsers to extract symbols such as:

- functions
- classes
- methods
- interfaces
- enums
- type aliases

Parser logic lives under:

- [src/axon/core/parsers/python_lang.py](/e:/ailocaly/axon/src/axon/core/parsers/python_lang.py)
- [src/axon/core/parsers/typescript.py](/e:/ailocaly/axon/src/axon/core/parsers/typescript.py)
- [src/axon/core/parsers/universal.py](/e:/ailocaly/axon/src/axon/core/parsers/universal.py)

### 6.3 Import resolution

[src/axon/core/ingestion/imports.py](/e:/ailocaly/axon/src/axon/core/ingestion/imports.py)

This adds import relationships between files and code entities.

### 6.4 Call tracing

[src/axon/core/ingestion/calls.py](/e:/ailocaly/axon/src/axon/core/ingestion/calls.py)

This adds `CALLS` edges between symbols.

This is one of the most important steps because later impact analysis and flow analysis depend on it.

### 6.5 Heritage extraction

[src/axon/core/ingestion/heritage.py](/e:/ailocaly/axon/src/axon/core/ingestion/heritage.py)

This adds:

- `EXTENDS`
- `IMPLEMENTS`

relationships where applicable.

### 6.6 Type analysis

[src/axon/core/ingestion/types.py](/e:/ailocaly/axon/src/axon/core/ingestion/types.py)

This adds `USES_TYPE` relationships from functions or methods to referenced types.


## 7. Higher-Level Analysis Phases

After structural extraction, Axon runs higher-level enrichment passes.

### 7.1 Community detection

[src/axon/core/ingestion/community.py](/e:/ailocaly/axon/src/axon/core/ingestion/community.py)

This groups symbols into communities using graph clustering.

This gives Axon an approximate map of code neighborhoods or functional clusters.

### 7.2 Process detection

[src/axon/core/ingestion/processes.py](/e:/ailocaly/axon/src/axon/core/ingestion/processes.py)

This tries to identify execution flows starting from likely entry points.

### 7.3 Dead code detection

[src/axon/core/ingestion/dead_code.py](/e:/ailocaly/axon/src/axon/core/ingestion/dead_code.py)

This marks symbols as dead if they appear unreachable after Axon’s exemptions and graph analysis.

### 7.4 Change coupling

[src/axon/core/ingestion/coupling.py](/e:/ailocaly/axon/src/axon/core/ingestion/coupling.py)

This uses git history to infer files or entities that tend to change together.


## 8. In-Memory Graph Model

The graph model is defined in:

- [src/axon/core/graph/model.py](/e:/ailocaly/axon/src/axon/core/graph/model.py)
- [src/axon/core/graph/graph.py](/e:/ailocaly/axon/src/axon/core/graph/graph.py)

The main concepts are:

- `GraphNode`
- `GraphRelationship`
- `KnowledgeGraph`

Important node labels include:

- `FILE`
- `FOLDER`
- `FUNCTION`
- `CLASS`
- `METHOD`
- `INTERFACE`
- `TYPE_ALIAS`
- `ENUM`
- `COMMUNITY`
- `PROCESS`

Important relationship types include:

- `CONTAINS`
- `DEFINES`
- `CALLS`
- `IMPORTS`
- `EXTENDS`
- `IMPLEMENTS`
- `USES_TYPE`
- `MEMBER_OF`
- `STEP_IN_PROCESS`
- `COUPLED_WITH`

This graph is built in memory first and only later written to storage.


## 9. Storage Layer

The storage contract is defined in [src/axon/core/storage/base.py](/e:/ailocaly/axon/src/axon/core/storage/base.py).

The current concrete backend is KuzuDB:

- [src/axon/core/storage/kuzu_backend.py](/e:/ailocaly/axon/src/axon/core/storage/kuzu_backend.py)

What Kuzu is used for:

- node storage
- relationship storage
- full-text search
- vector storage
- Cypher execution
- traversal-backed lookups

The backend supports:

- insert/upsert of nodes
- insert/upsert of relationships
- delete by file
- full graph bulk load
- full-text search
- fuzzy search
- vector search
- graph traversal
- raw query execution

Axon currently uses Kuzu as an embedded local graph database.


## 10. Search and Query Behavior

Search logic lives in [src/axon/core/search/hybrid.py](/e:/ailocaly/axon/src/axon/core/search/hybrid.py).

Axon combines:

- FTS
- fuzzy search
- optional vector search

and merges the result lists using reciprocal rank fusion.

This means a query can match:

- exact names
- approximate names
- keyword content
- semantic similarity if embeddings are available


## 11. CLI Layer

The CLI lives in [src/axon/cli/main.py](/e:/ailocaly/axon/src/axon/cli/main.py).

Important commands:

- `axon analyze`
- `axon provision`
- `axon status`
- `axon query`
- `axon context`
- `axon impact`
- `axon dead-code`
- `axon cypher`
- `axon watch`
- `axon diff`
- `axon mcp`
- `axon serve`

### 11.1 `axon analyze`

Builds a local graph index for a repository.

### 11.2 `axon provision`

This is the new two-tier provisioning command added in this branch.

It creates:

- local overlay storage path
- shared canonical storage path
- shared manifest file
- scope metadata in `.axon/meta.json`

It can also immediately run local indexing.

### 11.3 `axon query`

Runs hybrid search and prints ranked results.

### 11.4 `axon context`

Resolves a symbol and shows:

- callers
- callees
- type references
- dead-code state

### 11.5 `axon impact`

Traces blast radius through the call graph.

### 11.6 `axon cypher`

Executes read-only raw queries against the graph backend.


## 12. MCP Layer

The MCP server lives in [src/axon/mcp/server.py](/e:/ailocaly/axon/src/axon/mcp/server.py).

The handlers live in:

- [src/axon/mcp/tools.py](/e:/ailocaly/axon/src/axon/mcp/tools.py)
- [src/axon/mcp/resources.py](/e:/ailocaly/axon/src/axon/mcp/resources.py)

This server exposes graph intelligence to coding agents over stdio.

Important MCP tools:

- `axon_list_repos`
- `axon_query`
- `axon_context`
- `axon_impact`
- `axon_dead_code`
- `axon_detect_changes`
- `axon_cypher`

Important MCP resources:

- `axon://overview`
- `axon://dead-code`
- `axon://schema`

The server resolves storage lazily and dispatches calls to the right backend.


## 13. Local Overlay vs Shared Canonical

This is the new architectural direction.

### 13.1 Local overlay

`local_overlay` is the repo-local mutable graph.

Default path:

- `.axon/kuzu`

This is where local indexing currently writes.

### 13.2 Shared canonical

`shared_canonical` is the second graph scope meant for canonical, merge-only, or published graph state.

Default path:

- `.axon/shared/kuzu`

At the moment, Axon provisions and initializes this store, but does not publish into it automatically.

### 13.3 Runtime resolution

Scope resolution now lives in [src/axon/core/storage/runtime.py](/e:/ailocaly/axon/src/axon/core/storage/runtime.py).

The key concepts are:

- `GraphScope`
- `StorageRuntime`
- `StorageLocation`

This gives CLI and MCP a consistent way to select:

- `local_overlay`
- `shared_canonical`


## 14. Provisioning and Scope Metadata

Provisioning logic is in [src/axon/core/storage/provisioning.py](/e:/ailocaly/axon/src/axon/core/storage/provisioning.py).

When `axon provision <repo>` runs, Axon writes:

- `.axon/meta.json`
- `.axon/shared/meta.json`
- `.axon/shared/manifests/active.json`

### 14.1 Local meta

The repo-local metadata tracks:

- repo name
- repo path
- repo id
- local indexing stats
- last indexed time
- scope definitions

The `scopes` section now records:

- local overlay path
- shared canonical path
- backend type
- readiness
- whether the scope is currently indexed

### 14.2 Shared meta

The shared metadata tracks:

- canonical scope identity
- backend type
- initialization time
- active snapshot placeholder
- publish placeholders

### 14.3 Manifest

The shared manifest tracks:

- repo id
- backend
- canonical path
- active snapshot placeholder
- generation time

This is the basis for a later snapshot publication system.


## 15. Watch Mode

Watch mode lives in [src/axon/core/ingestion/watcher.py](/e:/ailocaly/axon/src/axon/core/ingestion/watcher.py).

How it works:

1. Watches the repo for file changes.
2. Filters unsupported and ignored files.
3. Reindexes changed files only.
4. Deletes graph nodes for removed files.
5. Periodically reruns broader analysis passes.

Important recent fix:

Incremental refresh no longer depends on a Kuzu-only method through the protocol path. Search index refresh is now optional and backend-safe via the base storage helper.


## 16. Branch Diffing

Diffing logic lives in [src/axon/core/diff.py](/e:/ailocaly/axon/src/axon/core/diff.py).

This feature compares graph structure between branches using graph snapshots built from each side.

This is related to, but separate from, the two-tier architecture.

Diffing gives temporary branch comparison.

The future shared canonical model is about durable published graph state.


## 17. What Was Added in This Branch

This branch introduces the foundation for the two-tier architecture.

### 17.1 Scope-aware runtime

Added in:

- [src/axon/core/storage/runtime.py](/e:/ailocaly/axon/src/axon/core/storage/runtime.py)

This lets Axon resolve and open storage based on scope.

### 17.2 Scope-aware CLI and MCP queries

Added to:

- [src/axon/cli/main.py](/e:/ailocaly/axon/src/axon/cli/main.py)
- [src/axon/mcp/server.py](/e:/ailocaly/axon/src/axon/mcp/server.py)

Commands and tools can now query:

- `local_overlay`
- `shared_canonical`

### 17.3 Provisioning command

Added:

- `axon provision`

This creates two-tier storage layout and scope metadata.

### 17.4 Metadata preservation fix

`axon analyze` now merges with existing metadata instead of overwriting scope provisioning info.

### 17.5 Config contract fix

[src/axon/config/languages.py](/e:/ailocaly/axon/src/axon/config/languages.py) now again exposes:

- `SUPPORTED_EXTENSIONS`
- `get_language`

That fix was necessary because the public config API had drifted from the implementation.


## 18. NLP-to-Sql Example

The repo [NLP-to-Sql](/e:/ailocaly/axon/NLP-to-Sql) was provisioned and indexed using Axon.

### 18.1 What Axon created

Axon created:

- [NLP-to-Sql/.axon/meta.json](/e:/ailocaly/axon/NLP-to-Sql/.axon/meta.json)
- [NLP-to-Sql/.axon/kuzu](/e:/ailocaly/axon/NLP-to-Sql/.axon/kuzu)
- [NLP-to-Sql/.axon/shared/meta.json](/e:/ailocaly/axon/NLP-to-Sql/.axon/shared/meta.json)
- [NLP-to-Sql/.axon/shared/kuzu](/e:/ailocaly/axon/NLP-to-Sql/.axon/shared/kuzu)
- [NLP-to-Sql/.axon/shared/manifests/active.json](/e:/ailocaly/axon/NLP-to-Sql/.axon/shared/manifests/active.json)

### 18.2 What Axon indexed

At the time of provisioning, the local overlay index for `NLP-to-Sql` contained:

- 15 files
- 54 symbols
- 135 relationships
- 6 communities
- 1 process
- 14 dead-code symbols

### 18.3 What this means

For `NLP-to-Sql`, Axon can now:

- search classes, methods, and files
- inspect symbol context
- run impact analysis
- expose the repo graph through MCP
- distinguish between local overlay and shared canonical paths

The shared canonical graph for `NLP-to-Sql` is provisioned and queryable, but empty because no publication pipeline exists yet.


## 19. Current Limitations

Axon does not yet fully implement the complete target architecture from the LadybugDB plan.

What is still missing:

- LadybugDB backend
- canonical snapshot publishing
- merge-only CI ingestion
- active snapshot promotion
- rollback to previous canonical snapshot
- dual-scope merged retrieval logic
- snapshot delta artifacts
- service, endpoint, migration, and DB-table graph enrichment from the target plan

So the current state is:

- local code graph intelligence is implemented
- two-tier storage scaffolding is implemented
- shared canonical publication lifecycle is not yet implemented


## 20. Practical Command Summary

### Provision a repo

```bash
axon provision /path/to/repo
```

### Provision without immediate indexing

```bash
axon provision /path/to/repo --skip-index-local
```

### Rebuild local overlay

```bash
axon analyze /path/to/repo --full
```

### Query the local overlay

```bash
axon query "QueryProcessingService" --scope local_overlay
```

### Query the shared canonical graph

```bash
axon cypher "MATCH (n) RETURN count(n)" --scope shared_canonical
```


## 21. Conceptual Summary

Axon is doing four things end to end.

First, it reads source code and extracts structure.

Second, it converts that structure into a graph that represents how the codebase is connected.

Third, it persists that graph into storage that can be searched and traversed efficiently.

Fourth, it exposes that graph to humans and coding agents through a CLI and MCP server.

With the additions in this branch, Axon now also prepares a repo for a two-tier graph future by provisioning:

- a local mutable graph
- a shared canonical graph location
- metadata and manifests needed for future publication workflows

That is the current end-to-end behavior of Axon in this repo.
