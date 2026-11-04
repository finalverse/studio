# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Embedded S1 controls. Inference and rendering are child processes, not threads."""
import json
import os
from pathlib import Path

import bpy
from bpy.app.handlers import persistent
from bpy.props import EnumProperty, PointerProperty, StringProperty
from bpy.types import Operator, PropertyGroup

from .host import Host
from .protocol import canonical
from .store import TERMINAL

_host = None
_provider_items = [('local', 'Local Ollama', 'Configured loopback provider')]
_model_items = [('unselected', 'Test connection first', '')]


def provider_items(_self, _context):
    return _provider_items


def model_items(_self, _context):
    return _model_items


class StudioSettings(PropertyGroup):
    provider: EnumProperty(name='Provider', items=provider_items)
    model: EnumProperty(name='Model', items=model_items)
    prompt: StringProperty(name='Intent', maxlen=4096, default='Create a teal beveled cube, animate a turn, add a camera and light, render a preview, export and save.')


def _root():
    # Host configuration only. A loaded .blend cannot choose a filesystem root.
    return os.environ.get('FINALVERSE_STUDIO_WORKSPACE') or str(Path(bpy.utils.user_resource('CONFIG'))/'studio-creation-s1')


def current():
    global _host, _provider_items
    if _host is None:
        _host = Host(_root())
        _provider_items = [(p['id'], p['id'] + ' · ' + p['kind'], p['base_url'])
                           for p in _host.providers.values() if p['enabled']]
        if not bpy.app.timers.is_registered(pump):
            bpy.app.timers.register(pump, first_interval=.2)
    return _host


def pump():
    global _model_items
    if _host is None:
        return None
    try:
        _host.tick()
        names = _host.model_names
        if names and [i[0] for i in _model_items] != names:
            _model_items = [(name, name, 'Discovered from the selected provider') for name in names]
            bpy.context.window_manager.finalverse_creation.model = names[0]
        for job in _host.store.jobs()[:3]:
            text_name = 'Finalverse Plan ' + job['id'][:8]
            if bpy.data.texts.get(text_name) is None:
                text = bpy.data.texts.new(text_name)
                text.write(json.dumps(job['plan'], indent=2))
    except Exception as error:
        _host.message = str(error)
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    return .2


class STUDIO_OT_connect(Operator):
    bl_idname = 'finalverse.ai_connect'
    bl_label = 'Test Connection / Discover Models'

    def execute(self, context):
        try:
            host = current(); host.infer(context.window_manager.finalverse_creation.provider, 'models')
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error)); return {'CANCELLED'}


class STUDIO_OT_plan(Operator):
    bl_idname = 'finalverse.ai_plan'
    bl_label = 'Create Plan'

    def execute(self, context):
        try:
            settings = context.window_manager.finalverse_creation
            current().infer(settings.provider, 'plan', settings.model, settings.prompt)
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error)); return {'CANCELLED'}


class STUDIO_OT_approve(Operator):
    bl_idname = 'finalverse.ai_approve'
    bl_label = 'Approve & Execute Plan'
    job_id: StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            current().approve(self.job_id); return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error)); return {'CANCELLED'}


class STUDIO_OT_review(Operator):
    bl_idname = 'finalverse.ai_review'
    bl_label = 'Review Full Plan JSON'
    job_id: StringProperty()

    def execute(self, context):
        job = current().store.get(self.job_id)
        name = 'Finalverse Plan ' + job['id'][:8]
        text = bpy.data.texts.get(name) or bpy.data.texts.new(name)
        text.clear(); text.write(json.dumps(job['plan'], indent=2))
        context.area.type = 'TEXT_EDITOR'
        context.area.spaces.active.text = text
        context.area.spaces.active.show_word_wrap = True
        self.report({'INFO'}, 'Review the stored proposal. Shift F5 returns to Studio. Text edits do not change the proposal.')
        return {'FINISHED'}


class STUDIO_OT_cancel(Operator):
    bl_idname = 'finalverse.ai_cancel'
    bl_label = 'Cancel'
    job_id: StringProperty()

    def execute(self, _context):
        current().cancel(self.job_id or None); return {'FINISHED'}


class STUDIO_OT_recover(Operator):
    bl_idname = 'finalverse.ai_recover'
    bl_label = 'Open Last Checkpoint'
    job_id: StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, _context):
        try:
            host = current(); job = host.store.get(self.job_id)
            if job['state'] not in {'Interrupted', 'Failed', 'Cancelled'}:
                raise ValueError('Only interrupted or failed work can be recovered')
            paths = sorted(host.store.directory(self.job_id).glob('checkpoint-*.blend'))
            if not paths or any(p.is_symlink() for p in paths):
                raise ValueError('No regular recovery checkpoint')
            path = paths[-1]
            host.store.update(job['id'], {job['state']}, recovered_checkpoint=path.name)
            bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False, use_scripts=False)
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error)); return {'CANCELLED'}


class STUDIO_OT_mcp_config(Operator):
    bl_idname = 'finalverse.ai_mcp_config'
    bl_label = 'Write MCP Client Configuration'

    def execute(self, _context):
        try:
            host = current()
            data = {'mcpServers': {'finalverse-studio': {
                'command': os.environ.get('FINALVERSE_MCP_PYTHON', 'python3'),
                'args': [str(Path(__file__).with_name('mcp_entry.py')), '--workspace', str(host.store.root)]}}}
            path = host.store.root/'mcp-client.json'
            path.write_text(json.dumps(data, indent=2))
            host.message = 'MCP config: ' + str(path) + ' (host Python needs mcp 1.23.3)'
            self.report({'INFO'}, str(path)); return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error)); return {'CANCELLED'}


def draw(layout, context):
    settings = context.window_manager.finalverse_creation
    box = layout.box(); box.label(text='AI Creation · S1', icon='LIGHT')
    box.prop(settings, 'provider'); box.prop(settings, 'model')
    controls = box.column(); controls.enabled = _host is None or not (_host.inference or _host.active)
    controls.operator('finalverse.ai_connect', icon='FILE_REFRESH')
    controls.prop(settings, 'prompt')
    controls.operator('finalverse.ai_plan', icon='PLAY')
    box.operator('finalverse.ai_mcp_config', icon='PLUGIN')
    if _host is None:
        box.label(text='Connect to start a local authoring session')
        return
    # The full structured plan is retained as a Blender Text datablock for review.
    box.label(text=_host.message[:75])
    if _host.inference or _host.active:
        box.operator('finalverse.ai_cancel', icon='CANCEL')
    for job in _host.store.jobs()[:3]:
        row = box.box(); row.label(text=f"{job['state']} · {job['step']}/{len(job['plan']['operations'])}")
        row.label(text=job['plan']['summary'][:70])
        for operation in job['plan']['operations'][:8]:
            row.label(text=canonical(operation)[:90])
        if len(job['plan']['operations']) > 8:
            row.label(text='Full plan: Text Editor → Finalverse Plan ' + job['id'][:8])
        row.operator('finalverse.ai_review', icon='TEXT').job_id = job['id']
        if job['state'] == 'Proposed':
            row.operator('finalverse.ai_approve', icon='CHECKMARK').job_id = job['id']
            row.operator('finalverse.ai_cancel').job_id = job['id']
        if job['state'] in {'Interrupted', 'Failed', 'Cancelled'}:
            row.operator('finalverse.ai_recover', icon='RECOVER_LAST').job_id = job['id']
        if job.get('error'):
            row.label(text=job['error'][:80], icon='ERROR')


@persistent
def before_load(_dummy):
    global _host
    if _host is not None:
        _host.close(); _host = None


def register():
    bpy.types.WindowManager.finalverse_creation = PointerProperty(type=StudioSettings)
    if before_load not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(before_load)


def unregister():
    before_load(None)
    if before_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(before_load)
    if bpy.app.timers.is_registered(pump):
        bpy.app.timers.unregister(pump)
    del bpy.types.WindowManager.finalverse_creation


classes = (StudioSettings, STUDIO_OT_connect, STUDIO_OT_plan, STUDIO_OT_approve, STUDIO_OT_review,
           STUDIO_OT_cancel, STUDIO_OT_recover, STUDIO_OT_mcp_config)
