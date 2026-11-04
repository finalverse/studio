"""Stable finding catalogue and collection.

Finding codes are part of the ``finalverse.asset-intelligence/v1`` contract: a code
is never renumbered or reused with a different meaning.  New codes are appended.

Classes
-------
``spec``           the asset violates glTF 2.0 (it is not a valid glTF asset)
``security``       the inspector refused untrusted content (e.g. a remote URI)
``resource``       an inspection safety limit was reached; inspection is incomplete
``limit``          valid glTF that exceeds a configured Finalverse runtime budget
``compatibility``  valid glTF that a Finalverse profile cannot consume
``quality``        advisory: the asset is valid but likely deficient
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEVERITIES = ("critical", "error", "warning", "info")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}
CLASSES = ("spec", "security", "resource", "limit", "compatibility", "quality")


@dataclass(frozen=True)
class Code:
    code: str
    name: str
    category: str
    cls: str
    severity: str
    action: str
    impact: str
    validation: tuple[str, ...]
    confidence: str = "high"


_ENTRIES: list[Code] = []


def _c(code, name, category, cls, severity, action, impact, validation, confidence="high"):
    assert cls in CLASSES and severity in SEVERITIES, code
    _ENTRIES.append(Code(code, name, category, cls, severity, action, impact, tuple(validation), confidence))


RE_INSPECT = "re-run finalverse-asset validate"
RE_EXPORT = "re-export from the authoring tool and re-run finalverse-asset validate"
RENDER = "render the corrected asset in Blender and Infinity and compare against the previous render"

# --- container -------------------------------------------------------------
_c(
    "FVA-CON-001",
    "unrecognized_container",
    "container",
    "spec",
    "critical",
    "Provide a glTF 2.0 asset: a GLB binary (magic 'glTF') or a UTF-8 JSON .gltf document.",
    "The asset can be parsed at all.",
    [RE_INSPECT],
)
_c(
    "FVA-CON-002",
    "glb_header_invalid",
    "container",
    "spec",
    "critical",
    "Re-export as GLB version 2 with a valid 12-byte header.",
    "The binary container can be read.",
    [RE_EXPORT],
)
_c(
    "FVA-CON-003",
    "glb_length_mismatch",
    "container",
    "spec",
    "critical",
    "The file is truncated or has trailing data; re-export or re-transfer it and verify its digest.",
    "The complete binary is available to readers.",
    [RE_EXPORT, "compare sha256 with the source export"],
)
_c(
    "FVA-CON-004",
    "glb_chunk_invalid",
    "container",
    "spec",
    "critical",
    "Write the JSON chunk first and the BIN chunk second, with lengths inside the file.",
    "Chunk data can be located.",
    [RE_EXPORT],
)
_c(
    "FVA-CON-005",
    "glb_chunk_alignment",
    "container",
    "spec",
    "error",
    "Pad GLB chunks to 4-byte boundaries (JSON with spaces, BIN with zeros).",
    "Strict readers (including Finalverse EC and Infinity) accept the container.",
    [RE_EXPORT],
)
_c(
    "FVA-CON-006",
    "json_invalid",
    "container",
    "spec",
    "critical",
    "Emit standard UTF-8 JSON without a byte-order mark.",
    "The document can be parsed.",
    [RE_EXPORT],
)
_c(
    "FVA-CON-007",
    "json_duplicate_key",
    "container",
    "spec",
    "error",
    "Remove duplicate object keys; readers disagree about which value wins.",
    "The document has a single unambiguous meaning; Finalverse strict JSON accepts it.",
    [RE_EXPORT],
)
_c(
    "FVA-CON-008",
    "json_nonfinite_number",
    "container",
    "spec",
    "error",
    "Replace overflowing or NaN numbers with finite values.",
    "All numeric properties are finite.",
    [RE_EXPORT],
)
_c(
    "FVA-CON-009",
    "schema_violation",
    "container",
    "spec",
    "error",
    "Correct the property type or supply the required property as defined by the glTF 2.0 schema.",
    "The document conforms to the glTF schema.",
    [RE_EXPORT],
)
_c(
    "FVA-CON-010",
    "asset_version_unsupported",
    "container",
    "spec",
    "critical",
    "Export as glTF 2.0 (asset.version '2.0').",
    "The asset uses the supported specification.",
    [RE_EXPORT],
)
_c(
    "FVA-CON-011",
    "index_out_of_range",
    "container",
    "spec",
    "error",
    "Fix the dangling index so it references an existing object.",
    "References resolve.",
    [RE_EXPORT],
)

# --- security ----------------------------------------------------------------
_c(
    "FVA-SEC-001",
    "remote_uri_refused",
    "security",
    "security",
    "error",
    "Embed the resource in the GLB or ship it as a reviewed local file; remote URIs are never fetched.",
    "The asset is self-contained and reproducible without network access.",
    [RE_INSPECT, "confirm no remote dependency remains"],
)
_c(
    "FVA-SEC-002",
    "unsafe_path_refused",
    "security",
    "security",
    "error",
    "Use a relative path inside the asset directory without '..', absolute roots or links that escape it.",
    "Resource resolution cannot read files outside the asset.",
    [RE_INSPECT],
)
_c(
    "FVA-SEC-003",
    "data_uri_invalid",
    "security",
    "spec",
    "error",
    "Encode embedded data as a base64 data: URI with a supported media type.",
    "Embedded resources decode.",
    [RE_EXPORT],
)

# --- resource limits ---------------------------------------------------------
_c(
    "FVA-RES-001",
    "file_too_large",
    "resource",
    "resource",
    "critical",
    "Reduce the asset or inspect it with an explicitly raised --limits configuration.",
    "The asset can be inspected within safety limits.",
    [RE_INSPECT],
)
_c(
    "FVA-RES-002",
    "json_limit_exceeded",
    "resource",
    "resource",
    "critical",
    "Reduce JSON size, nesting depth or array length.",
    "The document can be parsed safely.",
    [RE_INSPECT],
)
_c(
    "FVA-RES-003",
    "decode_budget_exceeded",
    "resource",
    "resource",
    "error",
    "Reduce accessor data or raise max_decoded_components; data beyond the budget was not checked.",
    "All accessor data is checked.",
    [RE_INSPECT],
)
_c(
    "FVA-RES-004",
    "time_budget_exceeded",
    "resource",
    "resource",
    "critical",
    "Reduce the asset or raise time_budget_seconds; the inspection stopped early.",
    "Inspection completes.",
    [RE_INSPECT],
)
_c(
    "FVA-RES-005",
    "node_depth_exceeded",
    "resource",
    "resource",
    "error",
    "Flatten the node hierarchy.",
    "The hierarchy can be traversed within limits.",
    [RE_INSPECT],
)

# --- buffers and accessors ---------------------------------------------------
_c(
    "FVA-BUF-001",
    "buffer_data_missing",
    "buffer",
    "spec",
    "error",
    "Provide buffer data: a GLB BIN chunk for buffer 0 or a valid uri.",
    "Geometry and animation data load.",
    [RE_EXPORT],
)
_c(
    "FVA-BUF-002",
    "buffer_length_mismatch",
    "buffer",
    "spec",
    "error",
    "Set buffer.byteLength to the actual data length.",
    "Buffer bounds are trustworthy.",
    [RE_EXPORT],
)
_c(
    "FVA-BUF-003",
    "buffer_view_out_of_bounds",
    "buffer",
    "spec",
    "error",
    "Keep bufferView byteOffset+byteLength within its buffer.",
    "Readers do not overrun buffers.",
    [RE_EXPORT],
)
_c(
    "FVA-BUF-004",
    "buffer_view_stride_invalid",
    "buffer",
    "spec",
    "error",
    "Use a byteStride between 4 and 252 that is a multiple of 4 and at least the element size.",
    "Interleaved data decodes correctly.",
    [RE_EXPORT],
)
_c(
    "FVA-BUF-005",
    "accessor_out_of_bounds",
    "buffer",
    "spec",
    "error",
    "Make accessor count, offset and stride fit inside the bufferView.",
    "Readers do not overrun data.",
    [RE_EXPORT],
)
_c(
    "FVA-BUF-006",
    "accessor_misaligned",
    "buffer",
    "spec",
    "error",
    "Align accessor offsets to the component size.",
    "Data can be read without misaligned access.",
    [RE_EXPORT],
)
_c(
    "FVA-BUF-007",
    "accessor_encoding_invalid",
    "buffer",
    "spec",
    "error",
    "Use a valid componentType/type combination appropriate for the attribute semantic.",
    "Values are interpreted as intended.",
    [RE_EXPORT],
)
_c(
    "FVA-BUF-008",
    "accessor_bounds_mismatch",
    "buffer",
    "spec",
    "error",
    "Recompute accessor min/max from the data.",
    "Culling and bounds use correct values.",
    [RE_EXPORT],
)
_c(
    "FVA-BUF-009",
    "accessor_bounds_missing",
    "buffer",
    "spec",
    "error",
    "Write min/max for POSITION and animation input accessors.",
    "Bounds and clip durations are known.",
    [RE_EXPORT],
)
_c(
    "FVA-BUF-010",
    "accessor_nonfinite",
    "buffer",
    "spec",
    "error",
    "Remove NaN/Inf values from float accessors.",
    "Geometry renders and simulates deterministically.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-BUF-011",
    "sparse_accessor_invalid",
    "buffer",
    "spec",
    "error",
    "Use strictly increasing in-range sparse indices with valid index component types.",
    "Sparse substitutions apply correctly.",
    [RE_EXPORT],
)

# --- dependencies ------------------------------------------------------------
_c(
    "FVA-DEP-001",
    "external_resource_missing",
    "dependency",
    "spec",
    "error",
    "Ship the referenced file next to the asset or embed it.",
    "All textures and buffers are available.",
    [RE_INSPECT, RENDER],
)
_c(
    "FVA-DEP-002",
    "external_dependency",
    "dependency",
    "compatibility",
    "warning",
    "Embed external resources (export as self-contained GLB) for Finalverse publication.",
    "The asset is a single content-addressed artifact.",
    [RE_INSPECT],
)

# --- scene -------------------------------------------------------------------
_c(
    "FVA-SCN-001",
    "node_hierarchy_invalid",
    "scene",
    "spec",
    "error",
    "Make the node graph a set of disjoint trees: no cycles, one parent per node, valid child indices.",
    "Transforms are well defined.",
    [RE_EXPORT],
)
_c(
    "FVA-SCN-002",
    "transform_nonfinite",
    "scene",
    "spec",
    "error",
    "Replace non-finite node transform values.",
    "Nodes have well-defined placement.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-SCN-003",
    "transform_conflict",
    "scene",
    "spec",
    "error",
    "Use either matrix or translation/rotation/scale, not both.",
    "Transforms are unambiguous.",
    [RE_EXPORT],
)
_c(
    "FVA-SCN-004",
    "rotation_not_unit",
    "scene",
    "spec",
    "error",
    "Normalize node rotation quaternions.",
    "Rotations do not introduce scale or skew.",
    [RE_EXPORT],
)
_c(
    "FVA-SCN-005",
    "scene_root_not_root",
    "scene",
    "spec",
    "error",
    "List only root nodes (nodes without a parent) in scene.nodes.",
    "Scene traversal visits each node once.",
    [RE_EXPORT],
)
_c(
    "FVA-SCN-006",
    "no_default_scene",
    "scene",
    "quality",
    "info",
    "Define scenes and the default scene so consumers know what to display.",
    "Deterministic scene selection.",
    [RE_EXPORT],
)
_c(
    "FVA-SCN-007",
    "skinned_node_transform_ignored",
    "scene",
    "spec",
    "warning",
    "Remove local transforms from skinned mesh nodes; glTF ignores them.",
    "Authoring intent matches runtime placement.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-SCN-008",
    "degenerate_transform",
    "scene",
    "quality",
    "warning",
    "Avoid zero or near-zero scale; it collapses geometry and produces singular matrices.",
    "Geometry remains visible and normals well defined.",
    [RE_EXPORT, RENDER],
)

# --- geometry ----------------------------------------------------------------
_c(
    "FVA-GEO-001",
    "position_missing",
    "geometry",
    "spec",
    "warning",
    "Provide a POSITION attribute; primitives without positions are not rendered.",
    "Geometry is visible.",
    [RE_EXPORT],
)
_c(
    "FVA-GEO-002",
    "attribute_count_mismatch",
    "geometry",
    "spec",
    "error",
    "Give all attributes of a primitive the same count.",
    "Vertices are consistent.",
    [RE_EXPORT],
)
_c(
    "FVA-GEO-003",
    "index_out_of_range",
    "geometry",
    "spec",
    "error",
    "Fix triangle indices so every index is below the vertex count.",
    "No out-of-bounds vertex fetch.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-GEO-004",
    "index_restart_value",
    "geometry",
    "spec",
    "error",
    "Do not use the maximum index value (primitive restart) in glTF index data.",
    "Consistent behaviour across graphics APIs.",
    [RE_EXPORT],
)
_c(
    "FVA-GEO-005",
    "index_count_invalid",
    "geometry",
    "spec",
    "error",
    "Use an index count that matches the primitive mode (multiple of 3 for triangles).",
    "All triangles are complete.",
    [RE_EXPORT],
)
_c(
    "FVA-GEO-006",
    "degenerate_triangles",
    "geometry",
    "quality",
    "warning",
    "Remove zero-area triangles (merge by distance / dissolve degenerate in Blender).",
    "Cleaner topology, fewer shading artifacts; Finalverse EC refuses degenerate triangles.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-GEO-007",
    "normals_missing",
    "geometry",
    "quality",
    "warning",
    "Export vertex normals (enable Normals in the glTF exporter; set shading smooth/flat intentionally).",
    "Lighting matches authoring intent instead of renderer-generated flat normals.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-GEO-008",
    "normals_not_unit",
    "geometry",
    "spec",
    "error",
    "Normalize vertex normals.",
    "Correct lighting.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-GEO-009",
    "primitive_mode_invalid",
    "geometry",
    "spec",
    "error",
    "Use a primitive mode between 0 and 6.",
    "The primitive can be drawn.",
    [RE_EXPORT],
)
_c(
    "FVA-GEO-010",
    "primitive_mode_unsupported",
    "geometry",
    "compatibility",
    "warning",
    "Triangulate the primitive (mode 4); Finalverse runtime profiles accept indexed triangles only.",
    "The primitive is consumable by Finalverse runtimes.",
    [RE_EXPORT],
)
_c(
    "FVA-GEO-011",
    "bounds_invalid",
    "geometry",
    "quality",
    "warning",
    "Check scale and units: the asset should have a finite, non-empty extent in metres.",
    "Correct placement and culling in Finalverse frames.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-GEO-012",
    "attribute_semantic_invalid",
    "geometry",
    "spec",
    "error",
    "Use accessor types allowed for the attribute semantic (e.g. NORMAL float VEC3).",
    "Attributes are interpreted correctly.",
    [RE_EXPORT],
)
_c(
    "FVA-GEO-013",
    "texcoord_missing",
    "geometry",
    "spec",
    "error",
    "Export the UV set referenced by the material's textures.",
    "Textures map onto the surface.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-GEO-014",
    "tangents_missing",
    "geometry",
    "quality",
    "info",
    "Export tangents for normal-mapped primitives to make tangent space deterministic.",
    "Normal maps shade identically in Blender and Infinity.",
    [RENDER],
    "medium",
)
_c(
    "FVA-GEO-015",
    "mesh_without_primitives",
    "geometry",
    "spec",
    "error",
    "Give every mesh at least one primitive.",
    "The mesh is drawable.",
    [RE_EXPORT],
)
_c(
    "FVA-GEO-016",
    "morph_target_invalid",
    "geometry",
    "spec",
    "error",
    "Give morph targets the same vertex count as their primitive and consistent target counts.",
    "Blend shapes deform correctly.",
    [RE_EXPORT],
)

# --- materials ---------------------------------------------------------------
_c(
    "FVA-MAT-001",
    "material_factor_out_of_range",
    "material",
    "spec",
    "error",
    "Clamp material factors to their specified ranges.",
    "Physically plausible shading.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-MAT-002",
    "alpha_mode_invalid",
    "material",
    "spec",
    "error",
    "Use alphaMode OPAQUE, MASK or BLEND.",
    "Transparency is interpreted correctly.",
    [RE_EXPORT],
)
_c(
    "FVA-MAT-003",
    "alpha_cutoff_ignored",
    "material",
    "spec",
    "warning",
    "Remove alphaCutoff or set alphaMode MASK.",
    "Authoring intent is explicit.",
    [RE_EXPORT],
)
_c(
    "FVA-MAT-004",
    "texture_reference_invalid",
    "material",
    "spec",
    "error",
    "Reference existing textures, images and samplers.",
    "Textures load.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-MAT-005",
    "image_invalid",
    "material",
    "spec",
    "error",
    "Provide a decodable PNG or JPEG image with a mimeType matching its content.",
    "Textures decode.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-MAT-006",
    "image_format_extension",
    "material",
    "compatibility",
    "warning",
    "Provide a PNG/JPEG fallback or confirm the runtime supports the image extension.",
    "Textures display in all Finalverse runtimes.",
    [RENDER],
)
_c(
    "FVA-MAT-007",
    "texture_dimension_over_budget",
    "material",
    "limit",
    "warning",
    "Downscale the texture to the configured maximum dimension.",
    "Lower memory and upload cost.",
    [RE_INSPECT, RENDER],
)
_c(
    "FVA-MAT-008",
    "texture_not_power_of_two",
    "material",
    "quality",
    "info",
    "Prefer power-of-two texture dimensions for mipmapping and compression.",
    "Better filtering and compression.",
    [RENDER],
    "medium",
)
_c(
    "FVA-MAT-009",
    "default_material",
    "material",
    "quality",
    "info",
    "Assign an explicit material; the glTF default material is plain white.",
    "Intended appearance is explicit.",
    [RENDER],
)
_c(
    "FVA-MAT-010",
    "unused_material_resource",
    "material",
    "quality",
    "info",
    "Remove unreferenced materials, textures or images.",
    "Smaller asset, clearer provenance.",
    [RE_EXPORT],
)

# --- extensions --------------------------------------------------------------
_c(
    "FVA-EXT-001",
    "extension_required_unsupported",
    "extension",
    "compatibility",
    "error",
    "Re-export without the required extension, or confirm runtime support before publication.",
    "The asset loads in Finalverse runtimes that do not implement the extension.",
    [RE_EXPORT],
)
_c(
    "FVA-EXT-002",
    "extension_not_declared",
    "extension",
    "spec",
    "warning",
    "List every used extension in extensionsUsed.",
    "Readers can detect the extension.",
    [RE_EXPORT],
)
_c(
    "FVA-EXT-003",
    "extension_required_not_used",
    "extension",
    "spec",
    "error",
    "Every extensionsRequired entry must also appear in extensionsUsed.",
    "Consistent extension declarations.",
    [RE_EXPORT],
)
_c(
    "FVA-EXT-004",
    "extension_optional_unverified",
    "extension",
    "compatibility",
    "info",
    "Confirm whether Finalverse runtimes honour this optional extension; until then its effect is unverified.",
    "Known rendering behaviour.",
    [RENDER],
    "medium",
)

# --- skins -------------------------------------------------------------------
_c(
    "FVA-SKN-001",
    "skin_joints_invalid",
    "skin",
    "spec",
    "error",
    "Give the skin a non-empty list of unique, existing joint nodes.",
    "The skeleton resolves.",
    [RE_EXPORT],
)
_c(
    "FVA-SKN-002",
    "inverse_bind_invalid",
    "skin",
    "spec",
    "error",
    "Export one finite, invertible MAT4 inverse bind matrix per joint.",
    "Skinning is well defined.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-SKN-003",
    "skeleton_root_invalid",
    "skin",
    "spec",
    "error",
    "Make all joints share one hierarchy and set skin.skeleton to their common root.",
    "Joint transforms are computed from one root.",
    [RE_EXPORT],
)
_c(
    "FVA-SKN-004",
    "skin_attributes_missing",
    "skin",
    "spec",
    "error",
    "Export JOINTS_0 and WEIGHTS_0 for skinned primitives.",
    "Vertices follow the skeleton.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-SKN-005",
    "joint_index_out_of_range",
    "skin",
    "spec",
    "error",
    "Keep JOINTS_n values below the skin's joint count.",
    "No invalid joint palette access.",
    [RE_EXPORT],
)
_c(
    "FVA-SKN-006",
    "weights_invalid",
    "skin",
    "spec",
    "error",
    "Use non-negative joint weights.",
    "Stable deformation.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-SKN-007",
    "weights_not_normalized",
    "skin",
    "spec",
    "warning",
    "Normalize per-vertex weights to sum to 1 (Blender: Normalize All).",
    "No shrinking or inflating vertices.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-SKN-008",
    "skin_without_mesh",
    "skin",
    "spec",
    "error",
    "Only nodes with a mesh may reference a skin.",
    "Skins attach to geometry.",
    [RE_EXPORT],
)
_c(
    "FVA-SKN-009",
    "bind_pose_differs_from_rest",
    "skin",
    "quality",
    "info",
    "Apply the rest pose so inverse binds equal the inverse rest transforms (required by finalverse.humanoid/v1).",
    "Retargeting and embodiment admission see a consistent rest pose.",
    [RE_EXPORT],
    "medium",
)
_c(
    "FVA-SKN-010",
    "unweighted_vertices",
    "skin",
    "spec",
    "error",
    "Weight every skinned vertex to at least one joint.",
    "No vertices collapse to the origin.",
    [RE_EXPORT, RENDER],
)

# --- animation ---------------------------------------------------------------
_c(
    "FVA-ANM-001",
    "channel_target_invalid",
    "animation",
    "spec",
    "error",
    "Target an existing node with path translation, rotation, scale or weights.",
    "The channel animates something.",
    [RE_EXPORT],
)
_c(
    "FVA-ANM-002",
    "sampler_invalid",
    "animation",
    "spec",
    "error",
    "Use valid sampler references, interpolation and accessor types for the target path.",
    "Keyframes are interpreted correctly.",
    [RE_EXPORT],
)
_c(
    "FVA-ANM-003",
    "keyframes_not_increasing",
    "animation",
    "spec",
    "error",
    "Make keyframe times strictly increasing (remove duplicate keys).",
    "Deterministic interpolation.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-ANM-004",
    "keyframe_count_mismatch",
    "animation",
    "spec",
    "error",
    "Match the output accessor count to input keys (x3 for CUBICSPLINE, x targets for weights).",
    "Every key has a value.",
    [RE_EXPORT],
)
_c(
    "FVA-ANM-005",
    "duplicate_channel_target",
    "animation",
    "spec",
    "error",
    "Use at most one channel per node and path in an animation.",
    "Unambiguous animation.",
    [RE_EXPORT],
)
_c(
    "FVA-ANM-006",
    "rotation_keys_not_unit",
    "animation",
    "spec",
    "error",
    "Normalize rotation keyframe quaternions.",
    "Rotations do not scale or skew.",
    [RE_EXPORT, RENDER],
)
_c(
    "FVA-ANM-007",
    "morph_animation_invalid",
    "animation",
    "spec",
    "error",
    "Animate weights only on nodes whose mesh has morph targets.",
    "Morph animation applies.",
    [RE_EXPORT],
)
_c(
    "FVA-ANM-008",
    "animation_empty",
    "animation",
    "spec",
    "error",
    "Give each animation at least one channel and sampler.",
    "The clip does something.",
    [RE_EXPORT],
)
_c(
    "FVA-ANM-009",
    "negative_keyframe_time",
    "animation",
    "spec",
    "error",
    "Use keyframe times >= 0.",
    "Clips start at a defined time.",
    [RE_EXPORT],
)
_c(
    "FVA-ANM-010",
    "animation_unnamed",
    "animation",
    "quality",
    "info",
    "Name animations so capabilities (idle, walk, ...) can be identified.",
    "Clips are addressable by intent.",
    [RE_EXPORT],
)

# --- runtime budget ----------------------------------------------------------
for _i, (_m, _what, _fix) in enumerate(
    [
        ("max_triangles", "triangle count", "Decimate or provide LODs."),
        ("max_vertices", "vertex count", "Reduce vertex count (merge, decimate, remove hidden geometry)."),
        ("max_file_bytes", "file size", "Compress textures/geometry or split the asset."),
        ("max_draw_calls", "primitive (draw call) count", "Merge primitives that share a material."),
        ("max_materials", "material count", "Merge or atlas materials."),
        ("max_joints", "joint count", "Reduce joint count or provide a simplified runtime rig."),
        ("max_animations", "animation count", "Split animation libraries from the body asset."),
        ("max_morph_targets", "morph target count", "Reduce morph targets per mesh."),
        ("max_nodes", "node count", "Flatten or merge nodes."),
    ],
    start=1,
):
    _c(
        f"FVA-CPX-{_i:03d}",
        f"{_m[4:]}_over_budget",
        "complexity",
        "limit",
        "warning",
        f"{_fix} The configured runtime budget for {_what} is exceeded.",
        f"The asset fits the configured Finalverse {_what} budget.",
        [RE_INSPECT, RENDER],
    )

# --- compatibility and embodiment --------------------------------------------
_c(
    "FVA-CMP-001",
    "target_profile_incompatible",
    "compatibility",
    "compatibility",
    "error",
    "Address the failed rules of the selected runtime profile.",
    "The asset is admissible to the target runtime.",
    [RE_INSPECT, "run the target runtime's own admission (Codex integration)"],
)
_c(
    "FVA-EMB-001",
    "embodiment_requirement_unmet",
    "embodiment",
    "compatibility",
    "error",
    "Satisfy the embodiment profile requirement.",
    "The body is usable for the intended embodiment.",
    [RE_INSPECT, "E1 runtime integration test (Codex)"],
    "medium",
)
_c(
    "FVA-EMB-002",
    "embodiment_capability_missing",
    "embodiment",
    "quality",
    "warning",
    "Add the expected capability (clip or feature) to the asset.",
    "The resident can perform the expected behaviour.",
    [RE_INSPECT, "E1 runtime integration test (Codex)"],
    "medium",
)

_c(
    "FVA-QLT-001",
    "visual_evidence_invalid",
    "quality",
    "quality",
    "warning",
    "Supply a finalverse.visual-evidence/v0 file whose renders exist, match their sha256 and are assessed.",
    "Subjective quality categories and tiers Q2+ can be assessed.",
    ["re-run with --visual-evidence"],
)

CATALOGUE: dict[str, Code] = {e.code: e for e in _ENTRIES}
assert len(CATALOGUE) == len(_ENTRIES), "duplicate finding code"


@dataclass
class Finding:
    code: str
    pointer: str
    message: str
    severity: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def meta(self) -> Code:
        return CATALOGUE[self.code]

    @property
    def id(self) -> str:
        return f"{self.code}:{self.pointer or '/'}"

    def sort_key(self) -> tuple:
        return (SEVERITY_RANK[self.severity], self.code, self.pointer, self.message)

    def to_dict(self) -> dict[str, Any]:
        m = self.meta
        return {
            "id": self.id,
            "code": self.code,
            "name": m.name,
            "category": m.category,
            "class": m.cls,
            "severity": self.severity,
            "component": self.pointer or "/",
            "message": self.message,
            "evidence": self.evidence,
        }


class Collector:
    """Accumulates findings; merges repeats of the same code at the same pointer."""

    def __init__(self, max_per_code: int = 200) -> None:
        self._items: dict[tuple[str, str], Finding] = {}
        self._per_code: dict[str, int] = {}
        self._suppressed: dict[str, int] = {}
        self.max_per_code = max_per_code

    def add(
        self, code: str, pointer: str, message: str, evidence: dict[str, Any] | None = None, severity: str | None = None
    ) -> Finding | None:
        meta = CATALOGUE[code]
        key = (code, pointer)
        if key in self._items:
            f = self._items[key]
            f.evidence["occurrences"] = f.evidence.get("occurrences", 1) + 1
            return f
        if self._per_code.get(code, 0) >= self.max_per_code:
            self._suppressed[code] = self._suppressed.get(code, 0) + 1
            return None
        self._per_code[code] = self._per_code.get(code, 0) + 1
        f = Finding(code, pointer, message, severity or meta.severity, dict(evidence or {}))
        self._items[key] = f
        return f

    def has(self, code: str) -> bool:
        return any(k[0] == code for k in self._items)

    def all(self) -> list[Finding]:
        return sorted(self._items.values(), key=Finding.sort_key)

    @property
    def suppressed(self) -> dict[str, int]:
        return dict(sorted(self._suppressed.items()))
