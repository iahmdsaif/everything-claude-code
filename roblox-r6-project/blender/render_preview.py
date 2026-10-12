"""
R6 Animation Pack - 60 fps preview reel
=======================================

Renders one continuous take of the pack: idle -> walk -> run -> stop ->
jump/fall/land -> glance around, blended with NLA strips the same way the
Roblox Animate script blends them, with matching root motion so you can
judge foot planting.

Run headless on the built file (the .blend is NOT modified on disk):
    blender -b R6_AnimPack.blend -P render_preview.py -- --out frames/ [--res 960x540] [--samples 10]
Then encode, e.g.:
    ffmpeg -framerate 60 -i frames/%04d.png -c:v libx264 -pix_fmt yuv420p -crf 16 preview.mp4
"""

import math
import os
import sys

import bpy
from mathutils import Vector

FPS = 60
RIG = "R6 Rig"
DURATION = 20.0

# action, start, end, blend in, blend out (seconds). Later rows sit on higher
# NLA tracks, so each one blends over the ones before it. Walk and run start
# on whole cycles of each other so their footfalls line up during the blend.
STRIPS = [
    ("R6_Idle", 0.0, DURATION, 0.0, 0.0),
    ("R6_Walk", 2.5, 6.1, 0.35, 0.0),
    ("R6_Run", 5.7, 10.3, 0.4, 0.6),
    ("R6_Jump", 12.0, 12.7, 0.12, 0.0),
    ("R6_Fall", 12.25, 12.66, 0.15, 0.0),
    ("R6_Land", 12.612, 13.112, 0.06, 0.25),
    ("R6_IdleLook", 13.6, 19.7, 0.45, 0.6),
]

WALK_SPEED = 6.25   # Stride.Walk / walk loop length (studs/s)
RUN_SPEED = 16.0    # Stride.Run / run loop length
JUMP_START, JUMP_POWER, GRAVITY = 12.0, 60.0, 196.2

LABELS = [  # (text, start, end) - used by the encoder for captions
    ("IDLE", 0.2, 2.4),
    ("WALK", 2.6, 5.8),
    ("RUN", 5.9, 10.2),
    ("JUMP  /  FALL  /  LAND", 11.8, 13.6),
    ("IDLE  -  LOOK AROUND", 13.8, 19.8),
]


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def ground_speed(t):
    walk = smooth((t - 2.5) / 0.35) * WALK_SPEED
    run = smooth((t - 5.7) / 0.4) * (RUN_SPEED - WALK_SPEED)
    stop = 1.0 - smooth((t - 9.7) / 0.6)
    return (walk + run) * stop


def jump_height(t):
    dt = t - JUMP_START
    air = 2 * JUMP_POWER / GRAVITY
    if dt <= 0 or dt >= air:
        return 0.0
    return JUMP_POWER * dt - 0.5 * GRAVITY * dt * dt


def setup_motion(scene, rig):
    for pb in rig.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
    ad = rig.animation_data or rig.animation_data_create()
    ad.action = None
    for track in list(ad.nla_tracks):
        ad.nla_tracks.remove(track)
    for name, start, end, blend_in, blend_out in STRIPS:
        act = bpy.data.actions[name]
        track = ad.nla_tracks.new()
        track.name = name
        f0, f1 = round(start * FPS), round(end * FPS)
        strip = track.strips.new(name, f0, act)
        if hasattr(strip, "action_slot") and act.slots:
            strip.action_slot = act.slots[0]
        length = act.frame_range[1] - act.frame_range[0]
        strip.repeat = max((f1 - f0) / length, 0.01)
        strip.blend_in = round(blend_in * FPS)
        strip.blend_out = round(blend_out * FPS)
        strip.extrapolation = "NOTHING"

    # Root motion: integrate ground speed, add the jump arc.
    rig.location = (0, 0, 0)
    dist = 0.0
    frames = round(DURATION * FPS)
    for f in range(frames + 1):
        t = f / FPS
        rig.location = (0, -dist, jump_height(t))
        rig.keyframe_insert("location", frame=f)
        dist += ground_speed(t) / FPS
    if rig.animation_data.action:
        rig.animation_data.action.name = "Preview_RootMotion"
    return dist


def setup_world(scene, rig, travel):
    world = bpy.data.worlds.new("Preview Sky")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.55, 0.68, 0.86, 1)
    bg.inputs[1].default_value = 0.8

    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    scene.collection.objects.link(sun)
    sun.data.energy = 4.0
    sun.data.angle = math.radians(6)
    sun.rotation_euler = (math.radians(48), math.radians(8), math.radians(-38))

    me = bpy.data.meshes.new("Ground")
    half = travel + 120
    me.from_pydata([(-80, 60, 0), (80, 60, 0), (80, -half, 0), (-80, -half, 0)], [], [(0, 3, 2, 1)])
    ground = bpy.data.objects.new("Ground", me)
    scene.collection.objects.link(ground)
    mat = bpy.data.materials.new("Baseplate")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.8
    tc = nt.nodes.new("ShaderNodeTexCoord")
    checker = nt.nodes.new("ShaderNodeTexChecker")
    checker.inputs["Scale"].default_value = 1.0 / 4.0  # 4-stud tiles
    checker.inputs["Color1"].default_value = (0.20, 0.21, 0.23, 1)
    checker.inputs["Color2"].default_value = (0.24, 0.25, 0.27, 1)
    nt.links.new(tc.outputs["Object"], checker.inputs["Vector"])
    nt.links.new(checker.outputs["Color"], bsdf.inputs["Base Color"])
    ground.data.materials.append(mat)

    cam = bpy.data.objects.new("Preview Camera", bpy.data.cameras.new("Preview Camera"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 40
    cam.location = Vector((-10.5, -9.0, 4.3))
    aim = Vector((0.0, -1.5, 2.4)) - cam.location
    cam.rotation_euler = aim.to_track_quat("-Z", "Y").to_euler()
    follow = cam.constraints.new("COPY_LOCATION")
    follow.target = rig
    follow.use_z = False
    follow.use_offset = True
    lift = cam.constraints.new("COPY_LOCATION")  # rise with jumps, but less
    lift.target = rig
    lift.use_x = lift.use_y = False
    lift.use_offset = True
    lift.influence = 0.75


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    def arg(name, default):
        return argv[argv.index(name) + 1] if name in argv else default

    out = arg("--out", "//preview_frames/")
    res = arg("--res", "960x540").split("x")
    samples = int(arg("--samples", "10"))
    engine = arg("--engine", "CYCLES")
    first, last = int(arg("--start", "0")), int(arg("--end", str(round(DURATION * FPS))))

    scene = bpy.context.scene
    rig = bpy.data.objects[RIG]
    travel = setup_motion(scene, rig)
    setup_world(scene, rig, travel)

    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = first, last
    scene.render.resolution_x, scene.render.resolution_y = int(res[0]), int(res[1])
    scene.render.resolution_percentage = 100
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
    scene.render.engine = engine
    if engine == "CYCLES":
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.max_bounces = 4
    scene.view_settings.view_transform = "AgX"
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = os.path.join(out, "")
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
