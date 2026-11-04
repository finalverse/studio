# S1 security boundary

Models and MCP clients propose **data** in a closed, validated language. The Blender
bridge implements a fixed allowlist. Neither interface offers arbitrary Python,
shell execution, arbitrary filesystem paths, network fetches from model output,
new executable tools or civilization publication. Studio remains a trusted local
desktop authoring application running as its user; it does not sandbox that user,
their installed add-ons, trusted Python console or a malicious same-account process.

Approval is local to the Studio host, tied to the exact envelope digest, scene
revision, random host session and 15-minute expiry by an in-memory HMAC key. MCP
can submit, inspect, monitor and cancel, but has no approval capability. Restart
invalidates approvals. SQLite serializes transactions, validates expected states
and rejects conflicting request UUID reuse. Only one host may own a workspace.
The scene is checked again before execution and between steps. Concurrent human
edits stop the remaining plan.

The trusted host chooses a private workspace (0700, database 0600). A loaded scene
cannot choose it. Symlink workspaces, ancestor symlinks, symlink job directories and
output reuse are refused. Every operation uses validated basenames under a fresh
UUID job directory; MCP accepts no workspace/path changes. The account that owns
these files can still alter them: local receipts are inspectable audit records,
not remote attestation against their owner. Do not share a writable workspace with
untrusted accounts or treat a `.blend`/add-on as an independently safe executable.

Inference runs in a fixed shipped helper without `bpy`. It receives an environment
cleared of unrelated credentials and only the selected provider token, if any.
It has CPU/file/wall limits, HTTP response bounds and no redirect/proxy handling.
Only loopback may use HTTP; remote inference requires HTTPS plus a referenced
credential. No credential belongs in a plan, command-line URL or receipt. Prompt
and scene summaries are sent to the selected provider, so provider selection is a
data-disclosure choice. No external provider was enabled in this local run.

Preview rendering uses a fixed shipped script and `--disable-autoexec`, two Blender
threads, a 60-second wall/CPU limit, 1 GiB aggregate process RSS limit, 128 MiB
per-file cap and 256-descriptor limit. macOS `sandbox-exec` denies default access,
allows executable/resources from the selected app and system, reads the exact
checkpoint, writes its private preview directory, permits required AGX
interfaces and grants no network rule. Two OS-provided per-app Metal compiler/GPU
archive cache subdirectories also permit reads/writes; growth is monitored with
a 128 MiB limit and 4,096-entry limit. No other user cache directory is granted.
The supervisor monitors descendants and
parent loss; cancellation kills the process group. GPU memory is not independently
metered or hard-capped by this policy; dimensions/samples and scene complexity
bound the requested workload. It is a local macOS development profile, not a
portable production isolation guarantee.

Main-thread mesh edits, save, export and index hashing are bounded by the supported
scene profile and workspace admission quota. They can briefly occupy the UI;
S1 does not claim hard realtime preemption inside a Blender operator. File-size
checks on host checkpoints occur after writing. The 512 MiB budget reserves space
before operations, while the render worker also has an OS file limit. Disk quotas
against arbitrary trusted packed Blender data are not claimed. The restricted
S1 scene profile excludes external texture/material graphs and evaluation drivers.

Restart never guesses that an uncertain effect should run twice. Applied steps
are visible and recoverable, cancellation is partial rather than transactional
rollback, and no job claims success after a worker failure. Rejected model JSON
stays inert; there is no hidden deterministic replacement or automatic repair.
Future repair proposals must be separately validated and approved.

The independent Genesis validator, Civilization policy, MutSea commit authority,
SpatialDB publication and WorldLine history remain outside this bridge. A rendered
or exported candidate supplies none of those grants. Existing Core/Native sources,
accepted founder embodiments, memories, balances and worlds are untouched.
