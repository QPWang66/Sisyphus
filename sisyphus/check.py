"""Self-checks: drive the FSM headless through every scenario, then a render
smoke test across seasons. Run with `python3 -m sisyphus --check`."""
import time

from .geometry import H, W
from .inputs import Stats
from .render import BG_LIGHT, render
from .sim import TOP_T, Sim


def _run(sim, dt, secs, drive=1.0):
    peak_fallen = 0.0
    for _ in range(int(secs / dt)):
        sim.update(dt, drive)
        peak_fallen = max(peak_fallen, sim.fallen)
    return peak_fallen


def check():
    dt = 1 / 30
    # 1. a plain full cycle: all five states, the turn, the season advancing
    sim = Sim()
    sim.tease = sim.will_slip = False
    seen, turned, s0 = {"ASCEND"}, False, sim.season
    for _ in range(int(60 / dt)):
        sim.update(dt, 1.0)
        if sim.state == "ASCEND":
            sim.tease = sim.will_slip = False
        seen.add(sim.state)
        turned = turned or sim.face < -0.9
        assert -1e-6 <= sim.ball_t <= TOP_T + 0.02, sim.ball_t
        if len(seen) >= 5 and sim.state == "ASCEND":
            break
    else:
        raise AssertionError(f"no full cycle, stuck near {sim.state}")
    assert turned, "figure never turned around before descending"
    assert sim.season == (s0 + 1) % 4, "a lap should advance the season"
    # 2. poke holds everything still
    sim.poke()
    b = sim.ball_t
    _run(sim, dt, 1.0)
    assert sim.ball_t == b and sim.rest > 0.5, "poke should pause the loop"
    # 3. slip: he falls, the boulder returns to base, he gets up into a new lap
    sim = Sim()
    sim.tease, sim.will_slip, sim.slip_at = False, True, 0.4
    peak, recovered = 0.0, False
    for _ in range(int(60 / dt)):
        sim.update(dt, 1.0)
        peak = max(peak, sim.fallen)
        if peak > 0.6 and sim.state == "ASCEND" and sim.fallen < 0.3:
            recovered = True
            break
    assert peak > 0.6, f"never properly fell (peak fallen {peak:.2f})"
    assert recovered, "never got back up into a new lap"
    # 4. drag to 99%, release → it rolls all the way back
    sim = Sim()
    sim.tease = sim.will_slip = False
    sim.start_drag()
    for _ in range(60):
        sim.drag_to(0.99)
        sim.update(dt)
    assert sim.ball_t > 0.9, sim.ball_t
    sim.end_drag()
    _run(sim, dt, 6, 0.0)
    assert sim.ball_t < 0.05 and sim.state in ("WATCH", "RETURN", "ASCEND"), \
        (sim.ball_t, sim.state)
    # 5. tease: an extended TOP still ends in a fall
    sim = Sim()
    sim.will_slip = False
    sim.tease = True
    for _ in range(int(30 / dt)):               # ride the ascent up to the crest
        sim.update(dt, 1.0)
        if sim.state == "TOP":
            break
    assert sim.state == "TOP" and sim.top_hold > 8, (sim.state, sim.top_hold)
    for _ in range(int(30 / dt)):               # …and it still must come down
        sim.update(dt, 1.0)
        if sim.state != "TOP" and sim.ball_t < 0.05:
            break
    else:
        raise AssertionError("even the near-success must roll back")
    # 6. events: each preview trigger runs its course and clears itself
    sim = Sim()
    sim.tease = sim.will_slip = False
    for name in ("companion", "meteor", "bird"):
        sim.trigger(name)
    assert sim.companion and sim.meteor and sim.bird
    _run(sim, dt, 40, 0.0)
    assert sim.companion is None and sim.meteor is None and sim.bird is None
    sim.trigger("sit")                          # he sits, then goes back to it
    _run(sim, dt, 0.5, 0.0)
    assert sim.state == "SIT" and sim.sit > 0.1, (sim.state, sim.sit)
    _run(sim, dt, 12, 0.0)
    assert sim.state != "SIT", "he cannot sit forever"
    sim.trigger("rock")
    assert sim.rock > 1.4                       # a heavy day
    # 7. a parked cursor blocks the walk; moving it away frees him
    sim = Sim()
    sim.tease = sim.will_slip = False
    _run(sim, dt, 2)
    from .geometry import A as _A, DIR as _DIR, M as _M, terrain as _terrain
    sim.cursor = _A(_terrain(sim.fig_t), _M(_DIR, 20))
    _run(sim, dt, 1.5)                          # he takes a moment to halt…
    b = sim.ball_t
    _run(sim, dt, 2)
    assert sim.ball_t - b < 0.005, "cursor in his path should stop him"
    sim.cursor = None
    _run(sim, dt, 3)
    assert sim.ball_t - b > 0.05, "he should move on once the path clears"
    # 8. render smoke: seasons × fallen × hover text × trail × wind, plus timing
    sim = Sim()
    sim.flourish, sim.info, sim.windy, sim.state = True, 1.0, True, "TOP"
    sim.meteor = {"p": 0.4, "paused": True}
    sim.companion = {"p": 0.5, "paused": True}
    sim.bird = {"ph": "perch", "t": 1.0}
    sim.sit, sim.chaos, sim.rock = 0.6, 0.8, 1.4
    sim.cursor, sim.blocked = (200, 150), 0.7
    stats = Stats()
    t0 = time.perf_counter()
    frames = 0
    for season in range(4):
        sim.season = season
        for fallen in (0.0, 1.0):
            BG_LIGHT[0] = fallen                # also covers dark + bright modes
            sim.fallen = fallen
            sim.trail = [(0.4, 0.1), (0.3, 0.3)]
            img = render(sim, stats)
            assert img.size == (W, H)
            frames += 1
    BG_LIGHT[0] = 0.0
    ms = (time.perf_counter() - t0) / frames * 1000
    # sanity bound only — CI runners are slow; ~15ms on a dev machine
    assert ms < 200, f"frame render pathologically slow: {ms:.1f}ms"
    print(f"ok: cycle+poke+slip+drag+tease+render ({ms:.1f}ms/frame)")
