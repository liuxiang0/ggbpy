"""二维图元命令（点/线/圆/多边形族，P2 结构拆分：从 commands.py 抽出）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .cmd_util import _label_of, _list_arg, _lookup, _mk, _point_arg, _resolve, _tuple_parts_any, label_of
from .stats import _fitline_state
from .geo2d import _line_state, _line_through, _linear
from .geometry3d import _is_solid_el, _ix_circle3d_circle3d, _ix_circle3d_plane, _ix_circle3d_solid, _ix_line3d_plane, _ix_line_plane, _ix_plane_plane, _ix_solid_line, _ix_solid_plane, _ix_solid_solid, _ix_sphere_circle3d, _ix_sphere_line, _ix_sphere_plane, _ix_sphere_solid, _ix_sphere_sphere
from .calculus import _cmd_of, _feval, _fmt, _roots_1d
from .elements import Geo3D, GeoArc, GeoBoolean, GeoCircle, GeoError, GeoLine, GeoNumber, GeoPoint, GeoPolygon, GeoPolyline, GeoRay, GeoSegment, GeoVector
from .tolerance import COORD, EPSILON, LOOSE, NEGLIGIBLE
from .parser import eval_number
from . import schemas

# 谓词判定用的固定视口（Are* 系列取元素几何状态）
_PRED_VIEW = (-10.0, 10.0, -10.0, 10.0)


__all__ = [
    "_PRED_VIEW",
    "_resolve_vector",
    "_resolve_vector3",
    "_intersect_lines",
    "_dist",
    "_line_circle",
    "_circle_circle",
    "_circumcircle",
    "_cmd_midpoint",
    "_cmd_line",
    "_line3d_state",
    "_parallel_state",
    "_cmd_segment",
    "_seg3d_state",
    "_cmd_ray",
    "_cmd_circle",
    "_circle_state",
    "_circ_state",
    "_cmd_polygon",
    "_cmd_rigidpolygon",
    "_cmd_polyline",
    "_cmd_intersect",
    "_cmd_isoline",
    "_isoline_state",
    "_ix_fn_fn",
    "_ix_fn_lin",
    "_ix_linlin",
    "_check_seg_ray",
    "_on_segment",
    "_ix_lincir",
    "_ix_circir",
    "_ix_conic_conic",
    "_cmd_vector",
    "_mk_free",
    "_line_y_x",
    "_cmd_tangent",
    "_tangent_state",
    "_cmd_perpendicularline",
    "_perp_state",
    "_cmd_foot",
    "_foot_state",
    "_cmd_perpbis",
    "_perpbis_state",
    "_perpbis_state2",
    "_cmd_regularpolygon",
    "_cmd_anglebisector",
    "_bisector_state",
    "_cmd_incenter",
    "_incenter_state",
    "_cmd_incircle",
    "_incircle_state",
    "_cmd_centroid",
    "_centroid_state",
    "_cmd_randpointin",
    "_randpointin_state",
    "_cmd_fitline",
    "_conic_coeffs",
    "_cmd_tangent_conic",
    "_tangent_conic_state_i",
    "_tangent_arc_state",
    "_tangent_conic_state",
    "_ix_lin_conic",
    "_pred_dir",
    "_pred_scale",
    "_numeric_verdict",
    "_prove_cmd",
    "_cmd_areparallel",
    "_cmd_areperpendicular",
    "_cmd_arecollinear",
    "_cmd_pointoncircle",
    "_cmd_pointonpath",
    "_pop_state",
    "_poc_state",
    "_cmd_arc",
    "_cmd_semicircle",
    "_semicircle_state",
    "_cmd_sector",
    "_arc_state",
]


def _resolve_vector(cons, s: str) -> Tuple[float, float]:
    """参数可以是向量元素或 (a,b) 元组，返回 (dx, dy)。"""
    dx, dy, _dz = _resolve_vector3(cons, s)
    return dx, dy

def _resolve_vector3(cons, s: str) -> Tuple[float, float, float]:
    """向量参数（支持三维）：(a,b) / (a,b,c) 元组或向量元素 → (dx, dy, dz)。

    向量元素本身只有 dx/dy 两个分量，其 dz 记为 0。
    """
    s = s.strip()
    if s.startswith("("):
        parts = _tuple_parts_any(s)
        vals = [eval_number(cons, p) for p in parts]
        if len(vals) == 2:
            return vals[0], vals[1], 0.0
        return vals[0], vals[1], vals[2]
    el = _lookup(cons, s)
    if el is None:
        raise GeoError("找不到对象 " + s)
    if el.kind == "vector":
        return el.dx, el.dy, 0.0
    if el.kind == "point":
        raise GeoError("需要向量或 (a,b) 元组，而不是点 " + s)
    raise GeoError("需要向量或 (a,b) 元组")

def _intersect_lines(a1, b1, c1, a2, b2, c2) -> Optional[Tuple[float, float]]:
    det = a1 * b2 - a2 * b1
    if abs(det) < EPSILON:
        return None
    x = (b1 * c2 - b2 * c1) / det
    y = (c1 * a2 - c2 * a1) / det
    return x, y

def _dist(p, q) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])

def _line_circle(line, cx, cy, r) -> List[Tuple[float, float]]:
    """直线 ax+by+c=0 与圆 (cx,cy,r) 的交点。"""
    a, b, c = line
    denom = a * a + b * b
    # 圆心到直线最近点
    t = -(a * cx + b * cy + c) / denom
    px, py = cx + a * t, cy + b * t
    d2 = r * r - ((px - cx) ** 2 + (py - cy) ** 2)
    if d2 < -COORD:
        return []
    # 弦半长（世界坐标）：沿单位方向 u 从垂足走到圆周的距离 = sqrt(d2)
    h = math.sqrt(max(0.0, d2))
    ux, uy = -b / math.sqrt(denom), a / math.sqrt(denom)
    return [(px + ux * h, py + uy * h), (px - ux * h, py - uy * h)]

def _circle_circle(c1x, c1y, r1, c2x, c2y, r2) -> List[Tuple[float, float]]:
    d = _dist((c1x, c1y), (c2x, c2y))
    if d < EPSILON:
        return []
    if d > r1 + r2 + COORD or d < abs(r1 - r2) - COORD:
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h2 = r1 * r1 - a * a
    h = math.sqrt(max(0.0, h2))
    px = c1x + a * (c2x - c1x) / d
    py = c1y + a * (c2y - c1y) / d
    if h < COORD:  # 内切/外切：只有一个交点
        return [(px, py)]
    ux = -(c2y - c1y) / d
    uy = (c2x - c1x) / d
    return [(px + ux * h, py + uy * h), (px - ux * h, py - uy * h)]

def _circumcircle(p1, p2, p3) -> Optional[Tuple[float, float, float]]:
    """三点外接圆 (cx, cy, r)；共线返回 None。"""
    (x1, y1), (x2, y2), (x3, y3) = p1, p2, p3
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < EPSILON:
        return None
    ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d
    uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d
    r = _dist((ux, uy), (x1, y1))
    return ux, uy, r

def _cmd_midpoint(cons, label, args):
    if len(args) == 1:
        el = _resolve(cons, args[0])
        if el.kind == "segment":
            return _mk(cons, GeoPoint, "point", label, [el],
                       lambda d: {"x": (d[0].x1 + d[0].x2) / 2, "y": (d[0].y1 + d[0].y2) / 2})
        if el.kind == "circle":
            return _mk(cons, GeoPoint, "point", label, [el],
                       lambda d: {"x": d[0].cx, "y": d[0].cy})
        raise GeoError("Midpoint 需要两个点、线段或圆")
    if len(args) == 2:
        p, q = _point_arg(cons, args[0]), _point_arg(cons, args[1])
        return _mk(cons, GeoPoint, "point", label, [p, q],
                   lambda d: {"x": (d[0].x + d[1].x) / 2, "y": (d[0].y + d[1].y) / 2})
    raise GeoError("Midpoint 参数数量错误")

def _cmd_line(cons, label, args):
    if len(args) == 2:
        # 过点作平行线：Line[A, g]（GGB 语法）
        e0 = _lookup(cons, args[0])
        e1 = _lookup(cons, args[1])
        if e0 is not None and e0.kind == "point" and e1 is not None and e1.kind in ("line", "segment", "ray"):
            return _mk(cons, GeoLine, "line", label, [e0, e1],
                       lambda d: _parallel_state(d[0], d[1]))
        if e1 is not None and e1.kind == "point" and e0 is not None and e0.kind in ("line", "segment", "ray"):
            return _mk(cons, GeoLine, "line", label, [e1, e0],
                       lambda d: _parallel_state(d[0], d[1]))
        p, q = _point_arg(cons, args[0]), _point_arg(cons, args[1])
        if p.z is not None or q.z is not None:
            # 3D 直线：过两点无限延伸（前端渲染为长线段）
            return _mk(cons, Geo3D, "geo3d", label, [p, q], lambda d: _line3d_state(d[0], d[1]))
        return _mk(cons, GeoLine, "line", label, [p, q],
                   lambda d: _line_state(*_line_through(d[0].x, d[0].y, d[1].x, d[1].y)))
    raise GeoError("Line 需要两个点 或 点+直线（平行线）")

def _line3d_state(p, q):
    """3D 直线：取两点方向，向两端延伸 ±R（可视范围）。"""
    px, py, pz = p.x, p.y, p.z or 0
    qx, qy, qz = q.x, q.y, q.z or 0
    dx, dy, dz = qx - px, qy - py, qz - pz
    ln = math.sqrt(dx * dx + dy * dy + dz * dz)
    if ln < EPSILON:
        raise GeoError("两点重合，无法确定直线")
    R = 25.0   # 直线延伸半长（世界单位）
    dx, dy, dz = dx / ln * R, dy / ln * R, dz / ln * R
    return schemas.line3d(px - dx, py - dy, pz - dz, px + dx, py + dy, pz + dz)

def _parallel_state(pt, lin):
    a, b, c = _linear(lin)
    return _line_state(a, b, -(a * pt.x + b * pt.y))

def _cmd_segment(cons, label, args):
    if len(args) == 2:
        p, q = _point_arg(cons, args[0]), _point_arg(cons, args[1])
        if p.z is not None or q.z is not None:
            return _mk(cons, Geo3D, "geo3d", label, [p, q], lambda d: _seg3d_state(d[0], d[1]))
        return _mk(cons, GeoSegment, "segment", label, [p, q],
                   lambda d: {"x1": d[0].x, "y1": d[0].y, "x2": d[1].x, "y2": d[1].y})
    raise GeoError("Segment 需要两个点")

def _seg3d_state(p, q):
    if math.sqrt((q.x - p.x) ** 2 + (q.y - p.y) ** 2 + ((q.z or 0) - (p.z or 0)) ** 2) < EPSILON:
        raise GeoError("线段两端点重合")
    return schemas.segment3d(p.x, p.y, p.z or 0, q.x, q.y, q.z or 0)

def _cmd_ray(cons, label, args):
    if len(args) == 2:
        p, q = _point_arg(cons, args[0]), _point_arg(cons, args[1])
        return _mk(cons, GeoRay, "ray", label, [p, q],
                   lambda d: {"ox": d[0].x, "oy": d[0].y, "dx": d[1].x - d[0].x, "dy": d[1].y - d[0].y})
    raise GeoError("Ray 需要两个点")

def _cmd_circle(cons, label, args):
    if len(args) == 1:
        # 外接圆：单个三角形/三点多边形 → 过三点外接圆（保留与顶点联动）
        poly = _resolve(cons, args[0], ("polygon",))
        pts = [p for p in poly.deps if p.kind == "point"]
        if len(pts) != 3:
            raise GeoError("外接圆需要三角形（三个顶点的多边形）")
        return _mk(cons, GeoCircle, "circle", label, pts,
                   lambda d: _circ_state(d[0].x, d[0].y, d[1].x, d[1].y, d[2].x, d[2].y))
    if len(args) == 2:
        c = _point_arg(cons, args[0])
        s = args[1].strip()
        el = _lookup(cons, s)
        if el is not None and el.kind == "point":
            return _mk(cons, GeoCircle, "circle", label, [c, el],
                       lambda d: {"cx": d[0].x, "cy": d[0].y, "r": _dist((d[0].x, d[0].y), (d[1].x, d[1].y))})
        if s.startswith("("):
            q = _point_arg(cons, s)
            return _mk(cons, GeoCircle, "circle", label, [c, q],
                       lambda d: {"cx": d[0].x, "cy": d[0].y, "r": _dist((d[0].x, d[0].y), (d[1].x, d[1].y))})
        if s in cons.elements and cons.elements[s].kind == "number":
            # 半径引用数值对象 → 依赖联动
            r = cons.elements[s]
            return _mk(cons, GeoCircle, "circle", label, [c, r],
                       lambda d: _circle_state(d[0].x, d[0].y, d[1].value))
        # 数值半径：字面量 / π·pi / 函数表达式（2*pi、sqrt(2) 等）
        try:
            r_val = eval_number(cons, s)
        except GeoError:
            raise GeoError("Circle 半径无效: " + s + "（需要 数字/常数表达式 或 数值对象）")
        return _mk(cons, GeoCircle, "circle", label, [c],
                   lambda d: _circle_state(d[0].x, d[0].y, r_val))
    if len(args) == 3:
        p1 = _resolve(cons, args[0], ("point",))
        p2 = _resolve(cons, args[1], ("point",))
        p3 = _resolve(cons, args[2], ("point",))
        return _mk(cons, GeoCircle, "circle", label, [p1, p2, p3],
                   lambda d: _circ_state(d[0].x, d[0].y, d[1].x, d[1].y, d[2].x, d[2].y))
    raise GeoError("Circle 需要 中心+点 / 中心+半径 / 三点")

def _circle_state(cx, cy, r):
    if r < COORD:
        raise GeoError("半径必须大于 0")
    return {"cx": cx, "cy": cy, "r": r}

def _circ_state(x1, y1, x2, y2, x3, y3):
    res = _circumcircle((x1, y1), (x2, y2), (x3, y3))
    if res is None:
        raise GeoError("三点共线，无法确定外接圆")
    cx, cy, r = res
    return {"cx": cx, "cy": cy, "r": r}

def _cmd_polygon(cons, label, args):
    if len(args) < 3:
        raise GeoError("Polygon 至少需要三个点")
    pts = [_point_arg(cons, a) for a in args]
    return _mk(cons, GeoPolygon, "polygon", label, pts,
               lambda d: {"xs": [p.x for p in d], "ys": [p.y for p in d]})

def _cmd_rigidpolygon(cons, label, args):
    """RigidPolygon[A,B,...]：刚性多边形（GeoGebra 语义）——
    - 只显示第一个与第二个顶点，其余顶点隐藏（不可见）；
    - 拖动第一个顶点 = 平移整块；拖动第二个顶点 = 绕第一个顶点旋转（保边/保形）；
    - 各边长度与夹角不变。顶点需为自由点（本命令新建的点自动隐藏）。"""
    if len(args) < 3:
        raise GeoError("RigidPolygon 至少需要三个点")
    pts = [_point_arg(cons, a) for a in args]
    for p in pts:
        if not (p.free and p.kind == "point"):
            raise GeoError("刚性多边形的顶点必须是自由点（" + p.label + " 是派生点）")
    # 刚性多边形只显示第一、第二顶点作为手柄：第 3+ 顶点隐藏（画布不可见；对象列表仍可恢复显隐）
    for p in pts[2:]:
        p.visible = False
    el = GeoPolygon(label_of(label), label)
    el.free = False
    el.rigid = True
    el.set_deps(pts, lambda d: {"xs": [p.x for p in d], "ys": [p.y for p in d]})
    return cons.add(el)

def _cmd_polyline(cons, defn, args):
    if len(args) < 2:
        raise GeoError("Polyline 至少需要两个点")
    pts = [_point_arg(cons, a) for a in args]
    return _mk(cons, GeoPolyline, "polyline", defn, pts,
               lambda d: {"xs": [p.x for p in d], "ys": [p.y for p in d]})

def _cmd_intersect(cons, defn, args, idx=None):
    if len(args) == 3:
        # 第 3 参数指定取第几个交点（1-based），如 Intersect[c,g,2]
        idx = int(eval_number(cons, args[2]))
        args = args[:2]
    elif len(args) != 2:
        raise GeoError("Intersect 需要两个对象（可选第 3 参数指定交点序号）")
    o1 = _resolve(cons, args[0])
    o2 = _resolve(cons, args[1])
    k1, k2 = o1.kind, o2.kind
    if k1 in ("line", "segment", "ray") and k2 in ("line", "segment", "ray"):
        return _mk(cons, GeoPoint, "point", defn, [o1, o2], lambda d: _ix_linlin(d[0], d[1]))
    if k1 in ("line", "segment", "ray") and k2 == "circle":
        return _mk(cons, GeoPoint, "point", defn, [o1, o2], lambda d: _ix_lincir(d[0], d[1], idx or 1))
    if k1 == "circle" and k2 in ("line", "segment", "ray"):
        return _mk(cons, GeoPoint, "point", defn, [o1, o2], lambda d: _ix_lincir(d[1], d[0], idx or 1))
    if k1 == "circle" and k2 == "circle":
        return _mk(cons, GeoPoint, "point", defn, [o1, o2], lambda d: _ix_circir(d[0], d[1], idx or 1))
    if k1 == "function" and k2 == "function":
        return _ix_fn_fn(cons, defn, o1, o2, idx)
    if k1 == "function" and k2 in ("line", "segment", "ray"):
        return _ix_fn_lin(cons, defn, o1, o2, idx)
    if k2 == "function" and k1 in ("line", "segment", "ray"):
        return _ix_fn_lin(cons, defn, o2, o1, idx)
    if k1 in ("line", "segment", "ray") and k2 in ("conic", "circle"):
        return _ix_lin_conic(cons, defn, o1, o2, idx)
    if k2 in ("line", "segment", "ray") and k1 in ("conic", "circle"):
        return _ix_lin_conic(cons, defn, o2, o1, idx)
    if k1 == "conic" and k2 in ("conic", "circle"):
        return _mk(cons, GeoPoint, "point", defn, [o1, o2], lambda d: _ix_conic_conic(d[0], d[1], idx or 1))
    if k2 == "conic" and k1 in ("conic", "circle"):
        return _mk(cons, GeoPoint, "point", defn, [o1, o2], lambda d: _ix_conic_conic(d[0], d[1], idx or 1))
    if k1 == "geo3d" and k2 == "geo3d":
        for _o in (o1, o2):
            if getattr(_o, "error", None):
                raise GeoError("求交参数无效：" + _o.label + "：" + str(_o.error))
        t1, t2 = o1.objtype, o2.objtype
        if t1 == "plane" and t2 == "plane":
            return _mk(cons, Geo3D, "geo3d", defn, [o1, o2], lambda d: _ix_plane_plane(d[0], d[1]))
        if (t1, t2) in (("segment", "plane"), ("plane", "segment")):
            seg, pl = (o1, o2) if t1 == "segment" else (o2, o1)
            return _mk(cons, GeoPoint, "point", defn, [seg, pl], lambda d: _ix_line_plane(d[0], d[1]))
        if (t1, t2) in (("line3d", "plane"), ("plane", "line3d")):
            lin, pl = (o1, o2) if t1 == "line3d" else (o2, o1)
            return _mk(cons, GeoPoint, "point", defn, [lin, pl], lambda d: _ix_line3d_plane(d[0], d[1]))
        if t1 == "plane" and _is_solid_el(o2):
            return _mk(cons, Geo3D, "geo3d", defn, [o1, o2], lambda d: _ix_solid_plane(d[1], d[0]))
        if t2 == "plane" and _is_solid_el(o1):
            return _mk(cons, Geo3D, "geo3d", defn, [o1, o2], lambda d: _ix_solid_plane(d[0], d[1]))
        if _is_solid_el(o1) and t2 in ("segment", "line3d"):
            return _mk(cons, GeoPoint, "point", defn, [o1, o2],
                       lambda d: _ix_solid_line(d[0], d[1], idx, t2 == "segment"))
        if _is_solid_el(o2) and t1 in ("segment", "line3d"):
            return _mk(cons, GeoPoint, "point", defn, [o1, o2],
                       lambda d: _ix_solid_line(d[1], d[0], idx, t1 == "segment"))
        if t1 == "sphere" and t2 == "sphere":
            return _mk(cons, Geo3D, "geo3d", defn, [o1, o2], lambda d: _ix_sphere_sphere(d[0], d[1]))
        if (t1, t2) in (("sphere", "circle3d"), ("circle3d", "sphere")):
            sph, cir = (o1, o2) if t1 == "sphere" else (o2, o1)
            return _mk(cons, GeoPoint, "point", defn, [sph, cir],
                       lambda d: _ix_sphere_circle3d(d[0], d[1], idx))
        if t1 == "circle3d" and t2 == "circle3d":
            return _mk(cons, GeoPoint, "point", defn, [o1, o2],
                       lambda d: _ix_circle3d_circle3d(d[0], d[1], idx))
        if (t1, t2) in (("circle3d", "plane"), ("plane", "circle3d")):
            cir, pl = (o1, o2) if t1 == "circle3d" else (o2, o1)
            return _mk(cons, GeoPoint, "point", defn, [cir, pl],
                       lambda d: _ix_circle3d_plane(d[0], d[1], idx))
        if t1 == "circle3d" and _is_solid_el(o2):
            return _mk(cons, GeoPoint, "point", defn, [o1, o2],
                       lambda d: _ix_circle3d_solid(d[0], d[1], idx))
        if t2 == "circle3d" and _is_solid_el(o1):
            return _mk(cons, GeoPoint, "point", defn, [o1, o2],
                       lambda d: _ix_circle3d_solid(d[1], d[0], idx))
        if (t1, t2) in (("sphere", "plane"), ("plane", "sphere")):
            sph, pl = (o1, o2) if t1 == "sphere" else (o2, o1)
            return _mk(cons, Geo3D, "geo3d", defn, [sph, pl], lambda d: _ix_sphere_plane(d[0], d[1]))
        if t1 == "sphere" and _is_solid_el(o2):
            return _mk(cons, Geo3D, "geo3d", defn, [o1, o2], lambda d: _ix_sphere_solid(d[0], d[1]))
        if t2 == "sphere" and _is_solid_el(o1):
            return _mk(cons, Geo3D, "geo3d", defn, [o1, o2], lambda d: _ix_sphere_solid(d[1], d[0]))
        if _is_solid_el(o1) and _is_solid_el(o2):
            return _mk(cons, Geo3D, "geo3d", defn, [o1, o2], lambda d: _ix_solid_solid(d[0], d[1]))
        if t1 == "sphere" and t2 in ("segment", "line3d"):
            return _mk(cons, GeoPoint, "point", defn, [o1, o2],
                       lambda d: _ix_sphere_line(d[0], d[1], idx, t2 == "segment"))
        if t2 == "sphere" and t1 in ("segment", "line3d"):
            return _mk(cons, GeoPoint, "point", defn, [o1, o2],
                       lambda d: _ix_sphere_line(d[1], d[0], idx, t1 == "segment"))
        raise GeoError("3D 求交暂不支持 " + t1 + " × " + t2 +
                       "（支持 面×面、直线/线段×面、平面×立体、立体×直线/线段、球×直线/线段）")
    raise GeoError("Intersect 暂不支持 " + k1 + " 与 " + k2 + " 的组合")

def _cmd_isoline(cons, defn, args):
    """SurfaceIsoline[曲面, 值, 维度?]：曲面在固定参数处的参数线（curve3d）。

    显式曲面 Surface[z=f(x,y)]：维度 1 → 固定 x；维度 2（默认）→ 固定 y。
    参数曲面 SurfaceParam[...]：维度 1 → 固定 s；维度 2 → 固定 t。
    """
    if len(args) not in (2, 3):
        raise GeoError("SurfaceIsoline 需要 曲面, 参数值[, 维度(1|2)]")
    surf = _resolve(cons, args[0], ("geo3d",))
    val = eval_number(cons, args[1])
    dim = int(eval_number(cons, args[2])) if len(args) == 3 else (2 if getattr(surf, "solid", "") == "surface"
                                                                  and (surf.data or {}).get("param") is None else 1)
    if dim not in (1, 2):
        raise GeoError("维度只能是 1 或 2")
    return _mk(cons, Geo3D, "geo3d", defn, [surf], lambda d: _isoline_state(d[0], val, dim))

def _isoline_state(surf, val, dim):
    import sympy
    d = surf.data or {}
    if getattr(surf, "solid", "") != "surface":
        raise GeoError("SurfaceIsoline 需要一个曲面（Surface / SurfaceParam / CovarianceEllipsoid）")
    M = 120
    if d.get("param"):
        xb, yb, zb, sname, tname, smin, smax, tmin, tmax = d["param"]
        su, tu = sympy.symbols(sname + " " + tname)
        loc = {sname: su, tname: tu, "pi": sympy.pi, "e": sympy.E}
        fns = [sympy.lambdify((su, tu), sympy.sympify(b.replace("^", "**"), locals=loc), "numpy")
               for b in (xb, yb, zb)]
        pts = []
        for i in range(M + 1):
            if dim == 1:
                s = val
                t = tmin + (tmax - tmin) * i / M
            else:
                s = smin + (smax - smin) * i / M
                t = val
            if dim == 1 and not (smin - COORD <= s <= smax + COORD):
                raise GeoError("参数值超出曲面定义域")
            if dim == 2 and not (tmin - COORD <= t <= tmax + COORD):
                raise GeoError("参数值超出曲面定义域")
            p = []
            for f in fns:
                v = f(s, t)
                v = float(v) if not hasattr(v, "__len__") else float(v[0])
                if not math.isfinite(v):
                    raise GeoError("参数线取值非有限（可能落在奇点）")
                p.append(v)
            pts.append(p)
    elif d.get("expr"):
        xmin, xmax, ymin, ymax = d["ranges"]
        f = sympy.lambdify(sympy.symbols("x y"), sympy.sympify(str(d["expr"]).replace("^", "**"),
                                                              locals={"pi": sympy.pi, "e": sympy.E}), "numpy")
        pts = []
        for i in range(M + 1):
            if dim == 1:
                x, y = val, ymin + (ymax - ymin) * i / M
                if not (xmin - COORD <= x <= xmax + COORD):
                    raise GeoError("参数值超出曲面定义域")
            else:
                x, y = xmin + (xmax - xmin) * i / M, val
                if not (ymin - COORD <= y <= ymax + COORD):
                    raise GeoError("参数值超出曲面定义域")
            z = f(x, y)
            z = float(z) if not hasattr(z, "__len__") else float(z[0])
            if not math.isfinite(z):
                raise GeoError("参数线取值非有限（可能落在奇点）")
            pts.append([x, y, z])
    else:
        raise GeoError("该曲面类型不支持参数线（需要 Surface / SurfaceParam）")
    segs = [[pts[i], pts[i + 1]] for i in range(len(pts) - 1)]
    return schemas.curve3d(segs)

def _ix_fn_fn(cons, defn, f, g, idx):
    """函数与函数求交（可多交点）。"""
    def build(i: int) -> GeoPoint:
        el = GeoPoint("", defn)
        el.free = False
        el._i = i

        def compute(deps):
            a, b = deps[0].expr, deps[1].expr
            x = deps[0].xsym
            roots = _roots_1d(a - b, x)
            if el._i >= len(roots):
                raise GeoError("交点数量不足")
            r = roots[el._i]
            y = _feval(deps[0], r)
            if y is None:
                raise GeoError("交点处函数未定义")
            return {"x": r, "y": y}
        el.set_deps([f, g], compute)
        return el

    if idx is not None:
        el = build(idx)
        el.label = _label_of(defn)
        el.defn = defn + "#" + str(idx)
        return cons.add(el)
    roots = _roots_1d(f.expr - g.expr, f.xsym)
    if not roots:
        raise GeoError("两函数没有交点")
    label = _label_of(defn)
    cmd = _cmd_of(defn)
    created = []
    for i in range(len(roots)):
        li = label if i == 0 else label + str(i)
        d = li + "=" + cmd + "#" + str(i)
        el = build(i)
        el.label = li
        el.defn = d
        created.append(cons.add(el))
    return created

def _ix_fn_lin(cons, defn, f, lin, idx):
    """函数与直线/线段/射线求交。"""
    def build(i: int) -> GeoPoint:
        el = GeoPoint("", defn)
        el.free = False
        el._i = i

        def compute(deps):
            fn, ln = deps[0], deps[1]
            a, b, c = _linear(ln)
            x = fn.xsym
            if abs(b) < EPSILON:
                # 垂直线 x=k
                k = -c / a
                y = _feval(fn, k)
                if y is None:
                    raise GeoError("交点处函数未定义")
                pt = {"x": k, "y": y}
            else:
                diff = fn.expr - (-(a * x + c) / b)
                roots = _roots_1d(diff, x)
                if el._i >= len(roots):
                    raise GeoError("交点数量不足")
                r = roots[el._i]
                pt = {"x": r, "y": _line_y_x(ln, r)}
            if ln.kind == "segment":
                if not (0.0 - COORD <= _on_segment((pt["x"], pt["y"]), ln) <= 1.0 + COORD):
                    raise GeoError("交点不在线段上")
            elif ln.kind == "ray":
                dx, dy = ln.dx, ln.dy
                t = ((pt["x"] - ln.ox) * dx + (pt["y"] - ln.oy) * dy) / (dx * dx + dy * dy + NEGLIGIBLE)
                if t < -COORD:
                    raise GeoError("交点不在射线上")
            return pt
        el.set_deps([f, lin], compute)
        return el

    if idx is not None:
        el = build(idx)
        el.label = _label_of(defn)
        el.defn = defn + "#" + str(idx)
        return cons.add(el)
    a, b, c = _linear(lin)
    if abs(b) < EPSILON:
        root_count = 1
    else:
        diff = f.expr - (-(a * f.xsym + c) / b)
        root_count = len(_roots_1d(diff, f.xsym))
    if root_count == 0:
        raise GeoError("函数与直线没有交点")
    label = _label_of(defn)
    cmd = _cmd_of(defn)
    created = []
    for i in range(root_count):
        li = label if i == 0 else label + str(i)
        d = li + "=" + cmd + "#" + str(i)
        el = build(i)
        el.label = li
        el.defn = d
        created.append(cons.add(el))
    return created

def _ix_linlin(o1, o2):
    a1, b1, c1 = _linear(o1)
    a2, b2, c2 = _linear(o2)
    pt = _intersect_lines(a1, b1, c1, a2, b2, c2)
    if pt is None:
        raise GeoError("两线平行或重合，无唯一交点")
    _check_seg_ray(o1, pt)
    _check_seg_ray(o2, pt)
    return {"x": pt[0], "y": pt[1]}

def _check_seg_ray(obj, pt):
    """若对象是线段/射线，检查交点是否在范围内。"""
    if obj.kind == "segment":
        if _on_segment(pt, obj) < 0:
            raise GeoError("交点不在线段上")
    elif obj.kind == "ray":
        dx, dy = obj.dx, obj.dy
        t = ((pt[0] - obj.ox) * dx + (pt[1] - obj.oy) * dy) / (dx * dx + dy * dy + NEGLIGIBLE)
        if t < -COORD:
            raise GeoError("交点不在射线上")

def _on_segment(pt, seg) -> float:
    """点在参数 t 上的位置；0<=t<=1 在段内。"""
    dx, dy = seg.x2 - seg.x1, seg.y2 - seg.y1
    denom = dx * dx + dy * dy
    if denom < EPSILON:
        return 0.0
    return ((pt[0] - seg.x1) * dx + (pt[1] - seg.y1) * dy) / denom

def _ix_lincir(lin, cir, idx=1):
    pts = _line_circle(_linear(lin), cir.cx, cir.cy, cir.r)
    valid = []
    for pt in pts[:2]:
        try:
            _check_seg_ray(lin, pt)
            valid.append(pt)
        except GeoError:
            continue
    if idx - 1 >= len(valid):
        raise GeoError("直线与圆交点不足 " + str(idx) + " 个")
    return {"x": valid[idx - 1][0], "y": valid[idx - 1][1]}

def _ix_circir(c1, c2, idx=1):
    pts = _circle_circle(c1.cx, c1.cy, c1.r, c2.cx, c2.cy, c2.r)
    if idx - 1 >= len(pts):
        raise GeoError("两圆交点不足 " + str(idx) + " 个")
    return {"x": pts[idx - 1][0], "y": pts[idx - 1][1]}

def _ix_conic_conic(c1, c2, idx=1):
    """圆锥曲线与圆锥曲线求交（sympy 解二元二次方程组）。"""
    import sympy
    x, y = sympy.symbols("x y")
    a1, b1, cc1, d1, e1, f1 = _conic_coeffs(c1)
    a2, b2, cc2, d2, e2, f2 = _conic_coeffs(c2)
    eq1 = a1 * x ** 2 + b1 * x * y + cc1 * y ** 2 + d1 * x + e1 * y + f1
    eq2 = a2 * x ** 2 + b2 * x * y + cc2 * y ** 2 + d2 * x + e2 * y + f2
    try:
        sols = sympy.solve([eq1, eq2], [x, y], dict=True)
    except Exception:
        raise GeoError("圆锥曲线求交失败（无法符号求解）")
    pts = []
    for s in sols:
        try:
            vx, vy = complex(sympy.N(s[x])), complex(sympy.N(s[y]))
            if abs(vx.imag) < COORD and abs(vy.imag) < COORD:
                pts.append((float(vx.real), float(vy.real)))
        except Exception:
            continue
    seen = set()
    uniq = []
    for p_ in pts:
        key = (round(p_[0], 5), round(p_[1], 5))
        if key not in seen:
            seen.add(key)
            uniq.append(p_)
    if idx - 1 >= len(uniq):
        raise GeoError("圆锥曲线交点不足 " + str(idx) + " 个")
    return {"x": uniq[idx - 1][0], "y": uniq[idx - 1][1]}

def _cmd_vector(cons, label, args):
    if len(args) == 1:
        s = args[0].strip()
        if s.startswith("("):
            dx, dy = _resolve_vector(cons, s)
            return _mk_free(cons, GeoVector, label, "(" + _fmt(dx) + "," + _fmt(dy) + ")", dx, dy)
        raise GeoError("Vector 需要一个元组或两个点")
    if len(args) == 2:
        p = _resolve(cons, args[0], ("point",))
        q = _resolve(cons, args[1], ("point",))
        return _mk(cons, GeoVector, "vector", label, [p, q],
                   lambda d: {"dx": d[1].x - d[0].x, "dy": d[1].y - d[0].y,
                              "sx": d[0].x, "sy": d[0].y})
    raise GeoError("Vector 参数错误")

def _mk_free(cons, cls, label, defn, *vals):
    el = cls(label, defn, *vals)
    return cons.add(el)

def _line_y_x(lin, x: float):
    """直线在 x 处的 y（垂直线返回 None）。"""
    a, b, c = _linear(lin)
    if abs(b) < EPSILON:
        return None
    return -(a * x + c) / b

def _cmd_tangent(cons, defn, args, idx=None):
    if len(args) != 2:
        raise GeoError("Tangent 需要 对象 和 切点 x 值 或 点")
    first = _resolve(cons, args[0])
    # Tangent[点, 圆]：圆外/圆上点作切线（GGB 顺序）
    if first.kind == "point":
        second = _lookup(cons, args[1])
        if second is not None and second.kind in ("conic", "circle"):
            return _cmd_tangent_conic(cons, defn, [args[1], args[0]], idx)
        raise GeoError("Tangent[点, 圆] 的第二个参数必须是圆或圆锥曲线")
    if first.kind in ("conic", "circle"):
        return _cmd_tangent_conic(cons, defn, args, idx)
    if first.kind == "arc":
        # 圆弧/扇形：在点击处沿弧所在圆作切线（切点钳制到弧范围内）
        pta = _point_arg(cons, args[1])
        return _mk(cons, GeoLine, "line", defn, [first, pta],
                   lambda d: _tangent_arc_state(d[0], d[1]))
    f = _resolve(cons, args[0], ("function",))
    s = args[1].strip()
    el = _lookup(cons, s)
    if el is not None and el.kind == "point":
        return _mk(cons, GeoLine, "line", defn, [f, el],
                   lambda d: _tangent_state(d[0], d[1].x))
    if el is not None and el.kind == "number":
        return _mk(cons, GeoLine, "line", defn, [f, el],
                   lambda d: _tangent_state(d[0], d[1].value))
    x0 = eval_number(cons, args[1])
    return _mk(cons, GeoLine, "line", defn, [f],
               lambda d: _tangent_state(d[0], x0))

def _tangent_state(f, x0: float):
    import sympy
    x = f.xsym
    try:
        y0 = float(sympy.N(f.expr.subs(x, x0)))
        m = float(sympy.N(sympy.diff(f.expr, x).subs(x, x0)))
    except Exception:
        raise GeoError("切点处函数不可求值")
    if not (math.isfinite(y0) and math.isfinite(m)):
        raise GeoError("切点处函数不可求值")
    return _line_state(-m, 1.0, -(y0 - m * x0))

def _cmd_perpendicularline(cons, defn, args):
    if len(args) != 2:
        raise GeoError("PerpendicularLine 需要 点 和 直线")
    pt = _point_arg(cons, args[0])
    lin = _resolve(cons, args[1], ("line", "segment", "ray"))
    return _mk(cons, GeoLine, "line", defn, [pt, lin], lambda d: _perp_state(d[0], d[1]))

def _perp_state(pt, lin):
    a, b, c = _linear(lin)
    return _line_state(b, -a, -(b * pt.x - a * pt.y))

def _cmd_foot(cons, defn, args):
    if len(args) != 2:
        raise GeoError("Foot 需要 点 和 直线")
    pt = _point_arg(cons, args[0])
    lin = _resolve(cons, args[1], ("line", "segment", "ray"))
    return _mk(cons, GeoPoint, "point", defn, [pt, lin], lambda d: _foot_state(d[0], d[1]))

def _foot_state(pt, lin):
    a, b, c = _linear(lin)
    denom = a * a + b * b
    if denom < EPSILON:
        raise GeoError("退化直线")
    t = -(a * pt.x + b * pt.y + c) / denom
    return {"x": pt.x + a * t, "y": pt.y + b * t}

def _cmd_perpbis(cons, defn, args):
    """PerpendicularBisector[线段] 或 [A, B]：中垂线。"""
    if len(args) == 1:
        seg = _resolve(cons, args[0], ("segment", "line", "ray"))
        return _mk(cons, GeoLine, "line", defn, [seg], lambda d: _perpbis_state(d[0]))
    if len(args) == 2:
        a = _point_arg(cons, args[0])
        b = _point_arg(cons, args[1])
        return _mk(cons, GeoLine, "line", defn, [a, b], lambda d: _perpbis_state2(d[0], d[1]))
    raise GeoError("PerpendicularBisector 需要 线段 或 两点")

def _perpbis_state(seg):
    mx, my = (seg.x1 + seg.x2) / 2.0, (seg.y1 + seg.y2) / 2.0
    dx, dy = seg.x2 - seg.x1, seg.y2 - seg.y1
    # 方向 (-dy, dx)，法向 (dx, dy)，过中点
    return _line_state(dx, dy, -(dx * mx + dy * my))

def _perpbis_state2(a, b):
    mx, my = (a.x + b.x) / 2.0, (a.y + b.y) / 2.0
    dx, dy = b.x - a.x, b.y - a.y
    return _line_state(dx, dy, -(dx * mx + dy * my))

def _cmd_regularpolygon(cons, defn, args):
    """RegularPolygon[A, B, n]：正 n 边形（AB 为一边，逆时针）。"""
    if len(args) != 3:
        raise GeoError("RegularPolygon 需要 两个顶点 和 边数 n")
    a = _point_arg(cons, args[0])
    b = _point_arg(cons, args[1])
    n = int(eval_number(cons, args[2]))
    if n < 3 or n > 100:
        raise GeoError("边数需在 3~100")

    def fn(d):
        x0, y0 = d[0].x, d[0].y
        x1, y1 = d[1].x, d[1].y
        xs, ys = [x0, x1], [y0, y1]
        ang = 2 * math.pi / n
        cx, cy = x1, y1
        dx, dy = x1 - x0, y1 - y0
        for _ in range(n - 2):
            ndx = dx * math.cos(ang) - dy * math.sin(ang)
            ndy = dx * math.sin(ang) + dy * math.cos(ang)
            cx += ndx
            cy += ndy
            xs.append(cx)
            ys.append(cy)
            dx, dy = ndx, ndy
        return {"xs": xs, "ys": ys}

    return _mk(cons, GeoPolygon, "polygon", defn, [a, b], fn)

def _cmd_anglebisector(cons, defn, args):
    if len(args) != 3:
        raise GeoError("AngleBisector 需要三点 A,B,C（∠ABC 的平分线）")
    a = _point_arg(cons, args[0])
    b = _point_arg(cons, args[1])
    c = _point_arg(cons, args[2])
    return _mk(cons, GeoLine, "line", defn, [a, b, c], lambda d: _bisector_state(d[0], d[1], d[2]))

def _bisector_state(a, b, c):
    ux, uy = a.x - b.x, a.y - b.y
    vx, vy = c.x - b.x, c.y - b.y
    nu = math.hypot(ux, uy)
    nv = math.hypot(vx, vy)
    if nu < EPSILON or nv < EPSILON:
        raise GeoError("退化角")
    dx, dy = ux / nu + vx / nv, uy / nu + vy / nv
    return _line_state(-dy, dx, -(-dy * b.x + dx * b.y))

def _cmd_incenter(cons, defn, args):
    poly = _resolve(cons, args[0], ("polygon",))
    pts = [p for p in poly.deps if p.kind == "point"]
    if len(pts) != 3:
        raise GeoError("Incenter 需要三角形")
    return _mk(cons, GeoPoint, "point", defn, pts, lambda d: _incenter_state(d[0], d[1], d[2]))

def _incenter_state(a, b, c):
    la = _dist((b.x, b.y), (c.x, c.y))
    lb = _dist((c.x, c.y), (a.x, a.y))
    lc = _dist((a.x, a.y), (b.x, b.y))
    s = la + lb + lc
    if s < EPSILON:
        raise GeoError("退化三角形")
    return {"x": (la * a.x + lb * b.x + lc * c.x) / s,
            "y": (la * a.y + lb * b.y + lc * c.y) / s}

def _cmd_incircle(cons, defn, args):
    poly = _resolve(cons, args[0], ("polygon",))
    pts = [p for p in poly.deps if p.kind == "point"]
    if len(pts) != 3:
        raise GeoError("Incircle 需要三角形")
    return _mk(cons, GeoCircle, "circle", defn, pts, lambda d: _incircle_state(d[0], d[1], d[2]))

def _incircle_state(a, b, c):
    la = _dist((b.x, b.y), (c.x, c.y))
    lb = _dist((c.x, c.y), (a.x, a.y))
    lc = _dist((a.x, a.y), (b.x, b.y))
    s = la + lb + lc
    if s < EPSILON:
        raise GeoError("退化三角形")
    ix = (la * a.x + lb * b.x + lc * c.x) / s
    iy = (la * a.y + lb * b.y + lc * c.y) / s
    area = abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)) / 2.0
    r = 2 * area / s
    return {"cx": ix, "cy": iy, "r": r}

def _cmd_centroid(cons, defn, args):
    """Centroid[多边形] 或 Centroid[点列表]：多边形顶点均值 / 点云质心（三维点列表带 z）。"""
    if len(args) != 1:
        raise GeoError("Centroid 需要一个多边形或点列表")
    txt = args[0].strip()
    _el = _lookup(cons, txt)
    if (_el is not None and _el.kind == "list") or txt.startswith("{"):
        el = _list_arg(cons, txt)
        if el.itemkind not in ("point", "point3d"):
            raise GeoError("Centroid 的点列表需要 (x,y) 或 (x,y,z) 元素")
        three = el.itemkind == "point3d"

        def fn(d):
            items = d[0].items
            if not items:
                raise GeoError("点列表为空")
            n = len(items)
            st = {"x": sum(p[0] for p in items) / n, "y": sum(p[1] for p in items) / n}
            if three:
                st["z"] = sum(p[2] for p in items) / n
            return st
        return _mk(cons, GeoPoint, "point", defn, [el], fn)
    obj = _resolve(cons, args[0], ("polygon",))
    return _mk(cons, GeoPoint, "point", defn, [obj], lambda d: _centroid_state(d[0]))

def _centroid_state(poly):
    xs, ys = poly.xs, poly.ys
    if not xs:
        raise GeoError("空多边形")
    return {"x": sum(xs) / len(xs), "y": sum(ys) / len(ys)}

def _cmd_randpointin(cons, defn, args):
    """RandomPointIn[圆 或 多边形] → 形状内均匀随机点（几何概型打点；拖动形状时点重算仍落在形状内）。"""
    if len(args) != 1:
        raise GeoError("RandomPointIn 需要一个 圆或多边形")
    el = _resolve(cons, args[0])
    if el.kind == "circle":
        sk = "circle"
    elif el.kind == "polygon":
        sk = "polygon"
    else:
        raise GeoError("RandomPointIn 仅支持 圆 或 多边形")

    def fn(d):
        return _randpointin_state(d[0], sk)

    return _mk(cons, GeoPoint, "point", defn, [el], fn)

def _randpointin_state(obj, kind):
    """均匀随机：圆内用 r·sqrt(U)·(cosθ,sinθ)；多边形按三角形扇面积加权 + 重心坐标。"""
    import random
    import math as _m
    if kind == "circle":
        rr = obj.r
        if rr <= EPSILON:
            raise GeoError("退化圆（半径为零）")
        u = random.random()
        th = 2 * _m.pi * random.random()
        rad = rr * _m.sqrt(u)
        return {"x": obj.cx + rad * _m.cos(th), "y": obj.cy + rad * _m.sin(th)}
    xs, ys = obj.xs, obj.ys
    n = len(xs)
    if n < 3:
        raise GeoError("多边形至少需要三个顶点")
    areas = []
    tot = 0.0
    for i in range(1, n - 1):
        a = abs((xs[i] - xs[0]) * (ys[i + 1] - ys[0]) - (xs[i + 1] - xs[0]) * (ys[i] - ys[0])) / 2.0
        areas.append(a)
        tot += a
    if tot <= EPSILON:
        raise GeoError("退化多边形（面积为零）")
    u = random.random() * tot
    acc = 0.0
    pick = len(areas) - 1
    for k, a in enumerate(areas):
        acc += a
        if u <= acc:
            pick = k
            break
    i1 = pick + 1
    r1 = _m.sqrt(random.random())
    r2 = random.random()
    x = xs[0] + r1 * (1 - r2) * (xs[i1] - xs[0]) + r1 * r2 * (xs[i1 + 1] - xs[0])
    y = ys[0] + r1 * (1 - r2) * (ys[i1] - ys[0]) + r1 * r2 * (ys[i1 + 1] - ys[0])
    return {"x": x, "y": y}

def _cmd_fitline(cons, defn, args):
    L = _list_arg(cons, args[0])
    if L.itemkind != "point":
        raise GeoError("FitLine 需要点列表，如 {(1,2),(2,3)}")
    return _mk(cons, GeoLine, "line", defn, [L], lambda d: _fitline_state(d[0].items))

def _conic_coeffs(el):
    """圆/圆锥曲线 → 一般系数 (a,b,c,d,e,f)。"""
    if el.kind == "circle":
        cx, cy, r = el.cx, el.cy, el.r
        return (1.0, 0.0, 1.0, -2 * cx, -2 * cy, cx * cx + cy * cy - r * r)
    if el.kind == "conic":
        return (el.a, el.b, el.c, el.d, el.e, el.f)
    raise GeoError("对象不是圆锥曲线")

def _cmd_tangent_conic(cons, defn, args, idx=None):
    """圆/圆锥曲线切线：点在曲线上 → 单切线；点在圆外 → 两条切线（多结果）。"""
    conic = _resolve(cons, args[0], ("conic", "circle"))
    pt = _point_arg(cons, args[1])

    def build(i):
        el = GeoLine("", defn)
        el.free = False
        el._i = i
        el.set_deps([conic, pt], lambda d: _tangent_conic_state_i(d[0], d[1], el._i))
        return el

    if conic.kind == "circle":
        d2 = math.hypot(pt.x - conic.cx, pt.y - conic.cy)
        if d2 > conic.r + COORD:
            # 圆外：两条切线
            if idx is not None:
                el = build(idx)
                el.label = label_of(defn)
                el.defn = defn + "#" + str(idx)
                return cons.add(el)
            created = []
            for i in range(2):
                li = label_of(defn) if i == 0 else label_of(defn) + str(i)
                el = build(i)
                el.label = li
                el.defn = li + "=" + _cmd_of(defn) + "#" + str(i)
                created.append(cons.add(el))
            return created
    return _mk(cons, GeoLine, "line", defn, [conic, pt], lambda d: _tangent_conic_state(d[0], d[1]))

def _tangent_conic_state_i(conic, pt, i):
    if conic.kind != "circle":
        raise GeoError("仅圆支持外部双切线")
    cx, cy, r = conic.cx, conic.cy, conic.r
    d2 = math.hypot(pt.x - cx, pt.y - cy)
    if d2 <= r + COORD:
        raise GeoError("点不在圆外")
    phi0 = math.atan2(pt.y - cy, pt.x - cx)
    alpha = math.acos(min(1.0, r / d2))
    phi = phi0 + (alpha if i == 0 else -alpha)
    tx = cx + r * math.cos(phi)
    ty = cy + r * math.sin(phi)
    return _line_state(*_line_through(pt.x, pt.y, tx, ty))

def _tangent_arc_state(arc, pt):
    """圆弧/扇形切线：弧所在圆在切点处的切线；切点取点击沿半径投影并钳制到弧的角度范围。"""
    import math as _m
    cx, cy, r = arc.cx, arc.cy, arc.r
    if r <= COORD:
        raise GeoError("退化圆弧")
    ang = _m.atan2(pt.y - cy, pt.x - cx)
    a1 = arc.ang1
    span = (arc.ang2 - a1) % (2 * _m.pi)
    # 环内最近角：优先落在 [a1, a1+span]
    d1 = (ang - a1) % (2 * _m.pi)
    use = a1 + d1 if d1 <= span + COORD else None
    if use is None:
        # 钳制到最近端点
        d_end = (d1 - span)
        use = a1 + span if d_end < (2 * _m.pi - d1) else a1
    qx = cx + r * _m.cos(use)
    qy = cy + r * _m.sin(use)
    return _line_state(qx - cx, qy - cy, -((qx - cx) * qx + (qy - cy) * qy))

def _tangent_conic_state(conic, pt):
    a, b, c, d_, e, f = _conic_coeffs(conic)
    x0, y0 = pt.x, pt.y
    q = a * x0 * x0 + b * x0 * y0 + c * y0 * y0 + d_ * x0 + e * y0 + f
    if abs(q) > 0.01:
        raise GeoError("点不在圆锥曲线上，无法作切线")
    # 切线：梯度方向
    A = 2 * a * x0 + b * y0 + d_
    B = b * x0 + 2 * c * y0 + e
    C = -(A * x0 + B * y0)
    return _line_state(A, B, C)

def _ix_lin_conic(cons, defn, lin, conic, idx):
    from .geom_util import line_conic_intersect

    def build(i):
        el = GeoPoint("", defn)
        el.free = False
        el._i = i

        def compute(deps):
            ln, cn = deps[0], deps[1]
            a, b, c = _linear(ln)
            denom = a * a + b * b
            p0x = -a * c / denom if denom > EPSILON else 0.0
            p0y = -b * c / denom if denom > EPSILON else 0.0
            dx, dy = (-b / math.sqrt(denom), a / math.sqrt(denom)) if denom > EPSILON else (1.0, 0.0)
            pts = line_conic_intersect(p0x, p0y, dx, dy, _conic_coeffs(cn))
            if el._i >= len(pts):
                raise GeoError("无足够交点")
            pt = pts[el._i]
            return {"x": pt[0], "y": pt[1]}
        el.set_deps([lin, conic], compute)
        return el

    if idx is not None:
        el = build(idx)
        el.label = label_of(defn)
        el.defn = defn + "#" + str(idx)
        return cons.add(el)
    a, b, c = _linear(lin)
    denom = a * a + b * b
    p0x = -a * c / denom if denom > EPSILON else 0.0
    p0y = -b * c / denom if denom > EPSILON else 0.0
    dx, dy = (-b / math.sqrt(denom), a / math.sqrt(denom)) if denom > EPSILON else (1.0, 0.0)
    pts = line_conic_intersect(p0x, p0y, dx, dy, _conic_coeffs(conic))
    if not pts:
        raise GeoError("直线与圆锥曲线不相交")
    created = []
    for i in range(len(pts)):
        li = label_of(defn) if i == 0 else label_of(defn) + str(i)
        el = build(i)
        el.label = li
        el.defn = li + "=" + _cmd_of(defn) + "#" + str(i)
        created.append(cons.add(el))
    return created

def _pred_dir(el):
    """取"线类"元素的方向向量：直线/线段/射线/向量。"""
    if el is None:
        return None
    d = el.draw(_PRED_VIEW) or {}
    if el.kind == "line":
        seg = d.get("seg")
        return None if not seg else (seg[2] - seg[0], seg[3] - seg[1])
    if el.kind == "segment":
        return (d.get("x2", 0.0) - d.get("x1", 0.0), d.get("y2", 0.0) - d.get("y1", 0.0))
    if el.kind == "ray":
        return (d.get("ux", 1.0), d.get("uy", 0.0))
    if el.kind == "vector":
        return (d.get("x", 0.0), d.get("y", 0.0))
    return None

def _pred_scale(*vals):
    m = 1.0
    for v in vals:
        m = max(m, abs(float(v)))
    return m

def _numeric_verdict(cons, kind, args):
    """具体数值输入的数值兜底判定（符号证明返回"未知"时使用）。

    返回 (True/False/None, 说明)。容差按量级取相对值。
    """
    els = []
    for a in args:
        raw = a.strip()
        e = _lookup(cons, raw)
        if e is None:
            try:
                e = _resolve(cons, raw)        # 内联命令（如 Line[(0,0),(1,1)]）的临时对象
            except Exception:
                e = None
        if e is None and raw.startswith("(") and raw.endswith(")"):
            try:
                e = _point_arg(cons, raw)      # 内联点字面量 (x,y)
            except Exception:
                e = None
        els.append(e)
    if any(e is None for e in els):
        return None, "数值判定：对象不存在"
    if kind in ("parallel", "perpendicular"):
        d1, d2 = _pred_dir(els[0]), _pred_dir(els[1])
        if d1 is None or d2 is None:
            return None, "数值判定：需要直线/线段/射线/向量"
        cross = d1[0] * d2[1] - d1[1] * d2[0]
        dot = d1[0] * d2[0] + d1[1] * d2[1]
        tol = COORD * _pred_scale(d1[0], d1[1], d2[0], d2[1]) ** 2
        if kind == "parallel":
            return (abs(cross) <= tol), "数值判定：方向叉积 = %.3e" % cross
        return (abs(dot) <= tol), "数值判定：方向点积 = %.3e" % dot
    if kind == "collinear":
        if not all(e.kind == "point" for e in els):
            return None, "数值判定：需要三个点"
        (x1, y1), (x2, y2), (x3, y3) = [(e.x, e.y) for e in els]
        cr = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)
        tol = COORD * _pred_scale(x2 - x1, y2 - y1, x3 - x1, y3 - y1) ** 2
        return (abs(cr) <= tol), "数值判定：三点叉积 = %.3e" % cr
    if kind == "congruent":
        d1, d2 = _pred_dir(els[0]), _pred_dir(els[1])
        if d1 is None or d2 is None:
            return None, "数值判定：需要两条线段"
        l1 = math.hypot(*d1)
        l2 = math.hypot(*d2)
        return (abs(l1 - l2) <= COORD * _pred_scale(l1, l2)), "数值判定：长度 %.6g vs %.6g" % (l1, l2)
    if kind == "concyclic":
        if not all(e.kind == "point" for e in els):
            return None, "数值判定：需要四个点"
        pts = [(e.x, e.y) for e in els]
        # 四点共圆 ⇔ 4×4 行列式为零
        import sympy
        rows = [[p[0], p[1], p[0] ** 2 + p[1] ** 2, 1] for p in pts]
        det = sympy.Matrix(rows).det()
        scale = _pred_scale(*[c for p in pts for c in p]) ** 4
        return (abs(float(det)) <= COORD * max(1.0, scale)), "数值判定：共圆行列式 = %.3e" % float(det)
    if kind == "concurrent":
        ds = [_pred_dir(e) for e in els]
        if any(d is None for d in ds):
            return None, "数值判定：需要三条直线"
        if not all(e.kind == "point" for e in els[:0]):   # 占位：直线可由两点确定
            pass
        # 用直线一般式：a x + b y + c = 0（方向 (dx,dy) → a=dy, b=-dx，过首点）
        def abc(el, d):
            a_, b_ = d[1], -d[0]
            dd = el.draw(_PRED_VIEW) or {}
            if el.kind == "line":
                return dd.get("a", a_), dd.get("b", b_), dd.get("c", 0.0)
            if el.kind == "segment":
                return a_, b_, -(a_ * dd.get("x1", 0.0) + b_ * dd.get("y1", 0.0))
            if el.kind == "ray":
                return a_, b_, -(a_ * dd.get("ox", 0.0) + b_ * dd.get("oy", 0.0))
            return None
        l1, l2, l3 = (abc(e, d) for e, d in zip(els, ds))
        if l1 is None or l2 is None or l3 is None:
            return None, "数值判定：无法取直线方程"
        def _pt_on(l):
            if abs(l[0]) >= abs(l[1]):
                return (-l[2] / l[0], 0.0)
            return (0.0, -l[2] / l[1])

        sc12 = _pred_scale(l1[0], l1[1], l2[0], l2[1])
        det12 = l1[0] * l2[1] - l1[1] * l2[0]
        if abs(det12) <= COORD * sc12 * sc12:
            # 前两条平行：不重合 ⇒ 无公共点（必不共点）；重合 ⇒ 看第三条是否也过这条线
            qx, qy = _pt_on(l1)
            off = abs(l2[0] * qx + l2[1] * qy + l2[2]) / max(EPSILON, math.hypot(l2[0], l2[1]))
            if off > LOOSE * _pred_scale(qx, qy, 1.0):
                return False, "数值判定：前两条直线平行且不重合 → 不共点"
            on3 = abs(l3[0] * qx + l3[1] * qy + l3[2]) / max(EPSILON, math.hypot(l3[0], l3[1]))
            return (on3 <= LOOSE * _pred_scale(qx, qy, 1.0)), "数值判定：前两条重合，第三条偏移 = %.3e" % on3
        px = (l1[1] * l2[2] - l2[1] * l1[2]) / det12
        py = (l2[0] * l1[2] - l1[0] * l2[2]) / det12
        val = l3[0] * px + l3[1] * py + l3[2]
        scale = _pred_scale(l3[0], l3[1], px, py)
        return (abs(val) <= LOOSE * scale), "数值判定：三线共点残差 = %.3e" % val
    return None, "数值判定：不支持的命题"

def _prove_cmd(cons, defn, args, kind, n):
    """Are* 命令：构造布尔元素，一次性符号证明（避免拖拽重跑 sympy）。

    符号化失败（具体数值构造常见）时退回数值判定，避免整条命令只剩"未知"。
    """
    if len(args) != n:
        raise GeoError("该命题需要 " + str(n) + " 个参数")
    from .prover import SymbolicGeo
    el = GeoBoolean(label_of(defn), defn)
    el.free = False
    el._prove_args = (kind, list(args))
    sg = SymbolicGeo(cons)
    res = sg.prove(kind, args)
    if res.value is None:
        nv, note = _numeric_verdict(cons, kind, args)
        if nv is not None:
            res = type(res)(nv, note)
    el.value = res.value
    el.detail = res.detail
    return cons.add(el)

def _cmd_areparallel(cons, defn, args):
    return _prove_cmd(cons, defn, args, "parallel", 2)

def _cmd_areperpendicular(cons, defn, args):
    return _prove_cmd(cons, defn, args, "perpendicular", 2)

def _cmd_arecollinear(cons, defn, args):
    return _prove_cmd(cons, defn, args, "collinear", 3)

def _cmd_pointoncircle(cons, defn, args):
    """PointOnCircle[圆] / PointOnCircle[圆, θ] → 圆上点。"""
    if len(args) not in (1, 2):
        raise GeoError("PointOnCircle 需要 圆（可选角度数值）")
    c = _resolve(cons, args[0], ("circle",))
    if len(args) == 2:
        th = _resolve(cons, args[1], ("number",))
        deps = [c, th]
    else:
        # 自动创建角度滑块 θ（0..2π），defn 显式引用（重放/轨迹解析一致）
        lab = label_of(defn)
        th_label = cons.auto_label("number")
        th = GeoNumber(th_label, th_label + "=Slider[0,6.283185307179586,0.05]", 0.0)
        th.value = 3.141592653589793  # 默认半圆处，便于选中
        th.min, th.max, th.step = 0.0, 6.283185307179586, 0.05
        cons.add(th)
        defn = lab + "=PointOnCircle[" + args[0] + "," + th_label + "]"
        deps = [c, th]
    return _mk(cons, GeoPoint, "point", defn, deps, lambda d: _poc_state(d[0], d[1]))

def _cmd_pointonpath(cons, defn, args):
    """PointOnPath[对象] → 对象上动点（线/线段/射线/圆/多边形/圆弧，自动参数滑块 0..1 驱动）。"""
    if len(args) != 1:
        raise GeoError("PointOnPath 需要 线/线段/射线/圆/多边形/圆弧")
    obj = _resolve(cons, args[0], ("line", "segment", "ray", "circle", "polygon", "arc"))
    lab = label_of(defn)
    t_label = cons.auto_label("number")
    t = GeoNumber(t_label, t_label + "=Slider[0,1,0.01]", 0.5)
    t.value = 0.5  # 默认中点，便于选中
    t.min, t.max, t.step = 0.0, 1.0, 0.01
    cons.add(t)
    defn = lab + "=PointOnPath[" + args[0] + "," + t_label + "]"
    return _mk(cons, GeoPoint, "point", defn, [obj, t], lambda d: _pop_state(d[0], d[1]))

def _pop_state(obj, t):
    tv = t.value
    if obj.kind == "circle":
        ang = tv * 2 * math.pi
        return {"x": obj.cx + obj.r * math.cos(ang), "y": obj.cy + obj.r * math.sin(ang)}
    if obj.kind == "segment":
        return {"x": obj.x1 + tv * (obj.x2 - obj.x1), "y": obj.y1 + tv * (obj.y2 - obj.y1)}
    if obj.kind == "line":
        a, b, c = obj.a, obj.b, obj.c
        denom = a * a + b * b
        if denom < EPSILON:
            raise GeoError("退化直线")
        spr = math.sqrt(denom)
        px, py = -a * c / denom, -b * c / denom
        s = (tv - 0.5) * 60  # 视口跨度附近
        return {"x": px + (-b / spr) * s, "y": py + (a / spr) * s}
    if obj.kind == "ray":
        el = math.hypot(obj.dx, obj.dy)
        s = tv * 20
        return {"x": obj.ox + obj.dx / el * s, "y": obj.oy + obj.dy / el * s}
    if obj.kind == "arc":
        span = (obj.ang2 - obj.ang1) % (2 * math.pi)  # 逆时针正跨度（优弧>π，劣弧<π）
        if span < COORD:
            span = 2 * math.pi
        ang = obj.ang1 + tv * span
        return {"x": obj.cx + obj.r * math.cos(ang), "y": obj.cy + obj.r * math.sin(ang)}
    if obj.kind == "polygon":
        xs, ys = obj.xs, obj.ys
        n = len(xs)
        if n < 3:
            raise GeoError("多边形退化")
        segs = []
        total = 0.0
        for i in range(n):
            j = (i + 1) % n
            ln = math.hypot(xs[j] - xs[i], ys[j] - ys[i])
            segs.append((xs[i], ys[i], xs[j], ys[j], ln))
            total += ln
        if total < EPSILON:
            raise GeoError("多边形退化")
        d = tv * total
        acc = 0.0
        for (x1, y1, x2, y2, ln) in segs:
            if ln < EPSILON:
                continue
            if d <= acc + ln:
                tt = (d - acc) / ln
                return {"x": x1 + tt * (x2 - x1), "y": y1 + tt * (y2 - y1)}
            acc += ln
        return {"x": segs[-1][2], "y": segs[-1][3]}
    raise GeoError("该对象暂不支持动点")

def _poc_state(c, th):
    return {"x": c.cx + c.r * math.cos(th.value), "y": c.cy + c.r * math.sin(th.value)}

def _cmd_arc(cons, defn, args):
    """Arc[A, B, C]：A 起点、B 终点、C 圆心（默认逆时针）。"""
    if len(args) != 3:
        raise GeoError("Arc 需要 起点、终点、圆心")
    a = _point_arg(cons, args[0])
    b = _point_arg(cons, args[1])
    c = _point_arg(cons, args[2])
    return _mk(cons, GeoArc, "arc", defn, [a, b, c], lambda d: _arc_state(d[0], d[1], d[2], False))

def _cmd_semicircle(cons, defn, args):
    """Semicircle[A, B]：以 AB 为直径的半圆（B 侧逆时针）。"""
    if len(args) != 2:
        raise GeoError("Semicircle 需要直径端点 A, B")
    a = _point_arg(cons, args[0])
    b = _point_arg(cons, args[1])
    return _mk(cons, GeoArc, "arc", defn, [a, b], lambda d: _semicircle_state(d[0], d[1]))

def _semicircle_state(a, b):
    cx, cy = (a.x + b.x) / 2, (a.y + b.y) / 2
    r = math.hypot(b.x - a.x, b.y - a.y) / 2.0
    if r < EPSILON:
        raise GeoError("退化半圆")
    ang1 = math.atan2(a.y - cy, a.x - cx)
    return {"sector": False, "semicircle": True, "cx": cx, "cy": cy,
            "r": r, "ang1": ang1, "ang2": ang1 + math.pi}

def _cmd_sector(cons, defn, args):
    if len(args) != 3:
        raise GeoError("Sector 需要 起点、终点、圆心")
    a = _point_arg(cons, args[0])
    b = _point_arg(cons, args[1])
    c = _point_arg(cons, args[2])
    return _mk(cons, GeoArc, "arc", defn, [a, b, c], lambda d: _arc_state(d[0], d[1], d[2], True))

def _arc_state(a, b, c, sector):
    """圆弧/扇形：C 为圆心，半径取 |CA|（保证弧过起点 A）。

    原先取 (|CA|+|CB|)/2，当 C 不是 A、B 的等距圆心时弧两个端点都不在弧上（静默错误）。
    现在要求圆心近似等距（相对偏差 ≤ 20%），否则明确报错。
    """
    ra = math.hypot(a.x - c.x, a.y - c.y)
    rb = math.hypot(b.x - c.x, b.y - c.y)
    if ra < EPSILON or rb < EPSILON:
        raise GeoError("退化圆弧（端点与圆心重合）")
    if abs(ra - rb) > 0.2 * max(ra, rb):
        raise GeoError("圆弧/扇形要求圆心 C 与两端点近似等距（|CA|=%.4f, |CB|=%.4f）；"
                       "请改用等距的圆心或合适的端点" % (ra, rb))
    r = ra
    ang1 = math.atan2(a.y - c.y, a.x - c.x)
    ang2 = math.atan2(b.y - c.y, b.x - c.x)
    return {"sector": sector, "cx": c.x, "cy": c.y, "r": r, "ang1": ang1, "ang2": ang2}
