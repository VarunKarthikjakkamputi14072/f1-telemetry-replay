import pygame
import sys


def scale_point(x, y, bounds, screen_size):
    min_x, max_x, min_y, max_y = bounds
    width, height = screen_size

    sx = int((x - min_x) / (max_x - min_x) * width)
    sy = int((y - min_y) / (max_y - min_y) * height)

    return sx, height - sy


def build_track_points(drivers_data, bounds, screen_size):
    first_driver = next(iter(drivers_data.values()))
    points = []

    for _, row in first_driver.iterrows():
        sx, sy = scale_point(row["X"], row["Y"], bounds, screen_size)
        points.append((sx, sy))

    return points


def find_position_at_time(telemetry, t):
    idx = telemetry["Time"].searchsorted(t)
    if idx >= len(telemetry):
        return None
    return telemetry.iloc[idx]


def run_replay(drivers_data, bounds, timeline):
    pygame.init()

    screen_size = (800, 800)
    screen = pygame.display.set_mode(screen_size)
    pygame.display.set_caption("F1 Telemetry Replay")

    clock = pygame.time.Clock()

    track_points = build_track_points(drivers_data, bounds, screen_size)

    time_idx = 0
    running = True
    paused = False
    speed = 1  

    while running:
        screen.fill((0, 0, 0))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    paused = not paused
                if event.key == pygame.K_UP:
                    speed = min(speed + 1, 10)
                if event.key == pygame.K_DOWN:
                    speed = max(speed - 1, 1)

        pygame.draw.lines(screen, (60, 60, 60), False, track_points, 2)

        if not paused:
            time_idx += speed
            if time_idx >= len(timeline):
                time_idx = 0

        t = timeline[time_idx]

        for telemetry in drivers_data.values():
            row = find_position_at_time(telemetry, t)
            if row is None:
                continue

            sx, sy = scale_point(row["X"], row["Y"], bounds, screen_size)
            pygame.draw.circle(screen, (255, 255, 255), (sx, sy), 3)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()

