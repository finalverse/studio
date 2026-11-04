# Upstream synchronization

1. Preserve a clean acceptance commit, artifact receipts and local changes.
2. Fetch the official Blender upstream into a separate integration branch.
3. Review upstream version, library gitlink, Python ABI and licensing changes.
4. Rebase/merge the small product patch inventory deliberately. Never replace
   technical Blender identifiers, APIs or canonical `.blend` signatures.
5. Fetch runtime LFS objects for that exact upstream commit; the GitHub fork does
   not currently mirror the original Blender LFS store. Keep original artwork in
   ordinary Git so it is independent of that upstream store.
6. Update the corresponding macOS library submodule only as an explicit dependency
   change, then configure/build the development and intended release profiles.
7. Run candidate-integrity negative tests, actual startup/render/save/reopen/GLB
   smoke, visible workspace/menu/icon checks, and supervised Genesis adapter proof.
   Re-test the offline-access banner on the Asset Browser's first draw and F3
   menu search from that editor, including nested menu layouts. The pinned 5.4
   alpha needed two null-initialization fixes; review and drop them once upstream
   supplies equivalent fixes. A search-only guard alone does not cover nested
   layouts without a region.
8. Compare Studio export against the accepted E1/Genesis/Infinity profile. A good
   Studio render does not prove equivalent Infinity materials or animation.

S1 must add typed creation operations and provider/MCP security while preserving
this boundary. V0 must establish visual conformance before V1 asset replacement.
