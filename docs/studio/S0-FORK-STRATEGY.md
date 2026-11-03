# Maintained fork strategy

The fork preserves Blender target names, Python modules, operators, file-version
constants, `.blend` type identifiers and upstream license/copyright notices.
Product-facing names, application bundle identity and original artwork change.
This avoids a global replacement that would corrupt Blender APIs and file paths.

Upstream base: `0f5a1ae067d9785d2c106a887c94a0c96c3239a4`. macOS library
submodule: `3cc5e2a51c1f8d839b8fcdcd3ef3552950b37da5`. Origin remains
`https://github.com/finalverse/studio`. Source contains no pre-existing Finalverse
implementation. The initial checkout had no Git index and 7,068 missing LFS files;
index metadata was rebuilt without overwriting source. Missing paths were restored
as pointers, then required runtime assets fetched from the official upstream LFS
endpoint because the GitHub fork returned 404 for its upstream objects.

Original branding is under `finalverse/branding`; the local UI is one startup
module. Small native product patches are recorded in `patch-inventory.json`.
Optional build configuration is separate from upstream release/lite presets.
The GPL and all third-party notices remain in place. This local build is not a
signed/notarized public release; public distribution requires the corresponding
source, notices and review of the actual packaged dependencies.

No source history is rewritten and no push or protected merge is part of S0.
Upstream project README is retained verbatim as UPSTREAM-README.md.
