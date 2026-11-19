# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent adversarial GLB admission tests, without Blender dependencies."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts/modules'))
from finalverse_fwd.glb import compare, parse
from finalverse_fwd.exchange import _new_output, _read


def encode(doc, binary):
    text = json.dumps(doc, separators=(',', ':')).encode()
    text += b' '*(-len(text) % 4)
    binary += b'\0'*(-len(binary) % 4)
    return (struct.pack('<III', 0x46546c67, 2, 28+len(text)+len(binary)) +
            struct.pack('<II', len(text), 0x4e4f534a)+text +
            struct.pack('<II', len(binary), 0x004e4942)+binary)


def triangle():
    binary = struct.pack('<9f3H', 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 2)
    doc = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
           'nodes': [{'mesh': 0}], 'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1}]}],
           'buffers': [{'byteLength': len(binary)}],
           'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': 36},
                           {'buffer': 0, 'byteOffset': 36, 'byteLength': 6}],
           'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3'},
                         {'bufferView': 1, 'componentType': 5123, 'count': 3, 'type': 'SCALAR'}]}
    return doc, binary


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.doc, self.binary = triangle()

    def test_valid_geometry(self):
        before = parse(encode(self.doc, self.binary))
        self.assertEqual(before['summary']['triangles'], 1)
        self.assertEqual(compare(before, before)['maximum_corner_error_gltf_units'], 0)

    def test_translation_detected(self):
        before = parse(encode(self.doc, self.binary))
        self.doc['nodes'][0]['translation'] = [1, 0, 0]
        with self.assertRaisesRegex(ValueError, 'drift'):
            compare(before, parse(encode(self.doc, self.binary)))

    def test_external_buffer_refused(self):
        self.doc['buffers'][0]['uri'] = 'https://example.invalid/private'
        with self.assertRaisesRegex(ValueError, 'embedded'):
            parse(encode(self.doc, self.binary))

    def test_external_image_refused(self):
        self.doc['images'] = [{'uri': 'file:///etc/passwd'}]
        with self.assertRaisesRegex(ValueError, 'URIs'):
            parse(encode(self.doc, self.binary))

    def test_extension_refused(self):
        self.doc['extensionsRequired'] = ['KHR_draco_mesh_compression']
        with self.assertRaisesRegex(ValueError, 'extension-free'):
            parse(encode(self.doc, self.binary))

    def test_cycle_refused(self):
        self.doc['nodes'][0]['children'] = [0]
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            parse(encode(self.doc, self.binary))

    def test_instance_budget(self):
        self.doc['nodes'] *= 1025
        with self.assertRaisesRegex(ValueError, 'budget'):
            parse(encode(self.doc, self.binary))

    def test_unrelated_scene_refused(self):
        self.doc['scenes'].append({'nodes': []})
        with self.assertRaisesRegex(ValueError, 'Exactly one GLB scene'):
            parse(encode(self.doc, self.binary))

    def test_orphan_geometry_refused(self):
        self.doc['nodes'].append({'mesh': 0})
        with self.assertRaisesRegex(ValueError, 'Orphaned'):
            parse(encode(self.doc, self.binary))

    def test_non_finite(self):
        bad = bytearray(self.binary)
        struct.pack_into('<f', bad, 0, float('nan'))
        with self.assertRaisesRegex(ValueError, 'Non-finite'):
            parse(encode(self.doc, bytes(bad)))

    def test_out_of_bounds_accessor(self):
        self.doc['accessors'][0]['count'] = 4
        with self.assertRaisesRegex(ValueError, 'escapes'):
            parse(encode(self.doc, self.binary))

    def test_invalid_index(self):
        bad = bytearray(self.binary)
        struct.pack_into('<H', bad, 36, 200)
        with self.assertRaisesRegex(ValueError, 'indices'):
            parse(encode(self.doc, bytes(bad)))

    def test_malformed_header(self):
        with self.assertRaisesRegex(ValueError, 'header'):
            parse(encode(self.doc, self.binary)+b'\0')

    def test_material_change_has_no_geometry_effect(self):
        before = parse(encode(self.doc, self.binary))
        self.doc['materials'] = [{'pbrMetallicRoughness': {'baseColorFactor': [0.4, 0.1, 0.1, 1]}}]
        self.doc['meshes'][0]['primitives'][0]['material'] = 0
        after = parse(encode(self.doc, self.binary))
        self.assertNotEqual(before['summary']['sha256'], after['summary']['sha256'])
        self.assertEqual(compare(before, after)['maximum_corner_error_gltf_units'], 0)

    def test_source_and_output_symlinks_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root/'actual').write_bytes(b'abc')
            (root/'link').symlink_to(root/'actual')
            with self.assertRaisesRegex(ValueError, 'symbolic'):
                _read(root/'link', 20)
            (root/'dir').mkdir()
            (root/'dirlink').symlink_to(root/'dir', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symbolic'):
                _new_output(root/'dirlink'/'new')

    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root/'existing').mkdir()
            (root/'existing'/'data').write_bytes(b'preserve')
            with self.assertRaises(FileExistsError):
                _new_output(root/'existing')
            self.assertEqual((root/'existing'/'data').read_bytes(), b'preserve')


if __name__ == '__main__':
    unittest.main()
