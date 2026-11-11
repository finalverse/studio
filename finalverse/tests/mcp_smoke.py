# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Real MCP SDK stdio client; local native test artist separately approves."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(root, entry):
    parameters = StdioServerParameters(command=sys.executable, args=[str(entry), '--workspace', str(root/'workspace')])
    transcript = []
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            assert names == ['studio_capabilities', 'studio_inspect', 'studio_submit', 'studio_status', 'studio_cancel']

            async def call(name, arguments=None, error=False):
                result = await session.call_tool(name, arguments or {})
                try: data = result.structuredContent or json.loads(result.content[0].text)
                except json.JSONDecodeError: data = {'sdk_validation_error': result.content[0].text}
                transcript.append({'tool': name, 'arguments': arguments, 'is_error': bool(result.isError), 'result': data})
                assert bool(result.isError) == error, data
                return data

            caps = await call('studio_capabilities'); assert not caps['publication_authorized']
            scene = await call('studio_inspect'); assert not scene['objects']
            plan = {'schema_version': 'finalverse.creation/v1', 'summary': 'MCP SDK fixture: create, material, animate, export, save',
                    'operations': [
                        {'op': 'object.create', 'ref': '@cube', 'name': 'MCP Beacon', 'primitive': 'cube'},
                        {'op': 'mesh.bevel', 'target': '@cube', 'width': .1, 'segments': 2},
                        {'op': 'material.create', 'ref': '@blue', 'name': 'MCP Blue', 'color': [.04,.2,.7,1], 'roughness': .4, 'metallic': .1},
                        {'op': 'material.assign', 'target': '@cube', 'material': '@blue'},
                        {'op': 'animation.keyframe', 'target': '@cube', 'frame': 1, 'location': [0,0,0]},
                        {'op': 'animation.keyframe', 'target': '@cube', 'frame': 24, 'location': [0,0,1]},
                        {'op': 'asset.export', 'path': 'mcp.fvasset'},
                        {'op': 'scene.save', 'path': 'mcp.blend'}]}
            arguments = {'plan': plan, 'scene_id': scene['scene_id'], 'base_revision': scene['revision'], 'request_id': str(uuid.uuid4())}
            job = await call('studio_submit', arguments)
            duplicate = await call('studio_submit', arguments); assert duplicate['id'] == job['id']
            await asyncio.sleep(.5)
            status = await call('studio_status', {'job_id': job['id']}); assert status['state'] == 'Proposed'
            assert not (await call('studio_inspect'))['objects']
            await call('studio_approve', {'job_id': job['id']}, error=True)
            (root/'artist-approval.json').write_text(json.dumps({'job_id': job['id']}))
            deadline = time.monotonic()+90
            while time.monotonic() < deadline:
                status = await call('studio_status', {'job_id': job['id']})
                if status['state'] in {'Completed', 'Failed'}: break
                await asyncio.sleep(.2)
            assert status['state'] == 'Completed', status
            scene = await call('studio_inspect'); oid = scene['objects'][0]['id']
            modify = {'schema_version': 'finalverse.creation/v1', 'summary': 'Modify existing UUID without rebuilding',
                      'operations': [{'op': 'object.transform', 'target': oid, 'scale': [1.5,1,1]}]}
            request = {'plan': modify, 'scene_id': scene['scene_id'], 'base_revision': scene['revision'], 'request_id': str(uuid.uuid4())}
            job2 = await call('studio_submit', request)
            (root/'artist-approval.json').write_text(json.dumps({'job_id': job2['id']}))
            while time.monotonic() < deadline:
                status2 = await call('studio_status', {'job_id': job2['id']})
                if status2['state'] in {'Completed', 'Failed'}: break
                await asyncio.sleep(.2)
            assert status2['state'] == 'Completed', status2
            scene = await call('studio_inspect')
            assert len(scene['objects']) == 1 and scene['objects'][0]['id'] == oid
            assert scene['objects'][0]['scale'] == [1.5,1,1]
            assert json.loads(scene['objects'][0]['creation_provenance'])['job'] == job['id']
            assert json.loads(scene['objects'][0]['provenance'])['job'] == job2['id']
            request.update(scene_id=scene['scene_id'], base_revision=scene['revision'], request_id=str(uuid.uuid4()))
            cancelled = await call('studio_submit', request)
            assert (await call('studio_cancel', {'job_id': cancelled['id']}))['state'] == 'Cancelled'
            request['plan'] = {'schema_version': 'finalverse.creation/v1', 'summary': 'Unauthorized', 'operations': [{'op': 'python', 'code': 'print(1)'}]}
            await call('studio_submit', request, error=True)
    (root/'mcp-result.json').write_text(json.dumps({'passed': True, 'protocol_version': init.protocolVersion,
        'client': 'official Python MCP SDK 1.23.3', 'tools': names, 'transcript': transcript}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--root', required=True); parser.add_argument('--entry', required=True)
    args = parser.parse_args(); root = Path(args.root).resolve()
    try: asyncio.run(run(root, Path(args.entry).resolve()))
    finally: (root/'stop').touch()
