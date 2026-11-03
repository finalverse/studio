# Apple Silicon development build

Source is Blender 5.4 alpha, not the installed Blender 5.2.2 LTS. Xcode's Apple
Silicon SDK, CMake, Ninja, Git LFS and the exact macOS library gitlink are required.
Use `finalverse/build_macos.sh ABS_BUILD ABS_INSTALL`. The executable is
`ABS_INSTALL/Finalverse Studio.app/Contents/MacOS/Finalverse Studio`.

The S0 preset extends upstream `blender_lite.cmake`: modeling, animation, Python,
GLB, Eevee and Metal remain. Cycles, USD and heavyweight optional integrations are
disabled for this development build, not removed from the fork. A production
feature-complete build must use and verify the appropriate upstream release profile.

```sh
cd /Users/wenyan/Finalverse/studio
# For upstream pointer assets missing from the GitHub fork:
git -c lfs.url=https://projects.blender.org/blender/blender.git/info/lfs lfs fetch origin 0f5a1ae067d9785d2c106a887c94a0c96c3239a4 --include='release/**,assets/**'
git lfs checkout
GIT_LFS_SKIP_SMUDGE=1 git submodule update --init --checkout --depth 1 lib/macos_arm64
# Optional libraries disabled by the S0 preset need not be downloaded.
git -C lib/macos_arm64 lfs pull --include='*' --exclude='llvm/**,usd/**,openimagedenoise/**,openpgl/**,embree/**,osl/**,openvdb/**,materialx/**,alembic/**,ceres/**'
finalverse/build_macos.sh /Users/wenyan/Finalverse/dev/studio-s0-20261104/build /Users/wenyan/Finalverse/dev/studio-s0-20261104/install
python3 -m unittest discover -s finalverse/tests -p 'test_*.py' -v
```

Run `finalverse/tests/smoke.py` with the **built executable**, `--background
--factory-startup --disable-autoexec --python`, then `-- NEW_OUTPUT SOURCE_ROOT`.
The script records the actual engine path/version and tests mesh editing,
rendering, scene save/reopen, IDs, GLB/source export and refusal to overwrite.
A compatibility probe using installed Blender is reported separately, never as
proof that this fork compiled. See acceptance for actual source-build results.

Create a host backend descriptor using Python 3.13:
`finalverse/genesis_backend.py APP_PATH NEW_CONFIG_PATH`. Select it in the isolated
Core adapter through `FINALVERSE_STUDIO_CONFIG`. The descriptor grants no world
mutation/publication rights. Rebuilds change the executable hash and require a
new explicit descriptor. This is an unsigned local development bundle.
