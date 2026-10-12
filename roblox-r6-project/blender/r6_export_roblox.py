"""
R6 Animation Pack - Blender -> Roblox exporter
==============================================

Exports every action marked for export (all "R6_*" actions made by
r6_build.py, including any edits you make to them) as Roblox
KeyframeSequence files (.rbxmx) that you can drop straight into Studio.

  * Samples the rig exactly as Blender evaluates it (constraints, NLA tweaks
    and graph-editor edits all included) at up to 60 keys per second, using
    linear easing between the dense keys, so Roblox plays back Blender's
    smooth curves instead of re-easing sparse keys.
  * Writes the true Motor6D.Transform for every joint, using Roblox's
    standard R6 C0 frames.

Run it inside YOUR Blender after editing:
    Scripting tab -> Open -> r6_export_roblox.py -> Run Script
Files go to a "roblox_export" folder next to your .blend file.

Headless:
    blender --background file.blend --python r6_export_roblox.py -- --out DIR
"""

import os
import sys

import bpy
from mathutils import Matrix

RIG_NAME = "R6 Rig"
A = Matrix(((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))

# Motor6D C0 rotations of a standard R6 character (row-major, Roblox space).
C0 = {
    "Torso": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),      # RootJoint
    "Head": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),       # Neck
    "Right Arm": ((0, 0, 1), (0, 1, 0), (-1, 0, 0)),  # Right Shoulder
    "Left Arm": ((0, 0, -1), (0, 1, 0), (1, 0, 0)),   # Left Shoulder
    "Right Leg": ((0, 0, 1), (0, 1, 0), (-1, 0, 0)),  # Right Hip
    "Left Leg": ((0, 0, -1), (0, 1, 0), (1, 0, 0)),   # Left Hip
}
PARENT = {"Torso": "HumanoidRootPart", "Head": "Torso", "Right Arm": "Torso",
          "Left Arm": "Torso", "Right Leg": "Torso", "Left Leg": "Torso"}
CHILD_ORDER = ["Head", "Left Arm", "Left Leg", "Right Arm", "Right Leg"]
PRIORITY = {"Idle": 0, "Movement": 1, "Action": 2, "Action2": 3, "Action3": 4,
            "Action4": 5, "Core": 1000}


def joint_transform(rig, joint):
    """Motor6D.Transform (3x3 rotation, translation) for a joint, in Roblox terms."""
    bones = rig.data.bones
    pose = rig.pose.bones

    def world(name):
        return pose[name].matrix @ bones[name].matrix_local.inverted()

    d = world(PARENT[joint]).inverted() @ world(joint)
    r_bl = d.to_3x3()
    pivot = bones[joint].head_local
    t_bl = (d @ pivot) - pivot
    r_char = A.transposed() @ r_bl @ A
    t_char = A.transposed() @ t_bl
    c0 = Matrix(C0[joint])
    return c0.transposed() @ r_char @ c0, c0.transposed() @ t_char


def fmt(v):
    v = round(v, 6)
    if v == 0:
        v = 0.0  # avoid "-0"
    return repr(v)


def cframe_xml(rot, pos, indent):
    vals = [("X", pos[0]), ("Y", pos[1]), ("Z", pos[2])]
    for i in range(3):
        for j in range(3):
            vals.append((f"R{i}{j}", rot[i][j]))
    inner = "".join(f"<{k}>{fmt(v)}</{k}>" for k, v in vals)
    return f'{indent}<CoordinateFrame name="CFrame">{inner}</CoordinateFrame>\n'


class Writer:
    def __init__(self):
        self.ref = 0
        self.parts = []

    def referent(self):
        self.ref += 1
        return f"RBX{self.ref:08X}"

    def pose(self, name, rot, pos, children, depth, weight=1.0):
        ind = "\t" * depth
        self.parts.append(f'{ind}<Item class="Pose" referent="{self.referent()}">\n')
        self.parts.append(f"{ind}\t<Properties>\n")
        self.parts.append(cframe_xml(rot, pos, ind + "\t\t"))
        self.parts.append(f'{ind}\t\t<token name="EasingDirection">0</token>\n')
        self.parts.append(f'{ind}\t\t<token name="EasingStyle">0</token>\n')  # Linear
        self.parts.append(f'{ind}\t\t<string name="Name">{name}</string>\n')
        self.parts.append(f'{ind}\t\t<float name="Weight">{fmt(weight)}</float>\n')
        self.parts.append(f"{ind}\t</Properties>\n")
        for child in children:
            child(depth + 1)
        self.parts.append(f"{ind}</Item>\n")


def reset_pose(rig):
    """Unkeyed bones keep whatever the previous action left behind - clear them."""
    for pb in rig.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.scale = (1, 1, 1)


def sample_action(rig, act, scene):
    step = int(act.get("r6_bake_step", 1))
    start, end = int(act.frame_range[0]), int(act.frame_range[1])
    frames = list(range(start, end + 1, step))
    if frames[-1] != end:
        frames.append(end)
    joints = [j for j in str(act.get("r6_joints", ",".join(C0))).split(",") if j]
    fps = scene.render.fps / scene.render.fps_base
    samples = []
    for f in frames:
        scene.frame_set(f)
        samples.append(((f - start) / fps, {j: joint_transform(rig, j) for j in joints}))
    return samples


def keyframe_sequence_xml(name, samples, loop, priority):
    w = Writer()
    out = w.parts
    out.append('<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
               'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
               'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">\n')
    out.append(f'\t<Item class="KeyframeSequence" referent="{w.referent()}">\n')
    out.append("\t\t<Properties>\n")
    out.append(f'\t\t\t<bool name="Loop">{"true" if loop else "false"}</bool>\n')
    out.append(f'\t\t\t<string name="Name">{name}</string>\n')
    out.append(f'\t\t\t<token name="Priority">{PRIORITY.get(priority, 1000)}</token>\n')
    out.append("\t\t</Properties>\n")
    ident = Matrix.Identity(3)
    for time, joints in samples:
        out.append(f'\t\t<Item class="Keyframe" referent="{w.referent()}">\n')
        out.append("\t\t\t<Properties>\n")
        out.append('\t\t\t\t<string name="Name">Keyframe</string>\n')
        out.append(f'\t\t\t\t<float name="Time">{fmt(time)}</float>\n')
        out.append("\t\t\t</Properties>\n")

        def limb(jname):
            return lambda d: w.pose(jname, *joints[jname], [], d)

        limbs = [limb(j) for j in CHILD_ORDER if j in joints]
        if "Torso" in joints:
            torso = [lambda d: w.pose("Torso", *joints["Torso"], limbs, d)]
        else:  # partial animation (e.g. ToolHold): keep hierarchy, zero weight
            torso = [lambda d: w.pose("Torso", ident, (0, 0, 0), limbs, d, weight=0.0)]
        w.pose("HumanoidRootPart", ident, (0, 0, 0), torso, 3, weight=0.0)
        out.append("\t\t</Item>\n")
    out.append("\t</Item>\n</roblox>\n")
    return "".join(out)


def export_all(out_dir, rig_name=RIG_NAME):
    scene = bpy.context.scene
    rig = bpy.data.objects[rig_name]
    ad = rig.animation_data or rig.animation_data_create()
    saved = (ad.action, ad.action_slot if ad.action else None, scene.frame_current)
    os.makedirs(out_dir, exist_ok=True)
    manifest = []
    for act in sorted(bpy.data.actions, key=lambda a: a.name):
        if not act.get("r6_export"):
            continue
        reset_pose(rig)
        ad.action = act
        if act.slots:
            ad.action_slot = act.slots[0]
        name = act.name[3:] if act.name.startswith("R6_") else act.name
        samples = sample_action(rig, act, scene)
        loop = bool(act.get("r6_loop", False))
        priority = str(act.get("r6_priority", "Core"))
        xml = keyframe_sequence_xml(name, samples, loop, priority)
        path = os.path.join(out_dir, name + ".rbxmx")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(xml)
        manifest.append(dict(name=name, length=samples[-1][0], keys=len(samples), loop=loop,
                             priority=priority, stride=act.get("r6_stride")))
        print(f"[R6] exported {name}: {len(samples)} keys, {samples[-1][0]:.3f}s -> {path}")
    ad.action = saved[0]
    if saved[0] is not None and saved[1] is not None:
        ad.action_slot = saved[1]
    scene.frame_set(saved[2])
    return manifest


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--out" in argv:
        out_dir = argv[argv.index("--out") + 1]
    else:
        base = bpy.path.abspath("//") or os.getcwd()
        out_dir = os.path.join(base, "roblox_export")
    manifest = export_all(out_dir)
    print(f"[R6] {len(manifest)} animations written to {out_dir}")


if __name__ == "__main__":
    main()
