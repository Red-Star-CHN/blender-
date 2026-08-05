bl_info = {
    "name": "曲线网格生成器",
    "author": "Red-Star-CHN",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "3D 视图 > 侧边栏 > 曲线网格",
    "description": "根据曲线生成管道、梯子和栏杆网格，可编辑分段与面数，支持倒角操作。",
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
# 通用工具
# ---------------------------------------------------------------------------


def ensure_selected_curve(context):
    obj = context.active_object
    if obj is None or obj.type != "CURVE":
        return None
    return obj


def _sample_spline_points(spline, per_seg=8):
    """沿一条样条（POLY 或 BEZIER）采样局部坐标点。"""
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
    """采样曲线对象的世界坐标点与切线方向。"""
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


def resample_points(points, num):
    """按弦长将折线均匀重采样为 num 个点。"""
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


def _frame_from_tangent(tang):
    """构建一个局部 Z 轴与切线对齐的旋转矩阵。"""
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
    """返回两点间（可选锥形）圆柱的 (顶点, 面) 列表。"""
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


def _append_swept_cylinder(all_verts, all_faces, path, radius, segments):
    """沿折线路径扫掠开口圆柱，追加到顶点/面列表。"""
    segments = max(3, segments)
    path = resample_points(path, max(len(path), 2))
    base = len(all_verts)
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
        for j in range(segments):
            angle = (j / segments) * math.tau
            local = Vector((math.cos(angle) * radius, math.sin(angle) * radius, 0.0))
            all_verts.append(mat @ local + loc)
    for i in range(len(path) - 1):
        off = i * segments
        for j in range(segments):
            j1 = (j + 1) % segments
            all_faces.append(
                (base + off + j, base + off + j1,
                 base + off + segments + j1, base + off + segments + j)
            )
    return base


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


# 面板属性键与默认值，用于将存储值同步回面板。
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
    """将选中物体存储的参数复制到面板属性。"""
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
# 网格构建
# ---------------------------------------------------------------------------


def build_pipe_mesh(name, points, radius, ring_segments, length_segments):
    """沿采样曲线路径扫掠的中空圆柱（管道）。"""
    ring_segments = max(3, ring_segments)
    length_segments = max(2, length_segments)
    path = resample_points(points, length_segments + 1)

    all_verts = []
    all_faces = []
    _append_swept_cylinder(all_verts, all_faces, path, radius, ring_segments)

    mesh = _new_mesh(name)
    mesh.from_pydata(all_verts, [], all_faces)
    mesh.update()
    return mesh


def build_ladder_mesh(name, points, width, rung_segments, num_rungs, side_diameter, rung_diameter):
    """沿曲线方向生成梯子：两根纵梁 + 等距横档。"""
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
    """栏杆沿曲线方向生成：上下横杆 + 立柱；下横杆位于立柱中央，上横杆位于柱顶。"""
    start, end = points[0], points[-1]
    axis = end - start
    if axis.length < 1e-9:
        return _new_mesh(name)
    tang = axis.normalized()
    mat = _frame_from_tangent(tang)
    # 立柱方向：默认朝上（绕水平面翻转 180 度后取反，栏杆位于曲线上方）
    up = -(mat @ Vector((0.0, 1.0, 0.0)))

    rail_segments = max(3, rail_segments)
    num_posts = max(2, num_posts)

    all_verts = []
    all_faces = []

    up_offset = up * height
    mid_offset = up * (height / 2)

    # 底部横杆：位于立柱中央
    v, f = _cylinder_between(start + mid_offset, end + mid_offset, rail_diameter / 2, rail_segments)
    base = len(all_verts)
    all_verts.extend(v)
    all_faces.extend([tuple(vi + base for vi in face) for face in f])

    # 顶部横杆：位于柱顶（保持不动）
    v, f = _cylinder_between(start + up_offset, end + up_offset, rail_diameter / 2, rail_segments)
    base = len(all_verts)
    all_verts.extend(v)
    all_faces.extend([tuple(vi + base for vi in face) for face in f])

    # 立柱：从曲线处到柱顶
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
# 属性组
# ---------------------------------------------------------------------------


class CMGProperties(bpy.types.PropertyGroup):
    gen_type: bpy.props.EnumProperty(
        name="生成类型",
        description="由曲线生成的网格类型",
        items=[
            (CMG_TYPE_PIPE, "管道", "生成沿曲线的中空圆柱管道"),
            (CMG_TYPE_LADDER, "梯子", "沿曲线方向生成梯子（纵梁 + 横档）"),
            (CMG_TYPE_RAILING, "栏杆", "生成水平栏杆（横杆水平延伸、立柱竖直）"),
        ],
        default=CMG_TYPE_PIPE,
    )

    pipe_radius: bpy.props.FloatProperty(
        name="半径", description="管道的半径", default=0.1, min=0.001, max=10.0, unit="LENGTH")
    pipe_ring_segments: bpy.props.IntProperty(
        name="环面数", description="管道圆周上的面数", default=12, min=3, max=256)
    pipe_length_segments: bpy.props.IntProperty(
        name="纵向分段", description="沿管道长度方向的分段数", default=32, min=2, max=4096)

    ladder_width: bpy.props.FloatProperty(
        name="宽度", description="梯子的宽度", default=0.5, min=0.01, max=10.0, unit="LENGTH")
    ladder_num_rungs: bpy.props.IntProperty(
        name="横档数量", description="梯子横档的根数", default=8, min=1, max=1024)
    ladder_side_diameter: bpy.props.FloatProperty(
        name="纵梁直径", description="两侧纵梁的直径", default=0.08, min=0.001, max=1.0, unit="LENGTH")
    ladder_rung_diameter: bpy.props.FloatProperty(
        name="横档直径", description="横档的直径", default=0.06, min=0.001, max=1.0, unit="LENGTH")
    ladder_rung_segments: bpy.props.IntProperty(
        name="横档面数", description="横档圆周上的面数", default=8, min=3, max=256)

    railing_height: bpy.props.FloatProperty(
        name="高度", description="栏杆的高度（立柱长度）", default=1.0, min=0.01, max=50.0, unit="LENGTH")
    railing_num_posts: bpy.props.IntProperty(
        name="立柱数量", description="栏杆立柱的根数", default=6, min=2, max=1024)
    railing_post_diameter: bpy.props.FloatProperty(
        name="立柱直径", description="立柱的直径", default=0.1, min=0.001, max=1.0, unit="LENGTH")
    railing_rail_diameter: bpy.props.FloatProperty(
        name="横杆直径", description="上下横杆的直径", default=0.08, min=0.001, max=1.0, unit="LENGTH")
    railing_rail_segments: bpy.props.IntProperty(
        name="横杆面数", description="横杆圆周上的面数", default=8, min=3, max=256)

    bevel_enabled: bpy.props.BoolProperty(
        name="启用倒角", description="是否为生成物体添加倒角修改器", default=True)
    bevel_width: bpy.props.FloatProperty(
        name="倒角宽度", description="倒角的宽度", default=0.005, min=0.0, max=1.0, unit="LENGTH")
    bevel_segments: bpy.props.IntProperty(
        name="倒角分段", description="倒角的细分段数", default=2, min=1, max=64)

    target_name: bpy.props.StringProperty(
        name="物体名称", description="生成物体的名称", default="Generated", maxlen=63)

    last_active: bpy.props.StringProperty(
        name="上次选中物体", description="内部使用：已同步到面板的物体", default="")


# ---------------------------------------------------------------------------
# 操作符
# ---------------------------------------------------------------------------


class MESH_OT_cmg_generate(bpy.types.Operator):
    bl_idname = "mesh.cmg_generate"
    bl_label = "生成"
    bl_description = "根据当前曲线生成所选类型的网格物体"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return ensure_selected_curve(context) is not None

    def execute(self, context):
        curve = ensure_selected_curve(context)
        if curve is None:
            self.report({"ERROR"}, "请先选择一条曲线")
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
            points, _ = sample_curve_points(curve, 16)
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

        type_names = {"PIPE": "管道", "LADDER": "梯子", "RAILING": "栏杆"}
        self.report({"INFO"}, "{}已生成".format(type_names.get(props.gen_type, props.gen_type)))
        return {"FINISHED"}


class MESH_OT_cmg_update(bpy.types.Operator):
    bl_idname = "mesh.cmg_update"
    bl_label = "更新选中物体"
    bl_description = "使用面板当前参数重建选中的物体"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and owns_prop(obj, "gen_type")

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH" or not owns_prop(obj, "gen_type"):
            self.report({"ERROR"}, "请选择由本插件生成的网格物体")
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
            self.report({"ERROR"}, "场景中未找到用于重建的曲线")
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
            points, _ = sample_curve_points(curve, 16)
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

        type_names = {"PIPE": "管道", "LADDER": "梯子", "RAILING": "栏杆"}
        self.report({"INFO"}, "{}已更新".format(type_names.get(gen_type, gen_type)))
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# 面板
# ---------------------------------------------------------------------------


class VIEW3D_PT_cmg(bpy.types.Panel):
    bl_label = "曲线网格生成器"
    bl_idname = "VIEW3D_PT_cmg"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "曲线网格"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.cmg_props
        curve = ensure_selected_curve(context)
        obj = context.active_object

        if obj is not None and obj.type == "MESH" and owns_prop(obj, "gen_type"):
            if props.last_active != obj.name:
                sync_props_from_object(props, obj)
                props.last_active = obj.name
            row = layout.row()
            row.label(text="已加载参数：", icon="MESH_DATA")
            row.label(text=obj.name)
        elif curve is not None:
            row = layout.row()
            row.label(text="曲线：", icon="CURVE_DATA")
            row.label(text=curve.name)
        else:
            layout.label(text="请先选择一条曲线", icon="INFO")

        layout.prop(props, "gen_type")

        if props.gen_type == CMG_TYPE_PIPE:
            box = layout.box()
            box.label(text="管道参数", icon="MESH_CYLINDER")
            col = box.column(align=True)
            col.prop(props, "pipe_radius")
            col.prop(props, "pipe_ring_segments", text="环面数（圆周分段）")
            col.prop(props, "pipe_length_segments", text="纵向分段")
        elif props.gen_type == CMG_TYPE_LADDER:
            box = layout.box()
            box.label(text="梯子参数", icon="MESH_CYLINDER")
            col = box.column(align=True)
            col.prop(props, "ladder_width")
            col.prop(props, "ladder_num_rungs", text="横档数量")
            col.prop(props, "ladder_side_diameter")
            col.prop(props, "ladder_rung_diameter")
            col.prop(props, "ladder_rung_segments", text="横档面数")
        else:
            box = layout.box()
            box.label(text="栏杆参数", icon="MESH_CYLINDER")
            col = box.column(align=True)
            col.prop(props, "railing_height")
            col.prop(props, "railing_num_posts", text="立柱数量")
            col.prop(props, "railing_post_diameter")
            col.prop(props, "railing_rail_diameter")
            col.prop(props, "railing_rail_segments", text="横杆面数")

        bevel_box = layout.box()
        bevel_box.label(text="倒角", icon="MOD_BEVEL")
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
            type_names = {"PIPE": "管道", "LADDER": "梯子", "RAILING": "栏杆"}
            row = layout.row()
            row.label(text="选中物体：", icon="MESH_DATA")
            row.label(text=obj.name)
            layout.label(text="类型：" + type_names.get(stored.get("gen_type", ""), "未知"))
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
