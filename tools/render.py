"""Procedural product renderer for the Ti22 titanium shaker.

Renders surfaces of revolution (defined by 2D profiles) with an anisotropic
brushed-metal shader lit by a synthetic studio environment, then composites
a soft contact shadow. Output is transparent PNG/WebP so the site can place
renders on any background.

    python3 tools/render.py            # renders everything into assets/img
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "img")
RNG = np.random.default_rng(22)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ---------------------------------------------------------------- geometry


def arc(cx, cy, rad, a0, a1, n=24):
    """Points (r, h) on a quarter/partial circle, angles in degrees."""
    return [(cx + rad * math.cos(math.radians(a)), cy + rad * math.sin(math.radians(a)))
            for a in np.linspace(a0, a1, n)]


def resample(profile, n):
    """Resample a polyline profile to n points evenly spaced by arc length."""
    p = np.array(profile, dtype=np.float64)
    seg = np.sqrt(((p[1:] - p[:-1]) ** 2).sum(1))
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, s[-1], n)
    r = np.interp(t, s, p[:, 0])
    h = np.interp(t, s, p[:, 1])
    return r, h, s[-1]


BODY = (
    [(0.0, 0.0), (0.86, 0.0)]
    + arc(0.86, 0.10, 0.10, -90, 0, 16)
    + [(0.965, 0.14), (1.0, 3.22)]
    + arc(0.97, 3.22, 0.03, 0, 90, 8)
    + [(0.965, 3.25)]
)
BODY_INNER = (
    [(0.965, 3.25), (0.935, 3.22), (0.935, 0.16)]
    + arc(0.835, 0.16, 0.10, 0, -90, 12)[1:]
    + [(0.0, 0.06)]
)
SEAL = [(0.965, 3.25), (0.99, 3.26), (0.99, 3.33), (0.965, 3.34)]
def bezier(p0, p1, p2, n=28):
    t = np.linspace(0, 1, n)[:, None]
    p = (1 - t) ** 2 * np.array(p0) + 2 * (1 - t) * t * np.array(p1) + t ** 2 * np.array(p2)
    return [tuple(q) for q in p]


LID = (
    [(0.97, 3.34)]
    + arc(0.975, 3.38, 0.035, -90, 0, 8)
    + [(1.01, 3.40), (1.01, 3.74)]
    + arc(0.95, 3.74, 0.06, 0, 70, 10)
    + bezier((0.97, 3.80), (0.78, 3.99), (0.50, 4.0))
    + [(0.47, 4.0)]
)
CAP_SEAM = [(0.47, 4.0), (0.46, 4.01), (0.46, 4.025), (0.45, 4.03)]
CAP = (
    [(0.45, 4.03), (0.45, 4.30)]
    + arc(0.39, 4.30, 0.06, 0, 90, 12)
    + [(0.0, 4.36)]
)


def sphere(cy, rad):
    return arc(0, cy, rad, -90, 90, 60)


# ---------------------------------------------------------------- materials

MATERIALS = {
    "raw":      dict(albedo=(0.82, 0.79, 0.745), spec=1.00, white=0.10, diffuse=0.10),
    "obsidian": dict(albedo=(0.13, 0.13, 0.14), spec=1.00, white=0.55, diffuse=0.03),
    "bronze":   dict(albedo=(0.86, 0.66, 0.46), spec=1.00, white=0.12, diffuse=0.08),
    "aurora":   dict(albedo=(0.40, 0.56, 0.76), spec=1.00, white=0.16, diffuse=0.08),
    "silicone": dict(albedo=(0.16, 0.16, 0.17), spec=0.35, white=0.6, diffuse=0.10, matte=True),
}

# ---------------------------------------------------------------- lighting


def gauss(x, w):
    return np.exp(-(x / w) ** 2)


def env(R, rough):
    """Synthetic studio: two vertical softboxes, rim strips, top light."""
    Rx, Ry, Rz = R
    psi = np.degrees(np.arctan2(Rx, Rz))  # 0 = back toward camera
    ey = Ry
    base = np.where(ey > 0, 0.10 + 0.22 * ey, 0.05 + 0.03 * ey)
    w = 1.0 + rough * 0.55
    vert = 1 / (1 + np.exp(-(ey + 0.55) * 10)) * (1 / (1 + np.exp((ey - 0.8) * 10)))
    key = 2.6 * gauss(psi + 34, 11 * w) * vert
    key_core = 1.4 * gauss(psi + 34, 4.5 * w) * vert
    fill = 1.0 * gauss(psi - 52, 9 * w) * vert
    front = 0.18 * gauss(psi, 30)
    rimL = 1.9 * gauss(psi + 116, 6 * w) * vert
    rimR = 1.6 * gauss(psi - 120, 5 * w) * vert
    top = 1.6 * np.clip((ey - 0.5) / 0.5, 0, 1) ** 1.4
    floor = 0.10 * gauss(ey + 0.9, 0.3)
    back = 1.1 * gauss(np.abs(psi) - 180, 55) * gauss(ey - 0.3, 0.35)
    return base + key + key_core + fill + front + rimL + rimR + top + floor + back


# ---------------------------------------------------------------- noise


def streak_noise(n, fine=1.0):
    """1D brushed streak noise: high-frequency grain with slow modulation."""
    a = RNG.standard_normal(n)
    k = np.ones(3) / 3
    a = np.convolve(a, k, "same")[:n]
    slow = np.convolve(RNG.standard_normal(n + 60), np.ones(61) / 61, "valid")[:n] * 4
    return (a * 0.7 * fine + slow * 0.3) / 1.0


# ---------------------------------------------------------------- renderer


class Scene:
    def __init__(self, W, H, scale, cx, cy, pitch=14):
        self.W, self.H = W, H
        self.scale, self.cx, self.cy = scale, cx, cy
        self.th = math.radians(pitch)
        self.depth = np.full(W * H, -1e9, dtype=np.float32)
        self.rgb = np.zeros((W * H, 3), dtype=np.float32)

    def add(self, profile, mat, y0=0.0, x0=0.0, z0=0.0, knurl=0, etch=None,
            brush="circ", n_h=None, n_phi=None, yaw=0.0, ao=1.0):
        m = MATERIALS[mat]
        sc = self.scale
        r_, h_, L = resample(profile, 2)
        n_h = n_h or int(L * sc * 1.6) + 8
        rr, hh, _ = resample(profile, n_h)
        # profile normals in (r,h) plane
        dr = np.gradient(rr)
        dh = np.gradient(hh)
        ln = np.sqrt(dr ** 2 + dh ** 2) + 1e-9
        nr, nh = dh / ln, -dr / ln
        n_phi = n_phi or int(2 * math.pi * max(rr.max(), 0.05) * sc * 1.3) + 64
        phi = np.linspace(-math.pi, math.pi, n_phi).astype(np.float32)

        grain_h = streak_noise(n_h)
        grain_p = streak_noise(n_phi)
        ct, st = math.cos(self.th), math.sin(self.th)
        d = np.array([0, -st, -ct], dtype=np.float32)

        # process in chunks along the profile to bound memory
        chunk = max(1, 3_000_000 // n_phi)
        for i0 in range(0, n_h, chunk):
            i1 = min(n_h, i0 + chunk)
            r = rr[i0:i1, None].astype(np.float32)
            h = hh[i0:i1, None].astype(np.float32)
            P = np.broadcast_to(phi[None, :] + yaw, (i1 - i0, n_phi))
            sp, cp = np.sin(P), np.cos(P)
            x = r * sp + x0
            z = r * cp + z0
            y = h + y0
            Nr = nr[i0:i1, None].astype(np.float32)
            Nh = nh[i0:i1, None].astype(np.float32)
            nphi = np.zeros_like(P)
            if knurl:
                nphi = 0.35 * np.sin(P * knurl) * (Nr > 0.9)
            Nx = Nr * sp + nphi * cp
            Nz = Nr * cp - nphi * sp
            Ny = np.broadcast_to(Nh, P.shape)
            nl = np.sqrt(Nx ** 2 + Ny ** 2 + Nz ** 2)
            Nx, Ny, Nz = Nx / nl, Ny / nl, Nz / nl

            # screen projection (orthographic, camera pitched down)
            Y = y * ct - z * st
            Dp = z * ct + y * st
            facing = (Nx * d[0] + Ny * d[1] + Nz * d[2]) < 0.02

            # reflection
            dn = Nx * d[0] + Ny * d[1] + Nz * d[2]
            Rx = d[0] - 2 * dn * Nx
            Ry = d[1] - 2 * dn * Ny
            Rz = d[2] - 2 * dn * Nz

            g = grain_h[i0:i1, None] if brush == "circ" else grain_p[None, :]
            g = np.broadcast_to(g, P.shape).astype(np.float32)
            rough = 1.0 + 0.18 * g
            if m.get("matte"):
                rough = rough + 3.0
            e = env((Rx, Ry, Rz), rough) * m["spec"]
            fres = 0.85 + 0.15 * (1 - np.abs(dn)) ** 3

            etch_mask = 0.0
            if etch is not None:
                tex, (pa, pb, ha, hb) = etch
                u = ((P - pa) / (pb - pa) * (tex.shape[1] - 1))
                v = ((hb - h) / (hb - ha) * (tex.shape[0] - 1))
                inside = (u >= 0) & (u < tex.shape[1] - 1) & (v >= 0) & (v < tex.shape[0] - 1)
                ui = np.clip(u, 0, tex.shape[1] - 1).astype(np.int32)
                vi = np.clip(np.broadcast_to(v, P.shape), 0, tex.shape[0] - 1).astype(np.int32)
                etch_mask = np.where(inside, tex[vi, ui], 0.0)

            alb = np.array(m["albedo"], dtype=np.float32)
            wmix = m["white"]
            lum = e * fres * (1 + 0.035 * g) * ao
            # laser etch: matte and slightly darker
            lum = lum * (1 - 0.45 * etch_mask) + 0.30 * etch_mask
            diff = m["diffuse"] * (0.5 + 0.5 * np.clip(-(Nx * -0.5 + Ny * 0.6 + Nz * 0.6), 0, 1))
            hi = np.clip((lum - 0.75) / 0.8, 0, 1)[..., None]
            col = lum[..., None] * alb * (1 - hi * wmix) + lum[..., None] * hi * wmix + diff[..., None] * alb

            px = (self.cx + x * self.scale).astype(np.int32)
            py = (self.cy - Y * self.scale).astype(np.int32)
            ok = facing & (px >= 0) & (px < self.W) & (py >= 0) & (py < self.H)
            idx = (py * self.W + px)[ok]
            dep = Dp[ok].astype(np.float32)
            np.maximum.at(self.depth, idx, dep)
            win = dep >= self.depth[idx] - 1e-6
            self.rgb[idx[win]] = col[ok][win]

    def image(self, shadow=True, shadow_spots=((0, 0, 1.0),), out_scale=0.5):
        W, H = self.W, self.H
        cover = (self.depth > -1e8).reshape(H, W)
        # fill single-pixel holes
        m = Image.fromarray((cover * 255).astype(np.uint8))
        m = m.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
        cover2 = np.array(m) > 127
        rgb = self.rgb.reshape(H, W, 3)
        rgb_img = Image.fromarray(np.clip(tone(rgb) * 255, 0, 255).astype(np.uint8))
        # hole fill for rgb: dilate color from neighbours
        dil = rgb_img.filter(ImageFilter.MaxFilter(3))
        holes = cover2 & ~cover
        arr = np.array(rgb_img)
        arr[holes] = np.array(dil)[holes]
        obj = np.dstack([arr, (cover2 * 255).astype(np.uint8)])
        obj_img = Image.fromarray(obj, "RGBA")

        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if shadow:
            sh = Image.new("L", (W, H), 0)
            dr = ImageDraw.Draw(sh)
            for (sx, sy, k) in shadow_spots:
                gx = self.cx + sx * self.scale
                gy = self.cy + (-sy) * self.scale
                rw = 1.15 * self.scale * k
                rh = 0.22 * self.scale * k
                dr.ellipse([gx - rw, gy - rh, gx + rw, gy + rh * 0.9], fill=110)
            sh = sh.filter(ImageFilter.GaussianBlur(self.scale * 0.14))
            sh2 = Image.new("L", (W, H), 0)
            dr2 = ImageDraw.Draw(sh2)
            for (sx, sy, k) in shadow_spots:
                gx = self.cx + sx * self.scale
                gy = self.cy + (-sy) * self.scale
                rw = 0.98 * self.scale * k
                rh = 0.12 * self.scale * k
                dr2.ellipse([gx - rw, gy - rh, gx + rw, gy + rh * 0.6], fill=210)
            sh2 = sh2.filter(ImageFilter.GaussianBlur(self.scale * 0.035))
            sh = Image.fromarray(np.maximum(np.array(sh), np.array(sh2)))
            shadow_layer = Image.new("RGBA", (W, H), (18, 16, 14, 0))
            shadow_layer.putalpha(sh)
            canvas = Image.alpha_composite(canvas, shadow_layer)
        canvas = Image.alpha_composite(canvas, obj_img)
        if out_scale != 1:
            canvas = canvas.resize((int(W * out_scale), int(H * out_scale)), Image.LANCZOS)
        return canvas


def tone(x):
    x = np.maximum(x, 0)
    y = 1 - np.exp(-x * 1.35)
    return y ** (1 / 1.25)


def etch_texture(text, w=1400, h=260, size=190, sub=None):
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, size)
    bb = d.textbbox((0, 0), text, font=f)
    tw = bb[2] - bb[0]
    d.text(((w - tw) / 2 - bb[0], (h - (bb[3] - bb[1])) / 2 - bb[1] - (20 if sub else 0)),
           text, font=f, fill=255)
    if sub:
        f2 = ImageFont.truetype(FONT, 34)
        bb2 = d.textbbox((0, 0), sub, font=f2)
        d.text(((w - (bb2[2] - bb2[0])) / 2, h - 50), sub, font=f2, fill=255)
    return np.array(img).astype(np.float32) / 255.0


ETCH = etch_texture("Ti22", w=1000, h=330, size=200, sub="GRADE 5 TITANIUM  ·  750 ML")


def shaker(scene, finish, x0=0.0, z0=0.0, y0=0.0, lift=0.0, cap_lift=0.0, yaw=0.0, etch=True):
    e = (ETCH, (-0.46, 0.46, 1.85, 2.155)) if etch else None
    scene.add(BODY, finish, x0=x0, z0=z0, y0=y0, etch=e, yaw=yaw)
    scene.add(SEAL, "silicone", x0=x0, z0=z0, y0=y0 + lift * 0.5)
    scene.add(LID, finish, x0=x0, z0=z0, y0=y0 + lift, knurl=0)
    scene.add(CAP_SEAM, "silicone", x0=x0, z0=z0, y0=y0 + lift + cap_lift * 0.5)
    scene.add(CAP, finish, x0=x0, z0=z0, y0=y0 + lift + cap_lift, knurl=90)


def save(img, name, webp=True):
    path = os.path.join(OUT, name)
    img.save(path + ".webp", "WEBP", quality=90, method=6)
    print("wrote", path + ".webp", img.size)


def render_single(finish, name, W=1800, H=2400):
    # render at 2x then downsample
    S = 2
    sc = Scene(W * S, H * S, scale=430 * S, cx=W * S / 2, cy=H * S * 0.90, pitch=14)
    shaker(sc, finish)
    save(sc.image(), name)


def render_exploded():
    W, H, S = 1600, 2400, 2
    sc = Scene(W * S, H * S, scale=300 * S, cx=W * S / 2, cy=H * S * 0.93, pitch=18)
    shaker(sc, "raw", lift=1.7, cap_lift=0.9)
    # mixing orb floating between body and seal
    sc.add(sphere(3.67, 0.30), "raw", brush="lin")
    save(sc.image(), "exploded")


def render_trio():
    W, H, S = 2600, 1700, 2
    sc = Scene(W * S, H * S, scale=265 * S, cx=W * S / 2, cy=H * S * 0.88, pitch=12)
    spots = []
    for fin, x, z in (("obsidian", -2.35, -1.0), ("aurora", 2.35, -1.0), ("bronze", 0.0, -2.6),
                      ("raw", 0.0, 0.6)):
        pass
    # draw back-to-front order does not matter (z-buffer)
    shaker(sc, "bronze", x0=-2.3, z0=-1.2)
    shaker(sc, "aurora", x0=2.3, z0=-1.2)
    shaker(sc, "obsidian", x0=0.0, z0=0.7)
    ct, st = math.cos(math.radians(12)), math.sin(math.radians(12))
    for x, z in ((-2.3, -1.2), (2.3, -1.2), (0.0, 0.7)):
        spots.append((x, -z * st, 1.0))
    save(sc.image(shadow_spots=spots), "trio")


def render_macro():
    """Tight crop of lid/body seam with the knurled cap for a detail shot."""
    W, H, S = 1600, 1200, 2
    sc = Scene(W * S, H * S, scale=800 * S, cx=W * S * 0.5, cy=H * S * 0.5 + 3.35 * 800 * S, pitch=24)
    shaker(sc, "raw")
    img = sc.image(shadow=False)
    save(img, "macro")


def render_hero_pair():
    W, H, S = 2000, 2200, 2
    sc = Scene(W * S, H * S, scale=400 * S, cx=W * S / 2, cy=H * S * 0.9, pitch=13)
    shaker(sc, "raw", x0=-0.72, z0=0.35)
    shaker(sc, "obsidian", x0=1.25, z0=-0.9)
    st = math.sin(math.radians(13))
    save(sc.image(shadow_spots=((-0.72, -0.35 * st, 1.0), (1.25, 0.9 * st, 1.0))), "hero-pair")


if __name__ == "__main__":
    import sys
    os.makedirs(OUT, exist_ok=True)
    jobs = sys.argv[1:] or ["raw", "obsidian", "bronze", "aurora", "exploded", "trio", "macro", "pair"]
    for j in jobs:
        if j in ("raw", "obsidian", "bronze", "aurora"):
            render_single(j, f"shaker-{j}")
        elif j == "exploded":
            render_exploded()
        elif j == "trio":
            render_trio()
        elif j == "macro":
            render_macro()
        elif j == "pair":
            render_hero_pair()
