"""Acceptance-only interactive-window provider check for the S1 provider revision.
Invokes the registered Studio operators (the ones the panel buttons call) from an
in-app timer and captures the live window framebuffer. Not human clicks."""
import json, secrets, sys, time
from pathlib import Path
import bpy
from finalverse_creation import keychain, ui

root = Path(sys.argv[sys.argv.index('--')+1]).resolve()
prompt = Path(sys.argv[sys.argv.index('--')+2]).read_text()
placeholder = 'fv-invalid-' + secrets.token_hex(12)
maple_had_key = keychain.exists('maple')
R = {'mode': 'interactive window (not --background); operators invoked by in-app timer; not human clicks',
     'build_hash': bpy.app.build_hash.decode(), 'background': bpy.app.background,
     'maple_key_preexisting': maple_had_key, 'checks': {}}
S = {'phase': 'start', 't0': time.monotonic()}
log = []


def note(**kw):
    kw['t'] = round(time.monotonic()-S['t0'], 2); log.append(kw); print('PROVIDER', kw, flush=True)


def ctx():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    return win, area


def op(name, *args, **kw):
    win, area = ctx()
    with bpy.context.temp_override(window=win, area=area):
        try:
            result = getattr(bpy.ops.finalverse, name)(*args, **kw)
        except RuntimeError as error:  # operator self.report ERROR surfaces as RuntimeError
            note(op=name, refused=str(error).strip()[:200]); return 'REFUSED', str(error)
    note(op=name, result=sorted(result)); return sorted(result)[0], ''


def shot(name):
    win, _ = ctx()
    with bpy.context.temp_override(window=win):
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        bpy.ops.screen.screenshot(filepath=str(root/f'{name}.png'), check_existing=False)
    note(screenshot=name)


def check(name, value):
    R['checks'][name] = bool(value); note(check=name, value=bool(value))


def settings():
    return bpy.context.window_manager.finalverse_creation


def finish():
    try:
        host = ui.current()
        for pid in [p for p in host.providers if p.startswith('custom-')]:
            settings().provider = pid; op('ai_provider_remove', 'EXEC_DEFAULT')
        if not maple_had_key:
            keychain.delete('maple')
        files = [p for p in (root/'workspace').rglob('*') if p.is_file()]
        leaks = [str(p.relative_to(root)) for p in files if placeholder.encode() in p.read_bytes()]
        R['placeholder_found_in_workspace_files'] = leaks
        check('no_secret_in_workspace_files', not leaks)
        check('custom_keychain_items_removed', not keychain.exists('custom-1') and not keychain.exists('custom-2'))
        R['providers_json_after'] = json.loads((host.store.root/'providers.json').read_text())
    finally:
        R['passed'] = all(R['checks'].values()) and not R['background']
        R['log'] = log
        (root/'result.json').write_text(json.dumps(R, indent=2))
        bpy.ops.wm.quit_blender()


def wait_inference(next_phase, interval=.3):
    if ui.current().inference:
        return interval
    S['phase'] = next_phase; return .5


def step():
    try:
        return _step()
    except Exception as error:
        import traceback; traceback.print_exc(); R['error'] = repr(error); finish(); return None


def _step():
    win, area = ctx(); phase = S['phase']
    if phase == 'start':
        area.spaces.active.show_region_ui = True
        region = next(r for r in area.regions if r.type == 'UI')
        try: region.active_panel_category = 'Finalverse'
        except Exception: pass
        host = ui.current()
        p = host.providers
        check('local_is_default_selection', settings().provider == 'local')
        check('local_default_model_gemma', p['local']['model'] == 'gemma4:e4b' and p['local']['enabled'])
        check('maple_listed_off_by_default', 'maple' in p and not p['maple']['enabled']
              and p['maple']['base_url'] == 'https://studio.finalverse.com')
        settings().provider = 'maple'; S['phase'] = 'maple_off'; return .8
    if phase == 'maple_off':
        shot('p01-maple-listed-off')
        status, message = op('ai_connect')
        check('maple_off_refuses_connect_without_network', status == 'REFUSED' and 'off' in message
              and ui.current().inference is None)
        op('ai_provider_toggle', 'EXEC_DEFAULT')
        check('maple_switched_on_in_studio', ui.current().providers['maple']['enabled'])
        if not maple_had_key:
            status, message = op('ai_connect')
            check('maple_without_key_refused', status == 'REFUSED' and 'Keychain' in message)
        status, _ = op('ai_provider_key', 'EXEC_DEFAULT', api_key=placeholder)
        check('maple_key_stored_in_keychain_from_studio', status == 'FINISHED' and keychain.read('maple') == placeholder
              and ui.current().key_status.get('maple'))
        S['phase'] = 'maple_on'; return .8
    if phase == 'maple_on':
        shot('p02-maple-on-key-in-keychain')
        S['started'] = time.monotonic(); op('ai_connect'); S['phase'] = 'maple_wait'; return .3
    if phase == 'maple_wait':
        if ui.current().inference: return .3
        host = ui.current(); res = host.model_result or {}
        R['maple_connect'] = {'error': res.get('error'), 'detail': res.get('detail'),
                              'seconds': round(time.monotonic()-S['started'], 3), 'message': host.message}
        check('maple_unreachable_reported_no_fallback', res.get('error') == 'provider_unreachable'
              and res.get('fallback_used') is False and not host.store.jobs())
        S['phase'] = 'maple_err_shot'; return .8
    if phase == 'maple_err_shot':
        shot('p03-maple-unreachable-error')
        op('ai_provider_toggle', 'EXEC_DEFAULT')
        check('maple_switched_back_off', not ui.current().providers['maple']['enabled'])
        status, _ = op('ai_provider_custom', 'EXEC_DEFAULT', label='Custom local Ollama', kind='ollama',
                       base_url='http://127.0.0.1:11434', model='gemma4:e4b', timeout=120)
        host = ui.current()
        check('custom_provider_added_and_selected', status == 'FINISHED' and settings().provider == 'custom-1'
              and host.providers['custom-1']['credential'] is None)
        S['phase'] = 'custom_connect'; return .8
    if phase == 'custom_connect':
        op('ai_connect'); S['phase'] = 'custom_models'; return .3
    if phase == 'custom_models':
        if ui.current().inference: return .3
        host = ui.current()
        check('custom_inventory_real', 'gemma4:e4b' in host.model_names)
        settings().model = 'gemma4:e4b'; settings().prompt = prompt
        S['started'] = time.monotonic(); op('ai_plan'); S['phase'] = 'custom_plan'; return .5
    if phase == 'custom_plan':
        if ui.current().inference: return .5
        host = ui.current(); jobs = host.store.jobs()
        R['custom_plan_seconds'] = round(time.monotonic()-S['started'], 2)
        R['custom_plan_message'] = host.message
        if not jobs or jobs[0]['state'] != 'Proposed':
            check('custom_plan_proposed', False); S['phase'] = 'anthropic'; return .5
        job = jobs[0]; S['job'] = job['id']
        receipt = job.get('model_receipt') or (host.model_result or {}).get('receipt')
        R['custom_receipt'] = receipt
        check('custom_plan_proposed_same_store', job['source'] == 'model' if 'source' in job else True)
        check('custom_receipt_names_provider_and_admission', receipt and receipt['provider'] == 'custom-1'
              and receipt['admission']['decision'] == 'admitted' and receipt['fallback_used'] is False)
        S['phase'] = 'custom_proposed_shot'; return .8
    if phase == 'custom_proposed_shot':
        shot('p04-custom-provider-proposal')
        op('ai_approve', 'EXEC_DEFAULT', job_id=S['job']); S['phase'] = 'custom_apply'; S['started'] = time.monotonic(); return .2
    if phase == 'custom_apply':
        job = ui.current().store.get(S['job'])
        if job['state'] in {'Approved', 'Applying', 'Rendering'} and time.monotonic()-S['started'] < 120: return .3
        R['custom_job'] = {'state': job['state'], 'step': job['step'], 'operations': len(job['plan']['operations']),
                           'error': job.get('error'), 'seconds': round(time.monotonic()-S['started'], 2)}
        check('custom_plan_approved_and_completed', job['state'] == 'Completed')
        S['phase'] = 'anthropic'; return .8
    if phase == 'anthropic':
        shot('p05-custom-provider-completed')
        status, _ = op('ai_provider_custom', 'EXEC_DEFAULT', label='Anthropic (invalid key test)', kind='anthropic',
                       base_url='https://api.anthropic.com', model='', timeout=20, api_key=placeholder)
        host = ui.current()
        check('remote_custom_requires_keychain', status == 'FINISHED' and host.providers['custom-2']['credential'] == 'keychain'
              and keychain.read('custom-2') == placeholder)
        S['started'] = time.monotonic(); op('ai_connect'); S['phase'] = 'anthropic_wait'; return .3
    if phase == 'anthropic_wait':
        if ui.current().inference: return .3
        host = ui.current(); res = host.model_result or {}
        R['anthropic_connect'] = {'error': res.get('error'), 'detail': res.get('detail'),
                                  'seconds': round(time.monotonic()-S['started'], 3), 'message': host.message}
        check('bad_credentials_reported', res.get('error') == 'provider_auth_failed')
        S['phase'] = 'anthropic_shot'; return .8
    if phase == 'anthropic_shot':
        shot('p06-bad-credentials-error')
        status, _ = op('ai_provider_custom', 'EXEC_DEFAULT', label='Remote without key', kind='openai_compatible',
                       base_url='https://example.invalid/v1', model='', timeout=10)
        check('remote_without_key_refused', status == 'REFUSED' and 'custom-3' not in ui.current().providers)
        settings().provider = 'local'; S['phase'] = 'qwen'; return .5
    if phase == 'qwen':
        op('ai_connect'); S['phase'] = 'qwen_models'; return .3
    if phase == 'qwen_models':
        if ui.current().inference: return .3
        settings().model = 'qwen3:30b-a3b'; settings().prompt = 'Inspect the scene.'
        op('ai_plan'); S['phase'] = 'qwen_wait'; return .3
    if phase == 'qwen_wait':
        if ui.current().inference: return .3
        res = ui.current().model_result or {}
        R['qwen_admission'] = {'error': res.get('error'), 'message': ui.current().message}
        check('oversize_model_refused_by_admission', res.get('error') == 'provider_admission_refused')
        finish(); return None


bpy.app.timers.register(step, first_interval=3.0)
