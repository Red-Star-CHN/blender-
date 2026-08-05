"""Open Blender GUI and generate sample pipe / ladder / railing from curves."""

import bpy
import os

ADDON_PATH = os.path.normpath(r"E:\blender-\addons\curve_mesh_generator.py")
SAVE_PATH = os.path.normpath(r"E:\blender-\docs\sample_scene.blend")


def enable_addon():
    prefs = bpy.context.preferences
    if "curve_mesh_generator" not in prefs.addons:
        bpy.ops.preferences.addon_install(filepath=ADDON_PATH)
    bpy.ops.preferences.addon_enable(module="curve_mesh_generator")
    assert "curve_mesh_generator" in prefs.addons, "Addon enable failed"


def make_curve(name, location, points):
    cd = bpy.data.curves.new(name, "CURVE")
    cd.dimensions = "3D"
    sp = cd.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for i, p in enumerate(points):
        sp.points[i].co = (*p, 1.0)
    obj = bpy.data.objects.new(name, cd)
    obj.location = location
    bpy.context.collection.objects.link(obj)
    return obj


def activate(obj):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def main():
    enable_addon()

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    props = bpy.context.scene.cmg_props

    # Curve 1: curved polyline -> Pipe
    c1 = make_curve(
        "SampleCurve_Pipe", (0, 0, 0),
        [(-3, 0, 0), (-1.5, 1.5, 0.5), (0, 0, 1), (1.5, -1.5, 1.5), (3, 0, 2)],
    )
    activate(c1)
    props.gen_type = "PIPE"
    props.pipe_radius = 0.15
    props.pipe_ring_segments = 16
    props.pipe_length_segments = 48
    props.target_name = "SamplePipe"
    props.bevel_enabled = False
    bpy.ops.mesh.cmg_generate()

    # Curve 2: straight line -> Ladder
    c2 = make_curve(
        "SampleCurve_Ladder", (8, 0, 0),
        [(0, 0, 0), (0, 0, 4)],
    )
    activate(c2)
    props.gen_type = "LADDER"
    props.ladder_width = 0.8
    props.ladder_num_rungs = 10
    props.ladder_side_diameter = 0.08
    props.ladder_rung_diameter = 0.06
    props.ladder_rung_segments = 10
    props.target_name = "SampleLadder"
    props.bevel_enabled = False
    bpy.ops.mesh.cmg_generate()

    # Curve 3: straight line -> Railing
    c3 = make_curve(
        "SampleCurve_Railing", (16, 0, 0),
        [(0, 0, 0), (0, 0, 6)],
    )
    activate(c3)
    props.gen_type = "RAILING"
    props.railing_height = 1.2
    props.railing_num_posts = 9
    props.railing_post_diameter = 0.1
    props.railing_rail_diameter = 0.08
    props.railing_rail_segments = 10
    props.target_name = "SampleRailing"
    props.bevel_enabled = True
    props.bevel_width = 0.01
    props.bevel_segments = 2
    bpy.ops.mesh.cmg_generate()

    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = None

    os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=SAVE_PATH)

    print("[SAMPLE] scene saved to", SAVE_PATH)


if __name__ == "__main__":
    main()
