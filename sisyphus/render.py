"""Offscreen PIL rendering: calligraphic brush strokes with a real glow.

Everything is drawn 2x supersampled on two layers — a bright core and a
wider ink layer that gets gaussian-blurred into the glow — then composited
and downscaled. `render(sim, stats)` is a pure function of the sim state.
"""
import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .geometry import (A, BASE, BUMPS, DL, DIR, FAR1, FAR2, H, LV, M, NRM, R,
                       SUMMIT, W, catmull, clamp, lerp, terrain)

SS = 2                       # supersample factor
SEASONS = ((150, 200, 120),  # spring — tender green
           (224, 170, 100),  # summer — vintage amber
           (210, 122, 66),   # autumn — rust
           (172, 196, 212))  # winter — pale ice
INK = list(SEASONS[1])       # current ink, eased toward the season each frame
WHITE = (255, 243, 216)      # warm white for stroke cores
DARKINK = (46, 30, 14)       # deep ink for bright wallpapers
BG_LIGHT = [0.0]             # wallpaper brightness under the window, 0=dark 1=bright


def _ink(alpha):
    alpha *= lerp(1.0, 0.45, clamp(BG_LIGHT[0], 0, 1))  # less halo on bright bg
    return (int(INK[0]), int(INK[1]), int(INK[2]), int(255 * clamp(alpha, 0, 1)))


def _core(alpha):
    # glowing warm-white cores on a dark wallpaper; deep calligraphy ink on a
    # bright one — blended continuously by measured background brightness
    lite = clamp(BG_LIGHT[0], 0, 1)
    r, g, b = (round(lerp(lerp(i, w, 0.85), d, lite))
               for i, w, d in zip(INK, WHITE, DARKINK))
    return (r, g, b, int(255 * clamp(alpha, 0, 1)))


class Frame:
    def __init__(self):
        size = (W * SS, H * SS)
        self.core = Image.new("RGBA", size)
        self.glow = Image.new("RGBA", size)
        self.dc = ImageDraw.Draw(self.core)
        self.dg = ImageDraw.Draw(self.glow)

    def out(self, dim=1.0, out_scale=1):
        img = Image.alpha_composite(
            self.glow.filter(ImageFilter.GaussianBlur(2.6 * SS)), self.core)
        # a soft dark shade under everything: keeps the glow legible on a
        # bright wallpaper, nearly invisible on a dark one
        a = img.getchannel("A").filter(ImageFilter.GaussianBlur(4.0 * SS))
        under = Image.new("RGBA", img.size, (16, 11, 6, 255))
        k = lerp(1.2, 0.55, clamp(BG_LIGHT[0], 0, 1))   # bright bg: the ink
        under.putalpha(a.point(lambda v: min(235, int(v * k))))  # itself carries
        # contrast, so the shade eases off; dark bg: shade stays subtle too
        img = Image.alpha_composite(under, img)
        if out_scale != SS:                     # HiDPI callers take SS-res as-is
            img = img.resize((W * out_scale, H * out_scale), Image.LANCZOS)
        if dim < 1.0:
            img.putalpha(img.getchannel("A").point(lambda v: int(v * dim)))
        return img


def brush(f, pts, w, alpha, tip=0.22):
    """A calligraphic stroke: sharp entry, full belly, flying exit."""
    line_pts = catmull(pts)
    n = len(line_pts)
    if n < 3:
        return
    left, right = [], []
    for i, p in enumerate(line_pts):
        q = line_pts[min(i + 1, n - 1)] if i < n - 1 else line_pts[i - 1]
        tx, ty = (q[0] - p[0], q[1] - p[1]) if i < n - 1 else (p[0] - q[0], p[1] - q[1])
        tl = math.hypot(tx, ty) or 1
        nx, ny = -ty / tl, tx / tl
        u = i / (n - 1)
        prof = (min(1, u / tip) ** 0.6) * (min(1, (1 - u) / tip) ** 0.45)
        hw = max(0.3, w * prof * (0.75 + 0.45 * math.sin(math.pi * u))) * SS / 2
        left.append((p[0] * SS + nx * hw, p[1] * SS + ny * hw))
        right.append((p[0] * SS - nx * hw, p[1] * SS - ny * hw))
    poly = left + right[::-1]
    f.dg.polygon(poly, fill=_ink(min(1.0, alpha * 0.9)))
    f.dc.polygon(poly, fill=_core(min(1.0, alpha * 1.15)))


def line(f, pts, w, alpha, closed=False, glow=True):
    sp = [(p[0] * SS, p[1] * SS) for p in pts]
    if closed:
        sp.append(sp[0])
    if glow:
        f.dg.line(sp, fill=_ink(min(1.0, alpha * 0.85)), width=int(w * SS * 1.8),
                  joint="curve")
    f.dc.line(sp, fill=_core(min(1.0, alpha * 1.15)), width=max(1, int(w * SS)),
              joint="curve")


def dot(f, p, r, alpha):
    x, y = p[0] * SS, p[1] * SS
    rr = r * SS
    f.dg.ellipse((x - rr * 2, y - rr * 2, x + rr * 2, y + rr * 2), fill=_ink(alpha * 0.4))
    f.dc.ellipse((x - rr, y - rr, x + rr, y + rr), fill=_core(alpha))


_FONT = None


def _font():
    global _FONT
    if _FONT is None:
        for p in ("/System/Library/Fonts/PingFang.ttc",              # macOS
                  "/System/Library/Fonts/Hiragino Sans GB.ttc",
                  "C:/Windows/Fonts/segoeui.ttf",                    # Windows
                  "C:/Windows/Fonts/arial.ttf"):
            try:
                _FONT = ImageFont.truetype(p, 11 * SS)
                break
            except OSError:
                continue
        else:
            _FONT = ImageFont.load_default()
    return _FONT


def draw_season(f, sim):
    """Seasonal touches on random laps — sprouts / fireflies / a leaf / snow."""
    t, s = sim.clock, sim.season
    if s == 0:      # spring — a few sprouts swaying on the slope
        for i, sp in enumerate(sim.spots):
            base = terrain(sp)
            sw = math.sin(t * 1.3 + sim.ph[i]) * 3
            tp = A(A(base, M(NRM, 9 + 2 * math.sin(t + i))), (sw, 0))
            mid = A(LV(base, tp, 0.55), (sw * 0.5, 0))
            brush(f, [base, mid, tp], 1.8, 0.7, tip=0.4)
    elif s == 1:    # summer — two or three fireflies, blinking
        for i, sp in enumerate(sim.spots):
            p = A(terrain(sp), (math.sin(t * 0.7 + sim.ph[i]) * 16,
                                -18 - 8 * math.sin(t * 0.53 + sim.ph[i] * 2)))
            a = max(0.0, math.sin(t * 1.1 + sim.ph[i] * 3))
            if a > 0.05:
                dot(f, p, 1.1, 0.25 + 0.6 * a)
    elif s == 2:    # autumn — now and then a leaf spirals down
        for i, sp in enumerate(sim.spots[:2]):
            fl = (t * 0.09 + sim.ph[i]) % 1.0
            p = A(terrain(sp), (math.sin(t * 1.7 + sim.ph[i]) * 10, -70 + fl * 85))
            ang = t * 2 + sim.ph[i]
            d = (math.cos(ang) * 3.5, math.sin(ang) * 1.8)
            brush(f, [A(p, M(d, -1)), p, A(p, d)], 2.2, 0.7, tip=0.5)
    else:           # winter — sparse snow
        for i in range(8):
            ph = sim.ph[i % len(sim.ph)] + i * 1.7
            fl = (t * (0.05 + 0.012 * (i % 3)) + ph * 0.13) % 1.0
            x = (ph * 61.8) % W
            dot(f, (x + math.sin(t * 0.8 + ph) * 6, fl * H), 0.9, 0.5)


def draw_ground(f, sim):
    line(f, FAR1, 1.2, 0.10, glow=False)                       # distant, silent
    line(f, FAR2, 1.2, 0.08, glow=False)
    pts = [A(BASE, (-30, 12)), A(BASE, (-14, 5))]
    pts += [terrain(t) for t, _ in BUMPS]
    for d in ((10, 9), (20, 13), (30, 26), (46, 33), (62, 52)):  # jagged far side
        pts.append(A(SUMMIT, d))
    line(f, pts, 1.6, 0.5)
    if sim.windy and sim.state in ("TOP", "ROLL", "WATCH"):    # wind at the crest
        t = sim.clock
        wp = [A(A(SUMMIT, (-30 + i * 9, -16 - i * 1.5)),
                (0, math.sin(t * 3 + i * 0.9) * 2.5)) for i in range(9)]
        line(f, wp, 1.0, 0.10 + 0.08 * math.sin(t * 1.7), glow=False)


def draw_meteor(f, ev):
    """A meteor over the far ridge. He watches. Then back to work."""
    p = ev["p"]
    a, b = (W * 0.12, H * 0.10), (W * 0.82, H * 0.30)
    pos = LV(a, b, p)
    fade = min(1.0, 4 * p, 4 * (1 - p))
    for i in range(5):                                         # the tail
        q = LV(a, b, max(0.0, p - 0.03 * (i + 1)))
        dot(f, q, 1.0 - i * 0.15, 0.5 * fade * (1 - i / 5))
    dot(f, pos, 1.5, 0.95 * fade)


def draw_bird(f, sim):
    """A small bird: lands on the boulder, will not be touched."""
    ph, t = sim.bird["ph"], sim.bird["t"]
    bc = A(terrain(sim.ball_t), M(NRM, R * sim.rock))
    perch = A(bc, M(NRM, R * sim.rock * 0.95))
    if ph == "in":
        p = 1 - (1 - min(1, t / 1.2)) ** 2
        pos, flap = LV(A(perch, (130, -80)), perch, p), math.sin(t * 16) * 0.8
    elif ph == "perch":
        pos, flap = A(perch, (0, math.sin(t * 2.2) * 0.6)), 0.12
    else:
        p = (min(1, t / 1.2)) ** 1.5
        pos, flap = LV(perch, A(perch, (150, -110)), p), math.sin(t * 18) * 0.9
    s = R * 0.24
    for sgn in (-1, 1):
        wing = (pos[0] + sgn * s * 1.5,
                pos[1] - s * (0.15 + 0.85 * abs(flap)) * (1 if sgn * flap >= 0 else 0.4))
        line(f, [pos, wing], 1.1, 0.7, glow=False)
    dot(f, pos, 1.0, 0.65)


def draw_companion(f, ev, clock):
    """Another one, far away on another ridge, pushing another boulder."""
    p = ev["p"]
    seg = p * (len(FAR1) - 1)
    i = min(int(seg), len(FAR1) - 2)
    pos = LV(FAR1[i], FAR1[i + 1], seg - i)
    d = (FAR1[i + 1][0] - FAR1[i][0], FAR1[i + 1][1] - FAR1[i][1])
    dl = math.hypot(*d) or 1
    d = (d[0] / dl, d[1] / dl)
    n = (d[1], -d[0])
    a = 0.38 * min(1.0, 6 * p, 6 * (1 - p))                    # fades in and out
    rr = 4.5
    ball = A(A(pos, M(d, rr * 1.6)), M(n, rr))
    line(f, [A(ball, (math.cos(clock + i) * rr, math.sin(clock + i) * rr))
             for i in range(6)], 1.0, a, closed=True, glow=False)
    hip = A(pos, M(n, 5.5))
    head = A(A(hip, M(n, 5.0)), M(d, 2.5))
    line(f, [A(pos, M(d, -2)), hip, head], 1.2, a, glow=False)  # a bent little figure
    dot(f, A(head, M(d, 1.2)), 0.9, a)


BOULDER_RADII = (1.0, 0.86, 1.08, 0.92, 1.12, 0.84, 1.05, 0.90, 1.10, 0.88)


def boulder_pts(center, theta, scale=1.0):
    n = len(BOULDER_RADII)
    return [A(center, (math.cos(theta + i * math.tau / n) * R * rr * scale,
                       math.sin(theta + i * math.tau / n) * R * rr * scale))
            for i, rr in enumerate(BOULDER_RADII)]


def draw_boulder(f, sim, center, theta):
    rk = sim.rock
    for bt, age in sim.trail:                                  # rolling afterimages
        c = A(terrain(bt), M(NRM, R * rk))
        line(f, boulder_pts(c, theta + (bt - sim.ball_t) * DL / (R * rk), rk),
             1.2, 0.16 * (1 - age / 0.5), closed=True, glow=False)
    pts = boulder_pts(center, theta, rk)
    line(f, pts, R * 0.10 * rk, 0.95, closed=True)             # the rock, angular
    line(f, [LV(pts[2], center, 0.15), LV(pts[2], center, 0.55)],
         1.2, 0.30, glow=False)                                # one crack, no more
    for pos, age in sim.dust:                                  # impact dust
        x, y, vx, vy = pos
        kk = age * (1 - age * 0.5)
        dot(f, (x + vx * kk, y + vy * kk), 1.0, 0.5 * (1 - age / 0.8))


def draw_figure(f, sim, feet, ball_c):
    e, t, fc, fl = sim.effort, sim.clock, sim.face, sim.fallen
    q, ch = sim.sit, sim.chaos
    up0 = (fc * math.sin(sim.lean), -math.cos(sim.lean))
    up = LV(up0, DIR, fl * 0.85)                               # fallen: torso to the ground
    ul = math.hypot(*up) or 1
    up = (up[0] / ul, up[1] / ul)
    fwd = M(DIR, fc)
    shrink = 1 - 0.45 * fl
    torso_len, head_r = R * 1.05 * shrink, R * 0.40
    leg_len = R * 1.15 * shrink * (1 - 0.06 * abs(math.cos(sim.walk)))
    trem = M((math.sin(t * 34) * R * 0.02 * e, math.sin(t * 29 + 1.7) * R * 0.02 * e),
             1 + 1.0 * ch)                                     # frantic typing shows
    breath = M(up, math.sin(t * 1.1 + sim.ph[0]) * R * 0.03 * (1 + 2 * fl))
    amp = R * 0.055 * (0.35 + 0.65 * e) * (1 + 0.6 * ch)

    hip = A(feet, M(up, leg_len * (1 - 0.7 * fl) * (1 - 0.55 * q)))  # sitting: low
    chest = A(A(A(hip, M(up, torso_len)), M(fwd, R * (0.18 * e + 0.10 * q))), trem)
    head_c = A(A(A(A(chest, M(up, head_r * 1.5)), M(fwd, R * 0.18 * e)), breath), trem)
    head_c = A(head_c, M(up, R * 0.18 * sim.rest))             # poked: he looks up
    if sim.blocked > 0.02 and sim.cursor:                      # blocked: he regards you
        dx, dy = sim.cursor[0] - head_c[0], sim.cursor[1] - head_c[1]
        dl_ = math.hypot(dx, dy) or 1
        head_c = A(head_c, (dx / dl_ * R * 0.16 * sim.blocked,
                            dy / dl_ * R * 0.16 * sim.blocked))

    stride, sw = R * 0.55 * (1 - fl) * (1 - 0.4 * q), math.sin(sim.walk)
    legs = []
    for i, sign in enumerate((1, -1)):
        s = sw * sign
        foot = A(A(feet, M(DIR, stride * s + fc * R * 0.35 * q)),
                 M(NRM, max(0, s) * R * 0.28 * (1 - fl) * (1 - q)))
        knee = A(A(LV(hip, foot, 0.5), M(fwd, R * (0.14 + 0.12 * e))),
                 A((math.sin(t * 3.1 + sim.ph[i]) * R * 0.04, 0),
                   M(NRM, R * 0.35 * q)))                      # sitting: knees up
        legs.append((knee, foot))

    def sway(pts, t0):
        out = [pts[0]]
        for i, p in enumerate(pts[1:-1], 1):
            ph = sim.ph[i % len(sim.ph)]
            out.append(A(p, (math.sin(t0 * 2.1 + ph + i * 1.3) * amp,
                             math.cos(t0 * 1.7 + ph + i * 0.9) * amp * 0.7)))
        out.append(pts[-1])
        return out

    # one flowing line: head base → bowed back → hip → trailing leg. one stroke.
    belly = A(LV(hip, chest, 0.5), M(fwd, R * 0.34 * e))
    body = [A(head_c, M(up, -head_r * 0.9)), chest, belly, hip] + list(legs[0])
    brush(f, sway(body, t), R * 0.30, 0.92, tip=0.12)
    brush(f, sway([hip] + list(legs[1]), t + 2.2), R * 0.24, 0.80, tip=0.2)

    # head — a wobbly organic loop, no face, never a perfect circle
    hpts = []
    for i in range(13):
        a = i * math.tau / 12
        rr = head_r * (1 + 0.10 * math.sin(3 * a + t * 1.6 + sim.ph[2])
                       + 0.05 * math.sin(5 * a - t))
        hpts.append(A(head_c, (math.cos(a) * rr, math.sin(a) * rr * 1.08)))
    line(f, hpts, R * 0.13, 0.95, closed=True)

    # arm — on the boulder while pushing, hanging loose otherwise
    hand_push = A(A(ball_c, M(DIR, -R * 0.55 * sim.rock)), M(NRM, R * 0.30 * sim.rock))
    hand_relax = A(A(chest, M(up, -torso_len * 0.45)), M(fwd, R * 0.1))
    hand = A(LV(hand_relax, hand_push, sim.push * (1 - fl)), trem)
    elbow = A(A(LV(chest, hand, 0.5), M(up, R * 0.18)),
              (math.sin(t * 2.6 + sim.ph[3]) * amp, 0))
    brush(f, sway([chest, elbow, hand], t + 4.1), R * 0.22, 0.80, tip=0.25)


def render(sim, stats=None, out_scale=1):
    """One full frame as a PIL RGBA image, W*out_scale × H*out_scale."""
    tgt = SEASONS[sim.season]
    for i in range(3):
        INK[i] += (tgt[i] - INK[i]) * 0.02      # the season fades in over ~2s
    f = Frame()
    draw_ground(f, sim)
    if sim.flourish:
        draw_season(f, sim)
    if sim.meteor:
        draw_meteor(f, sim.meteor)
    if sim.companion:
        draw_companion(f, sim.companion, sim.clock)
    feet = A(terrain(sim.fig_t), M(DIR, -R * (0.6 + sim.rock)))
    ball_c = A(terrain(sim.ball_t), M(NRM, R * sim.rock + sim.hop))
    if sim.prev_feet:
        d = math.hypot(feet[0] - sim.prev_feet[0], feet[1] - sim.prev_feet[1])
        sim.walk += d / (R * 0.9) * math.pi * (1 + 0.35 * sim.chaos)
    sim.prev_feet = feet
    draw_boulder(f, sim, ball_c, sim.ball_t * DL / (R * sim.rock))
    if sim.bird:
        draw_bird(f, sim)
    draw_figure(f, sim, feet, ball_c)
    if stats and sim.info > 0.02:                               # today's numbers
        txt = f"{stats.keys:,} keys today · boulder displacement: 0 m"
        f.dc.text((int(W * 0.06) * SS, int(H * 0.08) * SS), txt,
                  font=_font(), fill=_core(0.75 * sim.info))
    return f.out(sim.dim, out_scale)
