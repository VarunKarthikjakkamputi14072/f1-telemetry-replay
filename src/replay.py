import pygame
import sys
import numpy as np
import math

# --- Visual Configuration ---
BG_COLOR = (13, 13, 17)
TRACK_COLOR = (60, 60, 70)
TRACK_OUTLINE = (20, 20, 25)
TEXT_COLOR = (240, 240, 240)
SUBTEXT_COLOR = (150, 150, 150)
UI_BG = (22, 25, 30)
UI_BORDER = (55, 60, 70)
ACCENT_BLUE = (100, 200, 255)
DRS_GREEN = (90, 255, 120)
PIT_YELLOW = (255, 205, 80)
FASTEST_PURPLE = (190, 90, 255)
TRAIL_LENGTH = 28
SIDEBAR_WIDTH = 260
HEADER_HEIGHT = 76
SEEK_BAR_HEIGHT = 20


def clamp(value, low, high):
    return max(low, min(value, high))


def lerp(a, b, alpha):
    return a + (b - a) * alpha


def lerp_color(a, b, alpha):
    alpha = clamp(alpha, 0.0, 1.0)
    return tuple(int(lerp(a[i], b[i], alpha)) for i in range(3))


def muted_color(color, amount=0.25):
    return lerp_color(BG_COLOR, color, amount)


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


def parse_team_color(value):
    try:
        c_hex = value.lstrip("#")
        return tuple(int(c_hex[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (200, 200, 200)


def speed_to_color(speed, max_speed):
    ratio = clamp(speed / max(max_speed, 1.0), 0.0, 1.0)
    if ratio < 0.4:
        return lerp_color((50, 100, 255), (50, 230, 255), ratio / 0.4)
    if ratio < 0.75:
        return lerp_color((50, 230, 255), (255, 220, 80), (ratio - 0.4) / 0.35)
    return lerp_color((255, 220, 80), (255, 70, 70), (ratio - 0.75) / 0.25)


def trail_width(speed, max_speed):
    return max(1, int(1 + 5 * clamp(speed / max(max_speed, 1.0), 0.0, 1.0)))


def is_drs_active(value):
    return safe_float(value) >= 10.0


def format_lap_time(seconds):
    if seconds is None:
        return "--:--.---"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}:{secs:06.3f}"


def draw_badge(screen, text, font, x, y, fg, bg):
    surf = font.render(text, True, fg)
    rect = pygame.Rect(x, y, surf.get_width() + 10, surf.get_height() + 4)
    pygame.draw.rect(screen, bg, rect, border_radius=5)
    screen.blit(surf, (rect.x + 5, rect.y + 2))
    return rect


def scale_point(x, y, bounds, screen_size):
    min_x, max_x, min_y, max_y = bounds
    width, height = screen_size

    padding_x = 60
    padding_top = HEADER_HEIGHT + 28
    padding_bottom = 126

    avail_w = width - (padding_x * 2) - SIDEBAR_WIDTH
    avail_h = height - padding_top - padding_bottom

    range_x = max(1.0, max_x - min_x)
    range_y = max(1.0, max_y - min_y)

    sx = int((x - min_x) / range_x * avail_w) + padding_x
    sy_from_bottom = int((y - min_y) / range_y * avail_h) + padding_bottom
    return sx, height - sy_from_bottom


def build_track_segments(drivers_data, bounds, screen_size):
    if not drivers_data:
        return []

    try:
        reference_df = max(drivers_data.values(), key=len)
    except ValueError:
        return []

    segments = []
    for i in range(len(reference_df) - 1):
        row = reference_df.iloc[i]
        next_row = reference_df.iloc[i + 1]
        p1 = scale_point(row["X"], row["Y"], bounds, screen_size)
        p2 = scale_point(next_row["X"], next_row["Y"], bounds, screen_size)
        speed = safe_float(next_row.get("Speed", 0))
        drs = is_drs_active(next_row.get("DRS", 0))
        segments.append({"p1": p1, "p2": p2, "speed": speed, "drs": drs})

    return segments


def get_interpolated_state(df, t):
    """
    Returns interpolated telemetry state for time t.
    """
    defaults = {
        "X": 0.0,
        "Y": 0.0,
        "CumDist": 0.0,
        "LapNumber": 0.0,
        "Speed": 0.0,
        "Throttle": 0.0,
        "Brake": 0.0,
        "nGear": 0.0,
        "DRS": 0.0,
    }

    if df.empty:
        return defaults.copy()

    idx = df["Time"].searchsorted(t)

    if idx == 0:
        row = df.iloc[0]
        return {key: safe_float(row.get(key, value), value) for key, value in defaults.items()}
    if idx >= len(df):
        row = df.iloc[-1]
        return {key: safe_float(row.get(key, value), value) for key, value in defaults.items()}

    t0_row = df.iloc[idx - 1]
    t1_row = df.iloc[idx]
    t0, t1 = safe_float(t0_row["Time"]), safe_float(t1_row["Time"])

    if t1 == t0:
        return {key: safe_float(t0_row.get(key, value), value) for key, value in defaults.items()}

    alpha = (t - t0) / (t1 - t0)
    state = {}

    for key, default in defaults.items():
        if key in ("LapNumber", "nGear", "DRS"):
            source = t1_row if alpha >= 0.5 else t0_row
            state[key] = safe_float(source.get(key, default), default)
            continue

        v0 = safe_float(t0_row.get(key, default), default)
        v1 = safe_float(t1_row.get(key, default), default)
        state[key] = v0 + (v1 - v0) * alpha

    return state


def draw_track(screen, track_segments, show_heatmap, max_speed):
    if not track_segments:
        return

    points = [track_segments[0]["p1"]] + [segment["p2"] for segment in track_segments]
    if len(points) > 1:
        pygame.draw.lines(screen, TRACK_OUTLINE, False, points, 18)

    if show_heatmap:
        for segment in track_segments:
            pygame.draw.line(
                screen,
                speed_to_color(segment["speed"], max_speed),
                segment["p1"],
                segment["p2"],
                7
            )
    elif len(points) > 1:
        pygame.draw.lines(screen, TRACK_COLOR, False, points, 7)

    overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    for segment in track_segments:
        if segment["drs"]:
            pygame.draw.line(overlay, (*DRS_GREEN, 110), segment["p1"], segment["p2"], 12)
    screen.blit(overlay, (0, 0))


def draw_dashboard(
    screen,
    t,
    speed,
    driver_info,
    leaderboard_order,
    gaps,
    intervals,
    current_lap,
    total_laps,
    total_time,
    gap_mode,
    focused_driver,
    fastest_driver,
    fastest_lap_time,
    pit_drivers,
    drs_drivers,
    row_positions
):
    screen_w, screen_h = screen.get_size()

    # --- Top Header ---
    pygame.draw.rect(screen, UI_BG, (0, 0, screen_w, HEADER_HEIGHT))
    pygame.draw.line(screen, UI_BORDER, (0, HEADER_HEIGHT), (screen_w, HEADER_HEIGHT), 2)

    minutes = int(t // 60)
    seconds = int(t % 60)
    millis = int((t % 1) * 100)
    time_str = f"TIME {minutes:02}:{seconds:02}.{millis:02}"
    lap_str = f"LAP {int(current_lap)} / {total_laps}"

    font_large = pygame.font.SysFont("Consolas", 26, bold=True)
    font_small = pygame.font.SysFont("Consolas", 13)
    font_badge = pygame.font.SysFont("Consolas", 11, bold=True)

    screen.blit(font_large.render(time_str, True, (210, 210, 210)), (20, 16))
    lap_surf = font_large.render(lap_str, True, TEXT_COLOR)
    screen.blit(lap_surf, (screen_w // 2 - lap_surf.get_width() // 2, 16))

    speed_surf = font_large.render(f"{speed:g}x", True, ACCENT_BLUE)
    screen.blit(speed_surf, (screen_w - SIDEBAR_WIDTH - speed_surf.get_width() - 22, 16))

    if fastest_driver and fastest_driver in driver_info:
        fl_text = (
            f"FASTEST {driver_info[fastest_driver]['Abbreviation']} "
            f"{format_lap_time(fastest_lap_time)}"
        )
        screen.blit(font_small.render(fl_text, True, FASTEST_PURPLE), (22, 50))

    mode_text = f"G: {'intervals' if gap_mode == 'interval' else 'leader gaps'}"
    help_text = "Space pause | 1-4 speed | Arrows seek/speed | H heatmap | Click driver focus | F clear"
    screen.blit(font_small.render(mode_text, True, (190, 190, 190)), (screen_w // 2 + 135, 50))
    screen.blit(font_small.render(help_text, True, (120, 120, 120)), (screen_w - SIDEBAR_WIDTH - 610, 50))

    # --- Side Leaderboard ---
    panel_w = SIDEBAR_WIDTH
    panel_x = screen_w - panel_w
    panel_y = HEADER_HEIGHT
    panel_h = screen_h - HEADER_HEIGHT - SEEK_BAR_HEIGHT

    pygame.draw.rect(screen, UI_BG, (panel_x, panel_y, panel_w, panel_h))
    pygame.draw.line(screen, UI_BORDER, (panel_x, panel_y), (panel_x, screen_h - SEEK_BAR_HEIGHT), 2)

    header_font = pygame.font.SysFont("Consolas", 13, bold=True)
    pygame.draw.rect(screen, (30, 35, 45), (panel_x, panel_y, panel_w, 35))

    gap_header = "INT" if gap_mode == "interval" else "GAP"
    screen.blit(header_font.render("POS", True, (120, 120, 120)), (panel_x + 10, panel_y + 10))
    screen.blit(header_font.render("DRIVER", True, (120, 120, 120)), (panel_x + 50, panel_y + 10))
    screen.blit(header_font.render(gap_header, True, (120, 120, 120)), (panel_x + 204, panel_y + 10))

    row_h = 36
    name_font = pygame.font.SysFont("Consolas", 18, bold=True)
    gap_font = pygame.font.SysFont("Consolas", 15)

    sidebar_rects = {}
    ordered_positions = {drv_id: pos for pos, drv_id in enumerate(leaderboard_order)}

    for drv_id in leaderboard_order:
        pos = ordered_positions[drv_id]
        info = driver_info[drv_id]
        y_pos = int(row_positions.get(drv_id, panel_y + 40 + (pos * row_h)))

        if y_pos + row_h > screen_h - SEEK_BAR_HEIGHT:
            continue

        is_dimmed = focused_driver is not None and drv_id != focused_driver
        bg_col = (25, 30, 40) if pos % 2 == 0 else (22, 25, 30)
        if pos == 0:
            bg_col = (35, 40, 50)
        if is_dimmed:
            bg_col = muted_color(bg_col, 0.7)

        row_rect = pygame.Rect(panel_x, y_pos, panel_w, row_h)
        sidebar_rects[drv_id] = row_rect
        pygame.draw.rect(screen, bg_col, row_rect)

        if focused_driver == drv_id:
            pygame.draw.rect(screen, ACCENT_BLUE, row_rect.inflate(-4, -4), 2, border_radius=4)

        c_rgb = parse_team_color(info["TeamColor"])
        if is_dimmed:
            c_rgb = muted_color(c_rgb)
        pygame.draw.rect(screen, c_rgb, (panel_x + 4, y_pos + 4, 4, row_h - 8), border_radius=2)

        text_col = (115, 115, 115) if is_dimmed else TEXT_COLOR
        pos_surf = name_font.render(str(pos + 1), True, text_col if pos >= 3 else (255, 255, 255))
        screen.blit(pos_surf, (panel_x + 15, y_pos + 8))

        name_surf = name_font.render(info["Abbreviation"], True, text_col)
        screen.blit(name_surf, (panel_x + 50, y_pos + 8))

        badge_x = panel_x + 94
        if drv_id == fastest_driver:
            draw_badge(screen, "FL", font_badge, badge_x, y_pos + 9, (255, 245, 255), (80, 35, 110))
            badge_x += 30
        if drv_id in pit_drivers:
            draw_badge(screen, "PIT", font_badge, badge_x, y_pos + 9, (30, 20, 0), PIT_YELLOW)
            badge_x += 38
        if drv_id in drs_drivers:
            draw_badge(screen, "DRS", font_badge, badge_x, y_pos + 9, (0, 40, 8), DRS_GREEN)

        metric = intervals if gap_mode == "interval" else gaps
        gap_val = metric.get(drv_id, 0)
        if pos == 0:
            gap_str = "LEAD"
            col = (100, 255, 100)
        else:
            gap_str = f"+{gap_val:.1f}s"
            col = (220, 145, 145) if gap_mode == "gap" else (240, 215, 145)

        if is_dimmed:
            col = muted_color(col)
        gap_surf = gap_font.render(gap_str, True, col)
        screen.blit(gap_surf, (panel_x + 204, y_pos + 10))

    # --- Seek Bar ---
    bar_y = screen_h - SEEK_BAR_HEIGHT
    pygame.draw.rect(screen, (10, 10, 10), (0, bar_y, screen_w, SEEK_BAR_HEIGHT))
    progress = t / total_time if total_time > 0 else 0
    progress_w = int(screen_w * clamp(progress, 0.0, 1.0))
    pygame.draw.rect(screen, (200, 50, 50), (0, bar_y, progress_w, SEEK_BAR_HEIGHT))
    pygame.draw.line(screen, (255, 255, 255), (progress_w, bar_y), (progress_w, screen_h), 2)

    return sidebar_rects


def draw_telemetry_overlay(screen, focused_driver, driver_info, frame_by_driver, max_speed):
    if not focused_driver or focused_driver not in frame_by_driver:
        return

    screen_w, screen_h = screen.get_size()
    panel_w = screen_w - SIDEBAR_WIDTH - 120
    x = 60
    y = screen_h - SEEK_BAR_HEIGHT - 82
    h = 62

    panel = pygame.Surface((panel_w, h), pygame.SRCALPHA)
    pygame.draw.rect(panel, (18, 20, 26, 220), (0, 0, panel_w, h), border_radius=8)
    pygame.draw.rect(panel, (70, 75, 90, 210), (0, 0, panel_w, h), width=1, border_radius=8)
    screen.blit(panel, (x, y))

    info = driver_info[focused_driver]
    state = frame_by_driver[focused_driver]
    title_font = pygame.font.SysFont("Consolas", 16, bold=True)
    label_font = pygame.font.SysFont("Consolas", 12)
    value_font = pygame.font.SysFont("Consolas", 18, bold=True)

    title = f"{info['Abbreviation']} TELEMETRY"
    screen.blit(title_font.render(title, True, TEXT_COLOR), (x + 14, y + 10))

    speed = state["speed"]
    throttle = clamp(state["throttle"] / 100.0, 0.0, 1.0)
    brake_raw = state["brake"]
    brake = clamp(brake_raw if brake_raw <= 1 else brake_raw / 100.0, 0.0, 1.0)

    bar_specs = [
        ("SPD", clamp(speed / max(max_speed, 1.0), 0.0, 1.0), speed_to_color(speed, max_speed), f"{int(speed)} km/h"),
        ("THR", throttle, (80, 220, 100), f"{int(throttle * 100)}%"),
        ("BRK", brake, (255, 90, 90), f"{int(brake * 100)}%"),
    ]

    bar_x = x + 170
    bar_y = y + 12
    bar_w = 150
    for idx, (label, ratio, color, value) in enumerate(bar_specs):
        bx = bar_x + idx * 185
        screen.blit(label_font.render(label, True, SUBTEXT_COLOR), (bx, bar_y))
        pygame.draw.rect(screen, (38, 42, 50), (bx, bar_y + 18, bar_w, 12), border_radius=4)
        pygame.draw.rect(screen, color, (bx, bar_y + 18, int(bar_w * ratio), 12), border_radius=4)
        screen.blit(label_font.render(value, True, TEXT_COLOR), (bx, bar_y + 35))

    gear = int(state["gear"])
    drs_text = "DRS OPEN" if state["drs_active"] else "DRS CLOSED"
    gear_surf = value_font.render(f"G{gear}", True, TEXT_COLOR)
    screen.blit(gear_surf, (x + panel_w - 118, y + 12))
    screen.blit(label_font.render(drs_text, True, DRS_GREEN if state["drs_active"] else SUBTEXT_COLOR), (x + panel_w - 118, y + 40))


def run_replay(drivers_data, bounds, timeline, metadata):
    if not drivers_data or not timeline:
        print("❌ Replay Error: No driver data or timeline available.")
        return

    driver_info = metadata["driver_info"]
    total_laps = metadata.get("total_laps", 0)
    fastest_driver = metadata.get("fastest_driver")
    fastest_lap_time = metadata.get("fastest_lap_time")

    # --- DATA PREP (Calculate CumDist BEFORE using it) ---
    max_speed = 1.0
    for drv_id, df in drivers_data.items():
        if df.empty:
            continue
        coords = df[["X", "Y"]].values
        diffs = coords[1:] - coords[:-1]
        dists = np.sqrt((diffs ** 2).sum(axis=1))
        dists = np.insert(dists, 0, 0)
        df["CumDist"] = np.cumsum(dists)
        if "Speed" in df.columns:
            max_speed = max(max_speed, safe_float(df["Speed"].max(), 0))

    # Estimate track length dynamically for lap calculation.
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

    pygame.init()
    screen_size = (1280, 850)
    screen = pygame.display.set_mode(screen_size)
    pygame.display.set_caption(f"F1 Telemetry Pro | {metadata.get('race_name', 'Race')}")
    clock = pygame.time.Clock()

    tag_font = pygame.font.SysFont("Arial", 10, bold=True)
    badge_font = pygame.font.SysFont("Consolas", 10, bold=True)

    track_segments = build_track_segments(drivers_data, bounds, screen_size)

    time_val = timeline[0]
    total_time = timeline[-1]

    running = True
    paused = False
    speed = 1.0
    show_heatmap = True
    gap_mode = "gap"
    focused_driver = None
    sidebar_rects = {}

    drv_colors = {drv: parse_team_color(info["TeamColor"]) for drv, info in driver_info.items()}
    trails = {drv: [] for drv in drivers_data}
    row_positions = {}

    while running:
        screen.fill(BG_COLOR)
        dt = clock.get_time() / 1000.0
        screen_w, screen_h = screen.get_size()
        pending_click = None

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                if event.key == pygame.K_SPACE:
                    paused = not paused
                if event.key == pygame.K_1:
                    speed = 0.5
                if event.key == pygame.K_2:
                    speed = 1.0
                if event.key == pygame.K_3:
                    speed = 2.0
                if event.key == pygame.K_4:
                    speed = 4.0
                if event.key == pygame.K_UP:
                    speed = min(speed + 0.5, 10.0)
                if event.key == pygame.K_DOWN:
                    speed = max(speed - 0.5, 0.0)
                if event.key == pygame.K_RIGHT:
                    time_val += 5.0
                if event.key == pygame.K_LEFT:
                    time_val -= 5.0
                if event.key == pygame.K_h:
                    show_heatmap = not show_heatmap
                if event.key == pygame.K_g:
                    gap_mode = "interval" if gap_mode == "gap" else "gap"
                if event.key == pygame.K_f:
                    focused_driver = None
                if event.key == pygame.K_r:
                    time_val = timeline[0]
                    trails = {drv: [] for drv in drivers_data}
                    row_positions = {}

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = pygame.mouse.get_pos()
                if my > screen_h - SEEK_BAR_HEIGHT:
                    ratio = mx / screen_w
                    time_val = ratio * total_time
                    trails = {drv: [] for drv in drivers_data}
                else:
                    pending_click = (mx, my)

        if not paused:
            time_val += dt * speed
            if time_val > total_time:
                time_val = timeline[0]
                trails = {drv: [] for drv in drivers_data}

        time_val = max(timeline[0], min(time_val, total_time))

        draw_track(screen, track_segments, show_heatmap, max_speed)

        # --- UPDATE DRIVERS ---
        current_frame_data = []
        frame_by_driver = {}

        for drv_code, df in drivers_data.items():
            if df.empty:
                continue

            state = get_interpolated_state(df, time_val)
            sx, sy = scale_point(state["X"], state["Y"], bounds, screen_size)
            drs_active = is_drs_active(state["DRS"])
            in_pit = state["Speed"] < 5 and time_val > timeline[0] + 2

            trails[drv_code].append((sx, sy, state["Speed"]))
            if len(trails[drv_code]) > TRAIL_LENGTH:
                trails[drv_code].pop(0)

            frame_state = {
                "id": drv_code,
                "dist": state["CumDist"],
                "lap": state["LapNumber"],
                "sx": sx,
                "sy": sy,
                "speed": state["Speed"],
                "throttle": state["Throttle"],
                "brake": state["Brake"],
                "gear": state["nGear"],
                "drs": state["DRS"],
                "drs_active": drs_active,
                "in_pit": in_pit,
            }
            current_frame_data.append(frame_state)
            frame_by_driver[drv_code] = frame_state

        if current_frame_data:
            current_frame_data.sort(key=lambda x: x["dist"], reverse=True)
            leaderboard_order = [d["id"] for d in current_frame_data]

            leader_dist = current_frame_data[0]["dist"]
            current_lap = current_frame_data[0]["lap"]

            if current_lap == 0:
                current_lap = int(leader_dist / track_length_approx) + 1

            gaps = {}
            intervals = {}
            for pos, d in enumerate(current_frame_data):
                gaps[d["id"]] = (leader_dist - d["dist"]) / 70.0
                if pos == 0:
                    intervals[d["id"]] = 0.0
                else:
                    car_ahead = current_frame_data[pos - 1]
                    intervals[d["id"]] = (car_ahead["dist"] - d["dist"]) / 70.0

            list_start_y = HEADER_HEIGHT + 40
            row_h = 36
            smoothing = min(1.0, dt * 9.0)
            for pos, drv_id in enumerate(leaderboard_order):
                target_y = list_start_y + (pos * row_h)
                if drv_id not in row_positions:
                    row_positions[drv_id] = target_y
                else:
                    row_positions[drv_id] = lerp(row_positions[drv_id], target_y, smoothing)

            if pending_click:
                clicked_driver = None
                for drv_id, rect in sidebar_rects.items():
                    if rect.collidepoint(pending_click):
                        clicked_driver = drv_id
                        break

                if clicked_driver is None:
                    px, py = pending_click
                    for d in current_frame_data:
                        if math.hypot(px - d["sx"], py - d["sy"]) <= 16:
                            clicked_driver = d["id"]
                            break

                if clicked_driver:
                    focused_driver = None if focused_driver == clicked_driver else clicked_driver

            # Draw unfocused cars first, then focused car on top.
            draw_order = [d for d in current_frame_data if d["id"] != focused_driver]
            draw_order += [d for d in current_frame_data if d["id"] == focused_driver]

            for d in draw_order:
                drv_code = d["id"]
                pts = trails[drv_code]
                if len(pts) <= 1:
                    continue

                base_color = drv_colors[drv_code]
                is_dimmed = focused_driver is not None and drv_code != focused_driver
                color = muted_color(base_color) if is_dimmed else base_color

                for i in range(len(pts) - 1):
                    p1 = (pts[i][0], pts[i][1])
                    p2 = (pts[i + 1][0], pts[i + 1][1])
                    width = trail_width(pts[i + 1][2], max_speed)
                    if drv_code == focused_driver:
                        pygame.draw.line(screen, (5, 5, 8), p1, p2, width + 4)
                        width += 2
                    pygame.draw.line(screen, color, p1, p2, width)

            for d in draw_order:
                drv_id = d["id"]
                c = drv_colors[drv_id]
                is_dimmed = focused_driver is not None and drv_id != focused_driver
                if is_dimmed:
                    c = muted_color(c)

                sx, sy = d["sx"], d["sy"]
                radius = 9 if drv_id == focused_driver else 7

                if drv_id == focused_driver:
                    pygame.draw.circle(screen, ACCENT_BLUE, (sx, sy), 14, width=2)

                if d["in_pit"]:
                    flash = 0.5 + 0.5 * math.sin(time_val * 7)
                    pit_color = lerp_color((120, 80, 10), PIT_YELLOW, flash)
                    pygame.draw.circle(screen, pit_color, (sx, sy), radius + 5, width=3)

                pygame.draw.circle(screen, (0, 0, 0), (sx, sy), radius + 2)
                pygame.draw.circle(screen, c, (sx, sy), radius)
                pygame.draw.circle(screen, (255, 255, 255), (sx, sy), 2)

                label_color = (105, 105, 105) if is_dimmed else (230, 230, 230)
                lbl = tag_font.render(driver_info[drv_id]["Abbreviation"], True, label_color)
                screen.blit(lbl, (sx + 12, sy - 12))

                badge_y = sy + 4
                if d["drs_active"]:
                    draw_badge(screen, "DRS", badge_font, sx + 12, badge_y, (0, 40, 8), DRS_GREEN)
                    badge_y += 16
                if d["in_pit"]:
                    draw_badge(screen, "PIT", badge_font, sx + 12, badge_y, (30, 20, 0), PIT_YELLOW)

            pit_drivers = {d["id"] for d in current_frame_data if d["in_pit"]}
            drs_drivers = {d["id"] for d in current_frame_data if d["drs_active"]}

            draw_telemetry_overlay(screen, focused_driver, driver_info, frame_by_driver, max_speed)
            sidebar_rects = draw_dashboard(
                screen,
                time_val,
                speed,
                driver_info,
                leaderboard_order,
                gaps,
                intervals,
                current_lap,
                total_laps,
                total_time,
                gap_mode,
                focused_driver,
                fastest_driver,
                fastest_lap_time,
                pit_drivers,
                drs_drivers,
                row_positions
            )

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()
