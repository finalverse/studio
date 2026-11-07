# CF1 evidence: Elara Vayne candidate

- `renders/`: neutral rig (Khronos PBR Neutral, Infinity's tone mapper) and production rig (AgX) turnarounds and face close-ups; `v1elara_*` = V1 asset with identical camera and lights; `runtime_glb_*` = runtime GLB re-imported and rendered.
- `compare/`: V1 vs CF1 side by side, CF1 turnaround sheets.
- `motion/`: walk (side, every 4th frame of 32), idle and wave (front), face expressions.
- `elara_cf1_runtime.glb`, `elara_cf1_proxy.glb`, `glb-check-*.json`: runtime candidate, static proxy and validator reports.
- `recipe.json`: `finalverse.character-foundry.recipe/v1`, approval status `candidate`.

Not in git (project storage, digests in `recipe.json`): `elara_cf1.blend` (editable source, ~45 MB), `elara_cf1.glb` (hero profile), `textures/*.png` (lossless masters).

Status: candidate. Needs independent art review and Infinity Gate B captures. See `docs/character-foundry/CF1-ACCEPTANCE.md`.
