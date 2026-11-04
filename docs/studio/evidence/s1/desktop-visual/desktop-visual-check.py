"""Acceptance-only interactive-window driver. Runs inside the real windowed S1 app
(not --background), invokes the same registered operators a click would, and
captures the live window framebuffer with Blender's own screen.screenshot.
It is not a model/MCP tool and is never shipped in the product."""
import json, os, sys, time
from pathlib import Path
import bpy
from finalverse_creation import ui

root = Path(sys.argv[sys.argv.index('--')+1]).resolve()
prompt = Path(sys.argv[sys.argv.index('--')+2]).read_text()
log = []; state = {'phase': 'setup', 'n': 0, 't': time.monotonic()}
result = {'mode': 'interactive window (not --background); operators invoked by in-app timer, '
          'framebuffer captured with screen.screenshot; not human clicks',
          'build_hash': bpy.app.build_hash.decode(), 'background': bpy.app.background}


def note(**kw):
    kw['t'] = round(time.monotonic()-state['t'], 3); log.append(kw); print('VISUAL', kw, flush=True)


def ctx():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type in {'VIEW_3D', 'TEXT_EDITOR'} and a.width > 400)
    return win, area


def shot(name):
    win, _ = ctx()
    path = root/f'{name}.png'
    with bpy.context.temp_override(window=win):
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        bpy.ops.screen.screenshot(filepath=str(path), check_existing=False)
    note(screenshot=path.name, bytes=path.stat().st_size)


def step():
    try:
        return _step()
    except Exception as error:
        import traceback; traceback.print_exc()
        result['error'] = repr(error); finish(False); return None


def finish(passed):
    result['passed'] = passed; result['log'] = log
    (root/'result.json').write_text(json.dumps(result, indent=2))
    bpy.ops.wm.quit_blender()


def _step():
    win, area = ctx(); host = ui.current(); settings = bpy.context.window_manager.finalverse_creation
    phase = state['phase']
    if phase == 'setup':
        note(workspace=win.workspace.name)
        space = area.spaces.active; space.show_region_ui = True
        region = next(r for r in area.regions if r.type == 'UI')
        try: region.active_panel_category = 'Finalverse'
        except Exception as error: note(tab_select=repr(error))
        state['phase'] = 'connect'; return 1.0
    if phase == 'connect':
        with bpy.context.temp_override(window=win, area=area):
            assert bpy.ops.finalverse.ai_connect() == {'FINISHED'}
        state['phase'] = 'wait_models'; return .5
    if phase == 'wait_models':
        if host.inference: return .5
        note(models=host.model_names, message=host.message)
        assert 'gemma4:e4b' in host.model_names
        settings.model = 'gemma4:e4b'; settings.prompt = prompt
        state['plan_started'] = time.monotonic()
        with bpy.context.temp_override(window=win, area=area):
            assert bpy.ops.finalverse.ai_plan() == {'FINISHED'}
        state['phase'] = 'planning'; return .3
    if phase == 'planning':
        if state['n'] == 0:
            state['n'] = 1; shot('01-planning-responsive'); return .5
        if host.inference: return .5
        note(plan_seconds=round(time.monotonic()-state['plan_started'], 2), message=host.message,
             receipt=(host.model_result or {}).get('receipt'))
        jobs = host.store.jobs(); assert jobs and jobs[0]['state'] == 'Proposed', host.message
        state['job'] = jobs[0]['id']; result['operations'] = len(jobs[0]['plan']['operations'])
        state['phase'] = 'proposed'; return 1.0
    if phase == 'proposed':
        shot('02-proposed-panel-full-plan-control')
        with bpy.context.temp_override(window=win, area=area):
            assert bpy.ops.finalverse.ai_review(job_id=state['job']) == {'FINISHED'}
        state['phase'] = 'review'; return 1.0
    if phase == 'review':
        assert area.type == 'TEXT_EDITOR'
        text = area.spaces.active.text
        result['review_text_matches_proposal'] = json.loads(text.as_string()) == host.store.get(state['job'])['plan']
        text.current_line_index = 0; area.spaces.active.top = 0; area.tag_redraw()
        state['phase'] = 'review_shot'; return .5
    if phase == 'review_shot':
        shot('03-full-plan-review-text-editor')
        area.type = 'VIEW_3D'; state['phase'] = 'approve'; return 1.0
    if phase == 'approve':
        with bpy.context.temp_override(window=win, area=area):
            # EXEC_DEFAULT is the confirmed path after the invoke_confirm dialog.
            assert bpy.ops.finalverse.ai_approve('EXEC_DEFAULT', job_id=state['job']) == {'FINISHED'}
        state['phase'] = 'applying'; return .2
    if phase == 'applying':
        job = host.store.get(state['job'])
        if job['step'] < 4 and job['state'] in {'Approved', 'Applying'}: return .1
        shot('04-applying-before-cancel')
        step_before = job['step']; t = time.monotonic()
        with bpy.context.temp_override(window=win, area=area):
            assert bpy.ops.finalverse.ai_cancel(job_id=state['job']) == {'FINISHED'}
        result['cancel_operator_seconds'] = time.monotonic()-t
        result['step_at_cancel'] = step_before
        state['phase'] = 'cancelled'; state['wait_until'] = time.monotonic()+3; return .5
    if phase == 'cancelled':
        if time.monotonic() < state['wait_until']: return .5
        job = host.store.get(state['job'])
        result['state_after_cancel'] = job['state']; result['step_after_wait'] = job['step']
        result['no_steps_after_cancel'] = job['step'] == result['step_at_cancel']
        shot('05-cancelled-panel')
        with bpy.context.temp_override(window=win, area=area):
            assert bpy.ops.finalverse.ai_connect() == {'FINISHED'}
            proc = host.inference['process']; t = time.monotonic()
            assert bpy.ops.finalverse.ai_cancel() == {'FINISHED'}
        result['inference_cancel_seconds'] = time.monotonic()-t
        result['inference_child_stopped'] = proc.poll() is not None and host.inference is None
        state['phase'] = 'done'; return 1.0
    if phase == 'done':
        shot('06-after-inference-cancel')
        ok = (result.get('review_text_matches_proposal') and result['state_after_cancel'] == 'Cancelled'
              and result['no_steps_after_cancel'] and result['inference_child_stopped'] and not result['background'])
        finish(bool(ok)); return None


bpy.app.timers.register(step, first_interval=3.0)
