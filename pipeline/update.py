"""
One-command, consistent data update.

    python -m pipeline.update --year 2024 --race "Monaco"   # add/refresh one race
    python -m pipeline.update --all                          # re-export every race
    python -m pipeline.update --check                        # consistency report only

Adding a race by hand risks the dataset drifting out of sync — a race exported but
the model not retrained, or the manifest stale. This command does the whole thing
in the right order so the app's data is always self-consistent:

    export race(s)  ->  retrain the pace model  ->  refresh manifest + version stamp
                    ->  verify every race is complete and the model is in sync.
"""
from __future__ import annotations

import argparse
import glob
import json
import os

from .export import REQUIRED_FILES, WEB_DATA, refresh_manifest, run_export
from . import simulate, train_model


def known_races():
    """(year, round, race-name) for every race already on disk."""
    out = []
    for p in glob.glob(os.path.join(WEB_DATA, "*", "*", "meta.json")):
        m = json.load(open(p))
        out.append((m["year"], m["round"], m["race"]))
    return sorted(out)


def check():
    """Report completeness of each race and whether the model is in sync."""
    ok = True
    print("🔎 Consistency check")
    for year, rnd, name in known_races():
        d = os.path.join(WEB_DATA, str(year), str(rnd))
        missing = [f for f in REQUIRED_FILES if not os.path.exists(os.path.join(d, f))]
        status = "✅" if not missing else f"❌ missing {missing}"
        print(f"   {year} {name:<28} {status}")
        ok = ok and not missing
    model_path = os.path.join(WEB_DATA, "model.json")
    if os.path.exists(model_path):
        m = json.load(open(model_path))
        trained = set(m.get("races", []))
        current = {f"{y} {n}" for y, _, n in known_races()}
        if trained == current:
            print(f"   model: ✅ in sync (R² {m['metrics']['r2']}, {m['nSamples']} laps)")
        else:
            ok = False
            print(f"   model: ⚠️  STALE — trained on {len(trained)} races, "
                  f"now have {len(current)}. Run `--all` or any update to retrain.")
    else:
        print("   model: ⚠️  not trained yet")
    print("✅ all consistent" if ok else "⚠️  inconsistencies found")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int)
    ap.add_argument("--race", type=str)
    ap.add_argument("--all", action="store_true", help="re-export every known race")
    ap.add_argument("--check", action="store_true", help="report only, no changes")
    ap.add_argument("--step", type=float, default=0.5)
    args = ap.parse_args()

    if args.check:
        raise SystemExit(0 if check() else 1)

    if args.all:
        targets = [(y, n) for y, _, n in known_races()]
    elif args.year and args.race:
        targets = [(args.year, args.race)]
    else:
        ap.error("pass --year/--race, or --all, or --check")

    for year, race in targets:
        print(f"\n=== {year} {race} ===")
        run_export(year, race, args.step)

    print("\n🧠 retraining pace model on the full set...")
    train_model.main()

    print("\n🎲 re-running strategy simulations...")
    simulate.main()

    print("\n📇 refreshing manifest...")
    races, model = refresh_manifest()
    print(f"   {len(races)} races · model R² {model['r2'] if model else 'n/a'}")

    check()


if __name__ == "__main__":
    main()
