"""
Quick 60 fps preview of one animation (Workbench, fast), e.g. Walk, Run, GetUp, PickUp.

    blender -b R6_AnimPack.blend --python render_actions_preview.py -- R6_AnimPack.blend OUT_DIR PickUp

Walk/Run move across a 4-stud grid with a tracking camera so you can judge foot
contact; PickUp shows a crate that ends up in the hand.
"""
import os
import sys

import bpy
from mathutils import Vector, Matrix
BLEND, OUT, WHICH = sys.argv[sys.argv.index("--") + 1:][:3]
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
rig = bpy.data.objects["R6 Rig"]
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
except NameError:
    pass
import r6_export_roblox as ex
ex.reset_pose(rig)
act = bpy.data.actions["R6_" + WHICH]
rig.animation_data.action = act
rig.animation_data.action_slot = act.slots[0]
length = int(act.frame_range[1])

# ground with a 4-stud grid so motion reads
bpy.ops.mesh.primitive_plane_add(size=400, location=(0, -150, 0))
g = bpy.context.object
m = bpy.data.materials.new("grid"); m.use_nodes = True
m.diffuse_color = (0.32, 0.34, 0.37, 1)
g.data.materials.append(m)
for i in range(-12, 13):
    for name, size, loc in ((f"lx{i}", (0.06, 400, 0.01), (i * 4, -150, 0.005)),):
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc); o = bpy.context.object; o.scale = size
for j in range(0, 100):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 40 - j * 4, 0.005)); o = bpy.context.object; o.scale = (100, 0.06, 0.01)
line = bpy.data.materials.new("line"); line.diffuse_color = (0.25, 0.27, 0.3, 1)
for o in sc.objects:
    if o.type == "MESH" and o.dimensions.z < 0.02 and o != g:
        o.data.materials.append(line)

# Workbench shows the material's viewport colour - copy it from the shader.
for mat in bpy.data.materials:
    if mat.node_tree and "Principled BSDF" in mat.node_tree.nodes:
        mat.diffuse_color = mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value
bpy.data.materials["R6 Head"].diffuse_color = (0.91, 0.61, 0.03, 1)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 38
moving = WHICH in ("Walk", "Run")
speed = {"Walk": 6.25, "Run": 16.0}.get(WHICH, 0.0)
frames = {"Walk": 192, "Run": 150}.get(WHICH, length + 40)
if moving:
    for f in range(frames + 1):
        rig.location = (0, -speed * f / 60, 0); rig.keyframe_insert("location", frame=f)
    cam.location = (-17, -6, 5.0)
    c = cam.constraints.new("COPY_LOCATION"); c.target = rig; c.use_offset = True; c.use_z = False
    aim = Vector((0, -1.5, 2.6)) - Vector(cam.location)
else:
    cam.location = (-11.5, -12.5, 5.0) if WHICH == "PickUp" else (-16, -2, 5.0)
    aim = Vector((0, -1.0 if WHICH == "PickUp" else 1.0, 2.2)) - Vector(cam.location)
cam.rotation_euler = aim.to_track_quat("-Z", "Y").to_euler()

if WHICH == "PickUp":  # a crate on the floor that ends up in the hand
    grab = 60
    sc.frame_set(grab)
    arm = bpy.data.objects["R6 Right Arm"]
    hand = arm.matrix_world @ Vector((0, 0, -1.0))
    crate_mat = bpy.data.materials.new("crate"); crate_mat.diffuse_color = (0.85, 0.25, 0.15, 1)
    bpy.ops.mesh.primitive_cube_add(size=0.7, location=(hand.x, hand.y, 0.35)); floor_item = bpy.context.object
    floor_item.data.materials.append(crate_mat)
    bpy.ops.mesh.primitive_cube_add(size=0.7, location=(hand.x, hand.y, hand.z - 0.3)); held = bpy.context.object
    held.data.materials.append(crate_mat)
    held.parent = rig; held.parent_type = "BONE"; held.parent_bone = "Right Arm"
    bpy.context.view_layer.update(); held.matrix_world = Matrix.Translation((hand.x, hand.y, hand.z - 0.3))
    for ob, before, after in ((floor_item, False, True), (held, True, False)):
        ob.hide_render = before; ob.keyframe_insert("hide_render", frame=grab - 1)
        ob.hide_render = after; ob.keyframe_insert("hide_render", frame=grab)

sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light = "STUDIO"; sh.color_type = "MATERIAL"; sh.show_shadows = True; sh.show_cavity = True
sc.display.render_aa = "8"
sc.render.resolution_x, sc.render.resolution_y = 960, 540
sc.render.fps = 60
sc.frame_start, sc.frame_end = 0, frames
sc.render.filepath = os.path.join(OUT, WHICH + "_")
sc.render.image_settings.file_format = "PNG"
bpy.ops.render.render(animation=True)
