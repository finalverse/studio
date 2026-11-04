"""Acceptance-only headless native operator check, never a model/MCP tool."""
import json, os, sys, time, uuid
from pathlib import Path
import bpy
from finalverse_creation import ui
root=Path(sys.argv[sys.argv.index('--')+1]).resolve()
os.environ['FINALVERSE_STUDIO_WORKSPACE']=str(root/'workspace')
root.mkdir(parents=True,exist_ok=False)
windows=list(bpy.context.window_manager.windows)
assert windows, 'No native window context'
window=windows[0]
area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
host=ui.current(); snapshot=host.refresh()
plan={'schema_version':'finalverse.creation/v1','summary':'Native review fixture','operations':[{'op':'scene.inspect'}]}
job=host.store.submit(plan,snapshot['scene_id'],snapshot['revision'],str(uuid.uuid4()),source='test-fixture')
with bpy.context.temp_override(window=window,area=area):
    assert bpy.ops.finalverse.ai_review(job_id=job['id'])=={'FINISHED'}
    assert area.type=='TEXT_EDITOR'
    text=area.spaces.active.text
    assert json.loads(text.as_string())==plan and area.spaces.active.show_word_wrap
    text.clear(); text.write('{"edited":"inert text does not change durable proposal"}')
    area.type='VIEW_3D'
    assert host.store.get(job['id'])['plan']==plan
    assert bpy.ops.finalverse.ai_approve(job_id=job['id'])=={'FINISHED'}
    for _ in range(4): host.tick()
    assert host.store.get(job['id'])['state']=='Completed'
    assert bpy.ops.finalverse.ai_connect()=={'FINISHED'}
    process=host.inference['process']
    started=time.monotonic()
    assert bpy.ops.finalverse.ai_cancel()=={'FINISHED'}
    cancelled=time.monotonic()-started
    assert process.poll() is not None and host.inference is None
    assert bpy.ops.finalverse.ai_mcp_config()=={'FINISHED'}
    config=json.loads((host.store.root/'mcp-client.json').read_text())
    assert config['mcpServers']['finalverse-studio']['args'][-1]==str(host.store.root)
result={'passed':True,'mode':'native headless window/area context; not an interactive desktop capture',
        'source_build':bpy.app.build_hash.decode(),'window_context_count':len(windows),
        'full_plan_review_text_editor':True,'review_text_edits_cannot_mutate_proposal':True,
        'approval_operator_executes_exact_plan':True,'connection_cancel_operator':True,
        'cancel_seconds':cancelled,'mcp_config_operator':True}
(root/'result.json').write_text(json.dumps(result,indent=2))
ui.before_load(None)
print(json.dumps(result,indent=2))
