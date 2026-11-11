# S2 visual feedback and the creation loop

## Loop

`loop.CreationLoop` (started from the sidebar's **Creation loop · S2** box or
`Host.start_loop`) runs a bounded state machine:

```
Intent → Plan (model) → [artist approves] → Generate (bounded ops) → Preview (sandboxed render)
      → Evaluate (deterministic) ──pass──→ Validate + Export plan → [artist approves] → package
                                  └─fail─→ Revise (model gets failed checks) → [artist approves] → …
```

* **Nothing is auto-approved.** Each model plan, artist draft and final export
  plan is an ordinary Proposed job, approved by the same exact-digest approval as
  S1. **Reject & Revise** turns a declined proposal into a visible revision.
* **Bounded:** 0–3 revisions (default 2), a 30-minute wall budget, one inference
  at a time (each ≤ 300 s; the local model is unloaded after each v2 plan so the
  60 s sandboxed preview is not starved), plans ≤ 48 operations. Rejected model JSON, execution
  failures, evaluation failures and export-validation failures each consume one
  revision, with the reason passed back to the model. When the budget runs out,
  the loop ends **failed**, and that is visible.
* **Ledger:** `workspace/loops/<id>/loop.json` records every stage with times,
  job IDs, receipts and evaluation digests; each evaluation is saved as
  `evaluation-NN.json`.
* **Revision guidance** is deterministic. The model receives each failed check
  with its measured value and limit, a fix hint derived from the check (for
  example a front camera position computed from the subject's bounds), the
  subject's bounds, and a two-operation format example. Rejected plans come back
  with the exact JSON path, value and limit (for example
  `operations[1](material.preset).color[1]: 1.9 not in 0..1`). The model still
  writes every revision, and each revision still needs approval.
* **Export** is a deterministic plan built by the host, not the model: one
  re-render of the approved camera plus `asset.package`. Packaging runs the
  evaluator again as the Validate gate, then the GLB and E1 structural checks.
  Any failure aborts the export, and no package directory is left behind.

## Preview checks

Previews render with transparent film in the sandboxed worker and are read back
with NumPy:

| Check | Limit | Gating |
| --- | --- | --- |
| coverage (alpha > 0.02) | 3–85% of frame | yes (characters/props) |
| framing | no subject pixel on the border | yes |
| exposure (mean luminance of subject pixels) | 0.04–0.95 | yes |
| centring | centroid ≤ 0.25 from centre | advisory |
| viewpoint (characters) | scene camera faces the subject's front (−Y) within 60° and looks down ≤ 50° | yes |

Environments are checked for exposure only. Geometry, material, rig and animation
checks are listed in the [character pipeline](S2-CHARACTER-PIPELINE.md) and
[animation](S2-ANIMATION.md) docs. Every check reports a measured value and its
limit.

## Why the viewpoint check exists

The first intent-only run that completed (`806ff87734ce`) passed every check
then in place, but its preview looked straight down on Lumi. The checks proved
it well-formed, not that it met "frame Lumi from the front". The viewpoint gate
was added after that run. Two later intent-only runs failed for other reasons (a planner timeout, then
invalid revisions; see [attempts](evidence/s2/attempts.json)). The final run
(`f165abf4e77f`) failed the viewpoint gate, and Gemma's revision fixed it with a
front camera.

## What it does not do

The evaluator is deterministic measurement, not taste. A model critique of the
image (visual-language review) is **not** implemented: the local Gemma used here
is driven as a text planner. Aesthetic quality and canon likeness are still human
judgments. A passing evaluation means the asset is well-formed, framed and within
contract bounds, not that it is good art or matches Infinity rendering (V0).
