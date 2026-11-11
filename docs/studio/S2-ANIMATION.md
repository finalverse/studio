# S2 animation

## Clips

`action.create` makes one named Blender action per clip, targeting an object or
an armature, and stores it as its own **NLA track** (muted by default). Several
clips can therefore coexist on one subject and export as separate glTF
animations. Each action records `kind` (E1 expression: idle, greet, observe,
interact, speak, locomote), `locomotion` (walk, run, hover, fly, drift, climb,
rooted, none), `loop` and its target UUID. Keys hold absolute object values, or
pose-local values when `bone` is given. After keying, the subject's rest
transform is restored, so authoring a clip never moves the asset.

`action.retarget` copies a clip between armatures by an explicit bone map.
Rotation and scale curves copy key for key; root translation scales by the
root-bone length ratio. Unknown bones and empty maps are refused.

The archetype gates which locomotion a clip may declare (see the
[character pipeline](S2-CHARACTER-PIPELINE.md)). A floating spirit can hover, fly
and drift, and a walk clip is refused before approval.

## Deterministic checks (evaluate.py)

Each clip is sampled from its own F-curves at every frame, independent of NLA
mute state:

* finite values, at least 2 frames;
* duration 0.25–20 s at the scene fps;
* locomotion compatible with the archetype;
* loop clips: first and last frame equal within 0.001;
* object displacement from rest ≤ 2 m for locomotion clips, ≤ 0.3 m otherwise;
* character scale change ≤ 0.1 (E1 `max_scale_delta` bound).

## Export

* `asset.glb` exports the subject hierarchy with `NLA_TRACKS`: one glTF animation
  per clip, named after the clip.
* `clips/<name>.glb` holds each clip alone (active-action export), with exactly
  one animation.
* `clips/<name>.json` (`finalverse.studio-clip/v1`) holds the sampled tracks
  per frame, converted to glTF Y-up axes, with kind, locomotion, loop and fps.
  This engine-neutral form makes review independent of glTF tooling.

The independent GLB checker verifies sampler times are finite and ascending,
outputs are finite, channels target existing nodes, and the animation count
equals the clip count. Per-clip GLBs name their single animation `Animation`
(Blender exporter behaviour in active-action mode); the manifest maps each file
to its clip name.

## Limits

Clips use Blender's default Bézier interpolation between the authored keys. There
are no IK, constraints, drivers, shape-key animation, root-motion extraction or
foot-contact analysis. Emission brightness is not animated, because core glTF has
no material animation; E1's runtime light pulse covers that. Studio previews are
rest-pose stills, since clip tracks are muted; motion is checked numerically, not
visually.
