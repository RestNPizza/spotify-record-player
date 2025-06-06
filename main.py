
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

BASE_DIR = Path(__file__).resolve().parent

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
    record_image = pygame.image.load(str(random_record_path))
    record_image = pygame.transform.scale(record_image, (int(1080 * 1.25), int(1080 * 1.25)))

    icons_dir = BASE_DIR / 'spotify'
    play_btn  = pygame.image.load(str(icons_dir / 'play.png'))
    pause_btn = pygame.image.load(str(icons_dir / 'pause.png'))
    skip_btn  = pygame.image.load(str(icons_dir / 'skip.png'))
    prev_btn  = pygame.image.load(str(icons_dir / 'previous.png'))
    banner    = pygame.image.load(str(icons_dir / 'banner.png'))

    font = pygame.font.Font(None, 40)

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

    def update_details():
        nonlocal details, album_img
        try:
            new_details = get_current_playing_info()
        except Exception as e:
            print(f"Error fetching current playing info: {e}", file=sys.stderr)
            return
        if new_details:
            details = new_details
            try:
                r = requests.get(details["album_cover"])
                img = pygame.image.load(BytesIO(r.content))
                album_img = img.convert_alpha()
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
        rotated = pygame.transform.rotate(record_image, angle)
        screen.blit(rotated, rotated.get_rect(center=center))

        if album_img:
            label_size = 500
            masked_album = pygame.Surface((label_size, label_size), pygame.SRCALPHA)
            mask = pygame.Surface((label_size, label_size), pygame.SRCALPHA)

            pygame.draw.circle(mask, (204, 204, 204, 204), (label_size // 2, label_size // 2), label_size // 2)
            pygame.draw.circle(mask, (0, 0, 0, 0), (label_size // 2, label_size // 2), 24)

            album_scaled = pygame.transform.smoothscale(album_img, (label_size, label_size))
            masked_album.blit(album_scaled, (0, 0))
            masked_album.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            rotated_label = pygame.transform.rotate(masked_album, angle)
            screen.blit(rotated_label, rotated_label.get_rect(center=center))

        if is_playing:
            angle = (angle + angle_speed) % 360

        screen.blit(banner, ((1080 - banner.get_width()) // 2, 800))
        pygame.display.flip()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spotify Record Player")
    parser.add_argument('--windowed', action='store_true', help='Run in windowed mode (no fullscreen)')
    args = parser.parse_args()
    run(windowed=args.windowed)
