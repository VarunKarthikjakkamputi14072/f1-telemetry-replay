import pygame
import sys
import fastf1

# --- Menu Visual Configuration ---
BG_COLOR = (13, 13, 17)
ITEM_BG = (22, 25, 30)
SELECTED_BG = (40, 50, 60)
TEXT_COLOR = (220, 220, 220)
ACCENT_COLOR = (100, 200, 255)
SUBTEXT_COLOR = (120, 120, 120)

def draw_list(screen, font_item, font_small, title_str, items, selected_idx, scroll_offset, visible_items, list_start_y):
    screen_w, screen_h = screen.get_size()
    
    # Draw Header
    font_title = pygame.font.SysFont("Consolas", 32, bold=True)
    title = font_title.render(title_str, True, ACCENT_COLOR)
    screen.blit(title, (50, 30))
    
    sub = font_small.render("Arrow Keys: Navigate  |  Enter: Select  |  Esc: Quit", True, SUBTEXT_COLOR)
    screen.blit(sub, (52, 75))
    
    pygame.draw.line(screen, (50, 50, 60), (50, 95), (850, 95), 1)

    item_height = 60
    
    for i in range(visible_items):
        data_idx = scroll_offset + i
        if data_idx >= len(items):
            break
            
        item = items[data_idx]
        y_pos = list_start_y + (i * (item_height + 5))
        
        is_selected = (data_idx == selected_idx)
        bg_col = SELECTED_BG if is_selected else ITEM_BG
        text_col = ACCENT_COLOR if is_selected else TEXT_COLOR
        
        # Card Body
        rect = (50, y_pos, 800, item_height)
        pygame.draw.rect(screen, bg_col, rect, border_radius=6)
        
        if is_selected:
            pygame.draw.rect(screen, ACCENT_COLOR, rect, width=2, border_radius=6)
        
        # Text Content (Generic Render)
        label = item.get("label", str(item))
        sub_label = item.get("sub", "")
        
        txt = font_item.render(label, True, text_col)
        screen.blit(txt, (80, y_pos + 18))
        
        if sub_label:
            s_txt = font_small.render(sub_label, True, SUBTEXT_COLOR)
            s_rect = s_txt.get_rect(right=820, centery=y_pos + 30)
            screen.blit(s_txt, s_rect)
            
    # FIX 5: Correct Scrollbar Math
    if len(items) > visible_items:
        # Total height of the visible track area
        track_height = visible_items * (item_height + 5)
        
        # Calculate thumb height proportional to visible ratio
        # Ensure it's at least 20px so it remains visible
        visible_ratio = visible_items / len(items)
        thumb_height = max(20, int(visible_ratio * track_height))
        
        # Calculate scroll fraction (0.0 to 1.0) based on offset
        max_scroll_offset = len(items) - visible_items
        scroll_fraction = scroll_offset / max_scroll_offset if max_scroll_offset > 0 else 0
        
        # Calculate thumb Y position
        # It moves within (track_height - thumb_height) space
        thumb_travel = track_height - thumb_height
        thumb_y = list_start_y + int(scroll_fraction * thumb_travel)
        
        # Draw Track
        pygame.draw.rect(screen, (50, 50, 60), (860, list_start_y, 4, track_height))
        # Draw Thumb
        pygame.draw.rect(screen, ACCENT_COLOR, (860, thumb_y, 4, thumb_height))

def run_year_menu():
    """
    Displays a menu to select the F1 Season Year.
    """
    pygame.init()
    screen = pygame.display.set_mode((900, 700))
    pygame.display.set_caption("F1 Analytics Engine | Select Season")
    clock = pygame.time.Clock()
    
    font_item = pygame.font.SysFont("Consolas", 24, bold=True)
    font_small = pygame.font.SysFont("Arial", 14)
    
    # Generate Years (2025 down to 2018)
    years = [{"label": str(y), "sub": "Season"} for y in range(2025, 2017, -1)]
    
    selected_idx = 0
    scroll_offset = 0
    visible_items = 8
    
    running = True
    while running:
        screen.fill(BG_COLOR)
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected_idx = max(0, selected_idx - 1)
                    if selected_idx < scroll_offset: scroll_offset = selected_idx
                if event.key == pygame.K_DOWN:
                    selected_idx = min(len(years) - 1, selected_idx + 1)
                    if selected_idx >= scroll_offset + visible_items: scroll_offset = selected_idx - visible_items + 1
                if event.key == pygame.K_RETURN:
                    pygame.display.quit()
                    return int(years[selected_idx]["label"])
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                    
        draw_list(screen, font_item, font_small, "SELECT F1 SEASON", years, selected_idx, scroll_offset, visible_items, 110)
        pygame.display.flip()
        clock.tick(60)

def run_menu(year):
    """
    Displays a graphical menu to select a race from the given year.
    """
    pygame.init()
    screen = pygame.display.set_mode((900, 700))
    pygame.display.set_caption(f"F1 Analytics Engine | Select Race {year}")
    clock = pygame.time.Clock()
    
    font_title = pygame.font.SysFont("Consolas", 32, bold=True)
    font_item = pygame.font.SysFont("Consolas", 20)
    font_small = pygame.font.SysFont("Arial", 14)
    
    # Loading Screen
    screen.fill(BG_COLOR)
    loading_surf = font_title.render(f"Fetching {year} Schedule...", True, TEXT_COLOR)
    screen.blit(loading_surf, (450 - loading_surf.get_width()//2, 350))
    pygame.display.flip()
    
    fastf1.Cache.enable_cache("cache")
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        races = []
        for i, row in schedule.iterrows():
            loc = row.get("Location", "Unknown")
            date = row.get("EventDate").strftime('%d %b') if hasattr(row.get("EventDate"), 'strftime') else str(row.get("EventDate"))
            races.append({
                "label": row.get("EventName", "Unknown GP"),
                "sub": f"R{row.get('RoundNumber', i)} | {loc} | {date}"
            })
    except Exception as e:
        print(f"Error: {e}")
        return None

    if not races: return None

    selected_idx = 0
    scroll_offset = 0
    visible_items = 9
    
    running = True
    while running:
        screen.fill(BG_COLOR)
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected_idx = max(0, selected_idx - 1)
                    if selected_idx < scroll_offset: scroll_offset = selected_idx
                if event.key == pygame.K_DOWN:
                    selected_idx = min(len(races) - 1, selected_idx + 1)
                    if selected_idx >= scroll_offset + visible_items: scroll_offset = selected_idx - visible_items + 1
                if event.key == pygame.K_RETURN:
                    pygame.display.quit()
                    return races[selected_idx]["label"]
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()

        draw_list(screen, font_item, font_small, f"SEASON {year} CALENDAR", races, selected_idx, scroll_offset, visible_items, 110)
        pygame.display.flip()
        clock.tick(60)