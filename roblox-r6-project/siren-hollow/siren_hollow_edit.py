"""
SIREN HOLLOW - trailer edit of the in-game cutscene recording.

Takes the Roblox Studio screen recording of the cutscene, crops it to the game
view, re-cuts it into a slow, creepy trailer and finishes it: cold grade,
slow push-ins, a freeze on the creature reveal, glitchy "decoding" text,
static, grain, letterbox, and a sound design built around distant air-raid
sirens (the recording's own footsteps and siren are kept underneath).

    python3 siren_hollow_edit.py RECORDING.mkv OUT.mp4

Needs Python 3 with numpy + Pillow, and ffmpeg.
"""

import math
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ------------------------------------------------------------------ words ----
LINES = {
    "intro": "EVERY NIGHT, THE SIRENS SOUND.",
    "cabin": "NOBODY KNOWS WHO TURNS THEM ON.",
    "reveal": "DON'T LOOK UP.",
}
TITLE = "SIREN HOLLOW"
SUBTITLE = "COMING SOON TO ROBLOX"
# ---------------------------------------------------------------------------

W, H, FPS = 1920, 1080, 30
SR = 48000
CROP = "crop=2112:1188:224:168"  # the game view inside the Studio window
BAR = 60  # 2:1 letterbox

# The cut: (name, kind, source in, source out / length, options)
EDL = [
    ("intro", "black", 4.0, {"text": ("intro", 0.6, 3.6)}),
    ("bus", "clip", 10.4, 16.6, {"fade_in": 1.2}),
    ("walk", "clip", 24.0, 30.2, {}),
    ("hall", "clip", 35.0, 39.8, {}),
    ("room", "clip", 39.95, 46.8, {"glitch_at": [42.07, 43.67, 45.17]}),
    ("beat", "static", 0.7, {}),
    ("cabin", "clip", 47.5, 56.8, {"zoom": (1.0, 1.14, 0.52, 0.42), "text": ("cabin", 3.0, 7.4)}),
    ("away", "clip", 63.7, 66.5, {}),
    ("stutter", "clip", 66.6, 70.0, {"glitch_at": [67.43, 68.07, 69.0]}),
    ("shelter", "clip", 79.2, 83.0, {}),
    ("reveal", "clip", 83.65, 92.03, {"text": ("reveal", 1.0, 3.8), "freeze": 1.6}),
    ("smash", "black", 1.0, {}),
    ("title", "title", 6.5, {}),
    ("end", "black", 1.5, {}),
]

FONT_DIR = "/usr/share/fonts/opentype/inter/"
FONT_BOLD = FONT_DIR + "InterDisplay-Bold.otf"
FONT_MED = FONT_DIR + "InterDisplay-Medium.otf"

rng = np.random.default_rng(23)


# =========================================================================
# Timeline
# =========================================================================

def build_timeline():
    """Output start time and length of every EDL entry."""
    t = 0.0
    out = []
    for entry in EDL:
        name, kind = entry[0], entry[1]
        if kind == "clip":
            src_in, src_out, opts = entry[2], entry[3], entry[4]
            length = src_out - src_in + opts.get("freeze", 0.0)
        else:
            src_in = src_out = None
            length, opts = entry[2], entry[3]
        out.append(dict(name=name, kind=kind, start=t, length=length, src_in=src_in, src_out=src_out, opts=opts))
        t += length
    return out, t


TIMELINE, LENGTH = build_timeline()
AT = {e["name"]: e["start"] for e in TIMELINE}


# =========================================================================
# Picture
# =========================================================================

yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
VIGNETTE = np.clip(1.0 - 0.6 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) ** 1.5, 0.3, 1)[..., None]
GRAIN = [rng.normal(0, 1, (H // 2, W // 2, 1)).astype(np.float32).repeat(2, 0).repeat(2, 1) for _ in range(6)]
SCAN = (1.0 - 0.2 * (np.arange(H) % 3 == 0)).astype(np.float32)[:, None, None]
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


def grade(img):
    """Cold, drained, readable: lift the murk, desaturate, cold shadows, warm lights."""
    img = np.clip((img - 0.012) / 0.93, 0, 1) ** 0.82
    lum = (img @ LUMA)[..., None]
    img = lum + (img - lum) * 0.62
    img += (1 - lum) ** 3 * np.array([-0.018, 0.0, 0.022], np.float32)
    img += lum ** 2 * np.array([0.03, 0.008, -0.02], np.float32)
    img = np.clip(img, 0, 1)
    return np.clip(img + 0.7 * (img - 0.5) * img * (1 - img), 0, 1)


def zoom(img, scale, cx, cy, shake=(0.0, 0.0)):
    if scale <= 1.0001 and shake == (0.0, 0.0):
        return img
    w, h = W / scale, H / scale
    x0 = min(max(cx * W - w / 2 + shake[0], 0), W - w)
    y0 = min(max(cy * H - h / 2 + shake[1], 0), H - h)
    pil = Image.fromarray((img * 255).astype(np.uint8))
    pil = pil.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + w, y0 + h))
    return np.asarray(pil, np.float32) / 255


def rgb_split(img, k):
    k = int(round(k))
    if k == 0:
        return img
    out = img.copy()
    out[:, :, 0] = np.roll(img[:, :, 0], -k, axis=1)
    out[:, :, 2] = np.roll(img[:, :, 2], k, axis=1)
    return out


def slices(img, count, strength):
    out = img.copy()
    for _ in range(count):
        y0 = int(rng.integers(0, H - 10))
        h = int(rng.integers(6, 70))
        out[y0:y0 + h] = np.roll(img[y0:y0 + h], int(rng.normal(0, strength)), axis=1)
    return out


def static(level=1.0):
    noise = rng.random((H // 3, W // 3, 1)).astype(np.float32).repeat(3, 0).repeat(3, 1)
    rows = rng.random((H, 1, 1)).astype(np.float32) * 0.35
    return np.clip(noise * 0.75 + rows, 0, 1).repeat(3, axis=2) * SCAN * level


# --- text -------------------------------------------------------------------

GLYPHS = "#%&@$/\\|<>?!=+*"


def text_mask(text, size, font_path, tracking, y):
    font = ImageFont.truetype(font_path, size)
    widths = [font.getlength(ch) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = (W - total) / 2
    layer = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(layer)
    for ch, w in zip(text, widths):
        d.text((x, y), ch, font=font, fill=255)
        x += w + tracking
    return layer


def decoding(text, u, settle=0.9):
    """Characters scramble, then lock in left to right (u = seconds since start)."""
    out = []
    for i, ch in enumerate(text):
        lock = 0.12 + settle * i / max(len(text), 1)
        if ch == " " or u >= lock:
            out.append(ch)
        else:
            out.append(GLYPHS[int(rng.integers(0, len(GLYPHS)))] if rng.random() < 0.7 else " ")
    return "".join(out)


def put_text(img, layer, alpha, color=(0.92, 0.92, 0.92), glow=8, split=0):
    mask = np.asarray(layer, np.float32)[..., None] / 255.0 * alpha
    halo = np.asarray(layer.filter(ImageFilter.GaussianBlur(glow)), np.float32)[..., None] / 255.0 * alpha * 0.5
    col = np.array(color, np.float32)
    img = img + halo * col * 0.6
    if split:
        r = np.roll(mask, -split, axis=1)
        b = np.roll(mask, split, axis=1)
        tint = np.concatenate([r, mask, b], axis=2)
        return img * (1 - mask) + tint * col
    return img * (1 - mask) + col * mask


def caption(img, key, u, length):
    """A line that decodes in, holds with the odd flicker, then glitches out."""
    text = LINES[key]
    out_t = length - u
    alpha = min(1.0, u / 0.25, out_t / 0.35)
    if alpha <= 0:
        return img
    shown = decoding(text, u) if u < 1.2 else text
    if out_t < 0.35 and rng.random() < 0.5:
        shown = decoding(text, 0.3)
    split = 0
    if u < 0.4 or out_t < 0.3 or rng.random() < 0.04:
        split = int(rng.integers(3, 9))
        alpha *= 0.85 if rng.random() < 0.5 else 1.0
    layer = text_mask(shown, 40, FONT_MED, 11, H - BAR - 124)
    return put_text(img, layer, alpha, split=split)


_title_cache = {}


def title_card(u):
    img = np.zeros((H, W, 3), np.float32)
    # a red warning light sweeping slowly, like a siren lamp in the fog
    sweep = 0.5 + 0.5 * math.sin(u * 2 * math.pi / 2.2)
    cx = W * (0.5 + 0.18 * math.sin(u * 2 * math.pi / 2.2))
    glow = np.exp(-(((xx - cx) / 520.0) ** 2 + ((yy - H * 0.47) / 240.0) ** 2))[..., None]
    img += glow * np.array([0.30, 0.02, 0.015], np.float32) * (0.35 + 0.65 * sweep)
    img += static(0.05)
    if "title" not in _title_cache:
        _title_cache["title"] = text_mask(TITLE, 124, FONT_BOLD, 30, H / 2 - 104)
        _title_cache["sub"] = text_mask(SUBTITLE, 28, FONT_MED, 13, H / 2 + 62)
    reveal = min(1.0, u / 0.9)
    if u < 0.9:
        shown = text_mask(decoding(TITLE, u, settle=0.7), 124, FONT_BOLD, 30, H / 2 - 104)
    else:
        shown = _title_cache["title"]
    flicker = 0.0 if (u < 0.9 and rng.random() < 0.3 * (1 - reveal)) else 1.0
    burst = u < 0.9 or (u > 1.5 and u % 1.7 < 0.08)
    img = put_text(img, shown, flicker, color=(0.94, 0.93, 0.93), glow=16,
                   split=int(14 * (1 - reveal) + 4) if burst else 0)
    rule = int(min(1.0, max(0.0, (u - 0.8) / 0.9)) * 640)
    if rule:
        img[H // 2 + 40:H // 2 + 43, W // 2 - rule // 2:W // 2 + rule // 2] = (0.8, 0.07, 0.05)
    a = min(1.0, max(0.0, (u - 1.9) / 0.8))
    if a:
        img = put_text(img, _title_cache["sub"], a, color=(0.72, 0.72, 0.74), glow=6)
    if burst:
        img = slices(img, 10 if u < 0.9 else 4, 50 * (1 - reveal) + 14)
    return img


def finish(img, n, grain=0.024, bars=True):
    img = img * VIGNETTE + GRAIN[n % len(GRAIN)] * grain
    if bars:
        img[:BAR] = 0
        img[H - BAR:] = 0
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def read_clip(src, start, length):
    cmd = ["ffmpeg", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", src, "-t", f"{length:.3f}",
           "-vf", f"{CROP},scale={W}:{H}:flags=lanczos,fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size = W * H * 3
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W, 3).astype(np.float32) / 255
    proc.wait()


def render_video(src, sink):
    n = 0
    for e in TIMELINE:
        frames = int(round(e["length"] * FPS))
        opts = e["opts"]
        if e["kind"] == "clip":
            clip_len = e["src_out"] - e["src_in"]
            source = read_clip(src, e["src_in"], clip_len)
            last = None
            for i in range(frames):
                u = i / FPS
                if u < clip_len - 1e-6:
                    frame = next(source, None)
                    if frame is not None:
                        last = grade(frame)
                img = last.copy()
                if "zoom" in opts:
                    z0, z1, cx, cy = opts["zoom"]
                    k = u / e["length"]
                    img = zoom(img, z0 + (z1 - z0) * (k * k * (3 - 2 * k)), cx, cy)
                if opts.get("freeze") and u >= clip_len:  # the reveal: creep in, start to shake
                    f = (u - clip_len) / opts["freeze"]
                    amp = 6 * f * f
                    img = zoom(img, 1.0 + 0.08 * f, 0.5, 0.36,
                               (float(rng.normal(0, amp)), float(rng.normal(0, amp))))
                    if f > 0.75 and rng.random() < 0.5:
                        img = slices(rgb_split(img, 6), 5, 30)
                if "fade_in" in opts:
                    img *= min(1.0, u / opts["fade_in"])
                for g in opts.get("glitch_at", []):  # jump cuts in the footage get a kick
                    if 0 <= u - (g - e["src_in"]) < 3 / FPS:
                        img = slices(rgb_split(img, 9), 8, 45)
                if i < 2 and e["name"] not in ("bus",):
                    img = rgb_split(img, 5)
                if "text" in opts:
                    key, a, b = opts["text"]
                    if a <= u < b:
                        img = caption(img, key, u - a, b - a)
                sink.write(finish(img, n).tobytes())
                n += 1
            for _ in source:  # drain
                pass
        elif e["kind"] == "black":
            for i in range(frames):
                u = i / FPS
                img = np.zeros((H, W, 3), np.float32)
                if "text" in opts:
                    key, a, b = opts["text"]
                    if a <= u < b:
                        img = caption(img, key, u - a, b - a)
                sink.write(finish(img, n, grain=0.012 if e["name"] != "end" else 0.0).tobytes())
                n += 1
        elif e["kind"] == "static":
            for i in range(frames):
                sink.write(finish(static(0.9 if i % 4 else 0.5), n).tobytes())
                n += 1
        elif e["kind"] == "title":
            for i in range(frames):
                sink.write(finish(title_card(i / FPS), n).tobytes())
                n += 1
        print(f"  video {e['name']:8s} done ({n} frames)", flush=True)
    return n


# =========================================================================
# Sound
# =========================================================================

N = int(SR * LENGTH) + SR
T = np.arange(N) / SR


def bandpass(x, lo=None, hi=None, slope=4):
    spec = np.fft.rfft(x, axis=-1)
    f = np.fft.rfftfreq(x.shape[-1], 1 / SR) + 1e-9
    g = np.ones_like(f)
    if lo:
        g *= 1 / (1 + (lo / f) ** slope)
    if hi:
        g *= 1 / (1 + (f / hi) ** slope)
    return np.fft.irfft(spec * g, x.shape[-1], axis=-1)


def notch(x, f0, width=40.0):
    """Remove a narrow band (the recording has a wavering whine around 6.5-7 kHz)."""
    spec = np.fft.rfft(x, axis=-1)
    f = np.fft.rfftfreq(x.shape[-1], 1 / SR)
    g = 1 - np.exp(-((f - f0) / width) ** 4)
    return np.fft.irfft(spec * g, x.shape[-1], axis=-1)


def env(n, attack, release):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    r = np.clip((n / SR - t) / max(release, 1e-4), 0, 1)
    return a * r


def place(bus, start, sound, gain=1.0, pan=0.0):
    i = int(start * SR)
    if sound.ndim == 1:
        sound = np.stack([sound * math.sqrt(0.5 * (1 - pan)), sound * math.sqrt(0.5 * (1 + pan))])
    j = min(N, i + sound.shape[1])
    if j > i:
        bus[:, i:j] += sound[:, : j - i] * gain


def siren(length, lo=105, hi=480, rise=2.6, hold=1.6):
    """Air-raid siren: a slow rising howl, a wavering top, a long sinking fall."""
    n = int(SR * length)
    t = np.arange(n) / SR
    up = 1 - np.exp(-t / (rise / 3))
    fall_t = np.clip(t - rise - hold, 0, None)
    down = np.exp(-fall_t / ((length - rise - hold) / 2.2))
    f = lo + (hi - lo) * up * down
    f = f * (1 + 0.006 * np.sin(2 * np.pi * 5.3 * t))
    out = np.zeros(n)
    for ratio, gain in ((1.0, 1.0), (1.498, 0.55)):  # two rotors a fifth apart
        phase = 2 * np.pi * np.cumsum(f * ratio) / SR
        for h in range(1, 9):
            out += gain * np.sin(h * phase) / h ** 0.9
    amp = (0.25 + 0.75 * up * down) * env(n, 0.4, 1.0)
    return out * amp


def reverb(x, seconds=3.5, wet=0.5):
    n = int(SR * seconds)
    ir = rng.standard_normal((2, n)) * np.exp(-np.arange(n) / SR / (seconds / 6))
    ir = bandpass(ir, hi=4500)
    ir /= np.sqrt((ir ** 2).sum(axis=1, keepdims=True))
    size = 1 << int(np.ceil(np.log2(x.shape[1] + n)))
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:, : x.shape[1]]
    return x * (1 - wet) + y * wet * 1.7


def boom(length=3.0, f0=85, f1=26):
    n = int(SR * length)
    t = np.arange(n) / SR
    freq = f1 + (f0 - f1) * np.exp(-t / 0.3)
    body = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t / 1.0)
    crack = bandpass(rng.standard_normal(n), hi=800) * np.exp(-t / 0.07) * 0.5
    return np.tanh((body + crack) * 1.8) * env(n, 0.003, 0.2)


def tick(level=1.0):
    n = int(SR * 0.18)
    burst = bandpass(rng.standard_normal(n), lo=900, hi=9000) * (rng.random(n) > 0.4)
    return burst * env(n, 0.001, 0.12) * level


def heartbeat():
    n = int(SR * 0.75)
    t = np.arange(n) / SR
    lub = np.sin(2 * np.pi * 50 * t) * np.exp(-t / 0.07)
    dub = np.zeros(n)
    k = int(SR * 0.24)
    dub[k:] = np.sin(2 * np.pi * 44 * t[: n - k]) * np.exp(-t[: n - k] / 0.06) * 0.7
    return np.tanh((lub + dub) * 2.2)


def read_audio(src, start, length):
    cmd = ["ffmpeg", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", src, "-t", f"{length:.3f}",
           "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).T.astype(np.float64)


def render_audio(src):
    dry = np.zeros((2, N))
    wet = np.zeros((2, N))

    # The recording's own sound (footsteps, its siren), brought up and cleaned.
    for e in TIMELINE:
        if e["kind"] != "clip":
            continue
        length = e["src_out"] - e["src_in"] + e["opts"].get("freeze", 0.0)
        a = read_audio(src, e["src_in"], length)
        if a.shape[1] == 0:
            continue
        a = notch(bandpass(a, lo=35), 6750.0, 330.0)
        fade = min(int(0.02 * SR), a.shape[1] // 2)
        a[:, :fade] *= np.linspace(0, 1, fade)
        a[:, -fade:] *= np.linspace(1, 0, fade)
        place(dry, e["start"], a * 10 ** (27 / 20))

    # Wind and a low drone under everything until the smash cut.
    wind = bandpass(rng.standard_normal((2, N)), lo=80, hi=900)
    gust = 0.55 + 0.45 * np.sin(2 * np.pi * T / 7.3) * np.sin(2 * np.pi * T / 3.1 + 1)
    drone = sum(np.sin(2 * np.pi * f * T + rng.uniform(0, 6)) * g
                for f, g in ((36.7, 1.0), (55.0, 0.7), (55.4, 0.6), (58.3, 0.35), (82.4, 0.25)))
    drone = bandpass(drone, hi=400)
    reveal_end = AT["smash"]
    swell = 0.5 + 0.5 * np.clip((T - AT["reveal"]) / (reveal_end - AT["reveal"]), 0, 1)
    live = (T < reveal_end).astype(float)
    dry += wind * 0.035 * gust * live
    dry += drone * 0.09 * swell * np.clip(T / 3.0, 0, 1) * live

    # Distant sirens: the opening, over the cabin, and under the title.
    place(wet, 0.3, bandpass(siren(9.0, 95, 420, 3.2, 2.0), hi=1300), 0.08, pan=-0.3)
    place(wet, AT["cabin"] + 1.5, bandpass(siren(8.5, 110, 470, 2.8, 1.8), hi=1800), 0.11, pan=0.35)
    place(wet, AT["title"] + 0.4, bandpass(siren(6.5, 100, 450, 2.4, 1.5), hi=1600), 0.12)

    # Static under the decoding text and glitches.
    st = bandpass(rng.standard_normal((2, N)), lo=1200, hi=8000)
    level = np.zeros(N)
    for e in TIMELINE:
        if e["kind"] == "static":
            level += ((T >= e["start"]) & (T < e["start"] + e["length"])) * 0.5
        text = e["opts"].get("text")
        if text:
            a = e["start"] + text[1]
            level += ((T >= a) & (T < a + 1.1)) * 0.06
    dry += st * level
    for e in TIMELINE:
        for g in e["opts"].get("glitch_at", []):
            place(dry, e["start"] + g - e["src_in"], tick(0.5))
        if e["kind"] == "clip" and e["name"] != "bus":
            place(dry, e["start"], tick(0.18))

    # Heartbeat from the stutter shots, speeding up into the reveal.
    t = AT["stutter"]
    while t < reveal_end:
        place(dry, t, heartbeat(), 0.35)
        progress = (t - AT["stutter"]) / (reveal_end - AT["stutter"])
        t += 0.95 - 0.45 * progress

    # Riser through the reveal, a hit when the frame freezes, then the smash.
    riser_len = reveal_end - AT["reveal"]
    rn = int(SR * riser_len)
    u = np.arange(rn) / rn
    rise_tone = np.sin(2 * np.pi * np.cumsum(70 * 2 ** (u * 3.5)) / SR) * u ** 3
    rise_noise = bandpass(rng.standard_normal(rn), lo=2500) * u ** 4
    place(dry, AT["reveal"], (rise_tone * 0.22 + rise_noise * 0.18))
    reveal = next(e for e in TIMELINE if e["name"] == "reveal")
    freeze_at = reveal["start"] + reveal["src_out"] - reveal["src_in"]
    place(wet, freeze_at, boom(2.0, 70, 30), 0.45)
    blast = siren(0.6, 380, 520, 0.05, 0.4)
    place(dry, reveal_end - 0.25, np.tanh(blast * 3) * env(len(blast), 0.01, 0.01), 0.3)
    place(wet, reveal_end, boom(), 0.9)

    # Title hit.
    place(wet, AT["title"], boom(3.0, 95, 28), 0.8)
    place(dry, AT["title"], tick(0.9))

    mix = dry + reverb(wet)
    i0, i1 = int(reveal_end * SR), int((reveal_end + 0.02) * SR)
    mix[:, i0:i1] *= np.linspace(1, 0, i1 - i0)[None]  # hard cut into the smash
    mix[:, int(AT["end"] * SR):] = 0  # dead silence at the end
    mix = np.tanh(mix * 1.1)
    mix /= np.max(np.abs(mix)) + 1e-9
    return (mix[:, : int(SR * LENGTH)] * 0.9).astype(np.float32)


# =========================================================================

def main():
    src, out = sys.argv[1], sys.argv[2]
    wav = out.rsplit(".", 1)[0] + "_audio.wav"
    print(f"Trailer length {LENGTH:.2f}s; building sound...", flush=True)
    audio = render_audio(src)
    import wave
    with wave.open(wav, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(audio.T, -1, 1) * 32767).astype("<i2").tobytes())
    if "--audio-only" in sys.argv:  # keep the rendered picture, swap the sound
        tmp = out + ".tmp.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", out, "-i", wav, "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", tmp],
                       check=True)
        import os
        os.replace(tmp, out)
        print("replaced sound in", out)
        return
    print("Rendering picture...", flush=True)
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                            "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-maxrate", "10M",
                            "-bufsize", "20M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                            "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    render_video(src, enc.stdin)
    enc.stdin.close()
    enc.wait()
    print("wrote", out)


if __name__ == "__main__":
    main()
