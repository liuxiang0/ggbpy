"""仿射变换命令（反射/旋转/平移/位似/反演，P2 结构拆分：从 commands.py 抽出）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .cmd_util import _label_of, _mk, _resolve
from .geo2d import _linear, _transform_fn
from .primitives import _resolve_vector3
from .elements import GeoCircle, GeoConic, GeoCurve, GeoError, GeoFunction, GeoImplicit, GeoLine, GeoPoint, GeoPolygon, GeoPolyline, GeoRay, GeoSegment, GeoVector
from .tolerance import COORD, EPSILON, ZERO_SQ
from .parser import eval_number


__all__ = [
    "DEG",
    "_cmd_translate",
    "_cmd_rotate",
    "_cmd_reflect",
    "_transform_mk",
    "_inv_map",
    "_inv_circle_params",
    "_inv_linear_state",
    "_inv_circle_conic_state",
    "_inv_line_conic_state",
    "_source_chains",
    "_inv_sampled_state",
    "_invert_implicit_state",
    "_mk_implicit",
    "_mk_param_curve",
    "_compose_inv",
    "_seg_pole",
    "_cmd_invert",
    "_cmd_dilate",
]


DEG = math.pi / 180.0


def _cmd_translate(cons, label, args):
    if len(args) != 2:
        raise GeoError("Translate 需要 对象 和 向量")
    obj = _resolve(cons, args[0])
    dx, dy, dz = _resolve_vector3(cons, args[1])
    return _transform_mk(cons, label, obj, "translate", (dx, dy, dz))

def _cmd_rotate(cons, label, args):
    if len(args) not in (2, 3):
        raise GeoError("Rotate 需要 对象、角度 和 可选中心点")
    obj = _resolve(cons, args[0])
    ang = eval_number(cons, args[1]) * DEG
    if len(args) == 3:
        center = _resolve(cons, args[2], ("point",))
        return _transform_mk(cons, label, obj, "rotate", (ang, center))
    return _transform_mk(cons, label, obj, "rotate", (ang, None))

def _cmd_reflect(cons, label, args):
    if len(args) != 2:
        raise GeoError("Reflect 需要 对象 和 直线或点")
    obj = _resolve(cons, args[0])
    ms = args[1].strip().lower()
    if ms in ("x", "xaxis", "x-axis", "x轴"):
        # 匿名 x 轴（y=0）
        mirror = GeoLine("_axis", "x轴")
        mirror.a, mirror.b, mirror.c = 0.0, 1.0, 0.0
        return _transform_mk(cons, label, obj, "reflect_line", (mirror,))
    if ms in ("y", "yaxis", "y-axis", "y轴"):
        mirror = GeoLine("_axis", "y轴")
        mirror.a, mirror.b, mirror.c = 1.0, 0.0, 0.0
        return _transform_mk(cons, label, obj, "reflect_line", (mirror,))
    mirror = _resolve(cons, args[1])
    if mirror.kind in ("line", "segment", "ray"):
        return _transform_mk(cons, label, obj, "reflect_line", (mirror,))
    if mirror.kind == "point":
        return _transform_mk(cons, label, obj, "reflect_point", (mirror,))
    raise GeoError("Reflect 的镜像是直线或点")

def _transform_mk(cons, label, obj, op, extra):
    k = obj.kind
    kind_map = {
        "point": "point", "segment": "segment", "ray": "ray", "circle": "circle",
        "polygon": "polygon", "line": "line", "polyline": "polyline",
        "vector": "vector", "function": "function", "conic": "conic",
    }
    if k not in kind_map:
        raise GeoError("变换暂不支持 " + k + " 对象")
    cls_map = {
        "point": GeoPoint, "segment": GeoSegment, "ray": GeoRay,
        "circle": GeoCircle, "polygon": GeoPolygon, "line": GeoLine,
        "polyline": GeoPolyline, "vector": GeoVector,
        "function": GeoFunction, "conic": GeoConic,
    }
    deps = [obj] + [e for e in extra if hasattr(e, "kind")]
    fn = _transform_fn(op, k, extra)
    return _mk(cons, cls_map[k], kind_map[k], label, deps, fn)

def _inv_map(px, py, ox, oy, r):
    """点 (px,py) 关于反演圆 (O,r) 的像：OP·OP' = r²，像与原像同向。"""
    dx, dy = px - ox, py - oy
    d2 = dx * dx + dy * dy
    if d2 < ZERO_SQ:
        raise GeoError("对象经过反演圆心，其像在无穷远处")
    k = r * r / d2
    return ox + dx * k, oy + dy * k

def _inv_circle_params(dep):
    """从反演圆对象取 (cx, cy, r)；圆类圆锥曲线亦接受。"""
    if dep.kind == "circle":
        return dep.cx, dep.cy, dep.r
    if dep.kind == "conic" and getattr(dep, "ctype", "") == "circle":
        return dep.cx, dep.cy, dep.semi_a
    raise GeoError("反演圆需要圆（Circle）对象")

def _inv_linear_state(a, b, c):
    """线性方程 a x + b y + c = 0 的 GeoConic 状态（直线情形）。"""
    return {"a": 0.0, "b": 0.0, "c": 0.0, "d": a, "e": b, "f": c,
            "ctype": "general", "cx": 0.0, "cy": 0.0,
            "semi_a": 0.0, "semi_b": 0.0, "angle": 0.0}

def _inv_circle_conic_state(cx, cy, rr, ox, oy, r):
    """圆的反演：一般情形仍是圆；过反演圆心时退化为直线（GeoConic 统一表示）。"""
    dx, dy = cx - ox, cy - oy
    d2 = dx * dx + dy * dy
    den = d2 - rr * rr
    if abs(den) < COORD:
        # 过反演圆心：像为直线 (q-O)·(C-O) = r²/2
        A = dx
        B = dy
        C = -(dx * ox + dy * oy) - r * r / 2.0
        return _inv_linear_state(A, B, C)
    k = r * r / den
    ncx = ox + dx * k
    ncy = oy + dy * k
    nr = abs(k) * rr
    if nr < EPSILON:
        raise GeoError("反演退化")
    return {"a": 1.0, "b": 0.0, "c": 1.0,
            "d": -2.0 * ncx, "e": -2.0 * ncy,
            "f": ncx * ncx + ncy * ncy - nr * nr,
            "ctype": "circle", "cx": ncx, "cy": ncy,
            "semi_a": nr, "semi_b": nr, "angle": 0.0}

def _inv_line_conic_state(line, ox, oy, r):
    """直线反演：不过圆心 → 过圆心的圆；过圆心 → 自身直线。"""
    a, b, c = _linear(line)
    n = math.hypot(a, b)
    if n < EPSILON:
        raise GeoError("退化直线")
    dist = (a * ox + b * oy + c) / n
    if abs(dist) < EPSILON:
        return _inv_linear_state(a, b, c)
    rr = r * r / (2 * abs(dist))
    ncx = ox - a / n * (r * r / (2 * dist))
    ncy = oy - b / n * (r * r / (2 * dist))
    return {"a": 1.0, "b": 0.0, "c": 1.0,
            "d": -2.0 * ncx, "e": -2.0 * ncy,
            "f": ncx * ncx + ncy * ncy - rr * rr,
            "ctype": "circle", "cx": ncx, "cy": ncy,
            "semi_a": rr, "semi_b": rr, "angle": 0.0}

def _source_chains(el, ox=0.0, oy=0.0, r=1.0):
    """取源对象的采样折线链（世界坐标），返回 (chains, densify)。"""
    k = el.kind
    if k == "segment":
        return ([[(el.x1, el.y1), (el.x2, el.y2)]], True)
    if k == "vector":
        return ([[(el.sx, el.sy), (el.sx + el.dx, el.sy + el.dy)]], True)
    if k == "ray":
        n = math.hypot(el.dx, el.dy)
        if n < EPSILON:
            raise GeoError("退化射线")
        # 远端取到像点落入反演圆心附近（|像-O| = r²/|P-O| ≤ r/200）
        dist0 = math.hypot(el.ox - ox, el.oy - oy)
        far = 200.0 * r + dist0 + 1.0
        ux, uy = el.dx / n, el.dy / n
        m = 48
        pts = [(el.ox + ux * far * i / m, el.oy + uy * far * i / m) for i in range(m + 1)]
        return ([pts], False)
    if k == "polyline":
        if len(el.xs) < 2:
            raise GeoError("折线点数不足")
        return ([list(zip(el.xs, el.ys))], True)
    if k == "polygon":
        if len(el.xs) < 3:
            raise GeoError("多边形顶点不足")
        pts = list(zip(el.xs, el.ys))
        pts.append(pts[0])
        return ([pts], True)
    if k == "arc":
        sweep = (el.ang2 - el.ang1) % (2 * math.pi)
        n = 72
        pts = [(el.cx + el.r * math.cos(el.ang1 + sweep * i / n),
                el.cy + el.r * math.sin(el.ang1 + sweep * i / n)) for i in range(n + 1)]
        if getattr(el, "sector", False):
            pts.append((el.cx, el.cy))
            pts.append(pts[0])
        return ([pts], False)
    if k in ("parametric", "polar"):
        pts = [(p[0], p[1]) for p in el._sample()]
        if len(pts) < 2:
            raise GeoError("曲线采样点不足")
        return ([pts], False)
    if k == "locus":
        pts = [(p[0], p[1]) for p in el.pts]
        if len(pts) < 2:
            raise GeoError("轨迹点数不足")
        return ([pts], False)
    raise GeoError("反演暂不支持 " + k + " 类型对象")

def _inv_sampled_state(el, ox, oy, r):
    """采样反演：把源对象采样成折线，逐点反演。"""
    chains, densify = _source_chains(el, ox, oy, r)
    xs, ys = [], []
    for ch in chains:
        pts = []
        if densify:
            for i in range(len(ch) - 1):
                (x1, y1), (x2, y2) = ch[i], ch[i + 1]
                m = 96
                for j in range(m):
                    t = j / m
                    pts.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
            pts.append(ch[-1])
        else:
            pts = list(ch)
        for (px, py) in pts:
            qx, qy = _inv_map(px, py, ox, oy, r)
            xs.append(qx)
            ys.append(qy)
    return {"xs": xs, "ys": ys}

def _invert_implicit_state(src, circ):
    """圆锥曲线 / 函数 / 隐式曲线的反演：把反演映射复合进隐式方程（精确四次曲线）。"""
    import sympy
    ox, oy, r = _inv_circle_params(circ)
    x, y = sympy.symbols("x y")
    s = (x - ox) ** 2 + (y - oy) ** 2
    X = ox + r * r * (x - ox) / s
    Y = oy + r * r * (y - oy) / s
    if src.kind == "conic":
        a, b, c = src.a, src.b, src.c
        d, e, f = src.d, src.e, src.f
        F = a * X ** 2 + b * X * Y + c * Y ** 2 + d * X + e * Y + f
        return {"f_expr": sympy.expand(F * s ** 2)}
    if src.kind == "function":
        if src.expr is None:
            raise GeoError("函数尚未就绪")
        F = Y - src.expr.subs(src.xsym, X)
        try:
            num = sympy.fraction(sympy.together(F))[0]   # 去分母（可去极点，如原点）
            F = num
        except Exception:
            pass
        return {"f_expr": sympy.expand(F)}
    if src.kind == "implicit":
        if src.f_expr is None:
            raise GeoError("隐式曲线尚未就绪")
        F = src.f_expr.subs({sympy.Symbol("x"): X, sympy.Symbol("y"): Y})
        try:
            num = sympy.fraction(sympy.together(F))[0]
            F = num
        except Exception:
            pass
        return {"f_expr": sympy.expand(F)}
    raise GeoError("反演暂不支持 " + src.kind + " 类型对象")

def _mk_implicit(cons, defn, deps, fn):
    el = GeoImplicit(_label_of(defn), defn, "")
    el.free = False
    el.set_deps(deps, fn)
    return cons.add(el)

def _mk_param_curve(cons, defn, deps, fn):
    """参数曲线元素：复合反演映射后由曲线元素按参数域采样绘制（光滑）。"""
    el = GeoCurve(_label_of(defn), defn, "", "", "t", 0.0, 1.0)
    el.free = False
    el.set_deps(deps, fn)
    return cons.add(el)

def _compose_inv(px, py, ox, oy, r):
    """把反演映射复合到参数方程 (px(t), py(t))：返回像的 (X(t), Y(t))。"""
    r2 = r * r
    s = (px - ox) ** 2 + (py - oy) ** 2
    return ox + r2 * (px - ox) / s, oy + r2 * (py - oy) / s

def _seg_pole(ax, ay, bx, by, ox, oy):
    """若反演圆心 O 落在线段 AB 上（奇点），返回 True。"""
    dx, dy = bx - ax, by - ay
    n2 = dx * dx + dy * dy
    if n2 < ZERO_SQ:
        return math.hypot(ox - ax, oy - ay) < EPSILON
    t = ((ox - ax) * dx + (oy - ay) * dy) / n2
    if t < -COORD or t > 1 + COORD:
        return False
    px, py = ax + dx * t, ay + dy * t
    return math.hypot(ox - px, oy - py) < COORD * max(1.0, math.hypot(dx, dy))

def _cmd_invert(cons, defn, args):
    """Invert[对象, 反演圆] — 圆反演（Inversion in circle）。

    点/圆/直线 → 精确解析像；线段/射线/圆弧/向量/参数曲线/极坐标/椭圆 →
    反演映射复合参数方程（精确、光滑）；函数/双曲线/抛物线/隐式曲线 → 隐式方程；
    多边形/折线/扇形/轨迹 → 采样曲线。
    """
    if len(args) != 2:
        raise GeoError("Invert 需要 对象 和 反演圆（Circle[圆心,半径]）")
    obj = _resolve(cons, args[0])
    c0 = _resolve(cons, args[1], ("circle", "conic"))
    _inv_circle_params(c0)          # 提前校验反演圆
    deps = [obj, c0]
    k = obj.kind

    def _pt(d):
        ox, oy, r = _inv_circle_params(d[1])
        return dict(zip(("x", "y"), _inv_map(d[0].x, d[0].y, ox, oy, r)))

    def _circ(d):
        ox, oy, r = _inv_circle_params(d[1])
        return _inv_circle_conic_state(d[0].cx, d[0].cy, d[0].r, ox, oy, r)

    def _line(d):
        ox, oy, r = _inv_circle_params(d[1])
        return _inv_line_conic_state(d[0], ox, oy, r)

    def _sampled(d):
        ox, oy, r = _inv_circle_params(d[1])
        return _inv_sampled_state(d[0], ox, oy, r)

    def _implicit(d):
        return _invert_implicit_state(d[0], d[1])

    # ---- 参数方程复合（直接反演变换，按定义域限制）----
    def _segment_curve(d):
        import sympy
        t = sympy.Symbol("t")
        ox, oy, r = _inv_circle_params(d[1])
        el = d[0]
        if _seg_pole(el.x1, el.y1, el.x2, el.y2, ox, oy):
            raise GeoError("线段经过反演圆心，其像为两条射线（无界）")
        px = el.x1 + (el.x2 - el.x1) * t
        py = el.y1 + (el.y2 - el.y1) * t
        X, Y = _compose_inv(px, py, ox, oy, r)
        return {"x_expr": X, "y_expr": Y, "t0": 0.0, "t1": 1.0}

    def _vector_curve(d):
        import sympy
        t = sympy.Symbol("t")
        ox, oy, r = _inv_circle_params(d[1])
        el = d[0]
        x0, y0 = el.sx, el.sy
        x1, y1 = el.sx + el.dx, el.sy + el.dy
        if _seg_pole(x0, y0, x1, y1, ox, oy):
            raise GeoError("向量经过反演圆心，其像为两条射线（无界）")
        px = x0 + (x1 - x0) * t
        py = y0 + (y1 - y0) * t
        X, Y = _compose_inv(px, py, ox, oy, r)
        return {"x_expr": X, "y_expr": Y, "t0": 0.0, "t1": 1.0}

    def _ray_curve(d):
        import sympy
        t = sympy.Symbol("t")
        ox, oy, r = _inv_circle_params(d[1])
        el = d[0]
        n = math.hypot(el.dx, el.dy)
        if n < EPSILON:
            raise GeoError("退化射线")
        ux, uy = el.dx / n, el.dy / n
        dx0, dy0 = el.ox - ox, el.oy - oy
        perp = abs(dx0 * uy - dy0 * ux)
        pole_t = -(dx0 * ux + dy0 * uy)
        if perp < COORD * max(1.0, math.hypot(dx0, dy0)) and pole_t > -COORD:
            raise GeoError("射线经过反演圆心，其像无界")
        # 定义域限制：远端取到像点贴近反演圆心（|像-O| = r²/|P-O| ≤ r/200）
        t1 = 200.0 * r + math.hypot(dx0, dy0) + 1.0
        px = el.ox + ux * t
        py = el.oy + uy * t
        X, Y = _compose_inv(px, py, ox, oy, r)
        return {"x_expr": X, "y_expr": Y, "t0": 0.0, "t1": t1}

    def _arc_curve(d):
        import sympy
        t = sympy.Symbol("t")
        ox, oy, r = _inv_circle_params(d[1])
        el = d[0]
        cx, cy, rr = el.cx, el.cy, el.r
        sweep = (el.ang2 - el.ang1) % (2 * math.pi)
        dc = math.hypot(ox - cx, oy - cy)
        if abs(dc - rr) < COORD:
            aO = math.atan2(oy - cy, ox - cx)
            dO = (aO - el.ang1) % (2 * math.pi)
            if dO <= sweep + COORD:
                raise GeoError("圆弧经过反演圆心，其像无界")
        th = el.ang1 + sweep * t
        px = cx + rr * sympy.cos(th)
        py = cy + rr * sympy.sin(th)
        X, Y = _compose_inv(px, py, ox, oy, r)
        return {"x_expr": X, "y_expr": Y, "t0": 0.0, "t1": 1.0}

    def _parametric_curve(d):
        import sympy
        t = sympy.Symbol("t")
        ox, oy, r = _inv_circle_params(d[1])
        s = d[0]
        if s.x_expr is None or s.y_expr is None:
            raise GeoError("参数曲线尚未就绪")
        ps = sympy.Symbol(s.pname)
        xs = s.x_expr.subs(ps, t)
        ys = s.y_expr.subs(ps, t)
        X, Y = _compose_inv(xs, ys, ox, oy, r)
        return {"x_expr": X, "y_expr": Y, "t0": s.t0, "t1": s.t1}

    def _polar_curve(d):
        import sympy
        t = sympy.Symbol("t")
        ox, oy, r = _inv_circle_params(d[1])
        s = d[0]
        if s.r_expr is None:
            raise GeoError("极坐标曲线尚未就绪")
        ps = sympy.Symbol(s.pname)
        rr = s.r_expr.subs(ps, t)
        xs = rr * sympy.cos(t)
        ys = rr * sympy.sin(t)
        X, Y = _compose_inv(xs, ys, ox, oy, r)
        return {"x_expr": X, "y_expr": Y, "t0": 0.0, "t1": 2 * math.pi}

    def _ellipse_curve(d):
        import sympy
        t = sympy.Symbol("t")
        ox, oy, r = _inv_circle_params(d[1])
        cn = d[0]
        a, b, ang = cn.semi_a, cn.semi_b, cn.angle
        ca, sa = math.cos(ang), math.sin(ang)
        px = cn.cx + a * sympy.cos(t) * ca - b * sympy.sin(t) * sa
        py = cn.cy + a * sympy.cos(t) * sa + b * sympy.sin(t) * ca
        X, Y = _compose_inv(px, py, ox, oy, r)
        return {"x_expr": X, "y_expr": Y, "t0": 0.0, "t1": 2 * math.pi}

    if k == "point":
        return _mk(cons, GeoPoint, "point", defn, deps, _pt)
    if k == "circle":
        return _mk(cons, GeoConic, "conic", defn, deps, _circ)
    if k == "line":
        return _mk(cons, GeoConic, "conic", defn, deps, _line)
    if k == "conic":
        ct = getattr(obj, "ctype", "")
        if ct == "circle":
            def _circ_conic(d):
                ox, oy, r = _inv_circle_params(d[1])
                return _inv_circle_conic_state(d[0].cx, d[0].cy, d[0].semi_a, ox, oy, r)
            return _mk(cons, GeoConic, "conic", defn, deps, _circ_conic)
        if ct == "ellipse":
            return _mk_param_curve(cons, defn, deps, _ellipse_curve)
        return _mk_implicit(cons, defn, deps, _implicit)
    if k in ("function", "implicit"):
        return _mk_implicit(cons, defn, deps, _implicit)
    if k == "segment":
        return _mk_param_curve(cons, defn, deps, _segment_curve)
    if k == "vector":
        return _mk_param_curve(cons, defn, deps, _vector_curve)
    if k == "ray":
        return _mk_param_curve(cons, defn, deps, _ray_curve)
    if k == "arc" and not getattr(obj, "sector", False):
        return _mk_param_curve(cons, defn, deps, _arc_curve)
    if k == "parametric":
        return _mk_param_curve(cons, defn, deps, _parametric_curve)
    if k == "polar":
        return _mk_param_curve(cons, defn, deps, _polar_curve)
    if k == "polygon":
        return _mk(cons, GeoPolygon, "polygon", defn, deps, _sampled)
    if k == "arc" and getattr(obj, "sector", False):
        return _mk(cons, GeoPolygon, "polygon", defn, deps, _sampled)
    if k in ("polyline", "locus"):
        return _mk(cons, GeoPolyline, "polyline", defn, deps, _sampled)
    raise GeoError("反演暂不支持 " + k + " 类型对象")

def _cmd_dilate(cons, label, args):
    if len(args) not in (2, 3):
        raise GeoError("Dilate 需要 对象、比例 和 可选中心点")
    obj = _resolve(cons, args[0])
    k = eval_number(cons, args[1])
    if len(args) == 3:
        center = _resolve(cons, args[2], ("point",))
        return _transform_mk(cons, label, obj, "dilate", (k, center))
    return _transform_mk(cons, label, obj, "dilate", (k, None))
