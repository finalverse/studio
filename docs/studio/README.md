# Finalverse Studio engineering

Studio is the Blender-based authoring application for Finalverse. Its approved
white emblem, application icon and licensing foundation are documented in
[S0 branding](S0-BRANDING.md). The accepted S0 app remains separately installed.

The current isolated milestone is **S2** on `feat/studio-s2`: typed AI-native
creation tools, E1-archetype characters (no forced humanoid skeleton), clip
animation, deterministic preview evaluation, the bounded creation loop and
Genesis-contract candidate packages. Start with [S2 acceptance](S2-ACCEPTANCE.md),
then the [creation engine](S2-CREATION-ENGINE.md), [character pipeline](S2-CHARACTER-PIPELINE.md),
[animation](S2-ANIMATION.md), [visual feedback](S2-VISUAL-FEEDBACK.md),
[Genesis integration](S2-GENESIS-INTEGRATION.md) and [V1 handoff](S2-V1-HANDOFF.md).
In the sidebar, **Creation loop · S2** takes an archetype, asset name and revision
budget; every proposal it produces still needs your approval, and **Reject &
Revise** sends a declined proposal back for a visible revision.

S1 (embedded local AI planning, artist approval, bounded typed authoring and MCP)
is documented in [S1 acceptance](S1-ACCEPTANCE.md),
[provider architecture](S1-PROVIDER-ARCHITECTURE.md),
[creation protocol](S1-CREATION-PROTOCOL.md), [MCP setup](S1-MCP.md),
[security](S1-SECURITY.md) and [S2 handoff](S1-S2-HANDOFF.md).

Open the **Finalverse** tab in the 3D View sidebar. Test Connection discovers actual
local models; select Gemma on the tested 16 GB Mac. Enter intent, Create Plan, review
the full JSON and return with Shift F5. Approve & Execute starts that exact plan.
Cancel stops future work; checkpoints and job history remain in the workspace.
The UI never executes free-form model code. Precise prompts are needed for this
initial language; invalid output is rejected and does not receive a substitute.

The macOS build command remains `finalverse/build_macos.sh BUILD_ABSOLUTE
INSTALL_ABSOLUTE`; it reuses the S0 development profile and does not overwrite an
existing accepted installation when given a separate install directory. See
[S0 build](S0-BUILD.md) for the pinned upstream libraries and optional-feature limits.
No signing, notarization, public release or world publication is implied.
