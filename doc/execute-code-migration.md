# Execute-code migration

Prefer typed tools. For a normal PartDesign part:

```text
body_create
→ sketch_create / sketch_attach
→ sketch_add_* / sketch_add_constraint
→ get_sketch_diagnostics
→ pad_feature / pocket_feature
→ recompute_document
→ finalize_document_edit
```

Execution telemetry and benchmark reports distinguish
`public_execute_code`, `generated_internal_execute`, `typed_direct_rpc`,
`read_only_worker_analysis`, and `deprecated_execute_code_async`. Internal
signed templates do not count as agent-selected arbitrary Python.

Public source is parsed with AST only. Reports store imported API families,
call patterns, declared scope, mode/read-only classification, a source hash,
and an AST pattern hash—not raw code. When a known typed workflow matches, the
compatibility execution remains allowed and the result adds
`TYPED_TOOL_AVAILABLE` with preferred tool names. Generated operations do not
receive that warning.

Read-only public Python always runs against an immutable FreeCADCmd snapshot.
Mutating public Python remains disabled by default in enforce mode, requires
explicit declared/leased document scope when enabled, and reports rollback
coverage `unavailable`. `execute_code_async` remains available in off/observe
for compatibility, emits deprecation telemetry, and directs callers to worker
jobs or MCP Tasks. It is blocked in enforce mode.
