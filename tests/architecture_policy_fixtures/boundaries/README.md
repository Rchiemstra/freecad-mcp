# Boundary-policy adversarial fixtures

These fixtures are synthetic source roots for the Phase 2 architecture-policy
scanner. They intentionally do not import the real add-on and must be scanned
with `allowances=()`; production-tree allowances must never make a failing
fixture pass.

`manifest.json` is the test oracle. Each case supplies a root-relative source
file, its expected outcome, the rule code, and the exact offending import or
locator. A policy test may copy a case into a temporary source root, or scan the
directory named by `source_root` directly. It must not infer ownership from
comments: only the source path and imports are evidence.

## Proposed rule semantics

| Rule | Pass condition | Failure condition |
| --- | --- | --- |
| `ARCH101` capability ownership | A module below `capabilities/<subject>/` has exactly that one subject; support modules beneath that same subject are allowed. | A module outside a subject package implements/imports two distinct capability subjects, or a module below one subject imports implementation from another subject. |
| `ARCH102` add-on layer direction | `transport` may depend only on `dispatch` and lower-neutral/shared code; `dispatch` may depend only on `capabilities` and lower-neutral/shared code; `capabilities` may import FreeCAD; `runtime` is a composition root and no layer may import it. | Any import points upward (`dispatch` -> `transport`, `capabilities` -> `dispatch`/`transport`) or any layer imports `runtime`. |
| `ARCH103` runtime locator | A collaborator arrives as a parameter, constructor field, or explicit import. | Production application code defines/calls `_rpc_mod`, dynamically imports an application module, or reads an application module from `sys.modules`. |
| `ARCH104` internal barrel import | Internal application code imports the defining leaf module directly. A package `__init__.py` may re-export public compatibility symbols, but it is not an internal implementation dependency. | An internal module imports a symbol through its own package barrel (for example `from ...types import Record` rather than `from ...types.record import Record`). |

`internal` above excludes external consumers and explicit public compatibility
tests. The production scanner should classify a file as a barrel only when it is
the package `__init__.py`; it must not treat a leaf module named `types.py` as a
barrel.

## Allowances the integrator must derive from the current tree

The real tree has no `transport/`, `dispatch/`, or subject-nested
`capabilities/` directories yet. Do not create a blanket legacy-layer or
namespace allowance: the layer rules apply to new namespaces immediately. The
global ownership backstop still identifies mixed pre-layer façades; those
legacy findings are recorded as individual path/line/column/fingerprint
allowances and cannot waive a new occurrence in the same file.

The only Phase 2 locator allowances must be exact Phase 1 inventory records:

1. every `_rpc_mod` occurrence represented by
   `post_collaboration_compatibility_surface.json:locator_census.current_modules`,
   keyed by path plus AST occurrence position/type;
2. every `dynamic_module_lookups` and `local_import_locators` record from that
   same manifest, keyed by path, line, column, kind/target, and classification.

The policy must reject a new occurrence, a changed occurrence, or an occurrence
outside that exact record set. It must not use path globs, a module-wide waiver,
or silently allow every `sys.modules` access.

For `ARCH104`, derive a separate exact list only after AST resolution identifies
current production internal imports whose resolved target is an `__init__.py`.
Record importer path, line, column, imported module, imported symbol, and the
reason the existing compatibility layout needs the temporary exception. Do not
waive all imports from a package, external imports, or public consumers. There
is no layer-direction allowance at Phase 2. Capability-ownership allowances
cover only exact mixed pre-layer occurrences discovered by the integrated
scanner; new `capabilities/<subject>/` paths receive none.
