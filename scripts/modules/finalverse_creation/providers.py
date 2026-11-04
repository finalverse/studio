# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Network-only helper. Never imports bpy or executes model-provided code."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .protocol import CreationError, PLAN_SCHEMA, canonical, digest, parse, validate


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CreationError("Provider redirects are refused")


def profile(value):
    fields = {'id', 'kind', 'base_url', 'token_env', 'timeout_seconds', 'enabled'}
    if not isinstance(value, dict) or set(value) != fields:
        raise CreationError("Invalid provider configuration")
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', value['id']):
        raise CreationError("Invalid provider ID")
    if value['kind'] not in {'ollama', 'openai_compatible'} or type(value['enabled']) is not bool:
        raise CreationError("Unsupported provider type")
    url = urllib.parse.urlsplit(value['base_url'])
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise CreationError("Provider URL must not embed credentials or query parameters")
    try:
        loopback = ipaddress.ip_address(url.hostname).is_loopback
    except ValueError:
        loopback = url.hostname == 'localhost'
    if url.scheme not in {'http', 'https'} or (not loopback and url.scheme != 'https'):
        raise CreationError("Remote providers require an authenticated HTTPS gateway")
    token = value['token_env']
    if token is not None and (not isinstance(token, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{1,79}', token)):
        raise CreationError("Invalid credential environment reference")
    if not loopback and token is None:
        raise CreationError("Remote providers require a credential environment reference")
    if type(value['timeout_seconds']) not in (int, float) or not 2 <= value['timeout_seconds'] <= 120:
        raise CreationError("Provider timeout must be 2–120 seconds")
    return value


def registry(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 16384:
        raise CreationError("Invalid provider registry file")
    data = parse(path.read_text())
    if set(data) != {'schema_version', 'providers'} or data['schema_version'] != 'finalverse.providers/v1':
        raise CreationError("Incorrect provider registry version")
    if not isinstance(data['providers'], list) or not 1 <= len(data['providers']) <= 8:
        raise CreationError("Provider registry limit is eight")
    result = {}
    for item in data['providers']:
        p = profile(item)
        if p['id'] in result:
            raise CreationError("Duplicate provider ID")
        result[p['id']] = p
    return result


def default_registry(path):
    path = Path(path)
    if not path.exists():
        data = {'schema_version': 'finalverse.providers/v1', 'providers': [
            {'id': 'local', 'kind': 'ollama', 'base_url': 'http://127.0.0.1:11434',
             'token_env': None, 'timeout_seconds': 120, 'enabled': True}]}
        with path.open('x') as f:
            f.write(json.dumps(data, indent=2))
        os.chmod(path, 0o600)


def request(p, route, payload=None):
    if not p['enabled']:
        raise CreationError("Provider is disabled")
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if p['token_env']:
        token = os.environ.get(p['token_env'])
        if not token or '\n' in token or '\r' in token:
            raise CreationError("Configured provider credential is unavailable")
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(p['base_url'].rstrip('/') + route,
                                 canonical(payload).encode() if payload is not None else None, headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=p['timeout_seconds']) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise CreationError("Provider response exceeds 1 MiB")
    # Provider envelopes may be larger than a valid creation plan.
    return json.loads(data, parse_constant=lambda _: None)


def inventory(p):
    if p['kind'] == 'ollama':
        result = request(p, '/api/tags')
        records = result.get('models', [])
        names = [m['name'] for m in records]
    else:
        result = request(p, '/models')
        records = result.get('data', [])
        names = [m['id'] for m in records]
    if len(names) > 256 or any(not isinstance(n, str) or not 0 < len(n) <= 200 for n in names):
        raise CreationError("Invalid model inventory")
    return dict(zip(names, records))


def models(p):
    return sorted(inventory(p), key=lambda n: (not any(s in n.lower() for s in ['gemma', 'qwen']), n))


def admit_local(p, record):
    hostname = urllib.parse.urlsplit(p['base_url']).hostname
    try: loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError: loopback = hostname == 'localhost'
    if p['kind'] != 'ollama' or not loopback:
        return
    physical = os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    size = record.get('size')
    if type(size) is not int or size <= 0 or size > physical*.65:
        raise CreationError('Local model weights exceed the 65% physical-memory admission budget or have no size; choose a smaller model or configured remote provider')


SYSTEM = """You are Finalverse Studio's planner. Return only strict JSON matching the supplied
creation schema. Never emit Python, shell commands, markdown or unknown operations. You propose;
the human approves. Use @references for objects/materials you create, and UUIDs for existing ones.
Output filenames are basenames inside a new job directory. Do not publish or claim authorization.
Use metres, radians, Z-up for Blender operations. For a visible preview, add a camera looking at
the subject and an AREA light. Use material.create's RGBA color for the Principled BSDF.
Keep plans small. Include geometry modification, material assignment and at least two animation
keyframes when requested. Do not recreate existing objects when asked to modify their UUIDs.
Creation example: {"schema_version":"finalverse.creation/v1","summary":"New cube",
"operations":[{"op":"object.create","ref":"@cube","name":"Cube","primitive":"cube"},
{"op":"mesh.bevel","target":"@cube","width":0.1,"segments":2}]}.
object.transform cannot create an object. Every transform/keyframe needs a transform property.
rotation is EXACTLY three Euler numbers, never a quaternion or extra scale values.
camera.configure and light.configure CREATE their objects; never precede them with object.create.
object.create's primitive is only cube, sphere, cylinder or plane. Each ref is declared once.
"""

# A complete worked example teaches the small local models the language more
# reliably than a long JSON Schema union alone. It is prompt context, never an
# execution fallback; only a fresh validated model response can become a job.
EXAMPLE = {'schema_version': 'finalverse.creation/v1', 'summary': 'Example only: blue animated sample', 'operations': [
    {'op': 'scene.inspect'},
    {'op': 'object.create', 'ref': '@sample', 'name': 'Sample', 'primitive': 'cube'},
    {'op': 'object.transform', 'target': '@sample', 'location': [0,0,0], 'rotation': [0,0,0], 'scale': [1,1,1]},
    {'op': 'mesh.bevel', 'target': '@sample', 'width': .08, 'segments': 2},
    {'op': 'material.create', 'ref': '@finish', 'name': 'Blue', 'color': [.1,.2,.8,1], 'roughness': .5, 'metallic': .1},
    {'op': 'material.assign', 'target': '@sample', 'material': '@finish'},
    {'op': 'animation.keyframe', 'target': '@sample', 'frame': 1, 'rotation': [0,0,0]},
    {'op': 'animation.keyframe', 'target': '@sample', 'frame': 30, 'rotation': [0,0,1.57]},
    {'op': 'camera.configure', 'ref': '@view', 'name': 'View', 'location': [5,-7,4], 'look_at': [0,0,0], 'lens': 50},
    {'op': 'light.configure', 'ref': '@key', 'name': 'Key', 'location': [2,-4,6], 'kind': 'AREA', 'energy': 1000, 'color': [1,1,1]},
    {'op': 'scene.render', 'path': 'sample.png', 'width': 256, 'height': 256, 'samples': 16},
    {'op': 'asset.export', 'path': 'sample.fvasset'},
    {'op': 'scene.save', 'path': 'sample.blend'}]}
validate(EXAMPLE)


def plan(p, model, prompt, snapshot):
    if not isinstance(prompt, str) or not 1 <= len(prompt) <= 4096:
        raise CreationError("Prompt must contain 1–4096 characters")
    available = inventory(p)
    if model not in available:
        raise CreationError("Model is not in this provider's actual inventory")
    admit_local(p, available[model])
    fields = ('id', 'name', 'type', 'parent', 'location', 'rotation', 'scale', 'vertices', 'materials', 'description')
    visible = {'scene_id': snapshot['scene_id'], 'revision': snapshot['revision'],
               'objects': [{k: o[k] for k in fields if k in o} for o in snapshot['objects'][:32]],
               'materials': [{k: m[k] for k in ('id', 'name', 'color', 'roughness', 'metallic')}
                             for m in snapshot.get('materials', [])[:32]]}
    guide = ('The example shows every allowed operation. Change its content to the user intent. '
             'Only include requested steps. Primitive choices: cube/sphere/cylinder/plane; light kinds: AREA/POINT. '
             'All positions/rotations/scales have exactly 3 numbers; material color has 4, light color has 3. '
             'Frames 1..240; samples 1..64; image width/height 64..1024; at most 32 operations. '
             'Example: ' + canonical(EXAMPLE))
    messages = [{'role': 'system', 'content': SYSTEM + '\n' + guide},
                {'role': 'user', 'content': canonical({'intent': prompt, 'scene': visible})}]
    begin = time.monotonic()
    if p['kind'] == 'ollama':
        caps = request(p, '/api/show', {'model': model})
        # JSON mode avoids backend-specific union-schema grammar limitations.
        # The full closed schema remains in context and is enforced locally.
        payload = {'model': model, 'messages': messages, 'stream': False, 'format': 'json',
                   'options': {'temperature': 0, 'seed': 41, 'num_predict': 2304, 'num_ctx': 8192},
                   'keep_alive': '2m'}
        if False in caps.get('thinking', {}).get('values', []):
            payload['think'] = False
        response = request(p, '/api/chat', payload)
        content = response.get('message', {}).get('content', '')
        usage = {'input_tokens': response.get('prompt_eval_count'), 'output_tokens': response.get('eval_count')}
    else:
        payload = {'model': model, 'messages': messages, 'temperature': 0, 'max_tokens': 2304,
                   'response_format': {'type': 'json_schema', 'json_schema': {
                       'name': 'finalverse_creation', 'strict': True, 'schema': PLAN_SCHEMA}}}
        response = request(p, '/chat/completions', payload)
        content = response.get('choices', [{}])[0].get('message', {}).get('content', '')
        usage = response.get('usage', {})
    receipt = {'provider': p['id'], 'model': model,
        'served_model': response.get('model'), 'latency_ms': (time.monotonic()-begin)*1000,
        'input_digest': digest(messages), 'response_digest': hashlib.sha256(content.encode()).hexdigest(),
        'usage': usage, 'real_inference': True, 'fallback_used': False,
        'scene_id': snapshot['scene_id'], 'scene_revision': snapshot['revision']}
    result = None
    try:
        result = parse(content)
        validate(result)
    except (CreationError, ValueError) as error:
        return {'ok': False, 'error': 'Invalid creation plan: ' + str(error), 'receipt': receipt,
                'rejected_plan': result}
    return {'plan': result, 'receipt': receipt}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config'); parser.add_argument('input'); parser.add_argument('output')
    args = parser.parse_args()
    started = time.monotonic()
    try:
        data = parse(Path(args.input).read_text(), 4*1024*1024)
        p = registry(args.config)[data['provider']]
        if data['mode'] == 'models':
            result = {'models': models(p), 'provider': p['id']}
        elif data['mode'] == 'plan':
            result = plan(p, data['model'], data['prompt'], data['snapshot'])
        else:
            raise CreationError("Unsupported provider request")
        result = {'ok': True, **result}
    except Exception as error:
        # Never retain response bodies, credential values or remote stack traces.
        code = 'provider_timeout' if isinstance(error, TimeoutError) else 'provider_failure'
        result = {'ok': False, 'error': code, 'detail': str(error) if isinstance(error, CreationError) else type(error).__name__,
                  'fallback_used': False}
    result['total_latency_ms'] = (time.monotonic()-started)*1000
    path = Path(args.output); temporary = path.with_suffix('.tmp')
    with temporary.open('x') as f:
        f.write(canonical(result))
    os.replace(temporary, path)


if __name__ == '__main__':
    main()
