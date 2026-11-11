# S2 → V1 handoff

Read [S2 acceptance](S2-ACCEPTANCE.md) with the [creation engine](S2-CREATION-ENGINE.md),
[character pipeline](S2-CHARACTER-PIPELINE.md), [animation](S2-ANIMATION.md),
[visual feedback](S2-VISUAL-FEEDBACK.md) and [Genesis integration](S2-GENESIS-INTEGRATION.md)
docs. S2 is a local authoring milestone on `feat/studio-s2`. No merge, push or
deployment occurred, and this handoff does not authorize V1 by itself.

## Baseline

| Item | Value |
| --- | --- |
| Branch | `feat/studio-s2` from S1 close `5fa8900ee7b` |
| Final compiled S2 source | `f165abf4e77f`; executable `b23029a3…2d1591` |
| S2 close (docs/evidence) | the commit adding this file; its SHA is in the S2 report and `S2-FINAL-delivery.json` |
| E1 contract (read-only) | Core `33eb4b0` `finalverse-embodiment::universal` |
| Demo package | `docs/studio/evidence/s2/lumi.fvpkg` (also in the private root) |

## What V1 inherits

The closed `finalverse.creation/v2` language and its typed tools; E1-archetype
rules enforced before approval; the deterministic evaluator; the bounded loop
that routes every model plan and export through one approval store; the
`finalverse.studio-asset-package/v1` package with an E1 body, draft definition,
per-clip files, provenance and S0 candidate manifest; Maple as an OpenAI-compatible
`/v1` endpoint (off by default) plus custom providers with Keychain keys.

## Decisions V1 needs from outside Studio

1. **Generator admission.** E1 `Artifact::validate` admits only
   `blender-universal/1`. Studio bodies say `finalverse-studio-s2/1` and otherwise
   pass E1's real validators. Genesis/Core must decide whether, and under what
   review, Studio becomes an admitted generator. Studio must not impersonate the
   E1 worker.
2. **Genesis submission path.** Define how a package enters Genesis (CAS
   admission of `source.blend`, GLB proxy and body JSON) and who authorizes it
   (Civilization policy), and keep publication separate from artist approval.
3. **Maple deployment.** Serve `/v1/models` and `/v1/chat/completions` with
   `json_schema` structured outputs that accept `oneOf`/`anyOf` (vLLM, SGLang or
   llama.cpp server), with key auth at the gateway. Measured today: most loop
   revisions on the 16 GB M1 went to malformed small-model output. Constrained
   decoding removes those, but semantic validation and approval must stay (an
   Ollama `/v1` constrained answer was well-formed and still wrong).
4. **V0 rendering equivalence.** Studio Eevee previews are not evidence of
   Infinity output.

## Recommended V1 work (not started)

* A visual-language critic as a non-gating advisory in the evaluator, measured
  against the deterministic gates.
* Model-proposed parameter search for appearance (colour/emission bounds that
  keep subjects off white, size-in-frame targets), still validated and approved.
* Humanoid and environment model runs end to end (only fixtures today); facial
  and shape-key expression; rest-pose-compensated retargeting.
* Clip previews (rendered motion strips) instead of rest-pose stills.
* Per-clip GLB animation naming (currently `Animation`; the manifest maps names).
* Signed/notarized builds and the bundle-ID decision for Genesis's Studio pin
  (the S0 Genesis smoke expects `org.finalverse.studio`).

## Rules that still hold

No arbitrary generated code; every capability typed, bounded and covered by scene
revision. No hidden repair or fallback; model failures stay visible. Lumi stays a
skeleton-free floating spirit. Studio never changes canon, memories, authority,
balances or world revisions. Do not load `qwen3:30b-a3b` on the 16 GB Mac.
