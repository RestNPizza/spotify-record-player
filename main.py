import pygame
import os
import random
import sys
import requests
import time
import math
import threading
from io import BytesIO
from spot import get_current_playing_info, start_music, stop_music, skip_to_next, skip_to_previous
from pathlib import Path
from PIL import Image, ImageDraw
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent

def mask_album_art(image, size=500, opacity=204):
    mask_surface = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(mask_surface, (255, 255, 255, opacity), (size // 2, size // 2), size // 2)

    # Add center hole
    center_hole_radius = 21  # About 0.5 inches if ~100 dpi
    pygame.draw.circle(mask_surface, (0, 0, 0, 0), (size // 2, size // 2), center_hole_radius)

    image = pygame.transform.scale(image, (size, size))
    image.blit(mask_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return image

def get_dominant_color(pil_image, resize_to=(50, 50)):
    small_image = pil_image.resize(resize_to)
    pixels = list(small_image.getdata())
    pixels = [p for p in pixels if len(p) == 3 or (len(p) == 4 and p[3] > 0)]
    pixels = [p[:3] for p in pixels]
    most_common = Counter(pixels).most_common(1)[0][0]

    # Brightness calculation
    r, g, b = most_common
    brightness = 0.299 * r + 0.587 * g + 0.114 * b
    if brightness > 200:
        return (50, 50, 50)
    return most_common

def run(windowed=False):
    pygame.init()
    pygame.mixer.init()
    flags = 0 if windowed else pygame.FULLSCREEN
    screen = pygame.display.set_mode((1080, 1080), flags)
    pygame.display.set_caption("Spotify Record Spinner")
    pygame.mouse.set_visible(False)

    record_dir = BASE_DIR / 'records'
    record_files = [p for p in record_dir.iterdir() if p.is_file()]
    record_image = pygame.image.load(str(random.choice(record_files)))
    record_image = pygame.transform.scale(record_image, (int(1080 * 1.25), int(1080 * 1.25)))

    icons_dir = BASE_DIR / 'spotify'
    play_btn  = pygame.image.load(str(icons_dir / 'play.png'))
    pause_btn = pygame.image.load(str(icons_dir / 'pause.png'))
    skip_btn  = pygame.image.load(str(icons_dir / 'skip.png'))
    prev_btn  = pygame.image.load(str(icons_dir / 'previous.png'))

    font_title  = pygame.font.Font(None, 30)
    font_artist = pygame.font.Font(None, 26)

    sfx_dir = BASE_DIR / 'sfx'
    scratch_sounds = [pygame.mixer.Sound(str(p)) for p in sfx_dir.iterdir() if p.suffix.lower() == '.wav']

    center = (540, 540)
    angle = 0
    angle_speed = -0.5
    is_playing = True
    dragging = False
    last_mouse_pos = None
    details = None
    album_img = None
    masked_album_surface = None
    dominant_color = (50, 50, 50)

    def update_details():
        nonlocal details, album_img, masked_album_surface, dominant_color
        try:
            new_details = get_current_playing_info()
        except Exception as e:
            print(f"Error fetching playing info: {e}", file=sys.stderr)
            return
        if new_details:
            details = new_details
            try:
                r = requests.get(details["album_cover"])
                pil_img = Image.open(BytesIO(r.content)).convert("RGBA")
                dominant_color = get_dominant_color(pil_img)
                album_img = pygame.image.load(BytesIO(r.content)).convert_alpha()
                masked_album_surface = mask_album_art(album_img)
            except Exception as e:
                print(f"Error loading album art: {e}", file=sys.stderr)

    update_details()

    def details_thread():
        while True:
            time.sleep(5)
            update_details()

    threading.Thread(target=details_thread, daemon=True).start()

    swipe_start_pos = None
    swipe_start_time = None
    SWIPE_DIST = 100
    SWIPE_TIME = 0.5

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                pygame.quit()
                sys.exit()

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                swipe_start_pos = event.pos
                swipe_start_time = time.time()
                mx, my = event.pos

                gap = 51
                album_w, album_h = (137, 137) if album_img else (0, 0)
                prev_w, pause_w, skip_w = prev_btn.get_width(), pause_btn.get_width(), skip_btn.get_width()
                group_width = album_w + prev_w + pause_w + skip_w + (3 * gap)
                group_start_x = (1080 - group_width) // 2
                group_center_y = 800 + 30

                album_x = group_start_x
                album_y = group_center_y - (album_h // 2) - 30
                prev_x  = album_x + album_w + gap
                prev_y  = group_center_y - (prev_btn.get_height() // 2)
                pause_x = prev_x + prev_w + gap
                pause_y = group_center_y - (pause_btn.get_height() // 2)
                skip_x  = pause_x + pause_w + gap
                skip_y  = group_center_y - (skip_btn.get_height() // 2)

                if prev_x <= mx <= prev_x + prev_w and prev_y <= my <= prev_y + prev_btn.get_height():
                    skip_to_previous()
                    threading.Thread(target=update_details, daemon=True).start()
                elif pause_x <= mx <= pause_x + pause_w and pause_y <= my <= pause_y + pause_btn.get_height():
                    if is_playing:
                        stop_music()
                        is_playing = False
                        angle_speed = 0
                    else:
                        start_music()
                        is_playing = True
                        angle_speed = -0.5
                elif skip_x <= mx <= skip_x + skip_w and skip_y <= my <= skip_y + skip_btn.get_height():
                    skip_to_next()
                    new_path = random.choice(record_files)
                    record_image = pygame.image.load(str(new_path))
                    record_image = pygame.transform.scale(record_image, (int(1080 * 1.25), int(1080 * 1.25)))
                    threading.Thread(target=update_details, daemon=True).start()
                else:
                    if math.hypot(mx - center[0], my - center[1]) <= 540:
                        dragging = True
                        last_mouse_pos = event.pos

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if swipe_start_pos:
                    dx = event.pos[0] - swipe_start_pos[0]
                    dy = event.pos[1] - swipe_start_pos[1]
                    if math.hypot(dx, dy) > SWIPE_DIST and time.time() - swipe_start_time < SWIPE_TIME:
                        random.choice(scratch_sounds).play()
                dragging = False

            elif event.type == pygame.MOUSEMOTION and dragging:
                dx = event.pos[0] - last_mouse_pos[0]
                angle -= dx * 0.1
                angle %= 360
                last_mouse_pos = event.pos

        screen.fill((245, 230, 200))
        rotated = pygame.transform.rotate(record_image, angle)
        screen.blit(rotated, rotated.get_rect(center=center))
        if is_playing:
            angle = (angle + angle_speed) % 360

        # Masked album art (centered and rotating with record)
        if masked_album_surface:
            rot_mask = pygame.transform.rotate(masked_album_surface, angle)
            screen.blit(rot_mask, rot_mask.get_rect(center=center))

        # Banner replacement
        banner_w, banner_h = 600, 100
        banner_x = (1080 - banner_w) // 2
        banner_y = 800
        pygame.draw.rect(screen, dominant_color, (banner_x, banner_y, banner_w, banner_h), border_radius=12)

        # Playback controls
        gap = 51
        album_w, album_h = (137, 137) if album_img else (0, 0)
        prev_w, pause_w, skip_w = prev_btn.get_width(), pause_btn.get_width(), skip_btn.get_width()
        group_width = album_w + prev_w + pause_w + skip_w + (3 * gap)
        group_start_x = (1080 - group_width) // 2
        group_center_y = banner_y + (banner_h // 2) + 10

        album_x = group_start_x
        album_y = group_center_y - (album_h // 2) - 30
        prev_x  = album_x + album_w + gap
        prev_y  = group_center_y - (prev_btn.get_height() // 2)
        pause_x = prev_x + prev_w + gap
        pause_y = group_center_y - (pause_btn.get_height() // 2)
        skip_x  = pause_x + pause_w + gap
        skip_y  = group_center_y - (skip_btn.get_height() // 2)

        if album_img:
            screen.blit(album_img, (album_x, album_y))
        screen.blit(prev_btn, (prev_x, prev_y))
        screen.blit(pause_btn if is_playing else play_btn, (pause_x, pause_y))
        screen.blit(skip_btn, (skip_x, skip_y))

        if details:
            song_surf = font_title.render(details["title"], True, (255, 255, 255))
            artist_surf = font_artist.render(details["artist"], True, (255, 255, 255))
            pcx = pause_x + pause_w // 2
            tb  = pause_y - 10
            ay  = tb - artist_surf.get_height()
            sy  = ay - 5 - song_surf.get_height()
            sx  = pcx - (song_surf.get_width() // 2)
            ax  = pcx - (artist_surf.get_width() // 2)
            screen.blit(song_surf, (sx, sy))
            screen.blit(artist_surf, (ax, ay))

        pygame.display.flip()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Spotify Record Player")
    parser.add_argument('--windowed', action='store_true', help='Run in windowed mode')
    args = parser.parse_args()
    run(windowed=args.windowed)
