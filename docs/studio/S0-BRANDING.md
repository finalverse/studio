# Product identity

Name: **Finalverse Studio**. Workspace: **Finalverse AI Studio**. Bundle identity:
`org.finalverse.studio`. Positioning: AI-Native 3D Creation, Animation, and World
Authoring Environment.

The white angular Finalverse emblem is the base for the Studio identity, following
the user's 2026-11-04 instruction. The supplied white/silver reference is
`~/Project2026/Finalverse/Images/Finalverse_logo_07@3x.png`. Its unchanged bytes
are retained in `finalverse/branding/source-finalverse-logo.png`; source SHA-256
and authorization are recorded in `finalverse/branding/source.json`.

The white vector is an explicitly simplified outline of that emblem: four
separated angular pieces, without the reference's bevels, shadows or purple fill.
It replaces the provisional portal/F design from the initial S0 implementation.
New Studio wordmark, icon and splash compositions use white, deep ink and a
restrained violet accent. No Blender logo is adapted into the new mark.

`logo-white.svg` and transparent `logo-white.png` provide the reusable Studio
lockup; `logo-preview.png` shows it on a dark field. Reproducible vector/code
sources create the macOS icon, monochrome UI glyphs and startup image.
Regeneration uses Python 3.13, Pillow 12.1.1, system Arial and macOS iconutil;
generated artwork is committed, so no Pillow dependency is installed into the
application. Native icon SVGs explicitly use Blender's 1600-unit glyph canvas.

Application/window/menu/CLI/About, temporary render/file windows and bundle/install
names identify the fork.
About and the welcome artwork explicitly retain Blender attribution. Technical
Blender Python/operator/format names remain unchanged for interoperability.
Internal CMake target remains `blender`; the macOS product is Finalverse Studio.app.
The development profile is Apple Silicon/Metal/Eevee; other platforms and release
installer/signing workflows are not validated by this acceptance.
