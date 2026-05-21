# How to Run — F1 Telemetry Replay

## Every Time

```bash
cd /Users/varunkarthikjakkamputi/Documents/f1_replay
source venv/bin/activate
cd src && python main.py
```

## Skip the Year Menu

```bash
python main.py --year 2023
```

## When Done

```bash
deactivate
```

---

## Replay Controls

### Playback
- **Space** — Pause / Resume
- **1, 2, 3, 4** — Set Speed (0.5x, 1x, 2x, 4x)
- **Up / Down Arrows** — Adjust Speed in 0.5x increments
- **Left / Right Arrows** — Seek Forward / Backward 5 seconds
- **Click bottom Seek Bar** — Jump to any point in the race
- **R** — Restart race from beginning

### View & UI Toggles
- **H** — Toggle Heatmap view (shows track colored by top speeds)
- **G** — Toggle Leaderboard Mode (Gap to Leader vs. Interval to car ahead)

### Driver Focus & Ghost Mode (Comparison)
- **Click on a driver (or sidebar name)** — Focus Camera on that driver
- **S** — Toggle the Style Similarity Panel (only works when a driver is focused)
- **Shift + Click on another driver** — Set as Ghost Driver (shows their delta and trail relative to focused driver)
- **C** — Clear Ghost Driver
- **F** — Clear all Focus & Ghost selections (return to full track view)
