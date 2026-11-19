# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Create a deterministic Blender add-on archive from the maintained module."""
from pathlib import Path
import sys
import zipfile

root = Path(__file__).resolve().parents[1]/'scripts/modules/finalverse_fwd'
with zipfile.ZipFile(sys.argv[1], 'x', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.glob('*.py')):
        info = zipfile.ZipInfo('finalverse_fwd/'+path.name, (2026, 11, 19, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, path.read_bytes())
print(sys.argv[1])
