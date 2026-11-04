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
  at a time (each ≤ 120 s), plans ≤ 48 operations. Rejected model JSON, execution
  failures, evaluation failures and export-validation failures each consume one
  revision, with the reason passed back to the model. When the budget runs out,
  the loop ends **failed**, and that is visible.
* **Ledger:** `workspace/loops/<id>/loop.json` records every stage with times,
  job IDs, receipts and evaluation digests; each evaluation is saved as
  `evaluation-NN.json`.
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

Environments are checked for exposure only. Geometry, material, rig and animation
checks are listed in the [character pipeline](S2-CHARACTER-PIPELINE.md) and
[animation](S2-ANIMATION.md) docs. Every check reports a measured value and its
limit.

## What it does not do

The evaluator is deterministic measurement, not taste. A model critique of the
image (visual-language review) is **not** implemented: the local Gemma used here
is driven as a text planner. Aesthetic quality and canon likeness are still human
judgments. A passing evaluation means the asset is well-formed, framed and within
contract bounds, not that it is good art or matches Infinity rendering (V0).
