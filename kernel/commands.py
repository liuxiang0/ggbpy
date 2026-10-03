"""命令处理与几何算法（P0）。

实现：Midpoint Line Segment Ray Circle Polygon Intersect Distance Slope Angle
      Length Translate Rotate Reflect Vector

设计：每个命令创建"派生元素"（deps + compute_fn 闭包），数值状态在 compute 时
按 deps 当前坐标重算 —— 拖动自由点后由 Construction 增量重算整条依赖链。
"""

from __future__ import annotations

import math
import re
from typing import Callable, Dict, List, Optional, Tuple

from . import schemas
from .cmd_util import (  # 命令层共享工具（自本模块抽出）
    _nested_depth,
    label_of,
    _label_of,
    _mk,
    _auto,
    _resolve,
    _lookup,
    _tuple_parts_any,
    _list_arg,
    _point_arg,
    _num_deps,
    _num_list_items,
    _num_series,
    _elem_or_point,
    _is_segment_el,
)
from .cmd_util import set_nested_evaluator
# 微积分/符号计算命令已抽到 kernel/calculus.py；re-export 保持调用方兼容
from .calculus import (  # noqa: F401
    _fmt,
    _feval,
    _roots_1d,
    _cmd_of,
    _cmd_derivative,
    _cmd_integral,
    _cmd_root,
    _root_state,
    _cmd_extremum,
    _cmd_rectsum,
    _int_values,
    _cmd_isprime,
    _cmd_divisors,
    _cmd_factorslist,
    _parse_sympy,
    _fit_expr,
    _cmd_fitexpr,
    _cmd_sequence,
    _cmd_normaldist,
    _cmd_solveineq,
    _fmt_sol,
    _fmt_sol_num,
)

# 导入导出命令（OBJ/STL/glTF 导入导出、图片与文本，P2 结构拆分：从 commands.py 抽出）。（P2 结构拆分：命令组抽出）
from .io_cmds import (  # noqa: F401
    _tuple_parts,
    _cmd_image,
    _txt_num,
    _dyn_text_segments,
    _ref_text,
    _dyn_text_compute,
    _cmd_text,
)

# 数值与统计命令（求和/均值/方差/排序/四分位/组合数/取整等，P2 结构拆分：从 commands.py 抽出）。（P2 结构拆分：命令组抽出）
from .numeric import (  # noqa: F401
    _cmd_npr,
    _cmd_ncr,
    _cmd_gcd,
    _cmd_lcm,
    _resolve_complex,
    _cmd_complex_abs,
    _cmd_sum,
    _cmd_mean,
    _cmd_median,
    _cmd_mode,
    _cmd_variance,
    _cmd_stdev,
    _cmd_min,
    _cmd_max,
    _cmd_sort,
    _cmd_normal,
    _cmd_q1,
    _cmd_q3,
    _cmd_iqr,
)

# 编辑与样式命令（改值/改色/改名/重定义/删除/显隐，P2 结构拆分：从 commands.py 抽出）。（P2 结构拆分：命令组抽出）
from .editing import _COLOR_NAMES  # noqa: F401
from .editing import (  # noqa: F401
    _COLOR_NAMES,
    _cmd_slider,
    _cmd_setcoords,
    _cmd_setvalue,
    _cmd_setlocked,
    _parse_color,
    _cmd_delete,
    _cmd_rename,
    _cmd_redefine,
    _cmd_setcolor,
    _cmd_setvisible,
    _cmd_macrodelete,
)

# 仿射变换命令（反射/旋转/平移/位似/反演，P2 结构拆分：从 commands.py 抽出）。（P2 结构拆分：命令组抽出）
from .transforms import DEG  # noqa: F401
from .transforms import (  # noqa: F401
    DEG,
    _cmd_translate,
    _cmd_rotate,
    _cmd_reflect,
    _transform_mk,
    _inv_map,
    _inv_circle_params,
    _inv_linear_state,
    _inv_circle_conic_state,
    _inv_line_conic_state,
    _source_chains,
    _inv_sampled_state,
    _invert_implicit_state,
    _mk_implicit,
    _mk_param_curve,
    _compose_inv,
    _seg_pole,
    _cmd_invert,
    _cmd_dilate,
)

# 二维图元命令（点/线/圆/多边形族，P2 结构拆分：从 commands.py 抽出）。（P2 结构拆分：命令组抽出）
from .primitives import _PRED_VIEW  # noqa: F401
from .primitives import (  # noqa: F401
    _resolve_vector,
    _resolve_vector3,
    _intersect_lines,
    _dist,
    _line_circle,
    _circle_circle,
    _circumcircle,
    _cmd_midpoint,
    _cmd_line,
    _line3d_state,
    _parallel_state,
    _cmd_segment,
    _seg3d_state,
    _cmd_ray,
    _cmd_circle,
    _circle_state,
    _circ_state,
    _cmd_polygon,
    _cmd_rigidpolygon,
    _cmd_polyline,
    _cmd_intersect,
    _cmd_isoline,
    _isoline_state,
    _ix_fn_fn,
    _ix_fn_lin,
    _ix_linlin,
    _check_seg_ray,
    _on_segment,
    _ix_lincir,
    _ix_circir,
    _ix_conic_conic,
    _cmd_vector,
    _mk_free,
    _line_y_x,
    _cmd_tangent,
    _tangent_state,
    _cmd_perpendicularline,
    _perp_state,
    _cmd_foot,
    _foot_state,
    _cmd_perpbis,
    _perpbis_state,
    _perpbis_state2,
    _cmd_regularpolygon,
    _cmd_anglebisector,
    _bisector_state,
    _cmd_incenter,
    _incenter_state,
    _cmd_incircle,
    _incircle_state,
    _cmd_centroid,
    _centroid_state,
    _cmd_randpointin,
    _randpointin_state,
    _cmd_fitline,
    _conic_coeffs,
    _cmd_tangent_conic,
    _tangent_conic_state_i,
    _tangent_arc_state,
    _tangent_conic_state,
    _ix_lin_conic,
    _pred_dir,
    _pred_scale,
    _numeric_verdict,
    _prove_cmd,
    _cmd_areparallel,
    _cmd_areperpendicular,
    _cmd_arecollinear,
    _cmd_pointoncircle,
    _cmd_pointonpath,
    _pop_state,
    _poc_state,
    _cmd_arc,
    _cmd_semicircle,
    _semicircle_state,
    _cmd_sector,
    _arc_state,
)

# 三维命令（P2 结构拆分（P2 结构拆分）
from .commands3d import (  # noqa: F401
    _cmd_bbox,
    _bbox_state,
    _cmd_covariance,
    _cmd_convexhull,
    _convexhull_state,
    _surface_eval,
    _cmd_surfacepoint,
    _surfacepoint_state,
    _cmd_surfaceproject,
    _surfaceproject_state,
    _cmd_fitsphere,
    _polygon_area,
    _cmd_area,
    _cmd_volume,
    _cmd_surface,
    _surface_compute,
    _cmd_mesh,
    _cmd_surface_param,
    _surface_param_compute,
    _cmd_implicit_surface,
    _implicit_surface_compute,
    _cmd_fitplane,
    _cmd_sphere,
    _cmd_plane,
    _plane_state,
    _cmd_cube,
    _poly3_points,
    _poly_register,
    _number_arg,
    _vector3_arg,
    _infinite_cone_state,
    _cmd_cone,
    _cmd_cylinder,
    _cmd_prism,
    _cmd_pyramid,
    _cmd_tetrahedron,
    _cmd_octahedron,
    _cmd_hexahedron,
    _cmd_icosahedron,
    _cmd_dodecahedron,
)

# 统计图命令（P2 结构拆分（P2 结构拆分）
from .charts import (  # noqa: F401
    _cmd_piechart,
    _cmd_histogram,
    _cmd_boxplot,
    _cmd_barchart,
    _cmd_linechart,
    _cmd_scatterplot,
    _cmd_dotplot,
    _cmd_barchart3d,
    _cmd_scatterplot3d,
    _cmd_surfacechart3d,
    _anon_list,
)
from .cmd_util import _NESTED_CALL_RE, _NESTED_MAX_DEPTH  # noqa: F401
from .elements import (
    EPSILON, Geo3D, GeoAngle, GeoArc, GeoBarChart, GeoBoolean, GeoChart2D, GeoCircle, GeoConic,
    GeoDotPlot, GeoLineChart, GeoScatterPlot,
    GeoBoxPlot, GeoComplex, GeoCurve, GeoError, GeoFunction, GeoImage, GeoImplicit, GeoInequality, GeoLine, GeoList,
    GeoLocus, GeoMatrix, GeoNumber, GeoPolar, GeoPoint, GeoPolygon, GeoPolyline,
    GeoPie, GeoRay, GeoResult, GeoSegment, GeoSumRect, GeoText, GeoVector,
)
from .parser import _split_commas, eval_number, parse_line

# 3D 几何算法已抽到 kernel/geometry3d.py（P2 结构拆分）；此处 re-export 保持调用方兼容
from .geometry3d import (  # noqa: F401
    _tag3d,
    _z_of,
    _has_z,
    _dist3,
    _solve2,
    _line_ends,
    _circle3d_basis,
    _ray_triangle,
    _frame_from_axis,
    _normalize_mesh,
    _newell_normal,
    _mesh_volume,
    _mesh_area,
    _solid_volume,
    _solid_area,
    _is_solid_el,
    _solid_planes,
    _clip_polyhedron,
    _ix_plane_plane,
    _ix_line_plane,
    _ix_line3d_plane,
    _ix_solid_plane,
    _ix_sphere_sphere,
    _ix_sphere_circle3d,
    _ix_circle3d_circle3d,
    _ix_circle3d_plane,
    _ix_circle3d_solid,
    _ix_sphere_solid,
    _ix_sphere_plane,
    _ix_solid_solid,
    _ix_solid_line,
    _ix_sphere_line,
    _poly_state,
)

# 立体构造数学已抽到 kernel/solids.py（P2 结构拆分）；re-export 保持调用方兼容
from .solids import _PHI as _solids_PHI  # noqa: F401
from .solids import (  # noqa: F401
    _sphere_check,
    _sphere_state,
    _sphere_state_r,
    _sphere_state_fixed,
    _cube_seg_pts,
    _cube_from_edge,
    _cube_from_poly,
    _cube_build,
    _cube_state,
    _cube_state2,
    _ortho_frame,
    _with_analytic,
    _cone_mesh_axis,
    _cone_from_circle_state,
    _cone_apex_center_radius_state,
    _cone_state,
    _cyl_mesh_axis,
    _cylinder_from_circle_state,
    _cylinder_centers_radius_state,
    _cylinder_state,
    _prism_state,
    _pyramid_state,
    _tetrahedron_state,
    _regular_polyhedron,
    _octahedron_state,
    _hexahedron_state,
    _icosahedron_state,
    _dodecahedron_state,
)

# 二维几何基元与变换已抽到 kernel/geo2d.py（P2 结构拆分）；re-export 保持调用方兼容
from .geo2d import (  # noqa: F401
    _linear,
    _line_through,
    _reflect_point_line,
    _reflect_point_point,
    _rotate,
    _line_state,
    _dilate_pt,
    _transform_fn,
    _reflect_lin,
    _reflect_lin_xy,
    _reflected_line,
    _reflected_point_line,
    _rotated_line,
    _fn_state,
    _conic_t,
    _dilated_line,
)

# 统计/拟合已抽到 kernel/stats.py（P2 结构拆分）；re-export 保持调用方兼容
from .stats import (  # noqa: F401
    _median,
    _mode,
    _variance,
    _fit_silent_fit,
    _fitline_state,
    _barchart_state,
    _fitsphere_state,
    _fitplane_state,
)
from .stats import (  # noqa: F401
    _bars3d_mesh, _dotplot_state, _linechart_state, _scatter3d_mesh, _scatter_state,
    _surface3d_mesh,
)
from .stats import _REF_DOT, _REF_X  # noqa: F401
from .tolerance import EPSILON, TIGHT, COORD, ZERO_SQ, LOOSE, COARSE, NEGLIGIBLE, ROOT_TOL, OPT_XATOL, OPT_FATOL  # 统一数值容差（见 kernel/tolerance.py）


# 形如 "Circle[O,2]" / "Plane[A,B,C]" 的嵌套命令调用（不含赋值号）
# _NESTED_CALL_RE / _NESTED_MAX_DEPTH 已移至 kernel/cmd_util.py（此处 re-export）
# 嵌套命令最大层数（防御深层递归/自引用）


class _DetachedConstruction:
    """嵌套命令求值用的影子构造。

    依赖仍从父构造的 elements 查找，但新元素**不注册**（匿名辅助对象：
    不进对象列表 / 撤销快照 / 序列化），只作为依赖挂在父元素的 deps 上。
    父元素的 defn 保留用户原始写法（如 `k=Cone[Circle[O,2],3]`），
    因此撤销、.ggk/.ggb 往返重放时会重新求值出同样的匿名依赖。
    """

    def __init__(self, cons, depth: int) -> None:
        self._cons = cons
        self.elements = cons.elements       # 共享查找表（只读使用）
        self.created: List = []
        self._seq = 0
        self._nested_depth = depth

    def add(self, el):
        self.created.append(el)
        if not getattr(el, "free", False):
            el.compute()
        return el

    def auto_label(self, kind):
        self._seq += 1
        return "_n%d_%s" % (self._seq, kind)

    def _recompute(self, el):
        return self._cons._recompute(el)

    def get(self, label):
        return self._cons.get(label)

    def push_history(self):
        pass


def _eval_nested(cons, text: str):
    """就地求值一个嵌套命令调用，返回匿名辅助元素（不注册）。"""
    t = text.strip()
    m = _NESTED_CALL_RE.match(t)
    if m is None:
        raise GeoError("无法解析嵌套命令: " + t)
    depth = _nested_depth(cons)
    if depth >= _NESTED_MAX_DEPTH:
        raise GeoError("嵌套命令层数过深（最多 %d 层）: %s" % (_NESTED_MAX_DEPTH, t))
    name, inner = m.group(1), m.group(2)
    lname = name.lower()
    lname = ALIASES.get(lname, lname)          # 中文别名归一化
    handler = COMMANDS.get(lname)
    if handler is None:
        raise GeoError("嵌套命令中不支持命令 " + name + "：请先用一条独立语句创建该对象，再用其标签作为参数")
    args = [a for a in _split_commas(inner) if a != ""]
    shadow = _DetachedConstruction(cons, depth + 1)
    label = shadow.auto_label(_label_kind(cons, lname, args))
    defn = label + "=" + t
    if lname in ("intersect", "extremum", "focus", "tangent"):
        created = handler(shadow, defn, args, None)
    else:
        created = handler(shadow, defn, args)
    els = created if isinstance(created, list) else [created]
    els = [e for e in els if e is not None]
    if not els:
        raise GeoError("嵌套命令未产生结果: " + t)
    res = els[0]
    if getattr(res, "error", None):
        raise GeoError("嵌套命令失败 " + t + "：" + str(res.error))
    return res


set_nested_evaluator(_eval_nested)   # 供 cmd_util._lookup 就地求值嵌套命令


# ---------------------------------------------------------------------------
# 解析辅助
# ---------------------------------------------------------------------------







def _number(cons, s: str):
    s = s.strip()
    el = _lookup(cons, s)
    if el is not None and el.kind in ("number", "angle"):
        return el
    raise GeoError(s + " 不是数值对象")












# ---------------------------------------------------------------------------
# 创建派生元素的公共闭包工厂
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 各命令实现（返回新建元素）
# ---------------------------------------------------------------------------

















































def _cmd_cov_ellipsoid(cons, defn, args):
    """CovarianceEllipsoid[点列表, 倍数?]：协方差椭球（特征向量为轴，半轴 = k√λ）。"""
    if len(args) not in (1, 2):
        raise GeoError("CovarianceEllipsoid 需要点列表[, 倍数]")
    L = _list_arg(cons, args[0])
    if L.itemkind not in ("point", "point3d"):
        raise GeoError("CovarianceEllipsoid 需要三维点列表")
    k = eval_number(cons, args[1]) if len(args) == 2 else 2.0
    return _mk(cons, Geo3D, "geo3d", defn, [L], lambda d: _cov_ellipsoid_state(d[0].items, k))


def _cov_ellipsoid_state(items, k):
    import numpy as np
    if len(items) < 2:
        raise GeoError("协方差椭球至少需要两个点")
    pts = np.array([[float(p[0]), float(p[1]), float(p[2] if len(p) > 2 else 0.0)] for p in items])
    ctr = pts.mean(axis=0)
    q = pts - ctr
    cov = (q.T @ q) / len(pts)
    w, v = np.linalg.eigh(cov)          # 升序：w[i] 对应 v[:,i]
    axes = [float(k) * math.sqrt(max(0.0, float(w[i]))) for i in range(3)]
    if max(axes) < EPSILON:
        raise GeoError("点云退化（方差为 0），无法构成椭球")
    n = 20
    verts, faces, edges = [], [], []
    for j in range(n + 1):
        phi = math.pi * j / n
        for i in range(n + 1):
            th = 2 * math.pi * i / n
            u = [math.sin(phi) * math.cos(th), math.sin(phi) * math.sin(th), math.cos(phi)]
            p = [float(ctr[t]) for t in range(3)]
            for a in range(3):
                coef = axes[a] * sum(u[b] * float(v[b, a]) for b in range(3))
                for t in range(3):
                    p[t] += coef * float(v[t, a])
            verts.append(p)

    def vid(i, j):
        return j * (n + 1) + i

    for j in range(n):
        for i in range(n):
            faces.append([vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)])
            edges.append([vid(i, j), vid(i + 1, j)])
            edges.append([vid(i, j), vid(i, j + 1)])
    return schemas.surface(verts, faces, edges, n,
                           center=[float(c) for c in ctr], axes=axes)








# ---- 凸多面体半空间裁剪（体∩体） ----

















def _cmd_distance(cons, label, args):
    if len(args) != 2:
        raise GeoError("Distance 需要两个对象")
    o1 = _resolve(cons, args[0])
    o2 = _resolve(cons, args[1])
    if o1.kind == "point" and o2.kind == "point":
        return _mk(cons, GeoNumber, "number", label, [o1, o2],
                   lambda d: {"value": _dist3(d[0], d[1]) if _has_z(d[0], d[1])
                              else _dist((d[0].x, d[0].y), (d[1].x, d[1].y))})
    if o1.kind == "point" and o2.kind in ("line", "segment", "ray"):
        return _mk(cons, GeoNumber, "number", label, [o1, o2],
                   lambda d: {"value": _pt_linear_dist(d[0], d[1])})
    if o2.kind == "point" and o1.kind in ("line", "segment", "ray"):
        return _mk(cons, GeoNumber, "number", label, [o1, o2],
                   lambda d: {"value": _pt_linear_dist(d[1], d[0])})
    if o1.kind == "point" and o2.kind == "circle":
        return _mk(cons, GeoNumber, "number", label, [o1, o2],
                   lambda d: {"value": abs(_dist((d[0].x, d[0].y), (d[1].cx, d[1].cy)) - d[1].r)})
    if o2.kind == "point" and o1.kind == "circle":
        return _mk(cons, GeoNumber, "number", label, [o1, o2],
                   lambda d: {"value": abs(_dist((d[1].x, d[1].y), (d[0].cx, d[0].cy)) - d[0].r)})
    raise GeoError("Distance 暂不支持 " + o1.kind + " 与 " + o2.kind)


def _pt_linear_dist(pt, lin) -> float:
    a, b, c = _linear(lin)
    return abs(a * pt.x + b * pt.y + c) / math.hypot(a, b)


def _cmd_slope(cons, label, args):
    lin = _resolve(cons, args[0], ("line", "segment", "ray"))
    return _mk(cons, GeoNumber, "number", label, [lin],
               lambda d: _slope_state(*_linear(d[0])))


def _slope_state(a, b, c):
    if abs(b) < EPSILON:
        raise GeoError("直线垂直于 x 轴，斜率不存在")
    return {"value": -a / b}


def _cmd_angle(cons, label, args):
    if len(args) == 2:
        # Angle[u, v]：两向量/点 的夹角（0°..180°），弧画在原点
        u = _vec2_arg(cons, args[0])
        v = _vec2_arg(cons, args[1])
        objs = _vec_arg_objs(cons, args)
        return _mk(cons, GeoAngle, "angle", label, objs,
                   lambda d: _angle2_state(d, args, objs, (u, v)))

    if len(args) != 3:
        raise GeoError("Angle 需要三个点 A,B,C（∠ABC）或两个向量")
    a = _point_arg(cons, args[0])
    b = _point_arg(cons, args[1])
    c = _point_arg(cons, args[2])
    return _mk(cons, GeoAngle, "angle", label, [a, b, c],
               lambda d: _angle_state(d[0], d[1], d[2]))


def _angle2_state(d, texts, objs, frozen) -> Dict[str, float]:
    """两向量/点夹角状态（0..180°，弧以原点为中心）。frozen: 字面参数初值。"""
    def comp(txt, idx):
        txt = txt.strip()
        if txt.startswith("("):
            return frozen[idx]
        for i, o in enumerate(objs):
            if o.label == txt:
                o2 = d[i]
                return (o2.dx, o2.dy) if o2.kind == "vector" else (o2.x, o2.y)
        raise GeoError("Angle 参数未解析: " + txt)
    u = comp(texts[0], 0)
    v = comp(texts[1], 1)
    du = math.hypot(u[0], u[1])
    dv = math.hypot(v[0], v[1])
    if du < EPSILON or dv < EPSILON:
        raise GeoError("零向量无法求夹角")
    c = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (du * dv)))
    ang = math.degrees(math.acos(c))
    return {"value": ang, "rad": math.radians(ang), "cx": 0.0, "cy": 0.0,
            "ang1": math.atan2(u[1], u[0]), "ang2": math.atan2(v[1], v[0])}


def _angle_state(a, b, c) -> Dict[str, float]:
    ux, uy = a.x - b.x, a.y - b.y
    vx, vy = c.x - b.x, c.y - b.y
    cross = ux * vy - uy * vx
    dot = ux * vx + uy * vy
    ang = math.degrees(math.atan2(cross, dot))
    if ang < 0:
        ang += 360.0
    if ang > 180.0:
        ang = 360.0 - ang          # 无向角 0..180（初中直觉：∠ABC = 45° 而非 315°）
    # 三维点：值改用真三维夹角；弧的绘制字段仍按 xy 投影（3D 视图里弧为示意）
    if _has_z(a, b, c):
        uz, vz = _z_of(a) - _z_of(b), _z_of(c) - _z_of(b)
        nu = math.sqrt(ux * ux + uy * uy + uz * uz)
        nv = math.sqrt(vx * vx + vy * vy + vz * vz)
        if nu > EPSILON and nv > EPSILON:
            cs = max(-1.0, min(1.0, (ux * vx + uy * vy + uz * vz) / (nu * nv)))
            ang = math.degrees(math.acos(cs))   # 0..180
    rad = math.radians(ang)
    return {"value": ang, "rad": rad,
            "cx": b.x, "cy": b.y,
            "ang1": math.atan2(uy, ux), "ang2": math.atan2(vy, vx)}


# (旧 _cmd_length 已被下方新版覆盖，已删除)


# ---------------------------------------------------------------------------
# 变换：Translate / Rotate / Reflect（每个目标类型一个闭包）
# ---------------------------------------------------------------------------













# ---------------------------------------------------------------------------
# 函数（SymPy 解析）
# ---------------------------------------------------------------------------

def _make_function(cons, label, body: str) -> GeoFunction:
    refs = _function_refs(cons, body)
    # 未定义变量 → 自动生成参数滑块（多个未知量 → 多个 slider，类似 GeoGebra）
    import sympy
    try:
        x = sympy.Symbol("x")
        expr0 = _parse_sympy(body, {"x": x}, cons)
        free = expr0.free_symbols - {x}
        for s in sorted(free, key=str):
            sname = str(s)
            if sname in cons.elements:
                continue  # 已是已有对象（数值/函数）→ 作引用
            if not re.match(r"^[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*$", sname):
                raise GeoError("函数未知变量名非法: " + sname)
            sl = GeoNumber(sname, sname + "=Slider[-5,5,0.1]", 0.0)
            sl.min, sl.max, sl.step = -5.0, 5.0, 0.1
            cons.add(sl)
            refs.append(sl)
    except GeoError:
        raise
    except Exception:
        pass  # 解析失败交给 configure 报错
    el = GeoFunction(label, label + "(x)=" + body)
    try:
        el.configure(cons, body, refs)
    except GeoError:
        raise
    except Exception:
        raise GeoError("无法解析函数表达式: " + body)
    return cons.add(el)


def _function_refs(cons, body: str) -> List:
    """找出函数体中引用的已有元素（数值/函数），用于建立依赖。"""
    import re
    refs = []
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", body):
        if tok in ("x", "e", "pi", "sin", "cos", "tan", "exp", "log", "ln", "sqrt", "abs",
                   "log10", "asin", "acos", "atan", "sinh", "cosh", "tanh", "floor", "ceil", "round", "sign"):
            continue
        el = cons.elements.get(tok)
        if el is not None and el.kind in ("number", "function") and el not in refs:
            refs.append(el)
    return refs


# ---------------------------------------------------------------------------
# 数值求根（函数求交 / Root / Extremum 共用）
# ---------------------------------------------------------------------------



def _fn_line_diff(f, lin, x):
    """f(x) - line_y(x) 的符号表达式；垂直线返回 None（单独处理）。"""
    a, b, c = _linear(lin)
    if abs(b) < EPSILON:
        return None
    return f.expr - (-(a * x + c) / b)


# ---------------------------------------------------------------------------
# P1 命令：Derivative / Integral / Tangent / Root / Extremum
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# 初中几何补充：垂线/垂足/角平分线/度量/内心/重心/滑动条
# ---------------------------------------------------------------------------























def _polygon_perimeter(poly) -> float:
    xs, ys = poly.xs, poly.ys
    n = len(xs)
    if n < 2:
        return 0.0
    return sum(math.hypot(xs[i] - xs[(i + 1) % n], ys[i] - ys[(i + 1) % n]) for i in range(n))






def _section_perimeter(el) -> float:
    """截面多边形周长（闭合环边长之和）。"""
    pts = (getattr(el, "data", None) or {}).get("pts") or []
    if len(pts) < 2:
        raise GeoError("截面顶点不足，周长无定义")
    return sum(math.dist(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))


def _cmd_perimeter(cons, defn, args):
    obj = _resolve(cons, args[0])
    if obj.kind == "polygon":
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": _polygon_perimeter(d[0])})
    if obj.kind == "circle":
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": 2 * math.pi * d[0].r})
    if obj.kind == "geo3d" and getattr(obj, "objtype", "") == "section":
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": _section_perimeter(d[0])})
    raise GeoError("Perimeter 需要 多边形/圆 或 3D 截面")


def _cmd_circumference(cons, defn, args):
    obj = _resolve(cons, args[0], ("circle", "conic"))
    if obj.kind == "circle":
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": 2 * math.pi * d[0].r})
    if obj.ctype in ("ellipse", "circle"):
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": _ellipse_circumference(d[0].semi_a, d[0].semi_b or d[0].semi_a)})
    raise GeoError("Circumference 需要 圆或椭圆")


def _ellipse_circumference(a, b):
    if abs(a - b) < EPSILON:
        return 2 * math.pi * a
    h = ((a - b) / (a + b)) ** 2
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))  # Ramanujan 近似














def _tri_points(cons, args):
    """心类/半周长公共参数解析：接受 [poly]（三角形多边形）或 [A, B, C] 三点 → 三个顶点元素。"""
    if len(args) == 1:
        poly = _resolve(cons, args[0], ("polygon",))
        pts = [p for p in poly.deps if p.kind == "point"]
        if len(pts) != 3:
            raise GeoError("需要三角形（三个顶点的多边形）")
        return pts
    if len(args) == 3:
        return [_point_arg(cons, a) for a in args]
    raise GeoError("需要 三角形/多边形 或 三个顶点")


def _cmd_orthocenter(cons, defn, args):
    pts = _tri_points(cons, args)
    return _mk(cons, GeoPoint, "point", defn, pts, lambda d: _orthocenter_state(d[0], d[1], d[2]))


def _orthocenter_state(a, b, c):
    """垂心：过 A 垂直 BC 与过 B 垂直 AC 两条高线的交点。"""
    d1x, d1y = c.x - b.x, c.y - b.y   # BC 方向
    d2x, d2y = c.x - a.x, c.y - a.y   # AC 方向
    det = d1x * d2y - d2x * d1y
    if abs(det) < EPSILON:
        raise GeoError("退化三角形")
    e1 = d1x * a.x + d1y * a.y        # 高 A：d1·(X-A)=0 → d1x·x + d1y·y = e1
    e2 = d2x * b.x + d2y * b.y        # 高 B：d2·(X-B)=0
    hx = (e1 * d2y - e2 * d1y) / det
    hy = (d1x * e2 - d2x * e1) / det
    return {"x": hx, "y": hy}


def _cmd_circumcenter(cons, defn, args):
    pts = _tri_points(cons, args)
    return _mk(cons, GeoPoint, "point", defn, pts, lambda d: _circumcenter_state(d[0], d[1], d[2]))


def _circumcenter_state(a, b, c):
    res = _circumcircle((a.x, a.y), (b.x, b.y), (c.x, c.y))
    if res is None:
        raise GeoError("三点共线，无外心")
    return {"x": res[0], "y": res[1]}


def _cmd_excenter(cons, defn, args):
    pts = _tri_points(cons, args)
    return _mk(cons, GeoPoint, "point", defn, pts, lambda d: _excenter_state(d[0], d[1], d[2]))


def _excenter_state(a, b, c):
    """与顶点 A 相对的旁心（旁切圆圆心）：
    (-a·A + b·B + c·C) / (-a + b + c)，a=|BC|, b=|CA|, c=|AB|。"""
    aa = _dist((b.x, b.y), (c.x, c.y))
    bb = _dist((c.x, c.y), (a.x, a.y))
    cc = _dist((a.x, a.y), (b.x, b.y))
    denom = -aa + bb + cc
    if abs(denom) < EPSILON:
        raise GeoError("退化三角形")
    return {"x": (-aa * a.x + bb * b.x + cc * c.x) / denom,
            "y": (-aa * a.y + bb * b.y + cc * c.y) / denom}


def _cmd_radius(cons, defn, args):
    el = _resolve(cons, args[0])
    if el.kind == "circle":
        return _mk(cons, GeoNumber, "number", defn, [el], lambda d: {"value": d[0].r})
    if el.kind == "arc":
        return _mk(cons, GeoNumber, "number", defn, [el], lambda d: {"value": d[0].r})
    raise GeoError("Radius 需要 圆 或 圆弧")


def _cmd_diameter(cons, defn, args):
    el = _resolve(cons, args[0])
    if el.kind == "circle":
        return _mk(cons, GeoNumber, "number", defn, [el], lambda d: {"value": 2 * d[0].r})
    if el.kind == "arc":
        return _mk(cons, GeoNumber, "number", defn, [el], lambda d: {"value": 2 * d[0].r})
    raise GeoError("Diameter 需要 圆 或 圆弧")


def _cmd_semiperimeter(cons, defn, args):
    if len(args) == 3:
        pts = [_point_arg(cons, a) for a in args]
        return _mk(cons, GeoNumber, "number", defn, pts,
                   lambda d: {"value": (_dist((d[0].x, d[0].y), (d[1].x, d[1].y))
                                        + _dist((d[1].x, d[1].y), (d[2].x, d[2].y))
                                        + _dist((d[2].x, d[2].y), (d[0].x, d[0].y))) / 2.0})
    obj = _resolve(cons, args[0], ("polygon",))
    return _mk(cons, GeoNumber, "number", defn, [obj],
               lambda d: {"value": _polygon_perimeter(d[0]) / 2.0})



# ---------------------------------------------------------------------------
# 教学批次2：随机 / 排列组合 / 向量点积 / 相关系数
# ---------------------------------------------------------------------------

def _cmd_randombetween(cons, defn, args):
    """RandomBetween[min, max]：闭区间随机整数（创建时落定；Randomize 重滚）。"""
    if len(args) != 2:
        raise GeoError("RandomBetween 需要 最小值, 最大值")
    lo = int(eval_number(cons, args[0]))
    hi = int(eval_number(cons, args[1]))
    if hi < lo:
        raise GeoError("最大值必须不小于最小值")
    import random
    el = GeoNumber(label_of(defn), defn, float(random.randint(lo, hi)))
    el._random_src = (lo, hi)
    return cons.add(el)


def _cmd_randomize(cons, defn, args):
    """Randomize[A]：把 RandomBetween 数值重新随机（抛硬币/掷骰模拟）。"""
    if len(args) != 1:
        raise GeoError("Randomize 需要一个对象")
    from . import memo as _memo
    _memo.clear()          # 随机结果不参与计算记忆，清空以确保依赖它的对象重新生成
    el = _resolve(cons, args[0], ("number",))
    src = getattr(el, "_random_src", None)
    if not src:
        raise GeoError(el.label + " 不是 RandomBetween 创建的数值（无随机源）")
    import random
    el.value = float(random.randint(src[0], src[1]))
    el.defn = el.label + "=RandomBetween[" + str(src[0]) + "," + str(src[1]) + "]"
    cons._recompute(el)
    return []






def _vec2_arg(cons, s):
    """向量参数：向量/点对象 或 (a,b) 元组 → (dx, dy)。"""
    s = s.strip()
    if s.startswith("("):
        parts = _tuple_parts(s)
        return eval_number(cons, parts[0]), eval_number(cons, parts[1])
    el = _lookup(cons, s)
    if el is None:
        raise GeoError("找不到对象 " + s)
    if el.kind == "vector":
        return el.dx, el.dy
    if el.kind == "point":
        return el.x, el.y
    raise GeoError("Dot/Angle 需要 向量或点: " + s)


def _vec_arg_objs(cons, args):
    """Dot/Angle 两参数中引用的对象（向量/点）→ 依赖列表。"""
    objs = []
    for a in args:
        s = a.strip()
        if not s.startswith("("):
            e = _lookup(cons, s)
            if e is not None and e.kind in ("vector", "point") and e not in objs:
                objs.append(e)
    return objs


def _cmd_dot(cons, defn, args):
    """Dot[u, v]：两向量/点（或元组）的点积。"""
    if len(args) != 2:
        raise GeoError("Dot 需要 两个向量或点")
    objs = _vec_arg_objs(cons, args)

    def fn(d):
        def comp(txt):
            txt = txt.strip()
            if txt.startswith("("):
                return _vec2_arg(cons, txt)
            for i, o in enumerate(objs):
                if o.label == txt:
                    o2 = d[i]
                    return (o2.dx, o2.dy) if o2.kind == "vector" else (o2.x, o2.y)
            raise GeoError("Dot 参数未解析: " + txt)
        u = comp(args[0])
        v = comp(args[1])
        return {"value": u[0] * v[0] + u[1] * v[1]}

    return _mk(cons, GeoNumber, "number", defn, objs, fn)


def _cmd_pmcc(cons, defn, args):
    """PMCC[点列表] 或 PMCC[列表x, 列表y]：线性相关系数 r。"""
    import numpy as np
    if len(args) == 1:
        L = _list_arg(cons, args[0])
        if L.itemkind != "point":
            raise GeoError("PMCC 需要点列表，如 PMCC[{(1,2),(2,3)}]")
        deps = [L]
        mode = "pts"
    elif len(args) == 2:
        L1 = _list_arg(cons, args[0])
        L2 = _list_arg(cons, args[1])
        if L1.itemkind != "number" or L2.itemkind != "number":
            raise GeoError("PMCC 两个参数都需是数值列表")
        deps = [L1, L2]
        mode = "xy"
    else:
        raise GeoError("PMCC 需要点列表 或 两个数值列表")

    def fn(d):
        if mode == "pts":
            xs = np.array([float(p[0]) for p in d[0].items], dtype=float)
            ys = np.array([float(p[1]) for p in d[0].items], dtype=float)
        else:
            xs = np.array(list(d[0].items), dtype=float)
            ys = np.array(list(d[1].items), dtype=float)
        if len(xs) < 2 or len(xs) != len(ys):
            raise GeoError("至少需要两个配对数据")
        r = np.corrcoef(xs, ys)[0, 1]
        if not np.isfinite(r):
            raise GeoError("数据线性相关无法计算（常数数据）")
        return {"value": float(r)}

    return _mk(cons, GeoNumber, "number", defn, deps, fn)



# ---------------------------------------------------------------------------
# 教学批次3：黎曼和（LeftSum/RightSum/MidpointSum/LowerSum/UpperSum/RectangleSum/TrapezoidalSum）与饼图
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# 教学批次5：迭代（数列递推）与数论（GCD/LCM/素数/因数）
# ---------------------------------------------------------------------------

def _iter_setup(cons, args):
    """Iteration/IterationList 公共解析 → (f, x0, deps, n_el, n_fix)。"""
    if len(args) != 3:
        raise GeoError("需要 函数, 初值, 次数")
    f = _resolve(cons, args[0], ("function",))
    x0 = eval_number(cons, args[1])
    deps = [f]
    n_el = None
    n_txt = args[2].strip()
    if n_txt in cons.elements and cons.elements[n_txt].kind == "number":
        n_el = cons.elements[n_txt]
        deps.append(n_el)
        n_fix = 1
    else:
        n_fix = int(eval_number(cons, n_txt))
        if n_fix < 0 or n_fix > 100000:
            raise GeoError("迭代次数需在 0..100000")
    return f, x0, deps, n_el, n_fix


def _cmd_iteration(cons, defn, args):
    """Iteration[函数, 初值, 次数]：迭代末值（数列第 n 项）。"""
    f, x0, deps, n_el, n_fix = _iter_setup(cons, args)

    def fn(d):
        n = int(round(d[1].value)) if n_el is not None else n_fix
        n = max(0, min(100000, n))
        v = x0
        for _ in range(n):
            nv = f._eval1(v)
            if nv is None:
                raise GeoError("迭代在 x=" + str(v) + " 处发散")
            v = nv
        return {"value": float(v)}

    return _mk(cons, GeoNumber, "number", defn, deps, fn)


def _cmd_iterationlist(cons, defn, args):
    """IterationList[函数, 初值, 次数]：含初值的迭代序列（递推数列可视化）。"""
    f, x0, deps, n_el, n_fix = _iter_setup(cons, args)

    def fn(d):
        n = int(round(d[1].value)) if n_el is not None else n_fix
        n = max(0, min(100000, n))
        items = [x0]
        v = x0
        for _ in range(n):
            nv = f._eval1(v)
            if nv is None:
                raise GeoError("迭代在 x=" + str(v) + " 处发散")
            v = nv
            items.append(v)
        return {"items": items, "itemkind": "number"}

    el = GeoList(label_of(defn), defn, None, "number")
    el.free = False
    el.set_deps(deps, fn)
    el.compute()
    return cons.add(el)











# ---------------------------------------------------------------------------
# 复数（复平面）：z=3+4i；conj/re/im/abs/arg
# ---------------------------------------------------------------------------

_IMG_I_RE = None  # 占位


def _complex_build(cons, label, expr_text):
    import re as _re
    import sympy
    s = _re.sub(r"(?<=[0-9a-zA-Z_\])])i(?![A-Za-z_0-9])", "*I", expr_text)
    s = _re.sub(r"(?<![0-9a-zA-Z_])i(?![A-Za-z_0-9])", "I", s)
    tr = (sympy.parsing.sympy_parser.standard_transformations
          + (sympy.parsing.sympy_parser.implicit_multiplication_application,
             sympy.parsing.sympy_parser.convert_xor))
    e = sympy.parsing.sympy_parser.parse_expr(s, local_dict={"I": sympy.I}, transformations=tr)
    free = e.free_symbols - {sympy.I}
    if free:
        raise GeoError("复数表达式仅支持数值系数（如 3+4i、1-2i、i、-2.5i），出现未知符号: "
                       + ", ".join(sorted(str(v) for v in free)))
    rv, iv = e.as_real_imag()
    el = GeoComplex(label, label + "=" + expr_text, float(rv), float(iv))
    el.free = False
    return cons.add(el)




def _cmd_conj(cons, defn, args):
    if len(args) != 1:
        raise GeoError("conj 需要一个复数")
    z = _resolve_complex(cons, args[0])
    return _mk(cons, GeoComplex, "complex", defn, [z],
               lambda d: {"re": d[0].re, "im": -d[0].im})


def _cmd_re(cons, defn, args):
    z = _resolve_complex(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [z], lambda d: {"value": d[0].re})


def _cmd_im(cons, defn, args):
    z = _resolve_complex(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [z], lambda d: {"value": d[0].im})




def _cmd_arg(cons, defn, args):
    z = _resolve_complex(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [z],
               lambda d: {"value": _arg_deg(d[0].re, d[0].im)})


def _arg_deg(a, b):
    import math as _m
    ang = _m.degrees(_m.atan2(b, a))
    if ang < 0:
        ang += 360.0
    return ang




# ---------------------------------------------------------------------------
# P2：参数曲线 / 极坐标 / 隐式方程（参考 Desmos 的函数式绘图能力）
# ---------------------------------------------------------------------------

def _curve_compute(xb: str, yb: str, pname: str, kind: str):
    """参数/极坐标/隐式曲线的 compute 闭包：把 number 依赖替换为当前值后解析表达式。"""
    import sympy

    def fn(deps):
        ld = {pname: sympy.Symbol(pname), "π": sympy.pi}
        for d in deps:
            if d.kind == "number":
                ld[d.label] = sympy.Float(d.value)
        tr = (sympy.parsing.sympy_parser.standard_transformations
              + (sympy.parsing.sympy_parser.implicit_multiplication_application,
                 sympy.parsing.sympy_parser.convert_xor))
        if kind == "parametric":
            xe = sympy.parsing.sympy_parser.parse_expr(xb, local_dict=ld, transformations=tr)
            ye = sympy.parsing.sympy_parser.parse_expr(yb, local_dict=ld, transformations=tr)
            free = (xe.free_symbols | ye.free_symbols) - {sympy.Symbol(pname)}
            if free:
                raise GeoError("参数曲线出现未知变量: " + ", ".join(sorted(str(s) for s in free)))
            return {"x_expr": xe, "y_expr": ye}
        if kind == "polar":
            re_ = sympy.parsing.sympy_parser.parse_expr(xb, local_dict=ld, transformations=tr)
            free = re_.free_symbols - {sympy.Symbol(pname)}
            if free:
                raise GeoError("极坐标出现未知变量: " + ", ".join(sorted(str(s) for s in free)))
            return {"r_expr": re_}
        fe = sympy.parsing.sympy_parser.parse_expr(xb, local_dict=ld, transformations=tr)
        free = fe.free_symbols - {sympy.Symbol("x"), sympy.Symbol("y")}
        if free:
            raise GeoError("隐式方程出现未知变量: " + ", ".join(sorted(str(s) for s in free)))
        return {"f_expr": fe}

    return fn


def _cmd_parametric(cons, defn, args):
    """Parametric[x(t), y(t), t, tmin, tmax]（t 可省略，默认 t）。"""
    if len(args) == 5:
        xb, yb, pname, a, b = args
    elif len(args) == 4:
        xb, yb, a, b = args
        pname = "t"
    else:
        raise GeoError("Parametric 需要 x(t), y(t), 起点, 终点（可选第 3 参数指定参数名）")
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", pname):
        raise GeoError("非法参数名: " + pname)
    el = GeoCurve(label_of(defn), defn, xb, yb, pname,
                  eval_number(cons, a), eval_number(cons, b))
    el.set_deps(_num_deps(cons, defn), _curve_compute(xb, yb, pname, "parametric"))
    return cons.add(el)


def _cmd_polar(cons, defn, args):
    """Polar[r(θ)] 或 Polar[r, theta]，θ ∈ [0, 2π]。"""
    if len(args) == 2:
        rb, pname = args
    elif len(args) == 1:
        rb, pname = args[0], "theta"
    else:
        raise GeoError("Polar 需要 r(θ)，如 Polar[2*cos(theta)]")
    rb = rb.replace("θ", "theta")
    pname = pname.replace("θ", "theta")
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", pname):
        raise GeoError("非法参数名: " + pname)
    el = GeoPolar(label_of(defn), defn, rb, pname)
    el.set_deps(_num_deps(cons, defn), _curve_compute(rb, "", pname, "polar"))
    return cons.add(el)


def _cmd_implicit(cons, defn, args):
    """Implicit[F(x,y)=0]：等式或函数式，marching squares 渲染。"""
    if len(args) != 1:
        raise GeoError("Implicit 需要含 x, y 的方程，如 Implicit[x^2+y^2=9]")
    body = args[0]
    if "=" in body:
        lhs, rhs = body.split("=", 1)
        body = "(" + lhs + ")-(" + rhs + ")"
    el = GeoImplicit(label_of(defn), defn, body)
    el.set_deps(_num_deps(cons, defn), _curve_compute(body, "", "x", "implicit"))
    return cons.add(el)

# ---------------------------------------------------------------------------
# P3：不等式 / 列表 / 统计 / 圆锥曲线 / 3D
# ---------------------------------------------------------------------------

def _make_ineq_y(cons, label, op, body):
    import sympy
    x = sympy.Symbol("x")
    expr = _parse_sympy(body, {"x": x}, cons)
    free = expr.free_symbols - {x}
    if free:
        raise GeoError("不等式出现未知变量: " + ", ".join(sorted(str(s) for s in free)))
    el = GeoInequality(label, label + ": y " + op + " " + body)
    el.form = "y"
    el.expr = expr
    el.xsym = x
    el.ysym = None
    el.yside = 1 if op in (">", ">=") else -1
    el.strict = op not in (">=", "<=")
    el.free = False
    return cons.add(el)


def _make_ineq_general(cons, label, op, lhs, rhs):
    import sympy
    x = sympy.Symbol("x")
    y = sympy.Symbol("y")
    le = _parse_sympy(lhs, {"x": x, "y": y}, cons)
    re = _parse_sympy(rhs, {"x": x, "y": y}, cons)
    if op in ("<", "<="):
        expr = le - re
    else:
        expr = re - le
    free = expr.free_symbols - {x, y}
    if free:
        raise GeoError("不等式出现未知变量: " + ", ".join(sorted(str(s) for s in free)))
    el = GeoInequality(label, label + ": " + lhs + " " + op + " " + rhs)
    el.form = "general"
    el.expr = expr
    el.xsym = x
    el.ysym = y
    el.yside = 0
    el.strict = op not in (">=", "<=")
    el.free = False
    return cons.add(el)


def _list_defn(items, itemkind):
    if itemkind == "point":
        return "{" + ", ".join("(" + _fmt(a) + "," + _fmt(b) + ")" for a, b in items) + "}"
    if itemkind == "point3d":
        return "{" + ", ".join("(" + _fmt(a) + "," + _fmt(b) + "," + _fmt(c) + ")" for a, b, c in items) + "}"
    return "{" + ", ".join(_fmt(v) for v in items) + "}"


















def _cmd_length(cons, defn, args):
    el = _resolve(cons, args[0])
    if el.kind == "segment":
        return _mk(cons, GeoNumber, "number", defn, [el],
                   lambda d: {"value": _dist((d[0].x1, d[0].y1), (d[0].x2, d[0].y2))})
    if el.kind == "list":
        return _mk(cons, GeoNumber, "number", defn, [el], lambda d: {"value": float(len(d[0].items))})
    raise GeoError("Length 需要线段或列表")






def _cmd_fitpoly(cons, defn, args):
    L = _list_arg(cons, args[0])
    if L.itemkind != "point":
        raise GeoError("FitPoly 需要点列表")
    n = int(eval_number(cons, args[1])) if len(args) >= 2 else 2
    el = GeoFunction(label_of(defn), defn)
    el.free = False

    def fn(d):
        import numpy as np
        import sympy
        xs = np.array([p[0] for p in d[0].items])
        ys = np.array([p[1] for p in d[0].items])
        if len(xs) < n + 1:
            raise GeoError("点的数量不足")
        coeffs = np.polyfit(xs, ys, n)
        x = sympy.Symbol("x")
        poly = sum(float(c) * x ** (n - i) for i, c in enumerate(coeffs))
        return {"expr": sympy.expand(poly), "xsym": x, "body": "", "_lamb": None}
    el.set_deps([L], fn)
    return cons.add(el)


# ---- 圆锥曲线 ----



def _mk_conic(cons, cls, defn, deps, fn):
    """创建圆锥曲线：闭包返回 (coeffs, ctype, canonical) 元组。"""
    el = GeoConic(label_of(defn), defn)
    el.free = False

    def compute(deps):
        st = fn(deps)
        el.a, el.b, el.c, el.d, el.e, el.f = st["coeffs"]
        el.ctype = st["ctype"]
        el.cx, el.cy = st.get("cx", 0.0), st.get("cy", 0.0)
        el.semi_a, el.semi_b = st.get("semi_a", 0.0), st.get("semi_b", 0.0)
        el.angle = st.get("angle", 0.0)
        el.focus = st.get("focus")
        el.directrix = st.get("directrix")
        return {}   # 闭包自行写状态，返回空 state
    el.set_deps(deps, compute)
    return cons.add(el)


def _conic_from_canonical(pts5):
    """由规范参数生成 5 点 → 一般系数。"""
    from .geom_util import conic_from_five_points
    coeffs = conic_from_five_points(pts5)
    if coeffs is None:
        raise GeoError("圆锥曲线退化，无法确定")
    return coeffs


def _cmd_ellipse(cons, defn, args):
    if len(args) != 3:
        raise GeoError("Ellipse 需要 焦点A、焦点B、过点C")
    f1 = _point_arg(cons, args[0])
    f2 = _point_arg(cons, args[1])
    p = _point_arg(cons, args[2])

    def fn(d):
        a0, b0, c0 = d[0], d[1], d[2]
        fc = _dist((a0.x, a0.y), (b0.x, b0.y)) / 2.0
        sma = (_dist((a0.x, a0.y), (c0.x, c0.y)) + _dist((b0.x, b0.y), (c0.x, c0.y))) / 2.0
        if sma <= fc:
            raise GeoError("椭圆不存在（2a ≤ 焦距）")
        smb = math.sqrt(sma * sma - fc * fc)
        cx, cy = (a0.x + b0.x) / 2, (a0.y + b0.y) / 2
        ang = math.atan2(b0.y - a0.y, b0.x - a0.x)
        pts5 = []
        for t in (0.0, math.pi / 2, math.pi, 1.5 * math.pi, math.pi / 4):
            xl, yl = sma * math.cos(t), smb * math.sin(t)
            pts5.append((cx + xl * math.cos(ang) - yl * math.sin(ang),
                         cy + xl * math.sin(ang) + yl * math.cos(ang)))
        return {"coeffs": _conic_from_canonical(pts5), "ctype": "ellipse",
                "cx": cx, "cy": cy, "semi_a": sma, "semi_b": smb, "angle": ang}
    return _mk_conic(cons, GeoConic, defn, [f1, f2, p], fn)


def _cmd_hyperbola(cons, defn, args):
    if len(args) != 3:
        raise GeoError("Hyperbola 需要 焦点A、焦点B、过点C")
    f1 = _point_arg(cons, args[0])
    f2 = _point_arg(cons, args[1])
    p = _point_arg(cons, args[2])

    def fn(d):
        a0, b0, c0 = d[0], d[1], d[2]
        fc = _dist((a0.x, a0.y), (b0.x, b0.y)) / 2.0
        d1 = _dist((a0.x, a0.y), (c0.x, c0.y))
        d2 = _dist((b0.x, b0.y), (c0.x, c0.y))
        sma = abs(d1 - d2) / 2.0
        if sma <= 0 or sma >= fc:
            raise GeoError("双曲线不存在（2a ≥ 2c 或退化）")
        smb = math.sqrt(fc * fc - sma * sma)
        cx, cy = (a0.x + b0.x) / 2, (a0.y + b0.y) / 2
        ang = math.atan2(b0.y - a0.y, b0.x - a0.x)
        pts5 = []
        for t in (-1.6, -0.7, 0.7, 1.6, 0.0):
            xl, yl = sma * math.cosh(t), smb * math.sinh(t)
            pts5.append((cx + xl * math.cos(ang) - yl * math.sin(ang),
                         cy + xl * math.sin(ang) + yl * math.cos(ang)))
        return {"coeffs": _conic_from_canonical(pts5), "ctype": "hyperbola",
                "cx": cx, "cy": cy, "semi_a": sma, "semi_b": smb, "angle": ang}
    return _mk_conic(cons, GeoConic, defn, [f1, f2, p], fn)


def _cmd_parabola(cons, defn, args):
    if len(args) != 2:
        raise GeoError("Parabola 需要 焦点F 和 准线直线")
    f = _point_arg(cons, args[0])
    g = _resolve(cons, args[1], ("line", "segment", "ray"))

    def fn(d):
        foc, lin = d[0], d[1]
        a, b, c = _linear(lin)
        denom = a * a + b * b
        if denom < EPSILON:
            raise GeoError("准线退化")
        # 焦点到准线的垂足
        t = -(a * foc.x + b * foc.y + c) / denom
        hx, hy = foc.x + a * t, foc.y + b * t
        # 顶点 = 焦点与垂足中点
        vx, vy = (foc.x + hx) / 2, (foc.y + hy) / 2
        dx, dy = foc.x - hx, foc.y - hy
        p_len = math.hypot(dx, dy) / 2.0
        if p_len < EPSILON:
            raise GeoError("焦点在准线上")
        ux, uy = dx / (2 * p_len), dy / (2 * p_len)   # 指向焦点
        vx2, vy2 = -uy, ux
        pts5 = []
        for t_ in (-5.0, -2.5, 0.0, 2.5, 5.0):
            xl, yl = t_, t_ * t_ / (4 * p_len)
            pts5.append((vx + xl * vx2 + yl * ux, vy + xl * vy2 + yl * uy))
        return {"coeffs": _conic_from_canonical(pts5), "ctype": "parabola",
                "cx": vx, "cy": vy, "semi_a": p_len, "semi_b": 0.0, "angle": math.atan2(uy, ux),
                "focus": (foc.x, foc.y), "directrix": (a, b, c)}
    return _mk_conic(cons, GeoConic, defn, [f, g], fn)


def _cmd_conic5(cons, defn, args):
    if len(args) != 5:
        raise GeoError("Conic 需要五个点")
    pts = [_point_arg(cons, a) for a in args]
    from .geom_util import conic_from_five_points

    def fn(d):
        coords = [(p.x, p.y) for p in d]
        coeffs = conic_from_five_points(coords)
        if coeffs is None:
            raise GeoError("五点退化，无法确定圆锥曲线")
        from .geom_util import conic_classify, conic_canonical
        ctype = conic_classify(*coeffs)
        st = {"coeffs": coeffs, "ctype": ctype}
        if ctype in ("ellipse", "circle", "hyperbola"):
            can = conic_canonical(coeffs)
            if can is not None:
                cx, cy, sa, sb, ang, ct = can
                st["ctype"] = ct
                st["cx"], st["cy"] = cx, cy
                st["semi_a"], st["semi_b"] = sa, sb
                st["angle"] = ang
        # 抛物线 / 退化 / 无法参数化：保留 ctype=parabola 时前端用 p=semi_a；
        # 无法给出规范参数则退回 general，由 marching squares 画线。
        if st["ctype"] == "parabola":
            st["semi_a"] = 1.0
            st["angle"] = 0.0
            st["cx"] = st["cy"] = 0.0
            st["ctype"] = "general"
        return st
    return _mk_conic(cons, GeoConic, defn, pts, fn)


def _cmd_focus(cons, defn, args, idx=None):
    conic = _resolve(cons, args[0], ("conic", "circle"))

    def foci_of(el):
        if el.kind == "circle":
            return [(el.cx, el.cy)]
        if el.kind == "conic":
            if el.ctype in ("ellipse", "hyperbola"):
                c = math.sqrt(abs(el.semi_a * el.semi_a - el.semi_b * el.semi_b))
                ca, sa = math.cos(el.angle), math.sin(el.angle)
                return [(el.cx + c * ca, el.cy + c * sa), (el.cx - c * ca, el.cy - c * sa)]
            if el.ctype == "parabola" and el.focus:
                return [tuple(el.focus)]
        raise GeoError("该圆锥曲线没有焦点")

    def build(i):
        el = GeoPoint("", defn)
        el.free = False
        el._i = i

        def compute(deps):
            fl = foci_of(deps[0])
            if el._i >= len(fl):
                raise GeoError("焦点数量不足")
            return {"x": fl[el._i][0], "y": fl[el._i][1]}
        el.set_deps([conic], compute)
        return el

    all_foci = foci_of(conic)
    if idx is not None:
        el = build(idx)
        el.label = label_of(defn)
        el.defn = defn + "#" + str(idx)
        return cons.add(el)
    if len(args) > 1 and args[1].strip():
        raise GeoError("Focus 只接受圆锥曲线")
    created = []
    for i in range(len(all_foci)):
        li = label_of(defn) if i == 0 else label_of(defn) + str(i)
        el = build(i)
        el.label = li
        el.defn = li + "=" + _cmd_of(defn) + "#" + str(i)
        created.append(cons.add(el))
    return created












# ---- 3D ----

























# ---------------------------------------------------------------------------
# 3D 多面体：圆锥/圆柱/棱柱/棱锥/正四面体/正八面体/正二十面体/正十二面体
# 统一数据模型：{verts: [[x,y,z]...], faces: [[idx...]...], edges: [[i,j]...]}
# ---------------------------------------------------------------------------









# ---- 立体体积 / 表面积（网格散度定理 + 解析优先）----













# _PHI 已随立体构造数学移至 kernel/solids.py（此处 re-export 兼容）
_PHI = _solids_PHI










# ---------------------------------------------------------------------------
# P4：定理证明 / 序列 / 回归 / 脚本
# ---------------------------------------------------------------------------

# 与 construction.DEFAULT_VIEW 一致（此处避免循环导入而本地定义）
# _PRED_VIEW 已随图元/谓词命令移至 kernel/primitives.py（此处 re-export）
















def _cmd_areconcyclic(cons, defn, args):
    return _prove_cmd(cons, defn, args, "concyclic", 4)


def _cmd_arecongruent(cons, defn, args):
    return _prove_cmd(cons, defn, args, "congruent", 2)


def _cmd_areconcurrent(cons, defn, args):
    return _prove_cmd(cons, defn, args, "concurrent", 3)


def _cmd_prove(cons, defn, args):
    """Prove[b]：对 Are* 生成的布尔元素重新证明并生成新元素。"""
    if len(args) != 1:
        raise GeoError("Prove 需要一个布尔命题")
    el = _resolve(cons, args[0])
    if el.kind != "boolean" or not getattr(el, "_prove_args", None):
        raise GeoError("Prove 的参数必须是 AreParallel 等命题")
    kind, labels = el._prove_args
    from .prover import SymbolicGeo
    sg = SymbolicGeo(cons)
    res = sg.prove(kind, labels)
    new_el = GeoBoolean(label_of(defn), defn)
    new_el.free = False
    new_el.value = res.value
    new_el.detail = res.detail
    return cons.add(new_el)


def _fit_cmd(cons, defn, args, kind):
    L = _list_arg(cons, args[0])
    if L.itemkind != "point":
        raise GeoError("拟合需要点列表")
    el = GeoFunction(label_of(defn), defn)
    el.free = False

    def fn(d):
        import numpy as np
        import sympy
        pts = d[0].items
        xs = np.array([p[0] for p in pts])
        ys = np.array([p[1] for p in pts])
        x = sympy.Symbol("x")
        if kind == "exp":
            m = (ys > 0)
            k, c = np.polyfit(xs[m], np.log(ys[m]), 1)
            expr = sympy.exp(c) * sympy.exp(k * x)
        elif kind == "log":
            m = (xs > 0)
            a, b = np.polyfit(np.log(xs[m]), ys[m], 1)
            expr = a * sympy.log(x) + b
        elif kind == "pow":
            m = (xs > 0) & (ys > 0)
            k, c = np.polyfit(np.log(xs[m]), np.log(ys[m]), 1)
            expr = sympy.exp(c) * x ** k
        elif kind == "sin":
            from scipy.optimize import curve_fit
            def model(xv, a, b, c, d):
                return a * np.sin(b * xv + c) + d
            p0 = [(ys.max() - ys.min()) / 2, 2 * np.pi / max(xs.max() - xs.min(), COORD), 0, ys.mean()]
            popt, _ = _fit_silent_fit(model, xs, ys, p0=p0, maxfev=20000)
            a, b, c, d = popt
            expr = a * sympy.sin(b * x + c) + d
        else:
            raise GeoError("未知拟合类型")
        return {"expr": sympy.expand(expr), "xsym": x, "body": "", "_lamb": None}
    el.set_deps([L], fn)
    return cons.add(el)


def _cmd_fitexp(cons, defn, args):
    return _fit_cmd(cons, defn, args, "exp")


def _cmd_fitlog(cons, defn, args):
    return _fit_cmd(cons, defn, args, "log")


def _cmd_fitpow(cons, defn, args):
    return _fit_cmd(cons, defn, args, "pow")


def _cmd_fitsin(cons, defn, args):
    return _fit_cmd(cons, defn, args, "sin")






# ---------------------------------------------------------------------------
# 变换辅助：函数变换 / 圆锥曲线变换 / Dilate 命令
# ---------------------------------------------------------------------------































# ---------------------------------------------------------------------------
# 第二优先级：分布 / 直方图 / 文本 / 圆上点 / 轨迹
# ---------------------------------------------------------------------------





















# ---------------------------------------------------------------------------
# 三维统计图（网格对象，走既有 polyhedron 渲染管线）
# ---------------------------------------------------------------------------



























def _cmd_locus(cons, defn, args):
    """Locus[Q, P]：P 为圆上点（PointOnCircle），Q 依赖 P → 轨迹。"""
    if len(args) != 2:
        raise GeoError("Locus 需要 被驱动点 和 驱动点（圆上点）")
    q = _resolve(cons, args[0], ("point",))
    p = _resolve(cons, args[1], ("point",))
    el = GeoLocus(label_of(defn), defn)
    el.free = False
    el.set_deps([q, p], lambda d: _locus_state(cons, d[0], d[1]))
    return cons.add(el)


def _locus_state(cons, q, p):
    """扫描 P 的路径参数，记录 Q 的位置序列。"""
    import numpy as np
    import re
    mpoc = re.match(r"^[A-Za-z_][A-Za-z0-9_]*=PointOnCircle\[([^,]+),([^\]]+)\]", p.defn.strip())
    mpop = re.match(r"^[A-Za-z_][A-Za-z0-9_]*=PointOnPath\[([^,]+),([^\]]+)\]", p.defn.strip())
    if mpoc:
        plab, tlab = mpoc.group(1).strip(), mpoc.group(2).strip()
        lo, hi = 0.0, 2 * math.pi
    elif mpop:
        plab, tlab = mpop.group(1).strip(), mpop.group(2).strip()
        lo, hi = 0.0, 1.0
    else:
        raise GeoError("Locus 需要驱动点 P 是 PointOnCircle 或 PointOnPath 上的动点")
    c = cons.elements.get(plab)
    th = cons.elements.get(tlab)
    if c is None or th is None or th.kind != "number":
        raise GeoError("无法解析驱动点路径")
    # Q 的传递上游（含 P），按深度排序
    upstream = set()
    stack = [q]
    while stack:
        e = stack.pop()
        if e in upstream:
            continue
        upstream.add(e)
        stack.extend(e.deps)
    ordered = sorted(upstream, key=lambda e: e.depth)
    orig = th.value
    pts = []
    try:
        for t in np.linspace(lo, hi, 200):
            th.value = float(t)
            for e in ordered:
                if not e.free:
                    e.compute()
            if q.error is None:
                pts.append([q.x, q.y])
    finally:
        th.value = orig
        for e in ordered:
            if not e.free:
                e.compute()
    return {"pts": pts}


# ---------------------------------------------------------------------------
# 第三优先级：矩阵
# ---------------------------------------------------------------------------

def _parse_matrix_arg(cons, s: str):
    """解析 {{1,2},{3,4}} → numpy 数组。"""
    import numpy as np
    from .parser import _split_brace, tokenize
    s = s.strip()
    if not (s.startswith("{") and s.endswith("}")):
        raise GeoError("矩阵需要 {{...},{...}} 形式")
    rows = _split_brace(tokenize(s))
    data = []
    for row in rows:
        if not (row.startswith("{") and row.endswith("}")):
            raise GeoError("矩阵行需要 {...} 形式: " + row)
        vals = [eval_number(cons, v) for v in _split_brace(tokenize(row))]
        data.append(vals)
    if not data:
        raise GeoError("空矩阵")
    n = len(data[0])
    for r in data:
        if len(r) != n:
            raise GeoError("矩阵各行长度必须一致")
    return np.array(data, dtype=float)


def _cmd_matrix(cons, defn, args):
    if len(args) != 1:
        raise GeoError("Matrix 需要 {{1,2},{3,4}} 形式")
    data = _parse_matrix_arg(cons, args[0])
    el = GeoMatrix(label_of(defn), defn)
    el.free = False
    el.data = data
    return cons.add(el)


def _cmd_det(cons, defn, args):
    m = _resolve(cons, args[0], ("matrix",))
    return _mk(cons, GeoNumber, "number", defn, [m], lambda d: _det_state(d[0]))


def _det_state(m):
    import numpy as np
    if m.data is None:
        raise GeoError("空矩阵")
    if m.data.shape[0] != m.data.shape[1]:
        raise GeoError("行列式需要方阵")
    return {"value": float(np.linalg.det(m.data))}


def _cmd_transpose(cons, defn, args):
    m = _resolve(cons, args[0], ("matrix",))
    return _mk(cons, GeoMatrix, "matrix", defn, [m], lambda d: _transpose_state(d[0]))


def _transpose_state(m):
    if m.data is None:
        raise GeoError("空矩阵")
    return {"data": m.data.T}


def _cmd_inverse(cons, defn, args):
    m = _resolve(cons, args[0], ("matrix",))
    return _mk(cons, GeoMatrix, "matrix", defn, [m], lambda d: _inverse_state(d[0]))


def _inverse_state(m):
    import numpy as np
    if m.data is None:
        raise GeoError("空矩阵")
    if m.data.shape[0] != m.data.shape[1]:
        raise GeoError("逆矩阵需要方阵")
    try:
        inv = np.linalg.inv(m.data)
    except np.linalg.LinAlgError:
        raise GeoError("矩阵不可逆（奇异）")
    return {"data": inv}


# ---------------------------------------------------------------------------
# 第三优先级：圆弧/扇形 / 解不等式 / 对象锁定
# ---------------------------------------------------------------------------











def _sol_lo(part: str) -> float:
    """排序键：区间下界。"""
    import re
    m = re.match(r"[\[(]\s*(-?[0-9.]+)", part)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return -1e18   # -∞ 排最前




# ---------------------------------------------------------------------------
# 编辑命令：Delete / Rename / Redefine / SetColor / SetVisible
# ---------------------------------------------------------------------------















def _cmd_setwire(cons, defn, args):
    """SetWire[label, true/false]：3D 物体线框显示模式。"""
    if len(args) != 2:
        raise GeoError("SetWire 需要 对象 和 true/false")
    el = _resolve(cons, args[0])
    if el.kind != "geo3d":
        raise GeoError("线框模式仅适用于 3D 物体")
    v = args[1].strip().lower()
    if v in ("true", "1", "yes", "线框"):
        el.wire = True
    elif v in ("false", "0", "no", "实体"):
        el.wire = False
    else:
        raise GeoError("SetWire 需要 true 或 false")
    return []


# ---------------------------------------------------------------------------
# 自定义宏（Macro）
# ---------------------------------------------------------------------------

def _cmd_macrocreate(cons, defn, args):
    """MacroCreate[名称, {输入}, {输出}]：从当前构造创建宏。"""
    if len(args) != 3:
        raise GeoError("MacroCreate 需要 名称、输入对象集合、输出对象集合")
    from . import macro
    name = args[0].strip()
    inputs = [s.strip() for s in args[1].strip("{}").split(",") if s.strip()]
    outputs = [s.strip() for s in args[2].strip("{}").split(",") if s.strip()]
    try:
        m = macro.create_macro(cons, name, inputs, outputs)
    except ValueError as e:
        raise GeoError(str(e))
    return [cons.get(outputs[0])] if outputs and outputs[0] in cons.elements else []




def _cmd_macrolist(cons, defn, args):
    from . import macro
    ms = macro.list_macros(cons)
    if not ms:
        raise GeoError("暂无宏")
    return []


# ---------------------------------------------------------------------------
# 中文命令别名（GGB 中文版风格）
# ---------------------------------------------------------------------------

# 规范显示名（命令解析大小写不敏感；帮助面板/补全用它展示与插入）
DISPLAY_NAMES = {
    "surfacepoint": "SurfacePoint", "surfaceproject": "SurfaceProject",
    "surfaceisoline": "SurfaceIsoline", "surfaceparam": "SurfaceParam",
    "implicitsurface": "ImplicitSurface", "covarianceellipsoid": "CovarianceEllipsoid",
    "boundingbox": "BoundingBox", "convexhull": "ConvexHull", "fitplane": "FitPlane",
    "fitsphere": "FitSphere", "fitline": "FitLine", "fitpoly": "FitPoly", "fitexpr": "FitExpr",
    "pointoncircle": "PointOnCircle", "randompointin": "RandomPointIn",
    "anglebisector": "AngleBisector", "barchart": "BarChart", "piechart": "PieChart",
    "linechart": "LineChart", "scatterplot": "ScatterPlot", "dotplot": "DotPlot",
    "barchart3d": "BarChart3D", "scatterplot3d": "ScatterPlot3D",
    "surfacechart3d": "SurfaceChart3D",
    "boxplot": "BoxPlot", "histogram": "Histogram", "circumcircle": "CircumCircle",
    "rigidpolygon": "RigidPolygon", "randombetween": "RandomBetween",
    "areparallel": "AreParallel", "areperpendicular": "ArePerpendicular",
    "arecollinear": "AreCollinear", "areconcyclic": "AreConcyclic",
    "arecongruent": "AreCongruent", "areconcurrent": "AreConcurrent",
    "leftsum": "LeftSum", "rightsum": "RightSum", "midpointsum": "MidpointSum",
    "lowersum": "LowerSum", "uppersum": "UpperSum", "trapezoidalsum": "TrapezoidalSum",
    "rectanglesum": "RectangleSum", "iterationlist": "IterationList",
    "factorslist": "FactorsList", "partialfractions": "PartialFractions",
    "solveode": "SolveODE", "nsolve": "NSolve", "setcoords": "SetCoords",
    "setvalue": "SetValue", "setcolor": "SetColor", "setvisible": "SetVisible",
    "setlocked": "SetLocked", "setwire": "SetWire", "isfinite": "IsFinite",
    "isprime": "IsPrime", "divisors": "Divisors", "sequence": "Sequence",
    "normaldist": "NormalDist", "surfacearea": "SurfaceArea", "centroid": "Centroid",
    # 多词命令的规范写法（其余单词命令由首字母大写自动生成）
    "circumcenter": "CircumCenter", "orthocenter": "OrthoCenter",
    "correlationcoefficient": "CorrelationCoefficient",
    "macrocreate": "MacroCreate", "macrodelete": "MacroDelete", "macrolist": "MacroList",
    "perpendicularline": "PerpendicularLine", "perpendicularbisector": "PerpendicularBisector",
    "pointonpath": "PointOnPath", "semicircle": "SemiCircle", "semiperimeter": "SemiPerimeter",
    "solveineq": "SolveIneq", "regularpolygon": "RegularPolygon",
}


ALIASES = {
    "中点": "midpoint", "直线": "line", "线段": "segment", "射线": "ray",
    "圆": "circle", "多边形": "polygon", "刚性多边形": "rigidpolygon", "刚体多边形": "rigidpolygon", "折线": "polyline", "向量": "vector",
    "交点": "intersect", "距离": "distance", "斜率": "slope", "角度": "angle",
    "长度": "length", "平移": "translate", "旋转": "rotate", "镜像": "reflect",
    "对称": "reflect", "位似": "dilate", "缩放": "dilate", "椭圆": "ellipse",
    "反演": "invert",
    "图片": "image", "插入图片": "image", "图像": "image",
    "双曲线": "hyperbola", "抛物线": "parabola", "圆锥曲线": "conic",
    "焦点": "focus", "切线": "tangent", "导数": "derivative", "积分": "integral",
    "求根": "root", "极值": "extremum",
    "平行线": "perpendicularline", "垂线": "perpendicularline", "垂足": "foot",
    "角平分线": "anglebisector", "中垂线": "perpendicularbisector", "正多边形": "regularpolygon",
    "面积": "area", "体积": "volume", "表面积": "area", "周长": "perimeter",
    "曲面": "surface", "拟合平面": "fitplane", "平面拟合": "fitplane",
    "网格": "mesh", "导入网格": "mesh",
    "参数曲面": "surfaceparam", "隐式曲面": "implicitsurface",
    "质心": "centroid", "拟合球": "fitsphere", "球拟合": "fitsphere",
    "包围盒": "boundingbox", "点云包围盒": "boundingbox", "协方差": "covariance", "协方差矩阵": "covariance",
    "协方差椭球": "covarianceellipsoid", "椭球": "covarianceellipsoid", "参数线": "surfaceisoline",
    "凸包": "convexhull", "曲面取点": "surfacepoint", "曲面投影": "surfaceproject",
    "内切圆": "incircle", "内心": "incenter", "重心": "centroid",
    "滑动条": "slider", "文本": "text", "轨迹": "locus", "圆上点": "pointoncircle", "动点": "pointonpath",
    "删除": "delete", "重命名": "rename", "重定义": "redefine",
    "颜色": "setcolor", "显示": "setvisible", "隐藏": "setvisible",
    "线框": "setwire", "实体": "setwire",
    "平行": "areparallel", "垂直": "areperpendicular", "共线": "arecollinear",
    "共圆": "areconcyclic", "相等": "arecongruent", "共点": "areconcurrent",
    "证明": "prove", "序列": "sequence", "平均": "mean", "中位数": "median",
    "众数": "mode", "方差": "variance", "标准差": "stdev", "求和": "sum",
    "最大值": "max", "最小值": "min", "排序": "sort", "直线拟合": "fitline",
    "多项式拟合": "fitpoly", "指数拟合": "fitexp", "对数拟合": "fitlog",
    "幂拟合": "fitpow", "正弦拟合": "fitsin", "直方图": "barchart",
    "正态": "normal", "正态分布": "normaldist", "正态函数": "normaldist",
    "坐标": "setcoords", "赋值": "setvalue",
    "随机整数": "randombetween", "随机化": "randomize", "重新随机": "randomize",
    "排列": "npr", "组合": "ncr", "点积": "dot", "相关系数": "pmcc",
    "左端点矩形和": "leftsum", "右端点矩形和": "rightsum", "中点矩形和": "midpointsum",
    "下和": "lowersum", "上和": "uppersum", "梯形和": "trapezoidalsum", "矩形和": "rectanglesum",
    "饼图": "piechart", "扇形统计图": "piechart",
    "折线图": "linechart", "折线": "linechart",
    "散点图": "scatterplot", "散布图": "scatterplot",
    "点图": "dotplot", "点阵图": "dotplot",
    "三维柱状图": "barchart3d", "三维条形图": "barchart3d",
    "三维散点图": "scatterplot3d",
    "三维曲面图": "surfacechart3d", "高度场": "surfacechart3d",
    "分组直方图": "histogram", "直方图分组": "histogram",
    "下四分位数": "q1", "上四分位数": "q3", "四分位距": "iqr", "箱线图": "boxplot",
    "迭代": "iteration", "迭代表": "iterationlist", "迭代序列": "iterationlist",
    "最大公约数": "gcd", "最小公倍数": "lcm", "素数": "isprime", "质数": "isprime",
    "因数": "divisors", "质因数": "factorslist",
    "随机点": "randompointin",
    "共轭": "conj", "共轭复数": "conj", "实部": "re", "虚部": "im",
    "辐角": "arg", "幅角": "arg",
    "解不等式": "solveineq", "圆弧": "arc", "扇形": "sector", "半圆": "semicircle",
    "外接圆": "circle", "圆周长": "circumference", "椭圆周长": "circumference",
    "垂心": "orthocenter", "外心": "circumcenter", "旁心": "excenter",
    "半径": "radius", "直径": "diameter", "半周长": "semiperimeter",
    "矩阵": "matrix", "行列式": "det", "转置": "transpose", "逆矩阵": "inverse",
    "锁定": "setlocked",
    "参数曲线": "parametric", "极坐标": "polar", "隐式方程": "implicit", "隐式": "implicit",
    "拟合": "fitexpr", "回归": "fitexpr",
    "球": "sphere", "球面": "sphere", "平面": "plane", "立方体": "cube",
    "圆锥": "cone", "圆柱": "cylinder", "棱柱": "prism", "三棱柱": "prism",
    "棱锥": "pyramid", "三棱锥": "pyramid", "正四面体": "tetrahedron",
    "正八面体": "octahedron", "正六面体": "hexahedron", "正方体": "hexahedron", "正二十面体": "icosahedron", "正十二面体": "dodecahedron",
}


# ---------------------------------------------------------------------------
# 结果类型提示（自动标签用）
# ---------------------------------------------------------------------------

RESULT_KINDS = {
    "circumcircle": "circle", "pointonpath": "point",
    "macrocreate": "result", "macrodelete": "result", "macrolist": "result",
        "midpoint": "point", "line": "line", "segment": "segment", "ray": "ray",
        "circle": "circle", "polygon": "polygon", "intersect": "point",
        "distance": "number", "slope": "number", "angle": "number",
        "length": "number", "translate": "point", "rotate": "point",
        "reflect": "point", "vector": "vector",
        "invert": "point",
        "image": "image",
        "derivative": "function", "integral": "function", "tangent": "line",
        "root": "point", "extremum": "point",
        "ellipse": "conic", "hyperbola": "conic", "parabola": "conic",
        "conic": "conic", "focus": "point",
        "sum": "number", "mean": "number", "median": "number", "mode": "number",
        "variance": "number", "stdev": "number", "min": "number", "max": "number",
        "length": "number", "sort": "list", "fitline": "line", "fitpoly": "function",
        "sphere": "geo3d", "plane": "geo3d", "cube": "geo3d",
        "surface": "geo3d", "fitplane": "geo3d", "mesh": "geo3d",
        "barchart3d": "geo3d", "scatterplot3d": "geo3d", "surfacechart3d": "geo3d",
        "linechart": "linechart", "scatterplot": "scatterplot", "dotplot": "dotplot",
        "surfaceparam": "geo3d", "implicitsurface": "geo3d",
        "centroid": "point", "fitsphere": "geo3d", "boundingbox": "geo3d", "covariance": "matrix",
        "covarianceellipsoid": "geo3d", "surfaceisoline": "geo3d",
        "convexhull": "geo3d", "surfacepoint": "point", "surfaceproject": "point",
        "cone": "geo3d", "cylinder": "geo3d", "prism": "geo3d", "pyramid": "geo3d",
        "tetrahedron": "geo3d", "octahedron": "geo3d", "hexahedron": "geo3d", "icosahedron": "geo3d", "dodecahedron": "geo3d",
        "parametric": "parametric", "polar": "polar", "implicit": "implicit",
        "fitexpr": "function",
        "perpendicularbisector": "line", "regularpolygon": "polygon",
"areparallel": "boolean", "areperpendicular": "boolean",
        "arecollinear": "boolean", "areconcyclic": "boolean",
        "arecongruent": "boolean", "areconcurrent": "boolean",
        "prove": "boolean", "sequence": "list",
        "fitexp": "function", "fitlog": "function", "fitpow": "function", "fitsin": "function",
        "setcoords": "number", "setvalue": "number",
        "delete": "point", "rename": "point", "redefine": "point",
        "setcolor": "point", "setvisible": "point", "setwire": "point",
        "polyline": "polyline", "dilate": "point",
        "perpendicularline": "line", "foot": "point", "anglebisector": "line",
        "area": "number", "volume": "number", "perimeter": "number", "circumference": "number",
        "incenter": "point", "incircle": "circle", "centroid": "point",
        "rigidpolygon": "polygon",
        "slider": "number", "angle": "angle",
        "normal": "number", "normaldist": "function", "barchart": "barchart",
        "text": "text", "pointoncircle": "point", "locus": "locus",
        "arc": "arc", "sector": "arc", "semicircle": "arc", "solveineq": "result",
        "setlocked": "point",
        "matrix": "matrix", "det": "number", "transpose": "matrix", "inverse": "matrix",
        "orthocenter": "point", "circumcenter": "point", "excenter": "point",
        "radius": "number", "diameter": "number", "semiperimeter": "number",
        "randombetween": "number", "randomize": "number",
        "npr": "number", "ncr": "number", "dot": "number",
        "pmcc": "number", "correlationcoefficient": "number",
        "leftsum": "sumrect", "rightsum": "sumrect", "midpointsum": "sumrect",
        "lowersum": "sumrect", "uppersum": "sumrect", "trapezoidalsum": "sumrect",
        "rectanglesum": "sumrect", "piechart": "piechart",
        "histogram": "barchart", "q1": "number", "q3": "number",
        "iqr": "number", "boxplot": "boxplot",
        "iteration": "number", "iterationlist": "list",
        "gcd": "number", "lcm": "number", "isprime": "boolean",
        "divisors": "list", "factorslist": "list",
        "randompointin": "point",
        "conj": "complex", "conjugate": "complex",
        "re": "number", "im": "number", "arg": "number", "abs": "number",
}


def _result_kind(name: str) -> str:
    """命令的默认结果类型（自动标签、类型提示用）。表见模块级 RESULT_KINDS（单一来源，可检测）。"""
    return RESULT_KINDS.get(name, "point")


def _label_kind(cons, lname: str, args) -> str:
    """自动标签用的「命名类型」。

    与结果类型基本一致，唯一例外是反演（Invert）：它可能产生点，也可能是圆/直线/
    曲线/多边形等图形。点反演仍按点命名（A,B,C…），其余反演像用独立的 inv1,inv2…
    前缀（小写开头，见 Construction.auto_label）——避免图形被命名成"下一个点"。
    """
    # 三维统计图：虽然结果类型是 geo3d，但用独立的命名前缀（bc3_/sc3_/sf3_）便于识别
    _chart3d = {"barchart3d": "chart3dbar", "scatterplot3d": "chart3dscatter",
                "surfacechart3d": "chart3dsurface"}
    if lname in _chart3d:
        return _chart3d[lname]
    if lname != "invert":
        return _result_kind(lname)
    try:
        el = cons.elements.get(args[0].strip()) if args else None
        if el is None and args:
            el = _lookup(cons, args[0])          # 支持嵌套命令参数
        if el is not None and getattr(el, "kind", "") == "point":
            return "point"
    except Exception:
        pass
    return "invert"


# ---------------------------------------------------------------------------
# 命令表与主入口
# ---------------------------------------------------------------------------

COMMANDS = {
    "midpoint": _cmd_midpoint,
    "line": _cmd_line,
    "segment": _cmd_segment,
    "ray": _cmd_ray,
    "circle": _cmd_circle, "circumcircle": _cmd_circle,
    "polygon": _cmd_polygon, "rigidpolygon": _cmd_rigidpolygon,
    "intersect": _cmd_intersect,
    "distance": _cmd_distance,
    "slope": _cmd_slope,
    "angle": _cmd_angle,
    "length": _cmd_length,
    "translate": _cmd_translate,
    "rotate": _cmd_rotate,
    "reflect": _cmd_reflect,
    "invert": _cmd_invert,
    "image": _cmd_image,
    "vector": _cmd_vector,
    "derivative": _cmd_derivative,
    "integral": _cmd_integral,
    "tangent": _cmd_tangent,
    "root": _cmd_root,
    "extremum": _cmd_extremum,
    "ellipse": _cmd_ellipse,
    "hyperbola": _cmd_hyperbola,
    "parabola": _cmd_parabola,
    "conic": _cmd_conic5,
    "focus": _cmd_focus,
    "sum": _cmd_sum,
    "mean": _cmd_mean,
    "median": _cmd_median,
    "mode": _cmd_mode,
    "variance": _cmd_variance,
    "stdev": _cmd_stdev,
    "min": _cmd_min,
    "max": _cmd_max,
    "sort": _cmd_sort,
    "fitline": _cmd_fitline,
    "fitpoly": _cmd_fitpoly,
    "fitexpr": _cmd_fitexpr,
    "sphere": _cmd_sphere, "surface": _cmd_surface, "fitplane": _cmd_fitplane,
    "mesh": _cmd_mesh, "surfaceparam": _cmd_surface_param, "implicitsurface": _cmd_implicit_surface,
    "linechart": _cmd_linechart, "scatterplot": _cmd_scatterplot, "dotplot": _cmd_dotplot,
    "barchart3d": _cmd_barchart3d, "scatterplot3d": _cmd_scatterplot3d,
    "surfacechart3d": _cmd_surfacechart3d,
    "fitsphere": _cmd_fitsphere, "boundingbox": _cmd_bbox, "covariance": _cmd_covariance,
    "covarianceellipsoid": _cmd_cov_ellipsoid, "surfaceisoline": _cmd_isoline,
    "convexhull": _cmd_convexhull, "surfacepoint": _cmd_surfacepoint,
    "surfaceproject": _cmd_surfaceproject,
    "plane": _cmd_plane,
    "cube": _cmd_cube,
    "cone": _cmd_cone,
    "cylinder": _cmd_cylinder,
    "prism": _cmd_prism,
    "pyramid": _cmd_pyramid,
    "tetrahedron": _cmd_tetrahedron,
    "octahedron": _cmd_octahedron,
    "hexahedron": _cmd_hexahedron,
    "icosahedron": _cmd_icosahedron,
    "dodecahedron": _cmd_dodecahedron,
    "areparallel": _cmd_areparallel,
    "areperpendicular": _cmd_areperpendicular,
    "arecollinear": _cmd_arecollinear,
    "areconcyclic": _cmd_areconcyclic,
    "arecongruent": _cmd_arecongruent,
    "areconcurrent": _cmd_areconcurrent,
    "prove": _cmd_prove,
    "sequence": _cmd_sequence,
    "fitexp": _cmd_fitexp,
    "fitlog": _cmd_fitlog,
    "fitpow": _cmd_fitpow,
    "fitsin": _cmd_fitsin,
    "setcoords": _cmd_setcoords,
    "setvalue": _cmd_setvalue,
    "delete": _cmd_delete,
    "rename": _cmd_rename,
    "redefine": _cmd_redefine,
    "setcolor": _cmd_setcolor,
    "setvisible": _cmd_setvisible,
    "setwire": _cmd_setwire,
    "macrocreate": _cmd_macrocreate,
    "macrodelete": _cmd_macrodelete,
    "macrolist": _cmd_macrolist,
    "polyline": _cmd_polyline,
    "dilate": _cmd_dilate,
    "perpendicularline": _cmd_perpendicularline,
    "foot": _cmd_foot,
    "anglebisector": _cmd_anglebisector,
    "perpendicularbisector": _cmd_perpbis,
    "regularpolygon": _cmd_regularpolygon,
    "area": _cmd_area,
    "volume": _cmd_volume,
    "perimeter": _cmd_perimeter,
    "circumference": _cmd_circumference,
    "incenter": _cmd_incenter,
    "incircle": _cmd_incircle,
    "centroid": _cmd_centroid,
    "slider": _cmd_slider,
    "parametric": _cmd_parametric,
    "polar": _cmd_polar,
    "implicit": _cmd_implicit,
    "normal": _cmd_normal,
    "normaldist": _cmd_normaldist,
    "barchart": _cmd_barchart,
    "text": _cmd_text,
    "pointoncircle": _cmd_pointoncircle,
    "pointonpath": _cmd_pointonpath,
    "locus": _cmd_locus,
    "arc": _cmd_arc,
    "sector": _cmd_sector,
    "semicircle": _cmd_semicircle,
    "solveineq": _cmd_solveineq,
    "setlocked": _cmd_setlocked,
    "matrix": _cmd_matrix,
    "det": _cmd_det,
    "transpose": _cmd_transpose,
    "inverse": _cmd_inverse,
    "orthocenter": _cmd_orthocenter, "circumcenter": _cmd_circumcenter, "excenter": _cmd_excenter,
    "radius": _cmd_radius, "diameter": _cmd_diameter, "semiperimeter": _cmd_semiperimeter,
    "randombetween": _cmd_randombetween, "randomize": _cmd_randomize,
    "npr": _cmd_npr, "ncr": _cmd_ncr, "dot": _cmd_dot, "pmcc": _cmd_pmcc,
    "correlationcoefficient": _cmd_pmcc,
    "leftsum": lambda c, d, a: _cmd_rectsum(c, d, a, "left"),
    "rightsum": lambda c, d, a: _cmd_rectsum(c, d, a, "right"),
    "midpointsum": lambda c, d, a: _cmd_rectsum(c, d, a, "mid"),
    "lowersum": lambda c, d, a: _cmd_rectsum(c, d, a, "lower"),
    "uppersum": lambda c, d, a: _cmd_rectsum(c, d, a, "upper"),
    "trapezoidalsum": lambda c, d, a: _cmd_rectsum(c, d, a, "trap"),
    "rectanglesum": lambda c, d, a: _cmd_rectsum(c, d, a, "rect"),
    "piechart": _cmd_piechart,
    "histogram": _cmd_histogram, "q1": _cmd_q1, "q3": _cmd_q3,
    "iqr": _cmd_iqr, "boxplot": _cmd_boxplot,
    "iteration": _cmd_iteration, "iterationlist": _cmd_iterationlist,
    "gcd": _cmd_gcd, "lcm": _cmd_lcm, "isprime": _cmd_isprime,
    "divisors": _cmd_divisors, "factorslist": _cmd_factorslist,
    "randompointin": _cmd_randpointin,
    "conj": _cmd_conj, "conjugate": _cmd_conj,
    "re": _cmd_re, "im": _cmd_im, "arg": _cmd_arg, "abs": _cmd_complex_abs,
}


def process_line(cons, line: str) -> List:
    # 多结果命令的单一元素重放：#idx 后缀
    idx = None
    m = re.match(r"^(.*)#(\d+)$", line.strip())
    if m:
        line = m.group(1)
        idx = int(m.group(2))
    fm = re.match(r"^y\s*~\s*(.+)$", line.strip())
    if fm:
        return _fit_expr(cons, line, line)
    label, kind, payload = parse_line(cons, line)

    if kind == "parametric":
        # 裸参数曲线：(cos(t), sin(t)) 或 f(t)=...（payload 含可选参数名）
        xb, yb = payload[0], payload[1]
        pname = payload[2] if len(payload) == 3 else "t"
        if label is None:
            label = cons.auto_label("parametric")
        defn = label + "=" + xb + "," + yb
        el = GeoCurve(label, defn, xb, yb, pname, -2 * math.pi, 2 * math.pi)
        el.set_deps(_num_deps(cons, defn), _curve_compute(xb, yb, pname, "parametric"))
        return [cons.add(el)]

    if kind == "polar":
        if label is None:
            label = cons.auto_label("polar")
        return [_cmd_polar(cons, label + "=Polar[" + payload[0] + "]", [payload[0]])]

    if kind == "implicit":
        if label is None:
            label = cons.auto_label("implicit")
        return [_cmd_implicit(cons, label + "=Implicit[" + payload[0] + "]", [payload[0]])]

    if kind == "list_index":
        lname, arg = payload
        L = _resolve(cons, lname, ("list",))
        if label is None:
            label = cons.auto_label("number")
        defn = label + "=" + lname + "(" + arg + ")"
        if L.itemkind in ("point", "point3d"):
            three = L.itemkind == "point3d"

            def fn(d):
                idx = int(eval_number(cons, arg)) - 1
                items = d[0].items
                if idx < 0 or idx >= len(items):
                    raise GeoError("索引越界: " + arg)
                p = items[idx]
                if three:
                    return {"x": p[0], "y": p[1], "z": p[2]}
                return {"x": p[0], "y": p[1]}
            return [_mk(cons, GeoPoint, "point", defn, [L], fn)]
        def fn(d):
            idx = int(eval_number(cons, arg)) - 1
            items = d[0].items
            if idx < 0 or idx >= len(items):
                raise GeoError("索引越界: " + arg)
            return {"value": items[idx]}
        return [_mk(cons, GeoNumber, "number", defn, [L], fn)]

    if kind == "point":
        if len(payload) == 3:
            x, y, z = payload
            if label is None:
                label = cons.auto_label("point")
            el = GeoPoint(label, label + "=(" + _fmt(x) + "," + _fmt(y) + "," + _fmt(z) + ")", x, y, True, z)
            return [cons.add(el)]
        x, y = payload
        if label is None:
            label = cons.auto_label("point")
        el = GeoPoint(label, label + "=(" + _fmt(x) + "," + _fmt(y) + ")", x, y)
        return [cons.add(el)]

    if kind == "ineq_y":
        if label is None:
            label = cons.auto_label("inequality")
        return [_make_ineq_y(cons, label, payload[0], payload[1])]

    if kind == "ineq_general":
        if label is None:
            label = cons.auto_label("inequality")
        op, lhs, rhs = payload
        return [_make_ineq_general(cons, label, op, lhs, rhs)]

    if kind == "list":
        items, itemkind = payload
        if label is None:
            label = cons.auto_label("list")
        el = GeoList(label, label + "=" + _list_defn(items, itemkind), items, itemkind)
        return [cons.add(el)]

    if kind == "vector":
        dx, dy = payload
        if label is None:
            label = cons.auto_label("vector")
        el = GeoVector(label, label + "=(" + _fmt(dx) + "," + _fmt(dy) + ")", dx, dy)
        return [cons.add(el)]

    if kind == "complex":
        if label is None:
            label = cons.auto_label("complex")
        return [_complex_build(cons, label, payload)]

    if kind == "number":
        if label is None:
            label = cons.auto_label("number")
        el = GeoNumber(label, label + "=" + _fmt(payload), payload)
        return [cons.add(el)]

    if kind == "value":
        # 函数求值：f(2) → 数值对象（依赖函数与参数）
        fname, arg = payload
        f = _resolve(cons, fname, ("function",))
        deps = [f]
        arg_el = cons.elements.get(arg.strip())
        if arg_el is not None and arg_el.kind in ("number", "angle"):
            deps.append(arg_el)
            fixed = None
        else:
            fixed = eval_number(cons, arg)
        if label is None:
            label = cons.auto_label("number")
        defn = label + "=" + fname + "(" + arg + ")"

        def fn(d):
            import sympy
            xv = fixed if fixed is not None else d[1].value
            try:
                v = float(sympy.N(d[0].expr.subs(d[0].xsym, xv)))
            except Exception:
                raise GeoError("函数在该点无法求值")
            return {"value": v}
        return [_mk(cons, GeoNumber, "number", defn, deps, fn)]

    if kind == "function":
        if label is None:
            label = cons.auto_label("function")
        return [_make_function(cons, label, payload)]

    # command
    name, args = payload
    lname = name.lower()
    lname = ALIASES.get(lname, lname)   # 中文别名归一化
    handler = COMMANDS.get(lname)
    if handler is None:
        # 自定义宏：宏名[实参...]（宏名区分大小写，用原始 name 查表）
        from . import macro
        if name in macro.registry(cons):
            created = macro.run_macro(cons, name, args, label)
            if created is None:
                raise GeoError("宏执行失败: " + name)
            return created
        raise GeoError("未知命令: " + name + "（支持: " + ", ".join(sorted(COMMANDS)) + "）")
    if label is None:
        # 自动标签：需要知道结果类型 → 预注册占位
        kind_hint = _label_kind(cons, lname, args)
        label = cons.auto_label(kind_hint)
        defn = label + "=" + line.strip()
    else:
        defn = line.strip()
    if idx is not None and not defn.rstrip().endswith("#" + str(idx)):
        defn += "#" + str(idx)   # 保留多结果序号，保证 .ggk/.ggb 往返取同一分支
    if lname in ("intersect", "extremum", "focus", "tangent"):
        created = handler(cons, defn, args, idx)
    else:
        created = handler(cons, defn, args)
    return created if isinstance(created, list) else [created]