# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline S2 language tests (no Blender, no model)."""
import copy
import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[2]/'scripts/modules'))
sys.path.insert(0, str(Path(__file__).parent))
from finalverse_creation import glbcheck
from finalverse_creation.protocol import CreationError, SCHEMA, validate
from finalverse_creation.providers import EXAMPLE_V2, grammar_v2, plan_messages_v2
import s2_fixtures as F


def lumi():
    return F.plan('Lumi', [*F.lumi_scene(), F.LUMI_PACKAGE])


class LanguageV2(unittest.TestCase):
    def test_fixture_plans_validate(self):
        for p in (lumi(), F.environment(), F.humanoid_rigs(), EXAMPLE_V2):
            validate(p)

    def test_v1_plans_still_validate_and_cannot_use_v2_tools(self):
        validate({'schema_version': SCHEMA, 'summary': 'x', 'operations': [{'op': 'scene.inspect'}]})
        with self.assertRaises(CreationError):
            validate({'schema_version': SCHEMA, 'summary': 'x', 'operations': [
                {'op': 'character.spirit', 'ref': '@s', 'name': 'S', 'height': 1}]})

    def test_spirit_never_gets_skeleton_legs_or_walk(self):
        p = lumi(); p['operations'].insert(2, {'op': 'armature.create', 'ref': '@r', 'name': 'R',
                                                'template': 'humanoid_basic', 'height': 1})
        with self.assertRaises(CreationError): validate(p)
        p = lumi(); p['operations'][6]['locomotion'] = 'walk'
        with self.assertRaises(CreationError): validate(p)
        p = lumi(); p['operations'][1]['name'] = 'Lumi foot'
        with self.assertRaises(CreationError): validate(p)

    def test_humanoid_may_walk_but_not_hover_unless_allowed(self):
        p = F.humanoid_rigs(); validate(p)
        p['operations'][6]['locomotion'] = 'drift'
        with self.assertRaises(CreationError): validate(p)

    def test_references_types_and_bounds(self):
        p = lumi(); p['operations'][6]['keys'].reverse()
        with self.assertRaises(CreationError): validate(p)  # frames must ascend
        p = lumi(); p['operations'][6]['loop'] = 1
        with self.assertRaises(CreationError): validate(p)  # boolean, not integer
        p = lumi(); p['operations'][-1]['clips'] = ['@glow']
        with self.assertRaises(CreationError): validate(p)  # clip must be an action
        p = lumi(); p['operations'].append(copy.deepcopy(F.LUMI_PACKAGE)); p['operations'][-1]['path'] = 'b.fvpkg'
        with self.assertRaises(CreationError): validate(p)  # one package per plan
        p = F.environment(); p['operations'][-4]['scale_min'] = 3
        with self.assertRaises(CreationError): validate(p)
        p = lumi(); p['operations'][1]['height'] = 9
        with self.assertRaises(CreationError): validate(p)

    def test_model_prompt_is_generated_from_schema_and_bounded(self):
        text = grammar_v2()
        self.assertIn('character.spirit', text); self.assertIn('geonodes.scatter', text)
        self.assertNotIn('asset.package', text)
        messages = plan_messages_v2('make Lumi', {'objects': []}, {'failed_checks': [{'id': 'x'}]})
        self.assertLess(len(messages[0]['content']), 9000)
        self.assertIn('failed_checks', messages[1]['content'])


class GLBCheck(unittest.TestCase):
    def glb(self, doc, binary=b''):
        j = json.dumps(doc).encode(); j += b' '*(-len(j) % 4); binary += b'\0'*(-len(binary) % 4)
        chunks = struct.pack('<II', len(j), 0x4E4F534A) + j
        if binary:
            chunks += struct.pack('<II', len(binary), 0x004E4942) + binary
        return struct.pack('<III', 0x46546C67, 2, 12+len(chunks)) + chunks

    def test_valid_triangle_and_rejections(self):
        pos = struct.pack('<9f', 0, 0, 0, 1, 0, 0, 0, 1, 0)
        doc = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 36}],
               'bufferViews': [{'buffer': 0, 'byteLength': 36}],
               'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3',
                              'min': [0, 0, 0], 'max': [1, 1, 0]}],
               'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}], 'nodes': [{'mesh': 0}]}
        self.assertEqual(glbcheck.check(self.glb(doc, pos))['vertices'], 3)
        bad = copy.deepcopy(doc); bad['accessors'][0]['max'] = [5, 5, 5]
        with self.assertRaises(glbcheck.GLBError): glbcheck.check(self.glb(bad, pos))
        bad = copy.deepcopy(doc); bad['accessors'][0]['count'] = 30
        with self.assertRaises(glbcheck.GLBError): glbcheck.check(self.glb(bad, pos))
        with self.assertRaises(glbcheck.GLBError): glbcheck.check(b'glTF' + b'\0'*40)
