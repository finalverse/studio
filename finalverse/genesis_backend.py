#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit human-host approval of a local Studio binary, not publication authority."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib


def descriptor(app):
    app = Path(app).resolve(strict=True)
    if app.name != 'Finalverse Studio.app':
        raise ValueError('Finalverse Studio.app bundle required')
    with (app/'Contents/Info.plist').open('rb') as stream:
        info = plistlib.load(stream)
    if info.get('CFBundleIdentifier') != 'org.finalverse.studio':
        raise ValueError('bundle identity mismatch')
    executable = app/'Contents/MacOS/Finalverse Studio'
    if executable.is_symlink() or not executable.is_file():
        raise ValueError('regular built executable required')
    with executable.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'schema_version':'finalverse.studio-backend/v1', 'app':str(app),
            'executable_sha256':digest}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('app');p.add_argument('output');a=p.parse_args()
    result=descriptor(a.app)
    with Path(a.output).open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,sort_keys=True))
