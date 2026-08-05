"""Test railing layout: lower rail sits at mid-height of posts, upper rail stays at post top.

Curve is horizontal (along X). v1.0 orientation: rails run along the curve,
posts follow the curve-local up direction (which points -Z for a horizontal curve).
"""

import bpy
import sys
import os

ADDON_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "addons"))
sys.path.append(ADDON_PATH)

bpy.ops.preferences.addon_install(filepath=os.path.join(ADDON_PATH, "curve_mesh_generator.py"))
bpy.ops.preferences.addon_enable(module="curve_mesh_generator")

cd = bpy.data.curves.new("RailCurve", "CURVE")
cd.dimensions = "3D"
sp = cd.splines.new("POLY")
sp.points.add(1)
sp.points[0].co = (-2, 0, 0, 1)
sp.points[1].co = (2, 0, 0, 1)
obj = bpy.data.objects.new("RailCurve", cd)
bpy.context.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

props = bpy.context.scene.cmg_props
props.gen_type = "RAILING"
props.railing_height = 1.2
props.railing_num_posts = 5
props.railing_rail_diameter = 0.08
props.railing_post_diameter = 0.1
props.railing_rail_segments = 8
props.target_name = "LayoutRailing"
props.bevel_enabled = False
bpy.ops.mesh.cmg_generate()

rail = bpy.data.objects.get("LayoutRailing")
assert rail is not None, "Railing not created"

zs = [v.co.z for v in rail.data.vertices]
min_z, max_z = min(zs), max(zs)
print(f"[LAYOUT] min_z={min_z:.4f} max_z={max_z:.4f} verts={len(zs)}")

H = 1.2
R = 0.04  # rail radius

# Lower rail center must be at mid-height of the posts: -H/2
lower_band = [z for z in zs if -(H / 2 + R) - 1e-4 < z < -(H / 2 - R) + 1e-4]
assert lower_band, f"No vertices at lower rail mid-height band around -{H/2}: {zs}"
print(f"[LAYOUT] lower rail at -{H/2:.2f} (mid of posts): {len(lower_band)} verts")

# Upper rail center must stay at the post top: -H
upper_band = [z for z in zs if -(H + R) - 1e-4 < z < -(H - R) + 1e-4]
assert upper_band, f"No vertices at upper rail band around -{H}"
print(f"[LAYOUT] upper rail at -{H:.2f} (post top): {len(upper_band)} verts")

# Posts span from curve plane (z=0) down to the top rail
assert abs(max_z) < 1e-3, f"Posts should start at z=0, got max_z={max_z}"
print("[LAYOUT] PASSED")
bpy.ops.wm.quit_blender()
