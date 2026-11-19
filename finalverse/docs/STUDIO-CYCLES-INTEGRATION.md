# Canonical FWD geographic exchange

Supported module scripts/modules/finalverse_fwd/ and trusted CLI finalverse/fwd_exchange.py import static GLB through CoreFWD0.1 validation. They create an isolated scene, preserve geographic frame/TRS, apply a deterministic material palette, export only that scene, validate new geometry, compare every source triangle corner, and write a new asset identity and FWD version. Existing source bytes and accepted simulation bindings are not modified. Textures, skins, animations, external buffers, malformed scene graphs and unsupported profiles are refused. The UI is registered through supported Blender operators/panels; no kernel patch is introduced.

Reproduce with the explicit installed Studio executable and Core validator:

```sh
/path/to/Studio --background --factory-startup --python finalverse/fwd_exchange.py -- --definition /path/to/world.fwd.json --cas-root /path/to/objects --output /path/to/new-output --validator /path/to/finalverse-fwd --palette urban_clay --cycles-binary /path/to/cycles-enabled-Blender
```

Use --no-render to keep authoring independent from rendering. Source input is a canonical FWD plus CAS, not an arbitrary .blend/script. Rendering a newly generated internal scene uses the module's fixed trusted worker. Budgets: static profile,≤64samples, bounded preview size, default512×384/16samples/2CPUthreads; no inference. Existing output directories are refused. A simulation-binding reference cannot be silently rebound by artistic refinement.

Verified native authoring: installed Finalverse Studio5.4alpha/c1628e4e3f71, repository baseline57ed216cc8c634bdabdd3d61ff9c3a7a105d0d2d. Its Cycles build option is OFF; the failed first probe is retained. The explicit official Blender5.2.2LTS/d13f752e3b9c CyclesCPU backend produced both final previews. The receipt records both runtimes and does not claim Studio has built-in Cycles enabled.

Montréal source5046triangles and fictional Aetheria2050triangles retain all triangle corners with zero exact drift after material refinement. Refined SHA25677a3901edce0bebd881017265c22cb7ad58e3c1b08f48b46ecaa4b4afdfee38e /4fbae91f8009712abf599bf6c2c00001181ef216d99c6b67f57c4059d08c4f1c. Fresh-process GLB/FWD repeat and .blend reopen pass.16independent unit checks and6native refusal cases pass. Only macOSarm64 is executed; no full PBR/texture/rigging/collision/render-parity claim. Images are proxy/material studies, not photographs. See Core OmegaXIII3 delivery for artifact hashes and final merge commits.
