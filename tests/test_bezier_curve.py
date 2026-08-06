"""Extra test: generate from a BEZIER curve (curved path sampling)."""

import bpy
import sys
import os
from mathutils import Vector

ADDON_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "addons"))
sys.path.append(ADDON_PATH)

bpy.ops.preferences.addon_install(filepath=os.path.join(ADDON_PATH, "curve_mesh_generator.py"))
bpy.ops.preferences.addon_enable(module="curve_mesh_generator")

curve_data = bpy.data.curves.new("BezierCurve", "CURVE")
curve_data.dimensions = "3D"
spline = curve_data.splines.new("BEZIER")
spline.bezier_points.add(3)
pts = [
    ((-2, 0, 0), (-1.5, 0, 0), (-0.5, 0, 0)),
    ((0, 0, 0), (0.5, 0, 0), (1.5, 2, 1)),
    ((2, 2, 1), (2.5, 2, 1), (3.5, 2, 1)),
    ((4, 2, 1), (4.5, 2, 1), (5, 3, 2)),
]
for i, (co, hl, hr) in enumerate(pts):
    p = spline.bezier_points[i]
    p.co = co
    p.handle_left = hl
    p.handle_right = hr

curve_obj = bpy.data.objects.new("BezierCurve", curve_data)
bpy.context.collection.objects.link(curve_obj)
bpy.context.view_layer.objects.active = curve_obj
curve_obj.select_set(True)

props = bpy.context.scene.cmg_props
props.gen_type = "PIPE"
props.pipe_radius = 0.15
props.pipe_ring_segments = 12
props.pipe_length_segments = 40
props.target_name = "CurvedPipe"
props.bevel_enabled = True
props.bevel_width = 0.01
bpy.ops.mesh.cmg_generate()

pipe = bpy.data.objects.get("CurvedPipe")
assert pipe is not None, "Pipe not created"
verts = len(pipe.data.vertices)
faces = len(pipe.data.polygons)
print(f"[TEST2] Curved pipe: {verts} verts, {faces} faces")
assert verts == (40 + 1) * 12, f"Verts {verts} != {(40+1)*12}"
assert faces == 40 * 12, f"Faces {faces} != {40*12}"

# Bounding box should span the curve extent (non-degenerate).
# NOTE: use all vertex positions, not bound_box (which only holds 8 extreme corner
# combinations and can miss the true extreme vertex).
xs = [(pipe.matrix_world @ v.co).x for v in pipe.data.vertices]
span = max(xs) - min(xs)
print(f"[TEST2] Bounding box X span: {span:.3f}")
assert span > 6.0, f"Pipe not following curve (span {span})"

print("[TEST2] PASSED")
bpy.ops.wm.quit_blender()
