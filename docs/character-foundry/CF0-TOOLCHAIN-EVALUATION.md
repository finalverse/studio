# CF0: Toolchain evaluation

What is actually available to a cloud agent today, what CF1 used, and what is
missing. Verified on 2026-11-07 in the Claude cloud container, not on the Mac.

## Environment actually used

| Item | Value |
| --- | --- |
| Blender | upstream `bpy` 5.2.3 LTS wheel (PyPI, sha256 `8ef4a335…4db7`). This is not the Studio fork binary: Studio's S0–S2 build is local-only on the Mac. |
| Build options | OpenVDB (voxel remesh), OpenSubdiv, Cycles CPU, OIDN denoiser, cloth solver, glTF 2.0 add-on |
| Renderer | Cycles, CPU, 4 vCPU, no GPU (headless EEVEE unavailable) |
| Python libs | numpy only (no scipy). Texture painting is pure numpy. |
| Network | PyPI and raw.githubusercontent.com reachable. github.com HTML/API, polyhaven.com, blender.org and makehumancommunity.org asset servers **not** reachable through the proxy. |
| Studio repo | `finalverse/studio` branch `feat/studio-v1` @ `57ed216c` (V1 founders) |
| Core repo | `finalverse/finalverse` main @ `4cde961` (GC7 merge) |

## Methods evaluated

| Method | Available? | Licence | Automation | Quality | CF1 decision |
| --- | --- | --- | --- | --- | --- |
| **MakeHuman hm08 base mesh + targets** | yes (raw GitHub, `makehumancommunity/makehuman` master) | **CC0 1.0** for assets (LICENSE.md §C). Program code AGPL, *not used* | file formats are plain OBJ/JSON/text. Our loader is 200 lines | anatomically correct, quad topology designed for animation, full UVs, eye/lash/teeth helpers | **used** (body, UVs, landmarks) |
| **MakeHuman default skeleton + weights** | yes | CC0 | JSON | 163 bones incl. 60+ face bones, symmetric production weights | **used** (rig, body skin) |
| **MakeHuman face pose units** (`face-poseunits.bvh`) | yes | CC0 | BVH | 59 FACS-like units (brows, lids, cheeks, lips, jaw, tongue) | **used** (expressions, blinks) |
| MakeHuman high-poly eyes | yes | CC0 | OBJ | proper eyeball with UVs | **used** (iris texture is ours) |
| MakeHuman system clothes/hair/skins | **no** (not in the code repo; asset server unreachable) | mixed (CC0 / CC-BY) | n/a | n/a | not used. Garments and hair modelled in CF. |
| MPFB2 (Blender add-on) | not installable offline | GPL code + CC0 assets | needs UI/asset packs | high | not used. CF reads the same CC0 data directly. |
| Rigify | present in bpy add-ons | GPL (generated rigs are user data) | scriptable | great for animator control rigs | **deferred to CF2**: MH deform skeleton is game-ready; a Rigify control layer is an authoring nicety |
| Blender cloth solver | yes | GPL (output is user data) | fully scriptable headless | real drape and folds | **used** (cloak) |
| Geometry Nodes | yes | GPL | scriptable but verbose from Python | good for instancing/scatter | not needed for CF1; candidate for GeoWorld vegetation |
| Voxel remesh + Laplacian | yes | GPL | yes | good for fused shapes | used in V1; CF1 uses lofts instead (keeps UVs) |
| Sculpting (multires/dyntopo) | yes in bpy | GPL | brush strokes are not meaningfully scriptable by an agent | high in human hands | **not used**. Detail comes from normal maps. Missing capability (below). |
| Retopology (QuadriFlow) | yes | GPL | scriptable | acceptable | not needed (base mesh already production topology) |
| Texture baking (Cycles bake) | yes | GPL | scriptable | standard | not needed: CF paints maps directly in UV space with a numpy rasteriser, which is faster and deterministic |
| Poly Haven / ambientCG PBR textures | **unreachable** | CC0 | REST | excellent scanned materials | not used. Procedural textures painted instead. Recommended once network allows. |
| Mixamo animations | not used | Adobe terms forbid redistributing raw animation files | — | good | **rejected** (redistribution rights) |
| CMU mocap (BVH) | not fetched | free for any use (CMU statement) | BVH retarget needed | realistic | CF2 candidate for walk/idle realism |
| Proprietary AI 3D generators (Meshy, Tripo, Rodin, CSM…) | none available here | per-vendor terms | API keys needed | variable topology, no rig | **not used, and not claimed** |
| Local LLM (Gemma via Ollama) | Mac only | Gemma terms | n/a in cloud | n/a | not used for CF1. Path B hook documented. |

## Licence and provenance audit for CF1

| Source | Files | Licence | Redistribution | Digest recorded |
| --- | --- | --- | --- | --- |
| MakeHuman assets | `base.obj`, `default.mhskel`, `default_weights.mhw`, `high-poly.obj`, `face-poseunits.bvh/.json`, 4 macro targets | CC0 1.0 (asset licence text included as `LICENSE.ASSETS.md`) | unrestricted | yes, in `recipe.json` |
| Finalverse CF code | `finalverse/character_foundry/*.py` | GPL-2.0-or-later (Studio repo licence) | yes | git |
| Textures | painted by CF code | original, CC0-compatible | yes | yes |
| Vision art | Albert's uploads | Finalverse-owned reference | reference only, not shipped in assets | — |

No commercial or copyrighted character asset was imported.

## Missing capabilities (exact)

1. **Sculpted secondary detail.** Wrinkles, cloth seams, hair strand relief and
   facial pores come from painted normal maps, not sculpts. A human sculpt pass,
   or a scriptable sculpt-from-displacement step, would lift Q3 to Q4.
2. **Scanned PBR libraries.** Poly Haven / ambientCG would replace procedural
   fabric and leather. The proxy blocks them today.
3. **Strand hair.** Locks are meshes. Curves hair with a hair BSDF would look
   better in Studio, but it needs a card bake for runtime.
4. **Mocap-quality locomotion.** The walk is analytic FK with a ground solve.
   CMU retargeting or an animator pass would add weight and overlap.
5. **GPU rendering.** CPU Cycles limits evidence to ~64 samples at 1K. Turntable
   videos are impractical here.
6. **Infinity runtime path.** Infinity cannot yet draw UVs/textures/skinning/
   clips on the E1 character path (V0 matrix). See the handoff.
7. **Independent art review.** Not something an agent can supply for itself.
