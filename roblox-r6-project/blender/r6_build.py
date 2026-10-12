"""
R6 Animation Pack - Blender builder
===================================

Builds a Roblox-accurate R6 rig and a full movement animation pack as normal,
editable Blender actions (Bezier keys, loop-perfect cycles at 60 fps).

  * Part sizes and joint pivots match Roblox R6 Motor6Ds exactly, so what you
    see in Blender is what you get in Studio.
  * Bones are named after the Roblox parts (Torso, Head, Right Arm, ...).
  * Every animation is built from layered, phase-offset curves (overlap,
    drag, follow-through, head stabilisation) so nothing snaps or pops.

Run it inside YOUR Blender (4.4 or newer, 5.x recommended):
    Scripting tab -> Open -> r6_build.py -> Run Script
It only touches the "R6 AnimPack" collection and actions named "R6_*", so it
is safe to run in an existing file (re-running rebuilds them).

Headless:
    blender --background --python r6_build.py -- --save R6_AnimPack.blend
"""

import math
import sys

import bpy
from mathutils import Euler, Matrix, Vector

FPS = 60
TAU = math.tau
COLLECTION = "R6 AnimPack"
RIG_NAME = "R6 Rig"
ACTION_PREFIX = "R6_"

# Roblox character space: x = right, y = up, z = back (character faces -z).
# Blender armature space: the character faces -Y with its right side on -X.
# A maps Roblox vectors into Blender vectors (a proper rotation, det = +1).
A = Matrix(((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))
TORSO_HEIGHT = 3.0  # torso centre above the ground with HipHeight 0

# name: (parent, pivot, part centre, part size) - all in Roblox torso space.
# Pivots are the Motor6D C0 positions, so rotations happen exactly where
# Roblox rotates them (R6 shoulders pivot at the inner top edge, hips at
# the outer top edge).
JOINTS = {
    "Torso": ("HumanoidRootPart", (0, 0, 0), (0, 0, 0), (2, 2, 1)),
    "Head": ("Torso", (0, 1, 0), (0, 1.5, 0), (2, 1, 1)),
    "Right Arm": ("Torso", (1, 0.5, 0), (1.5, 0, 0), (1, 2, 1)),
    "Left Arm": ("Torso", (-1, 0.5, 0), (-1.5, 0, 0), (1, 2, 1)),
    "Right Leg": ("Torso", (1, -1, 0), (0.5, -2, 0), (1, 2, 1)),
    "Left Leg": ("Torso", (-1, -1, 0), (-0.5, -2, 0), (1, 2, 1)),
}
LIMBS = ("Right Arm", "Left Arm", "Right Leg", "Left Leg")


def rbx_point(v):
    return A @ Vector(v) + Vector((0, 0, TORSO_HEIGHT))


def srgb(r, g, b):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (lin(r), lin(g), lin(b), 1.0)


# --------------------------------------------------------------------------
# Small maths helpers
# --------------------------------------------------------------------------

def rad(d):
    return math.radians(d)


def rx(d):
    return Matrix.Rotation(rad(d), 3, "X")


def ry(d):
    return Matrix.Rotation(rad(d), 3, "Y")


def rz(d):
    return Matrix.Rotation(rad(d), 3, "Z")


def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def smoother(x):
    """Quintic smootherstep: zero velocity AND acceleration at both ends."""
    x = clamp01(x)
    return x * x * x * (x * (6 * x - 15) + 10)


def ramp(t, t0, t1, v0, v1):
    return v0 + (v1 - v0) * smoother((t - t0) / (t1 - t0))


def bump(t, t0, t1):
    """Smooth 0 -> 1 -> 0 hump over [t0, t1]."""
    if t <= t0 or t >= t1:
        return 0.0
    return math.sin(math.pi * (t - t0) / (t1 - t0)) ** 2


def warp(phi, w):
    """Gait phase warp. w > 0 lengthens stance (walk), w < 0 shortens it (run)."""
    return phi - w * (1.0 - math.cos(phi))


# --------------------------------------------------------------------------
# Pose language (all angles in degrees, all relative to the parent part)
#   Torso: lean (forward +), tilt (to the right +), turn (to the left +),
#          bob (up +), sway (to the right +), push (forward +)
#   Head : nod (down +), tilt, turn (same as torso)
#   Limbs: swing (forward/up +), spread (outward +), twist (outward +)
#   Legs are given in WORLD terms (upright body); the torso's rotation is
#   compensated automatically so feet stay planted while the body moves.
# --------------------------------------------------------------------------

def torso_rot(p):
    return ry(p.get("turn", 0)) @ rx(-p.get("lean", 0)) @ rz(-p.get("tilt", 0))


def head_rot(p):
    return ry(p.get("turn", 0)) @ rx(-p.get("nod", 0)) @ rz(-p.get("tilt", 0))


def limb_rot(name, p):
    side = 1.0 if name.startswith("Right") else -1.0
    return (rx(p.get("swing", 0))
            @ rz(side * p.get("spread", 0))
            @ ry(-side * p.get("twist", 0)))


def pose_to_char(pose):
    """pose params -> {joint: (3x3 rotation, translation)} in Roblox torso space."""
    out = {}
    tp = pose.get("Torso", {})
    r_torso = torso_rot(tp)
    out["Torso"] = (r_torso, Vector((tp.get("sway", 0), tp.get("bob", 0), -tp.get("push", 0))))
    out["Head"] = (head_rot(pose.get("Head", {})), Vector())
    for name in LIMBS:
        r = limb_rot(name, pose.get(name, {}))
        if "Leg" in name:
            r = r_torso.inverted() @ r
        out[name] = (r, Vector())
    return out


def add(*poses):
    """Sum pose dictionaries parameter by parameter."""
    out = {}
    for pose in poses:
        for joint, params in pose.items():
            dst = out.setdefault(joint, {})
            for k, v in params.items():
                dst[k] = dst.get(k, 0.0) + v
    return out


# Half sizes used for floor contact (the head mesh is ~1.25 studs, not its 2x1x1 part).
CONTACT_HALF = {"Torso": (1.0, 1.0, 0.5), "Head": (0.62, 0.6, 0.62), "Right Arm": (0.5, 1.0, 0.5),
                "Left Arm": (0.5, 1.0, 0.5), "Right Leg": (0.5, 1.0, 0.5), "Left Leg": (0.5, 1.0, 0.5)}


def ground(pose, lift=0.0, softness=0.025, whole_body=False, exclude=()):
    """R6 has no knees, so feet can only be kept on the floor by moving the
    whole body. Raise/lower the torso so the lowest corner of either leg block
    touches the ground exactly (soft-min keeps the result smooth), then add
    `lift` (>= 0) on top for flight phases. With whole_body=True every part
    counts (lying down, kneeling, reaching to the floor)."""
    pose = {k: dict(v) for k, v in pose.items()}
    pose.setdefault("Torso", {})["bob"] = 0.0
    rots = pose_to_char(pose)
    r_torso, t_torso = rots["Torso"]
    heights = []
    parts = [p for p in JOINTS if p not in exclude] if whole_body else ["Right Leg", "Left Leg"]
    for part in parts:
        pivot, centre = Vector(JOINTS[part][1]), Vector(JOINTS[part][2])
        r_part = rots[part][0]
        hx, hy, hz = CONTACT_HALF[part]
        for cx in (-hx, hx):
            for cy in ((-hy, hy) if whole_body else (-hy,)):
                for cz in (-hz, hz):
                    corner = Vector((cx, cy, cz))
                    if part == "Torso":
                        p = corner
                    else:
                        p = pivot + r_part @ (centre - pivot + corner)
                    heights.append((r_torso @ p + t_torso).y + TORSO_HEIGHT)
    low = min(heights)
    soft_min = low - softness * math.log(sum(math.exp(-(h - low) / softness) for h in heights))
    pose["Torso"]["bob"] = -soft_min + lift
    return pose


# --------------------------------------------------------------------------
# Animations
# --------------------------------------------------------------------------

def breath(phi):
    """Natural breath shape: quicker inhale, slower exhale."""
    return math.sin(phi) + 0.12 * math.sin(2 * phi + 0.6)


def idle(t):
    phi = TAU * t / 4.0
    b = breath(phi)
    lean = 1.2 - 0.8 * b
    tilt = 0.8 * math.sin(phi + 0.9)
    turn = 1.2 * math.sin(phi + 2.1) + 0.4 * math.sin(2 * phi)
    lean_lag = 1.2 - 0.8 * breath(phi - 0.4)
    pose = {
        "Torso": dict(lean=lean, tilt=tilt, turn=turn, sway=0.035 * math.sin(phi + 0.9)),
        "Head": dict(nod=-0.8 * lean + 0.8 + 0.9 * math.sin(phi - 1.4),
                     turn=-0.6 * turn + 4.0 * math.sin(phi + 0.4) + 1.2 * math.sin(2 * phi + 1.0),
                     tilt=-0.5 * tilt + 1.5 * math.sin(phi + 2.5)),
        "Right Leg": dict(swing=0.6, spread=2.2),
        "Left Leg": dict(swing=-0.6, spread=2.2),
    }
    for name, lag, ofs in (("Right Arm", 0.7, 0.5), ("Left Arm", 0.9, 0.6)):
        pose[name] = dict(
            swing=2.5 + 1.5 * math.sin(phi - lag) + 0.8 * lean_lag,
            spread=4.0 + 1.6 * breath(phi - ofs),
            twist=1.0 + 0.6 * math.sin(phi - lag - 0.5),
        )
    return ground(pose, lift=0.012 * (b + 1.12), softness=0.004)


def idle_look(t):
    """8 s idle variant: glance left, glance right, settle. Breathing continues."""
    base = idle(t % 4.0)
    turn = (ramp(t, 1.0, 2.0, 0, 38) + ramp(t, 3.4, 4.8, 0, -70) + ramp(t, 5.8, 7.0, 0, 32))
    turn_late = (ramp(t - 0.18, 1.0, 2.0, 0, 38) + ramp(t - 0.18, 3.4, 4.8, 0, -70)
                 + ramp(t - 0.18, 5.8, 7.0, 0, 32))
    dip = 4.0 * (bump(t, 1.0, 2.0) + bump(t, 3.4, 4.8) + bump(t, 5.8, 7.0))
    overlay = {
        "Torso": dict(turn=0.28 * turn_late),
        "Head": dict(turn=turn - 0.28 * turn_late, nod=dip, tilt=0.06 * turn),
        "Right Arm": dict(swing=-0.05 * turn_late),
        "Left Arm": dict(swing=0.05 * turn_late),
    }
    # Re-ground: the torso turn changes which foot corner is lowest.
    return ground(add(base, overlay), lift=0.012 * (breath(TAU * (t % 4.0) / 4.0) + 1.12),
                  softness=0.004)


def gait(t, cycle, leg_amp, leg_bias, stance_warp, arm_amp, arm_bias, arm_lag,
         arm_spread, arm_flare, lean, lean_amp, turn_amp, tilt_amp, sway_amp,
         flight, head_bob, swing_lift, arm_cross=0.0):
    """Shared locomotion engine for walk and run. Right leg plants at t = 0."""
    phi = TAU * t / cycle

    def leg_swing(ph):
        return leg_amp * math.cos(warp(ph, stance_warp)) + leg_bias

    def leg_spread(ph):
        # Foot moves forward during swing phase: lift it a touch outward.
        s = -math.sin(warp(ph, stance_warp))
        return 1.5 + swing_lift * max(0.0, s) ** 2

    def arm(ph):
        c = math.cos(ph - arm_lag)
        return dict(
            swing=-arm_amp * c + arm_bias + 0.08 * arm_amp * math.sin(2 * (ph - arm_lag) - 0.5),
            spread=arm_spread + arm_flare * (1 - math.cos(2 * (ph - arm_lag))) / 2 + arm_cross * c,
            twist=2.0 + 0.5 * arm_cross * c,
        )

    def torso_turn(ph):
        return -turn_amp * math.cos(ph - arm_lag - 0.3)

    def torso_tilt(ph):
        return tilt_amp * math.sin(ph - 0.3)

    torso = dict(
        lean=lean + lean_amp * math.cos(2 * phi - 0.5),
        turn=torso_turn(phi),
        tilt=torso_tilt(phi),
        sway=sway_amp * math.sin(phi - 0.6),
    )
    pose = {
        "Torso": torso,
        "Head": dict(
            nod=-0.75 * torso["lean"] + 1.5 + head_bob * math.cos(2 * phi - 1.2),
            turn=-0.8 * torso_turn(phi - 0.25),
            tilt=-0.6 * torso_tilt(phi - 0.3),
        ),
        "Right Leg": dict(swing=leg_swing(phi), spread=leg_spread(phi)),
        "Left Leg": dict(swing=leg_swing(phi + math.pi), spread=leg_spread(phi + math.pi)),
        "Right Arm": arm(phi),
        "Left Arm": arm(phi + math.pi),
    }
    # Feet locked to the floor; runs add a smooth hop after each push-off.
    hop = flight * (0.5 - 0.5 * math.cos(2 * phi - 2.2)) ** 2
    return ground(pose, lift=hop)


def walk(t):
    return gait(t, cycle=0.8, leg_amp=28, leg_bias=2, stance_warp=0.3,
                arm_amp=24, arm_bias=3, arm_lag=0.4, arm_spread=4.0, arm_flare=1.5,
                lean=4, lean_amp=1.2, turn_amp=4, tilt_amp=1.5, sway_amp=0.06,
                flight=0.0, head_bob=1.5, swing_lift=2.0)


def run(t):
    return gait(t, cycle=0.5, leg_amp=48, leg_bias=6, stance_warp=-0.22,
                arm_amp=46, arm_bias=14, arm_lag=0.35, arm_spread=7.0, arm_flare=2.0,
                lean=11, lean_amp=2.0, turn_amp=7, tilt_amp=2.0, sway_amp=0.05,
                flight=0.16, head_bob=2.5, swing_lift=3.0, arm_cross=3.0)


def fall(t):
    phi = TAU * t / 1.0

    def arm(ph):
        return dict(swing=150 + 5 * math.sin(ph) + 4 * math.sin(2 * ph + 0.7),
                    spread=30 + 6 * math.sin(2 * ph + 0.8) + 3 * math.sin(ph + 1.9),
                    twist=4 * math.sin(ph + 0.3))

    return {
        "Torso": dict(lean=4 + 2 * math.sin(2 * phi + 0.3), turn=2 * math.sin(phi),
                      tilt=1.5 * math.sin(phi + 1.2)),
        "Head": dict(nod=-8 + 2 * math.sin(2 * phi - 0.6), turn=-1.5 * math.sin(phi - 0.4)),
        "Right Arm": arm(phi),
        "Left Arm": arm(phi + math.pi),
        "Right Leg": dict(swing=12 + 9 * math.sin(phi + 0.4), spread=4 + 1.5 * math.sin(2 * phi)),
        "Left Leg": dict(swing=12 - 9 * math.sin(phi + 0.4), spread=4 + 1.5 * math.sin(2 * phi)),
    }


def climb(t):
    phi = TAU * t / 0.8

    def arm(ph):
        return dict(swing=145 + 28 * math.cos(ph), spread=10 - 4 * math.cos(ph), twist=3)

    def leg(ph):
        return dict(swing=18 - 22 * math.cos(ph), spread=4)

    return {
        "Torso": dict(lean=3, bob=0.1 * math.sin(2 * phi - 0.5),
                      tilt=2.5 * math.sin(phi - 0.3), sway=0.06 * math.sin(phi - 0.3)),
        "Head": dict(nod=-10 + 1.5 * math.sin(2 * phi - 1.0), turn=3 * math.sin(phi - 0.6)),
        "Right Arm": arm(phi),
        "Left Arm": arm(phi + math.pi),
        "Right Leg": leg(phi),
        "Left Leg": leg(phi + math.pi),
    }


def sit(t):
    phi = TAU * t / 4.0
    b = breath(phi)
    return {
        "Torso": dict(lean=-2 - 0.8 * b, bob=0.02 * b, turn=0.8 * math.sin(phi + 2.1)),
        "Head": dict(nod=2 + 1.0 * math.sin(phi - 1.4), turn=3 * math.sin(phi + 0.4),
                     tilt=1.2 * math.sin(phi + 2.5)),
        "Right Arm": dict(swing=12 + 1.2 * breath(phi - 0.5), spread=5 + 1.2 * breath(phi - 0.6)),
        "Left Arm": dict(swing=12 + 1.2 * breath(phi - 0.7), spread=5 + 1.2 * breath(phi - 0.8)),
        "Right Leg": dict(swing=90, spread=3),
        "Left Leg": dict(swing=88, spread=3),
    }


def tool_hold(t):
    phi = TAU * t / 4.0
    return {"Right Arm": dict(swing=90 + 1.2 * breath(phi - 0.5),
                              spread=0.8 * math.sin(phi + 1.0), twist=0)}


# Key-pose animations (Blender interpolates between these with clamped
# Bezier handles - no overshoot, fast-out / slow-in).

JUMP_KEYS = [
    (0, {"Torso": dict(lean=4), "Head": dict(nod=0),
         "Right Arm": dict(swing=10, spread=5), "Left Arm": dict(swing=10, spread=5),
         "Right Leg": dict(swing=0, spread=2), "Left Leg": dict(swing=0, spread=2)}),
    (7, {"Torso": dict(lean=-5, bob=0.08), "Head": dict(nod=-7),
         "Right Arm": dict(swing=112, spread=14), "Left Arm": dict(swing=110, spread=15),
         "Right Leg": dict(swing=22, spread=3), "Left Leg": dict(swing=-12, spread=3)}),
    (15, {"Torso": dict(lean=-3, bob=0.05), "Head": dict(nod=-8),
          "Right Arm": dict(swing=158, spread=20), "Left Arm": dict(swing=156, spread=21),
          "Right Leg": dict(swing=30, spread=3), "Left Leg": dict(swing=-8, spread=3)}),
    (30, {"Torso": dict(lean=2), "Head": dict(nod=-6),
          "Right Arm": dict(swing=152, spread=27), "Left Arm": dict(swing=150, spread=28),
          "Right Leg": dict(swing=20, spread=4), "Left Leg": dict(swing=-2, spread=4)}),
]

# Landing absorbs the impact by splitting the legs (the body drops because
# the feet stay glued to the floor), with the head and arms following late.
LAND_KEYS = [
    (0, ground(fall(0), softness=0.004)),
    (5, ground({"Torso": dict(lean=12), "Head": dict(nod=3),
                "Right Arm": dict(swing=62, spread=40), "Left Arm": dict(swing=60, spread=41),
                "Right Leg": dict(swing=24, spread=3), "Left Leg": dict(swing=-21, spread=3)})),
    (9, ground({"Torso": dict(lean=11), "Head": dict(nod=12),
                "Right Arm": dict(swing=26, spread=30), "Left Arm": dict(swing=25, spread=31),
                "Right Leg": dict(swing=22, spread=3), "Left Leg": dict(swing=-19, spread=3)})),
    (17, ground({"Torso": dict(lean=4), "Head": dict(nod=3),
                 "Right Arm": dict(swing=7, spread=11), "Left Arm": dict(swing=7, spread=11),
                 "Right Leg": dict(swing=6, spread=2.5), "Left Leg": dict(swing=-5, spread=2.5)})),
    (30, idle(0)),
]


# Getting up: lying on the back -> sit up -> knees-forward crouch -> lunge -> stand.
# Every key is grounded on the whole body so nothing sinks through the floor;
# the head and arms trail the torso by a few frames for weight.
def _gu(torso, head, ra, la, rl, ll):
    return ground({"Torso": torso, "Head": head, "Right Arm": ra, "Left Arm": la,
                   "Right Leg": rl, "Left Leg": ll}, softness=0.004, whole_body=True)


GETUP_KEYS = [
    (0, _gu(dict(lean=-90, tilt=2), dict(nod=-4, tilt=10, turn=8),
            dict(swing=-2, spread=12), dict(swing=2, spread=9),
            dict(swing=90, spread=5), dict(swing=88, spread=3))),
    (20, _gu(dict(lean=-88, tilt=1), dict(nod=10, tilt=4, turn=3),
             dict(swing=-6, spread=16), dict(swing=-4, spread=14),
             dict(swing=90, spread=5), dict(swing=89, spread=3))),
    (46, _gu(dict(lean=-22), dict(nod=6),
             dict(swing=-38, spread=16), dict(swing=-36, spread=15),
             dict(swing=88, spread=6), dict(swing=86, spread=5))),
    (62, _gu(dict(lean=-4), dict(nod=-4),
             dict(swing=-20, spread=12), dict(swing=-18, spread=12),
             dict(swing=82, spread=7), dict(swing=80, spread=6))),
    (84, _gu(dict(lean=34), dict(nod=-18),
             dict(swing=48, spread=10), dict(swing=44, spread=12),
             dict(swing=56, spread=6), dict(swing=40, spread=5))),
    (104, _gu(dict(lean=30, tilt=-3), dict(nod=-14),
              dict(swing=22, spread=14), dict(swing=18, spread=16),
              dict(swing=34, spread=4), dict(swing=-34, spread=4))),
    (124, _gu(dict(lean=9, tilt=-1), dict(nod=-4),
              dict(swing=6, spread=8), dict(swing=5, spread=9),
              dict(swing=10, spread=3), dict(swing=-9, spread=3))),
    (150, idle(0)),
]

# Picking something up off the floor with the right hand, then a look at it.
# R6 legs can't bend, so the body drops into a low lunge and bows deep over
# the front leg to bring the hand down to the floor.
def _pu(torso, head, ra, la, rl, ll):
    return ground({"Torso": torso, "Head": head, "Right Arm": ra, "Left Arm": la,
                   "Right Leg": rl, "Left Leg": ll}, softness=0.004, whole_body=True,
                  exclude=("Right Arm", "Left Arm"))


PICKUP_KEYS = [
    (0, idle(0)),
    (16, _pu(dict(lean=5, tilt=1), dict(nod=24, turn=-3),
             dict(swing=4, spread=5), dict(swing=3, spread=5),
             dict(swing=2, spread=2), dict(swing=-1, spread=2))),
    (38, _pu(dict(lean=46, tilt=-3, turn=-6), dict(nod=0, turn=-2),
             dict(swing=62, spread=5, twist=-5), dict(swing=26, spread=11),
             dict(swing=36, spread=3), dict(swing=-33, spread=3))),
    (54, _pu(dict(lean=72, tilt=-4, turn=-8), dict(nod=-10, turn=-3),
             dict(swing=90, spread=4, twist=-8), dict(swing=48, spread=10),
             dict(swing=58, spread=3), dict(swing=-58, spread=3))),
    (66, _pu(dict(lean=71, tilt=-4, turn=-8), dict(nod=-9, turn=-3),
             dict(swing=87, spread=3, twist=-12), dict(swing=47, spread=10),
             dict(swing=58, spread=3), dict(swing=-58, spread=3))),
    (82, _pu(dict(lean=44, tilt=-2, turn=-5), dict(nod=4, turn=-3),
             dict(swing=64, spread=-2, twist=-18), dict(swing=22, spread=9),
             dict(swing=38, spread=3), dict(swing=-34, spread=3))),
    (100, _pu(dict(lean=12, tilt=-1, turn=-3), dict(nod=22, turn=-4),
              dict(swing=56, spread=-4, twist=-22), dict(swing=10, spread=7),
              dict(swing=12, spread=3), dict(swing=-8, spread=3))),
    (118, _pu(dict(lean=2, turn=-2), dict(nod=16, tilt=6, turn=-6),
              dict(swing=78, spread=-8, twist=-28), dict(swing=6, spread=6),
              dict(swing=3, spread=2), dict(swing=-2, spread=2))),
    (134, _pu(dict(lean=2, turn=-1), dict(nod=14, tilt=8, turn=-8),
              dict(swing=80, spread=-9, twist=-30), dict(swing=5, spread=6),
              dict(swing=2, spread=2), dict(swing=-2, spread=2))),
    (164, idle(0)),
]


# name, frames, loop, key step, handles, Roblox priority, bake step,
# source (function of seconds, or key list), exported joints, stride (studs/cycle)
ANIMS = [
    dict(name="Idle", frames=240, loop=True, step=20, handles="AUTO", priority="Core",
         bake=2, source=idle),
    dict(name="IdleLook", frames=480, loop=True, step=12, handles="AUTO_CLAMPED",
         priority="Core", bake=2, source=idle_look),
    dict(name="Walk", frames=48, loop=True, step=4, handles="AUTO", priority="Core",
         bake=1, source=walk, stride=5.0),
    dict(name="Run", frames=30, loop=True, step=3, handles="AUTO", priority="Core",
         bake=1, source=run, stride=8.0),
    dict(name="Jump", frames=30, loop=False, step=None, handles="AUTO_CLAMPED",
         priority="Core", bake=1, source=JUMP_KEYS),
    dict(name="Fall", frames=60, loop=True, step=6, handles="AUTO", priority="Core",
         bake=1, source=fall),
    dict(name="Land", frames=30, loop=False, step=None, handles="AUTO_CLAMPED",
         priority="Idle", bake=1, source=LAND_KEYS),
    dict(name="Climb", frames=48, loop=True, step=4, handles="AUTO", priority="Core",
         bake=1, source=climb, stride=9.0),
    dict(name="Sit", frames=240, loop=True, step=20, handles="AUTO", priority="Core",
         bake=2, source=sit),
    dict(name="ToolHold", frames=240, loop=True, step=20, handles="AUTO", priority="Movement",
         bake=2, source=tool_hold, joints=["Right Arm"]),
    dict(name="GetUp", frames=150, loop=False, step=None, handles="AUTO_CLAMPED",
         priority="Action", bake=1, source=GETUP_KEYS),
    dict(name="PickUp", frames=164, loop=False, step=None, handles="AUTO_CLAMPED",
         priority="Action", bake=1, source=PICKUP_KEYS),
]


# --------------------------------------------------------------------------
# Rig
# --------------------------------------------------------------------------

def get_collection():
    col = bpy.data.collections.get(COLLECTION)
    if col is None:
        col = bpy.data.collections.new(COLLECTION)
        bpy.context.scene.collection.children.link(col)
    for ob in list(col.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    return col


def make_material(name, color, face=None):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.42
    bsdf.inputs["Base Color"].default_value = color
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if face is not None:
        # Project the face image onto the front of the head (object space).
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sep.inputs[0])
        u = nt.nodes.new("ShaderNodeMath")
        u.operation = "MULTIPLY_ADD"
        u.inputs[1].default_value = 0.75
        u.inputs[2].default_value = 0.5
        nt.links.new(sep.outputs["X"], u.inputs[0])
        v = nt.nodes.new("ShaderNodeMath")
        v.operation = "MULTIPLY_ADD"
        v.inputs[1].default_value = 0.75
        v.inputs[2].default_value = 0.5
        nt.links.new(sep.outputs["Z"], v.inputs[0])
        comb = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(u.outputs[0], comb.inputs["X"])
        nt.links.new(v.outputs[0], comb.inputs["Y"])
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = face
        tex.extension = "CLIP"
        nt.links.new(comb.outputs[0], tex.inputs["Vector"])
        front = nt.nodes.new("ShaderNodeMath")
        front.operation = "LESS_THAN"
        front.inputs[1].default_value = -0.15
        nt.links.new(sep.outputs["Y"], front.inputs[0])
        mask = nt.nodes.new("ShaderNodeMath")
        mask.operation = "MULTIPLY"
        nt.links.new(tex.outputs["Alpha"], mask.inputs[0])
        nt.links.new(front.outputs[0], mask.inputs[1])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        # ShaderNodeMix has one socket per data type; 6/7 are the colour A/B.
        mix.inputs[6].default_value = color
        mix.inputs[7].default_value = (0.01, 0.01, 0.01, 1)
        nt.links.new(mask.outputs[0], mix.inputs[0])
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    return mat


def make_face_image():
    name = "R6_Face"
    img = bpy.data.images.get(name)
    if img:
        return img
    size = 256
    img = bpy.data.images.new(name, size, size, alpha=True)
    px = [0.0] * (size * size * 4)

    def put(x, y, a):
        i = (y * size + x) * 4
        if a > px[i + 3]:
            px[i:i + 4] = [0.0, 0.0, 0.0, a]

    for y in range(size):
        for x in range(size):
            u = (x + 0.5) / size * 2 - 1
            v = (y + 0.5) / size * 2 - 1
            a = 0.0
            for ex in (-0.3, 0.3):  # eyes: tall ovals
                d = ((u - ex) / 0.085) ** 2 + ((v - 0.2) / 0.17) ** 2
                a = max(a, clamp01((1.0 - d) * 6))
            r = math.hypot(u, (v + 0.02) * 1.15)  # smile: arc under the eyes
            if v < -0.08 and abs(u) < 0.5:
                a = max(a, clamp01((0.045 - abs(r - 0.48)) * 60))
            put(x, y, a)
    img.pixels = px
    img.pack()
    return img


def block_mesh(name, size, bevel=0.06):
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for vert in bm.verts:
        vert.co = Vector((vert.co.x * size[0], vert.co.y * size[1], vert.co.z * size[2]))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    mod = ob.modifiers.new("Bevel", "BEVEL")
    mod.width = bevel
    mod.segments = 3
    mod.limit_method = "ANGLE"
    for poly in me.polygons:
        poly.use_smooth = True
    return ob


def head_mesh(name):
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=40, radius1=0.62, radius2=0.62, depth=1.2)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    mod = ob.modifiers.new("Bevel", "BEVEL")
    mod.width = 0.24
    mod.segments = 6
    mod.limit_method = "ANGLE"
    for poly in me.polygons:
        poly.use_smooth = True
    return ob


def build_rig():
    active = bpy.context.view_layer.objects.active
    if active is not None and active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    col = get_collection()
    arm = bpy.data.armatures.get(RIG_NAME) or bpy.data.armatures.new(RIG_NAME)
    rig = bpy.data.objects.new(RIG_NAME, arm)
    col.objects.link(rig)
    rig.show_in_front = True
    arm.display_type = "STICK"

    view_layer = bpy.context.view_layer
    for ob in view_layer.objects:
        ob.select_set(False)
    view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for b in list(arm.edit_bones):
        arm.edit_bones.remove(b)
    root = arm.edit_bones.new("HumanoidRootPart")
    root.head, root.tail, root.roll = (0, 0, 0), (0, 0, 0.8), 0
    for name, (parent, pivot, _c, _s) in JOINTS.items():
        b = arm.edit_bones.new(name)
        head = rbx_point(pivot)
        down = name in LIMBS
        b.head = head
        b.tail = head + Vector((0, 0, -1.5 if down else 1.0))
        b.roll = 0
        b.use_connect = False
        b.parent = arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in rig.pose.bones:
        pb.rotation_mode = "XYZ"

    face = make_face_image()
    colors = {
        "Head": srgb(245, 205, 48), "Right Arm": srgb(245, 205, 48),
        "Left Arm": srgb(245, 205, 48), "Torso": srgb(13, 105, 172),
        "Right Leg": srgb(164, 189, 71), "Left Leg": srgb(164, 189, 71),
    }
    for name, (_p, _pv, centre, size) in JOINTS.items():
        if name == "Head":
            ob = head_mesh("R6 " + name)
            mat = make_material("R6 Head", colors[name], face)
        else:
            ob = block_mesh("R6 " + name, (size[0], size[2], size[1]))
            mat = make_material("R6 " + name, colors[name])
        ob.data.materials.append(mat)
        col.objects.link(ob)
        ob.parent = rig
        ob.parent_type = "BONE"
        ob.parent_bone = name
        view_layer.update()
        ob.matrix_world = Matrix.Translation(rbx_point(centre))
    return rig


# --------------------------------------------------------------------------
# Baking poses into Blender actions
# --------------------------------------------------------------------------

def pose_to_basis(rig, pose):
    """Convert a pose to per-bone (euler-matrix, location) basis values."""
    out = {}
    for name, (r_char, t_char) in pose_to_char(pose).items():
        rest = rig.data.bones[name].matrix_local.to_3x3()
        r_bl = A @ r_char @ A.transposed()
        basis = rest.transposed() @ r_bl @ rest
        loc = rest.transposed() @ (A @ t_char)
        out[name] = (basis, loc)
    return out


def sample_keys(spec):
    src = spec["source"]
    if callable(src):
        frames = list(range(0, spec["frames"] + 1, spec["step"]))
        if frames[-1] != spec["frames"]:
            frames.append(spec["frames"])
        keys = []
        for f in frames:
            t = (f % spec["frames"] if spec["loop"] else f) / FPS
            keys.append((f, src(t)))
        return keys
    # key-pose list: any joint or parameter a key leaves out is neutral (0)
    return list(src)


def build_action(rig, spec):
    name = ACTION_PREFIX + spec["name"]
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    slot = act.slots.new(id_type="OBJECT", name=rig.name)
    from bpy_extras import anim_utils
    bag = anim_utils.action_ensure_channelbag_for_slot(act, slot)

    joints = spec.get("joints") or list(JOINTS)
    keys = sample_keys(spec)
    channels = {}
    prev = {}
    for frame, pose in keys:
        basis = pose_to_basis(rig, pose)
        for joint in joints:
            mat, loc = basis[joint]
            eul = mat.to_euler("XYZ", prev.get(joint, Euler()))
            prev[joint] = eul
            for i in range(3):
                channels.setdefault((joint, "rotation_euler", i), []).append((frame, eul[i]))
            if joint == "Torso":
                for i in range(3):
                    channels.setdefault((joint, "location", i), []).append((frame, loc[i]))

    for (joint, prop, index), pts in channels.items():
        fc = bag.fcurves.new(f'pose.bones["{joint}"].{prop}', index=index, group_name=joint)
        fc.keyframe_points.add(len(pts))
        for kp, (f, v) in zip(fc.keyframe_points, pts):
            kp.co = (f, v)
            kp.interpolation = "BEZIER"
            kp.handle_left_type = spec["handles"]
            kp.handle_right_type = spec["handles"]
        if spec["loop"]:
            fc.modifiers.new("CYCLES")
        fc.update()

    act.use_frame_range = True
    act.frame_start = 0
    act.frame_end = spec["frames"]
    act.use_cyclic = spec["loop"]
    act["r6_export"] = True
    act["r6_loop"] = spec["loop"]
    act["r6_priority"] = spec["priority"]
    act["r6_bake_step"] = spec["bake"]
    act["r6_joints"] = ",".join(joints)
    if "stride" in spec:
        act["r6_stride"] = spec["stride"]
    return act, slot


def assign(rig, act):
    ad = rig.animation_data or rig.animation_data_create()
    ad.action = act
    if act.slots:
        ad.action_slot = act.slots[0]


def build_all():
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.render.fps_base = 1.0
    rig = build_rig()
    actions = [build_action(rig, spec)[0] for spec in ANIMS]
    assign(rig, actions[0])
    scene.frame_start = 0
    scene.frame_end = ANIMS[0]["frames"]
    return rig, actions


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    rig, actions = build_all()
    print(f"[R6] built rig '{rig.name}' with {len(actions)} actions:",
          ", ".join(a.name for a in actions))
    if "--save" in argv:
        path = argv[argv.index("--save") + 1]
        bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
        print("[R6] saved", path)


if __name__ == "__main__":
    main()
