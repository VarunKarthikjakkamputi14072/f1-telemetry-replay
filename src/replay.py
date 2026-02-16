import pygame
import sys
import numpy as np
import math

# --- Visual Configuration ---
BG_COLOR = (13, 13, 17)
TRACK_COLOR = (60, 60, 70)
TRACK_OUTLINE = (20, 20, 25)
TEXT_COLOR = (240, 240, 240)
UI_BG = (22, 25, 30)
UI_BORDER = (55, 60, 70)
TRAIL_LENGTH = 15 

def scale_point(x, y, bounds, screen_size):
    min_x, max_x, min_y, max_y = bounds
    width, height = screen_size
    
    padding_x = 60
    padding_y = 90
    sidebar_width = 240 
    
    avail_w = width - (padding_x * 2) - sidebar_width
    avail_h = height - (padding_y * 2)
    
    # FIX 3: Division by Zero Protection
    range_x = max(1.0, max_x - min_x)
    range_y = max(1.0, max_y - min_y)
    
    sx = int((x - min_x) / range_x * avail_w) + padding_x
    sy = int((y - min_y) / range_y * avail_h) + padding_y
    return sx, height - sy

def build_track_points(drivers_data, bounds, screen_size):
    if not drivers_data:
        return []
    # Safely find best driver
    try:
        best_driver = max(drivers_data.items(), key=lambda x: len(x[1]))[1]
    except ValueError:
        return []

    points = []
    for _, row in best_driver.iterrows():
        sx, sy = scale_point(row["X"], row["Y"], bounds, screen_size)
        points.append((sx, sy))
    return points

def get_interpolated_state(df, t):
    """
    Returns interpolated (X, Y, CumDist, LapNumber) for time t.
    """
    if df.empty:
        return 0, 0, 0, 0
        
    idx = df["Time"].searchsorted(t)
    
    if idx == 0:
        row = df.iloc[0]
        return row["X"], row["Y"], row["CumDist"], row["LapNumber"]
    if idx >= len(df):
        row = df.iloc[-1]
        return row["X"], row["Y"], row["CumDist"], row["LapNumber"]
    
    t0_row = df.iloc[idx - 1]
    t1_row = df.iloc[idx]
    
    t0, t1 = t0_row["Time"], t1_row["Time"]
    
    if t1 == t0:
        return t0_row["X"], t0_row["Y"], t0_row["CumDist"], t0_row["LapNumber"]
    
    alpha = (t - t0) / (t1 - t0)
    
    x = t0_row["X"] + (t1_row["X"] - t0_row["X"]) * alpha
    y = t0_row["Y"] + (t1_row["Y"] - t0_row["Y"]) * alpha
    dist = t0_row["CumDist"] + (t1_row["CumDist"] - t0_row["CumDist"]) * alpha
    
    # For lap number, we just take the most recent completed lap (floor)
    lap = t0_row["LapNumber"] 
    
    return x, y, dist, lap

def draw_dashboard(screen, font, t, speed, driver_info, leaderboard_order, gaps, current_lap, total_laps, total_time):
    screen_w, screen_h = screen.get_size()
    
    # --- Top Header ---
    header_h = 70
    pygame.draw.rect(screen, UI_BG, (0, 0, screen_w, header_h))
    pygame.draw.line(screen, UI_BORDER, (0, header_h), (screen_w, header_h), 2)
    
    # Time
    minutes = int(t // 60)
    seconds = int(t % 60)
    millis = int((t % 1) * 100)
    time_str = f"TIME: {minutes:02}:{seconds:02}.{millis:02}"
    lap_str = f"LAP {int(current_lap)} / {total_laps}"
    
    font_large = pygame.font.SysFont("Consolas", 28, bold=True)
    
    # Stats
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
    
    screen.blit(header_font.render("POS", True, (120, 120, 120)), (panel_x + 10, panel_y + 10))
    screen.blit(header_font.render("DRIVER", True, (120, 120, 120)), (panel_x + 50, panel_y + 10))
    screen.blit(header_font.render("GAP", True, (120, 120, 120)), (panel_x + 160, panel_y + 10))
    
    list_start_y = panel_y + 40
    row_h = 36
    name_font = pygame.font.SysFont("Consolas", 18, bold=True)
    gap_font = pygame.font.SysFont("Consolas", 16)
    
    for pos, drv_id in enumerate(leaderboard_order):
        info = driver_info[drv_id]
        y_pos = list_start_y + (pos * row_h)
        
        if y_pos + row_h > screen_h - 20: break
        
        bg_col = (25, 30, 40) if pos % 2 == 0 else (22, 25, 30)
        if pos == 0: bg_col = (35, 40, 50)
        
        pygame.draw.rect(screen, bg_col, (panel_x, y_pos, panel_w, row_h))
        
        try:
            c_hex = info['TeamColor'].lstrip('#')
            c_rgb = tuple(int(c_hex[i:i+2], 16) for i in (0, 2, 4))
        except: c_rgb = (255, 255, 255)
        
        pygame.draw.rect(screen, c_rgb, (panel_x + 4, y_pos + 4, 4, row_h - 8), border_radius=2)
        
        pos_surf = name_font.render(str(pos + 1), True, (255, 255, 255) if pos < 3 else (150, 150, 150))
        screen.blit(pos_surf, (panel_x + 15, y_pos + 8))
        
        name_surf = name_font.render(info['Abbreviation'], True, TEXT_COLOR)
        screen.blit(name_surf, (panel_x + 50, y_pos + 8))
        
        gap_val = gaps.get(drv_id, 0)
        if pos == 0:
            gap_str = "INT"
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
    pygame.draw.line(screen, (255, 255, 255), (progress_w, bar_y), (progress_w, screen_h), 2)

def run_replay(drivers_data, bounds, timeline, metadata):
    # FIX 6: Guard empty timeline
    if not drivers_data or not timeline:
        print("❌ Replay Error: No driver data or timeline available.")
        return

    driver_info = metadata["driver_info"]
    total_laps = metadata.get("total_laps", 0) 
    
    # --- DATA PREP (Calculate CumDist BEFORE using it) ---
    for drv_id, df in drivers_data.items():
        if df.empty: continue
        coords = df[["X", "Y"]].values
        diffs = coords[1:] - coords[:-1]
        dists = np.sqrt((diffs**2).sum(axis=1))
        dists = np.insert(dists, 0, 0)
        df["CumDist"] = np.cumsum(dists)

    # FIX 1: Estimate Track Length dynamically for Lap Calculation
    # Find the maximum distance covered by any driver (usually the winner)
    max_total_dist = 0
    for df in drivers_data.values():
        if not df.empty and "CumDist" in df.columns:
            d = df["CumDist"].iloc[-1]
            if d > max_total_dist:
                max_total_dist = d
    
    # If total_laps is valid AND distance is valid, calculate approx track length. 
    # Otherwise default to 5000m. Prevents 0 division.
    if total_laps > 0 and max_total_dist > 0:
        track_length_approx = max_total_dist / total_laps
    else:
        track_length_approx = 5000 

    pygame.init()
    screen_size = (1280, 850) 
    screen = pygame.display.set_mode(screen_size)
    pygame.display.set_caption(f"F1 Telemetry Pro | {metadata.get('race_name', 'Race')}")
    clock = pygame.time.Clock()
    
    font = pygame.font.SysFont("Consolas", 24, bold=True)
    tag_font = pygame.font.SysFont("Arial", 10, bold=True)
    
    track_points = build_track_points(drivers_data, bounds, screen_size)
    
    time_val = timeline[0]
    total_time = timeline[-1]
    
    running = True
    paused = False
    speed = 1.0
    
    drv_colors = {}
    for drv, info in driver_info.items():
        try:
            h = info['TeamColor'].lstrip('#')
            drv_colors[drv] = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        except: drv_colors[drv] = (200, 200, 200)
        
    trails = {drv: [] for drv in drivers_data}
            
    while running:
        screen.fill(BG_COLOR)
        dt = clock.get_time() / 1000.0 
        screen_w, screen_h = screen.get_size()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE: paused = not paused
                if event.key == pygame.K_1: speed = 0.5
                if event.key == pygame.K_2: speed = 1.0
                if event.key == pygame.K_3: speed = 2.0
                if event.key == pygame.K_4: speed = 4.0
                if event.key == pygame.K_UP: speed = min(speed + 0.5, 10.0)
                if event.key == pygame.K_DOWN: speed = max(speed - 0.5, 0.0)
                if event.key == pygame.K_RIGHT: time_val += 5.0
                if event.key == pygame.K_LEFT: time_val -= 5.0
                if event.key == pygame.K_r: 
                    time_val = timeline[0]
                    trails = {drv: [] for drv in drivers_data} 
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    mx, my = pygame.mouse.get_pos()
                    if my > screen_h - 20:
                        ratio = mx / screen_w
                        time_val = ratio * total_time
                        trails = {drv: [] for drv in drivers_data}

        if len(track_points) > 1:
            pygame.draw.lines(screen, TRACK_OUTLINE, False, track_points, 16)
            pygame.draw.lines(screen, TRACK_COLOR, False, track_points, 6)
            
        if not paused:
            time_val += dt * speed
            if time_val > total_time: time_val = timeline[0]
        
        time_val = max(timeline[0], min(time_val, total_time))
        
        # --- UPDATE DRIVERS ---
        current_frame_data = [] 
        
        for drv_code, df in drivers_data.items():
            if df.empty: continue
            rx, ry, dist, lap = get_interpolated_state(df, time_val)
            sx, sy = scale_point(rx, ry, bounds, screen_size)
            
            trails[drv_code].append((sx, sy))
            if len(trails[drv_code]) > TRAIL_LENGTH:
                trails[drv_code].pop(0)
            
            current_frame_data.append({
                "id": drv_code,
                "dist": dist,
                "lap": lap,
                "sx": sx, 
                "sy": sy
            })

        # FIX 7: Guard empty frame (prevent crash if no drivers at timestamp)
        if current_frame_data:
            # Sort by Distance
            current_frame_data.sort(key=lambda x: x["dist"], reverse=True)
            leaderboard_order = [d["id"] for d in current_frame_data]
            
            # Calculate Gaps
            leader_dist = current_frame_data[0]["dist"]
            current_lap = current_frame_data[0]["lap"]
            
            # Fallback for lap calc if not in data (using estimated track length)
            if current_lap == 0:
                current_lap = int(leader_dist / track_length_approx) + 1

            gaps = {}
            for d in current_frame_data:
                delta_m = leader_dist - d["dist"]
                gaps[d["id"]] = delta_m / 70.0 

            draw_dashboard(screen, font, time_val, speed, driver_info, leaderboard_order, gaps, current_lap, total_laps, total_time)

            for drv_code in leaderboard_order:
                pts = trails[drv_code]
                if len(pts) > 1:
                    c = drv_colors[drv_code]
                    for i in range(len(pts) - 1):
                        th = max(1, int(4 * (i/len(pts))))
                        pygame.draw.line(screen, c, pts[i], pts[i+1], th)

            for d in current_frame_data:
                c = drv_colors[d["id"]]
                sx, sy = d["sx"], d["sy"]
                
                pygame.draw.circle(screen, (0, 0, 0), (sx, sy), 9)
                pygame.draw.circle(screen, c, (sx, sy), 7)
                pygame.draw.circle(screen, (255, 255, 255), (sx, sy), 2)
                
                lbl = tag_font.render(driver_info[d["id"]]['Abbreviation'], True, (220, 220, 220))
                screen.blit(lbl, (sx + 12, sy - 12))
            
        pygame.display.flip()
        clock.tick(60) 
        
    pygame.quit()
    sys.exit()