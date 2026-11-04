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
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from .protocol import CreationError, PLAN_SCHEMA, canonical, digest, parse, validate


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CreationError("Provider redirects are refused")


MAPLE_URL = 'https://studio.finalverse.com'
KINDS = ('ollama', 'openai_compatible', 'anthropic')
PRESETS = ('local', 'maple', 'custom')
V2_FIELDS = {'id', 'label', 'preset', 'kind', 'base_url', 'model', 'credential', 'timeout_seconds', 'enabled'}
SECRET_ENV = 'FINALVERSE_PROVIDER_SECRET'


def loopback(base_url):
    hostname = urllib.parse.urlsplit(base_url).hostname
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return hostname == 'localhost'


def defaults():
    """Local Gemma is the default; Maple is present but off until the artist enables it."""
    return {'schema_version': 'finalverse.providers/v2', 'providers': [
        {'id': 'local', 'label': 'Local Gemma (Ollama)', 'preset': 'local', 'kind': 'ollama',
         'base_url': 'http://127.0.0.1:11434', 'model': 'gemma4:e4b', 'credential': None,
         'timeout_seconds': 120, 'enabled': True},
        {'id': 'maple', 'label': 'Maple (studio.finalverse.com)', 'preset': 'maple', 'kind': 'ollama',
         'base_url': MAPLE_URL, 'model': None, 'credential': 'keychain',
         'timeout_seconds': 60, 'enabled': False}]}


def profile(value):
    if not isinstance(value, dict) or set(value) != V2_FIELDS:
        raise CreationError("Invalid provider configuration")
    if not isinstance(value['id'], str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', value['id']):
        raise CreationError("Invalid provider ID")
    if not isinstance(value['label'], str) or not re.fullmatch(r'[^\x00-\x1f\x7f]{1,64}', value['label']):
        raise CreationError("Provider label must be 1–64 printable characters")
    if value['kind'] not in KINDS or value['preset'] not in PRESETS or type(value['enabled']) is not bool:
        raise CreationError("Unsupported provider type")
    if not isinstance(value['base_url'], str) or len(value['base_url']) > 256:
        raise CreationError("Invalid provider URL")
    url = urllib.parse.urlsplit(value['base_url'])
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise CreationError("Provider URL must not embed credentials or query parameters")
    local = loopback(value['base_url'])
    if url.scheme not in {'http', 'https'} or (not local and url.scheme != 'https'):
        raise CreationError("Remote providers require HTTPS")
    if value['credential'] not in (None, 'keychain'):
        raise CreationError("Credentials may only be referenced in the macOS Keychain")
    if not local and value['credential'] is None:
        raise CreationError("Remote providers require a Keychain credential")
    if value['model'] is not None and (not isinstance(value['model'], str) or not 0 < len(value['model']) <= 200):
        raise CreationError("Invalid default model name")
    if value['preset'] == 'local' and not local:
        raise CreationError("The local preset must use a loopback address")
    if value['preset'] == 'maple' and value['base_url'].rstrip('/') != MAPLE_URL:
        raise CreationError("The Maple preset is fixed to " + MAPLE_URL)
    if type(value['timeout_seconds']) not in (int, float) or not 2 <= value['timeout_seconds'] <= 120:
        raise CreationError("Provider timeout must be 2–120 seconds")
    return value


def migrate(data):
    """Upgrade an S1 v1 registry in memory. Environment credential references are
    replaced by Keychain references; no secret value ever lived in the file."""
    result = {'schema_version': 'finalverse.providers/v2', 'providers': []}
    for item in data['providers']:
        if not isinstance(item, dict) or set(item) != {'id', 'kind', 'base_url', 'token_env', 'timeout_seconds', 'enabled'}:
            raise CreationError("Invalid v1 provider configuration")
        local = item['id'] == 'local'
        result['providers'].append({'id': item['id'], 'label': 'Local Gemma (Ollama)' if local else item['id'],
            'preset': 'local' if local else 'custom', 'kind': item['kind'], 'base_url': item['base_url'],
            'model': 'gemma4:e4b' if local else None,
            'credential': 'keychain' if item['token_env'] else None,
            'timeout_seconds': item['timeout_seconds'], 'enabled': item['enabled']})
    ids = {p['id'] for p in result['providers']}
    for preset in defaults()['providers']:
        if preset['id'] not in ids:
            result['providers'].append(preset)
    return result


def load(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 16384:
        raise CreationError("Invalid provider registry file")
    data = parse(path.read_text())
    if set(data) != {'schema_version', 'providers'} or not isinstance(data['providers'], list):
        raise CreationError("Incorrect provider registry version")
    if data['schema_version'] == 'finalverse.providers/v1':
        data = migrate(data)
    elif data['schema_version'] != 'finalverse.providers/v2':
        raise CreationError("Incorrect provider registry version")
    return data


def registry(path):
    data = load(path)
    if not 1 <= len(data['providers']) <= 8:
        raise CreationError("Provider registry limit is eight")
    result = {}
    for item in data['providers']:
        p = profile(item)
        if p['id'] in result:
            raise CreationError("Duplicate provider ID")
        result[p['id']] = p
    if 'local' not in result:
        raise CreationError("The local default provider must remain configured")
    return result


def save(path, providers):
    """Validate the whole registry, then replace it atomically (0600, no secrets)."""
    path = Path(path)
    data = {'schema_version': 'finalverse.providers/v2', 'providers': list(providers)}
    if not 1 <= len(data['providers']) <= 8:
        raise CreationError("Provider registry limit is eight")
    seen = set()
    for item in data['providers']:
        profile(item)
        if item['id'] in seen:
            raise CreationError("Duplicate provider ID")
        seen.add(item['id'])
    if 'local' not in seen:
        raise CreationError("The local default provider must remain configured")
    text = json.dumps(data, indent=2)
    if len(text) > 16384:
        raise CreationError("Provider registry exceeds 16 KiB")
    temporary = path.with_name(path.name + '.tmp')
    temporary.unlink(missing_ok=True)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(text)
    os.replace(temporary, path)


def default_registry(path):
    path = Path(path)
    if not path.exists():
        save(path, defaults()['providers'])
    elif parse(path.read_text()).get('schema_version') == 'finalverse.providers/v1':
        save(path, migrate(parse(path.read_text()))['providers'])


def tls_context():
    """Verified TLS for remote providers.

    Studio's bundled OpenSSL has no default trust store (its compiled CA path is
    /dev/null), so the bundled certifi bundle is used, then the macOS system
    bundle. Verification and hostname checks always stay on."""
    candidates = []
    try:
        import certifi
        candidates.append(certifi.where())
    except ImportError:
        pass
    candidates.append('/etc/ssl/cert.pem')
    for path in candidates:
        if os.path.isfile(path):
            context = ssl.create_default_context(cafile=path)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            return context, path
    raise CreationError("No trusted CA bundle is available for HTTPS providers")


def request(p, route, payload=None):
    if not p['enabled']:
        raise CreationError("Provider is disabled")
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if p['credential']:
        token = os.environ.get(SECRET_ENV)
        if not token or '\n' in token or '\r' in token:
            raise CreationError("No API key is stored in the Keychain for this provider")
        if p['kind'] == 'anthropic':
            headers['x-api-key'] = token
        else:
            headers['Authorization'] = 'Bearer ' + token
    if p['kind'] == 'anthropic':
        headers['anthropic-version'] = '2023-06-01'
    req = urllib.request.Request(p['base_url'].rstrip('/') + route,
                                 canonical(payload).encode() if payload is not None else None, headers)
    handlers = [urllib.request.ProxyHandler({}), NoRedirect()]
    if p['base_url'].startswith('https:'):
        handlers.append(urllib.request.HTTPSHandler(context=tls_context()[0]))
    opener = urllib.request.build_opener(*handlers)
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
        names = [m.get('name') for m in records]
    else:
        result = request(p, '/v1/models' if p['kind'] == 'anthropic' else '/models')
        records = result.get('data', [])
        names = [m.get('id') for m in records]
    if len(names) > 256 or any(not isinstance(n, str) or not 0 < len(n) <= 200 for n in names):
        raise CreationError("Invalid model inventory")
    return dict(zip(names, records))


def models(p):
    names = sorted(inventory(p), key=lambda n: (not any(s in n.lower() for s in ['gemma', 'qwen']), n))
    if p['model'] in names:
        names.remove(p['model']); names.insert(0, p['model'])
    return names


def admit(p, record):
    """One memory admission rule for every provider, applied before generation.

    Loopback servers load weights into this Mac's memory, so they must report the
    model's size and stay within 65% of physical memory. Remote providers do not
    load weights here; the decision and its basis are recorded in the receipt."""
    physical = os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    if not loopback(p['base_url']):
        return {'decision': 'admitted', 'basis': 'remote endpoint; no model weights loaded on this Mac',
                'physical_memory_bytes': physical}
    size = record.get('size') if isinstance(record, dict) else None
    if type(size) is not int or size <= 0 or size > physical*.65:
        raise CreationError('Local model weights exceed the 65% physical-memory admission budget or have no size; choose a smaller model or configured remote provider')
    return {'decision': 'admitted', 'basis': 'local weights within 65% of physical memory',
            'weights_bytes': size, 'physical_memory_bytes': physical}


admit_local = admit  # S1 name retained for existing harnesses


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
    admission = admit(p, available[model])
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
    elif p['kind'] == 'anthropic':
        payload = {'model': model, 'system': messages[0]['content'], 'messages': messages[1:],
                   'max_tokens': 2304, 'temperature': 0}
        response = request(p, '/v1/messages', payload)
        blocks = response.get('content') or [{}]
        content = ''.join(b.get('text', '') for b in blocks if isinstance(b, dict) and b.get('type') == 'text')
        usage = response.get('usage', {})
    else:
        payload = {'model': model, 'messages': messages, 'temperature': 0, 'max_tokens': 2304,
                   'response_format': {'type': 'json_schema', 'json_schema': {
                       'name': 'finalverse_creation', 'strict': True, 'schema': PLAN_SCHEMA}}}
        response = request(p, '/chat/completions', payload)
        content = response.get('choices', [{}])[0].get('message', {}).get('content', '')
        usage = response.get('usage', {})
    receipt = {'provider': p['id'], 'provider_kind': p['kind'], 'provider_preset': p['preset'],
        'endpoint_host': urllib.parse.urlsplit(p['base_url']).hostname, 'admission': admission, 'model': model,
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


def classify(error):
    """Map a failure to a stable code and a body-free detail."""
    if isinstance(error, urllib.error.HTTPError):
        code = {401: 'provider_auth_failed', 403: 'provider_auth_failed', 404: 'provider_endpoint_not_found',
                429: 'provider_rate_limited'}.get(error.code, 'provider_http_error')
        return code, f'HTTP {error.code}'
    reason = getattr(error, 'reason', error)
    if isinstance(reason, (TimeoutError, socket.timeout)) or isinstance(error, TimeoutError):
        return 'provider_timeout', 'no response within the provider timeout'
    if isinstance(reason, socket.gaierror):
        return 'provider_unreachable', 'DNS resolution failed for the provider host'
    if isinstance(reason, ConnectionRefusedError):
        return 'provider_unreachable', 'connection refused'
    if isinstance(reason, ssl.SSLError):
        return 'provider_tls_failed', 'TLS handshake failed: ' + type(reason).__name__
    if isinstance(reason, OSError):
        return 'provider_unreachable', type(reason).__name__
    if isinstance(error, CreationError):
        text = str(error)
        if 'disabled' in text:
            return 'provider_disabled', text
        if 'Keychain' in text:
            return 'provider_credential_missing', text
        if 'admission' in text:
            return 'provider_admission_refused', text
        return 'provider_failure', text
    if isinstance(error, json.JSONDecodeError):
        return 'provider_bad_response', 'response was not JSON'
    return 'provider_failure', type(error).__name__


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
        code, detail = classify(error)
        result = {'ok': False, 'error': code, 'detail': detail, 'fallback_used': False}
    result['total_latency_ms'] = (time.monotonic()-started)*1000
    path = Path(args.output); temporary = path.with_suffix('.tmp')
    with temporary.open('x') as f:
        f.write(canonical(result))
    os.replace(temporary, path)


if __name__ == '__main__':
    main()
