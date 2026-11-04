# S0 acceptance — Finalverse Studio foundation

2026-11-04, Asia/Shanghai. **S0 passes local acceptance for its documented Apple
Silicon development profile.** The source-built application, authoring workflow,
Core worker adapter and visible desktop gates are verified. The earlier locked-Mac
gate is resolved. Native testing exposed two alpha UI crashes; both are fixed and
their actual reproduction paths pass in the final executable. No release-quality
or exhaustive upstream test-suite claim is made.

| Gate | Actual result |
| --- | --- |
| Source fork | Blender 5.4.0 Alpha, upstream 0f5a1ae067d9785d2c106a887c94a0c96c3239a4; final compiled Studio 63e281993d748d6e3f9870dd9ecac1997514bf83. |
| Build/install | PASS, full Apple Silicon source compilation and local app installation using the documented S0 profile. |
| Product identity | PASS in executable version, native application menu, main/render/file window titles, splash, About and workspace. White Finalverse icon installed and verified in Finder's Info/Preview. |
| Copyright/license | COPYING and AUTHORS byte-identical to upstream; complete GPL/third-party files retained. Studio artwork derives from the user's authorized Finalverse emblem; its source/hash and vector simplification are documented. |
| Standard authoring smoke | PASS on the built 5.4 executable: real mesh edit, Principled material, Eevee render, save/reopen with persistent object IDs, GLB/editable-source export and overwrite refusal. |
| Actual rendered content | PASS; independent teal-subject assertion found 42,798 subject pixels; actual preview retained. Earlier camera/material fixture failures are disclosed. |
| Workspace | PASS, visible Finalverse AI Studio tab, working scene inspection/history, asset thumbnails and offline banner, render/save/export controls, disabled future S1 controls and candidate-only publication status. |
| Native crash regressions | PASS, first Asset Browser draw with an offline banner and F3 menu search from that editor, including regionless nested layouts. The initial search-only guard was insufficient; the final region guard passes the reproduction. |
| Studio unit/security checks | 9 passed; bundle identity/interoperability, native glyph dimensions, authorized source integrity, GPL/resources, hash corruption, duplicate JSON keys, traversal/extra assets, symlinks and false publication assertions. |
| Core integration | 333 workspace tests passed, 0 failed, 1 existing ignored; final 25-case Genesis regression passed; final warnings-denied all-target FEN Clippy and format passed. |
| Actual Genesis worker | PASS; selected hash-pinned Studio produced a valid 21-part room GWIR and AwaitingAuthorization job in one attempt; wrong pin refused before leasing/spawning. No world mutation or publication. |
| Upstream maintenance | Small native patch inventory, dedicated authoring module, upstream sync/build/source dependency records and S1 handoff provided. |
| Desktop launch | PASS, actual source-built application launched and was inspected after restart; About displays the exact final build hash without a modified-source marker. |

## Artifacts and measured conditions

App: `/Users/wenyan/Applications/Finalverse Studio.app` is a user-local link to
`/Users/wenyan/Finalverse/dev/studio-s0-20261104/install/Finalverse Studio.app`.
Core adapter source is the isolated `core-studio-s0-20261104` worktree, based on
accepted E1 Core 33eb4b032c91228d2f3929a9f74f63de072a33b9. Native E1 sources and
accepted worlds remain unchanged. Exact final source commits and hashes are in
external `S0-FINAL-delivery.json`; [revisions](S0-revisions.json) records build inputs.

The final authoring smoke took 5,252.94 ms with warm shader/filesystem caches;
this is not a cold-start or sustained rendering benchmark. The supervised Genesis
room job took 8,656.42 ms and produced GWIR
`79416251fb588b0c4e34bf6ad75e62b1b5ff0ee026665e0e4c2add23d6da3480`.
The candidate remains AwaitingAuthorization: successful creation supplies no
independent publication grant. The transport-integrity checker likewise explicitly
reports genesis_geometry_validated=false and publication_authorized=false.

Final executable SHA-256:
`e857ab2dfa7c316c9c69b2e6d85670b862d61a5907b7c6cff263f8b12b6343a4`.
The final supervised job is `5acac912-304f-4b33-8991-4d0348db51ac` (one attempt).
The unchanged Core adapter remains b601da2e7c9cdd673ab7d0a9b13ec2a68c7fea4f.
Later Studio commits contain acceptance documentation/evidence only; the external
delivery receipt records their final SHA separately from the compiled source SHA.

[Built-engine smoke](evidence/fork-smoke.json), [preview](evidence/preview.png),
[Genesis proof](evidence/genesis-proof.json), [version](evidence/version.txt),
[corrections](evidence/corrections.json), [index](evidence/index.json).

Actual desktop evidence: [verification record](evidence/gui-verification.json),
[workspace](evidence/gui-workspace.png), [splash](evidence/gui-splash.png),
[About](evidence/gui-about.png), [menu search](evidence/gui-menu-search.png),
[render](evidence/gui-render.png), [Mac icon](evidence/gui-mac-icon.png).
Screenshots are unaltered. Native menu and file-window accessibility text are
retained separately. The Asset Browser inherits the compact timeline height and
was resized interactively; selecting the Finalverse sidebar tab opens Studio
controls. The visible default-scene render reported 2.28 seconds, 109 MB memory
and 170 MB peak in its internal statistics; these are not process/GPU measurements.

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
visual/civilization milestones were not started. The S0 → S1 handoff is ready.
