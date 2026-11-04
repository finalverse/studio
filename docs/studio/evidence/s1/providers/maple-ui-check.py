"""Acceptance-only: Maple on → key in Keychain → connect → captured error, then cleanup."""
import json, secrets, sys, time
from pathlib import Path
import bpy
from finalverse_creation import keychain, ui
root = Path(sys.argv[sys.argv.index('--')+1]).resolve(); had = keychain.exists('maple'); S = {'p': 0}; R = {}
def ctx():
    w = bpy.context.window_manager.windows[0]; return w, next(a for a in w.screen.areas if a.type == 'VIEW_3D')
def shot(n):
    w, _ = ctx()
    with bpy.context.temp_override(window=w):
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
        bpy.ops.screen.screenshot(filepath=str(root/n), check_existing=False)
def step():
    w, a = ctx(); s = bpy.context.window_manager.finalverse_creation; h = ui.current()
    if S['p'] == 0:
        a.spaces.active.show_region_ui = True
        next(r for r in a.regions if r.type == 'UI').active_panel_category = 'Finalverse'
        s.provider = 'maple'
        with bpy.context.temp_override(window=w, area=a):
            bpy.ops.finalverse.ai_provider_toggle('EXEC_DEFAULT')
            bpy.ops.finalverse.ai_provider_key('EXEC_DEFAULT', api_key='fv-invalid-' + secrets.token_hex(12))
            bpy.ops.finalverse.ai_connect()
        S['p'] = 1; return .3
    if S['p'] == 1:
        if h.inference: return .3
        S['p'] = 2; return 1.5
    if S['p'] == 2:
        shot('p03-maple-unreachable-error.png'); R['message'] = h.message; R['result'] = h.model_result
        with bpy.context.temp_override(window=w, area=a):
            bpy.ops.finalverse.ai_provider_toggle('EXEC_DEFAULT')
        R['maple_enabled_after'] = h.providers['maple']['enabled']
        if not had: keychain.delete('maple')
        R['maple_key_removed'] = not keychain.exists('maple') if not had else 'preexisting kept'
        (root/'maple-result.json').write_text(json.dumps(R, indent=2)); bpy.ops.wm.quit_blender(); return None
bpy.app.timers.register(step, first_interval=3)
