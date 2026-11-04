# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Live provider connectivity acceptance. Not an offline unit test.

Runs the real isolated helper (provider_entry.py) with Studio's bundled Python,
the same clean environment the host uses and Keychain-held secrets. Every case
records its measured latency and the helper's classified outcome. Test secrets
are deliberately invalid placeholders generated here; they are removed from the
Keychain afterwards and are checked never to appear in any written file."""
import argparse
import json
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).parents[2]/'scripts/modules'))
from finalverse_creation import keychain
from finalverse_creation.providers import SECRET_ENV, default_registry, load, save

ENTRY = Path(__file__).parents[2]/'scripts/modules/finalverse_creation/provider_entry.py'
SNAPSHOT = {'scene_id': '00000000-0000-4000-8000-000000000001', 'revision': '0'*64, 'objects': [], 'materials': []}


class AuthServer(BaseHTTPRequestHandler):
    """Labelled loopback stand-in for a gateway that rejects the key (401)."""
    def log_message(self, *_): pass

    def do_GET(self):
        body = b'{"error":"invalid api key"}'
        self.send_response(401); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body)


def custom(pid, kind, url, credential=None, model=None, timeout=10):
    return {'id': pid, 'label': pid, 'preset': 'custom', 'kind': kind, 'base_url': url, 'model': model,
            'credential': credential, 'timeout_seconds': timeout, 'enabled': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', required=True, help="Studio's bundled python3.13")
    parser.add_argument('--output', required=True)
    parser.add_argument('--plan-model', default='gemma4:e4b')
    args = parser.parse_args()
    out = Path(args.output).resolve(); out.mkdir(parents=True, exist_ok=False)
    config = out/'providers.json'; default_registry(config)
    server = ThreadingHTTPServer(('127.0.0.1', 0), AuthServer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    placeholder = 'fv-invalid-' + secrets.token_hex(12)
    providers = load(config)['providers']
    providers += [
        custom('custom-ollama', 'ollama', 'http://127.0.0.1:11434', model=args.plan_model, timeout=120),
        custom('custom-openai-local', 'openai_compatible', 'http://127.0.0.1:11434/v1'),
        custom('custom-refused', 'openai_compatible', 'http://127.0.0.1:9/v1', timeout=5),
        custom('custom-blackhole', 'openai_compatible', 'https://10.255.255.1/v1', 'keychain', timeout=4),
        custom('custom-anthropic', 'anthropic', 'https://api.anthropic.com', 'keychain', timeout=20),
        custom('custom-auth-mock', 'ollama', f'http://127.0.0.1:{server.server_port}', 'keychain', timeout=5)]
    save(config, providers)
    accounts = ['custom-blackhole', 'custom-anthropic', 'custom-auth-mock']
    maple_had_key = keychain.exists('maple')
    cases = []

    def run(name, pid, mode, use_key=True, model='', prompt='', enable=None):
        if enable is not None:
            data = load(config)['providers']
            for p in data:
                if p['id'] == pid: p['enabled'] = enable
            save(config, data)
        work = out/'cases'/name; work.mkdir(parents=True)
        (work/'input.json').write_text(json.dumps({'provider': pid, 'mode': mode, 'model': model,
                                                   'prompt': prompt, 'snapshot': SNAPSHOT}))
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(work), 'TMPDIR': str(work), 'PYTHONDONTWRITEBYTECODE': '1'}
        profile = next(p for p in load(config)['providers'] if p['id'] == pid)
        key = keychain.read(pid) if (use_key and profile['credential'] == 'keychain') else None
        if key is not None:
            env[SECRET_ENV] = key
        started = time.monotonic()
        with (work/'helper.log').open('w') as log:
            subprocess.run([args.python, '-I', str(ENTRY), str(config), str(work/'input.json'), str(work/'output.json')],
                           env=env, stdout=log, stderr=log, timeout=130, check=False)
        wall = (time.monotonic()-started)*1000
        result = json.loads((work/'output.json').read_text())
        summary = {'case': name, 'provider': pid, 'mode': mode, 'enabled': profile['enabled'],
                   'credential': profile['credential'], 'key_supplied': key is not None,
                   'ok': result.get('ok'), 'error': result.get('error'), 'detail': result.get('detail'),
                   'helper_wall_ms': round(wall, 1), 'helper_total_latency_ms': round(result.get('total_latency_ms', 0), 1)}
        if 'models' in result: summary['models'] = result['models'][:8]
        if 'plan' in result:
            summary['plan_operations'] = [o['op'] for o in result['plan']['operations']]
            summary['receipt'] = result['receipt']
        if result.get('ok') is False and 'receipt' in result:
            summary['receipt'] = result['receipt']
        cases.append(summary); print(json.dumps(summary), flush=True)
        return result

    try:
        for account in accounts:
            keychain.store(account, placeholder)
        run('local-default-inventory', 'local', 'models')
        run('maple-default-off', 'maple', 'models')
        run('maple-on-no-key', 'maple', 'models', use_key=False, enable=True)
        if not maple_had_key:
            keychain.store('maple', placeholder)
        run('maple-on-with-key', 'maple', 'models')
        run('maple-plan-attempt', 'maple', 'plan', model='gemma4:e4b', prompt='Inspect the scene.')
        run('maple-off-again', 'maple', 'models', enable=False)
        run('custom-ollama-inventory', 'custom-ollama', 'models')
        run('custom-ollama-plan', 'custom-ollama', 'plan', model=args.plan_model, prompt=(
            'Return exactly two operations using the example flat JSON field shapes: 1 scene.inspect. '
            '2 object.create ref @marker name Provider Marker primitive sphere. Include schema_version and summary. '
            'Only strict JSON.'))
        run('custom-openai-local-inventory', 'custom-openai-local', 'models')
        run('custom-openai-local-plan-admission', 'custom-openai-local', 'plan', model=args.plan_model, prompt='Inspect the scene.')
        run('unreachable-refused', 'custom-refused', 'models')
        run('unreachable-blackhole-timeout', 'custom-blackhole', 'models')
        run('bad-credential-loopback-gateway', 'custom-auth-mock', 'models')
        run('bad-credential-anthropic', 'custom-anthropic', 'models')
        run('oversize-local-model-admission', 'local', 'plan', model='qwen3:30b-a3b', prompt='Inspect the scene.')
    finally:
        for account in accounts:
            keychain.delete(account)
        if not maple_had_key:
            keychain.delete('maple')
        server.shutdown()
    leaked = [str(p.relative_to(out)) for p in out.rglob('*') if p.is_file() and placeholder in p.read_text(errors='ignore')]
    report = {'schema_version': 'finalverse.studio-provider-connectivity/v1', 'cases': cases,
              'placeholder_secret_found_in_files': leaked,
              'keychain_items_removed': all(not keychain.exists(a) for a in accounts),
              'maple_key_preexisting': maple_had_key,
              'note': 'custom-auth-mock is a labelled loopback 401 stand-in; all other endpoints are real.'}
    (out/'report.json').write_text(json.dumps(report, indent=2))
    print('LEAKS', leaked)


if __name__ == '__main__':
    main()
