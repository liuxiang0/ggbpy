"""度量命令（距离/长度/周长/半周长/半径/斜率/角度，P2 结构拆分：从 commands.py 抽出）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .cmd_util import _mk, _point_arg, _resolve
from .geo2d import _arc_length, _linear, _polyline_length
from .geometry3d import _dist3, _has_z, _z_of
from .linalg import _vec2_arg, _vec_arg_objs
from .primitives import _dist
from .elements import GeoAngle, GeoError, GeoNumber
from .tolerance import EPSILON


__all__ = [
    "_cmd_distance",
    "_pt_linear_dist",
    "_cmd_slope",
    "_slope_state",
    "_cmd_angle",
    "_angle2_state",
    "_angle_state",
    "_polygon_perimeter",
    "_section_perimeter",
    "_cmd_perimeter",
    "_cmd_circumference",
    "_ellipse_circumference",
    "_cmd_radius",
    "_cmd_semiperimeter",
    "_cmd_length",
]


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
    # 有向角：逆时针从 u 到 v，范围 [0, 360)（与 GeoGebra 的 Angle 一致）
    ang = math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1]))
    if ang < 0:
        ang += 360.0
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
    # 有向角 [0, 360)：逆时针从 BA 到 BC，钝角/优角都能正确表示
    # （例：BA 指向右、BC 指向左下 → 225°，不再折成 135°）
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
    """周长：支持 多边形 / 圆 / 椭圆（圆锥曲线）/ 圆弧 / 扇形 / 折线 / 线段 / 3D 截面。

    语义约定：
    - 扇形 = 弧长 + 两条半径；圆弧 = 弧长（不闭合，不加弦）
    - 椭圆用 Ramanujan 近似（与 `Circumference` 同一实现，圆退化为精确 2πr）
    - 双曲线/抛物线无有限周长 → 明确报错
    """
    if len(args) != 1:
        raise GeoError("Perimeter 需要 1 个对象")
    obj = _resolve(cons, args[0])
    kind = obj.kind
    if kind == "polygon":
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": _polygon_perimeter(d[0])})
    if kind == "circle":
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": 2 * math.pi * d[0].r})
    if kind == "conic":
        ctype = getattr(obj, "ctype", "")
        if ctype in ("ellipse", "circle"):
            def _conic_perim(d):
                a = float(d[0].semi_a or 0.0)
                b = float(d[0].semi_b or a)
                return {"value": _ellipse_circumference(a, b)}
            return _mk(cons, GeoNumber, "number", defn, [obj], _conic_perim)
        raise GeoError("Perimeter：双曲线/抛物线/一般圆锥曲线无有限周长（只有圆与椭圆有）")
    if kind == "arc":
        if getattr(obj, "sector", False):
            return _mk(cons, GeoNumber, "number", defn, [obj],
                       lambda d: {"value": _arc_length(d[0]) + 2.0 * float(d[0].r)})
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": _arc_length(d[0])})
    if kind == "polyline":
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": _polyline_length(d[0])})
    if kind == "segment":
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": _dist((d[0].x1, d[0].y1), (d[0].x2, d[0].y2))})
    if kind == "geo3d" and getattr(obj, "objtype", "") == "section":
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": _section_perimeter(d[0])})
    raise GeoError("Perimeter 需要 多边形/圆/椭圆/圆弧/扇形/折线/线段 或 3D 截面")

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

def _cmd_radius(cons, defn, args):
    el = _resolve(cons, args[0])
    if el.kind == "circle":
        return _mk(cons, GeoNumber, "number", defn, [el], lambda d: {"value": d[0].r})
    if el.kind == "arc":
        return _mk(cons, GeoNumber, "number", defn, [el], lambda d: {"value": d[0].r})
    raise GeoError("Radius 需要 圆 或 圆弧")

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

def _cmd_length(cons, defn, args):
    """长度/弧长：线段 / 向量 / 折线 / 圆弧（扇形也只取**弧长**）/ 圆 / 椭圆 / 列表（元素个数）。

    与 `Perimeter` 的分工：
    - `Length` = **曲线自身长度**（扇形=弧长；圆/椭圆=周长）
    - `Perimeter` = **封闭边界**（扇形 = 弧长 + 两条半径；多边形=闭合边长和）
    """
    if len(args) != 1:
        raise GeoError("Length 需要 1 个对象")
    el = _resolve(cons, args[0])
    kind = el.kind
    if kind == "segment":
        return _mk(cons, GeoNumber, "number", defn, [el],
                   lambda d: {"value": _dist((d[0].x1, d[0].y1), (d[0].x2, d[0].y2))})
    if kind == "vector":
        return _mk(cons, GeoNumber, "number", defn, [el],
                   lambda d: {"value": math.hypot(float(d[0].dx), float(d[0].dy))})
    if kind == "polyline":
        return _mk(cons, GeoNumber, "number", defn, [el],
                   lambda d: {"value": _polyline_length(d[0])})
    if kind == "arc":
        # 扇形与圆弧都取弧长（曲线长度；扇形的两条半径属于 Perimeter）
        return _mk(cons, GeoNumber, "number", defn, [el],
                   lambda d: {"value": _arc_length(d[0])})
    if kind == "circle":
        return _mk(cons, GeoNumber, "number", defn, [el],
                   lambda d: {"value": 2 * math.pi * d[0].r})
    if kind == "conic":
        ctype = getattr(el, "ctype", "")
        if ctype in ("ellipse", "circle"):
            def _conic_len(d):
                a = float(d[0].semi_a or 0.0)
                b = float(d[0].semi_b or a)
                return {"value": _ellipse_circumference(a, b)}
            return _mk(cons, GeoNumber, "number", defn, [el], _conic_len)
        raise GeoError("Length：双曲线/抛物线/一般圆锥曲线长度无定义")
    if kind == "list":
        return _mk(cons, GeoNumber, "number", defn, [el], lambda d: {"value": float(len(d[0].items))})
    raise GeoError("Length 需要 线段/向量/折线/圆弧/扇形/圆/椭圆 或 列表")
