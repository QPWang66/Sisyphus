"""System-wide typing monitor and the daily keystroke count."""
import json
import math
import threading
import time
from pathlib import Path


class Typing:
    """drive ∈ [0,1]: 0 = idle crawl, 1 = hammering the keyboard."""

    def __init__(self):
        self._n, self._lock, self._rate = 0, threading.Lock(), 0.0
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

    def update(self, dt):
        """Returns (drive, keys_this_frame)."""
        with self._lock:
            n, self._n = self._n, 0
        self._rate = self._rate * math.exp(-dt / 0.45) + n  # short memory, snappy
        return min(1.0, self._rate / 2.0), n                # ~4 keys/s = flat out


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
