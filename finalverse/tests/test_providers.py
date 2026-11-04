# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Adapter contract tests use a mock HTTP service, never evidence of real inference."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[2]/'scripts/modules'))
from finalverse_creation.protocol import CreationError
import os
import socket
import tempfile
import urllib.error
from finalverse_creation import keychain
from finalverse_creation.providers import (MAPLE_URL, SECRET_ENV, classify, default_registry, models, plan,
                                           profile, registry, request, save)

PLAN = {'schema_version': 'finalverse.creation/v1', 'summary': 'Inspect', 'operations': [{'op': 'scene.inspect'}]}


class Handler(BaseHTTPRequestHandler):
    mode = 'valid'
    calls = []
    headers_seen = []
    required_key = None

    def log_message(self, *_): pass

    def authorized(self):
        self.headers_seen.append({k.lower(): v for k, v in self.headers.items()})
        if self.required_key is None:
            return True
        given = self.headers.get('Authorization') or ''
        if given == 'Bearer ' + self.required_key or self.headers.get('x-api-key') == self.required_key:
            return True
        body = b'{"error":"bad key SECRET-BODY-MARKER"}'
        self.send_response(401); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body); return False

    def do_GET(self):
        if not self.authorized(): return
        if self.path == '/api/tags': self.reply({'models': [{'name': 'mock-gemma', 'size': 1024}]})
        elif self.path == '/v1/models': self.reply({'data': [{'id': 'mock-gemma'}]})
        elif self.path == '/anthropic/v1/models': self.reply({'data': [{'id': 'mock-claude', 'type': 'model'}]})
        elif self.path == '/redirect':
            self.send_response(302); self.send_header('Location', '/api/tags'); self.end_headers()
        elif self.path == '/slow':
            time.sleep(3)
            try: self.reply({})
            except BrokenPipeError: pass
        else: self.send_error(404)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if not self.authorized(): return
        self.calls.append((self.path, data))
        if self.path == '/anthropic/v1/messages':
            return self.reply({'model': 'mock-claude', 'content': [{'type': 'text', 'text': json.dumps(PLAN)}],
                               'usage': {'input_tokens': 10, 'output_tokens': 5}})
        if self.path == '/api/show': self.reply({'thinking': {'values': [False, True]}})
        elif self.path in {'/api/chat', '/v1/chat/completions'}:
            content = json.dumps(PLAN) if self.mode == 'valid' else '{"operations":[{"op":"python"}]}'
            self.reply({'model': 'mock-gemma', 'message': {'content': content},
                        'choices': [{'message': {'content': content}}]})
        else: self.send_error(404)

    def reply(self, value):
        body = json.dumps(value).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)


class ProviderContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def setUp(self):
        Handler.mode = 'valid'; Handler.calls = []; Handler.headers_seen = []; Handler.required_key = None
        os.environ.pop(SECRET_ENV, None)
        self.p = {'id': 'test', 'label': 'Test', 'preset': 'custom', 'kind': 'ollama', 'enabled': True,
                  'credential': None, 'model': None, 'timeout_seconds': 2,
                  'base_url': f'http://127.0.0.1:{self.server.server_port}'}
        self.snapshot = {'scene_id': 'scene', 'revision': 'a'*64, 'objects': [], 'materials': []}

    def test_ollama_inventory_schema_and_supported_thinking(self):
        self.assertEqual(models(self.p), ['mock-gemma'])
        result = plan(self.p, 'mock-gemma', 'Inspect', self.snapshot)
        self.assertEqual(result['plan'], PLAN)
        payload = Handler.calls[-1][1]
        self.assertFalse(payload['think']); self.assertFalse(payload['stream'])
        self.assertEqual(payload['format'], 'json')

    def test_openai_compatible_uses_same_closed_plan(self):
        self.p.update(kind='openai_compatible', base_url=self.p['base_url']+'/v1')
        with patch('finalverse_creation.providers.loopback', return_value=False):  # emulate a remote host
            self.assertEqual(plan(self.p, 'mock-gemma', 'Inspect', self.snapshot)['plan'], PLAN)
        self.assertEqual(Handler.calls[-1][1]['response_format']['type'], 'json_schema')

    def test_malformed_model_output_is_rejected_without_fallback(self):
        Handler.mode = 'malformed'
        result = plan(self.p, 'mock-gemma', 'Inspect', self.snapshot)
        self.assertFalse(result['ok']); self.assertNotIn('plan', result)
        self.assertFalse(result['receipt']['fallback_used'])

    def test_redirect_disabled_and_unknown_model_are_refused(self):
        with self.assertRaises(CreationError): request(self.p, '/redirect')
        with self.assertRaises(CreationError): plan(self.p, 'invented-model', 'Inspect', self.snapshot)
        self.p['enabled'] = False
        with self.assertRaises(CreationError): models(self.p)

    def test_socket_timeout_is_bounded(self):
        started = time.monotonic()
        with self.assertRaises(TimeoutError): request(self.p, '/slow')
        self.assertLess(time.monotonic()-started, 2.8)

    def test_oversize_local_weights_are_refused_before_generation(self):
        with patch('finalverse_creation.providers.os.sysconf', side_effect=lambda name: 1024 if name == 'SC_PHYS_PAGES' else 1):
            with self.assertRaises(CreationError): plan(self.p, 'mock-gemma', 'Inspect', self.snapshot)
        self.assertEqual(Handler.calls, [])

    def test_anthropic_adapter_uses_messages_api_and_same_validation(self):
        self.p.update(kind='anthropic', base_url=self.p['base_url']+'/anthropic', credential='keychain')
        Handler.required_key = 'k-test'; os.environ[SECRET_ENV] = 'k-test'
        self.assertEqual(models(self.p), ['mock-claude'])
        with patch('finalverse_creation.providers.loopback', return_value=False):  # emulate a remote host
            result = plan(self.p, 'mock-claude', 'Inspect', self.snapshot)
        self.assertEqual(result['plan'], PLAN)
        self.assertEqual(Handler.headers_seen[-1].get('anthropic-version'), '2023-06-01')
        self.assertEqual(Handler.headers_seen[-1].get('x-api-key'), 'k-test')
        self.assertNotIn('authorization', Handler.headers_seen[-1])
        self.assertEqual(result['receipt']['provider_kind'], 'anthropic')
        self.assertEqual(result['receipt']['admission']['decision'], 'admitted')

    def test_bad_credentials_are_classified_without_body(self):
        Handler.required_key = 'right'; os.environ[SECRET_ENV] = 'wrong'; self.p['credential'] = 'keychain'
        with self.assertRaises(urllib.error.HTTPError) as caught: models(self.p)
        code, detail = classify(caught.exception)
        self.assertEqual((code, detail), ('provider_auth_failed', 'HTTP 401'))
        self.assertNotIn('SECRET-BODY-MARKER', detail)

    def test_missing_keychain_credential_fails_before_network(self):
        self.p['credential'] = 'keychain'
        with self.assertRaises(CreationError) as caught: models(self.p)
        self.assertEqual(classify(caught.exception)[0], 'provider_credential_missing')
        self.assertEqual(Handler.headers_seen, [])

    def test_unreachable_hosts_are_classified(self):
        closed = socket.socket(); closed.bind(('127.0.0.1', 0)); port = closed.getsockname()[1]; closed.close()
        self.p['base_url'] = f'http://127.0.0.1:{port}'
        with self.assertRaises(urllib.error.URLError) as caught: models(self.p)
        self.assertEqual(classify(caught.exception), ('provider_unreachable', 'connection refused'))
        dns = urllib.error.URLError(socket.gaierror(8, 'nodename nor servname provided'))
        self.assertEqual(classify(dns)[0], 'provider_unreachable')
        self.assertEqual(classify(urllib.error.URLError(TimeoutError()))[0], 'provider_timeout')

    def test_same_admission_runs_for_every_provider_kind(self):
        self.p.update(kind='openai_compatible', base_url=self.p['base_url']+'/v1')
        # Loopback servers that do not report weight size are refused before generation.
        with self.assertRaises(CreationError): plan(self.p, 'mock-gemma', 'Inspect', self.snapshot)
        self.assertEqual(Handler.calls, [])


class ProviderRegistry(unittest.TestCase):
    def test_default_registry_has_local_default_and_maple_off(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'providers.json'; default_registry(path)
            providers = registry(path)
            self.assertEqual(list(providers)[0], 'local')
            self.assertTrue(providers['local']['enabled']); self.assertEqual(providers['local']['model'], 'gemma4:e4b')
            self.assertFalse(providers['maple']['enabled'])
            self.assertEqual(providers['maple']['base_url'], MAPLE_URL)
            self.assertEqual(providers['maple']['credential'], 'keychain')
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_v1_registry_migrates_without_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'providers.json'
            path.write_text(json.dumps({'schema_version': 'finalverse.providers/v1', 'providers': [
                {'id': 'local', 'kind': 'ollama', 'base_url': 'http://127.0.0.1:11434', 'token_env': None,
                 'timeout_seconds': 120, 'enabled': True}]}))
            default_registry(path)
            data = json.loads(path.read_text())
            self.assertEqual(data['schema_version'], 'finalverse.providers/v2')
            self.assertEqual([p['id'] for p in data['providers']], ['local', 'maple'])

    def test_registry_refuses_literal_secrets_and_moved_maple(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'providers.json'; default_registry(path)
            providers = list(registry(path).values())
            bad = dict(providers[1], credential='sk-live-123')
            with self.assertRaises(CreationError): save(path, [providers[0], bad])
            moved = dict(providers[1], base_url='https://elsewhere.example')
            with self.assertRaises(CreationError): save(path, [providers[0], moved])
            with self.assertRaises(CreationError): save(path, [providers[1]])  # local must remain
            self.assertNotIn('sk-live', path.read_text())


@unittest.skipUnless(keychain.available(), 'macOS Keychain only')
class KeychainStorage(unittest.TestCase):
    account = 'fvtest-unit'

    def tearDown(self):
        keychain.delete(self.account)

    def test_round_trip_update_and_delete(self):
        self.assertIsNone(keychain.read(self.account))
        keychain.store(self.account, 'first'); keychain.store(self.account, 'second')
        self.assertEqual(keychain.read(self.account), 'second')
        self.assertTrue(keychain.delete(self.account)); self.assertIsNone(keychain.read(self.account))
        with self.assertRaises(keychain.KeychainError): keychain.store(self.account, 'two\nlines')
        with self.assertRaises(keychain.KeychainError): keychain.read('../escape')
