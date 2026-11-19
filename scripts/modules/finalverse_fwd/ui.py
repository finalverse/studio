# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Optional Blender sidebar extension; never publishes or mutates live worlds."""
import bpy
from bpy.props import StringProperty, EnumProperty
from .exchange import PALETTES, roundtrip


class FINALVERSE_OT_fwd_candidate(bpy.types.Operator):
    bl_idname = 'finalverse.fwd_candidate'
    bl_label = 'Build FWD Candidate'
    bl_description = 'Validate an FWD, refine materials in a new scene and export an offline candidate'

    def execute(self, context):
        scene = context.scene
        try:
            result = roundtrip(scene.fv_fwd_definition, scene.fv_fwd_cas,
                               scene.fv_fwd_output, scene.fv_fwd_validator,
                               scene.fv_fwd_asset or None, scene.fv_fwd_palette,
                               cycles_binary=scene.fv_fwd_cycles or None)
            self.report({'INFO'}, 'Validated offline candidate: '+result['output_asset_sha256'][:12])
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class FINALVERSE_PT_fwd(bpy.types.Panel):
    bl_label = 'Finalverse Geographic Exchange'
    bl_idname = 'FINALVERSE_PT_fwd'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Finalverse'

    def draw(self, context):
        layout = self.layout
        layout.label(text='Canonical FWD 0.1 · GLB · Cycles', icon='WORLD_DATA')
        for name in ('fv_fwd_definition', 'fv_fwd_cas', 'fv_fwd_output',
                     'fv_fwd_validator', 'fv_fwd_cycles', 'fv_fwd_asset', 'fv_fwd_palette'):
            layout.prop(context.scene, name)
        layout.label(text='Material refinement preserves geography.')
        layout.operator('finalverse.fwd_candidate', icon='EXPORT')
        layout.label(text='Offline candidate; publication requires review.', icon='LOCKED')


classes = (FINALVERSE_OT_fwd_candidate, FINALVERSE_PT_fwd)
PROPERTIES = ('fv_fwd_definition', 'fv_fwd_cas', 'fv_fwd_output',
              'fv_fwd_validator', 'fv_fwd_cycles', 'fv_fwd_asset', 'fv_fwd_palette')


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    fields = [('fv_fwd_definition', 'FWD Definition', 'FILE_PATH'),
              ('fv_fwd_cas', 'Source CAS', 'DIR_PATH'),
              ('fv_fwd_output', 'New Output Directory', 'DIR_PATH'),
              ('fv_fwd_validator', 'Core FWD Validator', 'FILE_PATH'),
              ('fv_fwd_cycles', 'Cycles Backend (optional)', 'FILE_PATH'),
              ('fv_fwd_asset', 'Asset ID (if multiple)', 'NONE')]
    for name, label, subtype in fields:
        setattr(bpy.types.Scene, name, StringProperty(name=label, subtype=subtype))
    bpy.types.Scene.fv_fwd_palette = EnumProperty(name='Generated Material',
        items=[(key, key.replace('_', ' ').title(), 'Explicitly generated material') for key in sorted(PALETTES)])


def unregister():
    for name in PROPERTIES:
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
