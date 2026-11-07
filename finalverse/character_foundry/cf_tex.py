"""Character Foundry texture authoring: UV-space rasterisation in numpy.

`position_map(obj)` rasterises the object's triangles into UV space and
returns per-texel object-space position, normal and a coverage mask. Painters
then compute albedo/roughness/normal fields as numpy functions of 3D position
(skin, eyes) or of UV (fabric weave, embroidery), at full texel resolution.
Results are written as Blender images (PNG, packed in the .blend) so the
authoring file keeps editable procedural sources and the GLB gets real maps.
"""
import math

import bpy
import numpy as np


def mesh_arrays(obj, uv_name=None):
    me = obj.data
    me.calc_loop_triangles()
    tris = me.loop_triangles
    n = len(tris)
    vidx = np.zeros(n * 3, dtype=np.int64); tris.foreach_get('vertices', vidx)
    lidx = np.zeros(n * 3, dtype=np.int64); tris.foreach_get('loops', lidx)
    co = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    nor = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get('normal', nor); nor = nor.reshape(-1, 3)
    uvl = me.uv_layers[uv_name] if uv_name else me.uv_layers.active
    uv = np.zeros(len(me.loops) * 2); uvl.data.foreach_get('uv', uv); uv = uv.reshape(-1, 2)
    mat = np.zeros(n, dtype=np.int64); tris.foreach_get('material_index', mat)
    return co, nor, vidx.reshape(-1, 3), uv[lidx].reshape(-1, 3, 2), mat


def position_map(obj, size, uv_name=None, material_index=None, pad=4):
    co, nor, tv, tuv, mat = mesh_arrays(obj, uv_name)
    H = W = size
    P = np.zeros((H, W, 3), np.float32); N = np.zeros((H, W, 3), np.float32)
    M = np.zeros((H, W), bool)
    for t in range(len(tv)):
        if material_index is not None and mat[t] not in material_index:
            continue
        uv = tuv[t] * (W, H)
        x0, y0 = np.floor(uv.min(0)).astype(int); x1, y1 = np.ceil(uv.max(0)).astype(int)
        x0 = max(x0, 0); y0 = max(y0, 0); x1 = min(x1, W - 1); y1 = min(y1, H - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
        (ax, ay), (bx, by), (cx, cy) = uv
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        l0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / d
        l1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / d
        l2 = 1 - l0 - l1
        e = -1.0 / max(abs(d), 1.0)  # include edge texels (small conservative margin)
        inside = (l0 >= e) & (l1 >= e) & (l2 >= e)
        if not inside.any():
            continue
        L = np.stack([l0, l1, l2], -1)[inside]
        p = L @ co[tv[t]]; nn = L @ nor[tv[t]]
        iy = (ys[inside] - .5).astype(int); ix = (xs[inside] - .5).astype(int)
        P[iy, ix] = p; N[iy, ix] = nn; M[iy, ix] = True
    nl = np.linalg.norm(N, axis=-1, keepdims=True); N = N / np.maximum(nl, 1e-8)
    return P, N, M


def dilate(img, mask, iterations=8):
    """Bleed colours outward past UV island borders (prevents seams at mips)."""
    img = img.copy(); m = mask.copy()
    for _ in range(iterations):
        acc = np.zeros_like(img); cnt = np.zeros(m.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sm = np.roll(m, (dy, dx), (0, 1)); si = np.roll(img, (dy, dx), (0, 1))
            acc[sm] += si[sm]; cnt[sm] += 1
        grow = (~m) & (cnt > 0)
        img[grow] = acc[grow] / cnt[grow][:, None]
        m = m | grow
    return img


def to_image(name, arr, colorspace='sRGB', alpha=None):
    """arr: HxWx3 float in [0,1] (display-referred for sRGB images)."""
    H, W = arr.shape[:2]
    img = bpy.data.images.get(name)
    if img is None or img.size[0] != W:
        if img:
            bpy.data.images.remove(img)
        img = bpy.data.images.new(name, W, H, alpha=alpha is not None)
    img.colorspace_settings.name = colorspace
    rgba = np.ones((H, W, 4), np.float32)
    rgba[..., :3] = np.clip(arr, 0, 1)
    if alpha is not None:
        rgba[..., 3] = np.clip(alpha, 0, 1)
    img.pixels.foreach_set(rgba.ravel())
    import os
    d = os.environ.get('CF_TEX_DIR', os.path.expanduser('~/cf/work/textures')); os.makedirs(d, exist_ok=True)
    img.filepath_raw = os.path.join(d, name + '.png')
    img.file_format = 'PNG'
    img.save()
    img.pack()
    return img


def lin2srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def srgb(hexstr):
    h = hexstr.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)


# ---- procedural noise (deterministic, numpy) ---------------------------------
def value_noise3(p, freq, seed=0):
    """Smooth value noise on 3D points p (...x3)."""
    q = p * freq
    i = np.floor(q).astype(np.int64); f = q - i
    f = f * f * (3 - 2 * f)

    def h(ix, iy, iz):
        n = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
        n = (n ^ (n >> 13)) * 1274126177
        return ((n ^ (n >> 16)) & 0xffff) / 65535.0
    out = 0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (f[..., 0] if dx else 1 - f[..., 0]) * (f[..., 1] if dy else 1 - f[..., 1]) * (f[..., 2] if dz else 1 - f[..., 2])
                out = out + w * h(i[..., 0] + dx, i[..., 1] + dy, i[..., 2] + dz)
    return out


def fbm3(p, freq, octaves=4, seed=0):
    out = 0; amp = .5; tot = 0
    for o in range(octaves):
        out = out + amp * value_noise3(p, freq * (2 ** o), seed + o); tot += amp; amp *= .5
    return out / tot


def value_noise2(uv, freq, seed=0):
    p = np.concatenate([uv, np.zeros(uv.shape[:-1] + (1,))], -1)
    return value_noise3(p, np.array([freq[0], freq[1], 1.0]) if np.ndim(freq) else freq, seed)


def height_to_normal(h, strength):
    """Tangent-space normal map (OpenGL +Y) from a height field."""
    gy, gx = np.gradient(h)
    n = np.stack([-gx * strength, -gy * strength, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * .5 + .5


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)
