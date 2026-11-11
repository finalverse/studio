"""Acceptance-only interactive-window S2 loop check. Runs inside the real windowed
app; invokes the panel's operators from an in-app timer (not human clicks) and
captures the live framebuffer at each loop stage."""
import json, sys, time
from pathlib import Path
import bpy
from finalverse_creation import ui

root = Path(sys.argv[sys.argv.index('--')+1]).resolve()
INTENT = ('Create Lumi, the floating spirit companion: a soft, rounded, luminous pale-mint body about 1.2 m tall with '
          'a rounded crown, small side fins and large dark expressive eyes. Lumi floats and never walks. Give the body '
          'a gentle glowing material and the eyes a dark glossy material. Add an idle hover loop, a slow drift loop and '
          'a short greet expression. Frame Lumi from the front in a 384x384 preview.')
S = {'phase': 'setup', 't0': time.monotonic(), 'shots': set(), 'approved': set()}
R = {'mode': 'interactive window; operators invoked by in-app timer; not human clicks',
     'build_hash': bpy.app.build_hash.decode(), 'background': bpy.app.background, 'log': []}


def note(**kw):
    kw['t'] = round(time.monotonic()-S['t0'], 2); R['log'].append(kw); print('S2UI', kw, flush=True)


def ctx():
    w = bpy.context.window_manager.windows[0]
    return w, next(a for a in w.screen.areas if a.type == 'VIEW_3D')


def op(name, *a, **k):
    w, area = ctx()
    with bpy.context.temp_override(window=w, area=area):
        return getattr(bpy.ops.finalverse, name)(*a, **k)


def shot(name):
    w, _ = ctx()
    with bpy.context.temp_override(window=w):
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
        bpy.ops.screen.screenshot(filepath=str(root/f'{name}.png'), check_existing=False)
    note(shot=name)


def finish():
    host = ui.current(); loop = host.loop
    R['loop'] = json.loads((loop.dir/'loop.json').read_text()) if loop else None
    R['passed'] = bool(loop and loop.result and loop.result.get('outcome') == 'completed') and not R['background']
    (root/'result.json').write_text(json.dumps(R, indent=2, default=str)); bpy.ops.wm.quit_blender()


def step():
    try:
        return _step()
    except Exception as e:
        import traceback; traceback.print_exc(); R['error'] = repr(e); finish(); return None


def _step():
    w, area = ctx(); s = bpy.context.window_manager.finalverse_creation
    if S['phase'] == 'setup':
        area.spaces.active.show_region_ui = True
        next(r for r in area.regions if r.type == 'UI').active_panel_category = 'Finalverse'
        op('ai_connect'); S['phase'] = 'models'; return .5
    host = ui.current()
    if S['phase'] == 'models':
        if host.inference: return .3
        s.model = 'gemma4:e4b'; s.prompt = INTENT; s.archetype = 'floating_spirit'; s.asset_name = 'Lumi'; s.revisions = 3
        shot('u01-loop-configured')
        assert op('ai_loop_start') == {'FINISHED'}; S['phase'] = 'loop'; return 1
    loop = host.loop
    if loop.finished:
        if 'final' not in S['shots']:
            S['shots'].add('final'); shot('u09-loop-' + loop.stage); return 1
        finish(); return None
    stage = loop.stage
    if stage in ('proposed', 'export_proposed') and loop.job not in S['approved']:
        job = host.store.get(loop.job)
        if job['state'] == 'Proposed':
            shot(f"u{len(S['approved'])+2:02d}-{stage}")
            S['approved'].add(loop.job)
            result = op('ai_approve', 'EXEC_DEFAULT', job_id=loop.job); note(approve=loop.job, result=sorted(result))
            return 1
    last = next((e for e in reversed(loop.ledger) if e['stage'] == 'evaluate'), None)
    if last and ('eval-' + last['digest']) not in S['shots']:
        S['shots'].add('eval-' + last['digest']); shot(f"u{len(S['shots'])+3:02d}-evaluate-{'pass' if last['passed'] else 'fail'}")
    if time.monotonic()-S['t0'] > 1500:
        R['error'] = 'ui check wall limit'; finish(); return None
    return .5


bpy.app.timers.register(step, first_interval=3)
