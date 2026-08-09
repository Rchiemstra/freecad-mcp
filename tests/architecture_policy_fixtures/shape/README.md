# Phase 2 shape-policy fixtures

These files are deliberately tiny, synthetic Python modules.  They are **not**
application code and must be read by the architecture-policy tests as source
fixtures; they must never be imported by the MCP server.

`manifest.json` is the machine-readable contract.  Each case names the policy
rule, expected verdict, diagnostic, and threshold (where applicable).  The
fixtures are intentionally adversarial: passing a file because it is short,
or failing it because it has several classes, is a defect in the replacement
policy.

## Policy boundary represented here

* A compatibility shim is declarative when its executable top-level statements
  are a module docstring, imports, an explicit literal `__all__`, immutable
  aliases/constants, and (where needed) the named `DEPRECATION` metadata
  mapping. It owns no function/class, mutable registry/cache, runtime lookup,
  or import-time call. Import-plus-`__all__` façades are recognized
  structurally, so alternate prose cannot evade the rule.
* A package's explicit `__all__` is limited to **16** public symbols.  Sixteen
  is intentionally generous for one coherent subject (types, errors, and a
  small factory); it is low enough that a package cannot become the normal
  public home for an entire server façade.  The test has both an exactly-at-
  budget pass case and a 17-symbol failure. An explicit surface that cannot be
  evaluated statically fails closed; augmented and dynamic forms have separate
  adversarial fixtures.
* Several related immutable value classes in one module are allowed.  This
  replaces the retired one-class-per-file rule and makes ownership, rather
  than physical file shape, decisive.
* A public module is rejected when its public surface spans unrelated capability
  families, even if it is short.  The giant-facade and mixed-grab-bag cases
  exercise two different evasions of that rule.
* Function complexity remains Ruff's responsibility. `ruff_c901_complexity.txt`
  is non-discoverable source that the focused test sends to Ruff with a `.py`
  logical filename. It must produce `C901` without becoming an architecture
  finding or poisoning touched-file Ruff.

## Exact current-tree allowance strategy

The production-policy implementation must not grant blanket glob allowances.
Every legacy exception is one normalized code/path/line/column/fingerprint
record with a reason and removal phase. The full production lint audits the
mapping against raw findings: unused, moved, changed, or missing occurrences
fail as stale, while a new finding in an allowed file remains unallowed. One
record suppresses only its own structural finding and never waives another
architecture rule or Ruff. New packages receive no allowance.

The fixture corpus intentionally contains no allowance case: it proves the
default rule and makes any real-tree exception visible in the integrator-owned
mapping rather than normalizing it here.
