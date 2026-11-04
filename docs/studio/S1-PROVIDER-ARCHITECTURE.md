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

The trusted workspace `providers.json` has schema `finalverse.providers/v2`
(S1 v1 files are migrated in place; they never held secrets). Fresh workspaces get:

```json
{
  "schema_version": "finalverse.providers/v2",
  "providers": [
    {"id": "local", "label": "Local Gemma (Ollama)", "preset": "local", "kind": "ollama",
     "base_url": "http://127.0.0.1:11434", "model": "gemma4:e4b", "credential": null,
     "timeout_seconds": 120, "enabled": true},
    {"id": "maple", "label": "Maple (studio.finalverse.com)", "preset": "maple", "kind": "ollama",
     "base_url": "https://studio.finalverse.com", "model": null, "credential": "keychain",
     "timeout_seconds": 60, "enabled": false}
  ]
}
```

`kind` is `ollama`, `openai_compatible` or `anthropic`. `credential` is `null`
(loopback only) or `"keychain"`; the key itself is in the macOS Keychain (see
[security](S1-SECURITY.md)). At most eight profiles; `local` cannot be removed or
turned off; the Maple preset's URL is fixed to `https://studio.finalverse.com`.

### Switching providers in Studio

The Finalverse sidebar lists every profile (disabled ones are marked `· off`).
For the selected profile it shows On/Off, kind and URL, Keychain key status, and
**Turn On / Turn Off**, **Set Key**, delete-key, and for custom profiles **Edit** and
**Remove**. **Add Custom AI Provider…** asks for name, API type, base URL, model,
timeout and API key. Remote URLs must be HTTPS and need a key; loopback servers may
omit one. A disabled provider, or one whose key is missing, is refused before any
network request.

### One path for every provider

Every provider goes through the same isolated helper, the same strict JSON parse
and closed-schema validation, the same Proposed → exact-approval → bounded
execution path and the same receipts (now with `provider_kind`, `provider_preset`,
`endpoint_host` and `admission`). The same memory admission rule runs before
every generation: a loopback endpoint loads weights on this Mac, so it must report
the model's size and stay within 65% of physical memory, otherwise it is refused
(`provider_admission_refused`). A remote endpoint is admitted with the recorded
basis "no model weights loaded on this Mac". As a result, a loopback
OpenAI-compatible server that does not report sizes, such as Ollama's `/v1`, can
list models but cannot plan. Use the Ollama kind for local Ollama.

Failure codes: `provider_disabled`, `provider_credential_missing`,
`provider_unreachable` (DNS, refused, other socket errors), `provider_timeout`,
`provider_tls_failed`, `provider_auth_failed` (HTTP 401/403),
`provider_endpoint_not_found`, `provider_rate_limited`, `provider_http_error`,
`provider_bad_response`, `provider_admission_refused`, `provider_failure`.

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

Maple is configured as an authenticated Ollama-protocol gateway at
`https://studio.finalverse.com` (Bearer key from the Keychain). It ships **off**.
On 2026-11-04 `studio.finalverse.com` did not resolve (NXDOMAIN), so only its
error path was exercised: off → refused locally; on without key → refused
locally; on with key → `provider_unreachable` (DNS) in about 0.13 s, with no fallback
and no job created. If Maple turns out to serve the OpenAI-compatible protocol,
change its kind in the registry; the URL stays fixed. Remote HTTP, embedded
credentials, literal keys and redirects are rejected.

`anthropic` uses `<base_url>/v1/models` and `/v1/messages` with `x-api-key` and
`anthropic-version: 2023-06-01`, temperature 0 and 2,304 max tokens. It relies on
the prompt plus local schema validation, not a provider-side schema feature.
Fenced or non-JSON replies are rejected, not repaired.

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
