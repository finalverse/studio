# S3-A Security

Every asset is treated as untrusted: AI-generated, imported, or hostile. S3-A parses
and analyses data; it never executes asset content.

## Threat model

| Threat | Control |
|---|---|
| Malformed containers (truncated, wrong lengths, misplaced chunks) | explicit header and chunk bounds checks before any slice; container failures abort with a critical finding |
| JSON bombs (deep nesting, huge arrays, huge documents) | `max_json_bytes`; nesting measured by a non-recursive token scan **before** `json.loads`; `RecursionError` caught; array lengths bounded after parse |
| Ambiguous JSON (duplicate keys, `NaN`, `1e400`) | detected and reported; non-finite values are never emitted raw (the whole report is sanitized before digesting) |
| Hostile numbers in data (NaN/Inf floats, huge counts, out-of-range indices) | accessors validated against their bufferViews before decoding; decoding charged against `max_decoded_components`; synthetic draw order derived only from *decoded* positions, never from a declared count |
| Type confusion (lists/objects where scalars are expected) | lookups go through a hashable-scalar guard; fuzzing found and closed every such path (see Testing) |
| Remote resources (`http(s)`, `file:`, `ftp:`, any scheme) | **never fetched**; recorded as `FVA-SEC-001`, status `refused` |
| Path escape (`..`, absolute paths, drive letters, encoded traversal, symlinks) | percent-decoded, segment-checked, then `realpath` must stay inside the asset directory; otherwise `FVA-SEC-002` |
| Local file disclosure via bytes input | `inspect_bytes` never resolves relative URIs (status `unresolved`) |
| Oversized files | size checked from `stat()` **before** reading; oversized files are hashed in streaming fashion but not loaded |
| Oversized images | header-only probing; pixels are never decoded |
| Embedded data URIs | base64 only, size-checked before decoding, counted in the total resource budget |
| Executable content | glTF has none; no `eval`, no imports of asset-named modules, no subprocesses, no `bpy` |
| Long-running inputs | cooperative time budget checked inside hot loops |
| Report injection | untrusted strings appear only as JSON values; untrusted metadata (generator, copyright) is accepted only as bounded strings |

## Inspection limits (`Limits`, configurable with `--limits`)

| Limit | Default | Effect when reached |
|---|---|---|
| `max_file_bytes` | 128 MiB | `FVA-RES-001`, refused, file not read |
| `max_json_bytes` | 32 MiB | `FVA-RES-002`, refused |
| `max_json_depth` | 64 | `FVA-RES-002`, refused before parsing |
| `max_array_length` | 1,000,000 | `FVA-RES-002`, refused |
| `max_total_buffer_bytes` | 256 MiB | `FVA-RES-003`, resource not loaded, inspection incomplete |
| `max_data_uri_bytes` | 64 MiB | `FVA-RES-003` |
| `max_external_files` | 256 | `FVA-RES-003` |
| `max_decoded_components` | 40,000,000 | `FVA-RES-003`, remaining accessors not decoded |
| `max_node_depth` | 256 | `FVA-RES-005` |
| `max_report_list_items` | 512 | inspection lists truncated (flagged) |
| `time_budget_seconds` | 60 | `FVA-RES-004`, inspection stops |
| `allow_local_resources` | true | false ⇒ local dependencies recorded but not read |

## What is *not* claimed

* **No sandbox.** S3-A runs in the caller's process with the caller's privileges. The
  controls above bound what *S3-A* reads and allocates; they are not OS-level isolation.
  For untrusted bulk input, run it in a separate process or container with OS memory/CPU
  limits.
* **Memory is bounded indirectly** (file size, JSON size, decode budget, resource budget),
  not by an allocator limit. Peak memory is proportional to the decoded data, roughly
  50–100 bytes per decoded component in CPython.
* **The time budget is cooperative**: it is checked in loops over accessor data and
  triangles, so a single very large `json.loads` is bounded by `max_json_bytes`, not by
  the clock. Time-limited results are machine-dependent and therefore marked incomplete.
* Image *headers* are parsed; image *contents* are not validated for decoder exploits —
  consumers that decode images must use hardened decoders.
* Reproduced Finalverse admission profiles are diagnostic; they do not replace running the
  real admission code before publication.

## Verification

* Hostile-input tests: remote URIs (http, https to a metadata address, file, ftp),
  traversal (`../`, `%2F`-encoded, `sub/../../`), absolute and drive paths, symlink
  escape, invalid data URIs, depth bomb (100,000 levels), array and decode budgets,
  oversized files (not read), node depth.
* A test replaces `socket.socket` and inspects every fixture: no network access occurs.
* A test blocks `bpy`, `bmesh`, `mathutils` and `numpy` imports: the full pipeline runs.
* Fuzzing: see [S3A-TESTING.md](S3A-TESTING.md). It found and drove fixes for:
  unhashable-value lookups (8 sites), `len()` on non-arrays, a null `sparse`, unbounded
  synthetic index allocation from a declared count (memory exhaustion), and a non-string
  `asset.generator` carrying a non-finite number into the digest.
