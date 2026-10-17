"""二维几何基元与变换算法（从 kernel/commands.py 抽出，P2 结构拆分）。

只依赖 math / numpy / tolerance 与 elements（GeoError），不依赖命令层：
- 基元状态：点/直线（一般式与法式）、函数、圆锥曲线参数化（_linear/_line_state/
  _line_through/_fn_state/_conic_t）
- 变换：平移/旋转/反射（点与直线、关于直线或点）、位似，以及统一的
  _transform_fn（按对象类型分派，支持 2D/3D 元素）
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .elements import GeoError
from .tolerance import COARSE, COORD, EPSILON, NEGLIGIBLE  # 统一数值容差（见 kernel/tolerance.py）

__all__ = [
    "_linear",
    "_line_through",
    "_reflect_point_line",
    "_reflect_point_point",
    "_rotate",
    "_line_state",
    "_dilate_pt",
    "_transform_fn",
    "_reflect_lin",
    "_reflect_lin_xy",
    "_reflected_line",
    "_reflected_point_line",
    "_rotated_line",
    "_fn_state",
    "_conic_t",
    "_dilated_line",
]


def _linear(obj) -> Tuple[float, float, float]:
    """把 line/segment/ray 统一为直线 ax+by+c=0。"""
    if obj.kind == "line":
        return obj.a, obj.b, obj.c
    if obj.kind == "segment":
        x1, y1, x2, y2 = obj.x1, obj.y1, obj.x2, obj.y2
        return _line_through(x1, y1, x2, y2)
    if obj.kind == "ray":
        return _line_through(obj.ox, obj.oy, obj.ox + obj.dx, obj.oy + obj.dy)
    raise GeoError("对象 " + obj.label + " 不是直线类对象")

def _line_through(x1, y1, x2, y2) -> Tuple[float, float, float]:
    a = y1 - y2
    b = x2 - x1
    c = x1 * y2 - x2 * y1
    norm = max(abs(a), abs(b), abs(c), NEGLIGIBLE)
    return a / norm, b / norm, c / norm

def _reflect_point_line(x, y, a, b, c) -> Tuple[float, float]:
    denom = a * a + b * b
    if denom < EPSILON:
        return x, y
    k = 2 * (a * x + b * y + c) / denom
    return x - a * k, y - b * k

def _reflect_point_point(x, y, cx, cy) -> Tuple[float, float]:
    return 2 * cx - x, 2 * cy - y

def _rotate(x, y, th, cx, cy) -> Tuple[float, float]:
    dx, dy = x - cx, y - cy
    cos, sin = math.cos(th), math.sin(th)
    return cx + dx * cos - dy * sin, cy + dx * sin + dy * cos

def _line_state(a, b, c) -> Dict[str, float]:
    return {"a": a, "b": b, "c": c}

def _dilate_pt(x, y, k, cx, cy):
    return (cx + k * (x - cx), cy + k * (y - cy))

def _transform_fn(op, kind, extra):
    if op == "translate":
        dx, dy, dz = extra
        if kind == "point":
            def _tp(d):
                st = {"x": d[0].x + dx, "y": d[0].y + dy}
                # 三维点（带 z）平移时 z 也随位移更新；二维点保持无 z
                if dz != 0.0 or d[0].z is not None:
                    st["z"] = (d[0].z or 0.0) + dz
                return st
            return _tp
        if kind == "segment":
            return lambda d: {"x1": d[0].x1 + dx, "y1": d[0].y1 + dy,
                              "x2": d[0].x2 + dx, "y2": d[0].y2 + dy}
        if kind == "ray":
            return lambda d: {"ox": d[0].ox + dx, "oy": d[0].oy + dy,
                              "dx": d[0].dx, "dy": d[0].dy}
        if kind == "circle":
            return lambda d: {"cx": d[0].cx + dx, "cy": d[0].cy + dy, "r": d[0].r}
        if kind == "polygon":
            return lambda d: {"xs": [x + dx for x in d[0].xs], "ys": [y + dy for y in d[0].ys]}
        if kind == "line":
            return lambda d: _line_state(d[0].a, d[0].b, d[0].c - d[0].a * dx - d[0].b * dy)
    if op == "rotate":
        th, center = extra
        cxp, cyp = (center.x, center.y) if center is not None else (0.0, 0.0)
        if kind == "point":
            def _rp(d):
                st = dict(zip(("x", "y"), _rotate(d[0].x, d[0].y, th, cxp, cyp)))
                # 三维点：绕「过中心、平行 z 轴」的轴旋转，z 分量不变
                if d[0].z is not None:
                    st["z"] = d[0].z
                return st
            return _rp
        if kind == "segment":
            def _rs(d):
                p1 = _rotate(d[0].x1, d[0].y1, th, cxp, cyp)
                p2 = _rotate(d[0].x2, d[0].y2, th, cxp, cyp)
                return {"x1": p1[0], "y1": p1[1], "x2": p2[0], "y2": p2[1]}
            return _rs
        if kind == "ray":
            def _rr(d):
                o = _rotate(d[0].ox, d[0].oy, th, cxp, cyp)
                e = _rotate(d[0].ox + d[0].dx, d[0].oy + d[0].dy, th, cxp, cyp)
                return {"ox": o[0], "oy": o[1], "dx": e[0] - o[0], "dy": e[1] - o[1]}
            return _rr
        if kind == "circle":
            def _rc(d):
                c = _rotate(d[0].cx, d[0].cy, th, cxp, cyp)
                return {"cx": c[0], "cy": c[1], "r": d[0].r}
            return _rc
        if kind == "polygon":
            def _rp(d):
                pts = [_rotate(x, y, th, cxp, cyp) for x, y in zip(d[0].xs, d[0].ys)]
                return {"xs": [p[0] for p in pts], "ys": [p[1] for p in pts]}
            return _rp
        if kind == "line":
            def _rl(d):
                return _rotated_line(d[0], th, cxp, cyp)
            return _rl
    if op == "reflect_line":
        mirror = extra[0]
        if kind == "point":
            return lambda d: dict(zip(("x", "y"), _reflect_lin(d[0], mirror)))
        if kind == "segment":
            def _f(d):
                p1 = _reflect_lin_xy(d[0].x1, d[0].y1, mirror)
                p2 = _reflect_lin_xy(d[0].x2, d[0].y2, mirror)
                return {"x1": p1[0], "y1": p1[1], "x2": p2[0], "y2": p2[1]}
            return _f
        if kind == "ray":
            def _f(d):
                o = _reflect_lin_xy(d[0].ox, d[0].oy, mirror)
                e = _reflect_lin_xy(d[0].ox + d[0].dx, d[0].oy + d[0].dy, mirror)
                return {"ox": o[0], "oy": o[1], "dx": e[0] - o[0], "dy": e[1] - o[1]}
            return _f
        if kind == "circle":
            def _f(d):
                c = _reflect_lin_xy(d[0].cx, d[0].cy, mirror)
                return {"cx": c[0], "cy": c[1], "r": d[0].r}
            return _f
        if kind == "polygon":
            def _f(d):
                pts = [_reflect_lin_xy(x, y, mirror) for x, y in zip(d[0].xs, d[0].ys)]
                return {"xs": [p[0] for p in pts], "ys": [p[1] for p in pts]}
            return _f
        if kind == "line":
            def _f(d):
                return _reflected_line(d[0], mirror)
            return _f
    if op == "reflect_point":
        mp = extra[0]
        if kind == "point":
            return lambda d: dict(zip(("x", "y"), _reflect_point_point(d[0].x, d[0].y, mp.x, mp.y)))
        if kind == "segment":
            def _f(d):
                p1 = _reflect_point_point(d[0].x1, d[0].y1, mp.x, mp.y)
                p2 = _reflect_point_point(d[0].x2, d[0].y2, mp.x, mp.y)
                return {"x1": p1[0], "y1": p1[1], "x2": p2[0], "y2": p2[1]}
            return _f
        if kind == "ray":
            def _f(d):
                o = _reflect_point_point(d[0].ox, d[0].oy, mp.x, mp.y)
                e = _reflect_point_point(d[0].ox + d[0].dx, d[0].oy + d[0].dy, mp.x, mp.y)
                return {"ox": o[0], "oy": o[1], "dx": e[0] - o[0], "dy": e[1] - o[1]}
            return _f
        if kind == "circle":
            def _f(d):
                c = _reflect_point_point(d[0].cx, d[0].cy, mp.x, mp.y)
                return {"cx": c[0], "cy": c[1], "r": d[0].r}
            return _f
        if kind == "polygon":
            def _f(d):
                pts = [_reflect_point_point(x, y, mp.x, mp.y) for x, y in zip(d[0].xs, d[0].ys)]
                return {"xs": [p[0] for p in pts], "ys": [p[1] for p in pts]}
            return _f
        if kind == "line":
            def _f(d):
                return _reflected_point_line(d[0], mp)
            return _f
    # ---- Polyline / Vector / Function / Conic ----
    if kind == "polyline":
        if op == "translate":
            dx, dy = extra
            return lambda d: {"xs": [x + dx for x in d[0].xs], "ys": [y + dy for y in d[0].ys]}
        th, center = extra if op in ("rotate", "dilate") else (0, None)
        cxp, cyp = (center.x, center.y) if center is not None else (0.0, 0.0)
        if op == "rotate":
            def _f(d):
                pts = [_rotate(x, y, th, cxp, cyp) for x, y in zip(d[0].xs, d[0].ys)]
                return {"xs": [p[0] for p in pts], "ys": [p[1] for p in pts]}
            return _f
        if op == "reflect_line":
            mirror = extra[0]
            def _f(d):
                pts = [_reflect_lin_xy(x, y, mirror) for x, y in zip(d[0].xs, d[0].ys)]
                return {"xs": [p[0] for p in pts], "ys": [p[1] for p in pts]}
            return _f
        if op == "reflect_point":
            m = extra[0]
            def _f(d):
                pts = [_reflect_point_point(x, y, m.x, m.y) for x, y in zip(d[0].xs, d[0].ys)]
                return {"xs": [p[0] for p in pts], "ys": [p[1] for p in pts]}
            return _f
        if op == "dilate":
            k = extra[0]
            def _f(d):
                pts = [_dilate_pt(x, y, k, cxp, cyp) for x, y in zip(d[0].xs, d[0].ys)]
                return {"xs": [p[0] for p in pts], "ys": [p[1] for p in pts]}
            return _f
    if kind == "vector":
        if op == "translate":
            dx, dy = extra
            return lambda d: {"dx": d[0].dx + dx, "dy": d[0].dy + dy}
        if op == "rotate":
            th2 = extra[0]
            return lambda d: dict(zip(("dx", "dy"), _rotate(d[0].dx, d[0].dy, th2, 0.0, 0.0)))
        if op == "reflect_line":
            mirror = extra[0]
            return lambda d: dict(zip(("dx", "dy"), _reflect_lin_xy(d[0].dx, d[0].dy, mirror)))
        if op == "reflect_point":
            return lambda d: {"dx": -d[0].dx, "dy": -d[0].dy}
        if op == "dilate":
            k = extra[0]
            return lambda d: {"dx": k * d[0].dx, "dy": k * d[0].dy}
    if kind == "function":
        import sympy
        if op == "translate":
            dx, dy = extra
            return lambda d: _fn_state(d[0], lambda x: d[0].expr.subs(x, x - dx) + dy)
        if op == "reflect_line":
            mirror = extra[0]
            a, b, c = _linear(mirror)
            if abs(a) < COORD:      # 水平线 y=k → 2k - f(x)
                k = -c / b
                return lambda d: _fn_state(d[0], lambda x: 2 * k - d[0].expr)
            if abs(b) < COORD:      # 垂直线 x=h → f(2h - x)
                h = -c / a
                return lambda d: _fn_state(d[0], lambda x: d[0].expr.subs(x, 2 * h - x))
            raise GeoError("函数只能沿水平或垂直线反射")
        if op == "reflect_point":
            m = extra[0]
            return lambda d: _fn_state(d[0], lambda x: 2 * m.y - d[0].expr.subs(x, 2 * m.x - x))
        if op == "dilate":
            k = extra[0]
            return lambda d: _fn_state(d[0], lambda x: k * d[0].expr)
        raise GeoError("函数暂不支持该变换")
    if kind == "conic":
        if op == "translate":
            dx, dy = extra
            return lambda d: _conic_t(d[0], cx=d[0].cx + dx, cy=d[0].cy + dy)
        if op == "rotate":
            th2 = extra[0]
            cx2, cy2 = (extra[1].x, extra[1].y) if extra[1] is not None else (0.0, 0.0)

            def _f(d):
                c = _rotate(d[0].cx, d[0].cy, th2, cx2, cy2)
                return _conic_t(d[0], cx=c[0], cy=c[1], angle=d[0].angle + th2)
            return _f
        if op == "reflect_line":
            mirror = extra[0]
            def _f(d):
                c = _reflect_lin_xy(d[0].cx, d[0].cy, mirror)
                a, b, _ = _linear(mirror)
                phi = math.atan2(a, -b)
                return _conic_t(d[0], cx=c[0], cy=c[1], angle=2 * phi - d[0].angle)
            return _f
        if op == "reflect_point":
            m = extra[0]
            def _f(d):
                c = _reflect_point_point(d[0].cx, d[0].cy, m.x, m.y)
                return _conic_t(d[0], cx=c[0], cy=c[1], angle=d[0].angle + math.pi)
            return _f
        if op == "dilate":
            k2 = extra[0]
            cx2, cy2 = (extra[1].x, extra[1].y) if extra[1] is not None else (0.0, 0.0)

            def _f(d):
                c = _dilate_pt(d[0].cx, d[0].cy, k2, cx2, cy2)
                return _conic_t(d[0], cx=c[0], cy=c[1],
                                a=abs(k2) * d[0].semi_a, b=abs(k2) * d[0].semi_b,
                                angle=d[0].angle + (math.pi if k2 < 0 else 0))
            return _f
    # ---- Dilate（位似）：经典类型 ----
    if op == "dilate":
        k, center = extra
        cxp, cyp = (center.x, center.y) if center is not None else (0.0, 0.0)
        if kind == "point":
            return lambda d: dict(zip(("x", "y"), _dilate_pt(d[0].x, d[0].y, k, cxp, cyp)))
        if kind == "segment":
            def _f(d):
                p1 = _dilate_pt(d[0].x1, d[0].y1, k, cxp, cyp)
                p2 = _dilate_pt(d[0].x2, d[0].y2, k, cxp, cyp)
                return {"x1": p1[0], "y1": p1[1], "x2": p2[0], "y2": p2[1]}
            return _f
        if kind == "ray":
            def _f(d):
                o = _dilate_pt(d[0].ox, d[0].oy, k, cxp, cyp)
                return {"ox": o[0], "oy": o[1], "dx": k * d[0].dx, "dy": k * d[0].dy}
            return _f
        if kind == "circle":
            return lambda d: {"cx": _dilate_pt(d[0].cx, d[0].cy, k, cxp, cyp)[0],
                              "cy": _dilate_pt(d[0].cx, d[0].cy, k, cxp, cyp)[1],
                              "r": abs(k) * d[0].r}
        if kind == "polygon":
            def _f(d):
                pts = [_dilate_pt(x, y, k, cxp, cyp) for x, y in zip(d[0].xs, d[0].ys)]
                return {"xs": [p[0] for p in pts], "ys": [p[1] for p in pts]}
            return _f
        if kind == "line":
            def _f(d):
                return _dilated_line(d[0], k, cxp, cyp)
            return _f
    raise GeoError("不支持的变换组合")

def _reflect_lin(pt, mirror):
    a, b, c = _linear(mirror)
    return _reflect_point_line(pt.x, pt.y, a, b, c)

def _reflect_lin_xy(x, y, mirror):
    a, b, c = _linear(mirror)
    return _reflect_point_line(x, y, a, b, c)

def _reflected_line(line, mirror):
    a, b, c = _linear(mirror)
    a0, b0, c0 = line.a, line.b, line.c
    norm = math.hypot(a0, b0)
    if norm < EPSILON:
        raise GeoError("退化的直线")
    p0x = -a0 * c0 / (norm * norm)
    p0y = -b0 * c0 / (norm * norm)
    dx, dy = -b0 / norm, a0 / norm
    p1 = _reflect_point_line(p0x, p0y, a, b, c)
    p2 = _reflect_point_line(p0x + dx, p0y + dy, a, b, c)
    return _line_state(*_line_through(p1[0], p1[1], p2[0], p2[1]))

def _reflected_point_line(line, mp):
    a0, b0, c0 = line.a, line.b, line.c
    norm = math.hypot(a0, b0)
    if norm < EPSILON:
        raise GeoError("退化的直线")
    p0x = -a0 * c0 / (norm * norm)
    p0y = -b0 * c0 / (norm * norm)
    dx, dy = -b0 / norm, a0 / norm
    p1 = _reflect_point_point(p0x, p0y, mp.x, mp.y)
    p2 = _reflect_point_point(p0x + dx, p0y + dy, mp.x, mp.y)
    return _line_state(*_line_through(p1[0], p1[1], p2[0], p2[1]))

def _rotated_line(line, th, cxp, cyp):
    a0, b0, c0 = line.a, line.b, line.c
    norm = math.hypot(a0, b0)
    if norm < EPSILON:
        raise GeoError("退化的直线")
    p0x = -a0 * c0 / (norm * norm)
    p0y = -b0 * c0 / (norm * norm)
    p1 = _rotate(p0x, p0y, th, cxp, cyp)
    dx, dy = _rotate(p0x - b0 / norm, p0y + a0 / norm, th, cxp, cyp)
    p2 = (dx, dy)
    return _line_state(*_line_through(p1[0], p1[1], p2[0], p2[1]))

def _fn_state(f, expr_fn):
    """函数变换状态：把 f.expr 经 expr_fn 变形后返回新函数状态。"""
    import sympy
    x = f.xsym
    expr = expr_fn(x)
    return {"expr": sympy.expand(expr), "xsym": x, "body": "", "_lamb": None}

def _conic_t(cn, cx=None, cy=None, a=None, b=None, angle=None):
    """由变换后的规范参数重建圆锥曲线系数（5 点法）。"""
    import math as _m
    from .geom_util import conic_classify, conic_from_five_points
    ncx = cn.cx if cx is None else cx
    ncy = cn.cy if cy is None else cy
    na = cn.semi_a if a is None else a
    nb = cn.semi_b if b is None else b
    nang = cn.angle if angle is None else angle
    ctype = cn.ctype
    pts = []
    if ctype in ("ellipse", "circle"):
        for t in (0.0, _m.pi / 2, _m.pi, 1.5 * _m.pi, _m.pi / 4):
            xl, yl = na * _m.cos(t), nb * _m.sin(t)
            pts.append((ncx + xl * _m.cos(nang) - yl * _m.sin(nang),
                        ncy + xl * _m.sin(nang) + yl * _m.cos(nang)))
    elif ctype == "hyperbola":
        for t in (-1.6, -0.7, 0.7, 1.6, 0.0):
            xl, yl = na * _m.cosh(t), nb * _m.sinh(t)
            pts.append((ncx + xl * _m.cos(nang) - yl * _m.sin(nang),
                        ncy + xl * _m.sin(nang) + yl * _m.cos(nang)))
    elif ctype == "parabola":
        p = na or 1.0
        ux, uy = _m.cos(nang), _m.sin(nang)
        vx, vy = -uy, ux
        for t in (-5.0, -2.5, 0.0, 2.5, 5.0):
            pts.append((ncx + t * vx + t * t / (4 * p) * ux,
                        ncy + t * vy + t * t / (4 * p) * uy))
    else:
        raise GeoError("一般圆锥曲线暂不支持变换")
    coeffs = conic_from_five_points(pts)
    if coeffs is None:
        raise GeoError("变换后的圆锥曲线退化")
    focus = None
    if ctype == "parabola":
        focus = (ncx + na * _m.cos(nang), ncy + na * _m.sin(nang))
    return {"a": coeffs[0], "b": coeffs[1], "c": coeffs[2],
            "d": coeffs[3], "e": coeffs[4], "f": coeffs[5],
            "ctype": conic_classify(*coeffs),
            "cx": ncx, "cy": ncy, "semi_a": na, "semi_b": nb, "angle": nang,
            "focus": focus, "directrix": cn.directrix}

def _dilated_line(line, k, cxp, cyp):
    """位似变换直线：取线上两点变换后重建。"""
    a0, b0, c0 = line.a, line.b, line.c
    norm = math.hypot(a0, b0)
    if norm < EPSILON:
        raise GeoError("退化的直线")
    p0x = -a0 * c0 / (norm * norm)
    p0y = -b0 * c0 / (norm * norm)
    dx, dy = -b0 / norm, a0 / norm
    p1 = _dilate_pt(p0x, p0y, k, cxp, cyp)
    p2 = _dilate_pt(p0x + dx, p0y + dy, k, cxp, cyp)
    return _line_state(*_line_through(p1[0], p1[1], p2[0], p2[1]))

# ---------------------------------------------------------------------------
# 弧长 / 折线长度（度量命令共用；放在几何层供 measures 与 3D 命令复用）
# ---------------------------------------------------------------------------
def _arc_span(el) -> float:
    """圆弧/扇形的**圆心角跨度**（弧度，0..2π；Semicircle 等价 a2=a1+π，端点重合取 0）。"""
    a1 = float(getattr(el, "ang1", 0.0))
    a2 = float(getattr(el, "ang2", 0.0))
    if getattr(el, "semicircle", False):
        a2 = a1 + math.pi
    span = (a2 - a1) % (2.0 * math.pi)
    return 0.0 if span < EPSILON else span


def _arc_length(el) -> float:
    """圆弧/扇形的**弧长**（不含半径边；与画布/导出同一套角度语义）。"""
    return float(getattr(el, "r", 0.0)) * _arc_span(el)


def _polyline_length(el) -> float:
    """折线总长（相邻顶点距离之和，不闭合）。顶点在 `.xs/.ys`（不是 `.pts`）。"""
    xs = [float(v) for v in (getattr(el, "xs", None) or [])]
    ys = [float(v) for v in (getattr(el, "ys", None) or [])]
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    return sum(math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]) for i in range(len(xs) - 1))

