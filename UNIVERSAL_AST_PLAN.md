# Universal Code Graph (UCG) Plan for Axon

## Objective
Transform Axon from a multi-language (Python/TS/JS) indexer into a **Universal Code Analysis Engine** that:
1.  Supports **any language** via configuration (no code changes required).
2.  Builds a **Code Property Graph (CPG)** (inspired by Joern) — combining AST, Control Flow, and Data Flow.
3.  Exposes this rich graph to AI editors (Cursor, Claude Code, VS Code) via MCP for advanced documentation, refactoring, and analysis.

## Core Architecture Changes

### 1. Universal Configuration-Driven Parser
Replace hardcoded `PythonParser` and `TypeScriptParser` with a single `UniversalParser` that reads language definitions from YAML/JSON.

**Configuration Structure (`languages.yaml`):**
```yaml
python:
  extensions: [.py]
  grammar: tree-sitter-python
  nodes:
    function: 
      - function_definition
    class:
      - class_definition
    call:
      - call
    import:
      - import_statement
      - import_from_statement
  fields:
    name: name
    body: body
    parameters: parameters
    return_type: return_type

go:
  extensions: [.go]
  grammar: tree-sitter-go
  nodes:
    function:
      - function_declaration
      - method_declaration
    class:
      - type_declaration  # struct
    call:
      - call_expression
```

### 2. Enhanced Graph Schema (The "John/CPG" Model)
Expand the KuzuDB schema to support finer-grained AST and Flow nodes.

**New Node Types:**
-   `AST_NODE`: Generic syntax tree node (If, For, While, Block, Assignment).
-   `VARIABLE`: Variable declaration/usage (distinct from Function/Class).

**New Relationship Types:**
-   `PARENT_OF`: Structural AST hierarchy.
-   `FLOWS_TO`: Control flow (Next statement).
-   `READS` / `WRITES`: Data flow (Variable usage).

### 3. End-to-End Workflow
1.  **User** runs `axon analyze .` on *any* codebase (e.g., Rust, Go, Ruby).
2.  **Axon** detects language via extension -> loads `config.yaml`.
3.  **UniversalParser** walks the Tree-sitter tree using the config mapping.
4.  **Graph Construction**: Builds the CPG in KuzuDB.
5.  **MCP Server**: Exposes `axon_query_ast`, `axon_get_flow` to the editor.
6.  **Editor (Cursor/Claude)**: Uses this to answer "Where is this variable modified?" or "Generate docs for this flow".

## Implementation Plan

### Phase 1: Universal Parser Infrastructure (Immediate)
-   [ ] Create `src/axon/core/parsers/universal.py`.
-   [ ] Define `LanguageConfig` data structure.
-   [ ] Create `src/axon/config/grammars/` for language definitions.
-   [ ] Port `python` and `typescript` to this new system to verify parity.

### Phase 2: Graph Schema Expansion (CPG-Lite)
-   [ ] Update `src/axon/core/graph/model.py` to include `AST_NODE` and `VARIABLE`.
-   [ ] Update `kuzu_backend.py` to store these new nodes/edges.
-   [ ] Implement "Statement Extraction" in `UniversalParser` (not just top-level definitions).

### Phase 3: Editor Integration & Documentation
-   [ ] Add `axon_dump_ast` tool to MCP.
-   [ ] Update `axon_query` to support structural queries (e.g., "Find all functions calling X inside a loop").
-   [ ] Generate Markdown docs from the graph automatically.

## Next Step
I will start by implementing **Phase 1**: The `UniversalParser` and the configuration system, effectively enabling "Any Language" support immediately for definition extraction.
