from data_loader import load_race
from replay import run_replay
from utils import plot_sample_path


def main():
    drivers_data, bounds, timeline = load_race(2023, "Monza")

    first_driver = next(iter(drivers_data.values()))
    plot_sample_path(first_driver)

    run_replay(drivers_data, bounds, timeline)


if __name__ == "__main__":
    main()

