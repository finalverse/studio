# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Dependency-free, closed creation language shared by UI, workers and MCP."""
import hashlib
import json
import math
import re

SCHEMA = "finalverse.creation/v1"
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


def check(value, schema):
    """The exact JSON Schema subset used above, rejecting bool-as-number and NaN."""
    if 'const' in schema and value != schema['const']:
        raise CreationError("Incorrect operation or schema version")
    if 'enum' in schema and value not in schema['enum']:
        raise CreationError("Unsupported enum value")
    kind = schema.get('type')
    if kind == 'object':
        if not isinstance(value, dict) or set(value) - set(schema['properties']):
            raise CreationError("Unknown object field")
        if set(schema['required']) - set(value):
            raise CreationError("Missing required field")
        for key, item in value.items():
            check(item, schema['properties'][key])
    elif kind == 'array':
        if not isinstance(value, list) or not schema['minItems'] <= len(value) <= schema['maxItems']:
            raise CreationError("Array length out of bounds")
        for item in value:
            if 'oneOf' in schema['items']:
                if not isinstance(item, dict) or item.get('op') not in OPERATIONS:
                    raise CreationError("Operation is not allowlisted")
                check(item, OPERATIONS[item['op']])
            else:
                check(item, schema['items'])
    elif kind == 'string':
        if not isinstance(value, str) or not schema['minLength'] <= len(value) <= schema['maxLength']:
            raise CreationError("String length out of bounds")
        if any(ord(c) < 32 for c in value) or ('pattern' in schema and not re.fullmatch(schema['pattern'], value)):
            raise CreationError("Invalid string or identifier")
    elif kind in ('number', 'integer'):
        if type(value) not in (int, float) or (kind == 'integer' and type(value) is not int):
            raise CreationError("Incorrect numeric type")
        if not math.isfinite(value) or not schema['minimum'] <= value <= schema['maximum']:
            raise CreationError("Number out of bounds")


def validate(plan):
    if len(canonical(plan).encode()) > MAX_BYTES:
        raise CreationError("Plan exceeds 64 KiB")
    check(plan, PLAN_SCHEMA)
    aliases, paths = set(), set()
    for item in plan['operations']:
        for field in ('target', 'material'):
            if field in item and item[field].startswith('@') and item[field] not in aliases:
                raise CreationError("Reference precedes its creation")
        if 'ref' in item:
            if item['ref'] in aliases:
                raise CreationError("Duplicate local reference")
            aliases.add(item['ref'])
        if item['op'] in ('object.transform', 'animation.keyframe'):
            if not {'location', 'rotation', 'scale'} & set(item):
                raise CreationError("Transform requires an allowed property")
        if 'path' in item:
            if item['path'] in paths:
                raise CreationError("Output path reused")
            paths.add(item['path'])
    return plan
