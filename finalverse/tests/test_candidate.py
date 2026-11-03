# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('candidate',Path(__file__).parents[1]/'validate_candidate.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class IntegrityBoundary(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        data={'asset.glb':struct.pack('<III',0x46546c67,2,20)+b'\0'*8,'source.blend':b'BLENDER-test-only'}
        for name,b in data.items():(self.root/name).write_bytes(b)
        self.doc={'schema_version':'finalverse.studio-candidate/v1','state':'candidate','published':False,
                  'assets':{n:{'sha256':hashlib.sha256(b).hexdigest(),'byte_length':len(b)} for n,b in data.items()}}
        self.write()
    def tearDown(self):self.temp.cleanup()
    def write(self): (self.root/'candidate.json').write_text(json.dumps(self.doc))
    def test_integrity_does_not_grant_geometry_or_publication(self):
        r=module.validate(self.root);self.assertTrue(r['valid']);self.assertFalse(r['publication_authorized']);self.assertFalse(r['genesis_geometry_validated'])
    def test_tampered_asset(self):
        (self.root/'asset.glb').write_bytes(b'bad')
        with self.assertRaises(ValueError):module.validate(self.root)
    def test_no_traversal_or_extra_asset(self):
        self.doc['assets']['../escape']=self.doc['assets']['source.blend'];self.write()
        with self.assertRaises(ValueError):module.validate(self.root)
    def test_no_symlink_asset(self):
        p=self.root/'source.blend';p.unlink();p.symlink_to('/etc/hosts')
        with self.assertRaises(ValueError):module.validate(self.root)
    def test_manifest_cannot_assert_publication(self):
        self.doc['published']=True;self.write()
        with self.assertRaises(ValueError):module.validate(self.root)
    def test_duplicate_json_keys(self):
        p=self.root/'candidate.json';s=p.read_text();p.write_text(s.replace('"published": false','"published": true, "published": false'))
        with self.assertRaises(ValueError):module.validate(self.root)


if __name__=='__main__':unittest.main()
