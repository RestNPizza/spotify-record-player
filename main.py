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
import argparse
from pathlib import Path
from PIL import Image, ImageDraw
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent

def create_circular_mask_with_hole(size, radius, hole_radius):
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    cx, cy = size[0] // 2, size[1] // 2
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=255)
    draw.ellipse((cx - hole_radius, cy - hole_radius, cx + hole_radius, cy + hole_radius), fill=0)
    return mask

def run(windowed=False):
    pygame.init()
    pygame.mixer.init()
    flags = 0 if windowed else pygame.FULLSCREEN
    screen = pygame.display.set_mode((1080, 1080), flags)
    pygame.display.set_caption("Spotify Record Spinner")
    pygame.mouse.set_visible(False)

    record_dir = BASE_DIR / 'records'
    record_files = [p for p in record_dir.iterdir() if p.is_file()]
    random_record_path = random.choice(record_files)
    record_image_raw = pygame.image.load(str(random_record_path)).convert_alpha()
    record_image_raw = pygame.transform.scale(record_image_raw, (int(1080 * 1.25), int(1080 * 1.25)))

    icons_dir = BASE_DIR / 'spotify'
    play_btn  = pygame.image.load(str(icons_dir / 'play.png'))
    pause_btn = pygame.image.load(str(icons_dir / 'pause.png'))
    skip_btn  = pygame.image.load(str(icons_dir / 'skip.png'))
    prev_btn  = pygame.image.load(str(icons_dir / 'previous.png'))
    banner    = pygame.image.load(str(icons_dir / 'banner.png'))

    font_title = pygame.font.Font(None, 36)
    font_artist = pygame.font.Font(None, 28)

    sfx_dir = BASE_DIR / 'sfx'
    sfx_paths = [p for p in sfx_dir.iterdir() if p.is_file() and p.suffix.lower() == '.wav']
    scratch_sounds = [pygame.mixer.Sound(str(path)) for path in sfx_paths]

    center = (540, 540)
    angle = 0
    angle_speed = -0.5
    is_playing = True
    dragging = False
    last_mouse_pos = None
    details = None
    album_img = None
    album_art_overlay = None

    def update_details():
        nonlocal details, album_img, album_art_overlay
        try:
            new_details = get_current_playing_info()
        except Exception as e:
            print(f"Error fetching current playing info: {e}", file=sys.stderr)
            return
        if new_details:
            details = new_details
            try:
                r = requests.get(details["album_cover"])
                pil_img = Image.open(BytesIO(r.content)).convert("RGBA")
                pil_img = pil_img.resize((500, 500), Image.LANCZOS)

                mask = create_circular_mask_with_hole(pil_img.size, 250, 21)
                pil_img.putalpha(mask)
                for y in range(pil_img.size[1]):
                    for x in range(pil_img.size[0]):
                        r, g, b, a = pil_img.getpixel((x, y))
                        pil_img.putpixel((x, y), (r, g, b, int(a * 0.8)))

                album_art_overlay = pygame.image.fromstring(pil_img.tobytes(), pil_img.size, pil_img.mode).convert_alpha()

                mini = pil_img.resize((137, 137), Image.LANCZOS)
                album_img = pygame.image.fromstring(mini.tobytes(), mini.size, mini.mode).convert_alpha()
            except Exception as e:
                print(f"Error loading album cover: {e}", file=sys.stderr)

    update_details()

    def details_thread():
        while True:
            time.sleep(5)
            try:
                update_details()
            except Exception as e:
                print(f"Error in details_thread: {e}", file=sys.stderr)

    threading.Thread(target=details_thread, daemon=True).start()

    swipe_start_pos = None
    swipe_start_time = None
    SWIPE_DIST = 100
    SWIPE_TIME = 0.5

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                swipe_start_pos = event.pos
                swipe_start_time = time.time()
                mx, my = event.pos

                banner_x = 0
                banner_y = 800
                gap = 51
                album_w, album_h = (137, 137) if album_img else (0, 0)
                prev_w, prev_h   = prev_btn.get_width(), prev_btn.get_height()
                pause_w, pause_h = pause_btn.get_width(), pause_btn.get_height()
                skip_w, skip_h   = skip_btn.get_width(), skip_btn.get_height()

                group_width   = album_w + prev_w + pause_w + skip_w + (3 * gap)
                group_start_x = (1080 - group_width) // 2
                group_center_y = banner_y + 100

                album_x = group_start_x
                album_y = (group_center_y - (album_h // 2)) - 5
                prev_x  = album_x + album_w + gap
                prev_y  = group_center_y - (prev_h // 2)
                pause_x = prev_x + prev_w + gap
                pause_y = group_center_y - (pause_h // 2)
                skip_x  = pause_x + pause_w + gap
                skip_y  = group_center_y - (skip_h // 2)

                if prev_x <= mx <= prev_x + prev_w and prev_y <= my <= prev_y + prev_h:
                    try:
                        skip_to_previous()
                    except Exception as e:
                        print(f"Error skipping to previous track: {e}", file=sys.stderr)
                    else:
                        threading.Thread(target=update_details, daemon=True).start()
                elif pause_x <= mx <= pause_x + pause_w and pause_y <= my <= pause_y + pause_h:
                    if is_playing:
                        try:
                            stop_music()
                        except Exception as e:
                            print(f"Error stopping music: {e}", file=sys.stderr)
                        else:
                            is_playing = False
                            angle_speed = 0
                    else:
                        try:
                            start_music()
                        except Exception as e:
                            print(f"Error starting music: {e}", file=sys.stderr)
                        else:
                            is_playing = True
                            angle_speed = -0.5
                elif skip_x <= mx <= skip_x + skip_w and skip_y <= my <= skip_y + skip_h:
                    try:
                        skip_to_next()
                    except Exception as e:
                        print(f"Error skipping to next track: {e}", file=sys.stderr)
                    else:
                        new_path = random.choice(record_files)
                        record_image_raw = pygame.image.load(str(new_path)).convert_alpha()
                        record_image_raw = pygame.transform.scale(record_image_raw, (int(1080 * 1.25), int(1080 * 1.25)))
                        threading.Thread(target=update_details, daemon=True).start()
                else:
                    if math.hypot(mx - center[0], my - center[1]) <= 540:
                        dragging = True
                        last_mouse_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if swipe_start_pos and swipe_start_time:
                    dx = event.pos[0] - swipe_start_pos[0]
                    dy = event.pos[1] - swipe_start_pos[1]
                    dist = math.hypot(dx, dy)
                    elapsed = time.time() - swipe_start_time
                    if dist > SWIPE_DIST and elapsed < SWIPE_TIME:
                        random.choice(scratch_sounds).play()
                dragging = False
                swipe_start_pos = None
                swipe_start_time = None
            elif event.type == pygame.MOUSEMOTION and dragging:
                dx = event.pos[0] - last_mouse_pos[0]
                angle -= dx * 0.1
                angle %= 360
                last_mouse_pos = event.pos

        screen.fill((245, 230, 200))

        rotated = pygame.transform.rotate(record_image_raw, angle)
        screen.blit(rotated, rotated.get_rect(center=center))
        if album_art_overlay:
            rotated_art = pygame.transform.rotate(album_art_overlay, angle)
            screen.blit(rotated_art, rotated_art.get_rect(center=center))
        if is_playing:
            angle = (angle + angle_speed) % 360

        banner_x = 0
        banner_y = 800
        screen.blit(banner, (banner_x, banner_y))

        gap = 51
        album_w, album_h = (137, 137) if album_img else (0, 0)
        prev_w, prev_h   = prev_btn.get_width(), prev_btn.get_height()
        pause_w, pause_h = pause_btn.get_width(), pause_btn.get_height()
        skip_w, skip_h   = skip_btn.get_width(), skip_btn.get_height()

        group_width   = album_w + prev_w + pause_w + skip_w + (3 * gap)
        group_start_x = (1080 - group_width) // 2
        group_center_y = banner_y + 100

        album_x = group_start_x
        album_y = (group_center_y - (album_h // 2)) - 5
        prev_x  = album_x + album_w + gap
        prev_y  = group_center_y - (prev_h // 2)
        pause_x = prev_x + prev_w + gap
        pause_y = group_center_y - (pause_h // 2)
        skip_x  = pause_x + pause_w + gap
        skip_y  = group_center_y - (skip_h // 2)

        if album_img:
            screen.blit(album_img, (album_x, album_y))
        screen.blit(prev_btn,  (prev_x,  prev_y))
        screen.blit(pause_btn if is_playing else play_btn, (pause_x, pause_y))
        screen.blit(skip_btn,  (skip_x,  skip_y))

        if details:
            song_surf   = font_title.render(details["title"],  True, (255, 255, 255))
            artist_surf = font_artist.render(details["artist"], True, (255, 255, 255))
            pcx = pause_x + pause_w // 2
            tb  = pause_y - 10
            ay  = tb - artist_surf.get_height()
            sy  = ay - 5 - song_surf.get_height()
            sx  = pcx - (song_surf.get_width()   // 2)
            ax  = pcx - (artist_surf.get_width() // 2)
            screen.blit(song_surf,   (sx, sy))
            screen.blit(artist_surf, (ax, ay))

        pygame.display.flip()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spotify Record Player")
    parser.add_argument('--windowed', action='store_true', help='Run in windowed mode (no fullscreen)')
    args = parser.parse_args()
    run(windowed=args.windowed)
