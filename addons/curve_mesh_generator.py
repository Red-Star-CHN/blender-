bl_info = {
    "name": "Curve Mesh Generator",
    "author": "Red-Star-CHN",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Curve Mesh",
    "description": "Generate pipe, ladder and railing meshes from curves. Editable segments/faces and bevel.",
    "warning": "",
    "doc_url": "",
    "category": "Mesh",
}

import bpy
import math
from mathutils import Vector, Matrix

CMG_TYPE_PIPE = "PIPE"
CMG_TYPE_LADDER = "LADDER"
CMG_TYPE_RAILING = "RAILING"

PROP_PREFIX = "cmg_"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ensure_selected_curve(context):
    obj = context.active_object
    if obj is None or obj.type != "CURVE":
        return None
    return obj


def _sample_spline_points(spline, per_seg=8):
    """Sample local-space points along one spline (POLY or BEZIER)."""
    pts = []
    if spline.type == "POLY":
        n = len(spline.points)
        for i in range(n - 1):
            a = spline.points[i].co.to_3d()
            b = spline.points[i + 1].co.to_3d()
            for k in range(per_seg):
                pts.append(a.lerp(b, k / per_seg))
        if n:
            pts.append(spline.points[-1].co.to_3d())
    elif spline.type == "BEZIER":
        n = len(spline.bezier_points)
        for i in range(n - 1):
            p0 = spline.bezier_points[i]
            p1 = spline.bezier_points[i + 1]
            for k in range(per_seg):
                t = k / per_seg
                mt = 1.0 - t
                pts.append(
                    p0.co * mt * mt * mt
                    + p0.handle_right * 3.0 * mt * mt * t
                    + p1.handle_left * 3.0 * mt * t * t
                    + p1.co * t * t * t
                )
        if n:
            pts.append(spline.bezier_points[-1].co.to_3d())
    return pts


def sample_curve_points(obj, num_points):
    """Sample world-space points and tangents along a curve object."""
    if num_points < 2:
        num_points = 2
    raw = []
    for spline in obj.data.splines:
        raw.extend(_sample_spline_points(spline))
    if not raw:
        return [], []
    world_raw = [obj.matrix_world @ v for v in raw]
    points = resample_points(world_raw, num_points)

    tangents = []
    for i in range(len(points)):
        if i == 0:
            t = points[1] - points[0]
        elif i == len(points) - 1:
            t = points[-1] - points[-2]
        else:
            t = points[i + 1] - points[i - 1]
        if t.length_squared < 1e-12:
            tangents.append(Vector((1.0, 0.0, 0.0)))
        else:
            tangents.append(t.normalized())
    return points, tangents


def _frame_from_tangent(tang):
    """Build a 3x3 rotation matrix whose local Z axis aligns with the tangent."""
    t = tang.normalized()
    ref = Vector((0.0, 0.0, 1.0)) if abs(t.dot(Vector((0.0, 0.0, 1.0)))) < 0.99 else Vector((1.0, 0.0, 0.0))
    x = t.cross(ref)
    if x.length_squared < 1e-12:
        x = Vector((1.0, 0.0, 0.0))
    else:
        x.normalize()
    y = t.cross(x)
    return Matrix((x, y, t)).transposed()


def _new_mesh(name):
    return bpy.data.meshes.new(name)


def _assign_object(context, mesh, name):
    obj = bpy.data.objects.new(name, mesh)
    context.collection.objects.link(obj)
    return obj


def _cylinder_between(p1, p2, radius, segments, radius2=None):
    """Return (verts, faces) of an open (optionally tapered) cylinder between p1 and p2."""
    axis = p2 - p1
    length = axis.length
    if length < 1e-9:
        return [], []
    tang = axis.normalized()
    mat = _frame_from_tangent(tang)
    r2 = radius if radius2 is None else radius2
    verts = []
    for k, center, rad in ((0, p1, radius), (1, p2, r2)):
        for j in range(segments):
            angle = (j / segments) * math.tau
            local = Vector((math.cos(angle) * rad, math.sin(angle) * rad, 0.0))
            verts.append(mat @ local + center)
    faces = []
    for j in range(segments):
        j1 = (j + 1) % segments
        faces.append((j, j1, segments + j1, segments + j))
    return verts, faces


def resample_points(points, num):
    """Resample a polyline into `num` evenly spaced points (chord length)."""
    if num < 2:
        num = 2
    if len(points) < 2:
        return points[:num] if len(points) else [Vector((0, 0, 0))] * num

    cum = [0.0]
    for i in range(1, len(points)):
        cum.append(cum[-1] + (points[i] - points[i - 1]).length)
    total = cum[-1]
    if total < 1e-12:
        return [points[0]] * num

    out = []
    for i in range(num):
        target = total * i / (num - 1)
        lo = 0
        while lo < len(cum) - 2 and cum[lo + 1] < target:
            lo += 1
        hi = lo + 1
        seg_len = cum[hi] - cum[lo]
        f = 0.0 if seg_len < 1e-12 else (target - cum[lo]) / seg_len
        out.append(points[lo].lerp(points[hi], f))
    return out


def store_props(obj, props):
    for key, value in props.items():
        obj[PROP_PREFIX + key] = value


def read_props(obj):
    out = {}
    if obj is None:
        return out
    for key in obj.keys():
        if key.startswith(PROP_PREFIX):
            out[key[len(PROP_PREFIX):]] = obj[key]
    return out


def owns_prop(obj, key):
    return PROP_PREFIX + key in obj


# Panel property keys and their defaults, used to sync stored values back to the panel.
SYNC_DEFAULTS = {
    "pipe_radius": 0.1,
    "pipe_ring_segments": 12,
    "pipe_length_segments": 32,
    "ladder_width": 0.5,
    "ladder_num_rungs": 8,
    "ladder_side_diameter": 0.08,
    "ladder_rung_diameter": 0.06,
    "ladder_rung_segments": 8,
    "railing_height": 1.0,
    "railing_num_posts": 6,
    "railing_post_diameter": 0.1,
    "railing_rail_diameter": 0.08,
    "railing_rail_segments": 8,
    "bevel_enabled": True,
    "bevel_width": 0.005,
    "bevel_segments": 2,
}


def sync_props_from_object(props, obj):
    """Copy stored object parameters into the scene panel properties."""
    stored = read_props(obj)
    for key, default in SYNC_DEFAULTS.items():
        value = stored.get(key, default)
        try:
            setattr(props, key, value)
        except Exception:
            pass
    gen_type = stored.get("gen_type", props.gen_type)
    if gen_type in (CMG_TYPE_PIPE, CMG_TYPE_LADDER, CMG_TYPE_RAILING):
        props.gen_type = gen_type


# ---------------------------------------------------------------------------
# Mesh builders
# ---------------------------------------------------------------------------


def build_pipe_mesh(name, points, radius, ring_segments, length_segments):
    """Hollow cylinder swept along the sampled curve path."""
    ring_segments = max(3, ring_segments)
    length_segments = max(2, length_segments)
    path = resample_points(points, length_segments + 1)

    verts = []
    tangents = []
    for i in range(len(path)):
        if i == 0:
            t = path[1] - path[0]
        elif i == len(path) - 1:
            t = path[-1] - path[-2]
        else:
            t = path[i + 1] - path[i - 1]
        tangents.append(t.normalized() if t.length > 1e-9 else Vector((0, 0, 1)))

    for i, loc in enumerate(path):
        mat = _frame_from_tangent(tangents[i])
        for j in range(ring_segments):
            angle = (j / ring_segments) * math.tau
            local = Vector((math.cos(angle) * radius, math.sin(angle) * radius, 0.0))
            verts.append(mat @ local + loc)

    faces = []
    for i in range(length_segments):
        base = i * ring_segments
        for j in range(ring_segments):
            j1 = (j + 1) % ring_segments
            faces.append((base + j, base + j1, base + ring_segments + j1, base + ring_segments + j))

    mesh = _new_mesh(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


def build_ladder_mesh(name, points, width, rung_segments, num_rungs, side_diameter, rung_diameter):
    """Ladder along the curve direction: two side rails + evenly spaced rungs."""
    start, end = points[0], points[-1]
    axis = end - start
    if axis.length < 1e-9:
        return _new_mesh(name)
    tang = axis.normalized()
    mat = _frame_from_tangent(tang)
    x_axis = mat @ Vector((1.0, 0.0, 0.0))

    rung_segments = max(3, rung_segments)
    num_rungs = max(1, num_rungs)

    all_verts = []
    all_faces = []

    for sign in (-1.0, 1.0):
        offset = x_axis * (width / 2) * sign
        v, f = _cylinder_between(start + offset, end + offset, side_diameter / 2, rung_segments)
        base = len(all_verts)
        all_verts.extend(v)
        all_faces.extend([tuple(vi + base for vi in face) for face in f])

    for i in range(num_rungs):
        factor = (i + 0.5) / num_rungs if num_rungs > 1 else 0.5
        center = start.lerp(end, factor)
        v, f = _cylinder_between(
            center - x_axis * (width / 2), center + x_axis * (width / 2),
            rung_diameter / 2, rung_segments,
        )
        base = len(all_verts)
        all_verts.extend(v)
        all_faces.extend([tuple(vi + base for vi in face) for face in f])

    mesh = _new_mesh(name)
    mesh.from_pydata(all_verts, [], all_faces)
    mesh.update()
    return mesh


def build_railing_mesh(name, points, height, num_posts, rail_segments, post_diameter, rail_diameter):
    """Railing along the curve: top+bottom rails, vertical posts."""
    start, end = points[0], points[-1]
    axis = end - start
    if axis.length < 1e-9:
        return _new_mesh(name)
    tang = axis.normalized()
    mat = _frame_from_tangent(tang)
    up = mat @ Vector((0.0, 1.0, 0.0))

    rail_segments = max(3, rail_segments)
    num_posts = max(2, num_posts)

    all_verts = []
    all_faces = []

    up_offset = up * height
    for p1, p2 in ((start, end), (start + up_offset, end + up_offset)):
        v, f = _cylinder_between(p1, p2, rail_diameter / 2, rail_segments)
        base = len(all_verts)
        all_verts.extend(v)
        all_faces.extend([tuple(vi + base for vi in face) for face in f])

    for i in range(num_posts):
        factor = i / (num_posts - 1) if num_posts > 1 else 0.0
        p1 = start.lerp(end, factor)
        p2 = p1 + up_offset
        v, f = _cylinder_between(p1, p2, post_diameter / 2, rail_segments)
        base = len(all_verts)
        all_verts.extend(v)
        all_faces.extend([tuple(vi + base for vi in face) for face in f])

    mesh = _new_mesh(name)
    mesh.from_pydata(all_verts, [], all_faces)
    mesh.update()
    return mesh


# ---------------------------------------------------------------------------
# Property group
# ---------------------------------------------------------------------------


class CMGProperties(bpy.types.PropertyGroup):
    gen_type: bpy.props.EnumProperty(
        name="Type",
        description="Mesh type to generate from the curve",
        items=[
            (CMG_TYPE_PIPE, "Pipe", "Generate a pipe (hollow cylinder) along the curve"),
            (CMG_TYPE_LADDER, "Ladder", "Generate a ladder along the curve"),
            (CMG_TYPE_RAILING, "Railing", "Generate a railing/fence along the curve"),
        ],
        default=CMG_TYPE_PIPE,
    )

    pipe_radius: bpy.props.FloatProperty(
        name="Radius", default=0.1, min=0.001, max=10.0, unit="LENGTH")
    pipe_ring_segments: bpy.props.IntProperty(
        name="Ring Segments", description="Number of faces around the pipe",
        default=12, min=3, max=256)
    pipe_length_segments: bpy.props.IntProperty(
        name="Length Segments", description="Segments along the pipe",
        default=32, min=2, max=4096)

    ladder_width: bpy.props.FloatProperty(
        name="Width", default=0.5, min=0.01, max=10.0, unit="LENGTH")
    ladder_num_rungs: bpy.props.IntProperty(
        name="Rungs", default=8, min=1, max=1024)
    ladder_side_diameter: bpy.props.FloatProperty(
        name="Side Rail Dia.", default=0.08, min=0.001, max=1.0, unit="LENGTH")
    ladder_rung_diameter: bpy.props.FloatProperty(
        name="Rung Dia.", default=0.06, min=0.001, max=1.0, unit="LENGTH")
    ladder_rung_segments: bpy.props.IntProperty(
        name="Rung Faces", default=8, min=3, max=256)

    railing_height: bpy.props.FloatProperty(
        name="Height", default=1.0, min=0.01, max=50.0, unit="LENGTH")
    railing_num_posts: bpy.props.IntProperty(
        name="Posts", default=6, min=2, max=1024)
    railing_post_diameter: bpy.props.FloatProperty(
        name="Post Dia.", default=0.1, min=0.001, max=1.0, unit="LENGTH")
    railing_rail_diameter: bpy.props.FloatProperty(
        name="Rail Dia.", default=0.08, min=0.001, max=1.0, unit="LENGTH")
    railing_rail_segments: bpy.props.IntProperty(
        name="Rail Faces", default=8, min=3, max=256)

    bevel_enabled: bpy.props.BoolProperty(name="Enable Bevel", default=True)
    bevel_width: bpy.props.FloatProperty(
        name="Bevel Width", default=0.005, min=0.0, max=1.0, unit="LENGTH")
    bevel_segments: bpy.props.IntProperty(
        name="Bevel Segments", default=2, min=1, max=64)

    target_name: bpy.props.StringProperty(
        name="Object Name", default="Generated", maxlen=63)

    last_active: bpy.props.StringProperty(
        name="Last Active", description="Internal: last object synced into the panel",
        default="")


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------


class MESH_OT_cmg_generate(bpy.types.Operator):
    bl_idname = "mesh.cmg_generate"
    bl_label = "Generate"
    bl_description = "Generate the selected mesh type from the active curve"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return ensure_selected_curve(context) is not None

    def execute(self, context):
        curve = ensure_selected_curve(context)
        if curve is None:
            self.report({"ERROR"}, "Select a curve object first")
            return {"CANCELLED"}

        props = context.scene.cmg_props
        name = props.target_name or props.gen_type.title()

        if props.gen_type == CMG_TYPE_PIPE:
            points, _ = sample_curve_points(curve, max(props.pipe_length_segments * 4, 64))
            mesh = build_pipe_mesh(
                name, points, props.pipe_radius,
                props.pipe_ring_segments, props.pipe_length_segments,
            )
        elif props.gen_type == CMG_TYPE_LADDER:
            points, _ = sample_curve_points(curve, 2)
            mesh = build_ladder_mesh(
                name, points, props.ladder_width, props.ladder_rung_segments,
                props.ladder_num_rungs, props.ladder_side_diameter, props.ladder_rung_diameter,
            )
        else:
            points, _ = sample_curve_points(curve, 2)
            mesh = build_railing_mesh(
                name, points, props.railing_height, props.railing_num_posts,
                props.railing_rail_segments, props.railing_post_diameter, props.railing_rail_diameter,
            )

        obj = _assign_object(context, mesh, name)

        if props.bevel_enabled and props.bevel_width > 0.0:
            bevel = obj.modifiers.new("cmg_bevel", "BEVEL")
            bevel.width = props.bevel_width
            bevel.segments = props.bevel_segments
            bevel.limit_method = "ANGLE"

        store_props(obj, {
            "gen_type": props.gen_type,
            "pipe_radius": props.pipe_radius,
            "pipe_ring_segments": props.pipe_ring_segments,
            "pipe_length_segments": props.pipe_length_segments,
            "ladder_width": props.ladder_width,
            "ladder_num_rungs": props.ladder_num_rungs,
            "ladder_side_diameter": props.ladder_side_diameter,
            "ladder_rung_diameter": props.ladder_rung_diameter,
            "ladder_rung_segments": props.ladder_rung_segments,
            "railing_height": props.railing_height,
            "railing_num_posts": props.railing_num_posts,
            "railing_post_diameter": props.railing_post_diameter,
            "railing_rail_diameter": props.railing_rail_diameter,
            "railing_rail_segments": props.railing_rail_segments,
            "bevel_enabled": props.bevel_enabled,
            "bevel_width": props.bevel_width,
            "bevel_segments": props.bevel_segments,
        })

        context.view_layer.objects.active = obj
        obj.select_set(True)
        curve.select_set(False)

        self.report({"INFO"}, "{} generated".format(props.gen_type.title()))
        return {"FINISHED"}


class MESH_OT_cmg_update(bpy.types.Operator):
    bl_idname = "mesh.cmg_update"
    bl_label = "Update Selected"
    bl_description = "Regenerate the selected mesh from the scene curve using current panel values"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and owns_prop(obj, "gen_type")

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH" or not owns_prop(obj, "gen_type"):
            self.report({"ERROR"}, "Select a generated mesh object")
            return {"CANCELLED"}

        props = context.scene.cmg_props
        stored = read_props(obj)
        gen_type = stored.get("gen_type", props.gen_type)

        curve = None
        for src in context.scene.objects:
            if src.type == "CURVE" and src != obj:
                curve = src
                break
        if curve is None:
            self.report({"ERROR"}, "No curve found to regenerate from")
            return {"CANCELLED"}

        if gen_type == CMG_TYPE_PIPE:
            length_segments = int(props.pipe_length_segments)
            radius = float(props.pipe_radius)
            ring = int(props.pipe_ring_segments)
            points, _ = sample_curve_points(curve, max(length_segments * 4, 64))
            mesh = build_pipe_mesh(obj.name, points, radius, ring, length_segments)
        elif gen_type == CMG_TYPE_LADDER:
            width = float(props.ladder_width)
            rungs = int(props.ladder_num_rungs)
            side_d = float(props.ladder_side_diameter)
            rung_d = float(props.ladder_rung_diameter)
            rung_seg = int(props.ladder_rung_segments)
            points, _ = sample_curve_points(curve, 2)
            mesh = build_ladder_mesh(obj.name, points, width, rung_seg, rungs, side_d, rung_d)
        else:
            height = float(props.railing_height)
            posts = int(props.railing_num_posts)
            post_d = float(props.railing_post_diameter)
            rail_d = float(props.railing_rail_diameter)
            rail_seg = int(props.railing_rail_segments)
            points, _ = sample_curve_points(curve, 2)
            mesh = build_railing_mesh(obj.name, points, height, posts, rail_seg, post_d, rail_d)

        old_data = obj.data
        obj.data = mesh
        if old_data and old_data.users == 0:
            bpy.data.meshes.remove(old_data)

        bevel = next((m for m in obj.modifiers if m.type == "BEVEL"), None)
        bevel_enabled = bool(props.bevel_enabled)
        bevel_width = float(props.bevel_width)
        bevel_segments = int(props.bevel_segments)

        if bevel_enabled and bevel_width > 0.0:
            if bevel is None:
                bevel = obj.modifiers.new("cmg_bevel", "BEVEL")
            bevel.width = bevel_width
            bevel.segments = bevel_segments
            bevel.limit_method = "ANGLE"
            bevel.show_viewport = True
            bevel.show_render = True
        elif bevel is not None:
            bevel.show_viewport = False
            bevel.show_render = False

        store_props(obj, {
            "gen_type": gen_type,
            "pipe_radius": radius if gen_type == CMG_TYPE_PIPE else stored.get("pipe_radius", 0.1),
            "pipe_ring_segments": ring if gen_type == CMG_TYPE_PIPE else stored.get("pipe_ring_segments", 12),
            "pipe_length_segments": length_segments if gen_type == CMG_TYPE_PIPE else stored.get("pipe_length_segments", 32),
            "ladder_width": width if gen_type == CMG_TYPE_LADDER else stored.get("ladder_width", 0.5),
            "ladder_num_rungs": rungs if gen_type == CMG_TYPE_LADDER else stored.get("ladder_num_rungs", 8),
            "ladder_side_diameter": side_d if gen_type == CMG_TYPE_LADDER else stored.get("ladder_side_diameter", 0.08),
            "ladder_rung_diameter": rung_d if gen_type == CMG_TYPE_LADDER else stored.get("ladder_rung_diameter", 0.06),
            "ladder_rung_segments": rung_seg if gen_type == CMG_TYPE_LADDER else stored.get("ladder_rung_segments", 8),
            "railing_height": height if gen_type == CMG_TYPE_RAILING else stored.get("railing_height", 1.0),
            "railing_num_posts": posts if gen_type == CMG_TYPE_RAILING else stored.get("railing_num_posts", 6),
            "railing_post_diameter": post_d if gen_type == CMG_TYPE_RAILING else stored.get("railing_post_diameter", 0.1),
            "railing_rail_diameter": rail_d if gen_type == CMG_TYPE_RAILING else stored.get("railing_rail_diameter", 0.08),
            "railing_rail_segments": rail_seg if gen_type == CMG_TYPE_RAILING else stored.get("railing_rail_segments", 8),
            "bevel_enabled": bevel_enabled,
            "bevel_width": bevel_width,
            "bevel_segments": bevel_segments,
        })

        self.report({"INFO"}, "{} updated".format(gen_type.title()))
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------


class VIEW3D_PT_cmg(bpy.types.Panel):
    bl_label = "Curve Mesh"
    bl_idname = "VIEW3D_PT_cmg"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Curve Mesh"

    def draw(self, context):
        layout = self.layout
        props = context.scene.cmg_props
        curve = ensure_selected_curve(context)
        obj = context.active_object

        if obj is not None and obj.type == "MESH" and owns_prop(obj, "gen_type"):
            if props.last_active != obj.name:
                sync_props_from_object(props, obj)
                props.last_active = obj.name
            layout.label(text="Loaded: " + obj.name, icon="MESH_DATA")
        elif curve is not None:
            layout.label(text="Curve: " + curve.name, icon="CURVE_DATA")
        else:
            layout.label(text="Select a curve", icon="INFO")

        layout.prop(props, "gen_type")

        if props.gen_type == CMG_TYPE_PIPE:
            box = layout.box()
            box.label(text="Pipe", icon="MESH_CYLINDER")
            col = box.column(align=True)
            col.prop(props, "pipe_radius")
            col.prop(props, "pipe_ring_segments", text="Ring Segments")
            col.prop(props, "pipe_length_segments", text="Length Segments")
        elif props.gen_type == CMG_TYPE_LADDER:
            box = layout.box()
            box.label(text="Ladder", icon="MESH_CYLINDER")
            col = box.column(align=True)
            col.prop(props, "ladder_width")
            col.prop(props, "ladder_num_rungs", text="Rungs")
            col.prop(props, "ladder_side_diameter")
            col.prop(props, "ladder_rung_diameter")
            col.prop(props, "ladder_rung_segments", text="Rung Faces")
        else:
            box = layout.box()
            box.label(text="Railing", icon="MESH_CYLINDER")
            col = box.column(align=True)
            col.prop(props, "railing_height")
            col.prop(props, "railing_num_posts", text="Posts")
            col.prop(props, "railing_post_diameter")
            col.prop(props, "railing_rail_diameter")
            col.prop(props, "railing_rail_segments", text="Rail Faces")

        bevel_box = layout.box()
        bevel_box.label(text="Bevel", icon="MOD_BEVEL")
        bevel_box.prop(props, "bevel_enabled")
        col = bevel_box.column(align=True)
        col.enabled = props.bevel_enabled
        col.prop(props, "bevel_width")
        col.prop(props, "bevel_segments")

        layout.prop(props, "target_name")
        row = layout.row()
        row.operator("mesh.cmg_generate", icon="CHECKMARK")

        if obj is not None and obj.type == "MESH" and owns_prop(obj, "gen_type"):
            layout.separator()
            stored = read_props(obj)
            layout.label(text="Selected: " + obj.name, icon="MESH_DATA")
            layout.label(text="Stored type: " + stored.get("gen_type", "?").title())
            layout.operator("mesh.cmg_update", icon="FILE_REFRESH")


classes = (
    CMGProperties,
    MESH_OT_cmg_generate,
    MESH_OT_cmg_update,
    VIEW3D_PT_cmg,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.cmg_props = bpy.props.PointerProperty(type=CMGProperties)


def unregister():
    del bpy.types.Scene.cmg_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
