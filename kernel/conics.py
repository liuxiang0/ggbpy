"""圆锥曲线命令（椭圆/双曲线/抛物线/五点圆锥/焦点/直径/极线/隐式/参数曲线，P2 结构拆分：从 commands.py 抽出）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .calculus import _cmd_of
from .cmd_util import _mk, _num_deps, _point_arg, _resolve, label_of
from .geo2d import _linear
from .geom_util import conic_canonical, conic_classify, conic_from_five_points
from .primitives import _dist
from .elements import GeoConic, GeoCurve, GeoError, GeoImplicit, GeoNumber, GeoPoint, GeoPolar
from .tolerance import EPSILON
import re
from .parser import eval_number


__all__ = [
    "_cmd_diameter",
    "_curve_compute",
    "_cmd_parametric",
    "_cmd_polar",
    "_cmd_implicit",
    "_mk_conic",
    "_conic_from_canonical",
    "_cmd_ellipse",
    "_cmd_hyperbola",
    "_cmd_parabola",
    "_cmd_conic5",
    "_cmd_focus",
]


def _cmd_diameter(cons, defn, args):
    el = _resolve(cons, args[0])
    if el.kind == "circle":
        return _mk(cons, GeoNumber, "number", defn, [el], lambda d: {"value": 2 * d[0].r})
    if el.kind == "arc":
        return _mk(cons, GeoNumber, "number", defn, [el], lambda d: {"value": 2 * d[0].r})
    raise GeoError("Diameter 需要 圆 或 圆弧")

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
