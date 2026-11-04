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
from finalverse_creation.providers import models, plan, request

PLAN = {'schema_version': 'finalverse.creation/v1', 'summary': 'Inspect', 'operations': [{'op': 'scene.inspect'}]}


class Handler(BaseHTTPRequestHandler):
    mode = 'valid'
    calls = []

    def log_message(self, *_): pass

    def do_GET(self):
        if self.path == '/api/tags': self.reply({'models': [{'name': 'mock-gemma', 'size': 1024}]})
        elif self.path == '/v1/models': self.reply({'data': [{'id': 'mock-gemma'}]})
        elif self.path == '/redirect':
            self.send_response(302); self.send_header('Location', '/api/tags'); self.end_headers()
        elif self.path == '/slow':
            time.sleep(3)
            try: self.reply({})
            except BrokenPipeError: pass
        else: self.send_error(404)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append((self.path, data))
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
        Handler.mode = 'valid'; Handler.calls = []
        self.p = {'id': 'test', 'kind': 'ollama', 'enabled': True, 'token_env': None,
                  'timeout_seconds': 2, 'base_url': f'http://127.0.0.1:{self.server.server_port}'}
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
