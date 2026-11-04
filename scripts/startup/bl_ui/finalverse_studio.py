# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Studio authoring UI; model proposals share the S1 validated creation bridge."""
import hashlib
import json
import os
from pathlib import Path
import uuid

import bpy
from bpy.app.handlers import persistent
from bpy.props import StringProperty
from bpy.types import Operator, Panel
from bpy_extras.io_utils import ExportHelper
from finalverse_creation import ui as creation_ui

PRODUCT = "Finalverse Studio"
WORKSPACE = "Finalverse AI Studio"
CANDIDATE_SCHEMA = "finalverse.studio-candidate/v1"


def receipt(scene, operation, result):
    entries = json.loads(scene.get("finalverse.creation_history", "[]"))
    entries.append({"operation": operation, "result": result})
    scene["finalverse.creation_history"] = json.dumps(entries[-64:], sort_keys=True)


def inspect_scene(scene):
    seen = set()
    objects = []
    for obj in sorted(scene.objects, key=lambda o: o.name):
        identity = obj.get("finalverse.object_id")
        if not isinstance(identity, str) or identity in seen:
            identity = str(uuid.uuid4())
            obj["finalverse.object_id"] = identity
        seen.add(identity)
    for obj in sorted(scene.objects, key=lambda o: o.name):
        identity = obj["finalverse.object_id"]
        objects.append({"id": identity, "name": obj.name, "type": obj.type,
                        "parent": obj.parent.get("finalverse.object_id") if obj.parent else None,
                        "materials": [m.name for m in obj.data.materials if m] if hasattr(obj.data, "materials") else []})
    return {"schema_version": "finalverse.studio-scene/v1", "objects": objects}


def export_candidate(directory, scene):
    """New directory only; editable source and GLB are immutable candidate inputs."""
    directory = Path(directory).absolute()
    for ancestor in directory.parents:
        if ancestor.is_symlink():
            raise ValueError("Candidate path must not traverse a symbolic link")
    directory.mkdir(parents=True, exist_ok=False)
    try:
        index = inspect_scene(scene)
        bpy.ops.wm.save_as_mainfile(filepath=str(directory / "source.blend"), copy=True)
        bpy.ops.export_scene.gltf(filepath=str(directory / "asset.glb"), export_format='GLB',
                                  export_animations=True, export_extras=True)
        assets = {}
        for name, media in [("source.blend", "application/x-blender"), ("asset.glb", "model/gltf-binary")]:
            if (directory / name).stat().st_size > 128 * 1024 * 1024:
                raise ValueError("Candidate exceeds the 128 MiB per-file limit")
            data = (directory / name).read_bytes()
            assets[name] = {"sha256": hashlib.sha256(data).hexdigest(), "byte_length": len(data), "media_type": media}
        result = {"schema_version": CANDIDATE_SCHEMA, "product": PRODUCT,
                  "blender_version": bpy.app.version_string, "state": "candidate",
                  "published": False, "source_license": "user-declared; required at Genesis admission",
                  "frame": {"axes": "glTF right-handed Y-up", "unit": "metre"},
                  "assets": assets, "scene": index,
                  "publication": "Independent Genesis validation and authorization required"}
        (directory / "candidate.json").write_text(json.dumps(result, indent=2, sort_keys=True))
        receipt(scene, "export_candidate", {"path": str(directory), "assets": assets})
        return result
    except Exception as error:
        (directory / "FAILED.txt").write_text(str(error))
        raise


class FINALVERSE_OT_inspect(Operator):
    bl_idname = "finalverse.inspect_scene"
    bl_label = "Inspect Scene"
    bl_description = "Assign persistent authoring IDs and inspect scene contents"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        result = inspect_scene(context.scene)
        receipt(context.scene, "inspect", {"objects": len(result["objects"])})
        self.report({'INFO'}, f"{len(result['objects'])} objects inspected")
        return {'FINISHED'}


class FINALVERSE_OT_export(Operator, ExportHelper):
    bl_idname = "finalverse.export_candidate"
    bl_label = "Export Genesis Candidate"
    bl_description = "Export source and GLB into a new candidate directory; does not publish"
    filename_ext = ".fvasset"
    filter_glob: StringProperty(default="*.fvasset", options={'HIDDEN'})

    def execute(self, context):
        try:
            result = export_candidate(self.filepath, context.scene)
            self.report({'INFO'}, "Candidate exported; independent Genesis admission required")
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class FINALVERSE_PT_studio(Panel):
    bl_label = "Finalverse AI Studio"
    bl_idname = "FINALVERSE_PT_studio"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Finalverse'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Create. Animate. Author worlds.")
        layout.label(text="Based on Blender · S1 development", icon='INFO')
        layout.separator()
        layout.operator("finalverse.inspect_scene", icon='VIEWZOOM')
        layout.label(text=f"Scene: {len(context.scene.objects)} objects")
        layout.operator("render.render", text="Render Preview", icon='RENDER_STILL').use_viewport = True
        layout.operator("wm.save_as_mainfile", text="Save Project…", icon='FILE_TICK')
        layout.operator("finalverse.export_candidate", icon='EXPORT')
        layout.separator()
        creation_ui.draw(layout, context)
        layout.label(text="Publication: candidate export only", icon='LOCKED')
        entries = json.loads(context.scene.get("finalverse.creation_history", "[]"))
        layout.label(text=f"Creation history: {len(entries)} local receipts")
        for entry in entries[-3:]:
            layout.label(text=entry["operation"].replace('_', ' ').title())


@persistent
def _load_workspace(_dummy):
    workspace = bpy.data.workspaces.get(WORKSPACE)
    if workspace is None:
        workspace = bpy.data.workspaces.get("Layout")
        if workspace:
            workspace.name = WORKSPACE
    if workspace:
        for screen in workspace.screens:
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    area.spaces.active.show_region_ui = True
                elif area.type == 'DOPESHEET_EDITOR':
                    area.type = 'FILE_BROWSER'
                    area.ui_type = 'ASSETS'


def register_workspace():
    creation_ui.register()
    if _load_workspace not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_load_workspace)


def unregister_workspace():
    creation_ui.unregister()
    if _load_workspace in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_workspace)


classes = (FINALVERSE_OT_inspect, FINALVERSE_OT_export, FINALVERSE_PT_studio, *creation_ui.classes)
