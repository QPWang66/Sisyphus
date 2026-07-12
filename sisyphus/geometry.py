"""Scene geometry: the slope, the summit, and small vector helpers."""
import math

W, H = 440, 280
R = 17                       # boulder mean radius, everything scales off it

BASE = (W * 0.13, H * 0.82)  # far enough in that a heavy boulder + glow stays inside
SUMMIT = (W * 0.80, H * 0.24)
_dx, _dy = SUMMIT[0] - BASE[0], SUMMIT[1] - BASE[1]
DL = math.hypot(_dx, _dy)             # base→summit distance
DIR = (_dx / DL, _dy / DL)            # uphill
NRM = (DIR[1], -DIR[0])               # off the slope, upward

# rugged slope: (t along base→summit, offset along NRM in px), piecewise-linear
BUMPS = ((0.00, 0), (0.08, 3), (0.16, -2.5), (0.26, 4), (0.34, -2), (0.45, 5),
         (0.55, -3), (0.66, 3.5), (0.76, -2), (0.88, 3), (1.00, 0))
FAR1 = ((W * 0.02, H * 0.52), (W * 0.13, H * 0.42), (W * 0.22, H * 0.47),
        (W * 0.35, H * 0.35), (W * 0.46, H * 0.43))          # distant ridges
FAR2 = ((W * 0.52, H * 0.34), (W * 0.64, H * 0.24), (W * 0.73, H * 0.30),
        (W * 0.86, H * 0.17), (W * 0.99, H * 0.27))


def A(a, b): return (a[0] + b[0], a[1] + b[1])
def M(v, s): return (v[0] * s, v[1] * s)
def LV(a, b, t): return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
def lerp(a, b, t): return a + (b - a) * t
def clamp(v, lo, hi): return max(lo, min(hi, v))
def ease(t): return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2
def slope(t): return LV(BASE, SUMMIT, t)


def terrain(t):
    """Point on the rugged ground at t ∈ [0,1]."""
    t = clamp(t, 0.0, 1.0)
    for (t0, o0), (t1, o1) in zip(BUMPS, BUMPS[1:]):
        if t <= t1:
            return A(slope(t), M(NRM, lerp(o0, o1, (t - t0) / (t1 - t0))))
    return slope(t)


def project(x, y):
    """Mouse point → t along the slope."""
    return clamp(((x - BASE[0]) * DIR[0] + (y - BASE[1]) * DIR[1]) / DL, 0.0, 0.99)


def catmull(pts, seg=6):
    """Catmull-Rom resample through pts — the flowing spine of every brush stroke."""
    if len(pts) < 3:
        return list(pts)
    p = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(len(p) - 3):
        p0, p1, p2, p3 = p[i], p[i + 1], p[i + 2], p[i + 3]
        for j in range(seg):
            u = j / seg
            u2, u3 = u * u, u * u * u
            out.append(tuple(
                0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * u
                       + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * u2
                       + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * u3)
                for k in (0, 1)))
    out.append(pts[-1])
    return out
