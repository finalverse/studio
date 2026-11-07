"""CF1 Elara: look development. Paints every texture in numpy (cf_tex) and builds
glTF-exportable Principled materials (BaseColor / Normal / ORM images).

Painters are deterministic functions of 3D position (skin, eyes) or UV
(fabric, embroidery, leather, hair strands). Palette follows the canonical
vision art: auburn hair, forest-green tunic with gold vine and music-staff
embroidery, brown leggings and boots, deep-blue wool cloak with gold leaves.
"""
import math

import bpy
import numpy as np

import cf_tex as TX

PAL = {
    'skin': '#e9bba0', 'blush': '#d9877a', 'lip': '#b85c58', 'brow': '#4e2416', 'freckle': '#b9714f',
    'tunic': '#47693a', 'tunic_dark': '#2f4a26', 'gold': '#d4a94e',
    'cloak': '#2c4b73', 'cloak_dark': '#1d3352', 'lining': '#1b2742',
    'leather': '#6e4527', 'leather_dark': '#3f2614', 'leggings': '#4c3b24',
    'hair': '#6a2914', 'hair_hi': '#a64c25', 'hair_root': '#3c160a',
    'wood': '#7a5230', 'brass': '#c9a050', 'flower': '#e2782a',
}


# ------------------------------------------------------------ drawing ------
def seg_dist(X, Y, a, b):
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy + 1e-12
    t = np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0, 1)
    return np.hypot(X - (ax + t * dx), Y - (ay + t * dy))


def draw_poly(mask, X, Y, pts, width, val=1.0):
    """Anti-aliased polyline (metric coordinates X, Y)."""
    px = (X[0, 1] - X[0, 0]) if X.shape[1] > 1 else 1e-3
    pts = np.asarray(pts)
    for a, b in zip(pts, pts[1:]):
        x0, x1 = min(a[0], b[0]) - width * 2, max(a[0], b[0]) + width * 2
        y0, y1 = min(a[1], b[1]) - width * 2, max(a[1], b[1]) + width * 2
        cols = np.nonzero((X[0] >= x0) & (X[0] <= x1))[0]
        rows = np.nonzero((Y[:, 0] >= y0) & (Y[:, 0] <= y1))[0]
        if not len(cols) or not len(rows):
            continue
        sl = (slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1))
        d = seg_dist(X[sl], Y[sl], a, b)
        a_ = np.clip((width / 2 - d) / max(px, 1e-6) + .5, 0, 1) * val
        mask[sl] = np.maximum(mask[sl], a_)


def draw_ellipse(mask, X, Y, c, rx, ry, rot=0.0, val=1.0):
    px = X[0, 1] - X[0, 0]
    r = max(rx, ry) * 1.5
    cols = np.nonzero((X[0] >= c[0] - r) & (X[0] <= c[0] + r))[0]
    rows = np.nonzero((Y[:, 0] >= c[1] - r) & (Y[:, 0] <= c[1] + r))[0]
    if not len(cols) or not len(rows):
        return
    sl = (slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1))
    x = X[sl] - c[0]; y = Y[sl] - c[1]
    cr, sr = math.cos(rot), math.sin(rot)
    xr, yr = x * cr + y * sr, -x * sr + y * cr
    q = np.sqrt((xr / rx) ** 2 + (yr / ry) ** 2)
    a = np.clip((1 - q) * min(rx, ry) / max(px, 1e-6) + .5, 0, 1) * val
    mask[sl] = np.maximum(mask[sl], a)


def leaf(mask, X, Y, base, ang, length, width):
    tip = (base[0] + math.cos(ang) * length, base[1] + math.sin(ang) * length)
    c = ((base[0] + tip[0]) / 2, (base[1] + tip[1]) / 2)
    draw_ellipse(mask, X, Y, c, length / 2, width / 2, ang)


def vine(mask, X, Y, p0, p1, amp, period, width, leaf_len, rng, phase=0.0, leaves=True):
    """Scrolling vine between p0 and p1 with alternating leaves."""
    p0 = np.array(p0, float); p1 = np.array(p1, float)
    d = p1 - p0; L = np.linalg.norm(d); t = d / L; n = np.array([-t[1], t[0]])
    s = np.linspace(0, L, max(8, int(L / (period / 16))))
    pts = [p0 + t * si + n * amp * math.sin(2 * math.pi * si / period + phase) for si in s]
    draw_poly(mask, X, Y, pts, width)
    if not leaves:
        return
    k = 0
    for si in np.arange(period * 0.25, L, period / 2):
        p = p0 + t * si + n * amp * math.sin(2 * math.pi * si / period + phase)
        side = 1 if k % 2 == 0 else -1
        ang = math.atan2(*(t[::-1])) + side * (0.9 + 0.2 * rng.random())
        leaf(mask, X, Y, p, ang, leaf_len * (0.8 + 0.4 * rng.random()), leaf_len * 0.45)
        # small curl tendril
        cc = p + n * side * leaf_len * 0.6
        draw_ellipse(mask, X, Y, cc, leaf_len * 0.18, leaf_len * 0.18, 0, 0.0)
        k += 1


def grid(size, wu, hv):
    """Metric pixel grid: X over u (metres), Y over v (metres)."""
    u = (np.arange(size) + .5) / size
    return np.meshgrid(u * wu, u * hv)


def orm(rough, metal=None, ao=None):
    H, W = rough.shape
    out = np.ones((H, W, 3), np.float32)
    out[..., 0] = 1 if ao is None else ao
    out[..., 1] = rough
    out[..., 2] = 0 if metal is None else metal
    return out


# ---------------------------------------------------------- materials ------
def pbr(name, base, normal=None, ormimg=None, rough=0.5, metal=0.0, uv_scale=None, subsurface=0.0,
        sss_radius=(1.0, 0.35, 0.2), sss_scale=0.008, coat=0.0, aniso=0.0, sheen=0.0, base_factor=None,
        emission=None, normal_strength=1.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (500, 0)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (200, 0)
    nt.links.new(b.outputs[0], out.inputs[0])
    uvn = None
    if uv_scale:
        tc = nt.nodes.new('ShaderNodeTexCoord'); tc.location = (-900, 0)
        uvn = nt.nodes.new('ShaderNodeMapping'); uvn.location = (-700, 0)
        uvn.inputs['Scale'].default_value = (uv_scale, uv_scale, 1)
        nt.links.new(tc.outputs['UV'], uvn.inputs['Vector'])

    def tex(img, y, cs='sRGB'):
        t = nt.nodes.new('ShaderNodeTexImage'); t.image = img; t.location = (-400, y)
        if img.colorspace_settings.name != cs:
            img.colorspace_settings.name = cs
            img.reload()
        if uvn:
            nt.links.new(uvn.outputs[0], t.inputs[0])
        return t
    if isinstance(base, bpy.types.Image):
        nt.links.new(tex(base, 300).outputs[0], b.inputs['Base Color'])
    else:
        b.inputs['Base Color'].default_value = (*base, 1)
    if normal is not None:
        tn = tex(normal, -300, 'Non-Color')
        nm = nt.nodes.new('ShaderNodeNormalMap'); nm.location = (-100, -300)
        nm.inputs['Strength'].default_value = normal_strength
        nt.links.new(tn.outputs[0], nm.inputs['Color']); nt.links.new(nm.outputs[0], b.inputs['Normal'])
    if ormimg is not None:
        to = tex(ormimg, 0, 'Non-Color')
        sep = nt.nodes.new('ShaderNodeSeparateColor'); sep.location = (-100, 0)
        nt.links.new(to.outputs[0], sep.inputs[0])
        nt.links.new(sep.outputs['Green'], b.inputs['Roughness'])
        nt.links.new(sep.outputs['Blue'], b.inputs['Metallic'])
    else:
        b.inputs['Roughness'].default_value = rough
        b.inputs['Metallic'].default_value = metal
    if subsurface:
        b.inputs['Subsurface Weight'].default_value = subsurface
        b.inputs['Subsurface Radius'].default_value = sss_radius
        b.inputs['Subsurface Scale'].default_value = sss_scale
    if coat:
        b.inputs['Coat Weight'].default_value = coat
        b.inputs['Coat Roughness'].default_value = 0.03
    if aniso:
        b.inputs['Anisotropic'].default_value = aniso
        tg = nt.nodes.new('ShaderNodeTangent'); tg.direction_type = 'UV_MAP'; tg.location = (-100, -550)
        nt.links.new(tg.outputs[0], b.inputs['Tangent'])
    if sheen:
        b.inputs['Sheen Weight'].default_value = sheen
        b.inputs['Sheen Roughness'].default_value = 0.5
    if emission:
        b.inputs['Emission Color'].default_value = (*emission[0], 1)
        b.inputs['Emission Strength'].default_value = emission[1]
    m.diffuse_color = (*(TX.srgb('#888888') if isinstance(base, bpy.types.Image) else base), 1)
    m['cf.painted'] = True
    return m


def lin(hexs):
    c = TX.srgb(hexs)
    return tuple(np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4))


# ---------------------------------------------------------------- skin -----
def paint_skin(body, lm, size=2048, mat_index=0):
    P, N, M = TX.position_map(body, size)
    rng = np.random.default_rng(5)
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    col = np.broadcast_to(TX.srgb(PAL['skin']), P.shape).astype(np.float32).copy()
    var = TX.fbm3(P, 14.0, 3, 1) - .5
    col *= (1 + 0.08 * var)[..., None]
    rough = np.full(x.shape, 0.50, np.float32)
    front = N[..., 1] < -0.15
    face = (z > lm['chin_z']) & (z < lm['brow_z'] + 0.05) & (np.abs(x) < 0.08)
    # cheeks & nose blush
    def g(c, r):
        return np.exp(-(((x - c[0]) ** 2 + (y - c[1]) ** 2 + (z - c[2]) ** 2) / (2 * r * r)))
    blush = np.zeros_like(x)
    for sx in (1, -1):
        ec = lm['eye'][sx]
        blush += 0.55 * g((ec[0] + sx * 0.010, ec[1] - 0.005, ec[2] - 0.030), 0.016)
    blush += 0.45 * g(lm['nose'], 0.010)
    blush += 0.25 * g((0, lm['nose'][1] + 0.01, lm['chin_z'] + 0.012), 0.012)
    # ears warmer
    for sx in (1, -1):
        blush += 0.35 * g((sx * 0.075, lm['ear_y'], lm['eye'][1][2] - 0.01), 0.018)
    blush = np.clip(blush, 0, 1) * face.astype(np.float32) + np.clip(blush, 0, 1) * (np.abs(x) > 0.06) * (z > lm['chin_z'])
    col = col * (1 - 0.45 * blush[..., None]) + TX.srgb(PAL['blush']) * 0.45 * blush[..., None]
    # freckles over nose bridge and upper cheeks
    fr_mask = np.zeros_like(x)
    for sx in (1, -1):
        ec = lm['eye'][sx]
        fr_mask += g((ec[0] * 0.6, ec[1] - 0.01, ec[2] - 0.022), 0.020)
    fr_mask = np.clip(fr_mask, 0, 1) * front
    spots = TX.value_noise3(P, 900.0, 9)
    fr = np.clip((spots - 0.80) / 0.08, 0, 1) * fr_mask
    col = col * (1 - 0.35 * fr[..., None]) + TX.srgb(PAL['freckle']) * 0.35 * fr[..., None]
    # lips
    m = lm['mouth']
    dx = (x - m[0]) / 0.0245
    up = z > m[2]
    dz = np.where(up, (z - m[2]) / (0.0072 + 0.0018 * np.cos(np.clip(dx, -1, 1) * math.pi * 1.0) * 0.0 + 0.0006),
                  (m[2] - z) / 0.0105)
    bow = 0.18 * np.exp(-((x - m[0]) / 0.004) ** 2) * up    # cupid's bow dip
    q = np.sqrt(dx ** 2 + dz ** 2) + bow
    lipm = np.clip((1 - q) / 0.12, 0, 1) * front * (y < m[1] + 0.012)
    col = col * (1 - 0.8 * lipm[..., None]) + TX.srgb(PAL['lip']) * 0.8 * lipm[..., None]
    seam = np.exp(-((z - m[2]) / 0.0009) ** 2) * (np.abs(dx) < 0.95) * front * (y < m[1] + 0.012)
    col *= (1 - 0.45 * seam)[..., None]
    rough = rough * (1 - lipm) + 0.32 * lipm
    # eyebrows: arched, tapered, stroke texture
    brow = np.zeros_like(x)
    for sx in (1, -1):
        ec = lm['eye'][sx]
        u = (x - ec[0]) * sx      # + outward
        inside = (u > -0.019) & (u < 0.024)
        tt = np.clip((u + 0.019) / 0.043, 0, 1)
        zc = ec[2] + 0.0160 + 0.0070 * np.sin(tt * math.pi * 0.8) - 0.003 * tt
        half = 0.0040 * (1 - 0.6 * tt) + 0.0009
        d = np.abs(z - zc)
        strokes = 0.65 + 0.35 * np.sin((u * 1800 + z * 2600 * (0.3 + tt))) ** 2
        brow = np.maximum(brow, np.clip((half - d) / 0.0009, 0, 1) * inside * strokes * (y < ec[1] + 0.01))
    col = col * (1 - 0.85 * brow[..., None]) + TX.srgb(PAL['brow']) * 0.85 * brow[..., None]
    rough = rough * (1 - brow) + 0.65 * brow
    # upper-lid liner: darken the lid crease ring slightly
    for sx in (1, -1):
        ec = lm['eye'][sx]
        r = np.sqrt((x - ec[0]) ** 2 + (z - ec[2] - 0.001) ** 2)
        lid = np.exp(-((r - 0.0118) / 0.0014) ** 2) * (z > ec[2] + 0.001) * (y < ec[1] + 0.004) * front
        col *= (1 - 0.55 * lid)[..., None]
        sock = np.exp(-((r - 0.016) / 0.006) ** 2) * front * (y < ec[1] + 0.01)
        col = col * (1 - 0.10 * sock[..., None]) + TX.srgb('#b77f74') * 0.10 * sock[..., None]
    tzone = np.exp(-(x / 0.012) ** 2) * (z > lm['nose'][2] - 0.01) * (z < lm['brow_z'] + 0.04) * front
    rough -= 0.10 * tzone
    pores = TX.fbm3(P, 700.0, 2, 3)
    h = pores * 0.6 + 0.4 * TX.fbm3(P, 160.0, 2, 4)
    nrm = TX.height_to_normal(h, 3.0)
    col = TX.lin2srgb(np.power(np.clip(col, 0, 1), 1.0)) if False else col
    col = TX.dilate(col, M, 8); nrm = TX.dilate(nrm, M, 8)
    rough = TX.dilate(np.repeat(rough[..., None], 3, -1), M, 8)[..., 0]
    return (TX.to_image('T_Elara_Skin_BaseColor', col), TX.to_image('T_Elara_Skin_Normal', nrm, 'Non-Color'),
            TX.to_image('T_Elara_Skin_ORM', orm(np.clip(rough, .25, .8)), 'Non-Color'))


# --------------------------------------------------------------- tunic -----
def paint_tunic(size=2048, wu=0.98, hv=0.80):
    rng = np.random.default_rng(21)
    X, Y = grid(size, wu, hv)
    U = X / wu
    base = TX.srgb(PAL['tunic'])
    # linen weave
    wx = np.sin(X * 2 * math.pi / 0.0011); wy = np.sin(Y * 2 * math.pi / 0.0011)
    weave = 0.5 + 0.25 * wx * np.sign(wy) + 0.25 * wy * np.sign(wx)
    slub = TX.value_noise2(np.stack([X * 60, Y * 6], -1), 1.0, 2)
    col = base * (0.88 + 0.12 * weave + 0.10 * (slub - .5))[..., None]
    col = col * (1 - 0.15 * np.clip((0.03 - Y) / 0.03, 0, 1))[..., None]
    emb = np.zeros(X.shape, np.float32)
    # hem: music staff + notes, framed by a vine band
    y0 = 0.035
    for k in range(5):
        draw_poly(emb, X, Y, [(0, y0 + k * 0.0055), (wu, y0 + k * 0.0055)], 0.0011)
    for xn in np.arange(0.02, wu, 0.045):
        k = rng.integers(0, 5); yy = y0 + k * 0.0055
        draw_ellipse(emb, X, Y, (xn, yy), 0.0042, 0.0030, 0.35)
        draw_poly(emb, X, Y, [(xn + 0.0038, yy), (xn + 0.0038, yy + 0.020)], 0.0013)
        if rng.random() < 0.4:
            draw_poly(emb, X, Y, [(xn + 0.0029, yy + 0.016), (xn + 0.011, yy + 0.011)], 0.0009)
    vine(emb, X, Y, (0, 0.080), (wu, 0.080), 0.008, 0.07, 0.0022, 0.013, rng)
    draw_poly(emb, X, Y, [(0, 0.012), (wu, 0.012)], 0.0016)
    # front placket vine (u = 0 / 1 wraps at the front centre)
    for xc in (0.0, wu):
        for sgn in (1, -1):
            draw_poly(emb, X, Y, [(xc + sgn * 0.020, 0.10), (xc + sgn * 0.020, hv * 0.99)], 0.0016)
        vine(emb, X, Y, (xc, 0.10), (xc, hv * 0.985), 0.009, 0.08, 0.0022, 0.014, rng, phase=0.5)
    # neckline trim
    draw_poly(emb, X, Y, [(0, hv * 0.985), (wu, hv * 0.985)], 0.0016)
    for xc in np.arange(0.01, wu, 0.03):
        leaf(emb, X, Y, (xc, hv * 0.965), math.pi / 2 + 0.6 * math.sin(xc * 40), 0.012, 0.005)
    gold = TX.srgb(PAL['gold']) * (0.85 + 0.15 * np.sin(X * 2 * math.pi / 0.0009)[..., None])
    col = col * (1 - emb[..., None]) + gold * emb[..., None]
    h = 0.3 * weave + 0.9 * emb
    nrm = TX.height_to_normal(h, 6.0)
    rough = 0.88 - 0.40 * emb
    metal = 0.55 * emb
    return (TX.to_image('T_Elara_Tunic_BaseColor', col), TX.to_image('T_Elara_Tunic_Normal', nrm, 'Non-Color'),
            TX.to_image('T_Elara_Tunic_ORM', orm(rough, metal), 'Non-Color'))


# --------------------------------------------------------------- cloak -----
def paint_cloak(size=2048, wu=1.9, hv=1.15):
    rng = np.random.default_rng(31)
    X, Y = grid(size, wu, hv)
    base = TX.srgb(PAL['cloak'])
    fib = TX.value_noise2(np.stack([X * 900, Y * 900], -1), 1.0, 4)
    tw = 0.5 + 0.5 * np.sin((X + Y) * 2 * math.pi / 0.0016)
    mott = TX.fbm3(np.stack([X, Y, np.zeros_like(X)], -1), 6.0, 3, 5)
    col = base * (0.85 + 0.10 * fib + 0.06 * tw + 0.18 * (mott - .5))[..., None]
    emb = np.zeros(X.shape, np.float32)
    # hem border
    draw_poly(emb, X, Y, [(0, 0.020), (wu, 0.020)], 0.0028)
    vine(emb, X, Y, (0, 0.065), (wu, 0.065), 0.016, 0.16, 0.0024, 0.026, rng)
    draw_poly(emb, X, Y, [(0, 0.112), (wu, 0.112)], 0.0018)
    # front edges
    for xc, sg in ((0.0, 1), (wu, -1)):
        draw_poly(emb, X, Y, [(xc + sg * 0.012, 0.0), (xc + sg * 0.012, hv)], 0.0024)
        vine(emb, X, Y, (xc + sg * 0.040, 0.11), (xc + sg * 0.040, hv), 0.010, 0.14, 0.0020, 0.022, rng, phase=1.0)
    # scattered single leaves on the upper back (reference: gold leaves on the shoulders)
    for _ in range(26):
        cx = rng.uniform(0.15, wu - 0.15); cy = rng.uniform(hv * 0.78, hv * 0.97)
        leaf(emb, X, Y, (cx, cy), rng.uniform(0, 2 * math.pi), 0.022, 0.010)
    gold = TX.srgb(PAL['gold'])
    col = col * (1 - emb[..., None]) + gold * emb[..., None]
    nrm = TX.height_to_normal(0.4 * fib + 0.25 * tw + 1.2 * emb, 5.0)
    rough = 0.92 - 0.45 * emb
    out = (TX.to_image('T_Elara_Cloak_BaseColor', col), TX.to_image('T_Elara_Cloak_Normal', nrm, 'Non-Color'),
           TX.to_image('T_Elara_Cloak_ORM', orm(rough, 0.5 * emb), 'Non-Color'))
    # lining: deep navy, a leaf frieze near the hem
    lin_ = TX.srgb(PAL['lining']) * (0.9 + 0.1 * fib + 0.1 * (mott - .5))[..., None]
    emb2 = np.zeros(X.shape, np.float32)
    vine(emb2, X, Y, (0, 0.10), (wu, 0.10), 0.03, 0.22, 0.0022, 0.034, rng)
    for _ in range(60):
        cx = rng.uniform(0, wu); cy = rng.uniform(0.15, 0.32)
        leaf(emb2, X, Y, (cx, cy), rng.uniform(0, 2 * math.pi), 0.024, 0.011)
    lin_ = lin_ * (1 - emb2[..., None]) + gold * 0.85 * emb2[..., None]
    out += (TX.to_image('T_Elara_CloakLining_BaseColor', lin_),)
    return out


# --------------------------------------------------------------- leather ---
def paint_leather(size=1024):
    rng = np.random.default_rng(41)
    u = (np.arange(size) + .5) / size
    U, V = np.meshgrid(u, u)
    P = np.stack([U, V, np.zeros_like(U)], -1)
    grain = TX.fbm3(P, 90.0, 3, 7)
    cells = TX.value_noise3(P, 260.0, 8)
    scratch = np.zeros_like(U)
    for _ in range(40):
        a = rng.uniform(0, 1, 2); b = a + rng.normal(0, 0.06, 2)
        draw_poly(scratch, U, V, [a, b], 0.0015, 0.6)
    base = TX.srgb(PAL['leather'])
    col = base * (0.86 + 0.14 * (grain - .5) + 0.05 * cells)[..., None] * (1 - 0.25 * scratch)[..., None]
    edge = np.clip(1 - np.minimum(V, 1 - V) / 0.08, 0, 1)
    col = col * (1 - 0.35 * edge[..., None]) + TX.srgb(PAL['leather_dark']) * 0.35 * edge[..., None]
    stitch = np.zeros_like(U)
    for vv in (0.14, 0.86):
        stitch += (np.abs(V - vv) < 0.006) * (np.sin(U * 2 * math.pi * 60) > 0.2)
    col = col * (1 - 0.5 * stitch[..., None]) + TX.srgb('#d8c49a') * 0.5 * stitch[..., None]
    h = 0.6 * grain + 0.3 * cells - 0.5 * scratch - 0.4 * stitch
    return (TX.to_image('T_Leather_BaseColor', col), TX.to_image('T_Leather_Normal', TX.height_to_normal(h, 1.6), 'Non-Color'),
            TX.to_image('T_Leather_ORM', orm(0.55 + 0.15 * (grain - .5) + 0.2 * scratch), 'Non-Color'))


# ------------------------------------------------------------------ hair ---
def paint_hair(size=1024):
    u = (np.arange(size) + .5) / size
    U, V = np.meshgrid(u, u)
    strands = np.zeros_like(U)
    for f, a in ((23, .35), (61, .25), (149, .2), (311, .2)):
        strands += a * (0.5 + 0.5 * np.sin(U * 2 * math.pi * f + 3 * np.sin(V * 7 + f)))
    col_base = TX.srgb(PAL['hair']); col_hi = TX.srgb(PAL['hair_hi']); col_root = TX.srgb(PAL['hair_root'])
    t = strands[..., None]
    col = col_base * (1 - t * 0.55) + col_hi * t * 0.55
    rootness = TX.smoothstep(0.75, 1.0, V)[..., None]
    col = col * (1 - 0.45 * rootness) + col_root * 0.45 * rootness
    tipness = TX.smoothstep(0.2, 0.0, V)[..., None]
    col = col * (1 - 0.25 * tipness) + col_hi * 0.25 * tipness
    nrm = TX.height_to_normal(strands, 6.0)
    return (TX.to_image('T_Hair_BaseColor', col), TX.to_image('T_Hair_Normal', nrm, 'Non-Color'),
            TX.to_image('T_Hair_ORM', orm(0.42 - 0.10 * strands), 'Non-Color'))


def paint_knit(size=512):
    u = (np.arange(size) + .5) / size
    U, V = np.meshgrid(u, u)
    rib = 0.5 + 0.5 * np.sin(U * 2 * math.pi * 48)
    loops = 0.5 + 0.5 * np.sin(V * 2 * math.pi * 96 + np.sin(U * 2 * math.pi * 48) * 1.5)
    h = 0.6 * rib + 0.4 * loops
    col = TX.srgb(PAL['leggings']) * (0.85 + 0.2 * h)[..., None]
    return (TX.to_image('T_Knit_BaseColor', col), TX.to_image('T_Knit_Normal', TX.height_to_normal(h, 3.0), 'Non-Color'))


def paint_wood(size=512):
    u = (np.arange(size) + .5) / size
    U, V = np.meshgrid(u, u)
    P = np.stack([U * 3, V * 30, np.zeros_like(U)], -1)
    g = TX.fbm3(P, 3.0, 3, 12)
    rings = 0.5 + 0.5 * np.sin((U * 40 + g * 6) * 2 * math.pi)
    col = TX.srgb(PAL['wood']) * (0.75 + 0.35 * rings)[..., None]
    return (TX.to_image('T_Wood_BaseColor', col), TX.to_image('T_Wood_Normal', TX.height_to_normal(rings * 0.5, 2.0), 'Non-Color'))


def build_materials(lm, body, eyes):
    import elara_face as EF
    sk = paint_skin(body, lm)
    tn = paint_tunic(); ck = paint_cloak(); le = paint_leather(); hr = paint_hair(); kn = paint_knit(); wd = paint_wood()
    M = {}
    M['Skin'] = pbr('M_Elara_Skin', sk[0], sk[1], sk[2], subsurface=0.18, sss_scale=0.006, normal_strength=0.35)
    M['Leggings'] = pbr('M_Elara_Leggings', kn[0], kn[1], rough=0.85, uv_scale=10, sheen=0.3)
    M['Tunic'] = pbr('M_Elara_Tunic', tn[0], tn[1], tn[2], sheen=0.25)
    M['Cloak'] = pbr('M_Elara_Cloak', ck[0], ck[1], ck[2], sheen=0.4)
    M['CloakLining'] = pbr('M_Elara_CloakLining', ck[3], ck[1], rough=0.8, sheen=0.3)
    M['CloakTrim'] = pbr('M_Elara_CloakTrim', lin(PAL['gold']), rough=0.45, metal=0.6)
    M['Leather'] = pbr('M_Elara_Leather', le[0], le[1], le[2])
    M['LeatherDark'] = pbr('M_Elara_LeatherDark', lin(PAL['leather_dark']), le[1], rough=0.6)
    M['Brass'] = pbr('M_Elara_Brass', lin(PAL['brass']), rough=0.32, metal=1.0)
    M['Wood'] = pbr('M_Elara_Wood', wd[0], wd[1], rough=0.45, coat=0.3)
    M['Hair'] = pbr('M_Elara_Hair', hr[0], hr[1], hr[2], aniso=0.6, sheen=0.2)
    M['HairCap'] = pbr('M_Elara_HairCap', lin('#5a2010'), rough=0.6)
    M['Flower'] = pbr('M_Elara_Flower', lin(PAL['flower']), rough=0.45, subsurface=0.2, sss_scale=0.002)
    M['Lashes'] = pbr('M_Elara_Lashes', lin('#2a170e'), rough=0.6)
    for e in eyes:
        img = EF.eye_texture(e)
        M[e.name] = pbr(f'M_{e.name}', img, rough=0.06, coat=1.0)
    return M
