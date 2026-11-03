# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
import json
import hashlib
from pathlib import Path
import plistlib
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).parents[2]


class ProductContract(unittest.TestCase):
    def test_native_icons_use_upstream_glyph_canvas(self):
        for name in ['blender.svg', 'blender_logo_large.svg']:
            svg = ET.parse(ROOT/'release/datafiles/icons_svg'/name).getroot()
            self.assertEqual(float(svg.attrib['width']), 1600)
            self.assertEqual(float(svg.attrib['height']), 1600)
            self.assertEqual(svg.attrib['viewBox'], '0 0 360 360')

    def test_macos_bundle_and_executable_agree(self):
        p=json.loads((ROOT/'finalverse/product.json').read_text())
        with (ROOT/'release/darwin/Blender.app/Contents/Info.plist').open('rb') as f:
            bundle=plistlib.load(f)
        self.assertEqual(bundle['CFBundleName'],p['display_name'])
        self.assertEqual(bundle['CFBundleExecutable'],p['display_name'])
        self.assertEqual(bundle['CFBundleIdentifier'],p['bundle_id'])
        self.assertIn('Blender',bundle['CFBundleGetInfoString'])
        self.assertIn('org.blenderfoundation.blender.file',str(bundle['UTExportedTypeDeclarations']))
    def test_upstream_licenses_and_original_resources_present(self):
        self.assertIn('GNU GENERAL PUBLIC LICENSE',(ROOT/'doc/license/GPL-license.txt').read_text())
        for f in ['mark.svg','splash.png','icon.png','finalverse-studio.icns']:
            self.assertTrue((ROOT/'finalverse/branding'/f).is_file())
        self.assertEqual((ROOT/'release/datafiles/splash.png').read_bytes(),(ROOT/'finalverse/branding/splash.png').read_bytes())
        origin=json.loads((ROOT/'finalverse/branding/source.json').read_text())
        reference=ROOT/'finalverse/branding'/origin['source_reference']
        self.assertEqual(hashlib.sha256(reference.read_bytes()).hexdigest(),origin['source_sha256'])


if __name__=='__main__':unittest.main()
