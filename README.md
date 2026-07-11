# Sisyphus

A desktop companion who pushes a boulder, forever.

The harder you type, the harder he pushes. The boulder never reaches the top.
Your measurable output: **zero**. (After Albert Camus.)

He lives in a corner of your desktop — a small glowing ink-brush figure on a
rugged slope, drawn in calligraphic strokes. Seasons pass, one per lap.
Nothing accumulates. Nothing is unlocked. That is the point.

## Install

Grab the latest build from [Releases](../../releases) — `Sisyphus-macos-arm64.zip`
(Apple Silicon) or `Sisyphus-windows-x64.exe` — or run from source:

```sh
pip install pillow pynput
python3 -m sisyphus
```

**Opening on macOS** (the build is not notarized): double-click once and let it
be blocked, then System Settings → Privacy & Security → **Open Anyway**.
Or clear the quarantine flag in Terminal: `xattr -cr ~/Downloads/Sisyphus.app`.

**Windows** may show a SmartScreen warning: More info → Run anyway.

macOS: for the typing-driven push, grant **Input Monitoring** to the app
(System Settings → Privacy & Security → Input Monitoring), then restart it.
Only a daily keystroke *count* is kept (`~/.sisyphus_stats.json`) — never
which keys.

## Interactions

- **Type anywhere** — he pushes harder. Stop, and he slows to a weary crawl.
- **Hold the boulder and drag it uphill** — you can help him. Up to 99%.
  Let go. You know what happens.
- **Click him** — he stops, straightens up, and rests a moment.
- **Hover near him** — today's numbers: `N keys today · boulder displacement: 0 m`.
- **Drag elsewhere** moves the window. **Right-click** or **Esc** quits.

Some laps carry a seasonal touch — sprouts, fireflies, a falling leaf, sparse
snow. Rarely, he slips. Very rarely, the boulder almost makes it.

## Check

```sh
python3 -m sisyphus --check
```

## Structure

```
sisyphus/
  geometry.py   # the slope, the summit, vectors, splines
  sim.py        # the state machine (headless)
  render.py     # PIL brush rendering: core + blurred glow
  inputs.py     # keyboard listener + daily count
  app.py        # tk window and event wiring
  check.py      # self-checks
```
