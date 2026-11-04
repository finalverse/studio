# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Embedded S1 controls. Inference and rendering are child processes, not threads."""
import json
import os
from pathlib import Path

import bpy
from bpy.app.handlers import persistent
from bpy.props import EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, PropertyGroup

from .host import Host
from .protocol import canonical
from .store import TERMINAL

_host = None
_provider_items = [('local', 'Local Gemma (Ollama)', 'Default local provider')]
_model_items = [('unselected', 'Test connection first', '')]
KIND_ITEMS = [('ollama', 'Ollama', 'Ollama /api/tags and /api/chat'),
              ('openai_compatible', 'OpenAI-compatible', '<base>/models and <base>/chat/completions; include /v1 in the base URL'),
              ('anthropic', 'Anthropic', '<base>/v1/models and <base>/v1/messages')]


def provider_items(_self, _context):
    return _provider_items


def model_items(_self, _context):
    return _model_items


def refresh_provider_items():
    global _provider_items
    if _host is None:
        return
    # Every configured provider is listed; disabled ones are marked and cannot connect.
    _provider_items = [(p['id'], p['label'] + ('' if p['enabled'] else ' · off'),
                        f"{p['kind']} · {p['base_url']}") for p in _host.providers.values()]


def provider_changed(self, _context):
    global _model_items
    _model_items = [('unselected', 'Test connection first', '')]
    if _host is not None:
        _host.model_names = []


ARCHETYPE_ITEMS = [('floating_spirit', 'Floating spirit', 'No skeleton; hover, fly, drift (e.g. Lumi)'),
                   ('humanoid', 'Humanoid', 'Skinned 6-joint rig; walk, run, climb'),
                   ('synthetic_humanoid', 'Synthetic humanoid', 'Skinned rig; walk, run, climb'),
                   ('botanical_sprite', 'Botanical sprite', 'No skeleton; fly, hover, drift'),
                   ('nature_elemental', 'Nature elemental', 'Rooted, walk, climb'),
                   ('fire_elemental', 'Fire elemental', 'Walk, run, hover'),
                   ('environment', 'Environment', 'Buildings, vegetation, terrain'),
                   ('prop', 'Prop', 'Static or hovering object')]


class StudioSettings(PropertyGroup):
    provider: EnumProperty(name='Provider', items=provider_items, update=provider_changed)
    archetype: EnumProperty(name='Archetype', items=ARCHETYPE_ITEMS)
    asset_name: StringProperty(name='Asset', maxlen=64, default='Lumi')
    revisions: IntProperty(name='Revisions', min=0, max=3, default=2)
    model: EnumProperty(name='Model', items=model_items)
    prompt: StringProperty(name='Intent', maxlen=4096, default='Create a teal beveled cube, animate a turn, add a camera and light, render a preview, export and save.')


def _root():
    # Host configuration only. A loaded .blend cannot choose a filesystem root.
    return os.environ.get('FINALVERSE_STUDIO_WORKSPACE') or str(Path(bpy.utils.user_resource('CONFIG'))/'studio-creation-s1')


def current():
    global _host
    if _host is None:
        _host = Host(_root())
        refresh_provider_items()
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
            bpy.context.window_manager.finalverse_creation.model = names[0]  # profile default first
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


def _selected(context):
    host = current()
    pid = context.window_manager.finalverse_creation.provider
    return host, host.providers[pid]


class STUDIO_OT_provider_toggle(Operator):
    bl_idname = 'finalverse.ai_provider_toggle'
    bl_label = 'Turn Provider On/Off'
    bl_description = 'Switch the selected provider on or off. Local Gemma stays on as the default'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        try:
            host, p = _selected(context)
            host.set_enabled(p['id'], not p['enabled']); refresh_provider_items()
            self.report({'INFO'}, host.message); return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error)); return {'CANCELLED'}


class STUDIO_OT_provider_key(Operator):
    bl_idname = 'finalverse.ai_provider_key'
    bl_label = 'Set API Key (Keychain)'
    bl_description = 'Store the API key for the selected provider in the macOS Keychain'
    bl_options = {'INTERNAL'}
    api_key: StringProperty(name='API key', subtype='PASSWORD', maxlen=4096, options={'SKIP_SAVE', 'HIDDEN'})

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        p = current().providers[context.window_manager.finalverse_creation.provider]
        self.layout.label(text='Provider: ' + p['label'])
        self.layout.prop(self, 'api_key')
        self.layout.label(text='Stored only in the macOS Keychain, never in files or .blend data.', icon='LOCKED')

    def execute(self, context):
        secret, self.api_key = self.api_key, ''
        try:
            host, p = _selected(context)
            if p['credential'] != 'keychain':
                raise ValueError(p['label'] + ' does not use an API key')
            if not secret:
                raise ValueError('Enter an API key')
            host.configure_provider(p, secret)
            self.report({'INFO'}, host.message); return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error)); return {'CANCELLED'}


class STUDIO_OT_provider_forget(Operator):
    bl_idname = 'finalverse.ai_provider_forget'
    bl_label = 'Delete Stored Key'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            host, p = _selected(context); host.forget_key(p['id'])
            self.report({'INFO'}, host.message); return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error)); return {'CANCELLED'}


class STUDIO_OT_provider_custom(Operator):
    bl_idname = 'finalverse.ai_provider_custom'
    bl_label = 'Custom AI Provider'
    bl_description = 'Add or edit a custom provider: base URL, API type, model and API key'
    bl_options = {'INTERNAL'}
    edit: StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    label: StringProperty(name='Name', maxlen=64, default='Custom provider', options={'SKIP_SAVE'})
    kind: EnumProperty(name='API type', items=KIND_ITEMS, options={'SKIP_SAVE'})
    base_url: StringProperty(name='Base URL', maxlen=256, default='https://', options={'SKIP_SAVE'})
    model: StringProperty(name='Model', maxlen=200, options={'SKIP_SAVE'})
    timeout: FloatProperty(name='Timeout (s)', min=2, max=120, default=60, options={'SKIP_SAVE'})
    api_key: StringProperty(name='API key', subtype='PASSWORD', maxlen=4096, options={'SKIP_SAVE', 'HIDDEN'})

    def invoke(self, context, event):
        host = current()
        if self.edit:
            p = host.providers[self.edit]
            self.label, self.kind, self.base_url = p['label'], p['kind'], p['base_url']
            self.model, self.timeout = p['model'] or '', p['timeout_seconds']
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, _context):
        col = self.layout.column()
        for name in ('label', 'kind', 'base_url', 'model', 'timeout', 'api_key'):
            col.prop(self, name)
        col.label(text='Remote URLs must use HTTPS and an API key. Loopback servers may omit the key.', icon='INFO')
        col.label(text='The key goes to the macOS Keychain; leave it empty to keep a stored key.', icon='LOCKED')

    def execute(self, context):
        secret, self.api_key = self.api_key, ''
        try:
            from .providers import loopback
            host = current()
            if self.edit:
                pid = self.edit
            else:
                used = set(host.providers); n = 1
                while f'custom-{n}' in used: n += 1
                pid = f'custom-{n}'
            remote = not loopback(self.base_url)
            had_key = host.key_status.get(pid, False)
            value = {'id': pid, 'label': self.label.strip(), 'preset': 'custom', 'kind': self.kind,
                     'base_url': self.base_url.strip().rstrip('/'), 'model': self.model.strip() or None,
                     'credential': 'keychain' if (remote or secret or had_key) else None,
                     'timeout_seconds': float(self.timeout), 'enabled': True}
            if remote and not (secret or had_key):
                raise ValueError('A remote provider needs an API key')
            host.configure_provider(value, secret or None); refresh_provider_items()
            context.window_manager.finalverse_creation.provider = pid
            self.report({'INFO'}, host.message); return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error)); return {'CANCELLED'}


class STUDIO_OT_provider_remove(Operator):
    bl_idname = 'finalverse.ai_provider_remove'
    bl_label = 'Remove Custom Provider'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            host, p = _selected(context); host.remove_provider(p['id']); refresh_provider_items()
            context.window_manager.finalverse_creation.provider = 'local'
            self.report({'INFO'}, host.message); return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error)); return {'CANCELLED'}


class STUDIO_OT_loop_start(Operator):
    bl_idname = 'finalverse.ai_loop_start'
    bl_label = 'Start Creation Loop'
    bl_description = 'Plan → preview → evaluate → revise (bounded) → validate → export; every plan needs your approval'

    def execute(self, context):
        try:
            s = context.window_manager.finalverse_creation
            current().start_loop(provider=s.provider, model=s.model, intent=s.prompt, archetype=s.archetype,
                                 name=s.asset_name.strip() or 'Asset', max_revisions=s.revisions)
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error)); return {'CANCELLED'}


class STUDIO_OT_loop_reject(Operator):
    bl_idname = 'finalverse.ai_loop_reject'
    bl_label = 'Reject & Revise'
    bl_options = {'INTERNAL'}
    reason: StringProperty(name='Reason', maxlen=400, default='Does not match the intent')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def execute(self, _context):
        try:
            current().loop.reject(self.reason); return {'FINISHED'}
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
    box.prop(settings, 'provider')
    busy = _host is not None and bool(_host.inference or _host.active)
    if _host is not None and settings.provider in _host.providers:
        p = _host.providers[settings.provider]
        info = box.column(align=True); info.enabled = not busy
        row = info.row(align=True)
        row.label(text=('On' if p['enabled'] else 'Off') + ' · ' + p['kind'] + ' · ' + p['base_url'][:40],
                  icon='CHECKBOX_HLT' if p['enabled'] else 'CHECKBOX_DEHLT')
        if p['id'] != 'local':
            row.operator('finalverse.ai_provider_toggle', text='Turn Off' if p['enabled'] else 'Turn On')
        if p['credential'] == 'keychain':
            row = info.row(align=True)
            stored = _host.key_status.get(p['id'])
            row.label(text='Key: in Keychain' if stored else 'Key: not set', icon='LOCKED' if stored else 'UNLOCKED')
            row.operator('finalverse.ai_provider_key', text='Set Key')
            if stored:
                row.operator('finalverse.ai_provider_forget', text='', icon='TRASH')
        if p['preset'] == 'custom':
            row = info.row(align=True)
            op = row.operator('finalverse.ai_provider_custom', text='Edit', icon='PREFERENCES'); op.edit = p['id']
            row.operator('finalverse.ai_provider_remove', text='Remove', icon='X')
    add = box.row(); add.enabled = not busy
    add.operator('finalverse.ai_provider_custom', text='Add Custom AI Provider…', icon='ADD')
    box.prop(settings, 'model')
    controls = box.column(); controls.enabled = not busy
    controls.operator('finalverse.ai_connect', icon='FILE_REFRESH')
    controls.prop(settings, 'prompt')
    controls.operator('finalverse.ai_plan', icon='PLAY')
    loop_box = box.box(); loop_box.label(text='Creation loop · S2', icon='FILE_REFRESH')
    row = loop_box.row(); row.enabled = not busy; row.prop(settings, 'archetype')
    row = loop_box.row(); row.enabled = not busy; row.prop(settings, 'asset_name'); row.prop(settings, 'revisions')
    loop = _host.loop if _host is not None else None
    start = loop_box.row(); start.enabled = not busy and (loop is None or loop.finished)
    start.operator('finalverse.ai_loop_start', icon='PLAY')
    if loop is not None:
        loop_box.label(text=f"Stage: {loop.stage} · revisions {loop.revisions}/{loop.max_revisions}")
        last = next((e for e in reversed(loop.ledger) if e['stage'] == 'evaluate'), None)
        if last:
            loop_box.label(text=('Evaluation passed' if last['passed'] else 'Failed: ' + ', '.join(last['failures'])[:70]),
                           icon='CHECKMARK' if last['passed'] else 'ERROR')
        if loop.stage in ('proposed', 'export_proposed'):
            loop_box.operator('finalverse.ai_loop_reject', icon='LOOP_BACK')
        if loop.result and loop.result.get('package'):
            loop_box.label(text='Package: ' + loop.result['package'], icon='PACKAGE')
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


classes = (StudioSettings, STUDIO_OT_provider_toggle, STUDIO_OT_provider_key, STUDIO_OT_provider_forget,
           STUDIO_OT_provider_custom, STUDIO_OT_provider_remove, STUDIO_OT_loop_start, STUDIO_OT_loop_reject,
           STUDIO_OT_connect, STUDIO_OT_plan, STUDIO_OT_approve, STUDIO_OT_review,
           STUDIO_OT_cancel, STUDIO_OT_recover, STUDIO_OT_mcp_config)
