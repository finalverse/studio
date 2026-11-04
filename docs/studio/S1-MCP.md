# Studio MCP integration

Model Context Protocol (MCP) connects external clients to Studio's validated tools.
`scripts/modules/finalverse_creation/mcp_entry.py` is a stdio MCP server using the
official Python MCP SDK **1.23.3**, installed in an external host Python. The Studio
application itself needs no pip packages. Install with
`python3 -m pip install -r finalverse/requirements-mcp.txt` in your chosen external
environment. The tested SDK negotiates its supported protocol with the client;
this is not a claim of every newer MCP transport/version feature. See the official
[stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
and [tools contract](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
Stdout is protocol-only; diagnostics use stderr.

Connect Studio's Finalverse sidebar first. **Write MCP Client Configuration**
records a workspace-specific JSON example. `FINALVERSE_MCP_PYTHON` may select the
external interpreter before launching Studio; otherwise replace its `python3`
with the interpreter where the pinned SDK is installed. The server and running
Studio must point to the same trusted workspace. Source and installed entry paths
are both supported, but use the installed entry matching the tested app build.

| Tool | Capability |
| --- | --- |
| `studio_capabilities` | Read full closed creation schema and authority limits |
| `studio_inspect` | Read the persistent host scene index/revision |
| `studio_submit` | Submit a plan with scene UUID, base_revision and request UUID |
| `studio_status` | Read durable state, step/results/errors/audit events |
| `studio_cancel` | Stop pending/active work; completed edits remain |

Use the exact UUID and revision returned by inspection. Retry a submission with
the same request UUID only when its entire input is identical. The client polls
status while the artist reviews and explicitly approves in Studio. There is no
MCP approval, arbitrary script, filesystem read/write, shell or publication tool.
Approval signatures are omitted from responses. MCP cancellation of work uses
`studio_cancel`; abandoning an already returned submission does not implicitly
roll back a job. The host revalidates the scene at approval/execution.

## Codex and Claude configuration

These are supported client configurations, not a claim that another proprietary
agent was launched during acceptance. The real client test uses the official SDK.
Use absolute paths; here is the tested local environment:

```sh
codex mcp add finalverse-studio -- \
  /Users/wenyan/.pyenv/versions/3.13.6/bin/python3 \
  '/Users/wenyan/Finalverse/dev/studio-s1-20261104/install/Finalverse Studio.app/Contents/Resources/5.4/scripts/modules/finalverse_creation/mcp_entry.py' \
  --workspace '/absolute/path/to/the/connected/Studio/workspace'
```

Codex documents stdio command/arguments in its official
[MCP integration guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
Alternatively configure `[mcp_servers.finalverse-studio]` with `command` and `args`
in Codex's selected config scope. This run does not modify global client settings.

```sh
claude mcp add --transport stdio finalverse-studio -- \
  /Users/wenyan/.pyenv/versions/3.13.6/bin/python3 \
  '/Users/wenyan/Finalverse/dev/studio-s1-20261104/install/Finalverse Studio.app/Contents/Resources/5.4/scripts/modules/finalverse_creation/mcp_entry.py' \
  --workspace '/absolute/path/to/the/connected/Studio/workspace'
```

Claude documents this interface in its official
[MCP guide](https://code.claude.com/docs/en/mcp). A `.mcp.json` uses
`mcpServers.finalverse-studio.command` and `args`, matching Studio's generated
JSON. Claude CLI was not installed in the acceptance environment. No API key is
required for this local MCP transport or local Ollama inference. Client-side
permissions remain the client's own policy and cannot authorize Studio execution.

## Reproduce the real client test

Launch `finalverse/tests/creation_mcp_host.py` under the built Studio in background
mode with a fresh evidence root. It creates a native Host and a separately labeled
**trusted test artist proxy**. Run `finalverse/tests/mcp_smoke.py --root ROOT
--entry INSTALLED_ENTRY` with the SDK Python. It initializes real stdio MCP, lists
tools, inspects, submits/idempotently repeats, proves the job waits for approval,
tests an unauthorized tool, and has the separate artist proxy approve. It observes
native geometry/material/animation/export/save completion, then modifies the
existing object's UUID, checks no rebuild, and tests cancellation/malformed tools.
The artist proxy's control file is acceptance harness code only and is neither
shipped as an MCP tool nor exposed to model output. Transcript and artist receipts
make this authority separation inspectable.
