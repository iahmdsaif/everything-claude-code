"""
DEADAIR - procedural trailer soundtrack.

Synthesises the whole score and sound design with numpy (no samples, no
licences): radio static, a dark drone, footsteps that land on the
animation's real foot contacts, dying street lamps, ladder clanks, impacts on
the cuts, a riser into the title, and a hard cut to silence at the end.

    python3 make_audio.py out.wav
"""

import sys
import wave

import numpy as np

SR = 44100
LENGTH = 34.5
rng = np.random.default_rng(7)
N = int(SR * LENGTH)
TIME = np.arange(N) / SR


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------

def spectrum_filter(x, lo=None, hi=None, slope=4):
    """Smooth FFT band filter (lo/hi in Hz)."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR) + 1e-9
    gain = np.ones_like(f)
    if lo:
        gain *= 1 / (1 + (lo / f) ** slope)
    if hi:
        gain *= 1 / (1 + (f / hi) ** slope)
    return np.fft.irfft(spec * gain, len(x))


def env_ad(n, attack, decay):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-np.maximum(t - attack, 0) / decay)


def place(bus, start, sound, gain=1.0, pan=0.0):
    i = int(start * SR)
    if i >= N or i + len(sound) <= 0:
        return
    j = min(N, i + len(sound))
    s = sound[: j - i] * gain
    left, right = np.sqrt(0.5 * (1 - pan)), np.sqrt(0.5 * (1 + pan))
    bus[0, i:j] += s * left
    bus[1, i:j] += s * right


def ramp(t, t0, t1):
    return np.clip((t - t0) / (t1 - t0), 0, 1)


def window(t, a, b, fade_in=0.3, fade_out=0.3):
    return ramp(t, a, a + fade_in) * (1 - ramp(t, b - fade_out, b))


# --------------------------------------------------------------------------
# Sounds
# --------------------------------------------------------------------------

def boom(length=3.0, f0=90, f1=28):
    n = int(SR * length)
    t = np.arange(n) / SR
    freq = f1 + (f0 - f1) * np.exp(-t / 0.25)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    body = np.sin(phase) * env_ad(n, 0.004, 0.9)
    crack = spectrum_filter(rng.standard_normal(n), hi=900) * env_ad(n, 0.001, 0.08) * 0.6
    return np.tanh((body + crack) * 1.6)


def metal_hit(length=2.5, base=180):
    n = int(SR * length)
    t = np.arange(n) / SR
    partials = [1.0, 2.76, 5.40, 8.93, 13.34]
    out = sum(np.sin(2 * np.pi * base * p * t + rng.uniform(0, 6)) * np.exp(-t / (0.9 / (k + 1)))
              for k, p in enumerate(partials))
    return out * env_ad(n, 0.002, 1.2) * 0.35


def clank(base):
    n = int(SR * 0.6)
    t = np.arange(n) / SR
    out = sum(np.sin(2 * np.pi * base * p * t) * np.exp(-t / (0.12 / (k + 1)))
              for k, p in enumerate([1.0, 2.31, 3.87, 5.12]))
    click = spectrum_filter(rng.standard_normal(n), lo=2000) * env_ad(n, 0.0005, 0.01)
    return (out * 0.5 + click * 0.4) * env_ad(n, 0.001, 0.25)


def footstep(weight=1.0):
    n = int(SR * 0.25)
    noise = rng.standard_normal(n)
    thud = spectrum_filter(noise, lo=60, hi=420 + 300 * rng.random()) * env_ad(n, 0.002, 0.045)
    grit = spectrum_filter(noise, lo=1500, hi=6000) * env_ad(n, 0.001, 0.02) * 0.25
    t = np.arange(n) / SR
    low = np.sin(2 * np.pi * 70 * t) * env_ad(n, 0.002, 0.05) * 0.8
    return (thud * 1.4 + grit + low) * weight


def heartbeat():
    n = int(SR * 0.7)
    t = np.arange(n) / SR
    lub = np.sin(2 * np.pi * 52 * t) * env_ad(n, 0.005, 0.07)
    dub = np.zeros(n)
    k = int(SR * 0.22)
    dub[k:] = (np.sin(2 * np.pi * 46 * t[: n - k]) * env_ad(n - k, 0.005, 0.06)) * 0.7
    return np.tanh((lub + dub) * 2.0)


def zap(length=0.45):
    n = int(SR * length)
    t = np.arange(n) / SR
    buzz = np.sign(np.sin(2 * np.pi * 120 * t)) * 0.4 + np.sin(2 * np.pi * 360 * t) * 0.3
    crackle = spectrum_filter(rng.standard_normal(n), lo=1200) * (rng.random(n) > 0.6)
    pop = spectrum_filter(rng.standard_normal(n), hi=2500) * env_ad(n, 0.0005, 0.03) * 2
    gate = (np.sin(2 * np.pi * 37 * t) > -0.2)
    return (buzz * gate + crackle * 0.5) * env_ad(n, 0.002, 0.12) + pop


def beep(freq, length):
    n = int(SR * length)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * freq * 2.01 * t)
    return tone * np.clip(t / 0.005, 0, 1) * np.clip((length - t) / 0.005, 0, 1)


def static_bed():
    """Radio static: band-limited hiss, flutter and sparse crackles."""
    hiss = spectrum_filter(rng.standard_normal(N), lo=700, hi=7000)
    flutter = 0.6 + 0.4 * spectrum_filter(rng.standard_normal(N), hi=6) * 30
    crack_mask = rng.random(N) > 0.9993
    crackles = spectrum_filter(crack_mask * rng.standard_normal(N) * 6, lo=900)
    return hiss * np.clip(flutter, 0.1, 1.5) + crackles


def drone():
    """Dark, slowly beating cluster with a sub."""
    out = np.zeros(N)
    for f, g in ((55.0, 1.0), (55.35, 0.8), (58.27, 0.45), (82.41, 0.35), (110.2, 0.25), (36.7, 0.9)):
        phase = 2 * np.pi * f * TIME + rng.uniform(0, 6)
        out += g * (np.sin(phase) + 0.3 * np.sin(2 * phase) + 0.12 * np.sin(3 * phase))
    out = spectrum_filter(out, hi=520)
    swell = 0.75 + 0.25 * np.sin(2 * np.pi * TIME / 9.0)
    return out * swell * 0.18


def riser(length):
    n = int(SR * length)
    t = np.arange(n) / SR
    u = t / length
    freq = 120 * (2 ** (u * 4))
    tone = np.sin(2 * np.pi * np.cumsum(freq) / SR) + 0.5 * np.sin(2 * np.pi * np.cumsum(freq * 1.5) / SR)
    noise = spectrum_filter(rng.standard_normal(n), lo=2000)
    return (tone * 0.35 + noise * 0.25 * u) * u ** 2.2


def reverb(x, seconds=2.6, wet=0.35):
    n = int(SR * seconds)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / SR / (seconds / 5.5))
    ir = spectrum_filter(ir, hi=5000)
    ir /= np.sqrt(np.sum(ir ** 2))
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
    return x * (1 - wet) + y * wet * 1.6


# --------------------------------------------------------------------------
# Score
# --------------------------------------------------------------------------

def build():
    bus = np.zeros((2, N))   # dry
    fx = np.zeros((2, N))    # goes through the reverb

    # Static: up in the black opening and glitches, a bed under the shots,
    # gone for the final silence.
    st = static_bed()
    level = (0.05 + 0.25 * window(TIME, 0.0, 3.0, 0.8, 0.1)
             + 1.1 * window(TIME, 14.5, 15.0, 0.02, 0.02) + 1.1 * window(TIME, 27.5, 28.0, 0.02, 0.02)
             + 0.07 * window(TIME, 28.0, 33.0, 0.1, 0.01))
    level *= 1 - ramp(TIME, 33.0, 33.02)
    bus += st * level * 0.5

    # Drone stays low under the walk so footsteps read, swells through the chase.
    dr = drone() * window(TIME, 2.6, 33.0, 1.5, 0.01)
    dr *= 0.22 + 0.25 * ramp(TIME, 14.8, 15.2) + 0.25 * ramp(TIME, 22.0, 27.5) + 0.3 * ramp(TIME, 28.0, 28.1)
    bus += dr

    # Impacts on the big cuts, the title hit.
    for t, g in ((3.0, 0.9), (15.0, 0.8), (19.0, 0.55), (22.0, 0.5), (28.0, 1.25)):
        place(fx, t, boom(), g)
    place(fx, 28.0, metal_hit(), 0.9)
    place(fx, 14.5, metal_hit(2.0, 240), 0.35)

    # Footsteps on the animation's foot contacts (right foot plants at loop start).
    for t in np.arange(7.7, 11.5, 0.4):  # shot B walk (loop offset 0.2 s)
        place(fx, t, footstep(0.35), 1.0, pan=0.15 if int(t / 0.4) % 2 else -0.15)
    for t in np.arange(11.5, 12.45, 0.4):  # shot C walk in, then stop
        place(fx, t, footstep(0.55), 1.0, pan=0.1 if int(t / 0.4) % 2 else -0.1)
    place(fx, 12.55, footstep(0.3), 1.0)
    for t in np.arange(15.0, 19.0, 0.25):  # shot D run
        place(fx, t, footstep(0.75), 1.0, pan=0.12 if int(t / 0.25) % 2 else -0.12)
    for t in np.arange(19.0, 20.05, 0.5):  # shot E slow motion run
        place(fx, t, spectrum_filter(footstep(0.9), hi=500), 1.0)
    place(fx, 21.3, boom(1.5, 70, 30), 0.6)  # landing
    place(fx, 21.3, spectrum_filter(footstep(1.6), hi=700), 1.0)
    for k, t in enumerate(np.arange(22.0, 25.5, 0.4)):  # shot F ladder
        place(fx, t, clank(420 + 37 * (k % 3)), 0.5, pan=0.3 if k % 2 else -0.3)

    # Heartbeat builds through the stop and the chase.
    for t, g in [(t, 0.45) for t in np.arange(12.6, 14.5, 0.9)] + [(t, 0.6) for t in np.arange(15.0, 19.0, 0.55)]:
        place(bus, t, heartbeat(), g)

    # Sick lamp buzz in shot B, lamps dying in shot D.
    buzz_t = TIME[(TIME >= 7.5) & (TIME < 11.5)]
    s = np.sin(buzz_t * 23) + np.sin(buzz_t * 37.3 + 1) + np.sin(buzz_t * 61.7 + 2)
    gate = np.where(s > 1.2, 1.0, 0.25)
    hum = (np.sign(np.sin(2 * np.pi * 120 * buzz_t)) * 0.2 + np.sin(2 * np.pi * 240 * buzz_t) * 0.2) * gate
    i0 = int(7.5 * SR)
    bus[:, i0:i0 + len(hum)] += spectrum_filter(hum, hi=3000) * 0.08
    for t in (15.25, 16.625, 18.0):
        place(fx, t, zap(), 0.35, pan=0.4 if t > 16 else -0.4)

    # The signal: thin radio beeps (morse-like) under the stop and the tower top.
    pattern = [0.0, 0.12, 0.24, 0.5, 0.75, 1.0, 1.26, 1.38, 1.5]
    for base in (12.8, 25.6):
        for k, dt in enumerate(pattern):
            ln = 0.08 if k in (0, 1, 2, 6, 7, 8) else 0.2
            place(fx, base + dt, spectrum_filter(beep(1180, ln), lo=500, hi=3500), 0.06)

    # Beacon hum pulses with the red light in shots F/G.
    for t in np.arange(22.0, 27.5, 1.6):
        n = int(SR * 0.7)
        tt = np.arange(n) / SR
        pulse = np.sin(np.pi * tt / 0.7) ** 1.5 * (np.sin(2 * np.pi * 110 * tt) + 0.4 * np.sin(2 * np.pi * 220 * tt))
        place(bus, t, pulse, 0.12)

    # Slow motion: everything muffles and whooshes.
    place(fx, 19.0, spectrum_filter(riser(1.0)[::-1], hi=1200), 0.6)

    # Riser into the title, cut at the hit.
    rs = riser(3.5)
    place(bus, 24.5, rs, 0.55)
    i = int(28.0 * SR)
    bus[:, i - 200:i] *= np.linspace(1, 0, 200)

    mix = bus + np.stack([reverb(fx[0]), reverb(fx[1])])
    # Total silence at the end: dead air.
    mix[:, int(33.0 * SR):] = 0.0
    mix = np.tanh(mix * 1.15)
    mix /= np.max(np.abs(mix)) + 1e-9
    return (mix * 0.89).astype(np.float32)


def write_wav(path, stereo):
    pcm = (np.clip(stereo.T, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "deadair_audio.wav"
    write_wav(out, build())
    print("wrote", out)
