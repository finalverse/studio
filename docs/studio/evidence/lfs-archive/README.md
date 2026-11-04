# Portable historical evidence

GitHub rejected new Git LFS objects for the public `finalverse/studio` fork.
This cloud handoff keeps the accepted commits intact: no rebase, history rewrite,
force push, repository detachment or main-branch change is required.

Current Finalverse PNG evidence is stored as ordinary Git blobs. This archive also
retains the exact bytes of all ten screenshots referenced by unpublished historical
LFS pointers. `manifest.json` maps their original paths, SHA-256 OIDs and sizes.
The objects total 7,990,573 bytes and are deduplicated by Git where content matches.
Upstream Blender's LFS policy and other file types are unchanged.

For a historical pointer with OID `OID`, read `OID.png` here, or use
`git show origin/feat/studio-v1:docs/studio/evidence/lfs-archive/OID.png`.
The historical pointer's SHA-256 matches the archived PNG byte-for-byte. Checking
out an old commit directly can still require skipping unavailable LFS smudging;
use this archive for its screenshot content. Current branch heads contain the
materialized screenshots at their original paths.

The handoff push skips only the redundant historical LFS upload after verifying
that every new LFS object is fully archived as an ordinary Git blob and every
current fork-owned screenshot is materialized. It does not skip tests, overwrite
remote history or claim the unavailable LFS server contains those objects.
See the Git LFS maintainer's [public-fork explanation](https://github.com/git-lfs/git-lfs/issues/1906).
