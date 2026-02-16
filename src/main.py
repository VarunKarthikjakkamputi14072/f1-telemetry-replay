import argparse
import sys
from data_loader import load_race
from replay import run_replay
from menu import run_menu, run_year_menu

def main():
    # 1. Setup CLI
    parser = argparse.ArgumentParser(description="F1 Telemetry Analytics Engine")
    parser.add_argument(
        "--year", 
        type=int, 
        default=None, 
        help="The race season year (Optional. Launches menu if omitted)"
    )
    args = parser.parse_args()

    # 2. Select Year (CLI or Menu)
    year = args.year
    if year is None:
        try:
            year = run_year_menu()
        except Exception as e:
            print(f"❌ Error in year menu: {e}")
            sys.exit(1)
            
    if not year:
        print("❌ No year selected. Exiting.")
        sys.exit(0)

    # 3. Select Race (Menu)
    try:
        race_name = run_menu(year)
    except Exception as e:
        print(f"❌ Error in race menu: {e}")
        sys.exit(1)
        
    if not race_name:
        print("❌ No race selected. Exiting.")
        sys.exit(0)

    # 4. Load Data & Run Replay
    race_data = load_race(year, race_name)

    try:
        # Pass full metadata object so replay.py can use dynamic values
        run_replay(
            race_data["drivers"],
            race_data["track"]["bounds"],
            race_data["track"]["timeline"],
            race_data["metadata"]
        )
    except Exception as e:
        print(f"❌ Critical Error running simulation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()