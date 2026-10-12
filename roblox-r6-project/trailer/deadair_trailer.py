"""
DEADAIR - teaser trailer scene (Blender)
========================================

Builds the whole trailer as one Blender scene: a foggy, blocky town at night
with street lamps, a radio tower with a blinking beacon, and the R6 character
(using the R6 Animation Pack) walking, running, jumping and climbing with a
flashlight. Every shot has its own camera, switched by timeline markers.

    blender -b --python deadair_trailer.py -- --save DEADAIR_Trailer.blend
    blender -b DEADAIR_Trailer.blend --python deadair_trailer.py -- --render frames/ [--shot B] [--frame 600]

Timeline runs at 60 fps; the trailer is rendered every 2nd frame (30 fps).
Titles, glitches, grain and sound are added afterwards by assemble.py.
"""

import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # pasted into Blender's text editor
    HERE = os.path.dirname(bpy.data.filepath) or os.getcwd()
sys.path.insert(0, os.path.join(HERE, "..", "blender"))
import r6_build  # noqa: E402

FPS = 60
WALK_SPEED, RUN_SPEED = 6.25, 16.0

# Shot list: name, start, end (trailer seconds). Gaps are title/glitch cards.
SHOTS = [
    ("A", 3.0, 7.5),    # establishing: foggy street, tiny figure, tower far away
    ("B", 7.5, 11.5),   # side track: walking under the lamps
    ("C", 11.5, 14.5),  # front close: stops, glances around
    ("D", 15.0, 19.0),  # run at camera, lamps die behind
    ("E", 19.0, 22.0),  # slow-motion jump off the loading dock
    ("F", 22.0, 25.5),  # climbing the radio tower
    ("G", 25.5, 27.5),  # on the tower balcony, beacon pulsing
]
SHOT_RANGE = {name: (a, b) for name, a, b in SHOTS}
END_TIME = 34.5


def frame(t):
    return int(round(t * FPS))


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------

def principled(name, color, rough=0.8, metal=0.0, emit=None, strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1)
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def window_material(name, wall, lit_color, seed):
    """Building facade with a grid of windows, a few of them lit."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.9
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nsep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Normal"], nsep.inputs[0])

    def math_node(op, a=None, b=None, va=None, vb=None):
        n = nt.nodes.new("ShaderNodeMath")
        n.operation = op
        if a is not None:
            nt.links.new(a, n.inputs[0])
        if va is not None:
            n.inputs[0].default_value = va
        if b is not None:
            nt.links.new(b, n.inputs[1])
        if vb is not None:
            n.inputs[1].default_value = vb
        return n.outputs[0]

    # 4-stud window cells along the facade (y) and up the wall (z)
    cy = math_node("DIVIDE", sep.outputs["Y"], vb=4.0)
    cz = math_node("DIVIDE", sep.outputs["Z"], vb=4.0)
    fy = math_node("FRACT", cy)
    fz = math_node("FRACT", cz)
    in_y = math_node("MULTIPLY", math_node("GREATER_THAN", fy, vb=0.22), math_node("LESS_THAN", fy, vb=0.78))
    in_z = math_node("MULTIPLY", math_node("GREATER_THAN", fz, vb=0.3), math_node("LESS_THAN", fz, vb=0.8))
    facing = math_node("GREATER_THAN", math_node("ABSOLUTE", nsep.outputs["X"]), vb=0.5)
    window = math_node("MULTIPLY", math_node("MULTIPLY", in_y, in_z), facing)
    cell = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(math_node("FLOOR", cy), cell.inputs["X"])
    nt.links.new(math_node("FLOOR", cz), cell.inputs["Y"])
    cell.inputs["Z"].default_value = seed
    noise = nt.nodes.new("ShaderNodeTexWhiteNoise")
    noise.noise_dimensions = "3D"
    nt.links.new(cell.outputs[0], noise.inputs["Vector"])
    lit = math_node("MULTIPLY", math_node("GREATER_THAN", noise.outputs["Value"], vb=0.86), window)

    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(window, mix.inputs[0])
    mix.inputs[6].default_value = (*wall, 1)
    mix.inputs[7].default_value = (0.012, 0.014, 0.018, 1)  # dark glass
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    bsdf.inputs["Emission Color"].default_value = (*lit_color, 1)
    nt.links.new(math_node("MULTIPLY", lit, vb=2.2), bsdf.inputs["Emission Strength"])
    return mat


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------

def box(name, size, loc, mat, col, bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    col.objects.link(ob)
    if bevel:
        mod = ob.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    return ob


def cylinder(name, radius, depth, loc, mat, col, segments=16):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=radius, radius2=radius, depth=depth)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    col.objects.link(ob)
    return ob


def point_light(name, loc, color, energy, radius, col):
    light = bpy.data.lights.new(name, "POINT")
    light.color = color
    light.energy = energy
    light.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, light)
    ob.location = loc
    col.objects.link(ob)
    return ob


# --------------------------------------------------------------------------
# Town
# --------------------------------------------------------------------------

class Town:
    def __init__(self):
        self.col = bpy.data.collections.new("DEADAIR Town")
        bpy.context.scene.collection.children.link(self.col)
        self.lamps = []  # (y, light object, bulb material)

    def build(self):
        col = self.col
        asphalt = principled("Asphalt", (0.035, 0.036, 0.04), rough=0.6)
        concrete = principled("Concrete", (0.11, 0.11, 0.115))
        dirt = principled("Dirt", (0.045, 0.05, 0.04))
        metal = principled("Metal", (0.06, 0.06, 0.065), rough=0.45, metal=0.8)
        rust = principled("Rust", (0.12, 0.05, 0.03), rough=0.7, metal=0.4)
        stripe = principled("Road Line", (0.4, 0.36, 0.2), rough=0.5)

        y0, y1 = 70.0, -300.0
        length, mid = y0 - y1, (y0 + y1) / 2
        box("Road", (16, length, 0.2), (0, mid, -0.1), asphalt, col)
        for side in (-1, 1):
            box(f"Sidewalk{side}", (5, length, 0.6), (side * 10.5, mid, 0.1), concrete, col)
            box(f"Lot{side}", (60, length, 0.2), (side * 43, mid, -0.12), dirt, col)
        for i in range(int(length / 10)):
            box(f"Dash{i}", (0.35, 4, 0.04), (0, y0 - 5 - i * 10, 0.02), stripe, col)

        # Buildings: blocky shops and flats on both sides, some windows lit.
        walls = [(0.13, 0.06, 0.05), (0.09, 0.09, 0.1), (0.12, 0.1, 0.08), (0.06, 0.07, 0.08)]
        y = y0
        k = 0
        while y > -140:
            for side in (-1, 1):
                w = 10 + (k * 7 % 5) * 2
                d = 14 + (k * 3 % 4) * 3
                h = 14 + (k * 11 % 7) * 5
                mat = window_material(f"Facade{k}{side}", walls[(k + side) % 4],
                                      (1.0, 0.62, 0.3) if k % 3 else (0.55, 0.75, 1.0), seed=k * 1.7 + side)
                box(f"Building{k}{side}", (d, w, h), (side * (14 + d / 2), y - w / 2, h / 2), mat, col)
                box(f"Roof{k}{side}", (d + 0.6, w + 0.6, 0.8), (side * (14 + d / 2), y - w / 2, h + 0.4), concrete, col)
                k += 1
            y -= 10 + (k * 5 % 4) * 3 + 2

        # Street lamps, alternating sides every 22 studs.
        pole = principled("Lamp Pole", (0.03, 0.03, 0.035), rough=0.4, metal=0.7)
        for i in range(16):
            ly = 40 - i * 22
            side = -1 if i % 2 else 1
            x = side * 9.3
            box(f"LampPole{i}", (0.5, 0.5, 13), (x, ly, 6.5), pole, col)
            box(f"LampArm{i}", (3.2, 0.4, 0.4), (x - side * 1.4, ly, 12.8), pole, col)
            bulb_mat = principled(f"Bulb{i}", (1, 1, 1), emit=(1.0, 0.72, 0.42), strength=18.0)
            box(f"LampHead{i}", (1.6, 1.0, 0.45), (x - side * 2.7, ly, 12.5), bulb_mat, col)
            light = point_light(f"Lamp{i}", (x - side * 2.7, ly, 11.9), (1.0, 0.7, 0.42), 3200, 0.6, col)
            light.data.use_shadow = 2 <= i <= 7  # only where the character passes under them
            self.lamps.append((ly, light, bulb_mat))

        # Loading dock the runner jumps off (shot E).
        box("Dock", (16, 26, 7), (0, -168, 3.5), concrete, col, bevel=0.1)
        box("DockRamp", (16, 31, 0.6), (0, -140, 3.5), concrete, col).rotation_euler = (math.radians(-13.1), 0, 0)
        for i, yy in enumerate((-160, -167, -174)):
            box(f"Crate{i}", (3, 3, 3), (6.5, yy, 8.5), principled(f"Crate{i}", (0.16, 0.11, 0.06)), col, bevel=0.08)

        # Radio tower: four legs, cross braces, a ladder, a balcony and a beacon.
        tx, ty = 0.0, -232.0
        for sx in (-1, 1):
            for sy in (-1, 1):
                box(f"TowerLeg{sx}{sy}", (0.8, 0.8, 96), (tx + sx * 3.6, ty + sy * 3.6, 48), rust, col)
        for j in range(24):
            z = 2 + j * 4
            for sy in (-1, 1):
                box(f"BraceX{j}{sy}", (7.6, 0.4, 0.4), (tx, ty + sy * 3.6, z), rust, col)
            for sx in (-1, 1):
                box(f"BraceY{j}{sx}", (0.4, 7.6, 0.4), (tx + sx * 3.6, ty, z), rust, col)
        ladder_y = ty + 4.4
        for sx in (-1, 1):
            box(f"LadderRail{sx}", (0.25, 0.25, 42), (tx + sx * 1.2, ladder_y, 21), metal, col)
        for j in range(52):
            box(f"Rung{j}", (2.4, 0.2, 0.2), (tx, ladder_y, 0.8 + j * 0.8), metal, col)
        box("Balcony", (12, 12, 0.6), (tx, ty, 42.3), metal, col)
        for i, (sx, sy, w, d) in enumerate(((0, 1, 12, 0.2), (0, -1, 12, 0.2), (1, 0, 0.2, 12), (-1, 0, 0.2, 12))):
            box(f"Rail{i}", (w, d, 0.2), (tx + sx * 6, ty + sy * 6, 45.2), metal, col)
        box("Antenna", (0.5, 0.5, 30), (tx, ty, 111), rust, col)
        self.beacon_mat = principled("Beacon", (1, 0, 0), emit=(1.0, 0.05, 0.03), strength=60)
        cylinder("BeaconLamp", 0.9, 1.2, (tx, ty, 126.6), self.beacon_mat, col)
        self.beacon = point_light("BeaconLight", (tx, ty, 126.6), (1.0, 0.06, 0.03), 60000, 1.0, col)
        self.beacon_mat2 = principled("Beacon Mid", (1, 0, 0), emit=(1.0, 0.05, 0.03), strength=60)
        cylinder("BeaconMid", 0.6, 0.8, (tx + 4.2, ty + 4.2, 50), self.beacon_mat2, col)
        self.beacon2 = point_light("BeaconLight2", (tx + 4.2, ty + 4.2, 50), (1.0, 0.06, 0.03), 9000, 0.6, col)
        for i, sx in enumerate((-1, 1)):
            flood = bpy.data.lights.new(f"Floodlight{i}", "SPOT")
            flood.energy = 60000
            flood.color = (1.0, 0.55, 0.25)
            flood.spot_size = math.radians(38)
            flood.spot_blend = 0.5
            ob = bpy.data.objects.new(f"Floodlight{i}", flood)
            ob.location = (tx + sx * 9, ty + 16, 0.8)
            aim = Vector((tx, ladder_y, 24)) - ob.location
            ob.rotation_euler = aim.to_track_quat("-Z", "Y").to_euler()
            col.objects.link(ob)
            box(f"FloodBox{i}", (1.2, 1.2, 1.0), (tx + sx * 9, ty + 16, 0.5), metal, col)
        self.tower = (tx, ty, ladder_y)

        # Fences and junk in the empty lots for depth.
        for i in range(30):
            side = -1 if i % 2 else 1
            box(f"Fence{i}", (0.3, 9, 4), (side * 13.2, -210 - (i // 2) * 9, 2), metal, col)

    def animate(self):
        """Lamp flicker, lamps dying behind the runner, tower beacon pulse."""
        runner = Performance.runner_y
        for i, (ly, light, bulb) in enumerate(self.lamps):
            emit = bulb.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
            base_energy, base_emit = light.data.energy, emit.default_value
            levels = []
            for f in range(0, frame(END_TIME) + 1, 2):
                t = f / FPS
                level = 1.0
                if i == 3 and 7.5 <= t < 11.5:  # sick lamp in shot B
                    s = math.sin(t * 23) + math.sin(t * 37.3 + 1) + math.sin(t * 61.7 + 2)
                    level = 0.15 if s > 1.6 else (0.6 if s > 1.2 else 1.0)
                if 15.0 <= t < 19.0:  # shot D: lamps die after the runner passes
                    passed = runner(t) < ly - 6
                    if passed:
                        since = t - Performance.pass_time(ly - 6)
                        level = 0.0 if since > 0.25 else (0.2 if int(since * 40) % 2 else 1.0)
                levels.append((f, level))
            if all(level == 1.0 for _, level in levels):
                continue
            for f, level in levels:
                light.data.energy = base_energy * level
                emit.default_value = base_emit * level
                light.data.keyframe_insert("energy", frame=f)
                emit.keyframe_insert("default_value", frame=f)
            for fc in _fcurves(light.data) + _fcurves(bulb.node_tree):
                for kp in fc.keyframe_points:
                    kp.interpolation = "CONSTANT"

        for light, mat, phase in ((self.beacon, self.beacon_mat, 0.0), (self.beacon2, self.beacon_mat2, 0.5)):
            emit = mat.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
            e0, l0 = emit.default_value, light.data.energy
            for f in range(0, frame(END_TIME) + 1, 2):
                t = f / FPS + phase
                pulse = max(0.0, math.sin(math.pi * (t % 1.6) / 0.7)) if (t % 1.6) < 0.7 else 0.0
                level = 0.04 + 0.96 * pulse ** 1.5
                light.data.energy = l0 * level
                emit.default_value = e0 * level
                light.data.keyframe_insert("energy", frame=f)
                emit.keyframe_insert("default_value", frame=f)


def _fcurves(idblock):
    ad = idblock.animation_data
    if not ad or not ad.action:
        return []
    from bpy_extras import anim_utils
    bag = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return list(bag.fcurves) if bag else []


# --------------------------------------------------------------------------
# Character performance
# --------------------------------------------------------------------------

class Performance:
    """Where the runner is (root motion) and what it plays, per shot."""

    @staticmethod
    def runner_y(t):
        a, _ = SHOT_RANGE["D"]
        return -50.0 - RUN_SPEED * (t - a)

    @staticmethod
    def pass_time(y):
        a, _ = SHOT_RANGE["D"]
        return a + (-50.0 - y) / RUN_SPEED

    # Each shot: list of NLA strips (action, start s, end s, blend in, blend out,
    # action start offset s, playback scale) in trailer seconds.
    STRIPS = {
        "A": [("Walk", 3.0, 7.5, 0, 0, 0.0, 1.0), ("ToolHold", 3.0, 7.5, 0, 0, 0.0, 1.0)],
        "B": [("Walk", 7.5, 11.5, 0, 0, 0.2, 1.0), ("ToolHold", 7.5, 11.5, 0, 0, 1.0, 1.0)],
        "C": [("Walk", 11.5, 12.5, 0, 0, 0.4, 1.0), ("IdleLook", 12.0, 14.5, 0.45, 0, 0.8, 0.7),
              ("ToolHold", 11.5, 14.5, 0, 0, 2.0, 1.0)],
        "D": [("Run", 15.0, 19.0, 0, 0, 0.0, 1.0), ("ToolHold", 15.0, 19.0, 0, 0, 0.5, 1.0)],
        "E": [("Run", 19.0, 20.2, 0, 0, 0.0, 2.0), ("Jump", 20.05, 21.2, 0.15, 0, 0.0, 2.0),
              ("Fall", 20.6, 21.36, 0.25, 0, 0.0, 2.0), ("Land", 21.3, 22.0, 0.08, 0, 0.0, 2.0)],
        "F": [("Climb", 22.0, 25.5, 0, 0, 0.0, 1.0)],
        "G": [("IdleLook", 25.5, 27.5, 0, 0, 3.2, 1.0), ("ToolHold", 25.5, 27.5, 0, 0, 0.0, 1.0)],
    }

    @staticmethod
    def root(t):
        """Rig object location for trailer time t (studs)."""
        if t < 7.5:  # A: walking away down the road
            return (1.0, 18.0 - WALK_SPEED * (t - 3.0), 0.0)
        if t < 11.5:  # B
            return (-2.5, -24.0 - WALK_SPEED * (t - 7.5), 0.0)
        if t < 14.5:  # C: walks in, eases to a stop as the idle blends in
            dt = t - 11.5
            stop, ease = 0.45, 0.55
            dist = WALK_SPEED * min(dt, stop)
            if dt > stop:
                e = min((dt - stop) / ease, 1.0)
                dist += WALK_SPEED * ease * (e - e * e / 2)
            return (0.0, -62.0 - dist, 0.0)
        if t < 19.0:  # D
            return (0.0, Performance.runner_y(t), 0.0)
        if t < 22.0:  # E: slow motion run, jump off the dock edge (y = -185, top z = 7)
            dt = (t - 19.0) / 2.0  # half speed
            jump_at = (20.05 - 19.0) / 2.0
            y = -172.0 - RUN_SPEED * min(dt, jump_at) - 12.0 * max(0.0, dt - jump_at)
            if dt < jump_at:
                return (0.0, y, 7.0)
            ta = dt - jump_at
            z = 7.0 + 50.0 * ta - 98.1 * ta * ta
            return (0.0, y, max(z, 0.0))
        if t < 25.5:  # F: climbing the ladder
            tx, ty, ladder_y = 0.0, -232.0, -232.0 + 4.4
            return (tx, ladder_y + 1.2, 2.0 + 11.2 * (t - 22.0) * 0.9)
        return (-1.0, -229.5, 42.6)  # G: on the balcony

    @staticmethod
    def heading(t):
        """Rig yaw (radians). The rig faces -Y; G looks out over the town (+Y)."""
        return math.pi if t >= 25.5 else 0.0


def beam_cone(col, length=16.0, radius=4.2):
    """Soft additive light cone - a fake volumetric flashlight beam."""
    me = bpy.data.meshes.new("Flashlight Cone")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=32, radius1=radius, radius2=0.18, depth=length)
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    mat = bpy.data.materials.new("Flashlight Cone")
    mat.use_nodes = True
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    mat.use_backface_culling = False
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    add = nt.nodes.new("ShaderNodeAddShader")
    transparent = nt.nodes.new("ShaderNodeBsdfTransparent")
    emission = nt.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (0.8, 0.88, 1.0, 1)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    along = nt.nodes.new("ShaderNodeMapRange")  # 1 at the lens, 0 at the far end
    along.inputs["From Min"].default_value = -length / 2
    along.inputs["From Max"].default_value = length / 2
    nt.links.new(sep.outputs["Z"], along.inputs["Value"])
    fade = nt.nodes.new("ShaderNodeMath")
    fade.operation = "POWER"
    fade.inputs[1].default_value = 1.8
    nt.links.new(along.outputs[0], fade.inputs[0])
    weight = nt.nodes.new("ShaderNodeLayerWeight")
    weight.inputs["Blend"].default_value = 0.5
    core = nt.nodes.new("ShaderNodeMath")  # bright through the middle, soft edges
    core.operation = "POWER"
    core.inputs[1].default_value = 2.5
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    nt.links.new(weight.outputs["Facing"], inv.inputs[1])
    nt.links.new(inv.outputs[0], core.inputs[0])
    strength = nt.nodes.new("ShaderNodeMath")
    strength.operation = "MULTIPLY"
    nt.links.new(fade.outputs[0], strength.inputs[0])
    nt.links.new(core.outputs[0], strength.inputs[1])
    scale = nt.nodes.new("ShaderNodeMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = 0.9
    nt.links.new(strength.outputs[0], scale.inputs[0])
    nt.links.new(scale.outputs[0], emission.inputs["Strength"])
    nt.links.new(transparent.outputs[0], add.inputs[0])
    nt.links.new(emission.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    me.materials.append(mat)
    ob = bpy.data.objects.new("Flashlight Cone", me)
    ob.location = (-1.5, -0.1, 1.2 - length / 2)  # apex sits on the lens
    ob.visible_shadow = False
    col.objects.link(ob)
    return ob


def setup_character(scene):
    rig, actions = r6_build.build_all()
    # Restyle: dark jacket, worn jeans, a little scarf of colour on the head.
    look = {"R6 Torso": (0.09, 0.035, 0.03), "R6 Right Leg": (0.03, 0.035, 0.05),
            "R6 Left Leg": (0.03, 0.035, 0.05)}
    for ob in bpy.data.collections[r6_build.COLLECTION].objects:
        if ob.name in look:
            mat = principled(ob.name + " Outfit", look[ob.name], rough=0.7)
            ob.data.materials.clear()
            ob.data.materials.append(mat)

    # Flashlight in the right hand, beam along the arm.
    col = bpy.data.collections[r6_build.COLLECTION]
    body_mat = principled("Flashlight", (0.02, 0.02, 0.022), rough=0.3, metal=0.9)
    lens_mat = principled("Flashlight Lens", (1, 1, 1), emit=(0.85, 0.92, 1.0), strength=40)
    torch = cylinder("Flashlight", 0.22, 1.1, (-1.5, -0.1, 1.85), body_mat, col)
    lens = cylinder("Flashlight Lens", 0.2, 0.06, (-1.5, -0.1, 1.28), lens_mat, col)
    spot_data = bpy.data.lights.new("Flashlight Beam", "SPOT")
    spot_data.energy = 9000
    spot_data.color = (0.85, 0.92, 1.0)
    spot_data.spot_size = math.radians(30)
    spot_data.spot_blend = 0.6
    spot_data.shadow_soft_size = 0.05
    spot_data.volume_factor = 0.0  # the visible beam is the soft cone below
    spot = bpy.data.objects.new("Flashlight Beam", spot_data)
    spot.location = (-1.5, -0.1, 1.2)
    col.objects.link(spot)
    beam = beam_cone(col)
    fill = bpy.data.objects.new("Fill Light", bpy.data.lights.new("Fill Light", "POINT"))
    fill.data.energy = 420
    fill.data.color = (0.75, 0.82, 1.0)
    fill.data.shadow_soft_size = 3.0
    fill.data.use_shadow = False
    fill.data.volume_factor = 0.0
    fill.location = (-2.0, -6.0, 6.0)
    fill.parent = rig
    col.objects.link(fill)

    rim = bpy.data.objects.new("Rim Light", bpy.data.lights.new("Rim Light", "POINT"))
    rim.data.energy = 650
    rim.data.color = (0.55, 0.7, 1.0)
    rim.data.shadow_soft_size = 1.5
    rim.data.use_shadow = False
    rim.location = (0.0, 4.0, 7.0)
    rim.parent = rig
    col.objects.link(rim)

    # Bone parenting offsets children to the bone tail, so set the world
    # placement again after parenting.
    for ob in (torch, lens, spot, beam):
        loc = ob.location.copy()
        ob.parent = rig
        ob.parent_type = "BONE"
        ob.parent_bone = "Right Arm"
        bpy.context.view_layer.update()
        ob.matrix_world = Matrix.Translation(loc)
    return rig


def animate_character(rig):
    ad = rig.animation_data or rig.animation_data_create()
    ad.action = None
    for pb in rig.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
    for shot, strips in Performance.STRIPS.items():
        for action, start, end, blend_in, blend_out, offset, scale in strips:
            act = bpy.data.actions["R6_" + action]
            track = ad.nla_tracks.new()
            track.name = f"{shot} {action}"
            strip = track.strips.new(f"{shot} {action}", frame(start), act)
            if hasattr(strip, "action_slot") and act.slots:
                strip.action_slot = act.slots[0]
            # Loops keep cycling past their last key (Cycles modifier) and
            # one-shots hold their last pose, so the strip can simply cover
            # [offset, offset + shot span] of the action - phase stays intact.
            off = frame(offset)
            span = (frame(end) - frame(start)) / scale
            strip.scale = scale
            strip.action_frame_end = off + span
            strip.action_frame_start = off
            strip.blend_in = frame(blend_in)
            strip.blend_out = frame(blend_out)
            strip.extrapolation = "NOTHING"
            strip.use_auto_blend = False

    for f in range(0, frame(END_TIME) + 1):
        t = f / FPS
        rig.location = Performance.root(t)
        rig.rotation_euler = (0, 0, Performance.heading(t))
        rig.keyframe_insert("location", frame=f)
        rig.keyframe_insert("rotation_euler", frame=f)
    for fc in _fcurves(rig):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


# --------------------------------------------------------------------------
# Cameras
# --------------------------------------------------------------------------

def handheld(t, amount):
    """Organic camera drift: a few incommensurate sines."""
    return Vector((
        amount * (0.6 * math.sin(t * 1.3) + 0.3 * math.sin(t * 2.9 + 1.0) + 0.1 * math.sin(t * 7.1)),
        amount * (0.5 * math.sin(t * 1.1 + 2.0) + 0.3 * math.sin(t * 3.3)),
        amount * (0.6 * math.sin(t * 1.7 + 0.5) + 0.25 * math.sin(t * 4.3 + 2.0)),
    ))


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def camera_path(shot, t):
    """(camera location, look-at point, lens mm) for trailer time t."""
    a, b = SHOT_RANGE[shot]
    u = (t - a) / (b - a)
    root = Vector(Performance.root(t))
    if shot == "A":
        eye = Vector((6.0, 52.0 - 14.0 * smooth(u), 34.0 - 16.0 * smooth(u)))
        return eye, Vector((0.0, -110.0, 14.0 - 6 * u)), 30
    if shot == "B":
        eye = root + Vector((-10.5, -2.0 + 1.2 * u, 2.4)) + handheld(t, 0.08)
        return eye, root + Vector((0, -2.5, 3.0)), 32
    if shot == "C":
        eye = Vector((-1.6, -77.5 + 1.2 * u, 4.4)) + handheld(t, 0.05)
        target = root + Vector((0.0, 0.0, 3.9))
        return eye, target, 40
    if shot == "D":
        eye = Vector((1.5, -64.0 - 14.5 * (t - a), 3.0)) + handheld(t, 0.18)
        return eye, root + Vector((0, 0, 3.4)), 28
    if shot == "E":
        eye = Vector((-26.0, -181.0 - 3.0 * u, 8.0)) + handheld(t, 0.06)
        return eye, Vector((0.0, -181.0 - 5.0 * smooth(u), 10.5 - 4.5 * smooth(u))), 26
    if shot == "F":
        eye = Vector((-4.0, -215.0, 1.8)) + handheld(t, 0.05)
        return eye, root + Vector((0.0, 0.0, 6.0 + 6.0 * u)), 24
    if shot == "G":
        eye = Vector((14.0, -207.0 - 2 * u, 37.0))
        return eye, Vector((-1.0, -229.5, 46.0)), 38
    raise ValueError(shot)


def setup_cameras(scene):
    cams = {}
    for shot, a, b in SHOTS:
        cam = bpy.data.objects.new(f"Cam {shot}", bpy.data.cameras.new(f"Cam {shot}"))
        scene.collection.objects.link(cam)
        cam.data.sensor_width = 36
        cam.data.clip_end = 1500
        for f in range(frame(a), frame(b) + 1):
            eye, target, lens = camera_path(shot, f / FPS)
            cam.location = eye
            cam.rotation_euler = (target - eye).to_track_quat("-Z", "Y").to_euler()
            cam.data.lens = lens
            cam.keyframe_insert("location", frame=f)
            cam.keyframe_insert("rotation_euler", frame=f)
            cam.data.keyframe_insert("lens", frame=f)
        marker = scene.timeline_markers.new(f"Shot {shot}", frame=frame(a))
        marker.camera = cam
        cams[shot] = cam
    scene.camera = cams["A"]
    return cams


# --------------------------------------------------------------------------
# World, render settings
# --------------------------------------------------------------------------

def setup_world(scene):
    world = bpy.data.worlds.new("Night Fog")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes["Background"]
    bg.inputs[0].default_value = (0.012, 0.016, 0.026, 1)
    bg.inputs[1].default_value = 1.0
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = 0.018
    vol.inputs["Anisotropy"].default_value = 0.35
    vol.inputs["Color"].default_value = (0.55, 0.62, 0.75, 1)
    nt.links.new(vol.outputs[0], nt.nodes["World Output"].inputs["Volume"])

    moon = bpy.data.objects.new("Moon", bpy.data.lights.new("Moon", "SUN"))
    scene.collection.objects.link(moon)
    moon.data.energy = 1.1
    moon.data.color = (0.55, 0.65, 1.0)
    moon.data.angle = math.radians(2)
    moon.rotation_euler = (math.radians(55), 0, math.radians(150))


def render_settings(scene):
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.fps = FPS
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.frame_step = 2
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 1.0  # 180-degree shutter at 30 fps
    ev = scene.eevee
    for attr, value in (("taa_render_samples", 8), ("volumetric_tile_size", "8"),
                        ("volumetric_samples", 32), ("volumetric_end", 220.0),
                        ("use_volumetric_shadows", True), ("volumetric_shadow_samples", 8),
                        ("use_shadows", True), ("shadow_ray_count", 1), ("shadow_step_count", 3),
                        ("use_bloom", True), ("bloom_intensity", 0.06)):
        if hasattr(ev, attr):
            try:
                setattr(ev, attr, value)
            except (TypeError, ValueError):
                pass
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Punchy"
    except TypeError:
        pass
    scene.view_settings.exposure = 0.4
    scene.render.image_settings.file_format = "PNG"


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "DEADAIR Trailer"
    rig = setup_character(scene)
    town = Town()
    town.build()
    town.animate()
    animate_character(rig)
    setup_cameras(scene)
    setup_world(scene)
    render_settings(scene)
    scene.frame_start, scene.frame_end = frame(SHOTS[0][1]), frame(SHOTS[-1][2])
    return scene


def render(out, shots=None, single=None):
    scene = bpy.context.scene
    os.makedirs(out, exist_ok=True)
    if single is not None:
        scene.frame_set(single)
        scene.render.filepath = os.path.join(out, f"{single:04d}.png")
        bpy.ops.render.render(write_still=True)
        return
    scene.render.use_overwrite = False  # resume-friendly
    for shot, a, b in SHOTS:
        if shots and shot not in shots:
            continue
        scene.frame_start, scene.frame_end = frame(a), frame(b) - 1
        scene.frame_step = 2
        scene.render.filepath = os.path.join(out, "")
        bpy.ops.render.render(animation=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    def arg(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    if "--render" not in argv or bpy.context.scene.name != "DEADAIR Trailer":
        build()
    if "--save" in argv:
        bpy.ops.wm.save_as_mainfile(filepath=arg("--save"), compress=True)
        print("[DEADAIR] saved", arg("--save"))
    if "--render" in argv:
        single = arg("--frame")
        shots = arg("--shot")
        render(arg("--render"), shots=shots.split(",") if shots else None,
               single=int(single) if single else None)


if __name__ == "__main__":
    main()
