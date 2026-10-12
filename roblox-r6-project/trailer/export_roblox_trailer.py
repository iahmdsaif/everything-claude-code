"""
Export the DEADAIR trailer scene from Blender to data the Roblox Studio
trailer project is built from (trailer/roblox/trailer_data.json):

  * every block of the town (position, rotation, size, material, colour)
  * the lights (street lamps, beacons, floodlights)
  * the shot list, baked at 30 fps: camera position/aim/field of view and the
    actor's root position/heading, so Roblox plays exactly the same shots
  * the animation strips for each shot and the lamp flicker/death timelines

    blender -b DEADAIR_Trailer.blend --python export_roblox_trailer.py
"""

import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    HERE = os.path.dirname(bpy.data.filepath) or os.getcwd()
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "blender"))
import deadair_trailer as trailer  # noqa: E402

# Blender (x, y, z) -> Roblox (-x, z, y): characters face -Y in Blender and -Z in Roblox.
M = Matrix(((-1, 0, 0), (0, 0, 1), (0, 1, 0)))
FPS = 30


def to_rbx(v):
    v = M @ Vector(v)
    return [round(v.x, 4), round(v.y, 4), round(v.z, 4)]


def rot_to_rbx(r3):
    r = M @ r3 @ M.transposed()
    return [round(r[i][j], 5) for i in range(3) for j in range(3)]


def srgb255(c):
    def enc(x):
        x = max(0.0, min(1.0, x))
        return x * 12.92 if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055
    return [round(enc(c[0]) * 255), round(enc(c[1]) * 255), round(enc(c[2]) * 255)]


def material_info(ob):
    mat = ob.active_material
    if mat is None or not mat.node_tree:
        return {"material": "", "color": [128, 128, 128]}
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    info = {"material": mat.name}
    if mat.name.startswith("Facade"):
        mix = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeMix")
        info["color"] = srgb255(mix.inputs[6].default_value)
        info["lit"] = srgb255(bsdf.inputs["Emission Color"].default_value)
    else:
        info["color"] = srgb255(bsdf.inputs["Base Color"].default_value)
        if bsdf.inputs["Emission Strength"].default_value > 0:
            info["emit"] = srgb255(bsdf.inputs["Emission Color"].default_value)
    return info


def export_map():
    parts = []
    for ob in bpy.data.collections["DEADAIR Town"].objects:
        if ob.type != "MESH":
            continue
        mw = ob.matrix_world
        dims = ob.dimensions
        parts.append({
            "name": ob.name,
            "shape": "cylinder" if ob.name.startswith("Beacon") else "block",
            "pos": to_rbx(mw.to_translation()),
            "rot": rot_to_rbx(mw.to_3x3().normalized()),
            "size": [round(dims.x, 4), round(dims.z, 4), round(dims.y, 4)],
            **material_info(ob),
        })
    lights = []
    for ob in bpy.data.collections["DEADAIR Town"].objects:
        if ob.type != "LIGHT":
            continue
        entry = {"name": ob.name, "kind": ob.data.type, "pos": to_rbx(ob.matrix_world.to_translation()),
                 "color": srgb255(ob.data.color)}
        if ob.data.type == "SPOT":
            aim = ob.matrix_world.to_3x3() @ Vector((0, 0, -1))
            entry["dir"] = to_rbx(aim)
            entry["angle"] = round(math.degrees(ob.data.spot_size), 2)
        lights.append(entry)
    return parts, lights


def export_shots(scene):
    rig = bpy.data.objects["R6 Rig"]
    cams = {shot: bpy.data.objects[f"Cam {shot}"] for shot, _a, _b in trailer.SHOTS}
    frames = []
    n_total = int(round(trailer.END_TIME * FPS))
    for n in range(n_total + 1):
        t = n / FPS
        scene.frame_set(int(round(t * trailer.FPS)))
        root = rig.matrix_world.to_translation()
        yaw = rig.matrix_world.to_euler().z
        entry = {"root": to_rbx(root), "yaw": round(yaw, 4)}
        shot = next((s for s, a, b in trailer.SHOTS if a <= t < b), None)
        if shot:
            cam = cams[shot]
            mw = cam.matrix_world
            look = mw.to_3x3() @ Vector((0, 0, -1))
            vfov = 2 * math.degrees(math.atan(10.125 / cam.data.lens))
            entry.update(shot=shot, eye=to_rbx(mw.to_translation()), look=to_rbx(look), fov=round(vfov, 3))
        frames.append(entry)
    return frames


def export_lamps(scene):
    """Brightness level (0..1) per lamp at 30 fps, only for lamps that change."""
    timelines = {}
    town = bpy.data.collections["DEADAIR Town"]
    lamps = [ob for ob in town.objects if ob.type == "LIGHT" and ob.name.startswith("Lamp")]
    base = {}
    scene.frame_set(0)
    for ob in lamps:
        ad = ob.data.animation_data
        if ad and ad.action:
            base[ob.name] = max(fc.keyframe_points[i].co[1] for fc in trailer._fcurves(ob.data)
                                for i in range(len(fc.keyframe_points)))
    n_total = int(round(trailer.END_TIME * FPS))
    for name, b in base.items():
        levels = []
        for n in range(n_total + 1):
            scene.frame_set(int(round(n / FPS * trailer.FPS)))
            levels.append(round(bpy.data.objects[name].data.energy / b, 3))
        timelines[name] = levels
    return timelines


def main():
    scene = bpy.context.scene
    parts, lights = export_map()
    data = {
        "fps": FPS,
        "length": trailer.END_TIME,
        "shots": [{"name": s, "start": a, "stop": b} for s, a, b in trailer.SHOTS],
        "strips": {shot: [dict(zip(("anim", "start", "stop", "blendIn", "blendOut", "offset", "scale"), s))
                          for s in strips] for shot, strips in trailer.Performance.STRIPS.items()},
        "parts": parts,
        "lights": lights,
        "frames": export_shots(scene),
        "lamps": export_lamps(scene),
    }
    out = os.path.join(HERE, "roblox", "trailer_data.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(f"[DEADAIR] exported {len(parts)} parts, {len(lights)} lights, {len(data['frames'])} frames -> {out}")


if __name__ == "__main__":
    main()
