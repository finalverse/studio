# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Supported Studio extension for canonical Finalverse World Definition files.

No world publication or authoritative mutation is provided by this package.
"""
SCHEMA = 'finalverse.world-definition/0.1'
VERSION = '0.1.0'

bl_info = {'name': 'Finalverse Geographic Exchange', 'author': 'Finalverse Authors',
           'version': (0, 1, 0), 'blender': (4, 2, 0), 'location': 'View3D > Sidebar > Finalverse',
           'description': 'Canonical FWD and GLB offline geographic asset round-trip',
           'category': 'Import-Export'}


def register():
    from . import ui
    ui.register()


def unregister():
    from . import ui
    ui.unregister()
