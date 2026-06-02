import os
import pygame
import sys
import numpy as np
from collections import deque

from recorder import ClipRecorder

# ---------------------------------------------------------------------------
# Visual configuration
# ---------------------------------------------------------------------------
BG_COLOR = (13, 13, 17)
TRACK_COLOR = (60, 60, 70)
TRACK_OUTLINE = (20, 20, 25)
TEXT_COLOR = (240, 240, 240)
UI_BG = (22, 25, 30)
UI_BORDER = (55, 60, 70)
TRAIL_LENGTH = 25

PURPLE = (170, 0, 255)
GREEN = (0, 230, 70)
YELLOW = (255, 230, 0)

HEATMAP_COLD = (30, 80, 220)
HEATMAP_MID = (50, 220, 50)
HEATMAP_HOT = (240, 50, 30)


def _lerp(a, b, t):
    return a + (b - a) * max(0.0, min(1.0, t))


def _lerp_color(c1, c2, t):
    return (
        int(_lerp(c1[0], c2[0], t)),
        int(_lerp(c1[1], c2[1], t)),
        int(_lerp(c1[2], c2[2], t)),
    )


def speed_to_color(ratio):
    """Map 0..1 speed ratio to a cool-to-hot colour."""
    if ratio < 0.5:
        return _lerp_color(HEATMAP_COLD, HEATMAP_MID, ratio * 2)
    return _lerp_color(HEATMAP_MID, HEATMAP_HOT, (ratio - 0.5) * 2)


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------
def scale_point(x, y, bounds, screen_size):
    min_x, max_x, min_y, max_y = bounds
    width, height = screen_size

    padding_x = 60
    padding_y = 90
    sidebar_width = 240

    avail_w = width - (padding_x * 2) - sidebar_width
    avail_h = height - (padding_y * 2)

    range_x = max(1.0, max_x - min_x)
    range_y = max(1.0, max_y - min_y)

    sx = int((x - min_x) / range_x * avail_w) + padding_x
    sy = int((y - min_y) / range_y * avail_h) + padding_y
    return sx, height - sy


def build_track_points(drivers_data, bounds, screen_size):
    if not drivers_data:
        return [], []
    try:
        best_driver = max(drivers_data.items(), key=lambda x: len(x[1]))[1]
    except ValueError:
        return [], []

    points = []
    speeds = []
    max_speed = best_driver["Speed"].max() if "Speed" in best_driver.columns else 1
    if max_speed <= 0:
        max_speed = 1

    for _, row in best_driver.iterrows():
        sx, sy = scale_point(row["X"], row["Y"], bounds, screen_size)
        points.append((sx, sy))
        spd = row.get("Speed", 0) if "Speed" in best_driver.columns else 0
        speeds.append(spd / max_speed)
    return points, speeds


# ---------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------
def get_interpolated_state(df, t):
    """Returns (X, Y, CumDist, LapNumber, Speed, DRS, Throttle, Brake, nGear)."""
    zero = (0, 0, 0, 0, 0, 0, 0, 0, 0)
    if df.empty:
        return zero

    idx = df["Time"].searchsorted(t)

    def _row_vals(row):
        return (
            row["X"], row["Y"], row["CumDist"], row["LapNumber"],
            row.get("Speed", 0), row.get("DRS", 0),
            row.get("Throttle", 0), row.get("Brake", 0), row.get("nGear", 0),
        )

    if idx == 0:
        return _row_vals(df.iloc[0])
    if idx >= len(df):
        return _row_vals(df.iloc[-1])

    r0 = df.iloc[idx - 1]
    r1 = df.iloc[idx]
    t0, t1 = r0["Time"], r1["Time"]

    if t1 == t0:
        return _row_vals(r0)

    a = (t - t0) / (t1 - t0)

    x = r0["X"] + (r1["X"] - r0["X"]) * a
    y = r0["Y"] + (r1["Y"] - r0["Y"]) * a
    dist = r0["CumDist"] + (r1["CumDist"] - r0["CumDist"]) * a
    lap = r0["LapNumber"]
    speed = r0["Speed"] + (r1["Speed"] - r0["Speed"]) * a
    drs = r1["DRS"]
    throttle = r0["Throttle"] + (r1["Throttle"] - r0["Throttle"]) * a
    brake = r0["Brake"] + (r1["Brake"] - r0["Brake"]) * a
    gear = r0["nGear"]

    return x, y, dist, lap, speed, drs, throttle, brake, gear


# ---------------------------------------------------------------------------
# Sector flash helpers
# ---------------------------------------------------------------------------
def _check_sector_flash(driver_info, drv_id, lap, prev_lap_sectors,
                        best_sectors, overall_best_sectors):
    """Return flash colour or None when a driver just completed a PB/OB sector."""
    info = driver_info.get(drv_id, {})
    sector_records = info.get("SectorTimes", [])
    if not sector_records:
        return None

    flash_colour = None
    for rec in sector_records:
        if rec["LapNumber"] != int(lap):
            continue
        sec = rec["Sector"]
        t_sec = rec["Time"]
        key = (drv_id, sec)

        prev = best_sectors.get(key)
        ov_prev = overall_best_sectors.get(sec)

        is_pb = prev is None or t_sec < prev
        is_ob = ov_prev is None or t_sec < ov_prev

        if is_pb:
            best_sectors[key] = t_sec
            flash_colour = GREEN
        if is_ob:
            overall_best_sectors[sec] = t_sec
            flash_colour = PURPLE

    return flash_colour


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def _draw_speed_heatmap(screen, track_points, track_speeds, show_heatmap):
    if not show_heatmap or len(track_points) < 2:
        return
    for i in range(len(track_points) - 1):
        col = speed_to_color(track_speeds[i])
        pygame.draw.line(screen, col, track_points[i], track_points[i + 1], 5)


def _draw_drs_zones(screen, track_points, drs_segments, show_drs):
    """Shade DRS activation zones on track outline."""
    if not show_drs or not drs_segments or len(track_points) < 2:
        return
    n = len(track_points)
    drs_col = (0, 200, 70)
    for start_f, end_f in drs_segments:
        i0 = max(0, int(start_f * n))
        i1 = min(n - 1, int(end_f * n))
        if i1 <= i0:
            continue
        for i in range(i0, i1):
            pygame.draw.line(screen, drs_col, track_points[i], track_points[i + 1], 10)


def _detect_drs_zones(best_driver_df):
    """Detect DRS activation zones as fractional track ranges."""
    if "DRS" not in best_driver_df.columns:
        return []
    drs_vals = best_driver_df["DRS"].values
    n = len(drs_vals)
    if n == 0:
        return []

    zones = []
    in_zone = False
    start = 0
    for i in range(n):
        active = int(drs_vals[i]) >= 10
        if active and not in_zone:
            start = i
            in_zone = True
        elif not active and in_zone:
            zones.append((start / n, i / n))
            in_zone = False
    if in_zone:
        zones.append((start / n, (n - 1) / n))
    return zones


def _draw_telemetry_bar(screen, font, d, screen_w, screen_h):
    """Render F1-TV style telemetry bars at the bottom for the focused driver."""
    bar_area_h = 60
    bar_y0 = screen_h - 20 - bar_area_h
    bg = pygame.Surface((screen_w, bar_area_h), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 160))
    screen.blit(bg, (0, bar_y0))

    metrics = [
        ("THR", d.get("throttle", 0) / 100.0, (0, 200, 80)),
        ("BRK", min(d.get("brake", 0), 100) / 100.0, (220, 40, 40)),
        ("SPD", min(d.get("speed", 0), 370) / 370.0, (80, 180, 255)),
    ]

    gear_val = int(d.get("gear", 0))
    speed_val = int(d.get("speed", 0))

    total_bar_w = screen_w - 340
    bar_w = total_bar_w // len(metrics) - 20
    x_start = 20
    label_font = pygame.font.SysFont("Consolas", 14, bold=True)

    for i, (label, ratio, col) in enumerate(metrics):
        bx = x_start + i * (bar_w + 20)
        by = bar_y0 + 30
        bh = 16

        pygame.draw.rect(screen, (40, 40, 50), (bx, by, bar_w, bh), border_radius=3)
        fill_w = int(bar_w * max(0, min(1, ratio)))
        if fill_w > 0:
            pygame.draw.rect(screen, col, (bx, by, fill_w, bh), border_radius=3)

        lbl = label_font.render(label, True, (180, 180, 180))
        screen.blit(lbl, (bx, bar_y0 + 10))

        pct_str = f"{int(ratio * 100)}%" if label != "SPD" else f"{speed_val} km/h"
        pct = label_font.render(pct_str, True, TEXT_COLOR)
        screen.blit(pct, (bx + bar_w + 4, by))

    val_font = pygame.font.SysFont("Consolas", 20, bold=True)
    gear_label = val_font.render(f"GEAR  {gear_val}", True, (255, 220, 60))
    screen.blit(gear_label, (screen_w - 310, bar_y0 + 20))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def draw_dashboard(screen, font, t, speed, driver_info, leaderboard_order,
                   gaps, current_lap, total_laps, total_time, gap_mode,
                   focused_driver, fastest_lap_driver, animated_y, pit_drivers,
                   sector_flash):
    screen_w, screen_h = screen.get_size()

    # --- Top Header ---
    header_h = 70
    pygame.draw.rect(screen, UI_BG, (0, 0, screen_w, header_h))
    pygame.draw.line(screen, UI_BORDER, (0, header_h), (screen_w, header_h), 2)

    minutes = int(t // 60)
    seconds = int(t % 60)
    millis = int((t % 1) * 100)
    time_str = f"TIME: {minutes:02}:{seconds:02}.{millis:02}"
    lap_str = f"LAP {int(current_lap)} / {total_laps}"

    font_large = pygame.font.SysFont("Consolas", 28, bold=True)

    time_surf = font_large.render(time_str, True, (200, 200, 200))
    screen.blit(time_surf, (20, 20))

    lap_surf = font_large.render(lap_str, True, (255, 255, 255))
    screen.blit(lap_surf, (screen_w // 2 - lap_surf.get_width() // 2, 20))

    speed_surf = font_large.render(f"SPEED: {speed}x", True, (100, 200, 255))
    screen.blit(speed_surf, (screen_w - speed_surf.get_width() - 20, 20))

    # --- Side Leaderboard ---
    panel_w = 240
    panel_x = screen_w - panel_w
    panel_y = header_h
    panel_h = screen_h - header_h - 20

    pygame.draw.rect(screen, UI_BG, (panel_x, panel_y, panel_w, panel_h))
    pygame.draw.line(screen, UI_BORDER, (panel_x, panel_y), (panel_x, screen_h - 20), 2)

    header_font = pygame.font.SysFont("Consolas", 14, bold=True)
    pygame.draw.rect(screen, (30, 35, 45), (panel_x, panel_y, panel_w, 35))

    screen.blit(header_font.render("POS", True, (120, 120, 120)),
                (panel_x + 10, panel_y + 10))
    screen.blit(header_font.render("DRIVER", True, (120, 120, 120)),
                (panel_x + 50, panel_y + 10))
    gap_label = "INT" if gap_mode == "interval" else "GAP"
    screen.blit(header_font.render(gap_label, True, (120, 120, 120)),
                (panel_x + 160, panel_y + 10))

    list_start_y = panel_y + 40
    row_h = 36
    name_font = pygame.font.SysFont("Consolas", 18, bold=True)
    gap_font = pygame.font.SysFont("Consolas", 16)
    badge_font = pygame.font.SysFont("Consolas", 10, bold=True)

    for pos, drv_id in enumerate(leaderboard_order):
        info = driver_info.get(drv_id, {})
        target_y = list_start_y + (pos * row_h)

        # Animated position lerp
        if drv_id not in animated_y:
            animated_y[drv_id] = float(target_y)
        animated_y[drv_id] = _lerp(animated_y[drv_id], target_y, 0.12)
        y_pos = int(animated_y[drv_id])

        if y_pos + row_h > screen_h - 20:
            continue

        is_focused = (focused_driver == drv_id)
        bg_col = (25, 30, 40) if pos % 2 == 0 else (22, 25, 30)
        if pos == 0:
            bg_col = (35, 40, 50)
        if is_focused:
            bg_col = (50, 55, 70)

        pygame.draw.rect(screen, bg_col, (panel_x, y_pos, panel_w, row_h))

        try:
            c_hex = info["TeamColor"].lstrip("#")
            c_rgb = tuple(int(c_hex[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            c_rgb = (255, 255, 255)

        pygame.draw.rect(screen, c_rgb,
                         (panel_x + 4, y_pos + 4, 4, row_h - 8), border_radius=2)

        pos_col = (255, 255, 255) if pos < 3 else (150, 150, 150)
        pos_surf = name_font.render(str(pos + 1), True, pos_col)
        screen.blit(pos_surf, (panel_x + 15, y_pos + 8))

        name_surf = name_font.render(info.get("Abbreviation", "???"), True, TEXT_COLOR)
        screen.blit(name_surf, (panel_x + 50, y_pos + 8))

        # Fastest lap crown
        if fastest_lap_driver and drv_id == fastest_lap_driver:
            crown_surf = badge_font.render("FL", True, PURPLE)
            screen.blit(crown_surf, (panel_x + 105, y_pos + 12))

        # Pit stop badge
        if drv_id in pit_drivers:
            pit_bg_rect = pygame.Rect(panel_x + 118, y_pos + 10, 28, 14)
            pygame.draw.rect(screen, (200, 60, 60), pit_bg_rect, border_radius=3)
            pit_surf = badge_font.render("PIT", True, (255, 255, 255))
            screen.blit(pit_surf, (panel_x + 120, y_pos + 11))

        # Gap / Interval display
        gap_val = gaps.get(drv_id, 0)
        if pos == 0:
            gap_str = "LEADER"
            col = (100, 255, 100)
        else:
            gap_str = f"+{gap_val:.1f}s"
            col = (200, 100, 100)

        gap_surf = gap_font.render(gap_str, True, col)
        screen.blit(gap_surf, (panel_x + 160, y_pos + 10))

    # --- Seek Bar ---
    bar_h = 20
    bar_y = screen_h - bar_h
    pygame.draw.rect(screen, (10, 10, 10), (0, bar_y, screen_w, bar_h))
    progress = t / total_time if total_time > 0 else 0
    progress_w = int(screen_w * progress)
    pygame.draw.rect(screen, (200, 50, 50), (0, bar_y, progress_w, bar_h))
    pygame.draw.line(screen, (255, 255, 255),
                     (progress_w, bar_y), (progress_w, screen_h), 2)

    # Mode indicator hints
    hint_font = pygame.font.SysFont("Consolas", 11)
    mode_text = f"[G] {'Interval' if gap_mode == 'interval' else 'Gap to Leader'}"
    mode_text += "  [H] Heatmap  [D] DRS  [T] Telemetry  [C] Clip"
    if focused_driver:
        abbr = driver_info.get(focused_driver, {}).get("Abbreviation", "???")
        mode_text += f"  | Focus: {abbr} (click to release)"
    hint = hint_font.render(mode_text, True, (100, 100, 110))
    screen.blit(hint, (10, screen_h - bar_h - 16))


# ---------------------------------------------------------------------------
# Main replay loop
# ---------------------------------------------------------------------------

# Module-level state for click detection across frames
_last_frame = []
_last_lb = []


def run_replay(drivers_data, bounds, timeline, metadata):
    global _last_frame, _last_lb

    if not drivers_data or not timeline:
        print("❌ Replay Error: No driver data or timeline available.")
        return

    driver_info = metadata["driver_info"]
    total_laps = metadata.get("total_laps", 0)

    # --- Precompute CumDist ---
    for drv_id, df in drivers_data.items():
        if df.empty:
            continue
        coords = df[["X", "Y"]].values
        diffs = coords[1:] - coords[:-1]
        dists = np.sqrt((diffs ** 2).sum(axis=1))
        dists = np.insert(dists, 0, 0)
        df["CumDist"] = np.cumsum(dists)

    max_total_dist = 0
    for df in drivers_data.values():
        if not df.empty and "CumDist" in df.columns:
            d = df["CumDist"].iloc[-1]
            if d > max_total_dist:
                max_total_dist = d

    if total_laps > 0 and max_total_dist > 0:
        track_length_approx = max_total_dist / total_laps
    else:
        track_length_approx = 5000

    global_max_speed = 1
    for df in drivers_data.values():
        if "Speed" in df.columns and not df.empty:
            mx = df["Speed"].max()
            if mx > global_max_speed:
                global_max_speed = mx

    pygame.init()
    screen_size = (1280, 850)
    screen = pygame.display.set_mode(screen_size)
    pygame.display.set_caption(
        f"F1 Telemetry Pro | {metadata.get('race_name', 'Race')}")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("Consolas", 24, bold=True)
    tag_font = pygame.font.SysFont("Arial", 10, bold=True)

    track_points, track_speeds = build_track_points(
        drivers_data, bounds, screen_size)

    try:
        best_drv_df = max(drivers_data.items(), key=lambda x: len(x[1]))[1]
        drs_segments = _detect_drs_zones(best_drv_df)
    except Exception:
        drs_segments = []

    time_val = timeline[0]
    total_time = timeline[-1]

    running = True
    paused = False
    speed = 1.0

    gap_mode = "leader"
    focused_driver = None
    show_heatmap = False
    show_drs = False
    show_telemetry = False

    sector_flashes = {}
    best_sectors = {}
    overall_best_sectors = {}
    prev_lap_per_driver = {}

    fastest_lap_time = None
    fastest_lap_driver = None

    animated_y = {}

    drv_colors = {}
    for drv, info in driver_info.items():
        try:
            h = info["TeamColor"].lstrip("#")
            drv_colors[drv] = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            drv_colors[drv] = (200, 200, 200)

    trails = {drv: deque(maxlen=TRAIL_LENGTH) for drv in drivers_data}
    trail_speeds = {drv: deque(maxlen=TRAIL_LENGTH) for drv in drivers_data}

    def _reset_trails():
        nonlocal trails, trail_speeds
        trails = {drv: deque(maxlen=TRAIL_LENGTH) for drv in drivers_data}
        trail_speeds = {drv: deque(maxlen=TRAIL_LENGTH) for drv in drivers_data}

    # Clip recorder — writes shareable MP4/GIF highlights to <root>/clips.
    clips_dir = os.path.join(os.path.dirname(__file__), os.pardir, "clips")
    recorder = ClipRecorder(out_dir=clips_dir, prefix="f1_replay")
    saved_msg = None
    saved_msg_until = 0.0
    rec_font = pygame.font.SysFont("Consolas", 14, bold=True)

    while running:
        screen.fill(BG_COLOR)
        dt = clock.get_time() / 1000.0
        screen_w, screen_h = screen.get_size()

        # ---- Events ----
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_1:
                    speed = 0.5
                elif event.key == pygame.K_2:
                    speed = 1.0
                elif event.key == pygame.K_3:
                    speed = 2.0
                elif event.key == pygame.K_4:
                    speed = 4.0
                elif event.key == pygame.K_UP:
                    speed = min(speed + 0.5, 10.0)
                elif event.key == pygame.K_DOWN:
                    speed = max(speed - 0.5, 0.0)
                elif event.key == pygame.K_RIGHT:
                    time_val += 5.0
                elif event.key == pygame.K_LEFT:
                    time_val -= 5.0
                elif event.key == pygame.K_r:
                    time_val = timeline[0]
                    _reset_trails()
                    sector_flashes.clear()
                elif event.key == pygame.K_g:
                    gap_mode = "interval" if gap_mode == "leader" else "leader"
                elif event.key == pygame.K_h:
                    show_heatmap = not show_heatmap
                elif event.key == pygame.K_d:
                    show_drs = not show_drs
                elif event.key == pygame.K_t:
                    show_telemetry = not show_telemetry
                elif event.key == pygame.K_c:
                    if recorder.available:
                        path = recorder.toggle()
                        if path:
                            saved_msg = f"Saved {os.path.basename(path)}"
                            saved_msg_until = pygame.time.get_ticks() + 4000
                    else:
                        saved_msg = "Install imageio to record clips"
                        saved_msg_until = pygame.time.get_ticks() + 4000

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = pygame.mouse.get_pos()
                if my > screen_h - 20:
                    ratio = mx / screen_w
                    time_val = ratio * total_time
                    _reset_trails()
                else:
                    panel_x = screen_w - 240
                    if mx >= panel_x:
                        row_h_click = 36
                        list_start_y_click = 70 + 40
                        clicked_pos = int(
                            (my - list_start_y_click) / row_h_click)
                        if 0 <= clicked_pos < len(_last_lb):
                            clicked_drv = _last_lb[clicked_pos]
                            focused_driver = (
                                None if focused_driver == clicked_drv
                                else clicked_drv)
                    else:
                        clicked_any = False
                        for fd in _last_frame:
                            dx = mx - fd["sx"]
                            dy = my - fd["sy"]
                            if dx * dx + dy * dy < 144:
                                focused_driver = (
                                    None if focused_driver == fd["id"]
                                    else fd["id"])
                                clicked_any = True
                                break
                        if not clicked_any and mx < panel_x:
                            focused_driver = None

        # ---- Draw track ----
        if len(track_points) > 1:
            pygame.draw.lines(screen, TRACK_OUTLINE, False, track_points, 16)
            pygame.draw.lines(screen, TRACK_COLOR, False, track_points, 6)

        _draw_drs_zones(screen, track_points, drs_segments, show_drs)
        _draw_speed_heatmap(screen, track_points, track_speeds, show_heatmap)

        # ---- Advance time ----
        if not paused:
            time_val += dt * speed
            if time_val > total_time:
                time_val = timeline[0]
                _reset_trails()

        time_val = max(timeline[0], min(time_val, total_time))

        # ---- Update drivers ----
        current_frame_data = []
        pit_drivers = set()

        for drv_code, df in drivers_data.items():
            if df.empty:
                continue
            (rx, ry, dist, lap, spd,
             drs, throttle, brake, gear) = get_interpolated_state(df, time_val)
            sx, sy = scale_point(rx, ry, bounds, screen_size)

            trails[drv_code].append((sx, sy))
            trail_speeds[drv_code].append(spd)

            if spd < 5:
                pit_drivers.add(drv_code)

            prev_lap = prev_lap_per_driver.get(drv_code, 0)
            if lap != prev_lap and lap > 0:
                flash_col = _check_sector_flash(
                    driver_info, drv_code, prev_lap,
                    prev_lap_per_driver, best_sectors, overall_best_sectors)
                if flash_col:
                    sector_flashes[drv_code] = (flash_col, time_val + 1.5)

                drv_lap_times = driver_info.get(
                    drv_code, {}).get("LapTimes", [])
                for lt_rec in drv_lap_times:
                    if (lt_rec["LapNumber"] == int(prev_lap)
                            and lt_rec["LapTime"] > 0):
                        if (fastest_lap_time is None
                                or lt_rec["LapTime"] < fastest_lap_time):
                            fastest_lap_time = lt_rec["LapTime"]
                            fastest_lap_driver = drv_code
            prev_lap_per_driver[drv_code] = lap

            current_frame_data.append({
                "id": drv_code,
                "dist": dist,
                "lap": lap,
                "sx": sx,
                "sy": sy,
                "speed": spd,
                "drs": drs,
                "throttle": throttle,
                "brake": brake,
                "gear": gear,
            })

        _last_frame = current_frame_data

        if current_frame_data:
            current_frame_data.sort(key=lambda x: x["dist"], reverse=True)
            leaderboard_order = [d["id"] for d in current_frame_data]
            _last_lb = leaderboard_order

            leader_dist = current_frame_data[0]["dist"]
            current_lap = current_frame_data[0]["lap"]
            if current_lap == 0:
                current_lap = int(leader_dist / track_length_approx) + 1

            gaps = {}
            if gap_mode == "leader":
                for d in current_frame_data:
                    delta_m = leader_dist - d["dist"]
                    gaps[d["id"]] = delta_m / 70.0
            else:
                for i, d in enumerate(current_frame_data):
                    if i == 0:
                        gaps[d["id"]] = 0
                    else:
                        delta_m = (current_frame_data[i - 1]["dist"]
                                   - d["dist"])
                        gaps[d["id"]] = delta_m / 70.0

            draw_dashboard(
                screen, font, time_val, speed, driver_info,
                leaderboard_order, gaps, current_lap, total_laps, total_time,
                gap_mode, focused_driver, fastest_lap_driver,
                animated_y, pit_drivers, sector_flashes)

            # ---- Draw trails ----
            for drv_code in leaderboard_order:
                pts = list(trails[drv_code])
                spds = list(trail_speeds[drv_code])
                if len(pts) < 2:
                    continue

                c = drv_colors.get(drv_code, (200, 200, 200))
                is_faded = (focused_driver is not None
                            and drv_code != focused_driver)
                if is_faded:
                    c = (c[0] // 5, c[1] // 5, c[2] // 5)

                for i in range(len(pts) - 1):
                    spd_ratio = (spds[i] / global_max_speed
                                 if global_max_speed > 0 else 0.5)
                    th = max(1, int(
                        _lerp(1, 5, spd_ratio) * (i / len(pts))))
                    pygame.draw.line(screen, c, pts[i], pts[i + 1], th)

            # ---- Draw driver dots ----
            for d in current_frame_data:
                c = drv_colors.get(d["id"], (200, 200, 200))
                sx, sy = d["sx"], d["sy"]

                is_faded = (focused_driver is not None
                            and d["id"] != focused_driver)
                am = 0.2 if is_faded else 1.0

                dot_c = (int(c[0] * am), int(c[1] * am), int(c[2] * am))
                outer_c = (0, 0, 0) if not is_faded else (5, 5, 5)
                inner_c = (int(255 * am), int(255 * am), int(255 * am))

                flash_entry = sector_flashes.get(d["id"])
                if flash_entry and time_val < flash_entry[1]:
                    pulse = 0.5 + 0.5 * np.sin(
                        (time_val - (flash_entry[1] - 1.5)) * 8)
                    dot_c = _lerp_color(dot_c, flash_entry[0], pulse)

                drs_active = int(d.get("drs", 0)) >= 10

                pygame.draw.circle(screen, outer_c, (sx, sy), 9)
                pygame.draw.circle(screen, dot_c, (sx, sy), 7)
                pygame.draw.circle(screen, inner_c, (sx, sy), 2)

                if drs_active and show_drs:
                    pts_diamond = [
                        (sx, sy - 13), (sx + 4, sy - 9),
                        (sx, sy - 5), (sx - 4, sy - 9)]
                    pygame.draw.polygon(screen, (0, 220, 80), pts_diamond)

                if not is_faded:
                    lbl = tag_font.render(
                        driver_info.get(d["id"], {}).get(
                            "Abbreviation", "???"),
                        True, (220, 220, 220))
                    screen.blit(lbl, (sx + 12, sy - 12))

            if show_telemetry and focused_driver:
                for d in current_frame_data:
                    if d["id"] == focused_driver:
                        _draw_telemetry_bar(
                            screen, font, d, screen_w, screen_h)
                        break

        expired = [k for k, v in sector_flashes.items() if time_val >= v[1]]
        for k in expired:
            del sector_flashes[k]

        # ---- Clip capture (before overlay, so the REC badge isn't in the clip) ----
        if recorder.recording:
            if recorder.capture(screen):
                path = recorder.stop()  # hit the length cap -> auto-save
                if path:
                    saved_msg = f"Saved {os.path.basename(path)}"
                    saved_msg_until = pygame.time.get_ticks() + 4000

        # ---- Recording / saved overlay (screen-only) ----
        now_ms = pygame.time.get_ticks()
        if recorder.recording:
            pygame.draw.circle(screen, (235, 50, 50), (24, 60), 7)
            rec_text = rec_font.render(
                f"REC  {recorder.seconds:4.1f}s   [C] stop",
                True, (235, 80, 80))
            screen.blit(rec_text, (38, 52))
        elif saved_msg and now_ms < saved_msg_until:
            saved_surf = rec_font.render(saved_msg, True, (90, 220, 120))
            screen.blit(saved_surf, (20, 52))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()
