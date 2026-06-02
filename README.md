# F1 Telemetry Replay

An interactive Formula 1 race replay and analytics engine. It pulls real timing and
telemetry data for any race weekend, reconstructs the on-track action, and plays it
back in real time with a rich, broadcast-style overlay — driver trails colored by
speed, live gaps and intervals, sector timing, tyre strategy, weather, and race
control messages.

Built in Python with [FastF1](https://docs.fastf1.dev/) for data and
[pygame](https://www.pygame.org/) for rendering.

## Features

- **Real telemetry replay** — positions interpolated and smoothed with Catmull–Rom
  splines for fluid motion at any playback speed.
- **Speed heatmap** — toggle a view that colors the racing line by top speed to see
  where time is won and lost.
- **Ghost / comparison mode** — focus a driver and overlay a Dynamic Time Warping
  (DTW) aligned "ghost" to compare laps lap-against-lap.
- **Live leaderboard** — switch between Gap-to-Leader and Interval-to-car-ahead.
- **Sector analysis** — overall sector bests and live purple/green sector flashes.
- **Tyre strategy** — compound coloring and pit-window tracking per driver.
- **Race context** — weather timeline, track status, and race control messages
  synced to the replay clock.
- **Full playback control** — pause, variable speed (0.5x–4x), seek bar, and restart.

## Quick start

```bash
# 1. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run (launches an interactive year/race menu)
cd src && python main.py

# Or skip the year menu:
python main.py --year 2023
```

> FastF1 caches downloaded session data locally, so the first load of a race is
> slower; subsequent replays of the same race are fast.

## Controls

| Key / Action            | Effect                                            |
| ----------------------- | ------------------------------------------------- |
| `Space`                 | Pause / resume                                     |
| `1` `2` `3` `4`         | Set speed to 0.5x / 1x / 2x / 4x                   |
| `Up` / `Down`           | Adjust speed in 0.5x steps                         |
| `Left` / `Right`        | Seek backward / forward 5 seconds                  |
| Click seek bar          | Jump to any point in the race                      |
| `R`                     | Restart from the beginning                         |
| `H`                     | Toggle speed heatmap                               |
| `G`                     | Toggle leaderboard mode (Gap vs. Interval)         |
| Click a driver / name   | Focus camera and enable ghost comparison           |

## Project structure

```
src/
  main.py          # CLI + menu entry point
  menu.py          # Year and race selection screens
  data_loader.py   # FastF1 ingestion: timeline, weather, sectors, pit windows
  replay.py        # Real-time rendering loop and overlays
  track_geo.py     # Track bounds, geometry, and racing-line helpers
  dtw.py           # Dynamic Time Warping for ghost-lap alignment
  similarity.py    # Lap comparison utilities
  tyre_model.py    # Compound coloring and tyre logic
  utils.py         # Color, easing, and math helpers
```

## Requirements

Python 3.9+ and the packages pinned in [`requirements.txt`](requirements.txt).

## License

See [LICENSE](LICENSE) if present, otherwise all rights reserved by the author.
