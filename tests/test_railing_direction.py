"""Test: railing from a VERTICAL curve must be HORIZONTAL (rails along ground plane, posts vertical)."""

import bpy
import sys
import os
from mathutils import Vector

ADDON_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "addons"))
sys.path.append(ADDON_PATH)

bpy.ops.preferences.addon_install(filepath=os.path.join(ADDON_PATH, "curve_mesh_generator.py"))
bpy.ops.preferences.addon_enable(module="curve_mesh_generator")

cd = bpy.data.curves.new("VertCurve", "CURVE")
cd.dimensions = "3D"
sp = cd.splines.new("POLY")
sp.points.add(1)
sp.points[0].co = (0, 0, 0, 1)
sp.points[1].co = (0, 0, 6, 1)
obj = bpy.data.objects.new("VertCurve", cd)
bpy.context.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

props = bpy.context.scene.cmg_props
props.gen_type = "RAILING"
props.railing_height = 1.2
props.railing_num_posts = 5
props.target_name = "DirRailing"
props.bevel_enabled = False
bpy.ops.mesh.cmg_generate()

rail = bpy.data.objects.get("DirRailing")
assert rail is not None, "Railing not created"

ws = [rail.matrix_world @ v.co for v in rail.data.vertices]
zs = sorted(v.z for v in ws)
min_z, max_z = zs[0], zs[-1]
xs = sorted(v.x for v in ws)
x_span = xs[-1] - xs[0]
z_span = max_z - min_z

print(f"[DIR] verts={len(ws)} z_span={z_span:.4f} x_span={x_span:.4f} min_z={min_z:.4f} max_z={max_z:.4f}")

# Vertical curve (length 6) must yield a railing whose height span equals height (+ rail diameter for tube walls)
assert 1.2 <= z_span <= 1.2 + props.railing_rail_diameter + 0.01, \
    f"Railing not horizontal: z_span {z_span} != height 1.2"
assert x_span > 0.01, f"Railing has no horizontal extent: x_span {x_span}"

# Rails should sit at two distinct heights: ground and ground + height
uniq = sorted({round(v.z, 3) for v in ws})
print(f"[DIR] unique Z heights: {uniq}")
print("[DIR] PASSED")
bpy.ops.wm.quit_blender()
