import pygame

_FONTS = {}
def get_font(name, size, bold=False):
    key = (name, size, bold)
    if key not in _FONTS:
        _FONTS[key] = pygame.font.SysFont(name, size, bold=bold)
    return _FONTS[key]
import sys
import numpy as np
import math
from track_geo import (compute_circuit_rotation, compute_track_normals,
                       build_track_edges, rotate_point, label_offset_from_normal)
from tyre_model import compound_color as tyre_compound_color

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
SECTOR_GREEN = (80, 255, 120)
SECTOR_FLASH_DURATION = 1.5
SECTOR_FLASH_COLORS = {
    "overall_best": FASTEST_PURPLE,
    "personal_best": SECTOR_GREEN,
    "normal": PIT_YELLOW
}
TRAIL_LENGTH = 28
SIDEBAR_WIDTH = 260
HEADER_HEIGHT = 76
SEEK_BAR_HEIGHT = 20

_COMPOUND_COLORS = {
    "SOFT": (220, 40, 40), "MEDIUM": (220, 190, 30),
    "HARD": (240, 240, 240), "INTERMEDIATE": (60, 180, 60), "WET": (60, 100, 220),
    "HYPERSOFT": (255, 105, 180), "ULTRASOFT": (138, 43, 226), "SUPERSOFT": (255, 69, 0),
    "UNKNOWN": (150, 150, 150), "nan": (150, 150, 150)
}

def tyre_compound_color(name):
    return _COMPOUND_COLORS.get(str(name).upper().strip(), (150, 150, 150))



def clamp(value, low, high):
    return max(low, min(value, high))


def lerp(a, b, alpha):
    return a + (b - a) * alpha


def lerp_color(a, b, alpha):
    alpha = clamp(alpha, 0.0, 1.0)
    return tuple(int(lerp(a[i], b[i], alpha)) for i in range(3))

def catmull_rom(p0, p1, p2, p3, alpha):
    t = alpha
    q = (
        (-t**3 + 2*t**2 - t) / 2 * p0 +
        (3*t**3 - 5*t**2 + 2) / 2 * p1 +
        (-3*t**3 + 4*t**2 + t) / 2 * p2 +
        (t**3 - t**2) / 2 * p3
    )
    return q


def muted_color(color, amount=0.2):
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
    ratio = clamp(speed / max(max_speed, 1.0), 0.0, 1.0)
    return max(1, int(round(lerp(1, 5, ratio))))


def get_sector_flash(info, t):
    active_event = None
    for event in info.get("SectorEvents", []):
        age = t - event.get("time", -9999)
        if 0 <= age <= SECTOR_FLASH_DURATION:
            if active_event is None or event["time"] > active_event["time"]:
                active_event = event

    if not active_event:
        return None

    event_type = active_event.get("type", "normal")
    label = {
        "overall_best": "BEST",
        "personal_best": "PB",
        "normal": "SEC"
    }.get(event_type, "SEC")

    return {
        "color": SECTOR_FLASH_COLORS.get(event_type, PIT_YELLOW),
        "label": f"S{active_event.get('sector', '')} {label}",
        "type": event_type,
        "age": t - active_event["time"]
    }


def is_in_pit_window(info, t):
    return any(window["start"] <= t <= window["end"] for window in info.get("PitWindows", []))


def get_live_fastest_lap(driver_info, t):
    fastest_driver = None
    fastest_lap_time = None
    personal_bests = {}

    for drv_id, info in driver_info.items():
        best_time = None
        for event in info.get("LapEvents", []):
            if event.get("time", 0) > t:
                continue

            lap_time = event.get("lap_time")
            if lap_time is not None and (best_time is None or lap_time < best_time):
                best_time = lap_time

        if best_time is not None:
            personal_bests[drv_id] = best_time
            if fastest_lap_time is None or best_time < fastest_lap_time:
                fastest_driver = drv_id
                fastest_lap_time = best_time

    return fastest_driver, fastest_lap_time, personal_bests


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
    last_p = None
    
    for i in range(len(reference_df) - 1):
        row = reference_df.iloc[i]
        next_row = reference_df.iloc[i + 1]
        
        # Prevent straight-line anomalies from telemetry dropouts
        dx = next_row["X"] - row["X"]
        dy = next_row["Y"] - row["Y"]
        if math.hypot(dx, dy) > 150:
            last_p = None
            continue
            
        p1 = scale_point(row["X"], row["Y"], bounds, screen_size)
        p2 = scale_point(next_row["X"], next_row["Y"], bounds, screen_size)
        
        if last_p is None:
            last_p = p1
            
        # Optimization: Only create a new segment if we've moved at least 3 pixels
        if math.hypot(p2[0] - last_p[0], p2[1] - last_p[1]) < 3:
            continue
            
        speed = safe_float(next_row.get("Speed", 0))
        drs = is_drs_active(next_row.get("DRS", 0))
        segments.append({"p1": last_p, "p2": p2, "speed": speed, "drs": drs})
        last_p = p2

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
    
    # Try to get p0 and p3 for catmull-rom
    p0_row = df.iloc[max(0, idx - 2)]
    p3_row = df.iloc[min(len(df) - 1, idx + 1)]
    
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

        v1 = safe_float(t0_row.get(key, default), default)
        v2 = safe_float(t1_row.get(key, default), default)
        
        if key in ("X", "Y"):
            v0 = safe_float(p0_row.get(key, default), default)
            v3 = safe_float(p3_row.get(key, default), default)
            state[key] = catmull_rom(v0, v1, v2, v3, alpha)
        else:
            state[key] = v1 + (v2 - v1) * alpha

    return state


def draw_track(screen, track_segments, show_heatmap, max_speed, camera=None, status_color=None):
    if not track_segments:
        return

    if camera is None:
        camera = {"scale": 1.0, "target": (0, 0), "center": (0, 0)}

    points = [apply_camera(track_segments[0]["p1"], camera)] + [
        apply_camera(segment["p2"], camera) for segment in track_segments
    ]
    if len(points) > 1:
        pygame.draw.lines(screen, TRACK_OUTLINE, False, points, 18)

    if show_heatmap:
        for segment in track_segments:
            pygame.draw.line(
                screen,
                speed_to_color(segment["speed"], max_speed),
                apply_camera(segment["p1"], camera),
                apply_camera(segment["p2"], camera),
                7
            )
    elif len(points) > 1:
        track_col = status_color if status_color else TRACK_COLOR
        pygame.draw.lines(screen, track_col, False, points, 7)

    overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    for segment in track_segments:
        if segment["drs"]:
            pygame.draw.line(
                overlay,
                (*DRS_GREEN, 110),
                apply_camera(segment["p1"], camera),
                apply_camera(segment["p2"], camera),
                12
            )
    screen.blit(overlay, (0, 0))


def track_view_center(screen_size):
    screen_w, screen_h = screen_size
    return ((screen_w - SIDEBAR_WIDTH) // 2, HEADER_HEIGHT + (screen_h - HEADER_HEIGHT - SEEK_BAR_HEIGHT) // 2)


def build_camera(focused_driver, frame_by_driver, screen_size):
    center = track_view_center(screen_size)
    if focused_driver and focused_driver in frame_by_driver:
        target = (frame_by_driver[focused_driver]["gx"], frame_by_driver[focused_driver]["gy"])
        return {"scale": 1.45, "target": target, "center": center}
    return {"scale": 1.0, "target": center, "center": center}


def apply_camera(point, camera):
    scale = camera.get("scale", 1.0)
    if scale == 1.0:
        return int(point[0]), int(point[1])

    target_x, target_y = camera["target"]
    center_x, center_y = camera["center"]
    return (
        int(center_x + (point[0] - target_x) * scale),
        int(center_y + (point[1] - target_y) * scale)
    )


def draw_dashed_line(surface, color, start, end, width=2, dash_length=10, gap_length=7):
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length <= 0:
        return

    ux = dx / length
    uy = dy / length
    pos = 0
    while pos < length:
        dash_end = min(pos + dash_length, length)
        dash_start_pt = (int(x1 + ux * pos), int(y1 + uy * pos))
        dash_end_pt = (int(x1 + ux * dash_end), int(y1 + uy * dash_end))
        pygame.draw.line(surface, color, dash_start_pt, dash_end_pt, width)
        pos += dash_length + gap_length


def draw_ghost_trail(screen, points, color, camera):
    if len(points) <= 1:
        return

    overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    ghost_color = (*color, 105)
    for i in range(len(points) - 1):
        p1 = apply_camera((points[i][0], points[i][1]), camera)
        p2 = apply_camera((points[i + 1][0], points[i + 1][1]), camera)
        draw_dashed_line(overlay, ghost_color, p1, p2, width=3)
    screen.blit(overlay, (0, 0))


def draw_minimap(screen, track_segments, current_frame_data, focused_driver, ghost_driver, drv_colors):
    if not track_segments or focused_driver is None:
        return

    rect = pygame.Rect(20, HEADER_HEIGHT + 14, 210, 145)
    pygame.draw.rect(screen, (16, 18, 24), rect, border_radius=8)
    pygame.draw.rect(screen, UI_BORDER, rect, width=1, border_radius=8)

    points = [track_segments[0]["p1"]] + [segment["p2"] for segment in track_segments]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    range_x = max(1, max_x - min_x)
    range_y = max(1, max_y - min_y)
    pad = 14

    def mini_point(point):
        x = rect.x + pad + int((point[0] - min_x) / range_x * (rect.w - pad * 2))
        y = rect.y + pad + int((point[1] - min_y) / range_y * (rect.h - pad * 2))
        return x, y

    mini_points = [mini_point(point) for point in points]
    if len(mini_points) > 1:
        pygame.draw.lines(screen, (70, 74, 86), False, mini_points, 2)

    mini_font = get_font("Consolas", 11, bold=True)
    screen.blit(mini_font.render("MINI MAP", True, SUBTEXT_COLOR), (rect.x + 10, rect.y + 8))

    for d in current_frame_data:
        drv_id = d["id"]
        pos = mini_point((d["gx"], d["gy"]))
        radius = 4 if drv_id in (focused_driver, ghost_driver) else 3
        color = drv_colors.get(drv_id, (220, 220, 220))
        if drv_id == ghost_driver:
            pygame.draw.circle(screen, (245, 245, 245), pos, radius + 2, width=1)
        if drv_id == focused_driver:
            pygame.draw.circle(screen, ACCENT_BLUE, pos, radius + 3, width=1)
        pygame.draw.circle(screen, color, pos, radius)


def draw_delta_panel(screen, focused_driver, ghost_driver, driver_info, frame_by_driver, delta_history):
    if not focused_driver or not ghost_driver:
        return
    if focused_driver not in frame_by_driver or ghost_driver not in frame_by_driver:
        return

    rect = pygame.Rect(20, HEADER_HEIGHT + 170, 210, 105)
    pygame.draw.rect(screen, (16, 18, 24), rect, border_radius=8)
    pygame.draw.rect(screen, UI_BORDER, rect, width=1, border_radius=8)

    focus_abbr = driver_info[focused_driver]["Abbreviation"]
    ghost_abbr = driver_info[ghost_driver]["Abbreviation"]
    delta = delta_history[-1] if delta_history else 0.0

    font_title = get_font("Consolas", 12, bold=True)
    font_value = get_font("Consolas", 16, bold=True)
    screen.blit(font_title.render(f"DELTA {focus_abbr} vs {ghost_abbr}", True, SUBTEXT_COLOR), (rect.x + 10, rect.y + 8))

    label = f"{ghost_abbr} {'+' if delta >= 0 else ''}{delta:.2f}s"
    value_color = (255, 120, 120) if delta > 0 else (120, 255, 145)
    screen.blit(font_value.render(label, True, value_color), (rect.x + 10, rect.y + 28))

    if len(delta_history) < 2:
        return

    chart = pygame.Rect(rect.x + 10, rect.y + 58, rect.w - 20, 34)
    pygame.draw.line(screen, (70, 74, 86), (chart.x, chart.centery), (chart.right, chart.centery), 1)
    visible = delta_history[-80:]
    max_abs = max(0.1, max(abs(value) for value in visible))
    points = []
    for idx, value in enumerate(visible):
        x = chart.x + int(idx / max(1, len(visible) - 1) * chart.w)
        y = chart.centery - int((value / max_abs) * (chart.h // 2))
        points.append((x, y))
    if len(points) > 1:
        pygame.draw.lines(screen, FASTEST_PURPLE, False, points, 2)


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
    row_positions,
    active_overtakes,
    frame_by_driver
):
    screen_w, screen_h = screen.get_size()

    # --- Top Header ---
    pygame.draw.rect(screen, UI_BG, (0, 0, screen_w, HEADER_HEIGHT))
    pygame.draw.line(screen, UI_BORDER, (0, HEADER_HEIGHT), (screen_w, HEADER_HEIGHT), 2)

    minutes = int(t // 60)
    seconds = int(t % 60)
    millis = int((t % 1) * 100)

    font_large = get_font("Consolas", 28, bold=True)
    font_label = get_font("Consolas", 12, bold=True)
    font_small = get_font("Consolas", 12)
    font_badge = get_font("Consolas", 11, bold=True)

    # 1. Race Time (Left)
    screen.blit(font_label.render("RACE TIME", True, (130, 130, 140)), (22, 12))
    time_val_str = f"{minutes:02}:{seconds:02}.{millis:02}"
    screen.blit(font_large.render(time_val_str, True, (240, 240, 240)), (20, 26))

    # 2. Lap Counter (Center)
    lap_val_str = f"{int(current_lap)} / {total_laps}"
    lap_surf = font_large.render(lap_val_str, True, (255, 255, 255))
    center_x = (screen_w - SIDEBAR_WIDTH) // 2
    screen.blit(font_label.render("CURRENT LAP", True, (130, 130, 140)), (center_x - lap_surf.get_width() // 2, 12))
    screen.blit(lap_surf, (center_x - lap_surf.get_width() // 2, 26))

    # 3. Playback Speed (Right)
    speed_surf = font_large.render(f"{speed:g}x", True, ACCENT_BLUE)
    speed_rect = speed_surf.get_rect(right=screen_w - SIDEBAR_WIDTH - 22, top=26)
    screen.blit(font_label.render("PLAYBACK", True, (130, 130, 140)), (speed_rect.x, 12))
    screen.blit(speed_surf, speed_rect)

    # 4. Fastest Lap Info (Bottom Left)
    if fastest_driver and fastest_driver in driver_info:
        fl_text = f"FASTEST LAP: {driver_info[fastest_driver]['Abbreviation']} ({format_lap_time(fastest_lap_time)})"
        screen.blit(font_small.render(fl_text, True, FASTEST_PURPLE), (22, 58))

    # 5. Help Text (Bottom Right)
    help_text = "[Click] Focus  [Shift+Click] Ghost  [H] Heatmap  [G] Gap  [M] RaceCtrl  [F] Clear"
    help_surf = font_small.render(help_text, True, (100, 100, 110))
    help_rect = help_surf.get_rect(right=screen_w - SIDEBAR_WIDTH - 22, top=58)
    screen.blit(help_surf, help_rect)

    # --- Side Leaderboard ---
    panel_w = SIDEBAR_WIDTH
    panel_x = screen_w - panel_w
    panel_y = HEADER_HEIGHT
    panel_h = screen_h - HEADER_HEIGHT - SEEK_BAR_HEIGHT

    pygame.draw.rect(screen, UI_BG, (panel_x, panel_y, panel_w, panel_h))
    pygame.draw.line(screen, UI_BORDER, (panel_x, panel_y), (panel_x, screen_h - SEEK_BAR_HEIGHT), 2)

    header_font = get_font("Consolas", 13, bold=True)
    pygame.draw.rect(screen, (30, 35, 45), (panel_x, panel_y, panel_w, 35))

    gap_header = "INT" if gap_mode == "interval" else "GAP"
    screen.blit(header_font.render("POS", True, (120, 120, 120)), (panel_x + 10, panel_y + 10))
    screen.blit(header_font.render("DRIVER", True, (120, 120, 120)), (panel_x + 50, panel_y + 10))
    screen.blit(header_font.render(gap_header, True, (120, 120, 120)), (panel_x + 204, panel_y + 10))

    row_h = 36
    name_font = get_font("Consolas", 18, bold=True)
    gap_font = get_font("Consolas", 15)

    sidebar_rects = {}
    ordered_positions = {drv_id: pos for pos, drv_id in enumerate(leaderboard_order)}

    for drv_id in leaderboard_order:
        pos = ordered_positions[drv_id]
        info = driver_info[drv_id]
        y_pos = int(row_positions.get(drv_id, panel_y + 40 + (pos * row_h)))

        if y_pos + row_h > screen_h - SEEK_BAR_HEIGHT:
            continue

        ot_attacker = any(o["attacker"] == drv_id for o in active_overtakes)
        ot_defender = any(o["defender"] == drv_id for o in active_overtakes)

        is_dimmed = focused_driver is not None and drv_id != focused_driver
        bg_col = (25, 30, 40) if pos % 2 == 0 else (22, 25, 30)
        if pos == 0:
            bg_col = (35, 40, 50)
            
        if ot_attacker:
            pulse = 0.5 + 0.5 * math.sin(t * 12)
            bg_col = lerp_color(bg_col, (30, 110, 50), pulse)
        elif ot_defender:
            pulse = 0.5 + 0.5 * math.sin(t * 12)
            bg_col = lerp_color(bg_col, (110, 40, 40), pulse)
        elif is_dimmed:
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

        drv_lap = int(frame_by_driver[drv_id]["lap"])
        lap_stints = info.get("LapStints", {})
        
        stint = lap_stints.get(drv_lap)
        if not stint and lap_stints:
            past = [k for k in lap_stints if k <= drv_lap]
            key = max(past) if past else min(lap_stints)
            stint = lap_stints[key]
        elif not stint:
            stint = {}
            
        compound = str(stint.get("Compound", "HARD")).upper()
        stint_start = stint.get("StintStartLap", drv_lap)
        tyre_life = max(1, drv_lap - stint_start + 1) if lap_stints else int(stint.get("TyreLife", 0))
        
        dot_x = panel_x + 94
        # Tyre health ring with degradation model
        _health_pct = 100
        if hasattr(draw_dashboard, '_tyre_model') and draw_dashboard._tyre_model and draw_dashboard._tyre_model.fitted:
            _h = draw_dashboard._tyre_model.get_health(compound, int(tyre_life))
            _health_pct = _h["health"]
        else:
            _health_pct = max(0, int(100 - tyre_life * 2.5))
        draw_tyre_health_ring(screen, dot_x, y_pos + 15, 8, _health_pct, compound)
        val_font = get_font("Consolas", 11, bold=True)
        life_surf = val_font.render(f"{tyre_life}L", True, SUBTEXT_COLOR)
        screen.blit(life_surf, (dot_x + 13, y_pos + 10))
        
        badge_x = dot_x + 36
        
        if ot_attacker:
            tri_x = badge_x + 6
            tri_y = y_pos + 17
            pygame.draw.polygon(screen, (80, 255, 120), [(tri_x, tri_y-5), (tri_x-5, tri_y+4), (tri_x+5, tri_y+4)])
            badge_x += 18
        elif ot_defender:
            tri_x = badge_x + 6
            tri_y = y_pos + 17
            pygame.draw.polygon(screen, (255, 80, 80), [(tri_x, tri_y+4), (tri_x-5, tri_y-5), (tri_x+5, tri_y-5)])
            badge_x += 18

        if drv_id == fastest_driver:
            crown_surf = name_font.render("♕", True, FASTEST_PURPLE)
            screen.blit(crown_surf, (badge_x, y_pos + 6))
            badge_x += 26
        if drv_id in pit_drivers:
            flash = 0.5 + 0.5 * math.sin(t * 8)
            pit_color = lerp_color((120, 80, 10), PIT_YELLOW, flash)
            pit_dur = pit_drivers[drv_id]
            if pit_dur < 120:
                badge_rect = draw_badge(screen, f"PIT {pit_dur:.1f}s", font_badge, badge_x, y_pos + 9, (30, 20, 0), pit_color)
            else:
                badge_rect = draw_badge(screen, "OUT", font_badge, badge_x, y_pos + 9, (30, 0, 0), (255, 60, 60))
            badge_x = badge_rect.right + 4
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
    title_font = get_font("Consolas", 16, bold=True)
    label_font = get_font("Consolas", 12)
    value_font = get_font("Consolas", 18, bold=True)

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


def blend_color(fg: tuple, bg: tuple, alpha: float) -> tuple:
    return tuple(int(f * alpha + b * (1 - alpha)) for f, b in zip(fg, bg))

def draw_similarity_panel(screen, focused_driver, driver_info, similarity_matrix):
    screen_w, screen_h = screen.get_size()
    panel_w = SIDEBAR_WIDTH
    panel_x = screen_w - panel_w
    panel_y = HEADER_HEIGHT

    # Draw Background
    pygame.draw.rect(screen, UI_BG, (panel_x, panel_y, panel_w, screen_h - panel_y))
    pygame.draw.line(screen, UI_BORDER, (panel_x, panel_y), (panel_x, screen_h), 2)

    font_header = get_font("Consolas", 14, bold=True)
    font_name = get_font("Arial", 14, bold=True)
    font_val = get_font("Consolas", 13)

    focused_abbr = driver_info.get(focused_driver, {}).get("Abbreviation", focused_driver)
    header = f"STYLE SIMILARITY — {focused_abbr}"
    screen.blit(font_header.render(header, True, (210, 210, 210)), (panel_x + 16, panel_y + 16))
    pygame.draw.line(screen, UI_BORDER, (panel_x, panel_y + 40), (screen_w, panel_y + 40), 1)

    if similarity_matrix is None or focused_driver not in similarity_matrix:
        screen.blit(font_val.render("No data", True, (120, 120, 120)), (panel_x + 16, panel_y + 60))
        return {}

    scores = similarity_matrix[focused_driver]
    # Filter valid
    valid_scores = [(drv, val) for drv, val in scores.items() if drv != focused_driver and not np.isnan(val)]
    if not valid_scores:
        screen.blit(font_val.render("No data", True, (120, 120, 120)), (panel_x + 16, panel_y + 60))
        return {}

    # Sort lowest first
    valid_scores.sort(key=lambda x: x[1])
    max_score = max(x[1] for x in valid_scores) if valid_scores else 1.0

    y = panel_y + 50
    for drv, score in valid_scores:
        info = driver_info.get(drv, {})
        abbr = info.get("Abbreviation", drv)
        c_hex = info.get("TeamColor", "#CCCCCC").lstrip("#")
        try:
            team_color = (int(c_hex[0:2], 16), int(c_hex[2:4], 16), int(c_hex[4:6], 16))
        except:
            team_color = (200, 200, 200)

        # Draw stripe
        pygame.draw.rect(screen, team_color, (panel_x + 16, y, 4, 20))
        
        # Draw bar
        bar_w = int((score / max_score) * (panel_w - 110))
        bar_color = blend_color(team_color, UI_BG, 0.6)
        pygame.draw.rect(screen, bar_color, (panel_x + 24, y + 2, bar_w, 16))

        # Text
        screen.blit(font_name.render(abbr, True, (240, 240, 240)), (panel_x + 28, y + 2))
        screen.blit(font_val.render(f"{score:.2f}", True, (190, 190, 190)), (panel_x + panel_w - 50, y + 2))

        y += 28

    return {}



# ---------------------------------------------------------------------------
# Track status colors  (FIA status codes)
# ---------------------------------------------------------------------------
_STATUS_TRACK_COLORS = {
    "1": (60, 60, 70),      # AllClear / Green
    "2": (200, 180, 0),     # Yellow
    "4": (180, 100, 30),    # Safety Car
    "5": (200, 30, 30),     # Red Flag
    "6": (180, 130, 50),    # VSC
    "7": (180, 130, 50),    # VSC Ending
}

def _get_track_status_at(track_statuses, t):
    """Return the status code active at time *t*."""
    current = "1"
    for s in track_statuses:
        if s["time"] <= t:
            current = s["status"]
        else:
            break
    return current

def _status_label(code):
    return {"1": "", "2": "YELLOW", "4": "SAFETY CAR",
            "5": "RED FLAG", "6": "VSC", "7": "VSC ENDING"}.get(code, "")


# ---------------------------------------------------------------------------
# Weather panel
# ---------------------------------------------------------------------------
def draw_weather_panel(screen, weather_timeline, t):
    """Small translucent weather overlay in the top-left area."""
    if not weather_timeline:
        return
    # Find closest weather sample
    best = weather_timeline[0]
    for w in weather_timeline:
        if w["time"] <= t:
            best = w
        else:
            break
    panel_w, panel_h = 195, 140
    px, py = 18, HEADER_HEIGHT + 14
    bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    bg.fill((16, 18, 24, 210))
    screen.blit(bg, (px, py))
    pygame.draw.rect(screen, UI_BORDER, (px, py, panel_w, panel_h), 1, border_radius=6)

    fnt = get_font("Consolas", 12, bold=True)
    fnt_val = get_font("Consolas", 13)
    screen.blit(fnt.render("WEATHER", True, (180, 180, 190)), (px + 10, py + 8))
    items = [
        ("Air",   f"{best.get('AirTemp', 0):.1f} C"),
        ("Track", f"{best.get('TrackTemp', 0):.1f} C"),
        ("Humid", f"{best.get('Humidity', 0):.0f}%"),
        ("Wind",  f"{best.get('WindSpeed', 0):.0f} km/h"),
        ("Rain",  "Yes" if best.get("Rainfall", 0) > 0 else "No"),
    ]
    for i, (label, val) in enumerate(items):
        y = py + 28 + i * 20
        screen.blit(fnt.render(label, True, SUBTEXT_COLOR), (px + 10, y))
        screen.blit(fnt_val.render(val, True, TEXT_COLOR), (px + 75, y))


# ---------------------------------------------------------------------------
# Race control feed (scrolling)
# ---------------------------------------------------------------------------
def draw_race_control_feed(screen, rc_messages, t, screen_w, show_feed):
    """Draw recent race control messages as a scrolling feed."""
    if not show_feed or not rc_messages:
        return
    recent = [m for m in rc_messages if m["time"] <= t][-8:]
    if not recent:
        return
    panel_w = 340
    panel_h = 20 + len(recent) * 18
    px = screen_w - SIDEBAR_WIDTH - panel_w - 15
    py = HEADER_HEIGHT + 14
    bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    bg.fill((16, 18, 24, 210))
    screen.blit(bg, (px, py))
    pygame.draw.rect(screen, UI_BORDER, (px, py, panel_w, panel_h), 1, border_radius=6)
    fnt = get_font("Consolas", 11)
    fnt_b = get_font("Consolas", 11, bold=True)
    screen.blit(fnt_b.render("RACE CONTROL", True, (180, 180, 190)), (px + 8, py + 4))
    for i, msg in enumerate(reversed(recent)):
        y = py + 22 + i * 18
        flag = msg.get("flag", "")
        col = (220, 220, 220)
        if "YELLOW" in flag.upper():
            col = (220, 200, 0)
        elif "RED" in flag.upper():
            col = (220, 50, 50)
        elif "GREEN" in flag.upper():
            col = (60, 220, 80)
        elif "BLUE" in flag.upper():
            col = (80, 140, 255)
        mins = int(msg["time"] // 60)
        secs = int(msg["time"] % 60)
        ts = f"{mins:02}:{secs:02}"
        text = msg.get("message", "")[:40]
        screen.blit(fnt.render(f"{ts}  {text}", True, col), (px + 8, y))


# ---------------------------------------------------------------------------
# Progress bar with event markers
# ---------------------------------------------------------------------------
def draw_progress_bar_with_markers(screen, t, total_time, screen_w, screen_h,
                                   track_statuses, rc_messages, driver_info):
    """Seek bar with colored status bands and event markers."""
    bar_h = SEEK_BAR_HEIGHT
    bar_y = screen_h - bar_h
    pygame.draw.rect(screen, (10, 10, 10), (0, bar_y, screen_w, bar_h))

    # Draw status color bands
    if track_statuses and total_time > 0:
        for i in range(len(track_statuses)):
            s = track_statuses[i]
            end_t = track_statuses[i + 1]["time"] if i + 1 < len(track_statuses) else total_time
            x0 = int(s["time"] / total_time * screen_w)
            x1 = int(end_t / total_time * screen_w)
            col = _STATUS_TRACK_COLORS.get(s["status"], (30, 30, 35))
            if s["status"] != "1":
                dim = (col[0] // 3, col[1] // 3, col[2] // 3)
                pygame.draw.rect(screen, dim, (x0, bar_y, x1 - x0, bar_h))

    # Pit stop markers (small triangles)
    for drv_id, info in driver_info.items():
        for pw in info.get("PitWindows", []):
            x = int(pw["start"] / total_time * screen_w) if total_time > 0 else 0
            pygame.draw.polygon(screen, (220, 190, 40),
                                [(x, bar_y), (x - 3, bar_y - 6), (x + 3, bar_y - 6)])

    # Progress fill
    progress = t / total_time if total_time > 0 else 0
    progress_w = int(screen_w * clamp(progress, 0.0, 1.0))
    pygame.draw.rect(screen, (200, 50, 50), (0, bar_y, progress_w, bar_h))
    pygame.draw.line(screen, (255, 255, 255), (progress_w, bar_y), (progress_w, screen_h), 2)


# ---------------------------------------------------------------------------
# Race controls HUD (clickable)
# ---------------------------------------------------------------------------
_CTRL_BTN_SIZE = 32

def _ctrl_button_layout(screen_w):
    """Return list of (name, center_x, center_y) for control buttons."""
    cy = HEADER_HEIGHT + 14 + 170 + 30
    cx = 110
    spacing = _CTRL_BTN_SIZE + 12
    return [
        ("rewind",  cx,               cy),
        ("play",    cx + spacing,      cy),
        ("forward", cx + 2 * spacing,  cy),
    ]

def draw_race_controls(screen, paused, speed, screen_w):
    """Render play/pause/speed buttons."""
    buttons = _ctrl_button_layout(screen_w)
    fnt = get_font("Consolas", 11, bold=True)
    for name, cx, cy in buttons:
        r = _CTRL_BTN_SIZE // 2
        pygame.draw.circle(screen, (30, 35, 45), (cx, cy), r)
        pygame.draw.circle(screen, UI_BORDER, (cx, cy), r, 2)
        if name == "play":
            if paused:
                # Triangle (play)
                pygame.draw.polygon(screen, (200, 220, 255),
                    [(cx - 5, cy - 7), (cx - 5, cy + 7), (cx + 7, cy)])
            else:
                # Pause bars
                pygame.draw.rect(screen, (200, 220, 255), (cx - 5, cy - 6, 4, 12))
                pygame.draw.rect(screen, (200, 220, 255), (cx + 1, cy - 6, 4, 12))
        elif name == "rewind":
            pygame.draw.polygon(screen, (180, 180, 190),
                [(cx + 4, cy - 6), (cx + 4, cy + 6), (cx - 5, cy)])
        elif name == "forward":
            pygame.draw.polygon(screen, (180, 180, 190),
                [(cx - 4, cy - 6), (cx - 4, cy + 6), (cx + 5, cy)])
    # Speed label
    spd_label = fnt.render(f"{speed:g}x", True, ACCENT_BLUE)
    screen.blit(spd_label, (buttons[-1][1] + _CTRL_BTN_SIZE // 2 + 8, buttons[-1][2] - 7))
    return buttons

def handle_controls_click(mx, my, buttons, paused, speed, time_val):
    """Check if a control button was clicked. Returns (paused, speed, time_val)."""
    for name, cx, cy in buttons:
        r = _CTRL_BTN_SIZE // 2
        if (mx - cx) ** 2 + (my - cy) ** 2 <= r * r:
            if name == "play":
                paused = not paused
            elif name == "rewind":
                time_val -= 5.0
            elif name == "forward":
                time_val += 5.0
            break
    return paused, speed, time_val


# ---------------------------------------------------------------------------
# Session info banner
# ---------------------------------------------------------------------------
def draw_session_info(screen, session_info, screen_w):
    """Display circuit/country/date below the header."""
    if not session_info:
        return
    fnt = get_font("Consolas", 11)
    parts = []
    if session_info.get("circuit"):
        parts.append(session_info["circuit"])
    if session_info.get("country"):
        parts.append(session_info["country"])
    if session_info.get("date"):
        parts.append(str(session_info["date"])[:10])
    if session_info.get("round"):
        parts.append(f"R{session_info['round']}")
    text = "  |  ".join(parts)
    surf = fnt.render(text, True, (130, 130, 140))
    screen.blit(surf, (22, HEADER_HEIGHT - 16))


# ---------------------------------------------------------------------------
# Tyre health ring in leaderboard
# ---------------------------------------------------------------------------
def draw_tyre_health_ring(screen, cx, cy, radius, health_pct, compound_name):
    """Draw a ring that depletes clockwise as health drops."""
    col = tyre_compound_color(compound_name)
    bg_col = (col[0] // 4, col[1] // 4, col[2] // 4)
    # Background ring
    pygame.draw.circle(screen, bg_col, (cx, cy), radius, 2)
    # Health arc (approximate with line segments)
    health = max(0, min(100, health_pct))
    n_segs = max(1, int(24 * health / 100))
    angle_span = 2 * math.pi * health / 100
    start_angle = -math.pi / 2  # 12 o'clock
    points = []
    for i in range(n_segs + 1):
        a = start_angle + angle_span * i / n_segs
        px = cx + int(radius * math.cos(a))
        py = cy + int(radius * math.sin(a))
        points.append((px, py))
    if len(points) > 1:
        pygame.draw.lines(screen, col, False, points, 2)
    # Inner dot with compound color
    pygame.draw.circle(screen, col, (cx, cy), radius - 4)


# ---------------------------------------------------------------------------
# Status banner (SC / VSC / RED FLAG overlay)
# ---------------------------------------------------------------------------
def draw_status_banner(screen, status_code, screen_w):
    """Show a prominent banner when track is under caution."""
    label = _status_label(status_code)
    if not label:
        return
    col = _STATUS_TRACK_COLORS.get(status_code, (200, 200, 200))
    banner_h = 28
    banner_y = HEADER_HEIGHT + 2
    bg = pygame.Surface((screen_w - SIDEBAR_WIDTH, banner_h), pygame.SRCALPHA)
    bg.fill((*col, 160))
    screen.blit(bg, (0, banner_y))
    fnt = get_font("Consolas", 16, bold=True)
    surf = fnt.render(label, True, (255, 255, 255))
    screen.blit(surf, ((screen_w - SIDEBAR_WIDTH) // 2 - surf.get_width() // 2, banner_y + 5))


def run_replay(drivers_data, bounds, timeline, metadata, similarity_matrix=None,
               track_statuses=None, rc_messages=None, weather_timeline=None, tyre_model=None):
    if not drivers_data or not timeline:
        print("❌ Replay Error: No driver data or timeline available.")
        return

    driver_info = metadata["driver_info"]
    total_laps = metadata.get("total_laps", 0)
    fastest_driver = None
    fastest_lap_time = None

    # Get max speed for heatmap
    max_speed = 1.0
    for drv_id, df in drivers_data.items():
        if not df.empty and "Speed" in df.columns:
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

    tag_font = get_font("Arial", 10, bold=True)
    badge_font = get_font("Consolas", 10, bold=True)

    track_segments = build_track_segments(drivers_data, bounds, screen_size)

    # --- Track geometry (inner/outer edges + normals) ---
    _center_pts = [track_segments[0]["p1"]] + [s["p2"] for s in track_segments] if track_segments else []
    from track_geo import build_track_edges as _bte, label_offset_from_normal
    _inner_edge, _outer_edge, _track_normals = _bte(_center_pts, track_half_width=7) if len(_center_pts) > 2 else ([], [], [])

    # Pre-compute spatial grid for O(1) label normal lookups
    _normal_grid = {}
    if _track_normals and len(_track_normals) > 0 and len(_center_pts) > 0:
        for _ni, pt in enumerate(_center_pts):
            gx, gy = int(pt[0] / 20), int(pt[1] / 20)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    _normal_grid[(gx + dx, gy + dy)] = _ni

    time_val = timeline[0]
    total_time = timeline[-1]

    running = True
    paused = False
    speed = 1.0
    show_heatmap = False
    draw_dashboard._tyre_model = tyre_model
    gap_mode = "gap"
    focused_driver = None
    ghost_driver = None
    show_similarity = False
    sidebar_rects = {}
    delta_history = []

    drv_colors = {drv: parse_team_color(info["TeamColor"]) for drv, info in driver_info.items()}
    trails = {drv: [] for drv in drivers_data}
    row_positions = {}
    previous_order = []
    active_overtakes = []
    ot_cooldowns = {}
    pit_entry_times = {}
    show_rc_feed = False
    ctrl_buttons = []
    if track_statuses is None:
        track_statuses = []
    if rc_messages is None:
        rc_messages = []
    if weather_timeline is None:
        weather_timeline = []
    session_info = metadata.get("session_info", {})

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
                if event.key == pygame.K_e and focused_driver:
                    import os
                    lap = int(frame_by_driver[focused_driver]["lap"])
                    drv = focused_driver
                    lap_df = drivers_data[drv][drivers_data[drv]["LapNumber"] == lap].copy()
                    if "LateralG" not in lap_df.columns:
                        lap_df["LateralG"] = 0
                    out_path = f"{drv}_lap{lap}.csv"
                    lap_df[["CumDist","Speed","Throttle","Brake","LateralG"]].to_csv(out_path, index=False)
                    print(f"✅ Exported {out_path}")
                if event.key == pygame.K_4:
                    speed = 4.0
                if event.key == pygame.K_UP:
                    speed = min(speed + 0.5, 10.0)
                if event.key == pygame.K_DOWN:
                    speed = max(speed - 0.5, 0.0)
                if event.key == pygame.K_RIGHT:
                    time_val += 5.0
                    previous_order = []
                    active_overtakes = []
                    ot_cooldowns = {}
                if event.key == pygame.K_LEFT:
                    time_val -= 5.0
                    previous_order = []
                    active_overtakes = []
                    ot_cooldowns = {}
                if event.key == pygame.K_h:
                    show_heatmap = not show_heatmap
                if event.key == pygame.K_m:
                    show_rc_feed = not show_rc_feed
                if event.key == pygame.K_s:
                    show_similarity = not show_similarity
                if event.key == pygame.K_g:
                    gap_mode = "interval" if gap_mode == "gap" else "gap"
                if event.key == pygame.K_f:
                    focused_driver = None
                    ghost_driver = None
                    delta_history = []
                if event.key == pygame.K_c:
                    ghost_driver = None
                    delta_history = []
                if event.key == pygame.K_r:
                    time_val = timeline[0]
                    trails = {drv: [] for drv in drivers_data}
                    row_positions = {}
                    delta_history = []
                    previous_order = []
                    active_overtakes = []
                    ot_cooldowns = {}

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = pygame.mouse.get_pos()
                if my > screen_h - SEEK_BAR_HEIGHT:
                    ratio = mx / screen_w
                    time_val = ratio * total_time
                    trails = {drv: [] for drv in drivers_data}
                    delta_history = []
                    previous_order = []
                    active_overtakes = []
                    ot_cooldowns = {}
                else:
                    # Check race controls HUD buttons first
                    _p, _s, _tv = handle_controls_click(mx, my, ctrl_buttons, paused, speed, time_val)
                    if _p != paused or _tv != time_val:
                        paused = _p
                        time_val = _tv
                    else:
                        pending_click = (mx, my, bool(pygame.key.get_mods() & pygame.KMOD_SHIFT))

        if not paused:
            time_val += dt * speed
            if time_val > total_time:
                time_val = timeline[0]
                trails = {drv: [] for drv in drivers_data}
                delta_history = []
                previous_order = []
                active_overtakes = []
                ot_cooldowns = {}

        time_val = max(timeline[0], min(time_val, total_time))

        # --- UPDATE DRIVERS ---
        current_frame_data = []
        frame_by_driver = {}

        for drv_code, df in drivers_data.items():
            if df.empty:
                continue

            state = get_interpolated_state(df, time_val)
            gx, gy = scale_point(state["X"], state["Y"], bounds, screen_size)
            info = driver_info.get(drv_code, {})
            sector_flash = get_sector_flash(info, time_val)
            drs_active = is_drs_active(state["DRS"])
            in_pit_window = is_in_pit_window(info, time_val)
            in_pit = state["Speed"] < 5 and (in_pit_window or not info.get("PitWindows")) and time_val > timeline[0] + 2

            trails[drv_code].append((gx, gy, state["Speed"]))
            if len(trails[drv_code]) > TRAIL_LENGTH:
                trails[drv_code].pop(0)

            frame_state = {
                "id": drv_code,
                "dist": state["CumDist"],
                "lap": state["LapNumber"],
                "gx": gx,
                "gy": gy,
                "sx": gx,
                "sy": gy,
                "speed": state["Speed"],
                "throttle": state["Throttle"],
                "brake": state["Brake"],
                "gear": state["nGear"],
                "drs": state["DRS"],
                "drs_active": drs_active,
                "in_pit": in_pit,
                "sector_flash": sector_flash,
            }
            current_frame_data.append(frame_state)
            frame_by_driver[drv_code] = frame_state

        camera = build_camera(focused_driver, frame_by_driver, screen_size)
        for frame_state in current_frame_data:
            frame_state["sx"], frame_state["sy"] = apply_camera((frame_state["gx"], frame_state["gy"]), camera)

        # Determine current track status
        _cur_status = _get_track_status_at(track_statuses, time_val)
        _status_col = _STATUS_TRACK_COLORS.get(_cur_status, TRACK_COLOR)
        draw_track(screen, track_segments, show_heatmap, max_speed, camera, _status_col)

        # Inner/outer edges (drawn on top of track for border effect)
        if len(_inner_edge) > 2:
            cam_inner = [apply_camera(p, camera) for p in _inner_edge]
            cam_outer = [apply_camera(p, camera) for p in _outer_edge]
            pygame.draw.lines(screen, (35, 35, 40), False, cam_inner, 2)
            pygame.draw.lines(screen, (35, 35, 40), False, cam_outer, 2)

        if current_frame_data:
            current_frame_data.sort(key=lambda x: x["dist"], reverse=True)
            leaderboard_order = [d["id"] for d in current_frame_data]

            # --- OVERTAKE DETECTION ---
            if previous_order and time_val > timeline[0] + 60.0:
                for new_pos, drv in enumerate(leaderboard_order):
                    if drv in previous_order:
                        old_pos = previous_order.index(drv)
                        if new_pos < old_pos:
                            for passed_drv in previous_order[new_pos:old_pos]:
                                if passed_drv in leaderboard_order:
                                    if not frame_by_driver[drv]["in_pit"] and not frame_by_driver[passed_drv]["in_pit"]:
                                        # Verify they are physically close to prevent glitch overtakes
                                        if abs(frame_by_driver[drv]["dist"] - frame_by_driver[passed_drv]["dist"]) < 150:
                                            pair = tuple(sorted([drv, passed_drv]))
                                            if time_val - ot_cooldowns.get(pair, -999) > 10.0:
                                                active_overtakes.append({
                                                    "attacker": drv,
                                                    "defender": passed_drv,
                                                    "time": time_val
                                                })
                                                ot_cooldowns[pair] = time_val
            previous_order = leaderboard_order.copy()
            active_overtakes = [o for o in active_overtakes if 0 <= time_val - o["time"] < 4.0]

            leader_dist = current_frame_data[0]["dist"]
            current_lap = current_frame_data[0]["lap"]

            if current_lap == 0:
                current_lap = int(leader_dist / track_length_approx) + 1

            fastest_driver, fastest_lap_time, _ = get_live_fastest_lap(driver_info, time_val)

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
            smoothing = min(1.0, dt / 0.3)
            for pos, drv_id in enumerate(leaderboard_order):
                target_y = list_start_y + (pos * row_h)
                if drv_id not in row_positions:
                    row_positions[drv_id] = target_y
                else:
                    row_positions[drv_id] = lerp(row_positions[drv_id], target_y, smoothing)

            if pending_click:
                clicked_driver = None
                for drv_id, rect in sidebar_rects.items():
                    if rect.collidepoint((pending_click[0], pending_click[1])):
                        clicked_driver = drv_id
                        break

                is_shift_click = pending_click[2]
                if clicked_driver is None:
                    px, py = pending_click[0], pending_click[1]
                    for d in current_frame_data:
                        if math.hypot(px - d["sx"], py - d["sy"]) <= 16:
                            clicked_driver = d["id"]
                            break

                if clicked_driver:
                    show_similarity = False
                    if is_shift_click:
                        if focused_driver is None:
                            focused_driver = clicked_driver
                        elif clicked_driver != focused_driver:
                            ghost_driver = None if ghost_driver == clicked_driver else clicked_driver
                            delta_history = []
                    else:
                        if focused_driver == clicked_driver:
                            focused_driver = None
                            ghost_driver = None
                            delta_history = []
                        else:
                            focused_driver = clicked_driver
                            if ghost_driver == clicked_driver:
                                ghost_driver = None
                            delta_history = []

                    camera = build_camera(focused_driver, frame_by_driver, screen_size)
                    for frame_state in current_frame_data:
                        frame_state["sx"], frame_state["sy"] = apply_camera((frame_state["gx"], frame_state["gy"]), camera)

            if focused_driver and ghost_driver and focused_driver in frame_by_driver and ghost_driver in frame_by_driver:
                delta = (frame_by_driver[ghost_driver]["dist"] - frame_by_driver[focused_driver]["dist"]) / 70.0
                delta_history.append(delta)
                if len(delta_history) > 240:
                    delta_history.pop(0)

            if ghost_driver in trails:
                draw_ghost_trail(screen, trails[ghost_driver], drv_colors.get(ghost_driver, (220, 220, 220)), camera)

            # Draw unfocused cars first, then comparison and focused cars on top.
            draw_order = [d for d in current_frame_data if d["id"] not in (focused_driver, ghost_driver)]
            draw_order += [d for d in current_frame_data if d["id"] == ghost_driver]
            draw_order += [d for d in current_frame_data if d["id"] == focused_driver]

            for d in draw_order:
                drv_code = d["id"]
                pts = trails[drv_code]
                if len(pts) <= 1:
                    continue

                base_color = drv_colors[drv_code]
                is_dimmed = focused_driver is not None and drv_code not in (focused_driver, ghost_driver)
                color = muted_color(base_color) if is_dimmed else base_color

                for i in range(len(pts) - 1):
                    p1 = apply_camera((pts[i][0], pts[i][1]), camera)
                    p2 = apply_camera((pts[i + 1][0], pts[i + 1][1]), camera)
                    width = trail_width(pts[i + 1][2], max_speed)
                    if drv_code == focused_driver:
                        pygame.draw.line(screen, (5, 5, 8), p1, p2, width + 4)
                        width += 2
                    pygame.draw.line(screen, color, p1, p2, width)

            for d in draw_order:
                drv_id = d["id"]
                c = drv_colors[drv_id]
                is_dimmed = focused_driver is not None and drv_id not in (focused_driver, ghost_driver)
                if is_dimmed:
                    c = muted_color(c)

                sx, sy = d["sx"], d["sy"]
                radius = 9 if drv_id == focused_driver else 7

                if drv_id == ghost_driver:
                    pygame.draw.circle(screen, (245, 245, 245), (sx, sy), 13, width=2)
                if drv_id == focused_driver:
                    pygame.draw.circle(screen, ACCENT_BLUE, (sx, sy), 14, width=2)

                sector_flash = d.get("sector_flash")
                if sector_flash:
                    pulse = 0.5 + 0.5 * math.sin(time_val * 18)
                    sector_color = lerp_color(c, sector_flash["color"], 0.65 + 0.35 * pulse)
                    pygame.draw.circle(screen, sector_color, (sx, sy), radius + 8, width=3)
                    c = sector_color

                if d["in_pit"]:
                    flash = 0.5 + 0.5 * math.sin(time_val * 7)
                    pit_color = lerp_color((120, 80, 10), PIT_YELLOW, flash)
                    pygame.draw.circle(screen, pit_color, (sx, sy), radius + 5, width=3)

                pygame.draw.circle(screen, (0, 0, 0), (sx, sy), radius + 2)
                pygame.draw.circle(screen, c, (sx, sy), radius)
                pygame.draw.circle(screen, (255, 255, 255), (sx, sy), 2)

                label_color = (105, 105, 105) if is_dimmed else (230, 230, 230)
                lbl = tag_font.render(driver_info[drv_id]["Abbreviation"], True, label_color)
                # Position label using track normals when available
                _lbl_dx, _lbl_dy = 12, -12
                if _track_normals is not None and len(_track_normals) > 0:
                    gx, gy = d.get("gx", sx), d.get("gy", sy)
                    cell = (int(gx / 20), int(gy / 20))
                    _best_ni = _normal_grid.get(cell)
                    if _best_ni is not None and _best_ni < len(_track_normals):
                        _lbl_dx, _lbl_dy = label_offset_from_normal(_track_normals[_best_ni], 30)
                screen.blit(lbl, (sx + _lbl_dx, sy + _lbl_dy))

                badge_y = sy + 4
                if d["drs_active"]:
                    draw_badge(screen, "DRS", badge_font, sx + 12, badge_y, (0, 40, 8), DRS_GREEN)
                    badge_y += 16
                if d["in_pit"]:
                    if d["id"] not in pit_entry_times:
                        pit_entry_times[d["id"]] = time_val
                    dur = time_val - pit_entry_times[d["id"]]
                    if dur < 120:
                        draw_badge(screen, f"PIT {dur:.1f}s", badge_font, sx + 12, badge_y, (30, 20, 0), PIT_YELLOW)
                    else:
                        draw_badge(screen, "OUT", badge_font, sx + 12, badge_y, (30, 0, 0), (255, 60, 60))
                    badge_y += 16
                else:
                    pit_entry_times.pop(d["id"], None)
                    
                if d.get("sector_flash"):
                    flash_info = d["sector_flash"]
                    draw_badge(screen, flash_info["label"], badge_font, sx + 12, badge_y, (20, 20, 25), flash_info["color"])

            pit_drivers = {d["id"]: (time_val - pit_entry_times[d["id"]]) for d in current_frame_data if d["in_pit"]}
            drs_drivers = {d["id"] for d in current_frame_data if d["drs_active"]}

            draw_minimap(screen, track_segments, current_frame_data, focused_driver, ghost_driver, drv_colors)
            draw_delta_panel(screen, focused_driver, ghost_driver, driver_info, frame_by_driver, delta_history)
            draw_telemetry_overlay(screen, focused_driver, driver_info, frame_by_driver, max_speed)
            if show_similarity and focused_driver:
                sidebar_rects = draw_similarity_panel(screen, focused_driver, driver_info, similarity_matrix)
            else:
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
                    row_positions,
                    active_overtakes,
                    frame_by_driver
                )
            draw_progress_bar_with_markers(screen, time_val, total_time, screen_w, screen_h,
                                           track_statuses, rc_messages, driver_info)

        # --- New Tier-1 overlays ---
        draw_status_banner(screen, _cur_status, screen_w)
        draw_weather_panel(screen, weather_timeline, time_val)
        draw_race_control_feed(screen, rc_messages, time_val, screen_w, show_rc_feed)
        draw_session_info(screen, session_info, screen_w)
        ctrl_buttons = draw_race_controls(screen, paused, speed, screen_w)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()
