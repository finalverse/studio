# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Dependency-free, closed creation language shared by UI, workers and MCP."""
import hashlib
import json
import math
import re

SCHEMA = "finalverse.creation/v1"
SCHEMA_V2 = "finalverse.creation/v2"
MAX_BYTES = 65536


class CreationError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CreationError("Duplicate JSON key")
        result[key] = value
    return result


def parse(text, maximum=MAX_BYTES):
    if not isinstance(text, str) or len(text.encode()) > maximum:
        raise CreationError("JSON exceeds its byte budget")
    try:
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(CreationError("Nonfinite JSON")))
    except (ValueError, RecursionError) as error:
        raise CreationError("Invalid strict JSON") from error


def number(low, high, integer=False):
    return {"type": "integer" if integer else "number", "minimum": low, "maximum": high}


def vector(n, low, high):
    return {"type": "array", "items": number(low, high), "minItems": n, "maxItems": n}


def string(pattern=None, maximum=80):
    result = {"type": "string", "minLength": 1, "maxLength": maximum}
    if pattern:
        result['pattern'] = pattern
    return result


REF = string(r"^(?:@[a-z][a-z0-9_]{0,31}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
ALIAS = string(r"^@[a-z][a-z0-9_]{0,31}$")
POS = vector(3, -1000, 1000)
ROT = vector(3, -6.284, 6.284)
SCALE = vector(3, .001, 100)
COLOR = vector(4, 0, 1)


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


def op(name, properties, required=None):
    return obj({"op": {"const": name}, **properties},
               ["op", *(properties if required is None else required)])


OPERATIONS = {
    "scene.inspect": op("scene.inspect", {}),
    "object.create": op("object.create", {"ref": ALIAS, "name": string(),
        "primitive": {"enum": ["cube", "sphere", "cylinder", "plane"]}}),
    "object.transform": op("object.transform", {"target": REF, "location": POS, "rotation": ROT,
        "scale": SCALE}, ["target"]),
    "mesh.bevel": op("mesh.bevel", {"target": REF, "width": number(.001, .5), "segments": number(1, 4, True)}),
    "material.create": op("material.create", {"ref": ALIAS, "name": string(), "color": COLOR,
        "roughness": number(0, 1), "metallic": number(0, 1)}),
    "material.assign": op("material.assign", {"target": REF, "material": REF}),
    "camera.configure": op("camera.configure", {"ref": ALIAS, "name": string(), "location": POS,
        "look_at": POS, "lens": number(20, 120)}),
    "light.configure": op("light.configure", {"ref": ALIAS, "name": string(), "location": POS,
        "kind": {"enum": ["AREA", "POINT"]}, "energy": number(0, 5000), "color": vector(3, 0, 1)}),
    "animation.keyframe": op("animation.keyframe", {"target": REF, "frame": number(1, 240, True),
        "location": POS, "rotation": ROT, "scale": SCALE}, ["target", "frame"]),
    "scene.render": op("scene.render", {"path": string(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\.png$"),
        "width": number(64, 1024, True), "height": number(64, 1024, True), "samples": number(1, 64, True)}),
    "scene.save": op("scene.save", {"path": string(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\.blend$")}),
    "asset.export": op("asset.export", {"path": string(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\.fvasset$")}),
}
PLAN_SCHEMA = obj({"schema_version": {"const": SCHEMA}, "summary": string(maximum=512),
                   "operations": {"type": "array", "minItems": 1, "maxItems": 32,
                                  "items": {"oneOf": list(OPERATIONS.values())}}})



# --- finalverse.creation/v2 (S2): typed, bounded creation tools -------------
# Every v2 operation is data. Each one maps to a fixed Blender implementation in
# creation2.py and is covered by scene revision, preflight and evaluation.
NAME = string(maximum=64)
PATH_BLEND = string(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\.blend$")
PATH_PNG = string(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\.png$")
SIZE = vector(3, .001, 200)
RGB = vector(3, 0, 1)
ARCHETYPES = ["humanoid", "synthetic_humanoid", "floating_spirit", "botanical_sprite",
              "nature_elemental", "fire_elemental", "environment", "prop"]
CHANNEL_KEY = obj({"frame": number(1, 480, True), "bone": string(r"^[A-Za-z][A-Za-z0-9_.]{0,47}$", 48),
                   "location": POS, "rotation": ROT, "scale": SCALE}, ["frame"])

V2_ONLY = {
    "mesh.primitive": op("mesh.primitive", {"ref": ALIAS, "name": NAME,
        "shape": {"enum": ["uv_sphere", "ico_sphere", "cube", "cylinder", "cone", "torus", "plane"]},
        "size": SIZE, "location": POS, "rotation": ROT, "segments": number(4, 64, True)},
        ["ref", "name", "shape"]),
    "mesh.subdivide": op("mesh.subdivide", {"target": REF, "levels": number(1, 3, True)}),
    "mesh.deform": op("mesh.deform", {"target": REF, "kind": {"enum": ["taper", "bend", "twist", "stretch"]},
        "axis": {"enum": ["X", "Y", "Z"]}, "amount": number(-3.2, 3.2)}),
    "object.parent": op("object.parent", {"target": REF, "parent": REF}),
    "geonodes.scatter": op("geonodes.scatter", {"ref": ALIAS, "name": NAME, "surface": REF, "instance": REF,
        "count": number(1, 512, True), "seed": number(0, 100000, True), "scale_min": number(.05, 4),
        "scale_max": number(.05, 4)}),
    "procedural.building": op("procedural.building", {"ref": ALIAS, "name": NAME, "location": POS,
        "floors": number(1, 20, True), "width": number(2, 60), "depth": number(2, 60),
        "floor_height": number(2.4, 6), "window_columns": number(0, 16, True),
        "roof": {"enum": ["flat", "gable"]}, "seed": number(0, 100000, True)}),
    "procedural.tree": op("procedural.tree", {"ref": ALIAS, "name": NAME, "location": POS,
        "kind": {"enum": ["broadleaf", "conifer", "shrub"]}, "height": number(.3, 30),
        "trunk_radius": number(.02, 2), "branches": number(0, 12, True), "seed": number(0, 100000, True)}),
    "character.spirit": op("character.spirit", {"ref": ALIAS, "name": NAME, "height": number(.3, 3.5),
        "body_width": number(.5, 1.5), "crown": number(0, 1.5), "fins": number(0, 1.5), "eyes": number(.5, 1.5),
        "location": POS}, ["ref", "name", "height"]),
    "character.humanoid": op("character.humanoid", {"ref": ALIAS, "name": NAME, "height": number(.5, 3.5),
        "build": {"enum": ["human", "synthetic"]}, "location": POS}, ["ref", "name", "height", "build"]),
    "material.preset": op("material.preset", {"ref": ALIAS, "name": NAME, "color": COLOR,
        "roughness": number(.04, 1), "metallic": number(0, 1), "emission": RGB,
        "emission_strength": number(0, 20), "alpha": number(.05, 1)}, ["ref", "name", "color"]),
    "material.assign_parts": op("material.assign_parts", {"target": REF, "material": REF,
        "part": {"enum": ["all", "body", "eyes", "crown", "fins", "trunk", "canopy", "walls", "roof", "windows"]}}),
    "armature.create": op("armature.create", {"ref": ALIAS, "name": NAME,
        "template": {"enum": ["humanoid_basic", "synthetic_basic", "tree_basic", "fire_basic"]},
        "height": number(.3, 3.5), "location": POS}, ["ref", "name", "template", "height"]),
    "armature.skin": op("armature.skin", {"target": REF, "armature": REF,
        "method": {"enum": ["automatic", "envelope"]}}),
    "action.create": op("action.create", {"ref": ALIAS, "name": NAME, "target": REF,
        "kind": {"enum": ["idle", "greet", "observe", "interact", "speak", "locomote"]},
        "locomotion": {"enum": ["none", "walk", "run", "hover", "fly", "drift", "climb", "rooted"]},
        "loop": {"type": "boolean"},
        "keys": {"type": "array", "minItems": 2, "maxItems": 96, "items": CHANNEL_KEY}},
        ["ref", "name", "target", "kind", "locomotion", "loop", "keys"]),
    "action.retarget": op("action.retarget", {"ref": ALIAS, "name": NAME, "action": REF, "source": REF,
        "target": REF, "bone_map": {"type": "array", "minItems": 1, "maxItems": 64,
            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                      "items": string(r"^[A-Za-z][A-Za-z0-9_.]{0,47}$", 48)}}}),
    "light.rig": op("light.rig", {"ref": ALIAS, "name": NAME, "style": {"enum": ["three_point", "soft_key", "rim"]},
        "target": POS, "distance": number(1, 200), "energy": number(10, 20000), "color": RGB}),
    "render.configure": op("render.configure", {"engine": {"enum": ["EEVEE"]}, "frame_start": number(1, 480, True),
        "frame_end": number(1, 480, True), "fps": number(12, 60, True), "transparent": {"type": "boolean"},
        "world_color": RGB, "world_strength": number(0, 10), "view_transform": {"enum": ["Standard", "AgX", "Filmic"]}},
        ["engine", "frame_start", "frame_end", "fps", "transparent"]),
    "preview.render": op("preview.render", {"path": PATH_PNG, "width": number(64, 1024, True),
        "height": number(64, 1024, True), "samples": number(1, 64, True), "frame": number(1, 480, True)},
        ["path", "width", "height", "samples", "frame"]),
    "asset.package": op("asset.package", {"path": string(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\.fvpkg$"),
        "archetype": {"enum": ARCHETYPES}, "subject": REF, "name": NAME,
        "identity": string(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", 36),
        "clips": {"type": "array", "minItems": 0, "maxItems": 16, "items": REF},
        "lod1_ratio": number(.05, 1)}, ["path", "archetype", "subject", "name", "clips"]),
}
OPERATIONS_V2 = {**{k: v for k, v in OPERATIONS.items()}, **V2_ONLY}
PLAN_SCHEMA_V2 = obj({"schema_version": {"const": SCHEMA_V2}, "summary": string(maximum=512),
                      "operations": {"type": "array", "minItems": 1, "maxItems": 48,
                                     "items": {"oneOf": list(OPERATIONS_V2.values())}}})
RENDER_OPS = {"scene.render", "preview.render"}
CREATES = {"object.create": "MESH", "camera.configure": "CAMERA", "light.configure": "LIGHT",
           "mesh.primitive": "MESH", "geonodes.scatter": "MESH", "procedural.building": "MESH",
           "procedural.tree": "MESH", "character.spirit": "MESH", "character.humanoid": "MESH",
           "armature.create": "ARMATURE", "light.rig": "LIGHT"}
MATERIAL_CREATES = {"material.create", "material.preset"}
ACTION_CREATES = {"action.create", "action.retarget"}
REF_FIELDS = ("target", "material", "parent", "surface", "instance", "armature", "subject", "action", "source")


def operations_for(plan):
    return OPERATIONS_V2 if isinstance(plan, dict) and plan.get('schema_version') == SCHEMA_V2 else OPERATIONS


def check(value, schema, path='plan'):
    """The exact JSON Schema subset used above, rejecting bool-as-number and NaN.
    Errors name the JSON path, the offending value and the limit."""
    def fail(reason):
        raise CreationError(f"{path}: {reason}")
    if 'const' in schema and value != schema['const']:
        fail("Incorrect operation or schema version")
    if 'enum' in schema and value not in schema['enum']:
        fail(f"Unsupported enum value {str(value)[:40]!r}; allowed: {'|'.join(map(str, schema['enum']))[:200]}")
    kind = schema.get('type')
    if kind == 'object':
        if not isinstance(value, dict):
            fail("Expected an object")
        unknown = sorted(set(value) - set(schema['properties']))
        if unknown:
            fail(f"Unknown object field {unknown[0][:40]!r}")
        missing = sorted(set(schema['required']) - set(value))
        if missing:
            fail(f"Missing required field {missing[0]!r}")
        for key, item in value.items():
            check(item, schema['properties'][key], f"{path}.{key}")
    elif kind == 'array':
        if not isinstance(value, list) or not schema['minItems'] <= len(value) <= schema['maxItems']:
            fail(f"Array length out of bounds (needs {schema['minItems']}..{schema['maxItems']} items)")
        for i, item in enumerate(value):
            where = f"{path}[{i}]"
            if 'oneOf' in schema['items']:
                table = OPERATIONS_V2 if schema['items'] is PLAN_SCHEMA_V2['properties']['operations']['items'] else OPERATIONS
                if not isinstance(item, dict) or item.get('op') not in table:
                    raise CreationError(f"{where}: Operation is not allowlisted")
                check(item, table[item['op']], f"{where}({item['op']})")
            else:
                check(item, schema['items'], where)
    elif kind == 'boolean':
        if type(value) is not bool:
            fail("Incorrect boolean type (use true or false)")
    elif kind == 'string':
        if not isinstance(value, str) or not schema['minLength'] <= len(value) <= schema['maxLength']:
            fail(f"String length out of bounds ({schema['minLength']}..{schema['maxLength']})")
        if any(ord(c) < 32 for c in value) or ('pattern' in schema and not re.fullmatch(schema['pattern'], value)):
            fail(f"Invalid string or identifier {value[:40]!r}")
    elif kind in ('number', 'integer'):
        if type(value) not in (int, float) or (kind == 'integer' and type(value) is not int):
            fail("Incorrect numeric type" + (" (needs a whole number)" if kind == 'integer' else ""))
        if not math.isfinite(value) or not schema['minimum'] <= value <= schema['maximum']:
            fail(f"Number out of bounds ({value} not in {schema['minimum']}..{schema['maximum']})")


def validate(plan):
    if len(canonical(plan).encode()) > MAX_BYTES:
        raise CreationError("Plan exceeds 64 KiB")
    v2 = isinstance(plan, dict) and plan.get('schema_version') == SCHEMA_V2
    check(plan, PLAN_SCHEMA_V2 if v2 else PLAN_SCHEMA)
    aliases, paths = set(), set()
    kinds = {}
    for item in plan['operations']:
        for field in REF_FIELDS:
            if isinstance(item.get(field), str) and item[field].startswith('@') and item[field] not in aliases:
                raise CreationError("Reference precedes its creation")
        for ref in item.get('clips', []):
            if ref.startswith('@') and kinds.get(ref) != 'ACTION':
                raise CreationError("Package clip must reference a created action")
        if 'ref' in item:
            if item['ref'] in aliases:
                raise CreationError("Duplicate local reference")
            aliases.add(item['ref'])
            kinds[item['ref']] = ('ACTION' if item['op'] in ACTION_CREATES else
                                  'MATERIAL' if item['op'] in MATERIAL_CREATES else CREATES.get(item['op']))
        if item['op'] in ('object.transform', 'animation.keyframe'):
            if not {'location', 'rotation', 'scale'} & set(item):
                raise CreationError("Transform requires an allowed property")
        if item['op'] == 'action.create':
            frames = [k['frame'] for k in item['keys']]
            if frames != sorted(frames) or any(not {'location', 'rotation', 'scale'} & set(k) for k in item['keys']):
                raise CreationError("Action keys need ascending frames and a channel")
        if item['op'] == 'geonodes.scatter' and item['scale_min'] > item['scale_max']:
            raise CreationError("Scatter scale range is inverted")
        if item['op'] == 'render.configure' and item['frame_start'] > item['frame_end']:
            raise CreationError("Render frame range is inverted")
        if 'path' in item:
            if item['path'] in paths:
                raise CreationError("Output path reused")
            paths.add(item['path'])
    if v2:
        archetype_rules(plan, kinds)
    return plan


SPIRITS = {"floating_spirit", "botanical_sprite"}
LOCOMOTION = {"humanoid": {"walk", "run", "climb", "none"}, "synthetic_humanoid": {"walk", "run", "climb", "none"},
              "floating_spirit": {"hover", "fly", "drift", "none"}, "botanical_sprite": {"fly", "hover", "drift", "none"},
              "nature_elemental": {"rooted", "walk", "climb", "none"}, "fire_elemental": {"walk", "run", "hover", "none"},
              "environment": {"none"}, "prop": {"none", "hover", "drift"}}


def archetype_rules(plan, kinds):
    """E1 archetype contract, enforced before any approval (not a single humanoid skeleton)."""
    packages = [i for i in plan['operations'] if i['op'] == 'asset.package']
    if len(packages) > 1:
        raise CreationError("One asset package per plan")
    if not packages:
        return
    archetype = packages[0]['archetype']
    clips = set(packages[0]['clips'])
    for item in plan['operations']:
        if archetype in SPIRITS:
            if item['op'] in {'armature.create', 'armature.skin', 'action.retarget', 'character.humanoid'}:
                raise CreationError(archetype + " has no skeleton or humanoid body")
            if any(word in item.get('name', '').lower() for word in ('leg', 'foot', 'walk')):
                raise CreationError(archetype + " cannot acquire conventional legs or walking")
        if item['op'] == 'action.create' and item['ref'] in clips and item['locomotion'] not in LOCOMOTION[archetype]:
            raise CreationError(f"{item['locomotion']} locomotion is not allowed for {archetype}")


