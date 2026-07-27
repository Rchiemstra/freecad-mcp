# Transactions and rollback

`GuiMutationTransaction` reports whether a transaction was enabled, started,
committed, or aborted, plus every rollback error. Validation happens before
commit:

```text
health before → open → execute → recompute → validate
              → commit when healthy
              → abort on failure/degradation → verify final health
```

Coverage values are:

- `complete`: all declared effects are reversible by the reported mechanism.
- `document_only`: declared FreeCAD document state is transactional.
- `partial`: document and filesystem/external effects have different guarantees.
- `unavailable`: no trustworthy outer rollback exists.

Exports and save operations report `partial`; arbitrary live public Python
reports `unavailable` with rollback policy `none`. Signed generated operations
use their typed operation identity and report their actual document coverage.
Document close is terminal and reports unavailable live-document validation.

Rollback failure produces `TRANSACTION_ROLLBACK_FAILED`, a degraded result, the
collected `abort_errors`, and invalid/degraded health. No response claims that
filesystem exports were undone by a FreeCAD document transaction.
