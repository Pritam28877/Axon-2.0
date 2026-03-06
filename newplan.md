# End-to-end Architecture Plan: Local AST Intelligence + Shared LadybugDB Knowledge Graph

## 1) Goal and Non-Negotiables

Build a two-tier code intelligence system for AI coding agents:

- **Tier A (Local, fast, mutable):** AST-driven local index updates on save/checkout.
- **Tier B (Shared, stable, merge-only):** LadybugDB graph updated only from merged commits on `main`/`trunk`.

Non-negotiables:

- Local developer experience must remain fast and incremental.
- Shared graph must never include unmerged branch state.
- Retrieval must support exact, structural, and semantic search in one workflow.
- Design must scale to many services, repos, APIs, and DB schemas.

---

## 2) Research Summary and Decision

## 2.1 What was reviewed

- Official docs and specs:
  - Tree-sitter official repository and docs.
  - LadybugDB docs and repository.
  - Joern docs and Code Property Graph specification.
- Academic references:
  - Original CPG paper (Yamaguchi et al., IEEE S&P 2014).
  - Recent work on scalable code-graph traversal and compressed CPG patterns.
- Existing tool patterns:
  - Axon (this repository): multi-phase tree-sitter ingestion + graph storage + vector/FTS support.
  - Open-source graph-RAG/code-intelligence systems using tree-sitter + graph + vectors.

## 2.2 Approach comparison

| Approach | Strengths | Weaknesses | Recommendation |
|---|---|---|---|
| Language-native AST only | Rich semantics per language | Hard to scale cross-language | Use selectively for premium languages later |
| Tree-sitter CST/AST-like parsing | Incremental, multi-language, editor-friendly | Needs extra passes for deep semantics | **Primary baseline** |
| Full CPG first (AST+CFG+DFG) | Best deep analysis | Heavy cost/complexity day 1 | Add as phase-2/3 overlay where needed |

## 2.3 Final design choice

- **Use Tree-sitter as baseline parser/indexer now.**
- **Use LadybugDB as shared graph + retrieval backend (Cypher + FTS + vectors).**
- **Introduce CPG-style overlays only for high-value repos/languages after MVP stabilization.**

---

## 3) Target Architecture

## 3.1 Two-tier indexing model

### Tier A: Local Overlay Index (per developer)

- Triggered by file save, branch switch, rebase, and local diff checks.
- Maintains a **local overlay graph** and local embedding cache.
- Can include unmerged state.
- Optimized for low-latency IDE/agent operations.

### Tier B: Shared Canonical Graph (merge-only)

- Produced only in CI/CD from merged commits.
- Represents canonical cross-repo knowledge.
- Versioned by merge SHA and distributed as snapshots/deltas.
- Queried by all agents for global architecture awareness.

## 3.2 Logical components

1. **Change Detector**
   - Local: file watcher + git state.
   - CI: merge SHA diff vs last indexed SHA.
2. **Parser Layer**
   - Tree-sitter incremental parsing.
   - Language adapters normalize extracted entities.
3. **Relationship Extractors**
   - Definitions, imports, calls, inheritance, endpoint mappings, SQL/table links.
4. **Graph Writer**
   - Upserts nodes/edges with stable IDs.
   - Handles deletes and re-linking.
5. **Embedding Pipeline**
   - Creates vectors for symbols/docs.
   - Updates only changed entities.
6. **Query Runtime**
   - Hybrid retrieval: Cypher traversal + FTS + vector search.
7. **Agent Orchestrator**
   - Uses local overlay first, shared graph second.

---

## 4) Code Understanding Design (Local AST Layer)

## 4.1 Extraction targets

Per file, extract:

- Symbols: function, method, class, interface, type alias, enum/module.
- Imports and module dependencies.
- Call sites and probable target symbols.
- Type references and inheritance links.
- Framework metadata (routes/handlers/consumers) when detectable.
- SQL string/table hints for DB linkage.

## 4.2 Stable identity model

- `repo_id = org/repo` (or workspace alias)
- `file_id = repo_id + ":" + normalized_path`
- `symbol_id = repo_id + ":" + file_path + ":" + kind + ":" + fqn + ":" + hash(signature_normalized)`
- `commit_id = git_sha`
- `doc_id = repo_id + ":" + source + ":" + hash(chunk_text)`

Why this works:

- Resistant to line shifts.
- Enables idempotent upserts.
- Cleanly supports deletion and re-parenting.

## 4.3 Incremental local update flow

1. Detect changed files.
2. Re-parse changed files only.
3. Remove stale symbols for those files.
4. Recompute relationships touching changed symbols.
5. Recompute embeddings for changed symbols/docs only.
6. Commit to local overlay store.

Latency targets (guidance):

- Single-file save: sub-second to a few seconds.
- Small batch change: under 5-10 seconds.

---

## 5) Shared Knowledge Layer (LadybugDB)

## 5.1 Graph schema (core)

### Node types

- `Repo`, `Commit`, `File`, `Symbol`, `Import`, `CallSite`
- `Service`, `APIEndpoint`
- `Database`, `DBTable`, `DBColumn`, `Migration`
- `DocChunk`, `ConfigKey`

### Relationship types

- `Repo-[:HAS_COMMIT]->Commit`
- `Repo-[:HAS_FILE]->File`
- `Commit-[:TOUCHED]->File`
- `File-[:DEFINES]->Symbol`
- `Symbol-[:CALLS]->Symbol`
- `Symbol-[:IMPORTS]->Import`
- `Symbol-[:USES_TYPE]->Symbol`
- `Service-[:OWNS_REPO]->Repo`
- `APIEndpoint-[:IMPLEMENTED_BY]->Symbol`
- `Symbol-[:READS_TABLE|WRITES_TABLE]->DBTable`
- `Migration-[:CHANGES_TABLE]->DBTable`
- `DocChunk-[:ABOUT]->Symbol`

## 5.2 Index strategy

- **Primary/unique keys:** stable IDs on key labels.
- **FTS fields:** `Symbol.name`, `Symbol.signature`, `File.path`, `DocChunk.text`, endpoint path/method.
- **Vector index:** embeddings for `Symbol` summaries and `DocChunk`.
- **Traversal-optimized patterns:** IDs + frequent relationship filter properties.

## 5.3 Storage and publication model

- Build graph in CI from merge SHA.
- Publish:
  - Full snapshot (`graph_<sha>.ladybug`).
  - Optional delta bundle (`from_sha -> to_sha`).
- Keep retention window (for rollback and comparison).

---

## 6) Update Policy: Local Immediately, Shared Only After Merge

## 6.1 Local workflow

- Trigger: save/checkout/rebase/manual reindex.
- Update only local overlay.
- Never push local overlay directly into shared graph.

## 6.2 Shared workflow

Trigger:

- Merge into protected branch (`main`/`trunk`).

CI sequence:

1. Checkout merge SHA.
2. Load `last_successful_indexed_sha`.
3. Compute changed/added/deleted files.
4. Re-index impacted subgraph.
5. Run graph integrity + retrieval smoke tests.
6. Publish snapshot/delta + metadata.
7. Mark SHA as active canonical graph version.

Hard gate:

- If indexing fails, previous shared snapshot remains active.

---

## 7) Fast Search and Reasoning Strategy

## 7.1 Hybrid retrieval algorithm

1. **Exact phase (FTS):**
   - Symbol names, endpoint paths, table names, config keys.
2. **Structural expansion (graph traversal):**
   - Callers, callees, owners, DB touchpoints, coupled files.
3. **Semantic phase (vector):**
   - Similar functions/implementations and related docs.
4. **Ranking and context assembly:**
   - Blend confidence from exact + structural + semantic scores.
5. **Agent planning:**
   - Build change plan and blast-radius map before edits.

## 7.2 Example query contract for agent runtime

- `search_text(query, limit, scope)`
- `search_vector(text, limit, scope)`
- `get_node(node_id)`
- `neighbors(node_id, edge_types, hops)`
- `trace_calls(symbol_id, direction, depth)`
- `files_changed_between(base_sha, head_sha)`

Scope behavior:

- `scope=local_overlay` for branch-aware work.
- `scope=shared_canonical` for organization-level context.

---

## 8) Agent Decision Loop: What to Change

For any task request, the agent should:

1. Identify entry points (handlers/commands/public APIs/jobs).
2. Trace downstream and upstream dependencies.
3. Detect contracts (API schemas, DTOs, DB schema, configs).
4. Compute impacted files/services/tables/tests.
5. Propose minimal ordered edit plan.
6. Propose validation commands and rollback notes.

Output requirements:

- Evidence-first plan.
- Explicit assumptions.
- Impact summary by service/repo.
- Test plan and migration plan when relevant.

---

## 9) Implementation Plan (Phased)

## Phase 0: Foundation and contracts

- Finalize graph schema and ID rules.
- Define parser adapter interface and event contracts.
- Define snapshot manifest format.

## Phase 1: Local indexing MVP

- Tree-sitter extraction for current supported languages.
- Local overlay store and incremental updater.
- CLI/MCP query APIs for symbol and dependency exploration.

## Phase 2: Merge-only shared graph pipeline

- CI job triggered on merge to `main`.
- Diff-based impacted reindexing.
- Snapshot artifact publishing and client sync metadata.

## Phase 3: Cross-service and database intelligence

- Endpoint extraction.
- SQL/table lineage extraction.
- Migration linking and service ownership mapping.

## Phase 4: Advanced semantics

- Add optional CPG overlays for selected repos.
- Add type-resolution enrichers via language tooling/LSP.
- Add confidence scoring and drift detection.

## Phase 5: Evaluation and guardrails

- Build benchmark tasks for impact analysis/refactor planning.
- Measure precision, latency, and stale-context incidents.
- Add strict guardrails for safe edit planning.

---

## 10) What Needs to Change in This Codebase

This repository already has a strong base (tree-sitter parsing, multi-phase ingestion, Kuzu backend, watch mode, MCP tools).  
To implement this target system with merge-only shared publication:

## 10.1 Immediate modifications

1. **Storage abstraction expansion**
   - Keep `StorageBackend` contract, add shared-snapshot and overlay methods.
   - Extend local-vs-shared scope support in query APIs.

2. **Ladybug backend integration**
   - Add Ladybug-backed storage implementation in parallel with current backend.
   - Keep backend selection configurable.

3. **Incremental file-level reindex APIs**
   - Add reindex-by-file-set and delete-by-file-set operations.
   - Ensure relationship repair for cross-file edges.

4. **Merge-only publisher pipeline**
   - Add CI entrypoint script:
     - read previous indexed SHA
     - diff file sets
     - run incremental index
     - publish snapshot metadata/artifacts.

5. **Dual-scope query runtime**
   - Read from local overlay first.
   - Fallback/augment with shared canonical graph.

6. **Schema enrichment**
   - Add service/API/DB/migration/doc nodes and relationships.
   - Add corresponding extractors in ingestion pipeline.

## 10.2 File areas to update (repo-specific)

- `src/axon/core/storage/base.py`: extend backend protocol for overlay/snapshot lifecycle.
- `src/axon/core/storage/`: add Ladybug backend and shared snapshot manager.
- `src/axon/core/ingestion/pipeline.py`: add incremental impacted-file pipeline path.
- `src/axon/core/ingestion/`: add endpoint, SQL lineage, migration extractors.
- `src/axon/mcp/server.py`: expose scope-aware retrieval/query tools.
- `README.md`: update architecture diagram and operational modes.
- `tests/core/`: add tests for merge-only publishing, snapshot consistency, and scoped queries.

---

## 11) Reliability, Security, and Operations

## 11.1 Integrity checks

- No dangling edges.
- No duplicate stable IDs.
- Schema-required properties present.
- Snapshot manifest hash matches graph artifact.

## 11.2 Drift checks

- Endpoint graph vs OpenAPI spec drift.
- Table references vs migrations drift.
- Unresolved symbol/call spikes by language.

## 11.3 Security and compliance

- No source exfiltration by default.
- Role-based access for shared graph reads/writes.
- PII-aware handling for docs/chunks in embeddings.

## 11.4 Observability

- Metrics: parse latency, index throughput, query latency, stale-hit ratio.
- Logs: per-phase timing and failure reasons.
- Traces: retrieval phases for explainability.

---

## 12) Agent Prompt (Production-Ready)

Use this prompt for the coding agent that consumes this system:

```text
You are a codebase change-planning agent.

Truth sources:
1) Local overlay index (unmerged branch-aware)
2) Shared canonical graph (merge-only main/trunk snapshots)
3) Repository files

Rules:
1. Retrieve evidence before planning any edits.
2. Prefer local overlay for current-branch truth.
3. Use shared graph for cross-repo/service context.
4. Never assume shared graph contains unmerged changes.
5. Produce the smallest correct blast radius.
6. Explicitly list assumptions and confidence.

Tooling contract:
- graph.search_text(query, limit, scope)
- graph.search_vector(text, limit, scope)
- graph.get_node(node_id, scope)
- graph.neighbors(node_id, hops, edge_types, scope)
- graph.trace_calls(symbol_id, direction, depth, scope)
- repo.read(path)
- repo.grep(pattern)
- git.diff(base, head)

Required response format:
1) Understanding
2) Evidence
3) Impact analysis
4) Ordered change plan (files + modifications)
5) Tests and validation commands
6) Risks (compatibility, performance, security)
```

---

## 13) Architecture Improvements Worth Adding

- **Overlay conflict visualization:** show where local overlay diverges from shared graph.
- **Confidence-weighted relationships:** rank weaker inferred links lower in retrieval.
- **Hotspot prioritization:** blend historical coupling and runtime/service criticality.
- **Schema evolution registry:** version graph schema and auto-run compatibility checks.
- **Policy engine for agent edits:** reject plans without tests or contract updates.

---

## 14) Success Criteria

Ship when all are true:

- Local index updates incrementally with low latency.
- Shared graph is updated only by merge-triggered CI.
- Agents can answer cross-repo dependency questions with grounded evidence.
- Impact plans include files/tests/contracts with high precision.
- Rollback to previous shared snapshot is one operation.

---

## 15) Sources

- Tree-sitter official repository and documentation: https://github.com/tree-sitter/tree-sitter
- LadybugDB repository: https://github.com/LadybugDB/ladybug
- LadybugDB documentation: https://docs.ladybugdb.com/
- Code Property Graph specification: https://cpg.joern.io/
- Joern code property graph docs: https://docs.joern.io/code-property-graph/
- Yamaguchi et al., 2014 (IEEE S&P): https://ieeexplore.ieee.org/document/6956585
- Example open-source implementation pattern (tree-sitter + graph-RAG): https://github.com/vitali87/code-graph-rag
