# Document health

Typed mutations capture a preflight snapshot, execute, recompute according to
their method policy, validate, and compare a postflight snapshot. Results
separate pre-existing problems from newly introduced problems and report
created, deleted, modified, and unexpected objects.

Profiles:

- `none`: validation deliberately skipped; verdict `unknown`.
- `minimal`: identity, object list, state, dirty flag, and bounded signatures.
- `default`: minimal checks plus affected-shape and Body/Tip validation.
- `full`: checks every relevant shape and is used for checkpoints/finalization.

Verdicts:

- `healthy`: no new errors and only expected changes.
- `warning`: pre-existing errors remain or unexpected non-invalid changes exist.
- `degraded`: new recompute/state/shape/Body-Tip errors.
- `invalid`: validation, restore, save/reopen, or rollback itself failed.
- `unknown`: validation was skipped or unavailable.

A degraded/invalid attempted mutation is aborted before commit where a document
transaction exists. If rollback restores the preflight state, the result reports
both `attempted_verdict` and final health. An unrelated declared-outside-scope
document change is degraded and never silently accepted.

Default validation hashes only bounded object/affected geometry signals; it
does not serialize all shapes for minor property edits. Save/finalize adds the
existing reopen/recompute/domain validation evidence.
