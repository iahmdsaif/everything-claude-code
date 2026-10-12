"""
DEADAIR - trailer assembly.

Takes the rendered shot frames (from deadair_trailer.py) and the soundtrack
(from make_audio.py) and builds the final video: title cards, glitch
transitions, bloom, vignette, film grain, letterbox, then encodes with ffmpeg.

    python3 assemble.py FRAMES_DIR AUDIO.wav OUT.mp4

Change the words here:
"""

import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- text ----
TITLE = "DEADAIR"
SUBTITLE = "COMING SOON TO ROBLOX"
CAPTIONS = [  # (start s, end s, text)
    (0.45, 2.75, "THE LAST BROADCAST ENDED AT 11:59 PM"),
    (4.3, 7.2, "BUT SOMETHING IS STILL ON THE AIR"),
    (25.75, 27.45, "FIND THE SIGNAL"),
]
FLASH_TEXT = "IT CAN HEAR YOU"  # flashes inside the first glitch
# ------------------------------------------------------------------------

W, H, FPS = 1280, 720, 30
LENGTH = 34.5
SHOTS = [(3.0, 7.5), (7.5, 11.5), (11.5, 14.5), (15.0, 19.0), (19.0, 22.0), (22.0, 25.5), (25.5, 27.5)]
GLITCHES = [(14.5, 15.0), (27.5, 28.0)]
TITLE_START, END_CUT = 28.0, 33.0
BAR = 40  # letterbox bar height (2:1)

FONT_DIR = "/usr/share/fonts/opentype/inter/"
FONT_BOLD = FONT_DIR + "InterDisplay-Bold.otf"
FONT_MED = FONT_DIR + "InterDisplay-Medium.otf"
if not os.path.exists(FONT_MED):
    FONT_MED = FONT_BOLD

rng = np.random.default_rng(11)

yy, xx = np.mgrid[0:H, 0:W]
VIGNETTE = (1.0 - 0.55 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) ** 1.4).clip(0.25, 1)[..., None]
GRAIN = [rng.normal(0, 1, (H, W, 1)).astype(np.float32) for _ in range(6)]
SCAN = (1.0 - 0.18 * (np.arange(H) % 3 == 0))[:, None, None]


def shot_at(t):
    for i, (a, b) in enumerate(SHOTS):
        if a <= t < b:
            return i, a, b
    return None


def load(frames_dir, t):
    f = int(round(t * 60))
    f -= f % 2
    path = os.path.join(frames_dir, f"{f:04d}.png")
    if not os.path.exists(path):
        return None
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0


def bloom(img, threshold=0.62, radius=16, amount=0.55):
    lum = img.mean(axis=2, keepdims=True)
    bright = np.clip(img * np.clip((lum - threshold) / (1 - threshold), 0, 1), 0, 1)
    glow = Image.fromarray((bright * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius))
    return img + np.asarray(glow, dtype=np.float32) / 255.0 * amount


def rgb_split(img, amount):
    if amount < 0.5:
        return img
    k = int(round(amount))
    out = img.copy()
    out[:, :, 0] = np.roll(img[:, :, 0], -k, axis=1)
    out[:, :, 2] = np.roll(img[:, :, 2], k, axis=1)
    return out


def slices(img, count, strength):
    out = img.copy()
    for _ in range(count):
        y0 = int(rng.integers(0, H - 8))
        h = int(rng.integers(4, 46))
        out[y0:y0 + h] = np.roll(img[y0:y0 + h], int(rng.normal(0, strength)), axis=1)
    return out


def static(level=1.0):
    noise = rng.random((H, W // 2, 1)).astype(np.float32).repeat(2, axis=1)
    rows = rng.random((H, 1, 1)).astype(np.float32) * 0.4
    return np.clip(noise * 0.8 + rows, 0, 1).repeat(3, axis=2) * SCAN * level


def text_layer(text, size, font_path, tracking, color=(235, 235, 235), y=None, glow=10, alpha=1.0):
    """Letter-spaced, centred text with a soft glow, as float RGBA."""
    font = ImageFont.truetype(font_path, size)
    widths = [font.getlength(ch) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = (W - total) / 2
    ascent, descent = font.getmetrics()
    y = (H - ascent) / 2 if y is None else y
    layer = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(layer)
    for ch, w in zip(text, widths):
        d.text((x, y), ch, font=font, fill=255)
        x += w + tracking
    mask = np.asarray(layer, dtype=np.float32) / 255.0
    halo = np.asarray(layer.filter(ImageFilter.GaussianBlur(glow)), dtype=np.float32) / 255.0
    col = np.array(color, dtype=np.float32) / 255.0
    return mask[..., None] * alpha, halo[..., None] * alpha * 0.45, col


def put_text(img, layer):
    mask, halo, col = layer
    img = img + halo * col
    return img * (1 - mask) + col * mask


def fade(t, a, b, inn=0.4, out=0.4):
    return max(0.0, min(1.0, (t - a) / inn, (b - t) / out))


_cache = {}


def caption(text, alpha):
    key = ("cap", text)
    if key not in _cache:
        _cache[key] = text_layer(text, 26, FONT_MED, 7, y=H - BAR - 92, glow=8)
    mask, halo, col = _cache[key]
    return mask * alpha, halo * alpha, col


def title_frame(t):
    u = t - TITLE_START
    img = np.zeros((H, W, 3), np.float32)
    # beacon glow pulsing behind the title, same rhythm as the tower light
    pulse = max(0.0, math.sin(math.pi * (u % 1.6) / 0.7)) if (u % 1.6) < 0.7 else 0.0
    glow = np.exp(-(((xx - W / 2) / 420.0) ** 2 + ((yy - H / 2) / 230.0) ** 2))[..., None]
    img += glow * np.array([0.32, 0.02, 0.015], np.float32) * (0.35 + 0.65 * pulse)
    img += static(0.06)
    if "title" not in _cache:
        _cache["title"] = text_layer(TITLE, 132, FONT_BOLD, 34, y=H / 2 - 110, glow=18)
        _cache["sub"] = text_layer(SUBTITLE, 24, FONT_MED, 12, color=(190, 190, 195), y=H / 2 + 62, glow=6)
    mask, halo, col = _cache["title"]
    reveal = min(1.0, u / 0.6)
    flicker = 0.0 if (u < 0.6 and rng.random() < 0.35 * (1 - reveal)) else 1.0
    layer = (mask * flicker, halo * flicker, col)
    img = put_text(img, layer)
    # thin red rule under the title
    line_w = int(min(1.0, max(0.0, (u - 0.5) / 0.8)) * 520)
    if line_w > 0:
        img[H // 2 + 40:H // 2 + 42, W // 2 - line_w // 2:W // 2 + line_w // 2] = (0.85, 0.08, 0.05)
    a = fade(t, TITLE_START + 1.6, END_CUT + 10, 0.7, 0.1)
    if a > 0:
        m, h, c = _cache["sub"]
        img = put_text(img, (m * a, h * a, c))
    # glitch: heavy at the reveal, then short bursts
    burst = (u < 0.6) or (u % 1.35 < 0.07 and u > 1.0)
    if burst:
        img = rgb_split(img, 14 * (1 - reveal) + 4)
        img = slices(img, 10 if u < 0.6 else 4, 40 * (1 - reveal) + 12)
    return img


def glitch_frame(t, frames_dir, a, b, flash=None):
    u = (t - a) / (b - a)
    prev = load(frames_dir, a - 1 / 30)
    nxt = load(frames_dir, b)
    choice = int(u * 15) % 5
    if choice in (0, 3) and prev is not None:
        img = slices(rgb_split(prev, 10), 14, 70)
    elif choice == 2 and nxt is not None:
        img = slices(rgb_split(nxt, 12), 14, 70)
    else:
        img = static(0.9)
    if flash and (0.25 < u < 0.42 or 0.6 < u < 0.7):
        if "flash" not in _cache:
            _cache["flash"] = text_layer(flash, 54, FONT_BOLD, 14, color=(255, 255, 255), glow=12)
        img = img * 0.25
        img = put_text(img, _cache["flash"])
        img = rgb_split(img, 6)
    return img


def finish(img, n, letterbox=True, grain=0.035):
    img = img * VIGNETTE + GRAIN[n % len(GRAIN)] * grain
    if letterbox:
        img[:BAR] = 0
        img[H - BAR:] = 0
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def frame_image(n, frames_dir):
    t = n / FPS
    for a, b in GLITCHES:
        if a <= t < b:
            return finish(glitch_frame(t, frames_dir, a, b, FLASH_TEXT if a < 20 else None), n)
    if TITLE_START <= t < END_CUT:
        return finish(title_frame(t), n)
    shot = shot_at(t)
    if shot is None:  # black cards (opening caption, final silence)
        img = np.zeros((H, W, 3), np.float32)
        for a, b, text in CAPTIONS:
            if a <= t < b and t < SHOTS[0][0]:
                img = put_text(img, caption(text, fade(t, a, b, 0.6, 0.5)))
        return finish(img, n, grain=0.02 if t < END_CUT else 0.0)
    i, a, b = shot
    img = load(frames_dir, t)
    if img is None:
        print(f"  missing render for t={t:.3f}s", file=sys.stderr)
        img = np.zeros((H, W, 3), np.float32)
    img = bloom(img)
    if i == 0:
        img *= min(1.0, (t - a) / 0.6)  # fade up from black
    elif t - a < 2 / FPS:  # two-frame glitch kick on every hard cut
        img = slices(rgb_split(img, 7), 6, 30)
    for ca, cb, text in CAPTIONS:
        if ca <= t < cb and ca >= SHOTS[0][0]:
            img = put_text(img, caption(text, fade(t, ca, cb, 0.6, 0.5)))
    return finish(img, n)


def stills(frames_dir, out_dir, times):
    """Preview: write single composited frames, e.g. --stills frames/ out/ 1.5 28.4"""
    os.makedirs(out_dir, exist_ok=True)
    for t in times:
        n = int(round(float(t) * FPS))
        Image.fromarray(frame_image(n, frames_dir)).save(os.path.join(out_dir, f"still_{float(t):05.2f}.png"))


def main():
    if sys.argv[1] == "--stills":
        stills(sys.argv[2], sys.argv[3], sys.argv[4:])
        return
    frames_dir, audio, out = sys.argv[1:4]
    total = int(round(LENGTH * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", audio, "-c:v", "libx264", "-preset", "slow", "-crf", "16",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    poster = None
    for n in range(total):
        img = frame_image(n, frames_dir)
        proc.stdin.write(img.tobytes())
        if n == int((TITLE_START + 2.2) * FPS):
            poster = img
        if n % 60 == 0:
            print(f"  {n}/{total}", flush=True)
    proc.stdin.close()
    proc.wait()
    if poster is not None:
        Image.fromarray(poster).save(os.path.splitext(out)[0] + "_poster.png")
    print("wrote", out)


if __name__ == "__main__":
    main()
