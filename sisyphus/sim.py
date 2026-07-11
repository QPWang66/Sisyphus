"""The state machine. Headless — no window needed, fully checkable.

States: ASCEND → TOP → ROLL → WATCH → RETURN → ASCEND, forever.
Extras: SLIP (a rare stumble mid-ascent), DRAG (a hand other than his
on the boulder). The boulder never passes top_t. Output is always zero.
"""
import math
import random
import time

from .geometry import clamp, ease, lerp, terrain

TOP_T = 0.85                                  # the ball never reaches the summit
DUR = {"TOP": 1.3, "ROLL": 1.5, "WATCH": 1.8, "RETURN": 5.5}
ASCEND_V0 = 0.135


class Sim:
    def __init__(self):
        self.state, self.st, self.clock = "ASCEND", 0.0, 0.0
        self.ball_t, self.fig_t = 0.0, 0.0
        self.lean, self.effort, self.push = 0.45, 0.6, 1.0
        self.face = 1.0                        # +1 uphill, -1 downhill
        self.pause, self.rest = 0.0, 0.0       # poked: stand still for a moment
        self.fallen = 0.0                      # 1 = flat on the ground (SLIP)
        self.info = 0.0                        # hover text fade
        self.walk, self.prev_feet = 0.0, None
        self.trail, self.dust = [], []         # rolling afterimages / impact dust
        self.roll_from, self.roll_dur = 0.0, 1.0
        self.ret_from, self.drag_t = 0.0, 0.0
        self._splashed = True
        self.season = ((time.localtime().tm_mon - 3) % 12) // 3
        self._new_cycle()

    # ── events ──
    def poke(self):
        """A click: he stops, straightens up, and just stands a while."""
        if self.state != "DRAG":
            self.pause = 2.2 + random.uniform(0, 1.2)

    def start_drag(self):
        """Another hand on the boulder. He keeps pushing anyway."""
        self.pause = 0.0
        self.drag_t = self.ball_t
        self._go("DRAG")

    def drag_to(self, t):
        self.drag_t = clamp(t, 0.0, 0.99)      # 99% at most. never 100.

    def end_drag(self):
        if self.state == "DRAG":
            self._start_roll("ROLL")           # let go. of course it rolls back.

    # ── internals ──
    def _new_cycle(self):
        """Every lap differs: pauses, crest, phases, and what the day feels like."""
        self.dur = {k: v * random.uniform(0.8, 1.35) for k, v in DUR.items()}
        self.top_t = TOP_T * random.uniform(0.90, 1.0)
        self.ph = [random.uniform(0, math.tau) for _ in range(6)]
        self.flourish = random.random() < 0.45          # a seasonal touch, some laps
        self.spots = sorted(random.uniform(0.08, 0.92) for _ in range(3))
        self.windy = random.random() < 0.30             # a thread of wind at the top
        self.tease = random.random() < 0.005            # the near-success
        self.will_slip = random.random() < 0.015        # the stumble
        self.slip_at = random.uniform(0.30, 0.70)
        lt = time.localtime()                           # the weight of this hour
        self.pace, self.heavy, self.dim = 1.0, 0.0, 1.0
        if lt.tm_wday == 0 and 6 <= lt.tm_hour < 12:
            self.pace, self.heavy = 0.85, 0.18          # Monday morning
        elif lt.tm_wday == 4 and 13 <= lt.tm_hour < 18:
            self.pace = 1.12                            # Friday afternoon
        if lt.tm_hour < 5:
            self.pace, self.dim = self.pace * 0.8, 0.85 # small hours: he keeps you company

    def _go(self, s):
        self.state, self.st = s, 0.0
        if s == "TOP":
            self.top_hold = self.dur["TOP"] + (8.0 if self.tease else 0.0)
        elif s == "RETURN":
            self.ret_from = self.fig_t

    def _start_roll(self, state):
        self.roll_from = self.ball_t
        self.roll_dur = self.dur["ROLL"] * max(0.35, math.sqrt(
            self.roll_from / self.top_t)) if self.roll_from > 0 else 0.1
        self._splashed = False
        self._go(state)

    def _splash(self):
        base = terrain(0.02)
        self.dust = [((base[0] + random.uniform(-4, 10),
                       base[1] + random.uniform(-3, 2),
                       random.uniform(-14, 22), random.uniform(-26, -8)), 0.0)
                     for _ in range(6)]

    def update(self, dt, drive=0.0):
        self.clock += dt
        k = min(1, dt * 4.0)
        for lst, life in ((self.trail, 0.5), (self.dust, 0.8)):    # age the ephemera
            lst[:] = [(e[0], e[1] + dt) for e in lst if e[1] + dt < life]

        if self.pause > 0:                     # poked: the world waits with him
            self.pause -= dt
            self.rest += (1 - self.rest) * k
            self.lean += (0.02 - self.lean) * k
            self.effort += (0.08 - self.effort) * k
            self.push += (0 - self.push) * min(1, dt * 3.5)
            return
        self.rest += (0 - self.rest) * k
        self.st += dt
        s = self.state

        if s == "ASCEND":                      # typing pushes; idle is a crawl
            v = ASCEND_V0 * self.pace * (0.25 + 1.75 * drive) \
                * (1 - 0.5 * self.ball_t / self.top_t)
            self.ball_t += v * dt
            self.fig_t = self.ball_t
            if self.will_slip and self.ball_t >= self.slip_at:
                self.will_slip = False
                self._start_roll("SLIP")
            elif self.ball_t >= self.top_t:
                self.ball_t = self.top_t
                self._go("TOP")
        elif s == "TOP":                       # a strained hover — sometimes longer
            if self.tease:                     # …it really does tip forward a hair
                p = self.st / self.top_hold
                self.ball_t = self.top_t + 0.008 * p * max(0.0, math.sin(self.st * 2.2))
            if self.st >= self.top_hold:
                self.ball_t = self.top_t
                self._start_roll("ROLL")
        elif s in ("ROLL", "SLIP"):            # crisp accelerating fall
            p = min(1, self.st / self.roll_dur)
            self.ball_t = self.roll_from * (1 - p * p)
            if self.ball_t > 0.02:
                self.trail.append((self.ball_t, 0.0))
            if p >= 1 and not self._splashed:
                self._splashed = True
                self._splash()
            if s == "ROLL" and p >= 1:
                self.ball_t = 0
                self._go("WATCH")
            elif s == "SLIP" and self.st >= max(self.roll_dur, 2.6):
                self.ball_t = 0
                self._go("RETURN")             # get up. walk back. again.
        elif s == "WATCH":                     # the stillness, then he turns away
            if self.st >= self.dur["WATCH"]:
                self._go("RETURN")
        elif s == "RETURN":                    # the calm walk back down
            p = min(1, self.st / max(1.0, self.dur["RETURN"] * self.ret_from / self.top_t))
            self.fig_t = lerp(self.ret_from, 0, ease(p))
            if p >= 1:
                self.fig_t = 0
                self.season = (self.season + 1) % 4   # one lap, one season
                self._new_cycle()
                self._go("ASCEND")
        elif s == "DRAG":                      # someone is helping. it changes nothing
            self.ball_t += (self.drag_t - self.ball_t) * min(1, dt * 8)
            # he hurries after the boulder rather than teleporting to it
            self.fig_t += clamp(self.ball_t - self.fig_t, -0.5 * dt, 0.5 * dt)

        # pose targets; the strain follows your typing — and the day of the week
        if s == "ASCEND":
            lt_, et, pt = 0.40 + 0.28 * drive + self.heavy * 0.3, \
                0.55 + 0.75 * drive + self.heavy, 1.0
        elif s == "TOP":
            x = min(1.0, self.st / self.top_hold)
            lt_, et, pt = 0.62, 1.15 + (0.55 * x if self.tease else 0), 1
        elif s == "DRAG":
            lt_, et, pt = 0.60, 1.2, 1
        elif s == "SLIP":
            lt_, et, pt = 0.05, 0.15, 0
        else:
            lt_, et, pt = {"ROLL": (0.06, 0.20, 0), "WATCH": (0.03, 0.10, 0),
                           "RETURN": (0.14, 0.35, 0)}[s]
        self.lean += (lt_ - self.lean) * k
        self.effort += (et - self.effort) * k
        self.push += (pt - self.push) * min(1, dt * 3.5)
        # he falls fast and gets up slowly
        ft = 1.0 if s == "SLIP" else 0.0
        self.fallen += (ft - self.fallen) * min(1, dt * (3.0 if ft else 1.4))
        # he turns around before walking down, and turns back at the base
        want = -1.0 if (s == "RETURN" or
                        (s == "WATCH" and self.st > 0.45 * self.dur["WATCH"])) else 1.0
        self.face += (want - self.face) * min(1, dt * 3.0)
