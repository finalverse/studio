# S0 verification and remaining acceptance gate

2026-11-04, Asia/Shanghai. The source-built Finalverse Studio foundation and Core
worker adapter are implemented and verified locally. **Full S0 acceptance is
pending visible desktop verification:** computer use reports the Mac locked and
could not unlock it. The user has been asked to unlock. No desktop screenshot or
visual inspection is fabricated. Do not start S1 on an assertion that this gate passed.

| Gate | Actual result |
| --- | --- |
| Source fork | Blender 5.4.0 Alpha, upstream 0f5a1ae067d9785d2c106a887c94a0c96c3239a4; Studio implementation ced9727a5c00fb2f46e01034466c3596684ace7b. |
| Build/install | PASS, full Apple Silicon source compilation and local app installation using the documented S0 profile. |
| Product identity | PASS in executable version, bundle metadata, source menu/window/About patches and startup workspace data. Original icon/splash resources installed; visible desktop check pending unlock. |
| Copyright/license | COPYING and AUTHORS byte-identical to upstream; complete GPL/third-party files retained. Original Finalverse artwork has no copied Blender logo. |
| Standard authoring smoke | PASS on the built 5.4 executable: real mesh edit, Principled material, Eevee render, save/reopen with persistent object IDs, GLB/editable-source export and overwrite refusal. |
| Actual rendered content | PASS; independent teal-subject assertion found 42,798 subject pixels; actual preview retained. Earlier camera/material fixture failures are disclosed. |
| Workspace | Built-in startup module loaded; Finalverse AI Studio workspace and operators registered in the actual engine. Visible desktop inspection remains pending. |
| Studio unit/security checks | 8 passed; bundle identity/interoperability, GPL/resources, hash corruption, duplicate JSON keys, traversal/extra assets, symlinks and false publication assertions. |
| Core integration | 333 workspace tests passed, 0 failed, 1 existing ignored; final 25-case Genesis regression passed; final warnings-denied all-target FEN Clippy and format passed. |
| Actual Genesis worker | PASS; selected hash-pinned Studio produced a valid 21-part room GWIR and AwaitingAuthorization job in one attempt; wrong pin refused before leasing/spawning. No world mutation or publication. |
| Upstream maintenance | Small native patch inventory, dedicated authoring module, upstream sync/build/source dependency records and S1 handoff provided. |
| Desktop launch | macOS open request succeeded; direct visible app/window verification could not proceed because Mac was locked. |

## Artifacts and measured conditions

App: `/Users/wenyan/Applications/Finalverse Studio.app` is a user-local link to
`/Users/wenyan/Finalverse/dev/studio-s0-20261104/install/Finalverse Studio.app`.
Core adapter source is the isolated `core-studio-s0-20261104` worktree, based on
accepted E1 Core 33eb4b032c91228d2f3929a9f74f63de072a33b9. Native E1 sources and
accepted worlds remain unchanged. Exact final source commits and hashes are in
external `S0-FINAL-delivery.json`; [revisions](S0-revisions.json) records build inputs.

The final authoring smoke took 1,671.55 ms with warm shader/filesystem caches;
this is not a cold-start or sustained rendering benchmark. The supervised Genesis
room job took 7,557.32 ms and produced GWIR
`79416251fb588b0c4e34bf6ad75e62b1b5ff0ee026665e0e4c2add23d6da3480`.
The candidate remains AwaitingAuthorization: successful creation supplies no
independent publication grant. The transport-integrity checker likewise explicitly
reports genesis_geometry_validated=false and publication_authorized=false.

[Built-engine smoke](evidence/fork-smoke.json), [preview](evidence/preview.png),
[Genesis proof](evidence/genesis-proof.json), [version](evidence/version.txt),
[corrections](evidence/corrections.json), [index](evidence/index.json).

The earlier Blender 5.2.2 compatibility probe is separate; it is not counted as
source-build evidence. Initial render fixtures were corrected after visual review:
update the parented camera's evaluated matrix, use the actual Principled BSDF
instead of viewport diffuse color, then assert a visible subject. Failed originals
remain in the private evidence root.

## Scope and limits

This is a local development build: modeling, animation/Python APIs, GLB, Metal and
Eevee. Heavy optional Cycles/USD and other production integrations are disabled
by the development profile and remain in upstream source. No feature-complete
release, signing, notarization, Windows/Linux build, sustained performance target
or Blender-to-Infinity material equivalence is claimed.

AI/provider/MCP controls are visibly future S1 work. S0 has no inference loop or
unrestricted model script execution. The new backend descriptor is a trusted local
host executable approval, not remote attestation or world authority. Existing
worker sandbox/resource limits, credential separation and independent Genesis
validation/publication gates remain. No accepted resident body/canon, resource
ledger, private world or historical record was modified.

No push, protected merge, deployment or public release occurred. S1 and later
visual/civilization milestones were not started. Finish the visible workspace,
icon, splash and menu check after Mac unlock, then update the gate and handoff.
