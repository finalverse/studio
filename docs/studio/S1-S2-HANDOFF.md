# S1 → S2 handoff

Read [S1 acceptance](S1-ACCEPTANCE.md), the [provider architecture](S1-PROVIDER-ARCHITECTURE.md),
the [creation protocol](S1-CREATION-PROTOCOL.md), [MCP](S1-MCP.md) and [security](S1-SECURITY.md)
before changing S2 code. S1 is an isolated local authoring milestone. No merge,
push or deployment occurred.

## Exact baseline

| Item | Value |
| --- | --- |
| Branch | `feat/studio-s1` (S2 continues on its own branch from the S1 close commit) |
| S0 accepted source / executable | `24d1acf06b55945bed5d247bd6e5184906bf4150` / `e857ab2d…b6343a4` (rehashed unchanged) |
| S1 implementation | `7e99e2fd3ae3556fde0f47410bda5ac82dc82cb3`, executable `e38aa33b…b573ff` |
| S1 provider revision | `452fedc0712` (Maple + custom providers, Keychain, TLS CA fix), executable `d38abfd5…7da1f` |
| S1 close (docs/evidence) | the commit that adds this file. Its SHA is recorded in the S1 close report and in S2 docs |
| Core adapter (unchanged) | `b601da2e7c9cdd673ab7d0a9b13ec2a68c7fea4f` |
| Provider app for S2 work | `/Users/wenyan/Finalverse/dev/studio-s1-20261104/install-providers/Finalverse Studio.app` |

## What S1 hands over

Closed `finalverse.creation/v1`: inspect, cube/sphere/cylinder/plane, transforms,
applied bevel, Principled presets, camera/light creation, linear transform keys,
sandboxed Eevee preview, editable save and S0 GLB candidate export. There is one
durable proposal store, exact approval bound to digest/scene/revision/session,
one operation per tick, checkpoints, cancellation and worker supervision, shared
by UI and MCP. Providers: Local Gemma by default; Maple (off, error path only
because the host does not resolve yet); custom Ollama/OpenAI-compatible/Anthropic
providers with Keychain keys; one memory admission rule.

## Rules S2 must keep

* Extend the creation language only through typed, bounded operations backed by
  Blender operators/data API. Add each capability together with its scene
  revision coverage, validation and budget. Never accept rigs, constraints,
  node graphs or drivers that the profile cannot inspect and bound. No arbitrary
  generated Python.
* Reuse the same proposal → approval → bounded execution path for UI, MCP and any
  automated refinement loop. Revisions are new, visible, validated proposals:
  no hidden repair and no silent fallback. Model failures stay visible.
* Honor E1's distinct residents and archetypes. Lumi is a floating spirit with no
  walking rig. Do not force one humanoid skeleton on every archetype.
* Studio exports candidates only. It cannot change founder canon, memories,
  institutional authority, balances or world revisions. Civilization policy
  authorizes, MutSea commits, Genesis/SpatialDB publish, Infinity renders and
  WorldLine records, each through its accepted contract.
* A Studio preview is not evidence of Infinity rendering equivalence (V0's job).
* Keep exact model/version/latency/failure receipts. Do not load `qwen3:30b-a3b`
  on this 16 GB Mac; the admission rule refuses it.

## Known limits carried forward

Reduced S0 build profile (Eevee/Metal, GLB; Cycles/USD off), unsigned and not
notarized, macOS only. Remote inference untested beyond failure modes. Main-thread
save/export can briefly occupy the UI. Computer-use clicks were declined for the
S1 visual check, which instead used timer-invoked operators in the real window.
