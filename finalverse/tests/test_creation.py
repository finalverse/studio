# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).parents[2]/'scripts/modules'))
from finalverse_creation.protocol import CreationError, parse, validate
from finalverse_creation.providers import profile
from finalverse_creation.store import HostAuthority, Store


def proposal():
    return {'schema_version': 'finalverse.creation/v1', 'summary': 'Create a cube', 'operations': [
        {'op': 'object.create', 'ref': '@cube', 'name': 'Cube', 'primitive': 'cube'},
        {'op': 'object.transform', 'target': '@cube', 'location': [0, 0, 1]}]}


class ProtocolTests(unittest.TestCase):
    def test_closed_language_rejects_unknown_code_and_fields(self):
        for item in [{'op': 'python', 'code': 'print(1)'}, {'op': 'object.create', 'ref': '@x',
                     'name': 'Cube', 'primitive': 'cube', 'python': 'print(1)'}]:
            p = proposal(); p['operations'] = [item]
            with self.assertRaises(CreationError): validate(p)

    def test_path_escape_and_nonfinite_bool_numbers_refused(self):
        for path in ['../x.blend', '/tmp/x.blend', 'a/b.blend', 'a\\b.blend']:
            p = proposal(); p['operations'] = [{'op': 'scene.save', 'path': path}]
            with self.assertRaises(CreationError): validate(p)
        for v in [True, float('nan'), float('inf'), 1001]:
            p = proposal(); p['operations'][1]['location'] = [v, 0, 0]
            with self.assertRaises((CreationError, ValueError)): validate(p)

    def test_duplicate_keys_and_forward_references_refused(self):
        with self.assertRaises(CreationError): parse('{"op":1,"op":2}')
        with self.assertRaises(CreationError): parse('{"value":NaN}')
        p = proposal(); p['operations'].reverse()
        with self.assertRaises(CreationError): validate(p)

    def test_repeated_outputs_and_count_bounds(self):
        p = proposal(); p['operations'] = [{'op': 'scene.save', 'path': 'x.blend'}]*2
        with self.assertRaises(CreationError): validate(p)
        p['operations'] = [{'op': 'scene.inspect'}]*33
        with self.assertRaises(CreationError): validate(p)

    def test_remote_transport_requires_https_and_auth(self):
        p = {'id': 'maple', 'kind': 'ollama', 'base_url': 'http://maple.example',
             'token_env': None, 'timeout_seconds': 30, 'enabled': True}
        with self.assertRaises(CreationError): profile(p)
        p['base_url'] = 'https://maple.example'
        with self.assertRaises(CreationError): profile(p)
        p['token_env'] = 'FINALVERSE_MAPLE_TOKEN'; profile(p)
        p['base_url'] = 'https://secret@maple.example'
        with self.assertRaises(CreationError): profile(p)


class DurableApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name).resolve()/'workspace')
        self.host = HostAuthority(self.store)
        self.snapshot = {'scene_id': str(uuid.uuid4()), 'revision': 'a'*64}

    def tearDown(self):
        self.host.close(); self.store.db.close(); self.tmp.cleanup()

    def submit(self, request_id=None):
        return self.store.submit(proposal(), self.snapshot['scene_id'], self.snapshot['revision'],
                                 request_id or str(uuid.uuid4()))

    def test_missing_approval_and_stale_scene_refused(self):
        job = self.submit()
        with self.assertRaises(CreationError): self.host.verify(job)
        stale = dict(self.snapshot, revision='b'*64)
        with self.assertRaises(CreationError): self.host.approve(job['id'], stale)
        approved = self.host.approve(job['id'], self.snapshot)
        self.host.verify(approved)

    def test_approval_cannot_be_transferred_or_plan_tampered(self):
        first, second = self.submit(), self.submit()
        approved = self.host.approve(first['id'], self.snapshot)
        second['approval'] = approved['approval']
        with self.assertRaises(CreationError): self.host.verify(second)
        approved['plan']['operations'][0]['name'] = 'Tampered'
        with self.assertRaises(CreationError): self.host.verify(approved)

    def test_duplicate_jobs_across_connections_are_idempotent(self):
        request = str(uuid.uuid4()); first = self.submit(request)
        other = Store(self.store.root)
        repeated = other.submit(proposal(), self.snapshot['scene_id'], self.snapshot['revision'], request)
        self.assertEqual(first['id'], repeated['id']); self.assertEqual(len(other.jobs()), 1)
        modified = proposal(); modified['summary'] = 'Different'
        with self.assertRaises(CreationError):
            other.submit(modified, self.snapshot['scene_id'], self.snapshot['revision'], request)
        other.db.close()

    def test_cancel_invalidates_execution_state(self):
        job = self.submit(); self.host.approve(job['id'], self.snapshot)
        self.assertEqual(self.store.cancel(job['id'])['state'], 'Cancelled')
        with self.assertRaises(CreationError): self.host.verify(self.store.get(job['id']))
        with self.assertRaises(CreationError): self.store.update(job['id'], {'Approved'}, state='Applying')

    def test_restart_never_replays_uncertain_work(self):
        job = self.submit(); self.host.approve(job['id'], self.snapshot)
        self.store.update(job['id'], {'Approved'}, state='Applying', step=1)
        old_session = self.host.session; self.host.close(); self.host = HostAuthority(self.store)
        self.assertNotEqual(old_session, self.host.session)
        after = self.store.get(job['id'])
        self.assertEqual(after['state'], 'Interrupted'); self.assertEqual(after['step'], 1)
        self.assertIsNone(after['approval'])

    def test_restart_requires_new_approval_for_unstarted_work(self):
        job = self.submit(); self.host.approve(job['id'], self.snapshot)
        self.host.close(); self.host = HostAuthority(self.store)
        self.assertEqual(self.store.get(job['id'])['state'], 'Proposed')

    def test_second_host_is_refused_and_symlink_workspace_rejected(self):
        with self.assertRaises(CreationError): HostAuthority(self.store)
        alias = Path(self.tmp.name)/'alias'; alias.symlink_to(self.store.root)
        with self.assertRaises(CreationError): Store(alias)


if __name__ == '__main__': unittest.main()
