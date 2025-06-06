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

BASE_DIR = Path(__file__).resolve().parent


def mask_album_art(img_surface, size=500):
    raw_str = pygame.image.tostring(img_surface, 'RGBA', False)
    img = Image.frombytes('RGBA', img_surface.get_size(), raw_str)
    img = img.resize((size, size))

    # Create circular mask with transparent center (record hole)
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    center_hole_radius = size // 21
    center = size // 2
    draw.ellipse((center - center_hole_radius, center - center_hole_radius,
                  center + center_hole_radius, center + center_hole_radius), fill=0)

    # Apply mask and reduce opacity
    img.putalpha(mask)
    img = img.convert('RGBA')
    pixels = img.getdata()
    new_pixels = [(r, g, b, int(a * 0.8)) for r, g, b, a in pixels]
    img.putdata(new_pixels)

    return pygame.image.fromstring(img.tobytes(), img.size, img.mode)


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
    record_image = pygame.image.load(str(random_record_path)).convert_alpha()
    record_image = pygame.transform.scale(record_image, (int(1080 * 1.25), int(1080 * 1.25)))

    icons_dir = BASE_DIR / 'spotify'
    play_btn = pygame.image.load(str(icons_dir / 'play.png'))
    pause_btn = pygame.image.load(str(icons_dir / 'pause.png'))
    skip_btn = pygame.image.load(str(icons_dir / 'skip.png'))
    prev_btn = pygame.image.load(str(icons_dir / 'previous.png'))
    banner = pygame.image.load(str(icons_dir / 'banner.png'))

    font_title = pygame.font.Font(None, 30)
    font_artist = pygame.font.Font(None, 26)

    center = (540, 540)
    angle = 0
    angle_speed = -0.5
    is_playing = True
    dragging = False
    last_mouse_pos = None
    details = None
    album_img = None
    masked_album_surface = None

    def update_details():
        nonlocal details, album_img, masked_album_surface
        try:
            new_details = get_current_playing_info()
        except Exception as e:
            print(f"Error fetching current playing info: {e}", file=sys.stderr)
            return
        if new_details:
            details = new_details
            try:
                r = requests.get(details["album_cover"])
                img = pygame.image.load(BytesIO(r.content)).convert_alpha()
                album_img = pygame.transform.scale(img, (137, 137))
                masked_album_surface = mask_album_art(img)
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

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                dragging = math.hypot(mx - center[0], my - center[1]) <= 540
                last_mouse_pos = event.pos

                banner_x = (1080 - banner.get_width()) // 2
                banner_y = 800
                gap = 51
                album_w, album_h = (137, 137) if album_img else (0, 0)
                prev_w, pause_w, skip_w = prev_btn.get_width(), pause_btn.get_width(), skip_btn.get_width()
                group_width = album_w + prev_w + pause_w + skip_w + (3 * gap)
                group_start_x = (1080 - group_width) // 2
                group_center_y = banner_y + (banner.get_height() // 2) + 30

                prev_x = group_start_x + album_w + gap
                pause_x = prev_x + prev_w + gap
                skip_x = pause_x + pause_w + gap

                prev_y = pause_y = skip_y = group_center_y - (pause_btn.get_height() // 2)

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
                    record_image = pygame.image.load(str(new_path)).convert_alpha()
                    record_image = pygame.transform.scale(record_image, (int(1080 * 1.25), int(1080 * 1.25)))
                    threading.Thread(target=update_details, daemon=True).start()

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                dragging = False
            elif event.type == pygame.MOUSEMOTION and dragging:
                dx = event.pos[0] - last_mouse_pos[0]
                angle -= dx * 0.1
                angle %= 360
                last_mouse_pos = event.pos

        screen.fill((245, 230, 200))

        rotated = pygame.transform.rotate(record_image, angle)
        screen.blit(rotated, rotated.get_rect(center=center))
        if masked_album_surface:
            rotated_album = pygame.transform.rotate(masked_album_surface, angle)
            screen.blit(rotated_album, rotated_album.get_rect(center=center))
        if is_playing:
            angle = (angle + angle_speed) % 360

        banner_x = (1080 - banner.get_width()) // 2
        banner_y = 800
        screen.blit(banner, (banner_x, banner_y))

        gap = 51
        album_w, album_h = (137, 137) if album_img else (0, 0)
        prev_w, pause_w, skip_w = prev_btn.get_width(), pause_btn.get_width(), skip_btn.get_width()
        group_width = album_w + prev_w + pause_w + skip_w + (3 * gap)
        group_start_x = (1080 - group_width) // 2
        group_center_y = banner_y + (banner.get_height() // 2) + 30

        album_x = group_start_x
        album_y = (group_center_y - (album_h // 2)) - 30
        prev_x = album_x + album_w + gap
        pause_x = prev_x + prev_w + gap
        skip_x = pause_x + pause_w + gap
        prev_y = pause_y = skip_y = group_center_y - (pause_btn.get_height() // 2)

        if album_img:
            screen.blit(album_img, (album_x, album_y))
        screen.blit(prev_btn, (prev_x, prev_y))
        screen.blit(pause_btn if is_playing else play_btn, (pause_x, pause_y))
        screen.blit(skip_btn, (skip_x, skip_y))

        if details:
            song_surf = font_title.render(details["title"], True, (255, 255, 255))
            artist_surf = font_artist.render(details["artist"], True, (255, 255, 255))
            pcx = pause_x + pause_w // 2
            tb = pause_y - 10
            ay = tb - artist_surf.get_height()
            sy = ay - 5 - song_surf.get_height()
            sx = pcx - (song_surf.get_width() // 2)
            ax = pcx - (artist_surf.get_width() // 2)
            screen.blit(song_surf, (sx, sy))
            screen.blit(artist_surf, (ax, ay))

        pygame.display.flip()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--windowed', action='store_true', help='Run in windowed mode')
    args = parser.parse_args()
    run(windowed=args.windowed)
