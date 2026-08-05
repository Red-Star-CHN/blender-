"""Test the Curve Mesh Generator addon in Blender (headless)."""

import bpy
import sys
import os

ADDON_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "addons"))
sys.path.append(ADDON_PATH)


def run_test():
    # 1. Install / enable addon
    bpy.ops.preferences.addon_install(filepath=os.path.join(ADDON_PATH, "curve_mesh_generator.py"))
    bpy.ops.preferences.addon_enable(module="curve_mesh_generator")
    enabled = "curve_mesh_generator" in bpy.context.preferences.addons
    print("[TEST] addon enabled:", enabled)
    assert enabled, "Addon failed to enable"

    # 2. Create a curve
    curve_data = bpy.data.curves.new("TestCurve", "CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("POLY")
    spline.points.add(3)
    spline.points[0].co = (-2, 0, 0, 1)
    spline.points[1].co = (0, 1.5, 1, 1)
    spline.points[2].co = (2, 0, 2, 1)
    spline.points[3].co = (4, -1, 3, 1)
    curve_obj = bpy.data.objects.new("TestCurve", curve_data)
    bpy.context.collection.objects.link(curve_obj)
    bpy.context.view_layer.objects.active = curve_obj
    curve_obj.select_set(True)

    props = bpy.context.scene.cmg_props

    # 3. Generate pipe
    props.gen_type = "PIPE"
    props.pipe_radius = 0.2
    props.pipe_ring_segments = 16
    props.pipe_length_segments = 24
    props.target_name = "TestPipe"
    bpy.ops.mesh.cmg_generate()
    pipe = bpy.data.objects.get("TestPipe")
    assert pipe is not None, "Pipe not created"
    verts = len(pipe.data.vertices)
    faces = len(pipe.data.polygons)
    print(f"[TEST] Pipe: {verts} verts, {faces} faces")
    expected_verts = (24 + 1) * 16
    expected_faces = 24 * 16
    assert verts == expected_verts, f"Pipe verts {verts} != {expected_verts}"
    assert faces == expected_faces, f"Pipe faces {faces} != {expected_faces}"
    assert pipe.get("cmg_gen_type") == "PIPE", "Pipe props not stored"

    # 4. Generate ladder
    bpy.context.view_layer.objects.active = curve_obj
    curve_obj.select_set(True)
    for o in bpy.data.objects:
        if o is not curve_obj and o.type != "CURVE":
            o.select_set(False)
    props.gen_type = "LADDER"
    props.ladder_width = 0.6
    props.ladder_num_rungs = 10
    props.ladder_rung_segments = 10
    props.target_name = "TestLadder"
    bpy.ops.mesh.cmg_generate()
    ladder = bpy.data.objects.get("TestLadder")
    assert ladder is not None, "Ladder not created"
    print(f"[TEST] Ladder: {len(ladder.data.vertices)} verts, {len(ladder.data.polygons)} faces")
    assert ladder.get("cmg_gen_type") == "LADDER"

    # 5. Generate railing
    bpy.context.view_layer.objects.active = curve_obj
    curve_obj.select_set(True)
    for o in bpy.data.objects:
        if o is not curve_obj and o.type != "CURVE":
            o.select_set(False)
    props.gen_type = "RAILING"
    props.railing_height = 1.2
    props.railing_num_posts = 8
    props.target_name = "TestRailing"
    bpy.ops.mesh.cmg_generate()
    railing = bpy.data.objects.get("TestRailing")
    assert railing is not None, "Railing not created"
    print(f"[TEST] Railing: {len(railing.data.vertices)} verts, {len(railing.data.polygons)} faces")
    assert railing.get("cmg_gen_type") == "RAILING"
    assert any(m.type == "BEVEL" for m in railing.modifiers), "Railing bevel missing"

    # 6. Update existing object (change segments)
    bpy.context.view_layer.objects.active = pipe
    pipe.select_set(True)
    ladder.select_set(False)
    railing.select_set(False)
    curve_obj.select_set(False)
    props.pipe_ring_segments = 6
    props.pipe_length_segments = 10
    bpy.ops.mesh.cmg_update()
    verts2 = len(pipe.data.vertices)
    print(f"[TEST] Pipe updated: {verts2} verts")
    assert verts2 == (10 + 1) * 6, f"Update failed: {verts2} != {(10+1)*6}"

    # 7. Bevel update
    props.bevel_width = 0.02
    props.bevel_segments = 4
    bpy.ops.mesh.cmg_update()
    bevel = next(m for m in pipe.modifiers if m.type == "BEVEL")
    print(f"[TEST] Bevel: width={bevel.width}, segments={bevel.segments}")
    assert abs(bevel.width - 0.02) < 1e-6 and bevel.segments == 4

    print("[TEST] ALL TESTS PASSED")


if __name__ == "__main__":
    run_test()
    bpy.ops.wm.quit_blender()
