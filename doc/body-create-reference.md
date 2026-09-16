# Body creation reference implementation

`body_create` is the reference for migrating a CAD mutation to typed RPC. Its
public arguments remain `doc_name` and `body_name`. Native FreeCAD owns the
transaction, final recompute, read-only postcondition interval, and rollback.

## Acceptance evidence

| Acceptance area | Result | Regression evidence |
| --- | --- | --- |
| Native recompute before inspection | PASS | Native phase-order test; native property and structural writes during postflight are rejected and rolled back. |
| Native capability required | PASS | Production bridge refuses documents without the native postcondition API before apply. |
| Exact admitted document | PASS | One lookup in the bridge; native apply and inspection must receive the same object. |
| Strict public success shape | PASS | Exact version/boolean checks, required fields and contradictory error, rollback, native-status and completion evidence are tested. |
| MCP static contract | PASS | The public client re-export and concrete MCP return type are followed by mypy. Negative examples reject swapped names, missing postconditions and writes through the read interface. Body modules reject explicit and unfollowed-import `Any`. |
| Automatic editor/CI mypy gate | PASS | `pyproject.toml` supplies default targets and per-module strictness. The provided editor workspace enables mypy. Parent Woodpecker lint executes the same architecture/type gate. |
| Public JSON-RPC contract | PASS | A real MCP memory session initializes, discovers the registered schema and calls the tool. Invalid types never reach JSON-RPC; authenticated request values and success/failure/uncertain results are checked. |
| Native qualification matrix | PASS | Apply, recompute, inspection and validation failures restore native property values/schema, geometry, placement, expressions, links, Body membership, Tip, object state and document/object/property revisions. Rollback failure remains uncertain and fences later mutations. |
| Deliberately broken variants | PASS | Separate mutants release cached success after native rejection and omit the postcondition check. Both fail the behavioral gate. Other mutants cover fallback, document resolution, inspection ordering, validation bypass and leaf-owned recompute. |
| Committed/unknown response outcome | PASS | Unknown objects, non-objects, transport failures and GUI timeouts remain uncertain. Valid uncertain responses round-trip without changing their evidence. Malformed committed results retain `committed=true` and prohibit replay. |

The wire test substitutes the FreeCAD HTTP transport to inspect exact bytes; it
does not substitute MCP registration, discovery, schema dispatch, or result
serialization. The separate native lane executes the production bridge and Body
handler inside the branch-built FreeCAD runtime. The native C++ lane verifies
the coordinator and Python binding themselves.

## Code boundaries

1. [`body_create.py`](../addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/body_create.py)
   validates the request, creates the Body and records its actual identity.
   Inspection verifies that the same object still exists and is a PartDesign
   Body. It contains no transaction or recompute operations.
2. [`body_mutation.py`](../addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/body_mutation.py)
   owns the fixed orchestration policy. Apply and inspection raise ordinary
   typed errors; the adapter captures them provisionally and releases them only
   after a recognized native rollback result. An exception or unknown native
   status is not proof of rollback.
3. [`collaboration_api.py`](../addon/FreeCADMCP/collaboration_api.py)
   resolves one document, checks its native capability and binds both callbacks
   to it. It normalizes FreeCAD's missing-document `NameError` at lookup.
4. [`body_create_contract.py`](../src/freecad_mcp/_shared/protocol/body_create_contract.py)
   validates untrusted responses. It never interprets a malformed response as a
   proven rejection. Its vendored add-on copy must be identical; the gate checks
   this. Native terminal statuses are interpreted in the native adapter, not by
   passing an unversioned native dictionary through the wire parser.
5. [`body_ops.py`](../src/freecad_mcp/operations/parametric_ops/body_ops.py)
   sends the typed request, parses the response and returns a concrete
   `CallToolResult`. Transport loss produces a Body-specific uncertain result.
   The legacy Body Tip implementation lives separately.

Use `object` at an untrusted boundary, `Protocol` for injected capabilities,
`NewType` for names with different meanings, and discriminated `TypedDict`
variants for the wire result. Construct success only after native commit.
Preserve the existing public API while keeping legacy implementations outside
the reference mutation's typed slice.

## Repeating qualification

From this repository root:

```sh
uv sync --locked --extra dev
uv run python ci/qualify_body_create.py
```

The command runs the architecture gate, strict mypy and the focused Python/MCP
regression lane. The mypy configuration applies explicit-`Any` restrictions only
to Body modules, while following the shared client and result types. Running
`uv run mypy` or checking a Body file in an editor uses those same rules.

Open [`body-create.code-workspace`](../body-create.code-workspace) in VS Code with
its recommended Python and mypy extensions to check changes in the project
environment. Other mypy integrations can use `pyproject.toml` directly.

With the branch-built FreeCAD libraries and Mod directories on `PYTHONPATH` and
the native library search path:

```sh
python3 ci/qualify_body_create.py --native
```

This lane imports real FreeCAD before test collection and enables the required
native capability checks. A missing runtime is an error. Python proxy objects
serve as fault injectors: their identities are compared, but arbitrary Python
attributes are not claimed to be native transactional state.

The parent CI entry point is:

```sh
sh ci/woodpecker/freecad-mcp-lint.sh
```

Run it from the FreeCAD parent checkout. It installs the minimum supported MCP
SDK 1.26.0 and pinned mypy 2.3.1 before invoking the contract gate. The SDK minimum
is intentional: the former 1.13 lock treated postponed `Context` annotations as
client inputs and lost `isError` when adapting native tool results.

## Qualified baseline

On 2026-09-13 the focused lane passed **218 tests**, the branch-built native lane
passed **16 tests**, and the native collaboration/binding lane passed **77 tests**.
Ruff and the architecture/type gate passed. The actual parent Woodpecker lint
script also passed in a clean `python:3.12` container. Native C++ code was unchanged in this
follow-up; the existing native build was checked by SHA-256:

| Artifact | SHA-256 |
| --- | --- |
| `libFreeCADApp.so` | `79953D6B37CA536A8F76C01685C79168C5A5F876FC7D85743276EA61167A16BA` |
| `App_tests_run` | `82D2A626B00909EC986F3730D3077F41CCF6F5818D392BA9DDCB6C98EFD32286` |

The tests used the current working changes on parent base
`b253505340ce45d0d6720bc9894f0e063e6196e5` and MCP base
`c4fa4f5562e2319606945efc7c1aa0767ad5f9d9`. The native run used
`freecad-ci-mcp:24.04-phase1`, with this checkout mounted read-only and
`build_docker` supplying the native libraries. Native C++ selection:

```text
DocumentCollaborationServiceTest.*:DocumentCollaborationPythonCompatibilityTest.*
```

These results qualify this slice and its adjacent MCP compatibility tests; they
are not a claim that the complete FreeCAD or platform-specific Python suite was run.
