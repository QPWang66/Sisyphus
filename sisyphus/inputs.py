"""System-wide typing monitor and the daily keystroke count."""
import json
import math
import threading
import time
from collections import deque
from pathlib import Path


class Typing:
    """drive ∈ [0,1]: 0 = idle crawl, 1 = hammering the keyboard.
    chaos ∈ [0,1]: 0 = steady rhythm, 1 = frantic bursts."""

    def __init__(self):
        self._n, self._lock, self._rate = 0, threading.Lock(), 0.0
        self._times = deque(maxlen=12)
        self._chaos = 0.0
        self.ok = False
        try:
            from pynput import keyboard
            keyboard.Listener(on_press=self._hit, daemon=True).start()
            self.ok = True
        except Exception:
            pass                      # no listener → he just crawls on his own

    def _hit(self, *_):
        with self._lock:
            self._n += 1
            self._times.append(time.monotonic())

    def update(self, dt):
        """Returns (drive, keys_this_frame, chaos)."""
        with self._lock:
            n, self._n = self._n, 0
            times = list(self._times)
        self._rate = self._rate * math.exp(-dt / 0.45) + n  # short memory, snappy
        target = 0.0
        if len(times) >= 6 and time.monotonic() - times[-1] < 2.0:
            iv = [b - a for a, b in zip(times, times[1:]) if b - a < 2.0]
            if len(iv) >= 4:
                m = sum(iv) / len(iv)
                if m > 1e-6:
                    cv = (sum((x - m) ** 2 for x in iv) / len(iv)) ** 0.5 / m
                    target = max(0.0, min(1.0, (cv - 0.35) / 0.65))
        self._chaos += (target - self._chaos) * min(1, dt * 3)
        return min(1.0, self._rate / 2.0), n, self._chaos  # ~4 keys/s = flat out


class Stats:
    """Daily keystroke count. Only the number is stored — never which keys."""

    PATH = Path.home() / ".sisyphus_stats.json"

    def __init__(self):
        self.date, self.keys = time.strftime("%Y-%m-%d"), 0
        try:
            d = json.loads(self.PATH.read_text())
            if d.get("date") == self.date:
                self.keys = int(d.get("keys", 0))
        except Exception:
            pass

    def hit(self, n):
        today = time.strftime("%Y-%m-%d")
        if today != self.date:
            self.date, self.keys = today, 0     # a new day, a new zero
        self.keys += n

    def save(self):
        try:
            self.PATH.write_text(json.dumps({"date": self.date, "keys": self.keys}))
        except Exception:
            pass
