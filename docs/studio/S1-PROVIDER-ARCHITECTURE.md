# S1 provider architecture

Studio S1 extends accepted S0 `24d1acf06b55945bed5d247bd6e5184906bf4150`
on isolated `feat/studio-s1`. Core and Native E1, accepted worlds, resident identities
and the S0 installation are preserved. This is an authoring layer, not civilization
authority. See [acceptance](S1-ACCEPTANCE.md) for tested artifacts and exact revisions.

`scripts/modules/finalverse_creation` contains the dependency-free protocol,
durable SQLite proposal store, provider helper, Blender bridge, scheduler, UI and
MCP adapter. `bl_ui.finalverse_studio` retains S0 inspection/candidate tools and
registers S1 controls in the Finalverse sidebar of the Finalverse AI Studio workspace.

The artist selects an inventoried provider/model, enters intent and requests a
plan. A **child process** performs HTTP inference. A main-thread timer polls it;
no Python inference thread calls Blender. The response is strict JSON and is
validated before it becomes a Proposed job. Approval binds its digest, scene UUID,
revision, host session and expiry. One bounded typed operation executes per tick.
Rendering runs in a separate supervised, deny-default sandbox. Save, export and
checkpoint operations use the Blender main thread; these can briefly occupy it.
This follows upstream's [Python threading warning](../../doc/python_api/rst/info_gotchas_threading.rst).

## Providers

The trusted workspace `providers.json` has schema `finalverse.providers/v1`:

```json
{
  "schema_version": "finalverse.providers/v1",
  "providers": [{
    "id": "local", "kind": "ollama", "base_url": "http://127.0.0.1:11434",
    "token_env": null, "timeout_seconds": 120, "enabled": true
  }]
}
```

The default is local Ollama. `/api/tags` inventories real model names and sizes;
loopback Ollama requests reject missing size metadata or weights exceeding 65% of
physical memory before generation. This is an admission estimate, not a hard
memory cap on the independently running, shared Ollama daemon. Its runtime context,
GPU/CPU allocations and other users' requests are outside Studio's process limits.
`/api/show` probes capabilities. `/api/chat` uses non-streaming JSON output,
temperature 0, seed 41, context 8,192 and at most 2,304 generated tokens.
The closed schema is enforced locally; compact worked operation examples teach
the model its flat field shapes. Initial full union-schema
grammar probes produced rejected plans on the installed MLX backend; JSON mode
avoids depending on that backend's union grammar. Each retry is a new visible
inference, not an automatic repair or substituted plan.
Thinking is disabled only when the installed model explicitly supports false.
The installed Qwen build permits true only; its setting is respected. These are
generation bounds, not a guarantee of deterministic inference or valid semantics.
See official [chat API](https://docs.ollama.com/api/chat) and
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

An authenticated Maple Ollama gateway uses the same `ollama` adapter. Add a profile
such as `id=maple`, HTTPS `base_url`, and `token_env=FINALVERSE_MAPLE_TOKEN`.
Remote HTTP, embedded credentials, missing credential references and redirects
are rejected. The helper receives only that selected credential. The user selected
**local models for now**; no Maple endpoint or remote gateway was contacted.

`openai_compatible` uses `<base_url>/models` and `/chat/completions` with
`response_format.type=json_schema`. Include the endpoint's `/v1` in its configured
base URL where required. It is an interface adapter, not a claim that every server
supports the requested strict schema. Unsupported responses fail visibly. Both
adapter contracts are tested with a clearly labeled mock HTTP service; no paid
provider is claimed tested. Codex/Claude connect through [MCP](S1-MCP.md), not through
unrestricted generation of Blender scripts.

## Bounds and receipts

At most eight provider profiles, 256 inventoried model names, 4,096 intent characters,
1 MiB HTTP envelope, 64 KiB plan, 32 operations and 120 seconds per inference helper.
The parent kills a helper exceeding 122 seconds or cancelled by the artist. Proxies
and HTTP redirects are disabled. Scene context includes at most 32 object/material
summaries; UUIDs remain available through full local/MCP inspection.

Actual attempts retain input/response digests, selected/served model, token counts
when supplied, latency, outcome and fallback=false. A parsed rejected proposal may
be retained as inert JSON in its private attempt directory for diagnosis. HTTP
error bodies and credentials are never deliberately copied into receipts. Network
or model failures do not generate a substitute scene. The UI exposes status,
cancellation, proposed plans, approval, progress, errors and recent job history.
Full plans are inert Text datablocks named `Finalverse Plan <job-prefix>`; editing
one does not change the signed durable proposal.

The workspace holds SQLite WAL/FULL metadata and private versioned job outputs.
It is capped at 256 jobs and a 512 MiB admission budget, with 128 MiB reserved for
each checkpoint and 256 MiB before operations. Retention is explicit: archive a
completed workspace locally and start a new one; the app never silently deletes
artist sources, checkpoints or accepted artifacts. Render workers additionally
enforce filesystem size, wall, CPU, descriptor and aggregate RSS limits.
