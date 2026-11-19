# V0 renderer capability matrix (Infinity / FinalStorm)

Read from source: Infinity E1 `eb3cd4a`, vendored FinalStorm runtime
(`vendor/finalstorm/runtime/crates/render`, `fsir`), and the E1 character path
`src/civilization_e1.rs`. "Renderer" is what FinalStorm can draw. "E1 character
path" is what Infinity actually feeds it for founders today, which is the binding
constraint for V1.

| Capability | Renderer | E1 character path today | Consequence for Studio assets |
| --- | --- | --- | --- |
| PBR metallic-roughness | yes (`surface.wgsl`, Cook-Torrance + split-sum IBL with BRDF LUT, irradiance and specular cubes) | yes, **factors only** per part (`MaterialBehavior` → `Material` base colour, metallic, roughness, emissive) | material zones must be separate parts; roughness ≥ 0.04 |
| Base-colour / ORM / normal / occlusion / emissive textures | yes (glTF channel layout, sampled by UV) | **no**: body parts carry no UVs (`uvs: vec![]`) and no textures | no texture detail in Infinity; detail must be geometric or per-part |
| Normal mapping | yes (tangent-space, `normal_scale`) | no (no UVs/tangents) | surface detail must be real geometry |
| Shadows | yes: one directional sun, up to 4 cascaded shadow maps with blend, normal offset | yes | contact grounding comes for free; floating spirits cast detached shadows |
| Ambient occlusion | yes: bounded SSAO on the IBL term, plus occlusion texture | SSAO only | crevices read slightly darker; no baked AO |
| Transparency | `Opaque` and `Mask` (alpha cutoff). **`Blend` has no blend pipeline** (all `blend: None`) | opaque | glass, glow halos and soft spirit edges cannot be translucent; use emissive and geometry |
| Emissive | yes, HDR (linear, before tone mapping) | yes, emissive RGB ≤ 8 per part, plus E1 pulse | emission is the main tool for luminous characters; over-emission clips to white |
| Tone mapping | AgX, ACES fit, Reinhard, Khronos PBR Neutral; default **Khronos Neutral**, exposure 1.0 | default | Studio previews must use a matching view transform to be comparable |
| Colour management | linear HDR `Rgba16Float` → tone map → `Rgba8UnormSrgb` output; base colour is linear | same | author colours in linear; Studio "Standard"/AgX previews are not equivalent by default |
| Anti-aliasing | FXAA (post); MSAA sample count 1 | FXAA | thin geometry (whiskers, petals edge-on) shimmers |
| Skinning (GPU) | **no** joints/weights in the renderer | rigid parts per joint, posed on the CPU by `Artifact::pose` | no smooth bending at elbows/knees; deformation via rigid parts or E1 procedural displacement |
| Morph targets / shape keys | no | no (procedural displacement only, ≤ 0.3 m, scale delta ≤ 0.1) | facial expression must be part motion or emissive change |
| Baked animation clips | n/a | **no**: E1 runtime animates procedurally (`bounded-archetype-expression/1`) | Studio clips are review assets, not played in Infinity without a runtime change |
| Instancing | yes: per-view culled, batched instanced draws | parts become separate meshes with per-pose cache keys | draw calls scale with parts × actors (159 peak today) |
| LOD | renderer draws what it is given | two LODs (0 m, 18 m) chosen by camera distance; pose stride 1/2/4 frames by distance | LOD1 must keep the silhouette; triangles ≤ 100,000 per LOD (E1) |
| Particles | as meshes | ≤ 6 spirit/synthetic, ≤ 16 fire; tetrahedra, emissive | Ignis/Lumi sparkle is bounded |
| Culling | frustum + shadow culling; **no backface culling** (`cull_mode: None`) | same | single-sided cards are visible from both sides |
| Asset budget | streaming budget (E1 uses 8 MiB requested GPU assets) | 8,177,744 B peak today | V1 must stay inside the 8 MiB character budget or raise it explicitly |

Main conclusion: in today's E1 path, Infinity renders **untextured, rigid,
per-part PBR with HDR emission and cascaded shadows**. A Studio asset whose
quality comes from textures, smooth skinning, transparency or baked clips will
look worse in Infinity, and under the V0 rule that is a failure. V1 quality must
come from silhouette, part design, purposeful PBR factors, emission and
E1-compatible articulation, unless the runtime path is extended first.
