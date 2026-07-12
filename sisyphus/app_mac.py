"""The desktop window, via AppKit.

Tk cannot composite an RGBA image over a transparent window on macOS (the
frame simply never shows), so the display layer is a borderless NSWindow with
a clear background — which also buys true per-pixel alpha: the glow really
glows over any wallpaper. Everything else (sim, render, inputs) is unchanged.
"""
import io
import math
import time

import objc
from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory,
                    NSBackingStoreBuffered, NSColor, NSEvent, NSImage,
                    NSCompositingOperationSourceOver, NSFloatingWindowLevel,
                    NSMakeRect, NSScreen, NSTimer, NSTrackingActiveAlways,
                    NSTrackingArea, NSTrackingMouseMoved, NSView, NSWindow,
                    NSWindowCollectionBehaviorCanJoinAllSpaces,
                    NSWindowStyleMaskBorderless, NSZeroRect)
from Foundation import NSData, NSObject

from .geometry import A, H, M, NRM, R, W, project, terrain
from .inputs import Stats, Typing
from .render import BG_LIGHT, SS, render
from .sim import Sim

FPS = 30.0


def wallpaper_light(window):
    """Mean brightness (0..1) of the wallpaper under the window.

    Reads the desktop image file — no screen-recording permission needed.
    Approximate (assumes fill scaling, ignores overlapping windows); it only
    steers a soft dark/light blend, so approximate is enough.
    """
    try:
        from AppKit import NSWorkspace
        from PIL import Image
        screen = window.screen() or NSScreen.mainScreen()
        url = NSWorkspace.sharedWorkspace().desktopImageURLForScreen_(screen)
        img = Image.open(url.path()).convert("L")
        sf, wf = screen.frame(), window.frame()
        # map the window rect into image pixels (flip y: Cocoa origin is bottom-left)
        kx, ky = img.width / sf.size.width, img.height / sf.size.height
        x0 = int((wf.origin.x - sf.origin.x) * kx)
        y0 = int((sf.size.height - (wf.origin.y - sf.origin.y) - wf.size.height) * ky)
        box = (max(0, x0), max(0, y0),
               min(img.width, x0 + int(wf.size.width * kx)),
               min(img.height, y0 + int(wf.size.height * ky)))
        if box[2] <= box[0] or box[3] <= box[1]:
            return 0.3
        region = img.crop(box).resize((16, 16))
        return sum(region.getdata()) / (255.0 * 256)
    except Exception:
        return 0.3                              # unknown → assume darkish


def _nsimage(pil_img):
    buf = io.BytesIO()
    pil_img.save(buf, "PNG")
    raw = buf.getvalue()
    return NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(raw, len(raw)))


class SisyphusWindow(NSWindow):
    def canBecomeKeyWindow(self):               # borderless windows say no by default
        return True


class SisyphusView(NSView):
    def isFlipped(self):                        # y grows downward = scene coordinates
        return True

    @objc.python_method
    def setup(self):
        self.sim, self.stats, self.typing = Sim(), Stats(), Typing()
        self.image = None
        self.last = time.monotonic()
        self.saved = self.last
        self.press_ball = False
        self.press_moved = False
        self.press_at = (0, 0)
        self.bg_target = 0.3
        self.bg_checked = 0.0

    def updateTrackingAreas(self):
        from AppKit import NSTrackingMouseEnteredAndExited
        for ta in self.trackingAreas():
            self.removeTrackingArea_(ta)
        self.addTrackingArea_(NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(),
            NSTrackingMouseMoved | NSTrackingMouseEnteredAndExited
            | NSTrackingActiveAlways, self, None))

    # ── frame loop ──
    def tick_(self, _timer):
        now = time.monotonic()
        dt = min(0.05, now - self.last)
        self.last = now
        drive, n, chaos = self.typing.update(dt)
        if n:
            self.stats.hit(n)
        if now - self.saved > 10:
            self.saved = now
            self.stats.save()
        if now - self.bg_checked > 30:          # wallpaper may have changed
            self.bg_checked = now
            self.bg_target = wallpaper_light(self.window())
        BG_LIGHT[0] += (self.bg_target - BG_LIGHT[0]) * 0.05
        self.sim.update(dt, drive, chaos)
        self.sim.info *= 0.94                   # fades unless hover keeps feeding it
        # render at SS resolution and let Quartz map it 1:1 onto Retina pixels
        self.image = _nsimage(render(self.sim, self.stats, out_scale=SS))
        self.setNeedsDisplay_(True)

    def drawRect_(self, _rect):
        if self.image:
            self.image.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
                NSMakeRect(0, 0, W, H), NSZeroRect,
                NSCompositingOperationSourceOver, 1.0, True, None)

    # ── mouse ──
    @objc.python_method
    def _pt(self, event):
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        return (p.x, p.y)

    def mouseDown_(self, event):
        self.window().makeKeyWindow()           # so Esc works after any click
        x, y = self._pt(event)
        bc = A(terrain(self.sim.ball_t), M(NRM, R))
        self.press_ball = math.hypot(x - bc[0], y - bc[1]) < R * 1.6
        self.press_moved = False
        self.press_at = NSEvent.mouseLocation()
        if self.press_ball:
            self.sim.start_drag()

    def mouseDragged_(self, event):
        if self.press_ball:
            x, y = self._pt(event)
            self.sim.drag_to(project(x, y))
            return
        loc = NSEvent.mouseLocation()
        dx, dy = loc.x - self.press_at.x, loc.y - self.press_at.y
        if abs(dx) + abs(dy) > 3:
            self.press_moved = True
        f = self.window().frame()
        self.window().setFrameOrigin_((f.origin.x + dx, f.origin.y + dy))
        self.press_at = loc

    def mouseUp_(self, _event):
        if self.press_ball:
            self.press_ball = False
            self.sim.end_drag()
        elif not self.press_moved:
            self.sim.poke()
        else:                                   # window moved: resample what's under it
            self.bg_target = wallpaper_light(self.window())
            self.bg_checked = time.monotonic()

    def rightMouseDown_(self, _event):          # quit — never collides with play
        self._quit()

    def mouseMoved_(self, event):
        x, y = self._pt(event)
        self.sim.cursor = (x, y)                # he notices where you stand
        ft = terrain(self.sim.fig_t)
        if math.hypot(x - ft[0], y - ft[1]) < 70:
            self.sim.info = min(1.0, self.sim.info + 0.15)

    def mouseExited_(self, _event):
        self.sim.cursor = None

    # ── keys ──
    def acceptsFirstResponder(self):
        return True

    PREVIEW = {"1": "companion", "2": "meteor", "3": "bird", "4": "sit",
               "5": "slip", "6": "tease", "8": "rock"}

    def keyDown_(self, event):
        if event.keyCode() == 53:               # Esc
            self._quit()
            return
        name = self.PREVIEW.get(str(event.characters()))
        if name:                                # preview keys force a rare event
            self.sim.trigger(name)

    @objc.python_method
    def _quit(self):
        self.stats.save()
        NSApplication.sharedApplication().terminate_(None)


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # no Dock icon

    screen = NSScreen.mainScreen().frame()
    rect = NSMakeRect(screen.size.width - W - 24, 80, W, H)   # bottom-right corner
    win = SisyphusWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
    win.setOpaque_(False)
    win.setBackgroundColor_(NSColor.clearColor())
    win.setLevel_(NSFloatingWindowLevel)                      # always on top
    win.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces)
    win.setHasShadow_(False)

    view = SisyphusView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
    view.setup()
    win.setContentView_(view)
    win.makeFirstResponder_(view)
    win.orderFrontRegardless()

    if view.typing.ok:
        print("Keyboard listener started. If typing has no effect: System Settings "
              "→ Privacy & Security → Input Monitoring, enable this app, restart.")
    else:
        print("pynput unavailable — falling back to the slow automatic loop.")

    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        1.0 / FPS, view, objc.selector(view.tick_, signature=b"v@:@"), None, True)
    app.run()
