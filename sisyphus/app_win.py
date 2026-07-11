"""The desktop window on Windows: tk with color-key transparency.

Windows tk supports `-transparentcolor`: every pixel of an exact key color
becomes see-through. Each frame is flattened onto that key color, so the
strokes stay and the rest of the window vanishes. Anti-aliased edges blend
toward the (near-black) key, which reads as the same soft dark shade the
renderer already puts under everything.

No wallpaper-brightness probe here — BG_LIGHT stays at its dark-mode default.
"""
import math
import time
import tkinter as tk

from PIL import Image, ImageTk

from .geometry import A, H, M, NRM, R, W, project, terrain
from .inputs import Stats, Typing
from .render import render
from .sim import Sim

FPS_MS = 33
KEY_RGB = (1, 2, 3)          # improbable color, keyed to transparent
KEY = "#010203"


def main():
    root = tk.Tk()
    root.overrideredirect(True)                 # frameless
    root.attributes("-topmost", True)
    try:
        root.attributes("-transparentcolor", KEY)
    except tk.TclError:
        pass                                    # e.g. Linux: opaque dark window
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{sw - W - 24}+{sh - H - 80}")       # bottom-right corner

    c = tk.Canvas(root, width=W, height=H, bg=KEY, highlightthickness=0)
    c.pack()

    sim, stats = Sim(), Stats()
    key_bg = Image.new("RGBA", (W, H), KEY_RGB + (255,))

    def flat_frame():
        return Image.alpha_composite(key_bg, render(sim, stats)).convert("RGB")

    press = {"x": 0, "y": 0, "moved": False, "ball": False}

    def near_ball(x, y):
        bc = A(terrain(sim.ball_t), M(NRM, R))
        return math.hypot(x - bc[0], y - bc[1]) < R * 1.6

    def p_down(e):
        press.update(x=e.x, y=e.y, moved=False, ball=near_ball(e.x, e.y))
        if press["ball"]:
            sim.start_drag()

    def p_move(e):
        if abs(e.x - press["x"]) + abs(e.y - press["y"]) > 3:
            press["moved"] = True
        if press["ball"]:
            sim.drag_to(project(e.x, e.y))
        else:
            root.geometry(f"+{root.winfo_x() + e.x - press['x']}"
                          f"+{root.winfo_y() + e.y - press['y']}")

    def p_up(_):
        if press["ball"]:
            sim.end_drag()
        elif not press["moved"]:
            sim.poke()

    def hover(e):
        ft = terrain(sim.fig_t)
        if math.hypot(e.x - ft[0], e.y - ft[1]) < 70:
            sim.info = min(1.0, sim.info + 0.15)

    def quit_(*_):
        stats.save()
        root.destroy()

    c.bind("<ButtonPress-1>", p_down)
    c.bind("<B1-Motion>", p_move)
    c.bind("<ButtonRelease-1>", p_up)
    c.bind("<Motion>", hover)
    c.bind("<Button-3>", quit_)                 # right-click quits, same as macOS
    root.bind("<Escape>", quit_)

    typing = Typing()
    print("Keyboard listener started." if typing.ok
          else "pynput unavailable — falling back to the slow automatic loop.")

    photo = ImageTk.PhotoImage(flat_frame())
    c.create_image(0, 0, image=photo, anchor="nw")
    last, saved = [time.monotonic()], [time.monotonic()]

    def tick():
        now = time.monotonic()
        dt = min(0.05, now - last[0])
        last[0] = now
        drive, n = typing.update(dt)
        if n:
            stats.hit(n)
        if now - saved[0] > 10:
            saved[0] = now
            stats.save()
        sim.update(dt, drive)
        sim.info *= 0.94                        # fades unless hover keeps feeding it
        photo.paste(flat_frame())
        root.after(FPS_MS, tick)

    tick()
    root.mainloop()
