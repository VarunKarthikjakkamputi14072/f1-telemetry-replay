# Apex — F1 Telemetry Replay & Analytics

A broadcast-style Formula 1 race replay and analytics studio built on real
[FastF1](https://docs.fastf1.dev/) telemetry. Scrub through a Grand Prix with a
live timing tower, then dig into tyre strategy, the race's position-change
story, and distance-aligned driver-vs-driver telemetry.

The project has two halves:

- **`web/`** — a Next.js app: a 60 fps `<canvas>` replay plus a Recharts
  analytics dashboard (this is the headline).
- **`pipeline/`** — a Python exporter that does the heavy, browser-unfriendly
  data work once and emits compact JSON for the web app to read.
- **`src/`** — the original desktop replay (pygame) the project grew out of,
  kept working.

---

## Why it's built this way

Browsers can't run FastF1, and a 90-minute race of 20 cars' telemetry is far too
much to ship raw. So all the expensive and *correctness-sensitive* work happens
in the Python pipeline, and the front-end consumes precomputed, quantized JSON.

The interesting part is getting the racing maths right rather than eyeballed:

| Concern | Naive approach | What this does |
| --- | --- | --- |
| **Time gaps** | `metres_behind / 70` | Resample every car onto one shared session clock, then derive the gap as *the time when the car ahead passed the position the car behind is now at* — the same thing a real timing screen computes. |
| **Track position** | sort by distance | Use FastF1's official per-lap `Position`, with cumulative-distance sorting only for the live replay order. |
| **The track** | hard-coded outline | Racing line + corner numbers + start/finish taken from the session's fastest lap and `circuit_info`. |
| **Lap comparison** | overlay vs time | Distance-aligned delta time: integrate `dx / v(x)` along the lap so the two cars are compared at the same point on track. |

Everything is quantized to integers and sliced to each driver's active window,
so a full race exports to **~5 MB** of JSON.

---

## The app

- **Replay** — canvas track render with the racing line, numbered corners and
  start/finish; team-coloured cars with speed-weighted comet trails and DRS
  markers; a live timing tower with real gap/interval (and "+1 lap" for lapped
  cars); F1-TV-style telemetry bars for the car you click to focus, plus a live
  ahead/behind battle readout. An **onboard** mode zooms and follows the focused
  car. The scrub bar overlays **race-control bands** (safety car / VSC / yellow /
  red) and clickable **key-moment markers** (pit stops, lead changes, fastest
  lap), with a live **flag + weather** readout. Transport controls + keyboard
  shortcuts (`Space`, `←/→`, `r`).
- **Strategy** — every driver's race as a tyre-stint timeline, ordered by
  finishing position, with pit stops as the breaks between compounds.
- **Pace** — the race as a position-change "spaghetti" chart, plus a
  gap-to-leader evolution chart.
- **Compare** — pick two drivers for a distance-aligned delta-time curve and
  overlaid speed/throttle traces from their quickest laps.
- **AI Engineer** — an independent strategist makes pit calls lap by lap (tyre
  life, pit loss, undercuts, box-under-safety-car) and is graded against what
  each driver actually did, with reasons and a verdict. Decisions are
  deterministic and reproducible; set `GROQ_API_KEY` to have **Llama** (Groq's
  free tier) write the verdicts. On 2021 Abu Dhabi the engine independently
  reproduces Verstappen's three stops, including the lap-54 switch to softs.

---

## Running it

### 1. Export a race (Python)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Downloads telemetry (cached after first run) and writes web/public/data/<year>/<round>/
python -m pipeline.export --year 2021 --race "Abu Dhabi"
# any race works:
python -m pipeline.export --year 2023 --race "Brazil"

# optional: AI Engineer verdicts written by Llama (Groq free tier)
export GROQ_API_KEY=...   # then re-run the export above
```

### 2. Run the web app

```bash
cd web
npm install
npm run dev        # http://localhost:3000
```

The landing page lists every race you've exported.

### Desktop replay (original)

```bash
cd src && python main.py            # menu-driven season/race picker
```

---

## Stack

**Pipeline:** Python · FastF1 · NumPy · pandas
**Web:** Next.js (App Router) · TypeScript · Tailwind CSS · Recharts · HTML Canvas

## Data & attribution

Telemetry is sourced from FastF1, which surfaces official F1 timing data. This
is an independent project and is not associated with Formula 1, the FIA, or any
team. For personal and educational use.
