"""The state machine. Headless — no window needed, fully checkable.

States: ASCEND → TOP → ROLL → WATCH → RETURN → ASCEND, forever.
Extras: SLIP (a rare stumble), DRAG (a hand other than his on the boulder),
SIT (small hours: he rests by the boulder before starting again).
Rare passing events: a meteor, a bird, another Sisyphus on a distant ridge.
The boulder never passes top_t. Output is always zero.
"""
import math
import random
import time

from .geometry import A, DIR, M, clamp, ease, lerp, terrain

TOP_T = 0.85                                  # the ball never reaches the summit
DUR = {"TOP": 1.3, "ROLL": 1.5, "WATCH": 1.8, "RETURN": 5.5}
ASCEND_V0 = 0.135
R = 17


def _night(lt=None):
    h = (lt or time.localtime()).tm_hour
    return h >= 22 or h < 5


class Sim:
    def __init__(self):
        self.state, self.st, self.clock = "ASCEND", 0.0, 0.0
        self.ball_t, self.fig_t = 0.0, 0.0
        self.lean, self.effort, self.push = 0.45, 0.6, 1.0
        self.face = 1.0                        # +1 uphill, -1 downhill
        self.pause, self.rest = 0.0, 0.0       # poked: stand still for a moment
        self.fallen = 0.0                      # 1 = flat on the ground (SLIP)
        self.sit = 0.0                         # 1 = sitting by the boulder
        self.info = 0.0                        # hover text fade
        self.chaos = 0.0                       # typing rhythm: 0 steady, 1 frantic
        self.cursor = None                     # mouse in scene coords, or None
        self.blocked = 0.0                     # cursor standing in his path
        self.walk, self.prev_feet = 0.0, None
        self.trail, self.dust = [], []         # rolling afterimages / impact dust
        self.meteor = None                     # {"p": 0..1, "paused": bool}
        self.bird = None                       # {"ph": in|perch|off, "t": s}
        self.companion = None                  # {"p": 0..1, "paused": bool}
        self.roll_from, self.roll_dur = 0.0, 1.0
        self.ret_from, self.drag_t = 0.0, 0.0
        self.sit_dur, self._sit_back = 6.0, "ASCEND"
        self.force_sit = False
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

    def trigger(self, name):
        """Force a rare event now — the preview keys route here."""
        if name == "companion" and self.companion is None:
            self.companion = {"p": 0.0, "paused": False}
        elif name == "meteor" and self.meteor is None:
            self.meteor = {"p": 0.0, "paused": False}
        elif name == "bird" and self.bird is None:
            self.bird = {"ph": "in", "t": 0.0}
        elif name == "sit" and self.state not in ("SIT", "DRAG"):
            self.sit_dur, self._sit_back = random.uniform(5, 9), self.state
            self._go("SIT")                    # sits right where he is
        elif name == "slip" and self.state == "ASCEND":
            self.will_slip, self.slip_at = True, min(0.9, self.ball_t + 0.05)
        elif name == "tease":
            self.tease = True                  # takes effect at the next crest
        elif name == "rock":
            self.rock = 1.45                   # a heavy day, effective immediately

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
        # some days the boulder is simply bigger; it means nothing, carries over
        # nothing — 4% of laps are heavy days
        self.rock = 1.4 if random.random() < 0.04 else random.uniform(0.90, 1.15)
        # rare passings, armed to fire mid-ascent
        self.companion_at = random.uniform(0.2, 0.6) \
            if random.random() < 0.003 else None
        self.meteor_at = random.uniform(0.2, 0.8) \
            if (_night() and random.random() < 0.03) else None
        self.bird_p = 0.08                              # chance per WATCH
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
        elif s == "WATCH" and self.bird is None and random.random() < self.bird_p:
            self.bird = {"ph": "in", "t": 0.0}

    def _start_roll(self, state):
        self.roll_from = self.ball_t
        self.roll_dur = self.dur["ROLL"] * max(0.35, math.sqrt(
            self.roll_from / self.top_t)) if self.roll_from > 0 else 0.1
        self._splashed = False
        self._go(state)

    def _lap_done(self):
        self.fig_t = 0
        self.season = (self.season + 1) % 4             # one lap, one season
        self._new_cycle()
        if self.force_sit or (_night() and random.random() < 0.30):
            self.force_sit = False
            self.sit_dur, self._sit_back = random.uniform(5, 9), "ASCEND"
            self._go("SIT")                             # he sits a while first
        else:
            self._go("ASCEND")

    def _splash(self):
        base = terrain(0.02)
        self.dust = [((base[0] + random.uniform(-4, 10),
                       base[1] + random.uniform(-3, 2),
                       random.uniform(-14, 22), random.uniform(-26, -8)), 0.0)
                     for _ in range(6)]

    def _update_events(self, dt):
        """Meteor / bird / distant companion run on their own little clocks."""
        if self.meteor:
            self.meteor["p"] += dt / 2.6
            if self.meteor["p"] > 0.25 and not self.meteor["paused"]:
                self.meteor["paused"] = True
                self.pause = max(self.pause, 2.0)       # he stops to watch it
            if self.meteor["p"] >= 1:
                self.meteor = None
        if self.companion:
            self.companion["p"] += dt / 14.0
            if 0.45 < self.companion["p"] < 0.55 and not self.companion["paused"]:
                self.companion["paused"] = True
                self.pause = max(self.pause, 1.6)       # they see each other
            if self.companion["p"] >= 1:
                self.companion = None
        if self.bird:
            self.bird["t"] += dt
            ph, t = self.bird["ph"], self.bird["t"]
            if ph == "in" and t > 1.2:
                self.bird.update(ph="perch", t=0.0)
            elif ph == "perch":
                near = self.state == "RETURN" and self.fig_t < 0.25
                if near or t > 20:
                    self.bird.update(ph="off", t=0.0)   # it will not be touched
            elif ph == "off" and t > 1.2:
                self.bird = None

    def update(self, dt, drive=0.0, chaos=0.0):
        self.clock += dt
        k = min(1, dt * 4.0)
        self.chaos += (chaos - self.chaos) * k
        self._update_events(dt)
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

        # a cursor parked in his path: he stops and waits, without a word
        want_b = 0.0
        if self.cursor and s in ("ASCEND", "RETURN"):
            ahead = A(terrain(self.fig_t), M(DIR, R * 1.2 * (1 if self.face >= 0 else -1)))
            if math.hypot(self.cursor[0] - ahead[0], self.cursor[1] - ahead[1]) < R * 2.4:
                want_b = 1.0
        self.blocked += (want_b - self.blocked) * min(1, dt * 5.0)
        if self.blocked > 0.5 and s in ("ASCEND", "RETURN"):
            self.st -= dt * min(1.0, self.blocked)      # time holds its breath

        if s == "ASCEND":                      # typing pushes; idle is a crawl
            v = ASCEND_V0 * self.pace * (0.25 + 1.75 * drive) \
                * (1 - 0.5 * self.ball_t / self.top_t) \
                * (1.0 / self.rock) ** 1.3 * (1 - self.blocked)
            self.ball_t += v * dt
            self.fig_t = self.ball_t
            if self.companion_at and self.ball_t >= self.companion_at:
                self.companion_at = None
                if self.companion is None:
                    self.companion = {"p": 0.0, "paused": False}
            if self.meteor_at and self.ball_t >= self.meteor_at:
                self.meteor_at = None
                if self.meteor is None:
                    self.meteor = {"p": 0.0, "paused": False}
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
                self._lap_done()
        elif s == "SIT":                       # he sits. the boulder waits.
            if self.st >= self.sit_dur:
                self._go(self._sit_back)
        elif s == "DRAG":                      # someone is helping. it changes nothing
            self.ball_t += (self.drag_t - self.ball_t) * min(1, dt * 8)
            # he hurries after the boulder rather than teleporting to it
            self.fig_t += clamp(self.ball_t - self.fig_t, -0.5 * dt, 0.5 * dt)

        # pose targets; the strain follows your typing — and the day of the week
        if s == "ASCEND":
            lt_, et, pt = 0.40 + 0.28 * drive + self.heavy * 0.3, \
                0.55 + 0.75 * drive + self.heavy + (self.rock - 1) * 0.9 \
                + 0.2 * self.chaos, 1.0
        elif s == "TOP":
            x = min(1.0, self.st / self.top_hold)
            lt_, et, pt = 0.62, 1.15 + (0.55 * x if self.tease else 0), 1
        elif s == "DRAG":
            lt_, et, pt = 0.60, 1.2, 1
        elif s == "SLIP":
            lt_, et, pt = 0.05, 0.15, 0
        elif s == "SIT":
            lt_, et, pt = 0.06, 0.10, 0
        else:
            lt_, et, pt = {"ROLL": (0.06, 0.20, 0), "WATCH": (0.03, 0.10, 0),
                           "RETURN": (0.14, 0.35, 0)}[s]
        lt_ = lerp(lt_, 0.08, self.blocked)             # blocked: he straightens
        et = lerp(et, 0.25, self.blocked)
        self.lean += (lt_ - self.lean) * k
        self.effort += (et - self.effort) * k
        self.push += (pt - self.push) * min(1, dt * 3.5)
        # he falls fast and gets up slowly; he sits down gently
        ft = 1.0 if s == "SLIP" else 0.0
        self.fallen += (ft - self.fallen) * min(1, dt * (3.0 if ft else 1.4))
        st_ = 1.0 if s == "SIT" else 0.0
        self.sit += (st_ - self.sit) * min(1, dt * (2.0 if st_ else 1.6))
        # he turns around before walking down, and turns back at the base
        want = -1.0 if (s == "RETURN" or
                        (s == "WATCH" and self.st > 0.45 * self.dur["WATCH"])) else 1.0
        self.face += (want - self.face) * min(1, dt * 3.0)
