#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""MCP stdio host adapter. No approval tool, arbitrary script or arbitrary path tool."""
import argparse
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finalverse_creation.protocol import PLAN_SCHEMA, canonical, obj, string
from finalverse_creation.store import Store


def main():
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

    parser = argparse.ArgumentParser(); parser.add_argument('--workspace', required=True)
    args = parser.parse_args(); store = Store(args.workspace)
    server = Server('finalverse-studio', version='1.0.0')
    tool_specs = [
        ('studio_capabilities', 'Read the closed creation protocol and its bounds.', obj({}), True),
        ('studio_inspect', 'Read the host scene index; proposal execution revalidates its revision.', obj({}), True),
        ('studio_submit', 'Submit a creation proposal. Human approval in Studio is required; this tool cannot approve.',
         obj({'plan': PLAN_SCHEMA, 'scene_id': string(maximum=36), 'base_revision': string(maximum=64),
              'request_id': string(maximum=36)}), False),
        ('studio_status', 'Read a proposal status, progress and audit events.', obj({'job_id': string(maximum=36)}), True),
        ('studio_cancel', 'Cancel pending or executing authoring work; applied steps remain inspectable.',
         obj({'job_id': string(maximum=36)}), False),
    ]

    @server.list_tools()
    async def tools():
        return [Tool(name=name, description=description, inputSchema=schema,
                     annotations=ToolAnnotations(readOnlyHint=read_only, destructiveHint=False,
                                                 idempotentHint=True, openWorldHint=False))
                for name, description, schema, read_only in tool_specs]

    @server.call_tool()
    async def call(name, arguments):
        try:
            if name == 'studio_capabilities':
                result = {'protocol': PLAN_SCHEMA, 'approval': 'Studio host only', 'publication_authorized': False}
            elif name == 'studio_inspect':
                result = store.snapshot() or {'state': 'host_not_connected'}
            elif name == 'studio_submit':
                result = store.submit(arguments['plan'], arguments['scene_id'], arguments['base_revision'],
                                      arguments['request_id'])
            elif name == 'studio_status':
                result = store.get(arguments['job_id'])
            elif name == 'studio_cancel':
                result = store.cancel(arguments['job_id'])
            else:
                raise ValueError('Unknown tool')
            if isinstance(result, dict) and 'approval' in result and name != 'studio_capabilities':
                result = dict(result); result.pop('approval')
            return CallToolResult(content=[TextContent(type='text', text=canonical(result))], structuredContent=result)
        except Exception as error:
            result = {'error': type(error).__name__, 'detail': str(error)}
            return CallToolResult(content=[TextContent(type='text', text=canonical(result))], isError=True)

    async def run():
        async with stdio_server() as (reader, writer):
            await server.run(reader, writer, server.create_initialization_options())
    asyncio.run(run())


if __name__ == '__main__':
    main()
