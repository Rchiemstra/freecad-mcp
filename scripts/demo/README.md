# Strawberry picker recording

A scripted replay using real MCP tools on the companion FreeCAD fork. No language
model runs during replay. freecad-mcp is its own project.

The seven chapters cover spreadsheet-driven regeneration, the force budget, a pick
motion, clearance measurements, a 10 mm clash and the retained nose fix, actual jaw
FEM, and mass/parts/exports. Prompts and a single “what this proves” line stay visible.
One tightly framed fixed camera is used per chapter. The pick uses a high oblique view fitted to the complete motion envelope, keeping the wrist, cluster and tray inside the caption gap. The FEM camera turns the jaw horizontally so both ends fit between the captions. Cursor capture is disabled with `-draw_mouse 0`; the GUI cursor is also hidden and parked outside the 3D view. The scene wrist and its pilot boss read the same `Motion.HeadX/Y/Z` expressions as the head; `wrist-poses.jsonl` checks coincident transforms after presentation refreshes. Motion follows small eased poses through MCP `spreadsheet_set_cells`, with an
explicit recompute before each selected GUI sample. The retained placement
correction initializes the pose; typed tools handle the checks and edits.
Start/end reading holds target 4.4 seconds, with 0.6 second chapter fades.
The final chapter has a 4.1 second end hold; every reading hold stays above
3 seconds after its fade. Idle waiting
is trimmed from a continuous real GUI capture. GUI takes may be joined at fixed poses and chapter boundaries. No CAD pixels are synthesized. Caption/readback panels are restored in post to avoid
GUI redraw damage, with the original wording and layout.

## Run

From this worktree, with the supplied runtime mounts and image available:

```sh
bash scripts/demo/record.sh
```

Required host paths are `/home/msi/FreeCAD` (read-only at `/workspace`) and
`/home/msi/mcp-wt-demofix` (read-only at `/mcpfix`). The supplied companion FreeCAD fork
is revision `a084e95695`; the add-on is `227db9d`. The existing FEM-capable image is
`127.0.0.1:5001/freecad-ci-mcp-fem:24.04`. Nothing is built. The image provides the
solver; the container installs the video encoder if needed.

Every container uses `--rm --memory=2g --memory-swap=2g`. The runner checks at least
1500 MB available with `free -m`, refuses a second local FreeCAD process or replay
container, and launches exactly one GUI. Check that no other container is running
FreeCAD before starting. The replay also records a memory check before FEM.
All encoding goes through [ffmpeg-bounded.sh](ffmpeg-bounded.sh), with one encoder
and filter thread. The launcher stops only its own recorded GUI PID.

The recording starts from the packaged native parametric checkpoint. Chapter 1
changes/restores the jaw-height and cluster-spacing cells, verifies the restored
jaw volume, and reveals the scene/head; it does not
claim a fresh design conversation. Chapter 5 temporarily restores the original
nose parameters, reapplies the retained fix through `spreadsheet_set_cells`, and
checks it. Temporary pose, layout and dimension edits are never saved over the input checkpoint. After capture, `reference_checkpoint.py` reopens a clean copy and saves the wrist bindings, checking unchanged print geometry and sheet contents. The final
tray transfer is a placement preview outside the checked approach/withdrawal paths.
**Forces from datasheets + FEM, not measured.**

## Files and responsibilities

| File | Purpose |
|---|---|
| [record.sh](record.sh), [replay_inside.sh](replay_inside.sh) | Memory guard, isolated profile, one GUI, capture/postproduction lifecycle |
| [replay_driver.py](replay_driver.py) | Seven prompt-led chapters, real MCP reads/writes, eased poses, timeline |
| [reference_checkpoint.py](reference_checkpoint.py) | Save the two wrist reference bindings from a clean checkpoint; verify unchanged printed geometry and sheet contents |
| [rework_presentation.py](rework_presentation.py) | Bind the visual wrist and pilot reference to the existing head motion cells |
| [replay_cameras.py](replay_cameras.py) | Fixed cameras fitted to the complete motion envelope and caption/card boundaries |
| [replay_director.py](replay_director.py) | GUI-thread text, actual readback cards and fixed camera presentation |
| [polish_stills.py](polish_stills.py), [stage2_renderer.py](stage2_renderer.py) | Seven native stills, low camera angles, clearance witnesses and hardware labels |
| [stdio_client.py](stdio_client.py), [stage2_support.py](stage2_support.py) | MCP stdio session, receipts and uncertain-reply handling |
| [stage2_runtime.py](stage2_runtime.py), [replay_bootstrap.FCMacro](replay_bootstrap.FCMacro) | Existing isolated launcher with the `/mcpfix` add-on |
| [caption_panels.py](caption_panels.py) | Restore the original caption/readback panels after GUI redraw damage; leave CAD viewport pixels unchanged |
| [postproduce.py](postproduce.py) | Trim selected real GUI intervals, fade chapters, chapter metadata, four GIFs, QA samples |
| [package_demo.py](package_demo.py), [inspect_exports.py](inspect_exports.py), [verify_delivery.py](verify_delivery.py) | Copy unchanged native/part files, write docs/evidence, verify budgets/links/results |
| [strawberry_model.py](strawberry_model.py), [strawberry_checks.py](strawberry_checks.py), [strawberry_driver.py](strawberry_driver.py) | Retained strawberry design construction, linkage calculations and engineering checks |
| [stage2_job.py](stage2_job.py), [stage2_fem.py](stage2_fem.py), [stage2_fem_phased.py](stage2_fem_phased.py), [fixed_fem.py](fixed_fem.py) | Retained design changes, typed checks and real coarse FEM setup/fallback |

The remaining `stage2_` gate, bootstrap, notes and verification scripts retain the
Stage 2a engineering workflow. They require its earlier design checkpoint. The
final replay is self-contained from the files in
[examples/strawberry-picker](../../examples/strawberry-picker/).

The video parts view arranges the existing display copies in two rows and a hardware strip so the fixed camera can fill the caption-free area. The manufacturing objects and retained parts still are unchanged. The packaged checkpoint adds only the two wrist reference motion bindings; its printed geometry and sheet contents are checked against a clean input.

For static camera retakes, `--only-chapters 2,4,5` writes a separate raw take and
`timeline-static.json`. Replace only those completed chapter entries in the main
timeline before postproduction. Review every final chapter again.

The driver also supports `--start N` for recovery at a completed chapter boundary.
`--start 3 --motion-cut` retains the first take through the fully clamped pose
(first 59 selected intervals) and continues with the cut. Postproduction joins
those real captures at that fixed pose, with no camera change.
`--start 3 --motion-tray` similarly resumes at the completed withdrawal pose
from a cut continuation, retaining its first 67 selected intervals. A normal full run
does not need this recovery option. Runtime logs and the timeline keep the source
file and selected intervals for each take.

A native admission conflict is retried only when the reply explicitly says
`committed=false`, `retry_safe=true` and `native_status=Conflict`. The runner
waits for the active commit to settle and makes at most three attempts. An
uncertain or contradictory completion flag ends that retry path.

The FEM chapter uses [fixed_fem.py](fixed_fem.py) to run the actual solver on
the saved 367-node / 1,063-element mesh and import its real results. This preserves
the Stage 2a comparison. A public `run_fem_analysis` remesh made 1,061 elements
and a slightly different result; both are disclosed in the example evidence.
[retake_fem.py](retake_fem.py) replaces only that chapter when recovering a capture. `--release-head` closes the transient assembly before the FEM take when memory needs to be released; `replay_driver.py --start 7` then reopens the checkpoint for the final chapter.

If committed notifications leave a document with pending recompute work, the runner waits for native writes and replay to settle, then completes a separate recompute. A pre-execution native readiness refusal may be retried after settling.

Uncertain writes settle first and are verified by committed receipts or cell
readback; a mutation is never blindly resent. Read-only checks may be repeated
after readiness settles. A write with unverifiable completion stops the replay.

Outputs are seven 1600 × 1000 stills in `demo-out/stills3/`, the local full video
`demo-out/strawberry-picker.mp4`, raw capture, calls and timings in `demo-out/stage3/`,
and four 960 px / 10 fps GIFs in `assets/`. The overview budget is 5 MB; chapter
3, 5 and 6 GIFs each have a 3 MB budget. The example package budget is 15 MB.

Re-edit an existing capture inside the same bounded image with:

```sh
python3 scripts/demo/postproduce.py
```

After replacing only the FEM take, `python3 scripts/demo/postproduce.py --chapters 6`
reuses the other verified chapter clips and rebuilds the final video, GIFs and samples.
An optional `demo-out/stage3/frame-review.json` removes reviewed redraw or notification
frames. Its capture signature must match the selected source intervals. Review a new
capture again; move an old review file to `demo-out/trash/` before editing a different capture.

Review all seven stills and the 28 required video QA samples (start, one third, two thirds, end; middle samples are also retained) in `demo-out/stage3/qc/`.
The visual review manifest records SHA-256 hashes of the chapter samples actually viewed. A new capture must be reviewed again; the final verifier rejects a missing or stale manifest.

[verify_delivery.py](verify_delivery.py) checks output structure, retained engineering
results, local README links, archive integrity, STL closure, frame rate, chapters
and size limits. The package retains the source evidence and engineering gaps;
see its [README](../../examples/strawberry-picker/README.md).

No script stages, commits, pushes or publishes anything. `demo-out/` and the MP4
must stay out of the paths to stage.

<!-- generated media summary -->
Local video: **3:51.0**, seven chapters. GIFs: overview **2.36 MB**; motion **1.43 MB**; tight cluster **0.56 MB**; FEM **0.37 MB**. All GIFs are 960 px at 10 fps.
