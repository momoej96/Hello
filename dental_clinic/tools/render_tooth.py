"""يرسم أيقونة السن ثلاثية الأبعاد (tooth.ico و static/icon.png). للمطور فقط، يحتاج numpy و Pillow.
Raymarch a 3D molar (signed distance field) and save PNG + multi-size ICO.
Usage: python tools/render_tooth.py out/tooth 1024
"""
import sys
import numpy as np
from PIL import Image, ImageFilter

OUT = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 1024


def length(v):
    return np.sqrt(np.sum(v * v, axis=-1))


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b + (a - b) * h - k * h * (1 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def sd_roundbox(p, b, r):
    q = np.abs(p) - b
    return length(np.maximum(q, 0)) + np.minimum(np.max(q, axis=-1), 0) - r


def sd_ellipsoid(p, r):
    k0 = length(p / r)
    k1 = length(p / (r * r))
    return k0 * (k0 - 1) / np.maximum(k1, 1e-6)


def sd_capsule(p, a, b, r):
    pa, ba = p - a, b - a
    h = np.clip(np.sum(pa * ba, -1) / np.dot(ba, ba), 0, 1)
    return length(pa - ba * h[..., None]) - r


def sd_roundcone(p, a, b, r1, r2):
    # exact tapered capsule (Inigo Quilez)
    ba = b - a
    l2 = np.dot(ba, ba)
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pa = p - a
    y = np.sum(pa * ba, -1)
    z = y - l2
    xv = pa * l2 - y[..., None] * ba
    x2 = np.sum(xv * xv, -1)
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    out = (np.sqrt(x2 * a2 * il2) + y * rr) * il2 - r1
    out = np.where(np.sign(z) * a2 * z2 > k, np.sqrt(x2 + z2) * il2 - r2, out)
    out = np.where(np.sign(y) * a2 * y2 < k, np.sqrt(x2 + y2) * il2 - r1, out)
    return out


V = np.array


def tooth(p):
    # crown: bulbous body + four rounded cusps
    crown = sd_ellipsoid(p - V([0, 0.40, 0]), V([0.62, 0.34, 0.54]))
    for sx in (-1, 1):
        for sz in (-1, 1):
            c = sd_ellipsoid(p - V([sx * 0.25, 0.62, sz * 0.21]), V([0.31, 0.27, 0.29]))
            crown = smin(crown, c, 0.14)
    # occlusal fissures (cross-shaped grooves between cusps)
    g = np.minimum(sd_capsule(p, V([-0.40, 0.90, 0]), V([0.40, 0.90, 0]), 0.045),
                   sd_capsule(p, V([0, 0.90, -0.34]), V([0, 0.90, 0.34]), 0.045))
    crown = smax(crown, -g, 0.08)
    # neck (cervical constriction)
    neck = sd_ellipsoid(p - V([0, 0.10, 0]), V([0.46, 0.22, 0.40]))
    body = smin(crown, neck, 0.14)
    # roots: two flattened, curved, tapering roots (tips bend slightly inward)
    q = p * V([1, 1, 1.2])
    for sx in (-1, 1):
        pts = [V([sx * 0.25, 0.05, 0]), V([sx * 0.34, -0.30, 0.0]), V([sx * 0.31, -0.62, 0.03]), V([sx * 0.20, -0.86, 0.05])]
        rad = [0.23, 0.18, 0.12, 0.05]
        # smooth curve through the control points, many short segments -> no visible seams
        P, Rr = np.array(pts), np.array(rad)
        ts = np.linspace(0, 3, 13)
        cp = np.array([np.interp(ts, range(4), P[:, j]) for j in range(3)]).T
        cr = np.interp(ts, range(4), Rr)
        cp[1:-1] = (cp[:-2] + 2 * cp[1:-1] + cp[2:]) / 4  # soften corners
        r = None
        for i in range(12):
            d = sd_roundcone(q, cp[i], cp[i + 1], cr[i], cr[i + 1])
            r = d if r is None else smin(r, d, 0.04)
        body = smin(body, r / 1.2, 0.16)
    return body


def rot(yaw, pitch):
    cy, sy, cp, sp = np.cos(yaw), np.sin(yaw), np.cos(pitch), np.sin(pitch)
    ry = V([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rx = V([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    rz = V([[np.cos(0.17), -np.sin(0.17), 0], [np.sin(0.17), np.cos(0.17), 0], [0, 0, 1]])
    return rz @ ry @ rx


def main():
    R = rot(np.radians(-24), np.radians(-22))  # world -> object
    ys, xs = np.mgrid[0:N, 0:N]
    u = (xs + 0.5) / N * 2 - 1
    v = -((ys + 0.5) / N * 2 - 1)
    cam = V([0, 0.02, 6.0])
    dirs = np.stack([u * 0.36, v * 0.36 - 0.0, -np.ones_like(u)], -1)
    dirs /= length(dirs)[..., None]
    ro = (cam @ R.T) * 0 + cam  # camera in world
    ro_o = ro @ R              # to object space (R orthonormal)
    rd_o = dirs @ R
    shape = u.shape
    rd = rd_o.reshape(-1, 3)
    t = np.full(rd.shape[0], 4.0)
    hit = np.zeros(rd.shape[0], bool)
    alive = np.ones(rd.shape[0], bool)
    mind = np.full(rd.shape[0], 9.0)
    for _ in range(160):
        idx = np.nonzero(alive)[0]
        if idx.size == 0:
            break
        p = ro_o + rd[idx] * t[idx, None]
        d = tooth(p)
        mind[idx] = np.minimum(mind[idx], d)
        t[idx] += d * 0.9
        h = d < 1e-4
        hit[idx[h]] = True
        alive[idx[h]] = False
        alive[idx[t[idx] > 8.0]] = False

    rgba = np.zeros((rd.shape[0], 4))
    idx = np.nonzero(hit)[0]
    p = ro_o + rd[idx] * t[idx, None]
    e = 1e-3
    n = np.stack([tooth(p + V([e, 0, 0])) - tooth(p - V([e, 0, 0])),
                  tooth(p + V([0, e, 0])) - tooth(p - V([0, e, 0])),
                  tooth(p + V([0, 0, e])) - tooth(p - V([0, 0, e]))], -1)
    n /= length(n)[..., None]
    # back to world/view space for lighting
    nw = n @ R.T
    vdir = -dirs.reshape(-1, 3)[idx]

    ao = np.ones(idx.size)
    for i in range(1, 6):
        hh = 0.04 * i
        ao -= (hh - tooth(p + n * hh)) * (0.9 / i)
    ao = np.clip(ao, 0, 1) ** 1.2

    def L(x):
        x = V(x, float); return x / np.linalg.norm(x)
    key, fill, rim = L([-0.6, 0.8, 0.7]), L([0.8, 0.1, 0.5]), L([0.3, 0.4, -1.0])
    wrap = lambda l, w: np.clip((nw @ l + w) / (1 + w), 0, 1)

    py = p[:, 1]
    k = np.clip((py + 0.02) / 0.30, 0, 1)  # 1 = enamel crown, 0 = root
    k = k * k * (3 - 2 * k)
    enamel = V([0.97, 0.965, 0.94])
    root = V([0.96, 0.87, 0.70])
    alb = root * (1 - k[:, None]) + enamel * k[:, None]
    sss = V([1.0, 0.86, 0.74])  # warm scatter tint in shadowed areas

    dif = wrap(key, 0.35)[:, None] * V([1.0, 0.98, 0.95]) * 0.82 \
        + wrap(fill, 0.5)[:, None] * V([0.75, 0.85, 1.0]) * 0.35
    amb = (0.18 + 0.10 * nw[:, 1:2]) * V([0.85, 0.92, 1.0])
    col = alb * (dif + amb) * ao[:, None]
    col += alb * sss * (1 - wrap(key, 0.0))[:, None] * 0.12 * ao[:, None]
    hv = key + vdir; hv /= length(hv)[..., None]
    spec = np.clip(np.sum(nw * hv, -1), 0, 1) ** 70 * (0.25 + 0.75 * k)
    hv2 = fill + vdir; hv2 /= length(hv2)[..., None]
    spec += np.clip(np.sum(nw * hv2, -1), 0, 1) ** 40 * 0.25 * k
    fres = (1 - np.clip(np.sum(nw * vdir, -1), 0, 1)) ** 3
    col += spec[:, None] * 0.9
    col += (fres * (0.35 + 0.65 * np.clip(nw @ rim + 0.3, 0, 1)))[:, None] * V([0.55, 0.78, 1.0]) * 0.45
    col = col / (1 + 0.25 * col) * 1.12  # gentle tone map
    col = np.clip(col, 0, 1) ** (1 / 1.1)
    rgba[idx, :3] = col
    rgba[idx, 3] = 1
    img = (rgba.reshape(shape + (4,)) * 255 + 0.5).astype(np.uint8)
    tooth_img = Image.fromarray(img, 'RGBA')

    # soft drop shadow so the white tooth stays visible on light wallpapers
    a = tooth_img.split()[3]
    sh = Image.new('RGBA', tooth_img.size, (10, 40, 80, 0))
    sh.putalpha(a.point(lambda x: x * 0.55))
    sh = sh.filter(ImageFilter.GaussianBlur(N * 0.018))
    canvas = Image.new('RGBA', tooth_img.size, (0, 0, 0, 0))
    canvas.alpha_composite(sh, (int(N * 0.012), int(N * 0.028)))
    canvas.alpha_composite(tooth_img)

    bbox = canvas.getbbox()
    crop = canvas.crop(bbox)
    side = int(max(crop.size) * 1.04)
    sq = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    sq.alpha_composite(crop, ((side - crop.size[0]) // 2, (side - crop.size[1]) // 2))
    big = sq.resize((256, 256), Image.LANCZOS)
    big.save(OUT + '.png')
    sq.resize((512, 512), Image.LANCZOS).save(OUT + '_512.png')
    big.save(OUT + '.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


main()
