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

from .elements import (
    EPS, Geo3D, GeoAngle, GeoArc, GeoBarChart, GeoBoolean, GeoCircle, GeoConic,
    GeoBoxPlot, GeoComplex, GeoCurve, GeoError, GeoFunction, GeoImage, GeoImplicit, GeoInequality, GeoLine, GeoList,
    GeoLocus, GeoMatrix, GeoNumber, GeoPolar, GeoPoint, GeoPolygon, GeoPolyline,
    GeoPie, GeoRay, GeoResult, GeoSegment, GeoSumRect, GeoText, GeoVector,
)
from .parser import _split_commas, eval_number, parse_line

DEG = math.pi / 180.0

# 形如 "Circle[O,2]" / "Plane[A,B,C]" 的嵌套命令调用（不含赋值号）
_NESTED_CALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\[(.*)\]$", re.S)
# 嵌套命令最大层数（防御深层递归/自引用）
_NESTED_MAX_DEPTH = 4


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


def _nested_depth(cons) -> int:
    return int(getattr(cons, "_nested_depth", 0))


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
    label = shadow.auto_label(_result_kind(lname))
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


def _lookup(cons, s: str):
    """按标签查元素；参数是嵌套命令时即时求值（匿名辅助，不注册）。查不到返回 None。"""
    key = s.strip()
    el = cons.elements.get(key)
    if el is not None:
        return el
    if _NESTED_CALL_RE.match(key):
        return _eval_nested(cons, key)
    return None


def _tag3d(el, solid: str):
    """给 Geo3D 元素标注具体立体类型（objtype 保持历史值不变）。"""
    if el is not None:
        el.solid = solid
    return el


def _z_of(el) -> float:
    z = getattr(el, "z", None)
    return 0.0 if z is None else float(z)


def _has_z(*els) -> bool:
    """任一元素带显式 z（即三维点）时为真；纯二维对象全为 None。"""
    return any(getattr(e, "z", None) is not None for e in els)


def _dist3(a, b) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (_z_of(a) - _z_of(b)) ** 2)


# ---------------------------------------------------------------------------
# 解析辅助
# ---------------------------------------------------------------------------

def _resolve(cons, s: str, kinds: Optional[Tuple[str, ...]] = None):
    """把参数字符串解析为元素；kinds 非空时校验类型。"""
    s = s.strip()
    el = _lookup(cons, s)
    if el is None:
        raise GeoError("找不到对象 " + s)
    if kinds and el.kind not in kinds:
        raise GeoError(s + " 的类型是 " + el.kind + "，这里需要 " + "/".join(kinds))
    return el


def _point_arg(cons, s: str):
    """命令参数中的点：可以是标签，也可以是 (x,y) 字面量（自动创建隐藏辅助点）。"""
    s = s.strip()
    el = _lookup(cons, s)
    if el is not None:
        if el.kind != "point":
            raise GeoError(s + " 不是点")
        return el
    if s.startswith("("):
        parts = _tuple_parts_any(s)
        vals = [eval_number(cons, p) for p in parts]
        z = vals[2] if len(vals) == 3 else None
        # 匿名辅助点：不注册进构造（不可见、不参与撤销/序列化），仅作依赖
        el = GeoPoint("_h", s, vals[0], vals[1], True, z)
        el.visible = False
        return el
    raise GeoError("找不到点 " + s)


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


def _tuple_parts(s: str) -> List[str]:
    s = s.strip()
    if not (s.startswith("(") and s.endswith(")")):
        raise GeoError("需要 (a,b) 形式: " + s)
    inner = s[1:-1]
    parts = inner.split(",")
    if len(parts) != 2:
        raise GeoError("元组需要恰好两个分量: " + s)
    return [p.strip() for p in parts]


def _tuple_parts_any(s: str) -> List[str]:
    """任意分量数的元组（2 或 3 个分量）。"""
    s = s.strip()
    if not (s.startswith("(") and s.endswith(")")):
        raise GeoError("需要 (a,b) 形式: " + s)
    inner = s[1:-1]
    parts = inner.split(",")
    if len(parts) not in (2, 3):
        raise GeoError("元组需要两个或三个分量: " + s)
    return [p.strip() for p in parts]


def _number(cons, s: str):
    s = s.strip()
    el = _lookup(cons, s)
    if el is not None and el.kind in ("number", "angle"):
        return el
    raise GeoError(s + " 不是数值对象")


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
    norm = max(abs(a), abs(b), abs(c), 1e-300)
    return a / norm, b / norm, c / norm


def _intersect_lines(a1, b1, c1, a2, b2, c2) -> Optional[Tuple[float, float]]:
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-12:
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
    if d2 < -1e-9:
        return []
    # 弦半长（世界坐标）：沿单位方向 u 从垂足走到圆周的距离 = sqrt(d2)
    h = math.sqrt(max(0.0, d2))
    ux, uy = -b / math.sqrt(denom), a / math.sqrt(denom)
    return [(px + ux * h, py + uy * h), (px - ux * h, py - uy * h)]


def _circle_circle(c1x, c1y, r1, c2x, c2y, r2) -> List[Tuple[float, float]]:
    d = _dist((c1x, c1y), (c2x, c2y))
    if d < EPS:
        return []
    if d > r1 + r2 + 1e-9 or d < abs(r1 - r2) - 1e-9:
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h2 = r1 * r1 - a * a
    h = math.sqrt(max(0.0, h2))
    px = c1x + a * (c2x - c1x) / d
    py = c1y + a * (c2y - c1y) / d
    if h < 1e-9:  # 内切/外切：只有一个交点
        return [(px, py)]
    ux = -(c2y - c1y) / d
    uy = (c2x - c1x) / d
    return [(px + ux * h, py + uy * h), (px - ux * h, py - uy * h)]


def _circumcircle(p1, p2, p3) -> Optional[Tuple[float, float, float]]:
    """三点外接圆 (cx, cy, r)；共线返回 None。"""
    (x1, y1), (x2, y2), (x3, y3) = p1, p2, p3
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        return None
    ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d
    uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d
    r = _dist((ux, uy), (x1, y1))
    return ux, uy, r


def _reflect_point_line(x, y, a, b, c) -> Tuple[float, float]:
    denom = a * a + b * b
    if denom < EPS:
        return x, y
    k = 2 * (a * x + b * y + c) / denom
    return x - a * k, y - b * k


def _reflect_point_point(x, y, cx, cy) -> Tuple[float, float]:
    return 2 * cx - x, 2 * cy - y


def _rotate(x, y, th, cx, cy) -> Tuple[float, float]:
    dx, dy = x - cx, y - cy
    cos, sin = math.cos(th), math.sin(th)
    return cx + dx * cos - dy * sin, cy + dx * sin + dy * cos


# ---------------------------------------------------------------------------
# 创建派生元素的公共闭包工厂
# ---------------------------------------------------------------------------

def _mk(cons, cls, kind_for_label, defn, deps, fn):
    label = defn.split("=")[0].split(":")[0].strip()
    if not label or label[0].isdigit():
        raise GeoError("内部错误: 派生对象缺标签")
    el = cls(label, defn)
    el.free = False
    el.set_deps(deps, fn)
    return cons.add(el)


def _auto(cons, cls, kind, defn, deps, fn):
    label = cons.auto_label(kind)
    el = cls(label, defn)
    el.free = False
    el.set_deps(deps, fn)
    return cons.add(el)


# ---------------------------------------------------------------------------
# 各命令实现（返回新建元素）
# ---------------------------------------------------------------------------

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
    if ln < 1e-12:
        raise GeoError("两点重合，无法确定直线")
    R = 25.0   # 直线延伸半长（世界单位）
    dx, dy, dz = dx / ln * R, dy / ln * R, dz / ln * R
    return {"objtype": "line3d",
            "data": {"x1": px - dx, "y1": py - dy, "z1": pz - dz,
                     "x2": px + dx, "y2": py + dy, "z2": pz + dz}}


def _parallel_state(pt, lin):
    a, b, c = _linear(lin)
    return _line_state(a, b, -(a * pt.x + b * pt.y))


def _line_state(a, b, c) -> Dict[str, float]:
    return {"a": a, "b": b, "c": c}


def _cmd_segment(cons, label, args):
    if len(args) == 2:
        p, q = _point_arg(cons, args[0]), _point_arg(cons, args[1])
        if p.z is not None or q.z is not None:
            return _mk(cons, Geo3D, "geo3d", label, [p, q], lambda d: _seg3d_state(d[0], d[1]))
        return _mk(cons, GeoSegment, "segment", label, [p, q],
                   lambda d: {"x1": d[0].x, "y1": d[0].y, "x2": d[1].x, "y2": d[1].y})
    raise GeoError("Segment 需要两个点")


def _seg3d_state(p, q):
    if math.sqrt((q.x - p.x) ** 2 + (q.y - p.y) ** 2 + ((q.z or 0) - (p.z or 0)) ** 2) < 1e-12:
        raise GeoError("线段两端点重合")
    return {"objtype": "segment",
            "data": {"x1": p.x, "y1": p.y, "z1": p.z or 0,
                     "x2": q.x, "y2": q.y, "z2": q.z or 0}}


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
    if r < 1e-9:
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


def _ix_plane_plane(p1, p2):
    """两面交线：方向 = 法向叉积；线上一点解 2x2。"""
    a1, b1, c1, d1 = p1.data["a"], p1.data["b"], p1.data["c"], p1.data["d"]
    a2, b2, c2, d2 = p2.data["a"], p2.data["b"], p2.data["c"], p2.data["d"]
    dx = b1 * c2 - c1 * b2
    dy = c1 * a2 - a1 * c2
    dz = a1 * b2 - b1 * a2
    ln = math.sqrt(dx * dx + dy * dy + dz * dz)
    if ln < 1e-12:
        raise GeoError("两平面平行或重合，无唯一交线")
    # 求交线上一点：消去分量最大的坐标
    if abs(dz) > abs(dx) and abs(dz) > abs(dy):
        x, y = _solve2(a1, b1, -d1, a2, b2, -d2)
        px, py, pz = x, y, 0.0
    elif abs(dy) > abs(dx):
        x, z = _solve2(a1, c1, -d1, a2, c2, -d2)
        px, py, pz = x, 0.0, z
    else:
        y, z = _solve2(b1, c1, -d1, b2, c2, -d2)
        px, py, pz = 0.0, y, z
    # 延展成线段（两端）
    L = 15.0
    return {"objtype": "line3d",
            "data": {"x1": px - dx / ln * L, "y1": py - dy / ln * L, "z1": pz - dz / ln * L,
                     "x2": px + dx / ln * L, "y2": py + dy / ln * L, "z2": pz + dz / ln * L}}


def _solve2(a, b, e, c, f, g):
    """解 ax+by=e, cx+fy=g。"""
    det = a * f - c * b
    if abs(det) < 1e-12:
        raise GeoError("退化方程组")
    return (e * f - b * g) / det, (a * g - e * c) / det


def _ix_line_plane(seg, pl):
    """线段与平面交点。"""
    d = seg.data
    x1, y1, z1 = d["x1"], d["y1"], d["z1"]
    x2, y2, z2 = d["x2"], d["y2"], d["z2"]
    a, b, c, dd = pl.data["a"], pl.data["b"], pl.data["c"], pl.data["d"]
    ux, uy, uz = x2 - x1, y2 - y1, z2 - z1
    denom = a * ux + b * uy + c * uz
    if abs(denom) < 1e-12:
        raise GeoError("线段与平面平行")
    t = -(a * x1 + b * y1 + c * z1 + dd) / denom
    if t < -1e-9 or t > 1 + 1e-9:
        raise GeoError("交点不在线段上")
    return {"x": x1 + t * ux, "y": y1 + t * uy, "z": z1 + t * uz}


def _is_solid_el(el) -> bool:
    """网格立体（立方体/多面体/锥/柱：objtype 为 cube 或 polyhedron）。"""
    return getattr(el, "objtype", "") in ("cube", "polyhedron")


def _line_ends(el):
    d = el.data
    return ([d["x1"], d["y1"], d["z1"]], [d["x2"], d["y2"], d["z2"]])


def _ix_line3d_plane(lin, pl):
    """三维直线（无限）与平面交点。"""
    p, q = _line_ends(lin)
    a, b, c, dd = pl.data["a"], pl.data["b"], pl.data["c"], pl.data["d"]
    ux, uy, uz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
    denom = a * ux + b * uy + c * uz
    if abs(denom) < 1e-12:
        raise GeoError("直线与平面平行")
    t = -(a * p[0] + b * p[1] + c * p[2] + dd) / denom
    return {"x": p[0] + t * ux, "y": p[1] + t * uy, "z": p[2] + t * uz}


def _ix_solid_plane(solid, pl):
    """凸立体与平面相交 → 截面多边形（objtype=section）。

    沿网格边两两求交（端点异号），去重后在平面内按极角排序成环。
    """
    vs = solid.data["verts"]
    edges = solid.data["edges"]
    a, b, c, dd = pl.data["a"], pl.data["b"], pl.data["c"], pl.data["d"]

    def _val(p):
        return a * p[0] + b * p[1] + c * p[2] + dd

    pts = []
    for i, j in edges:
        p, q = vs[i], vs[j]
        fp, fq = _val(p), _val(q)
        if abs(fp) < 1e-9 and abs(fq) < 1e-9:
            continue                      # 整条边落在平面上：该面本身在平面内，交由其它边给出顶点
        if abs(fp) < 1e-9:
            pts.append([p[0], p[1], p[2]])
            continue                      # 端点恰在平面上（如平面正好切过顶面）
        if abs(fq) < 1e-9:
            pts.append([q[0], q[1], q[2]])
            continue
        if (fp > 0) == (fq > 0):
            continue
        t = fp / (fp - fq)
        pts.append([p[k] + t * (q[k] - p[k]) for k in range(3)])
    uniq = []
    for p in pts:
        if not any(math.dist(p, q) < 1e-9 for q in uniq):
            uniq.append(p)
    if len(uniq) < 3:
        raise GeoError("平面与立体的截面不足 3 个顶点（相切或不相交）")
    ctr = [sum(p[k] for p in uniq) / len(uniq) for k in range(3)]
    ln = math.sqrt(a * a + b * b + c * c)
    nx, ny, nz = a / ln, b / ln, c / ln
    ux = uy = uz = 0.0
    for p in uniq:
        dx, dy, dz = p[0] - ctr[0], p[1] - ctr[1], p[2] - ctr[2]
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d > 1e-12:
            ux, uy, uz = dx / d, dy / d, dz / d
            break
    wx = ny * uz - nz * uy
    wy = nz * ux - nx * uz
    wz = nx * uy - ny * ux

    def _ang(p):
        dx, dy, dz = p[0] - ctr[0], p[1] - ctr[1], p[2] - ctr[2]
        return math.atan2(dx * wx + dy * wy + dz * wz, dx * ux + dy * uy + dz * uz)

    uniq.sort(key=_ang)
    return {"objtype": "section",
            "data": {"pts": uniq, "normal": [nx, ny, nz], "count": len(uniq)}}


def _ray_triangle(orig, dirv, a, b, c):
    """Möller–Trumbore：射线 orig + t·dirv 与三角形求交，返回 t 或 None。"""
    e1 = [b[k] - a[k] for k in range(3)]
    e2 = [c[k] - a[k] for k in range(3)]
    h = [dirv[1] * e2[2] - dirv[2] * e2[1],
         dirv[2] * e2[0] - dirv[0] * e2[2],
         dirv[0] * e2[1] - dirv[1] * e2[0]]
    det = e1[0] * h[0] + e1[1] * h[1] + e1[2] * h[2]
    if abs(det) < 1e-12:
        return None
    inv = 1.0 / det
    s = [orig[k] - a[k] for k in range(3)]
    u = (s[0] * h[0] + s[1] * h[1] + s[2] * h[2]) * inv
    if u < -1e-9 or u > 1 + 1e-9:
        return None
    q = [s[1] * e1[2] - s[2] * e1[1], s[2] * e1[0] - s[0] * e1[2], s[0] * e1[1] - s[1] * e1[0]]
    v = (dirv[0] * q[0] + dirv[1] * q[1] + dirv[2] * q[2]) * inv
    if v < -1e-9 or u + v > 1 + 1e-9:
        return None
    t = (e2[0] * q[0] + e2[1] * q[1] + e2[2] * q[2]) * inv
    # 容差：起点恰在面上（t=0）也算命中；由调用方按线段范围过滤
    return t if t > -1e-9 else None


def _circle3d_basis(d):
    """空间圆的 (圆心, 半径, 法向, 基 u, 基 v)。"""
    return ([d["cx"], d["cy"], d["cz"]], d["r"], d["normal"], d["u"], d["v"])


def _ix_sphere_sphere(s1, s2):
    """两球求交 → 交圆（空间圆）：交平面垂直于连心线，半径 √(r1²−a²)。"""
    a1, b1, c1, r1 = s1.data["cx"], s1.data["cy"], s1.data["cz"], s1.data["r"]
    a2, b2, c2, r2 = s2.data["cx"], s2.data["cy"], s2.data["cz"], s2.data["r"]
    dx, dy, dz = a2 - a1, b2 - b1, c2 - c1
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    if dist < 1e-9:
        raise GeoError("同心球没有交线（球面重合或内含）")
    if dist > r1 + r2 + 1e-9:
        raise GeoError("两球相离，无交线")
    if dist < abs(r1 - r2) - 1e-9:
        raise GeoError("一球完全在另一球内部，无交线")
    ux, uy, uz = dx / dist, dy / dist, dz / dist
    t = (dist * dist + r1 * r1 - r2 * r2) / (2 * dist)      # 交平面到球心 1 的距离
    rr2 = r1 * r1 - t * t
    if rr2 <= 1e-18:
        raise GeoError("两球相切（交线退化为一点）")
    ox, oy, oz = a1 + t * ux, b1 + t * uy, c1 + t * uz
    u, v, _n = _frame_from_axis([ux, uy, uz])
    return {"objtype": "circle3d",
            "data": {"cx": ox, "cy": oy, "cz": oz, "r": math.sqrt(rr2),
                     "normal": [ux, uy, uz], "u": u, "v": v}}


def _ix_sphere_circle3d(sph, cir, idx=None):
    """球 ∩ 空间圆 → 交点（0/1/2 个）。圆上点 P(t)=C+r(cos t·u+sin t·v)，解 |P−S|²=R²。"""
    c, r, _n0, u, v = _circle3d_basis(cir.data)
    d = sph.data
    S = [d["cx"], d["cy"], d["cz"]]
    R = d["r"]
    w = [c[0] - S[0], c[1] - S[1], c[2] - S[2]]
    wu = w[0] * u[0] + w[1] * u[1] + w[2] * u[2]
    wv = w[0] * v[0] + w[1] * v[1] + w[2] * v[2]
    ww = w[0] * w[0] + w[1] * w[1] + w[2] * w[2]
    D = (R * R - ww - r * r) / (2 * r)
    R0 = math.sqrt(wu * wu + wv * wv)
    if R0 < 1e-12:
        if abs(D) < 1e-9:
            raise GeoError("圆在球面上（无穷多交点）")
        raise GeoError("圆与球不相交")
    if abs(D) > R0 + 1e-12:
        raise GeoError("圆与球不相交")
    phi = math.atan2(wv, wu)
    delta = math.acos(max(-1.0, min(1.0, D / R0)))
    ts = sorted([phi + delta, phi - delta])
    if len(ts) == 2 and abs(ts[0] - ts[1]) < 1e-12:
        ts = [ts[0]]
    k = idx or 1
    if k > len(ts):
        raise GeoError("交点只有 " + str(len(ts)) + " 个（请求第 " + str(k) + " 个）")
    t = ts[k - 1]
    return {"x": c[0] + r * (math.cos(t) * u[0] + math.sin(t) * v[0]),
            "y": c[1] + r * (math.cos(t) * u[1] + math.sin(t) * v[1]),
            "z": c[2] + r * (math.cos(t) * u[2] + math.sin(t) * v[2])}


def _ix_circle3d_circle3d(c1_el, c2_el, idx=None):
    """两空间圆求交 → 交点（共面走解析解，异面走采样 + 二分）。"""
    c1, r1, n1, u1, v1 = _circle3d_basis(c1_el.data)
    c2, r2, n2, u2, v2 = _circle3d_basis(c2_el.data)
    dvec = [c2[i] - c1[i] for i in range(3)]
    dot_n = n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2]
    plane_gap = n1[0] * dvec[0] + n1[1] * dvec[1] + n1[2] * dvec[2]
    same_plane = abs(abs(dot_n) - 1.0) < 1e-9 and abs(plane_gap) < 1e-7

    if same_plane:
        # 平面内两圆（经典 2D 情形），以 c1 为原点、u1/v1 为基
        px = dvec[0] * u1[0] + dvec[1] * u1[1] + dvec[2] * u1[2]
        py = dvec[0] * v1[0] + dvec[1] * v1[1] + dvec[2] * v1[2]
        dist = math.sqrt(px * px + py * py)
        if dist < 1e-9:
            if abs(r1 - r2) < 1e-9:
                raise GeoError("两圆重合（无穷多交点）")
            raise GeoError("同心圆无交点")
        if dist > r1 + r2 + 1e-12 or dist < abs(r1 - r2) - 1e-12:
            raise GeoError("两圆不相交")
        a = (dist * dist + r1 * r1 - r2 * r2) / (2 * dist)
        h2 = r1 * r1 - a * a
        ux, uy = px / dist, py / dist
        bx = c1[0] + a * ux * u1[0] + a * uy * v1[0]
        by = c1[1] + a * ux * u1[1] + a * uy * v1[1]
        bz = c1[2] + a * ux * u1[2] + a * uy * v1[2]
        if h2 <= 1e-18:
            pts = [[bx, by, bz]]
        else:
            h = math.sqrt(h2)
            perp = [-uy * u1[0] + ux * v1[0], -uy * u1[1] + ux * v1[1], -uy * u1[2] + ux * v1[2]]
            pts = [[bx + h * perp[0], by + h * perp[1], bz + h * perp[2]],
                   [bx - h * perp[0], by - h * perp[1], bz - h * perp[2]]]
    else:
        # 平面不平行：圆2 与平面1 恰好交于 2 点，再筛「到 c1 距离 = r1」。
        # （若用 |P−c1|²−r1² 作判别函数，两圆共球面/同轴时该函数恒为 0，会漏判。）
        nx = n1[1] * n2[2] - n1[2] * n2[1]
        ny = n1[2] * n2[0] - n1[0] * n2[2]
        nz = n1[0] * n2[1] - n1[1] * n2[0]
        if math.sqrt(nx * nx + ny * ny + nz * nz) < 1e-9:
            raise GeoError("两圆所在平面平行，无交点")
        dvec2 = [c2[i] - c1[i] for i in range(3)]
        E = n1[0] * dvec2[0] + n1[1] * dvec2[1] + n1[2] * dvec2[2]
        A = r2 * (n1[0] * u2[0] + n1[1] * u2[1] + n1[2] * u2[2])
        B = r2 * (n1[0] * v2[0] + n1[1] * v2[1] + n1[2] * v2[2])
        R0 = math.sqrt(A * A + B * B)
        if abs(E) > R0 + 1e-12:
            raise GeoError("两圆不相交")
        phi = math.atan2(B, A)
        delta = math.acos(max(-1.0, min(1.0, -E / R0)))
        ts = sorted([phi + delta, phi - delta])
        if len(ts) == 2 and abs(ts[0] - ts[1]) < 1e-12:
            ts = [ts[0]]

        def _p2(t):
            return [c2[0] + r2 * (math.cos(t) * u2[0] + math.sin(t) * v2[0]),
                    c2[1] + r2 * (math.cos(t) * u2[1] + math.sin(t) * v2[1]),
                    c2[2] + r2 * (math.cos(t) * u2[2] + math.sin(t) * v2[2])]

        pts = []
        for t in ts:
            p = _p2(t)
            ddx, ddy, ddz = p[0] - c1[0], p[1] - c1[1], p[2] - c1[2]
            if abs(math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz) - r1) < 1e-7:
                pts.append(p)
        if not pts:
            raise GeoError("两圆不相交")

    k = idx or 1
    if k > len(pts):
        raise GeoError("交点只有 " + str(len(pts)) + " 个（请求第 " + str(k) + " 个）")
    p = pts[k - 1]
    return {"x": p[0], "y": p[1], "z": p[2]}


def _ix_circle3d_plane(cir, pl, idx=None):
    """空间圆 ∩ 平面 → 交点（0/1/2 个，按 idx 取第 n 个，默认第 1 个）。"""
    c, r, _n0, u, v = _circle3d_basis(cir.data)
    a, b, cc, dd = pl.data["a"], pl.data["b"], pl.data["c"], pl.data["d"]
    ln = math.sqrt(a * a + b * b + cc * cc)
    if ln < 1e-12:
        raise GeoError("平面退化")
    nx, ny, nz = a / ln, b / ln, cc / ln
    dpl = dd / ln
    E = nx * c[0] + ny * c[1] + nz * c[2] + dpl          # 圆心到平面的有符号距离
    A = r * (nx * u[0] + ny * u[1] + nz * u[2])
    B = r * (nx * v[0] + ny * v[1] + nz * v[2])
    R = math.sqrt(A * A + B * B)
    if R < 1e-12:
        if abs(E) < 1e-9:
            raise GeoError("圆与平面共面（交线为整个圆）")
        raise GeoError("圆所在平面与给定平面平行，无交点")
    if abs(E) > R + 1e-12:
        raise GeoError("平面与圆不相交")
    phi = math.atan2(B, A)
    delta = math.acos(max(-1.0, min(1.0, -E / R)))
    ts = [phi + delta, phi - delta]
    ts.sort()
    if len(ts) == 2 and abs(ts[0] - ts[1]) < 1e-12:
        ts = [ts[0]]
    k = idx or 1
    if k > len(ts):
        raise GeoError("交点只有 " + str(len(ts)) + " 个（请求第 " + str(k) + " 个）")
    t = ts[k - 1]
    return {"x": c[0] + r * (math.cos(t) * u[0] + math.sin(t) * v[0]),
            "y": c[1] + r * (math.cos(t) * u[1] + math.sin(t) * v[1]),
            "z": c[2] + r * (math.cos(t) * u[2] + math.sin(t) * v[2])}


def _ix_circle3d_solid(cir, solid, idx=None):
    """空间圆 ∩ 凸立体 → 交点（沿圆周采样 + 二分细化；相切时用最近点兜底）。"""
    c, r, _n0, u, v = _circle3d_basis(cir.data)
    planes = _solid_planes(solid)

    def pt(t):
        return [c[0] + r * (math.cos(t) * u[0] + math.sin(t) * v[0]),
                c[1] + r * (math.cos(t) * u[1] + math.sin(t) * v[1]),
                c[2] + r * (math.cos(t) * u[2] + math.sin(t) * v[2])]

    def inside(p):
        return all(n[0] * p[0] + n[1] * p[1] + n[2] * p[2] + dd <= 1e-9 for n, dd in planes)

    N = 720
    crossings = []
    prev_t, prev_ins = 0.0, inside(pt(0.0))
    for k in range(1, N + 1):
        t = 2 * math.pi * k / N
        ins = inside(pt(t))
        if ins != prev_ins:
            lo, hi, ilo = prev_t, t, prev_ins
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                if inside(pt(mid)) == ilo:
                    lo = mid
                else:
                    hi = mid
            crossings.append(0.5 * (lo + hi))
        prev_t, prev_ins = t, ins
    if not crossings:
        # 相切兜底：找圆周上距某面最近且整体在体内的点
        best = None
        for k in range(N):
            t = 2 * math.pi * k / N
            p = pt(t)
            if not inside(p):
                continue
            dist = min(abs(n[0] * p[0] + n[1] * p[1] + n[2] * p[2] + dd) for n, dd in planes)
            if best is None or dist < best[0]:
                best = (dist, t)
        if best is not None and best[0] < 1e-6:
            crossings = [best[1]]
        else:
            raise GeoError("圆与立体无交点（整圆在立体内部或外部）")
    # 去重（相切会成对出现）
    uniq = []
    for t in sorted(crossings):
        if not uniq or abs(t - uniq[-1]) > 1e-6:
            uniq.append(t)
    k = idx or 1
    if k > len(uniq):
        raise GeoError("交点只有 " + str(len(uniq)) + " 个（请求第 " + str(k) + " 个）")
    return dict(zip(("x", "y", "z"), pt(uniq[k - 1])))


def _ix_sphere_plane(sph, pl):
    """球 ∩ 平面 → 3D 圆（objtype=circle3d，带圆心/半径/所在平面法向与基）。"""
    d = sph.data
    cx, cy, cz, r = d["cx"], d["cy"], d["cz"], d["r"]
    a, b, c, dd = pl.data["a"], pl.data["b"], pl.data["c"], pl.data["d"]
    ln = math.sqrt(a * a + b * b + c * c)
    if ln < 1e-12:
        raise GeoError("平面退化")
    nx, ny, nz = a / ln, b / ln, c / ln
    sdist = nx * cx + ny * cy + nz * cz + dd / ln          # 球心到平面的有符号距离（平面：n·x+d=0）
    if abs(sdist) > r + 1e-9:
        raise GeoError("平面与球不相交（球心距 %.6f > 半径 %.6f）" % (abs(sdist), r))
    rr = math.sqrt(max(0.0, r * r - sdist * sdist))
    if rr < 1e-9:
        raise GeoError("平面与球相切（交线退化为一点）")
    ox, oy, oz = cx - sdist * nx, cy - sdist * ny, cz - sdist * nz   # 圆心 = 球心在平面上的投影
    u, v, _n = _frame_from_axis([nx, ny, nz])
    return {"objtype": "circle3d",
            "data": {"cx": ox, "cy": oy, "cz": oz, "r": rr,
                     "normal": [nx, ny, nz], "u": u, "v": v}}


# ---- 凸多面体半空间裁剪（体∩体） ----

def _solid_planes(el):
    """把凸立体转成外向半空间列表 [(n, d)]：内部满足 n·x + d ≤ 0。"""
    vs = el.data["verts"]
    faces = el.data["faces"]
    planes = []
    for f in faces:
        nx, ny, nz = _newell_normal(vs, f)
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        if ln < 1e-12:
            continue
        nx, ny, nz = nx / ln, ny / ln, nz / ln
        p = vs[f[0]]
        planes.append(((nx, ny, nz), -(nx * p[0] + ny * p[1] + nz * p[2])))
    return planes


def _clip_polyhedron(verts, faces, plane):
    """用一个半空间 n·x + d ≤ 0 裁剪凸多面体（顶点/面表），返回新的 (verts, faces)。"""
    n, d = plane

    def inside(p):
        return n[0] * p[0] + n[1] * p[1] + n[2] * p[2] + d <= 1e-12

    def cut_point(p, q):
        fp = n[0] * p[0] + n[1] * p[1] + n[2] * p[2] + d
        fq = n[0] * q[0] + n[1] * q[1] + n[2] * q[2] + d
        t = fp / (fp - fq)
        return [p[k] + t * (q[k] - p[k]) for k in range(3)]

    out_faces = []
    cut_pts = []
    for f in faces:
        pts = [verts[i] for i in f]
        newpoly = []
        m = len(pts)
        for i in range(m):
            p, q = pts[i], pts[(i + 1) % m]
            ip, iq = inside(p), inside(q)
            if ip:
                newpoly.append(p)
            if ip != iq:
                cp = cut_point(p, q)
                newpoly.append(cp)
                cut_pts.append(cp)
        # 去重（相邻重复点）
        dedup = []
        for p in newpoly:
            if not dedup or math.dist(p, dedup[-1]) > 1e-9:
                dedup.append(p)
        if len(dedup) >= 3:
            if math.dist(dedup[0], dedup[-1]) < 1e-9:
                dedup.pop()
            out_faces.append(dedup)
    if not out_faces:
        return [], []
    # 顶点表（按坐标去重）
    new_verts = []
    for f in out_faces:
        for p in f:
            if not any(math.dist(p, q) < 1e-9 for q in new_verts):
                new_verts.append(p)
    idx_faces = [[next(i for i, q in enumerate(new_verts) if math.dist(p, q) < 1e-9) for p in f] for f in out_faces]
    # 截面封盖：把裁剪产生的点按平面内极角排序
    if len(cut_pts) >= 3:
        uniq = []
        for p in cut_pts:
            if not any(math.dist(p, q) < 1e-9 for q in uniq):
                uniq.append(p)
        if len(uniq) >= 3:
            ctr = [sum(p[k] for p in uniq) / len(uniq) for k in range(3)]
            ux = uy = uz = 0.0
            for p in uniq:
                dx, dy, dz = p[0] - ctr[0], p[1] - ctr[1], p[2] - ctr[2]
                dd = math.sqrt(dx * dx + dy * dy + dz * dz)
                if dd > 1e-12:
                    ux, uy, uz = dx / dd, dy / dd, dz / dd
                    break
            wx = n[1] * uz - n[2] * uy
            wy = n[2] * ux - n[0] * uz
            wz = n[0] * uy - n[1] * ux

            def _ang(p):
                dx, dy, dz = p[0] - ctr[0], p[1] - ctr[1], p[2] - ctr[2]
                return math.atan2(dx * wx + dy * wy + dz * wz, dx * ux + dy * uy + dz * uz)

            uniq.sort(key=_ang)
            cap = []
            for p in uniq:
                if not any(math.dist(p, q) < 1e-9 for q in [new_verts[i] for i in range(len(new_verts))]):
                    new_verts.append(p)
                cap.append(next(i for i, q in enumerate(new_verts) if math.dist(p, q) < 1e-9))
            idx_faces.append(cap)
    return new_verts, idx_faces


def _ix_solid_solid(s1, s2):
    """两个凸立体求交 → 凸多面体（半空间裁剪）。"""
    verts = [list(v) for v in s1.data["verts"]]
    faces = [list(f) for f in s1.data["faces"]]
    for pl in _solid_planes(s1) + _solid_planes(s2):
        verts, faces = _clip_polyhedron(verts, faces, pl)
        if len(verts) < 4 or not faces:
            raise GeoError("两个立体的交集为空或退化为面/点")
    # 由面表恢复边表
    edges = []
    for f in faces:
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            if a == b:
                continue
            key = (min(a, b), max(a, b))
            if key not in edges:
                edges.append(key)
    if not edges:
        raise GeoError("两个立体的交集退化")
    mesh = {"verts": [list(v) for v in verts], "faces": [list(f) for f in faces], "edges": [list(e) for e in edges]}
    if _mesh_volume(mesh) < 1e-9:
        raise GeoError("两个立体的交集退化为零体积（面/点接触）")
    return {"objtype": "polyhedron", "data": mesh}


def _ix_solid_line(solid, lin, idx, bounded):
    """凸立体与直线/线段求交 → 按 idx 取第 idx 个交点（1-based，默认第 1 个）。"""
    vs = solid.data["verts"]
    p, q = _line_ends(lin)
    dirv = [q[k] - p[k] for k in range(3)]
    ts = []
    for face in solid.data["faces"]:
        a = vs[face[0]]
        for i in range(1, len(face) - 1):
            t = _ray_triangle(p, dirv, a, vs[face[i]], vs[face[i + 1]])
            if t is None:
                continue
            if bounded and (t < -1e-9 or t > 1 + 1e-9):
                continue
            ts.append(min(1.0, max(0.0, t)) if bounded else t)
    if not ts:
        raise GeoError("线段与立体无交点（整段在立体内部或外部）" if bounded else "直线与立体不相交")
    ts.sort()
    uniq = []
    for t in ts:
        if not uniq or abs(t - uniq[-1]) > 1e-7:
            uniq.append(t)
    k = (idx or 1)
    if k > len(uniq):
        raise GeoError("交点只有 " + str(len(uniq)) + " 个（请求第 " + str(k) + " 个）")
    t = uniq[k - 1]
    return {"x": p[0] + t * dirv[0], "y": p[1] + t * dirv[1], "z": p[2] + t * dirv[2]}


def _ix_sphere_line(sph, lin, idx, bounded):
    """球与直线/线段求交 → 按 idx 取第 idx 个交点。"""
    d = sph.data
    cx, cy, cz, r = d["cx"], d["cy"], d["cz"], d["r"]
    p, q = _line_ends(lin)
    dx, dy, dz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
    fx, fy, fz = p[0] - cx, p[1] - cy, p[2] - cz
    A = dx * dx + dy * dy + dz * dz
    if A < 1e-18:
        raise GeoError("直线退化")
    B = 2 * (fx * dx + fy * dy + fz * dz)
    C = fx * fx + fy * fy + fz * fz - r * r
    disc = B * B - 4 * A * C
    if disc < -1e-12:
        raise GeoError("直线与球不相交")
    disc = max(0.0, disc)
    sq = math.sqrt(disc)
    ts = [(-B - sq) / (2 * A), (-B + sq) / (2 * A)]
    ts = [t for t in ts if (not bounded) or (-1e-9 <= t <= 1 + 1e-9)]
    if not ts:
        raise GeoError("交点不在线段上")
    ts.sort()
    if len(ts) == 2 and abs(ts[0] - ts[1]) < 1e-9:
        ts = [ts[0]]          # 相切：判别式≈0 时两根重合，只算一个交点
    k = (idx or 1)
    if k > len(ts):
        raise GeoError("交点只有 " + str(len(ts)) + " 个（请求第 " + str(k) + " 个）")
    t = ts[k - 1]
    return {"x": p[0] + t * dx, "y": p[1] + t * dy, "z": p[2] + t * dz}


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
            if abs(b) < 1e-12:
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
                if not (0.0 - 1e-9 <= _on_segment((pt["x"], pt["y"]), ln) <= 1.0 + 1e-9):
                    raise GeoError("交点不在线段上")
            elif ln.kind == "ray":
                dx, dy = ln.dx, ln.dy
                t = ((pt["x"] - ln.ox) * dx + (pt["y"] - ln.oy) * dy) / (dx * dx + dy * dy + 1e-300)
                if t < -1e-9:
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
    if abs(b) < 1e-12:
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


def _label_of(defn: str) -> str:
    idx = defn.find("=")
    if idx == -1:
        idx = defn.find(":")
    return defn[:idx].strip() if idx != -1 else defn.strip()


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
        t = ((pt[0] - obj.ox) * dx + (pt[1] - obj.oy) * dy) / (dx * dx + dy * dy + 1e-300)
        if t < -1e-9:
            raise GeoError("交点不在射线上")


def _on_segment(pt, seg) -> float:
    """点在参数 t 上的位置；0<=t<=1 在段内。"""
    dx, dy = seg.x2 - seg.x1, seg.y2 - seg.y1
    denom = dx * dx + dy * dy
    if denom < EPS:
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
            if abs(vx.imag) < 1e-9 and abs(vy.imag) < 1e-9:
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
    if abs(b) < 1e-12:
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
    if du < 1e-12 or dv < 1e-12:
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
        if nu > 1e-12 and nv > 1e-12:
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
            if abs(a) < 1e-9:      # 水平线 y=k → 2k - f(x)
                k = -c / b
                return lambda d: _fn_state(d[0], lambda x: 2 * k - d[0].expr)
            if abs(b) < 1e-9:      # 垂直线 x=h → f(2h - x)
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
    if norm < EPS:
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
    if norm < EPS:
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
    if norm < EPS:
        raise GeoError("退化的直线")
    p0x = -a0 * c0 / (norm * norm)
    p0y = -b0 * c0 / (norm * norm)
    p1 = _rotate(p0x, p0y, th, cxp, cyp)
    dx, dy = _rotate(p0x - b0 / norm, p0y + a0 / norm, th, cxp, cyp)
    p2 = (dx, dy)
    return _line_state(*_line_through(p1[0], p1[1], p2[0], p2[1]))


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


def _fmt(v: float) -> str:
    s = ("%.6f" % v).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


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

def _feval(f, xi: float):
    """函数 f 在 xi 处的数值。"""
    return f._eval1(xi)


def _roots_1d(expr, x, xmin: float = -60.0, xmax: float = 60.0, n: int = 900):
    """求 expr(x)=0 在区间内的全部实根（符号优先，数值兜底）。返回排序后的 x 列表。"""
    import sympy
    roots: List[float] = []
    # 符号解（多项式等）
    try:
        sol = sympy.solve(expr, x)
        for s in sol:
            v = complex(sympy.N(s))
            if abs(v.imag) < 1e-9 and xmin - 1e-6 <= v.real <= xmax + 1e-6:
                roots.append(float(v.real))
    except Exception:
        pass
    if roots:
        roots = sorted(set(round(r, 9) for r in roots))
        return roots
    # 数值扫描 + 二分
    import numpy as np
    try:
        lam = sympy.lambdify(x, expr, "numpy")
        xs = np.linspace(xmin, xmax, n)
        ys = lam(xs)
    except Exception:
        return []
    for i in range(n - 1):
        y1, y2 = ys[i], ys[i + 1]
        if not (np.isfinite(y1) and np.isfinite(y2)):
            continue
        if y1 == 0.0:
            roots.append(float(xs[i]))
        elif y1 * y2 < 0.0:
            a, b = float(xs[i]), float(xs[i + 1])
            fa = y1
            for _ in range(60):
                mid = (a + b) / 2.0
                fm = float(lam(mid))
                if not np.isfinite(fm):
                    break
                if fa * fm <= 0.0:
                    b, fb = mid, fm
                else:
                    a, fa = mid, fm
                if abs(b - a) < 1e-10:
                    break
            roots.append((a + b) / 2.0)
    # 去重
    dedup: List[float] = []
    for r in sorted(roots):
        if not dedup or abs(r - dedup[-1]) > 1e-7:
            dedup.append(r)
    return dedup


def _line_y_x(lin, x: float):
    """直线在 x 处的 y（垂直线返回 None）。"""
    a, b, c = _linear(lin)
    if abs(b) < 1e-12:
        return None
    return -(a * x + c) / b


def _fn_line_diff(f, lin, x):
    """f(x) - line_y(x) 的符号表达式；垂直线返回 None（单独处理）。"""
    a, b, c = _linear(lin)
    if abs(b) < 1e-12:
        return None
    return f.expr - (-(a * x + c) / b)


def _cmd_of(defn: str) -> str:
    """从 defn（label=cmd）中取出 cmd 部分。"""
    idx = defn.find("=")
    if idx == -1:
        idx = defn.find(":")
    return defn[idx + 1:].strip() if idx != -1 else defn


# ---------------------------------------------------------------------------
# P1 命令：Derivative / Integral / Tangent / Root / Extremum
# ---------------------------------------------------------------------------

def _cmd_derivative(cons, defn, args):
    if len(args) not in (1, 2):
        raise GeoError("Derivative 需要 函数 和 可选的阶数")
    f = _resolve(cons, args[0], ("function",))
    n = 1
    if len(args) == 2:
        n = int(eval_number(cons, args[1]))
        if n < 1:
            raise GeoError("导数阶数必须 >= 1")
    return _mk(cons, GeoFunction, "function", defn, [f],
               lambda d: {"expr": __import__("sympy").diff(d[0].expr, d[0].xsym, n)})


def _cmd_integral(cons, defn, args):
    if len(args) == 1:
        f = _resolve(cons, args[0], ("function",))
        return _mk(cons, GeoFunction, "function", defn, [f],
                   lambda d: {"expr": __import__("sympy").integrate(d[0].expr, d[0].xsym)})
    if len(args) == 3:
        f = _resolve(cons, args[0], ("function",))
        dyn = []
        a_fixed = b_fixed = None
        a_el = _lookup(cons, args[1])
        b_el = _lookup(cons, args[2])
        if a_el is not None and a_el.kind == "number":
            dyn.append(a_el)
        else:
            a_fixed = eval_number(cons, args[1])
        if b_el is not None and b_el.kind == "number":
            dyn.append(b_el)
        else:
            b_fixed = eval_number(cons, args[2])
        deps = [f] + dyn

        def fn(d):
            import sympy
            fn0 = d[0]
            x = fn0.xsym
            i = 1
            a = a_fixed if a_fixed is not None else d[i].value if i < len(d) else a_fixed
            if a_fixed is None:
                a = d[i].value
                i += 1
            b = b_fixed if b_fixed is not None else d[i].value
            try:
                v = sympy.integrate(fn0.expr, (x, a, b))
                return {"value": float(sympy.N(v))}
            except Exception:
                raise GeoError("定积分无法计算")
        return _mk(cons, GeoNumber, "number", defn, deps, fn)
    raise GeoError("Integral 需要 函数 或 函数+上下限")


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


def _cmd_root(cons, defn, args):
    f = _resolve(cons, args[0], ("function",))
    if len(args) == 1:
        # 全部根中最小的一个
        return _mk(cons, GeoPoint, "point", defn, [f], lambda d: _root_state(d[0], None, None))
    if len(args) == 2:
        a = eval_number(cons, args[1])
        return _mk(cons, GeoPoint, "point", defn, [f], lambda d: _root_state(d[0], a, None))
    if len(args) == 3:
        a = eval_number(cons, args[1])
        b = eval_number(cons, args[2])
        return _mk(cons, GeoPoint, "point", defn, [f], lambda d: _root_state(d[0], a, b))
    raise GeoError("Root 需要 函数 或 函数+起点 或 函数+区间")


def _root_state(f, a, b):
    import sympy
    x = f.xsym
    roots = _roots_1d(f.expr, x)
    if a is not None and b is not None:
        cand = [r for r in roots if a - 1e-9 <= r <= b + 1e-9]
        if not cand:
            raise GeoError("区间内没有根")
        r = cand[0]
    elif a is not None:
        if not roots:
            raise GeoError("没有根")
        r = min(roots, key=lambda t: abs(t - a))
    else:
        if not roots:
            raise GeoError("没有根")
        r = roots[0]
    y = _feval(f, r)
    if y is None:
        raise GeoError("根处函数未定义")
    return {"x": r, "y": y}


def _cmd_extremum(cons, defn, args, idx=None):
    if len(args) != 3:
        raise GeoError("Extremum 需要 函数 和 区间端点")
    f = _resolve(cons, args[0], ("function",))
    a = eval_number(cons, args[1])
    b = eval_number(cons, args[2])

    def build(i: int) -> GeoPoint:
        el = GeoPoint("", defn)
        el.free = False
        el._i = i

        def compute(deps):
            import sympy
            fn0 = deps[0]
            x = fn0.xsym
            diff = sympy.diff(fn0.expr, x)
            roots = [r for r in _roots_1d(diff, x, a, b) if a - 1e-9 <= r <= b + 1e-9]
            if el._i >= len(roots):
                raise GeoError("极值点数量不足")
            r = roots[el._i]
            y = _feval(fn0, r)
            if y is None:
                raise GeoError("极值点处函数未定义")
            return {"x": r, "y": y}
        el.set_deps([f], compute)
        return el

    import sympy
    roots = [r for r in _roots_1d(sympy.diff(f.expr, f.xsym), f.xsym, a, b) if a - 1e-9 <= r <= b + 1e-9]
    if not roots:
        raise GeoError("区间内没有极值点")
    if idx is not None:
        el = build(idx)
        el.label = _label_of(defn)
        el.defn = defn + "#" + str(idx)
        return cons.add(el)
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


# ---------------------------------------------------------------------------
# 初中几何补充：垂线/垂足/角平分线/度量/内心/重心/滑动条
# ---------------------------------------------------------------------------

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
    if denom < 1e-12:
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
    if nu < 1e-12 or nv < 1e-12:
        raise GeoError("退化角")
    dx, dy = ux / nu + vx / nv, uy / nu + vy / nv
    return _line_state(-dy, dx, -(-dy * b.x + dx * b.y))


def _polygon_area(poly) -> float:
    xs, ys = poly.xs, poly.ys
    n = len(xs)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        j = (i + 1) % n
        s += xs[i] * ys[j] - xs[j] * ys[i]
    return abs(s) / 2.0


def _polygon_perimeter(poly) -> float:
    xs, ys = poly.xs, poly.ys
    n = len(xs)
    if n < 2:
        return 0.0
    return sum(math.hypot(xs[i] - xs[(i + 1) % n], ys[i] - ys[(i + 1) % n]) for i in range(n))


def _cmd_area(cons, defn, args):
    if len(args) == 3 and args[0].strip() in cons.elements             and cons.elements[args[0].strip()].kind == "function":
        f = _resolve(cons, args[0], ("function",))
        a = eval_number(cons, args[1])
        b = eval_number(cons, args[2])
        import sympy
        return _mk(cons, GeoNumber, "number", defn, [f],
                   lambda d: {"value": float(sympy.N(sympy.integrate(d[0].expr, (d[0].xsym, a, b))))})
    obj = _resolve(cons, args[0])
    if obj.kind == "polygon":
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": _polygon_area(d[0])})
    if obj.kind == "circle":
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": math.pi * d[0].r * d[0].r})
    if obj.kind == "conic" and obj.ctype in ("ellipse", "circle"):
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": math.pi * d[0].semi_a * (d[0].semi_b or d[0].semi_a)})
    if obj.kind == "geo3d":
        return _mk(cons, GeoNumber, "number", defn, [obj],
                   lambda d: {"value": _solid_area(d[0])})
    raise GeoError("Area 需要 多边形/圆/椭圆/3D 立体 或 函数+上下限")


def _cmd_volume(cons, defn, args):
    """Volume[立体]：球/圆锥/圆柱解析精确，多面体按网格精确求和。"""
    if len(args) != 1:
        raise GeoError("Volume 需要一个立体对象")
    obj = _resolve(cons, args[0])
    if obj.kind != "geo3d":
        raise GeoError("Volume 需要 3D 立体（球/圆锥/圆柱/棱柱/棱锥/正多面体）")
    return _mk(cons, GeoNumber, "number", defn, [obj],
               lambda d: {"value": _solid_volume(d[0])})


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
    if abs(a - b) < 1e-12:
        return 2 * math.pi * a
    h = ((a - b) / (a + b)) ** 2
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))  # Ramanujan 近似


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
    if s < 1e-12:
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
    if s < 1e-12:
        raise GeoError("退化三角形")
    ix = (la * a.x + lb * b.x + lc * c.x) / s
    iy = (la * a.y + lb * b.y + lc * c.y) / s
    area = abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)) / 2.0
    r = 2 * area / s
    return {"cx": ix, "cy": iy, "r": r}


def _cmd_centroid(cons, defn, args):
    obj = _resolve(cons, args[0], ("polygon",))
    return _mk(cons, GeoPoint, "point", defn, [obj], lambda d: _centroid_state(d[0]))


def _centroid_state(poly):
    xs, ys = poly.xs, poly.ys
    if not xs:
        raise GeoError("空多边形")
    return {"x": sum(xs) / len(xs), "y": sum(ys) / len(ys)}


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
    if abs(det) < 1e-12:
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
    if abs(denom) < 1e-12:
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
    el = _resolve(cons, args[0], ("number",))
    src = getattr(el, "_random_src", None)
    if not src:
        raise GeoError(el.label + " 不是 RandomBetween 创建的数值（无随机源）")
    import random
    el.value = float(random.randint(src[0], src[1]))
    el.defn = el.label + "=RandomBetween[" + str(src[0]) + "," + str(src[1]) + "]"
    cons._recompute(el)
    return []


def _cmd_npr(cons, defn, args):
    """nPr[n, r]：排列数。"""
    if len(args) != 2:
        raise GeoError("nPr 需要 n, r")
    n = int(eval_number(cons, args[0]))
    r = int(eval_number(cons, args[1]))
    if n < 0 or r < 0 or r > n:
        raise GeoError("需要 0 ≤ r ≤ n")
    try:
        v = math.perm(n, r)
    except (OverflowError, ValueError):
        raise GeoError("结果过大")
    el = GeoNumber(label_of(defn), defn, float(v))
    el.free = False
    return cons.add(el)


def _cmd_ncr(cons, defn, args):
    """nCr[n, r]：组合数。"""
    if len(args) != 2:
        raise GeoError("nCr 需要 n, r")
    n = int(eval_number(cons, args[0]))
    r = int(eval_number(cons, args[1]))
    if n < 0 or r < 0 or r > n:
        raise GeoError("需要 0 ≤ r ≤ n")
    try:
        v = math.comb(n, r)
    except (OverflowError, ValueError):
        raise GeoError("结果过大")
    el = GeoNumber(label_of(defn), defn, float(v))
    el.free = False
    return cons.add(el)


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

def _cmd_rectsum(cons, defn, args, variant):
    """矩形/梯形逼近：参数 函数, a, b, n（n 可为滑块引用）[, 采样 left/right/mid/0..1]。variant 见命令。"""
    if len(args) not in (4, 5):
        raise GeoError("黎曼和需要 函数, 下限, 上限, 分割数 n（可选 采样位置 left/right/mid/0..1）")
    f = _resolve(cons, args[0], ("function",))
    a = eval_number(cons, args[1])
    b = eval_number(cons, args[2])
    if b <= a:
        raise GeoError("上限必须大于下限")
    deps = [f]
    n_el = None
    n_txt = args[3].strip()
    if n_txt in cons.elements and cons.elements[n_txt].kind == "number":
        n_el = cons.elements[n_txt]
        deps.append(n_el)
        n_val = 1
    else:
        n_val = int(eval_number(cons, n_txt))
        if n_val < 1 or n_val > 1000:
            raise GeoError("分割数 n 需在 1..1000")
    pos = None
    if len(args) == 5:
        p = args[4].strip()
        if p == "left":
            pos = 0.0
        elif p == "right":
            pos = 1.0
        elif p == "mid":
            pos = 0.5
        else:
            pos = float(eval_number(cons, p))
            if not (0.0 <= pos <= 1.0):
                raise GeoError("采样位置需在 0..1（或 left/right/mid）")
    if variant == "rect":
        mode = "left"
        use_pos = None
        if len(args) == 5 and pos is not None:
            if abs(pos - 0.5) < 1e-9:
                mode = "mid"
            elif abs(pos - 1.0) < 1e-9:
                mode = "right"
            elif abs(pos) < 1e-9:
                mode = "left"
            else:
                mode = "pos"
                use_pos = pos
    else:
        mode = variant
        use_pos = None
    el = GeoSumRect(label_of(defn), defn)
    el.free = False
    el.mode = mode

    def fn(d):
        import numpy as np
        n = int(round(d[1].value)) if n_el is not None else n_val
        n = max(1, min(1000, n))
        w = (b - a) / n

        def ev(x):
            return d[0]._eval1(x)
        rects = []
        total = 0.0
        for i in range(n):
            x0 = a + i * w
            x1 = x0 + w
            if variant == "trap":
                y0 = ev(x0)
                y1 = ev(x1)
                if y0 is None or y1 is None:
                    continue
                rects.append([x0, x1, y0, y1])
                total += w * (y0 + y1) / 2.0
            elif variant in ("lower", "upper"):
                ys = [ev(float(x)) for x in np.linspace(x0, x1, 9)]
                ys = [v for v in ys if v is not None]
                if not ys:
                    continue
                y = min(ys) if variant == "lower" else max(ys)
                rects.append([x0, x1, y])
                total += w * y
            else:
                if mode == "left":
                    xi = x0
                elif mode == "right":
                    xi = x1
                elif mode == "mid":
                    xi = (x0 + x1) / 2.0
                else:
                    xi = x0 + (x1 - x0) * use_pos
                y = ev(xi)
                if y is None:
                    continue
                rects.append([x0, x1, y])
                total += w * y
        el.rects = rects
        el.value = float(total)
        el.n = n
        el.a, el.b = a, b
        return {}

    el.set_deps(deps, fn)
    el.compute()
    return cons.add(el)


def _cmd_piechart(cons, defn, args):
    """PieChart[数值列表]：扇形统计图（列表可内联 {..} 或标签）。"""
    if len(args) != 1:
        raise GeoError("PieChart 需要数值列表，如 PieChart[{3,5,2}]")
    L = _list_arg(cons, args[0])
    if L.itemkind != "number":
        raise GeoError("PieChart 需要数值列表")
    el = GeoPie(label_of(defn), defn)
    el.free = False

    def fn(d):
        items = [float(v) for v in d[0].items]
        if not items:
            raise GeoError("饼图数据为空")
        if any(v < 0 for v in items):
            raise GeoError("饼图数据须非负")
        tot = sum(items)
        if tot <= 0:
            raise GeoError("饼图数据总和须为正")
        el.items = items
        el.total = tot
        return {}

    el.set_deps([L], fn)
    el.compute()
    return cons.add(el)



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


def _int_values(cons, args):
    """数论输入：支持多值或 {列表} → 整数列表。"""
    items = []
    for a in args:
        s = a.strip()
        if s.startswith("{"):
            L = _list_arg(cons, a)
            items.extend(int(round(float(v))) for v in L.items)
        elif s in cons.elements and cons.elements[s].kind == "list":
            items.extend(int(round(float(v))) for v in cons.elements[s].items)
        else:
            items.append(int(round(eval_number(cons, a))))
    return items


def _cmd_gcd(cons, defn, args):
    vals = _int_values(cons, args)
    if not vals:
        raise GeoError("GCD 需要数值")
    import math
    if any(v < 0 for v in vals):
        raise GeoError("GCD 需要非负整数")
    g = 0
    for v in vals:
        g = math.gcd(g, v)
    el = GeoNumber(label_of(defn), defn, float(g))
    el.free = False
    return cons.add(el)


def _cmd_lcm(cons, defn, args):
    vals = _int_values(cons, args)
    if not vals:
        raise GeoError("LCM 需要数值")
    import math
    if any(v < 0 for v in vals):
        raise GeoError("LCM 需要非负整数")
    l = 1
    for v in vals:
        l = l * v // math.gcd(l, v)
    el = GeoNumber(label_of(defn), defn, float(l))
    el.free = False
    return cons.add(el)


def _cmd_isprime(cons, defn, args):
    vals = _int_values(cons, args)
    if len(vals) != 1:
        raise GeoError("IsPrime 需要一个整数")
    import sympy
    el = GeoBoolean(label_of(defn), defn)
    el.free = False
    el.value = bool(sympy.isprime(vals[0]))
    el.detail = ""
    return cons.add(el)


def _cmd_divisors(cons, defn, args):
    vals = _int_values(cons, args)
    if len(vals) != 1 or vals[0] < 1:
        raise GeoError("Divisors 需要正整数")
    import sympy
    ds = sorted(sympy.divisors(vals[0]))
    el = GeoList(label_of(defn), defn, [float(v) for v in ds], "number")
    el.free = False
    return cons.add(el)


def _cmd_factorslist(cons, defn, args):
    """FactorsList[n]：质因数（含重数）列表，如 420 → {2,2,3,5,7}。"""
    vals = _int_values(cons, args)
    if len(vals) != 1 or vals[0] < 2:
        raise GeoError("FactorsList 需要 ≥2 的整数")
    import sympy
    out = []
    for p, e in sorted(sympy.factorint(vals[0]).items()):
        out.extend([float(p)] * e)
    el = GeoList(label_of(defn), defn, out, "number")
    el.free = False
    return cons.add(el)



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
        if rr <= 1e-12:
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
    if tot <= 1e-12:
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


def _resolve_complex(cons, s):
    z = _resolve(cons, s, ("complex",))
    return z


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


def _cmd_complex_abs(cons, defn, args):
    z = _resolve_complex(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [z],
               lambda d: {"value": math.hypot(d[0].re, d[0].im)})


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


def _cmd_slider(cons, defn, args):
    if len(args) not in (2, 3):
        raise GeoError("Slider 需要 最小值、最大值（可选步长）")
    lo = eval_number(cons, args[0])
    hi = eval_number(cons, args[1])
    step = eval_number(cons, args[2]) if len(args) == 3 else (hi - lo) / 100.0
    if hi <= lo:
        raise GeoError("最大值必须大于最小值")
    if step <= 0:
        raise GeoError("步长必须为正")
    el = GeoNumber(label_of(defn), defn, lo)
    el.min, el.max, el.step = lo, hi, step
    return cons.add(el)


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


def _num_deps(cons, defn):
    """defn 中引用的 number 对象（滑块等）→ deps。"""
    return [e for lab, e in cons.elements.items()
            if e.kind == "number" and re.search(r"\b" + re.escape(lab) + r"\b", defn)]


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

def _parse_sympy(body, symbols, cons=None):
    """sympy 解析（^ 与隐式乘法），可引用绘图区数值对象。"""
    import sympy
    ld = dict(symbols)
    ld.update({"e": sympy.E, "pi": sympy.pi, "π": sympy.pi,
               "ln": sympy.log, "log": sympy.log, "log10": lambda a: sympy.log(a, 10),
               "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan, "exp": sympy.exp,
               "sqrt": sympy.sqrt, "abs": sympy.Abs})
    if cons is not None:
        for lab, el in cons.elements.items():
            if el.kind == "number":
                ld[lab] = sympy.Float(el.value)
    return sympy.parsing.sympy_parser.parse_expr(
        body, local_dict=ld,
        transformations=(sympy.parsing.sympy_parser.standard_transformations
                         + (sympy.parsing.sympy_parser.implicit_multiplication_application,
                            sympy.parsing.sympy_parser.convert_xor)))


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


def _list_arg(cons, s):
    s = s.strip()
    el = _lookup(cons, s)
    if el is None and s.startswith("{"):
        # 内联列表 → 匿名列表（不注册，仅作依赖）
        from .parser import _split_brace, tokenize
        parts = _split_brace(tokenize(s))
        if parts and parts[0].startswith("("):
            items = []
            for p in parts:
                tp = _tuple_parts(p)
                items.append((eval_number(cons, tp[0]), eval_number(cons, tp[1])))
            el = GeoList("_hl", s, items, "point")
        else:
            items = [eval_number(cons, p) for p in parts]
            el = GeoList("_hl", s, items, "number")
        el.visible = False
        return el
    if el is None:
        raise GeoError("找不到对象 " + s)
    if el.kind != "list":
        raise GeoError(s + " 不是列表")
    return el


def _cmd_sum(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L],
               lambda d: {"value": float(sum(d[0].items))})


def _cmd_mean(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L],
               lambda d: {"value": float(sum(d[0].items)) / len(d[0].items) if d[0].items else 0.0})


def _cmd_median(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L], lambda d: {"value": _median(d[0].items)})


def _median(items):
    s = sorted(items)
    n = len(s)
    if n == 0:
        return 0.0
    if n % 2 == 1:
        return float(s[n // 2])
    return float((s[n // 2 - 1] + s[n // 2]) / 2.0)


def _cmd_mode(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L], lambda d: {"value": _mode(d[0].items)})


def _mode(items):
    if not items:
        return 0.0
    from collections import Counter
    c = Counter(items)
    return float(max(c, key=c.get))


def _cmd_variance(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L], lambda d: {"value": _variance(d[0].items)})


def _variance(items):
    n = len(items)
    if n == 0:
        return 0.0
    m = sum(items) / n
    return float(sum((v - m) ** 2 for v in items) / n)


def _cmd_stdev(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L], lambda d: {"value": math.sqrt(_variance(d[0].items))})


def _cmd_min(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L], lambda d: {"value": float(min(d[0].items)) if d[0].items else 0.0})


def _cmd_max(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L], lambda d: {"value": float(max(d[0].items)) if d[0].items else 0.0})


def _cmd_length(cons, defn, args):
    el = _resolve(cons, args[0])
    if el.kind == "segment":
        return _mk(cons, GeoNumber, "number", defn, [el],
                   lambda d: {"value": _dist((d[0].x1, d[0].y1), (d[0].x2, d[0].y2))})
    if el.kind == "list":
        return _mk(cons, GeoNumber, "number", defn, [el], lambda d: {"value": float(len(d[0].items))})
    raise GeoError("Length 需要线段或列表")


def _cmd_sort(cons, defn, args):
    L = _list_arg(cons, args[0])
    el = GeoList(label_of(defn), defn, None, "number")
    el.free = False
    el.set_deps([L], lambda d: {"items": sorted(d[0].items), "itemkind": "number"})
    return cons.add(el)


def _cmd_fitline(cons, defn, args):
    L = _list_arg(cons, args[0])
    if L.itemkind != "point":
        raise GeoError("FitLine 需要点列表，如 {(1,2),(2,3)}")
    return _mk(cons, GeoLine, "line", defn, [L], lambda d: _fitline_state(d[0].items))


def _fitline_state(items):
    import numpy as np
    xs = np.array([p[0] for p in items])
    ys = np.array([p[1] for p in items])
    if len(xs) < 2:
        raise GeoError("至少需要两个点")
    k, b = np.polyfit(xs, ys, 1)
    return _line_state(float(-k), 1.0, float(-b))



def _fit_expr(cons, defn, body):
    """Desmos 风格回归：y~a*x+b。数据 = 绘图区所有自由点，最小二乘拟合。"""
    import sympy
    m = re.match(r"^\s*y\s*~\s*(.+)$", body)
    if not m:
        raise GeoError("回归需形如 y~a*x+b")
    expr_str = m.group(1)
    x = sympy.Symbol("x")
    # 独立解析：回归参数（a,b,c…）必须是自由符号，不把已有数值对象当常量
    expr = sympy.parsing.sympy_parser.parse_expr(
        expr_str, local_dict={"x": x},
        transformations=(sympy.parsing.sympy_parser.standard_transformations
                         + (sympy.parsing.sympy_parser.implicit_multiplication_application,
                            sympy.parsing.sympy_parser.convert_xor)))
    params = sorted(expr.free_symbols - {x}, key=str)
    if not params:
        raise GeoError("回归表达式中未发现参数（如 a, b）")
    data = [(e.x, e.y) for lab, e in cons.elements.items()
            if e.kind == "point" and e.free and not lab.startswith("_")]
    if len(data) < 2:
        raise GeoError("至少需要两个自由点作为拟合数据（先创建点，如 A=(1,2) B=(2,4)）")
    import numpy as np
    try:
        import scipy.optimize as opt
    except Exception:
        raise GeoError("缺少 scipy，无法拟合")
    f_num = sympy.lambdify((x,) + tuple(params), expr, "numpy")
    xs = np.array([p[0] for p in data])
    ys = np.array([p[1] for p in data])

    def resid(pvals):
        return f_num(xs, *pvals) - ys

    best = None
    for guess in ([1.0] * len(params), [0.0] * len(params)):
        try:
            res = opt.least_squares(resid, guess)
            if best is None or res.cost < best.cost:
                best = res
        except Exception:
            continue
    if best is None:
        raise GeoError("拟合失败")
    vals = dict(zip(params, best.x))
    expr_sub = expr.subs(vals)
    label = label_of(defn) if defn and ("=" in defn or ":" in defn) else ""
    if not label:
        label = cons.auto_label("function")
    fdefn = label + "(x)=" + sympy.sstr(expr_sub)
    f_el = GeoFunction(label, fdefn)
    try:
        f_el.configure(cons, sympy.sstr(expr_sub), [])
    except Exception:
        raise GeoError("无法解析拟合表达式: " + expr_str)
    f_el.fit_msg = "拟合 " + expr_str + "：" + ", ".join(
        "%s=%s" % (pname, _fmt(float(vals[pname]))) for pname in params)
    created = [cons.add(f_el)]
    for pname in params:
        plab = str(pname)
        if plab in cons.elements:
            continue
        created.append(cons.add(GeoNumber(plab, plab + "=" + _fmt(float(vals[pname])), float(vals[pname]))))
    return created


def _cmd_fitexpr(cons, defn, args):
    """FitExp[y~a*x+b]：命令形式的回归拟合。"""
    if len(args) != 1:
        raise GeoError("FitExp 需要如 y~a*x+b 的表达式")
    return _fit_expr(cons, defn, args[0])

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


def label_of(defn):
    idx = defn.find("=")
    if idx == -1:
        idx = defn.find(":")
    return defn[:idx].strip()


# ---- 圆锥曲线 ----

def _conic_coeffs(el):
    """圆/圆锥曲线 → 一般系数 (a,b,c,d,e,f)。"""
    if el.kind == "circle":
        cx, cy, r = el.cx, el.cy, el.r
        return (1.0, 0.0, 1.0, -2 * cx, -2 * cy, cx * cx + cy * cy - r * r)
    if el.kind == "conic":
        return (el.a, el.b, el.c, el.d, el.e, el.f)
    raise GeoError("对象不是圆锥曲线")


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
        if denom < 1e-12:
            raise GeoError("准线退化")
        # 焦点到准线的垂足
        t = -(a * foc.x + b * foc.y + c) / denom
        hx, hy = foc.x + a * t, foc.y + b * t
        # 顶点 = 焦点与垂足中点
        vx, vy = (foc.x + hx) / 2, (foc.y + hy) / 2
        dx, dy = foc.x - hx, foc.y - hy
        p_len = math.hypot(dx, dy) / 2.0
        if p_len < 1e-12:
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
        if d2 > conic.r + 1e-9:
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
    if d2 <= r + 1e-9:
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
    if r <= 1e-9:
        raise GeoError("退化圆弧")
    ang = _m.atan2(pt.y - cy, pt.x - cx)
    a1 = arc.ang1
    span = (arc.ang2 - a1) % (2 * _m.pi)
    # 环内最近角：优先落在 [a1, a1+span]
    d1 = (ang - a1) % (2 * _m.pi)
    use = a1 + d1 if d1 <= span + 1e-9 else None
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
            p0x = -a * c / denom if denom > 1e-12 else 0.0
            p0y = -b * c / denom if denom > 1e-12 else 0.0
            dx, dy = (-b / math.sqrt(denom), a / math.sqrt(denom)) if denom > 1e-12 else (1.0, 0.0)
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
    p0x = -a * c / denom if denom > 1e-12 else 0.0
    p0y = -b * c / denom if denom > 1e-12 else 0.0
    dx, dy = (-b / math.sqrt(denom), a / math.sqrt(denom)) if denom > 1e-12 else (1.0, 0.0)
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


# ---- 3D ----

def _cmd_surface(cons, defn, args):
    """Surface[z=f(x,y), xmin, xmax, ymin, ymax, 网格数?]：显式曲面网格。

    网格元素复用 polyhedron 渲染/导出/求交链路，solid="surface" 区分类型；
    表达式可引用既有滑块（重算时取当前值），开放式曲面不做外向规范化。
    """
    if len(args) not in (5, 6):
        raise GeoError("Surface 需要 z=f(x,y), xmin, xmax, ymin, ymax[, 网格数]")
    expr = args[0]
    xmin, xmax = eval_number(cons, args[1]), eval_number(cons, args[2])
    ymin, ymax = eval_number(cons, args[3]), eval_number(cons, args[4])
    n = int(eval_number(cons, args[5])) if len(args) == 6 else 24
    if xmax <= xmin or ymax <= ymin:
        raise GeoError("Surface 的范围需满足 xmax > xmin 且 ymax > ymin")
    n = max(2, min(n, 96))
    el = Geo3D(label_of(defn), defn)
    el.objtype = "polyhedron"
    el.solid = "surface"
    deps = _num_deps(cons, defn)
    el.set_deps(deps, _surface_compute(expr, xmin, xmax, ymin, ymax, n))
    return cons.add(el)


def _surface_compute(expr, xmin, xmax, ymin, ymax, n):
    """构造 z=f(x,y) 的 (n+1)² 网格（面片绕向一致；不做凸体外向规范化）。"""
    import sympy

    def fn(deps):
        vals = {}
        for d in deps:
            if hasattr(d, "value"):
                vals[d.label] = d.value
        try:
            body = expr.replace("^", "**")
            e = sympy.sympify(body, locals={**vals, "pi": sympy.pi, "e": sympy.E})
            f = sympy.lambdify(sympy.symbols("x y"), e, "numpy")
            xs = [xmin + (xmax - xmin) * i / n for i in range(n + 1)]
            ys = [ymin + (ymax - ymin) * j / n for j in range(n + 1)]
            verts, faces, edges = [], [], []
            for j in range(n + 1):
                for i in range(n + 1):
                    z = f(xs[i], ys[j])
                    z = float(z) if not hasattr(z, "__len__") else float(z[0])
                    if not math.isfinite(z):
                        raise GeoError("曲面在该网格点取值非有限（f(%.3f,%.3f) 可能为奇点）" % (xs[i], ys[j]))
                    verts.append([xs[i], ys[j], z])
            def vid(i, j):
                return j * (n + 1) + i
            for j in range(n):
                for i in range(n):
                    faces.append([vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)])
                    edges.append([vid(i, j), vid(i + 1, j)])
                    edges.append([vid(i, j), vid(i, j + 1)])
            for i in range(n):
                edges.append([vid(i, n), vid(i + 1, n)])
            for j in range(n):
                edges.append([vid(n, j), vid(n, j + 1)])
        except GeoError:
            raise
        except Exception as ex:
            raise GeoError("曲面表达式无法求值：" + str(ex)[:80])
        return {"objtype": "polyhedron", "solid": "surface",
                "data": {"verts": verts, "faces": faces, "edges": edges,
                         "grid": n, "expr": expr}}
    return fn


def _cmd_mesh(cons, defn, args):
    """Mesh[网格id]：把 OBJ 导入的网格数据建成 3D 网格元素（objtype=polyhedron, solid=mesh）。"""
    if len(args) != 1:
        raise GeoError("Mesh 需要一个网格 id（由 OBJ 导入生成）")
    mid = args[0].strip()
    from . import mesh_store
    rec = mesh_store.get(mid)
    if rec is None:
        raise GeoError("找不到网格数据（请先导入 OBJ）: " + mid)
    data = {"verts": rec["verts"], "faces": rec["faces"],
            "edges": mesh_store.edges_of(rec["faces"]), "meshid": mid}
    el = _mk(cons, Geo3D, "geo3d", defn, [],
             lambda d: {"objtype": "polyhedron", "solid": "mesh", "data": data})
    el.meshid = mid
    return el


def _cmd_fitplane(cons, defn, args):
    """FitPlane[点列表]：三维点云最小二乘拟合平面（法向 = 协方差最小特征向量）。"""
    if len(args) != 1:
        raise GeoError("FitPlane 需要点列表，如 {(0,0,0),(1,0,0),(0,1,1),(1,1,1)}")
    L = _list_arg(cons, args[0])
    if L.itemkind not in ("point", "point3d"):
        raise GeoError("FitPlane 需要点列表（三维点，如 {(0,0,0),(1,0,0),(0,1,1)}）")
    return _mk(cons, Geo3D, "geo3d", defn, [L], lambda d: _fitplane_state(d[0].items))


def _fitplane_state(items):
    import numpy as np
    pts = np.array([[float(p[0]), float(p[1]), float(p[2] if len(p) > 2 else 0.0)] for p in items])
    if len(pts) < 3:
        raise GeoError("FitPlane 至少需要 3 个点")
    ctr = pts.mean(axis=0)
    q = pts - ctr
    cov = q.T @ q
    w, v = np.linalg.eigh(cov)        # 升序：w[0] ≤ w[1] ≤ w[2]
    if w[2] <= 1e-12:
        raise GeoError("点云重合，无法确定平面")
    if w[1] <= 1e-9 * w[2]:
        raise GeoError("点云共线（秩 1），无法确定平面")
    nrm = v[:, 0]                     # 最小特征值对应法向
    ln = float(np.linalg.norm(nrm))
    if ln < 1e-12:
        raise GeoError("点云退化，无法确定法向")
    nx, ny, nz = (nrm / ln).tolist()
    dd = -(nx * ctr[0] + ny * ctr[1] + nz * ctr[2])
    # 平面内正交基（供渲染/面片使用）
    ref = [1.0, 0.0, 0.0] if abs(nx) < 0.9 else [0.0, 1.0, 0.0]
    ux = ref[1] * nz - ref[2] * ny
    uy = ref[2] * nx - ref[0] * nz
    uz = ref[0] * ny - ref[1] * nx
    lu = math.sqrt(ux * ux + uy * uy + uz * uz)
    ux, uy, uz = ux / lu, uy / lu, uz / lu
    vx = ny * uz - nz * uy
    vy = nz * ux - nx * uz
    vz = nx * uy - ny * ux
    return {"objtype": "plane", "solid": "plane",
            "data": {"a": nx, "b": ny, "c": nz, "d": dd,
                     "ax": float(ctr[0]), "ay": float(ctr[1]), "az": float(ctr[2]),
                     "ux": ux, "uy": uy, "uz": uz, "vx": vx, "vy": vy, "vz": vz,
                     "fit": True}}


def _cmd_sphere(cons, defn, args):
    if len(args) != 2:
        raise GeoError("Sphere 需要 球心 和 球面点或半径")
    c = _point_arg(cons, args[0])
    s = args[1].strip()
    el2 = _lookup(cons, s)
    if el2 is not None and el2.kind == "point":
        return _mk(cons, Geo3D, "geo3d", defn, [c, el2], lambda d: _sphere_state(d[0], d[1]))
    if el2 is not None and el2.kind == "number":
        return _mk(cons, Geo3D, "geo3d", defn, [c, el2], lambda d: _sphere_state_r(d[0], d[1]))
    r = eval_number(cons, args[1])
    return _mk(cons, Geo3D, "geo3d", defn, [c], lambda d: _sphere_state_fixed(d[0], r))


def _sphere_check(r):
    if r <= 1e-12:
        raise GeoError("球半径需为正")
    return r


def _sphere_state(c, p):
    r = math.sqrt((p.x - c.x) ** 2 + (p.y - c.y) ** 2 + ((p.z or 0) - (c.z or 0)) ** 2)
    return {"objtype": "sphere", "solid": "sphere", "data": {"cx": c.x, "cy": c.y, "cz": c.z or 0, "r": _sphere_check(r)}}


def _sphere_state_r(c, r):
    return {"objtype": "sphere", "solid": "sphere", "data": {"cx": c.x, "cy": c.y, "cz": c.z or 0, "r": _sphere_check(r.value)}}


def _sphere_state_fixed(c, r):
    return {"objtype": "sphere", "solid": "sphere", "data": {"cx": c.x, "cy": c.y, "cz": c.z or 0, "r": _sphere_check(r)}}


def _cmd_plane(cons, defn, args):
    if len(args) != 3:
        raise GeoError("Plane 需要三个点")
    a = _point_arg(cons, args[0])
    b = _point_arg(cons, args[1])
    c = _point_arg(cons, args[2])
    return _mk(cons, Geo3D, "geo3d", defn, [a, b, c], lambda d: _plane_state(d[0], d[1], d[2]))


def _plane_state(a, b, c):
    ax, ay, az = a.x, a.y, a.z or 0
    bx, by, bz = b.x, b.y, b.z or 0
    cx, cy, cz = c.x, c.y, c.z or 0
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
    if ln < 1e-12:
        raise GeoError("三点共线，无法确定平面")
    nx, ny, nz = n[0] / ln, n[1] / ln, n[2] / ln
    dd = -(nx * ax + ny * ay + nz * az)
    return {"objtype": "plane", "solid": "plane",
            "data": {"a": nx, "b": ny, "c": nz, "d": dd,
                     "ax": ax, "ay": ay, "az": az, "ux": ux, "uy": uy, "uz": uz,
                     "vx": vx, "vy": vy, "vz": vz}}


def _is_segment_el(el) -> bool:
    return el.kind == "segment" or (el.kind == "geo3d" and getattr(el, "objtype", "") == "segment")


def _cube_seg_pts(el):
    """取线段两端点（3D 元组），支持 2D 线段与 3D 线段。"""
    if el.kind == "segment":
        return (el.x1, el.y1, 0.0), (el.x2, el.y2, 0.0)
    if el.kind == "geo3d" and getattr(el, "objtype", "") == "segment":
        d = el.data
        return ((d.get("x1", 0.0), d.get("y1", 0.0), d.get("z1", 0.0)),
                (d.get("x2", 0.0), d.get("y2", 0.0), d.get("z2", 0.0)))
    raise GeoError("需要一个线段对象")


def _elem_or_point(cons, s: str):
    """参数解析：优先按已有元素标签；否则尝试 (x,y) / (x,y,z) 字面量点。"""
    txt = s.strip()
    el = _lookup(cons, txt)
    if el is not None:
        return el
    if txt.startswith("("):
        return _point_arg(cons, txt)
    raise GeoError("找不到对象 " + txt)


def _cube_from_edge(p1, p2, dirpt=None):
    """由一条棱 p1→p2 构建立方体；dirpt 为相邻顶点方向（可选，缺省系统自选）。

    - 2D 线段且未给方向点：底面在 xy 平面、AB 垂直方向补全，向 +z 挤出（与 Cube[A,B] 一致）；
    - 其它情况：把方向点（或 z 轴）对 AB 取垂直分量并缩放到边长，得到相邻棱方向。
    """
    u = [p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]]
    L = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
    if L < 1e-12:
        raise GeoError("线段退化，无法构建立方体")
    n = [u[0] / L, u[1] / L, u[2] / L]
    # 经典 2D 情形
    if dirpt is None and abs(p1[2]) < 1e-12 and abs(p2[2]) < 1e-12:
        v = [-u[1], u[0], 0.0]
        base = [list(p1), list(p2),
                [p2[0] + v[0], p2[1] + v[1], p2[2] + v[2]],
                [p1[0] + v[0], p1[1] + v[1], p1[2] + v[2]]]
        return _cube_build(base, (0.0, 0.0, 1.0), L)
    # 一般情形：确定相邻棱方向
    if dirpt is not None:
        w = [dirpt[0] - p1[0], dirpt[1] - p1[1], dirpt[2] - p1[2]]
    else:
        w = [0.0, 0.0, 1.0]
        if abs(n[2]) > 0.999:
            w = [1.0, 0.0, 0.0]
    dot = w[0] * n[0] + w[1] * n[1] + w[2] * n[2]
    v = [w[0] - dot * n[0], w[1] - dot * n[1], w[2] - dot * n[2]]
    lv = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if lv < 1e-9:
        # 方向与棱共线：换参考轴
        ref = [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0]
        dot2 = ref[0] * n[0] + ref[1] * n[1] + ref[2] * n[2]
        v = [ref[0] - dot2 * n[0], ref[1] - dot2 * n[1], ref[2] - dot2 * n[2]]
        lv = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
        if lv < 1e-12:
            raise GeoError("无法确定立方体方向")
    v = [v[0] / lv * L, v[1] / lv * L, v[2] / lv * L]
    base = [list(p1), list(p2),
            [p2[0] + v[0], p2[1] + v[1], p2[2] + v[2]],
            [p1[0] + v[0], p1[1] + v[1], p1[2] + v[2]]]
    vn = [v[0] / L, v[1] / L, v[2] / L]
    nx = n[1] * vn[2] - n[2] * vn[1]
    ny = n[2] * vn[0] - n[0] * vn[2]
    nz = n[0] * vn[1] - n[1] * vn[0]
    ln = math.sqrt(nx * nx + ny * ny + nz * nz)
    if ln < 1e-12:
        raise GeoError("底面退化，无法构建立方体")
    return _cube_build(base, (nx / ln, ny / ln, nz / ln), L)


def _cube_from_poly(poly):
    """由 4 顶点正方形多边形构建立方体（底面 = 该正方形，高度 = 边长）。"""
    pts = [[x, y, 0.0] for x, y in zip(poly.xs, poly.ys)]
    if len(pts) != 4:
        raise GeoError("Cube[正方形] 需要 4 个顶点的正方形")
    def _sub(a, b):
        return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
    def _dot(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    def _norm(a):
        return math.sqrt(_dot(a, a))
    e = [_sub(pts[(i + 1) % 4], pts[i]) for i in range(4)]
    lens = [_norm(x) for x in e]
    if min(lens) < 1e-9:
        raise GeoError("正方形边长退化")
    if max(lens) - min(lens) > 1e-6 * max(lens):
        raise GeoError("Cube[正方形] 的四边形边长不等，不是正方形")
    if abs(_dot(e[0], e[1])) > 1e-6 * (lens[0] * lens[1]):
        raise GeoError("Cube[正方形] 的相邻边不垂直，不是正方形")
    u, v = e[0], e[1]
    nv = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    ln = _norm(nv)
    if ln < 1e-12:
        raise GeoError("正方形退化")
    return _cube_build(pts, (nv[0] / ln, nv[1] / ln, nv[2] / ln), lens[0])


def _cmd_cube(cons, defn, args):
    """Cube[A,B] / Cube[A,B,C] / Cube[线段] / Cube[线段, 方向点] / Cube[正方形]。

    - 两空间点：以 AB 为棱，底面在 AB 垂直方向，高 = 边长；
    - 三点：A 角点 + 两相邻顶点（自动识别，也支持连续/对角顺序）；
    - 线段：以线段为棱；未给方向点时系统自选垂直方向（2D 线段向 +z 挤出）；
    - 线段 + 点：以线段为棱、该点确定相邻棱方向（自动投影到垂直方向）；
    - 正方形多边形（或正四边形）：以该正方形为底面。
    """
    if len(args) == 1:
        el = _resolve(cons, args[0])
        if el.kind == "polygon":
            return _mk(cons, Geo3D, "geo3d", defn, [el], lambda d: _cube_from_poly(d[0]))
        if _is_segment_el(el):
            def _f(d):
                p1, p2 = _cube_seg_pts(d[0])
                return _cube_from_edge(p1, p2, None)
            return _mk(cons, Geo3D, "geo3d", defn, [el], _f)
        raise GeoError("Cube 需要一个正方形（多边形）或线段，或两点/三点")
    if len(args) == 2:
        o1 = _elem_or_point(cons, args[0])
        o2 = _elem_or_point(cons, args[1])
        if _is_segment_el(o1) and o2.kind == "point":
            seg_el, pt_el = o1, o2
        elif _is_segment_el(o2) and o1.kind == "point":
            seg_el, pt_el = o2, o1
        else:
            seg_el = pt_el = None
        if seg_el is not None:
            def _f(d):
                seg = d[0] if _is_segment_el(d[0]) else d[1]
                pt = d[1] if _is_segment_el(d[0]) else d[0]
                p1, p2 = _cube_seg_pts(seg)
                return _cube_from_edge(p1, p2, (pt.x, pt.y, pt.z or 0))
            return _mk(cons, Geo3D, "geo3d", defn, [seg_el, pt_el], _f)
        a = _point_arg(cons, args[0])
        b = _point_arg(cons, args[1])
        return _mk(cons, Geo3D, "geo3d", defn, [a, b], lambda d: _cube_state2(d[0], d[1]))
    if len(args) == 3:
        a = _point_arg(cons, args[0])
        b = _point_arg(cons, args[1])
        c = _point_arg(cons, args[2])
        # 预检：三点必须能构成正方形（两点距离相等为边、第三点在对角）
        def _d2(p, q):
            return (p.x - q.x) ** 2 + (p.y - q.y) ** 2 + ((p.z or 0) - (q.z or 0)) ** 2
        d01, d02, d12 = _d2(a, b), _d2(a, c), _d2(b, c)
        ok3 = (abs(d01 - d02) < 1e-9 and d01 < d12) or               (abs(d01 - d12) < 1e-9 and d01 < d02) or               (abs(d02 - d12) < 1e-9 and d02 < d01)
        if not ok3:
            raise GeoError("Cube 三点需构成正方形底面（两点距离相等为边）")
        return _mk(cons, Geo3D, "geo3d", defn, [a, b, c], lambda d: _cube_state(d[0], d[1], d[2]))
    raise GeoError("Cube 需要 两点 / 三点 / 线段 / 线段+点 / 正方形")


def _cube_build(base_verts, n, h):
    """由底面 4 顶点 + 单位法向 n + 高度 h 构建立方体（8 顶点/6 面/12 边）。"""
    verts = [list(v) for v in base_verts]
    for v in base_verts:
        verts.append([v[0] + n[0] * h, v[1] + n[1] * h, v[2] + n[2] * h])
    # 底面 0,1,2,3；顶面 4,5,6,7（对应）
    faces = [
        [0, 1, 2, 3], [4, 6, 7, 5], [0, 1, 5, 4],
        [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7],
    ]
    edges = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4],
             [0, 4], [1, 5], [2, 6], [3, 7]]
    return {"objtype": "cube", "solid": "cube",
            "data": {"verts": verts, "faces": _normalize_mesh(verts, faces), "edges": edges}}


def _cube_state(a, b, c):
    """三点构成立方体底面正方形：自动识别哪一点是角点（两条最短边共用的顶点），
    另两点为相邻顶点；高度 = 边长，沿底面法向垂直延伸。
    支持：角点+两相邻、连续三点（中间为角点）、对角两点+角点 三种输入顺序。"""
    pts = [[a.x, a.y, a.z or 0], [b.x, b.y, b.z or 0], [c.x, c.y, c.z or 0]]

    def _d2(p, q):
        return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2

    d01 = _d2(pts[0], pts[1])
    d02 = _d2(pts[0], pts[2])
    d12 = _d2(pts[1], pts[2])
    # 找出角点：它到另外两点的距离相等且最短（两条边），第三条距离最长（对角线）
    # 角点 i：到 j、k 的平方距离相等（d_ij == d_ik），且小于 d_jk（对角线最长）
    corner = -1
    if abs(d01 - d02) < 1e-9 and d01 < d12:
        corner = 0          # a 是角点
    elif abs(d01 - d12) < 1e-9 and d01 < d02:
        corner = 1          # b 是角点
    elif abs(d02 - d12) < 1e-9 and d02 < d01:
        corner = 2          # c 是角点
    if corner < 0:
        raise GeoError("三点不能确定正方形底面（需两点距离相等为边、第三点在对角）")
    # 角点 → 相邻两顶点（环绕顺序 角点, 邻1, 对顶点, 邻2）
    o = pts[corner]
    n1 = pts[(corner + 1) % 3]
    n2 = pts[(corner + 2) % 3]
    u = [n1[0] - o[0], n1[1] - o[1], n1[2] - o[2]]
    v = [n2[0] - o[0], n2[1] - o[1], n2[2] - o[2]]
    # 环绕顺序：o, n1, o+u+v(=对角), n2
    base = [o,
            [o[0] + u[0], o[1] + u[1], o[2] + u[2]],
            [o[0] + u[0] + v[0], o[1] + u[1] + v[1], o[2] + u[2] + v[2]],
            [o[0] + v[0], o[1] + v[1], o[2] + v[2]]]
    # 法向 = u × v（归一化）
    nx = u[1] * v[2] - u[2] * v[1]
    ny = u[2] * v[0] - u[0] * v[2]
    nz = u[0] * v[1] - u[1] * v[0]
    ln = math.sqrt(nx * nx + ny * ny + nz * nz)
    if ln < 1e-12:
        raise GeoError("三点共线/重合，无法确定底面")
    nx, ny, nz = nx / ln, ny / ln, nz / ln
    # 边长 = |u|（正方形两邻边等长）
    h = math.sqrt(u[0] * u[0] + u[1] * u[1] + u[2] * u[2])
    return _cube_build(base, (nx, ny, nz), h)


def _cube_state2(a, b):
    """两点：AB 为底面正方形的一条边，正方形在 AB 垂直方向（xy 平面内），高 = 边长。"""
    ax, ay, az = a.x, a.y, a.z or 0
    ux, uy, uz = b.x - ax, b.y - ay, (b.z or 0) - az
    h = math.sqrt(ux * ux + uy * uy + uz * uz)
    if h < 1e-12:
        raise GeoError("两点重合，无法构成底面")
    # 底面正方形在 AB 的垂直方向补全：v = rot90(u)（xy 平面内）
    vx, vy, vz = -uy, ux, 0.0
    lv = math.sqrt(vx * vx + vy * vy)
    if lv < 1e-12:
        # AB 竖直：退化为水平方向补全
        vx, vy, vz = h, 0.0, 0.0
    else:
        vx, vy = vx / lv * h, vy / lv * h
    base = [[ax, ay, az],
            [ax + ux, ay + uy, az + uz],
            [ax + ux + vx, ay + uy + vy, az + uz + vz],   # D：环绕顺序 A→B→D→C
            [ax + vx, ay + vy, az + vz]]
    # 法向 = u × v（归一化，垂直底面）
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    ln = math.sqrt(nx * nx + ny * ny + nz * nz)
    if ln < 1e-12:
        nx, ny, nz = 0.0, 0.0, 1.0
    else:
        nx, ny, nz = nx / ln, ny / ln, nz / ln
    return _cube_build(base, (nx, ny, nz), h)


# ---------------------------------------------------------------------------
# 3D 多面体：圆锥/圆柱/棱柱/棱锥/正四面体/正八面体/正二十面体/正十二面体
# 统一数据模型：{verts: [[x,y,z]...], faces: [[idx...]...], edges: [[i,j]...]}
# ---------------------------------------------------------------------------

def _poly_state(verts, faces, edges):
    return {"objtype": "polyhedron",
            "data": {"verts": verts, "faces": _normalize_mesh(verts, faces), "edges": edges}}


def _poly3_points(cons, args, n, name):
    if len(args) != n:
        raise GeoError(name + " 需要 " + str(n) + " 个点")
    return [_point_arg(cons, a) for a in args]


def _ortho_frame(a, b, c):
    """由三点构造正交基 (u, v, n)：u 沿 B-A，v 在 ABC 平面内，n = u×v。"""
    u = [b.x - a.x, b.y - a.y, (b.z or 0) - (a.z or 0)]
    lu = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
    if lu < 1e-12:
        raise GeoError("基准两点重合，无法确定立体方向")
    u = [u[0] / lu, u[1] / lu, u[2] / lu]
    w = [c.x - a.x, c.y - a.y, (c.z or 0) - (a.z or 0)]
    n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]
    ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
    if ln < 1e-12:
        n = [0.0, 0.0, 1.0]
    else:
        n = [n[0] / ln, n[1] / ln, n[2] / ln]
    v = [n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0]]
    return u, v, n


def _poly_register(cons, defn, deps, fn, objtype):
    """创建多面体元素：objtype 仍为历史值 polyhedron，solid 记录具体立体类型。"""
    el = _mk(cons, Geo3D, "geo3d", defn, deps, fn)
    return _tag3d(el, objtype)


def _number_arg(cons, s):
    """数值参数：已有 数值/角度 元素 → (el, None)；否则字面量 → (None, value)。"""
    txt = s.strip()
    el = _lookup(cons, txt)
    if el is not None and el.kind in ("number", "angle"):
        return el, None
    return None, eval_number(cons, txt)


def _vector3_arg(cons, s):
    """方向参数：向量元素 → (dx,dy,0)；元组 → (dx,dy,dz)；否则 None。"""
    txt = s.strip()
    el = _lookup(cons, txt)
    if el is not None:
        if el.kind == "vector":
            return (el.dx, el.dy, 0.0)
        return None
    if txt.startswith("("):
        parts = _tuple_parts_any(txt)
        vals = [eval_number(cons, p) for p in parts]
        if len(vals) == 2:
            return (vals[0], vals[1], 0.0)
        if len(vals) == 3:
            return (vals[0], vals[1], vals[2])
    return None


def _frame_from_axis(d):
    """由轴向构造正交基 (u, v, n)：n 为单位轴，u/v 为垂直平面的基。"""
    n = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
    if n < 1e-12:
        raise GeoError("方向向量退化")
    n = [d[0] / n, d[1] / n, d[2] / n]
    ref = [0.0, 0.0, 1.0]
    if abs(n[2]) > 0.9:
        ref = [1.0, 0.0, 0.0]
    dot = ref[0] * n[0] + ref[1] * n[1] + ref[2] * n[2]
    u = [ref[0] - dot * n[0], ref[1] - dot * n[1], ref[2] - dot * n[2]]
    ln = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
    if ln < 1e-12:
        ref = [0.0, 1.0, 0.0]
        dot = ref[0] * n[0] + ref[1] * n[1] + ref[2] * n[2]
        u = [ref[0] - dot * n[0], ref[1] - dot * n[1], ref[2] - dot * n[2]]
        ln = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
    u = [u[0] / ln, u[1] / ln, u[2] / ln]
    v = [n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0]]
    return u, v, n


# ---- 立体体积 / 表面积（网格散度定理 + 解析优先）----

def _with_analytic(state, **kw):
    """给网格状态附加解析参数，供 Volume/Area 取精确值（锥/柱为旋转体）。"""
    st = dict(state)
    data = dict(st.get("data", {}))
    data["analytic"] = kw
    st["data"] = data
    return st


def _newell_normal(vs, face):
    """Newell 法向（模长 = 2×面积）；对面顶点环序不敏感程度优于简单叉积。"""
    nx = ny = nz = 0.0
    n = len(face)
    for i in range(n):
        a = vs[face[i]]
        b = vs[face[(i + 1) % n]]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return nx, ny, nz


def _normalize_mesh(verts, faces):
    """把网格面统一为「平面内正确环序（凸多边形）+ 外向法向」。

    历史构造器的面顶点顺序/朝向并不一致（例如立方体顶面是 [4,6,7,5] 的蝴蝶结序、
    二十面体 20 个面里 10 个朝内），会导致体积计算相互抵消、遮挡判断异常。
    这里以顶点质心为内点统一修正——所有立体都是凸体，此规则成立。
    """
    if not verts or not faces:
        return faces
    cx = sum(v[0] for v in verts) / len(verts)
    cy = sum(v[1] for v in verts) / len(verts)
    cz = sum(v[2] for v in verts) / len(verts)
    out = []
    for f in faces:
        idx = list(f)
        if len(idx) < 3:
            out.append(idx)
            continue
        nx, ny, nz = _newell_normal(verts, idx)
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        if ln < 1e-12 and len(idx) < 3:
            continue
        if ln < 1e-12:
            # 蝴蝶结/乱序面（如立方体顶面 [4,6,7,5]）Newell 法向会抵消为 0：
            # 改用「最大面积三角形」的叉积作平面法向，再走同一套排序 + 外向判定。
            best = (0.0, 0.0, 0.0, 0.0)
            n = len(idx)
            for i in range(n):
                for j in range(i + 1, n):
                    for k in range(j + 1, n):
                        ax, ay, az = verts[idx[i]]
                        bx, by, bz = verts[idx[j]]
                        qx, qy, qz = verts[idx[k]]
                        ux_, uy_, uz_ = bx - ax, by - ay, bz - az
                        vx_, vy_, vz_ = qx - ax, qy - ay, qz - az
                        mx = uy_ * vz_ - uz_ * vy_
                        my = uz_ * vx_ - ux_ * vz_
                        mz = ux_ * vy_ - uy_ * vx_
                        area = 0.5 * math.sqrt(mx * mx + my * my + mz * mz)
                        if area > best[0]:
                            best = (area, mx, my, mz)
            if best[0] < 1e-12:
                continue          # 退化面（面积≈0）直接丢弃，避免污染体积/遮挡计算
            nx, ny, nz = best[1], best[2], best[3]
            ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        hx, hy, hz = nx / ln, ny / ln, nz / ln
        fx = sum(verts[i][0] for i in idx) / len(idx)
        fy = sum(verts[i][1] for i in idx) / len(idx)
        fz = sum(verts[i][2] for i in idx) / len(idx)
        # 面内正交基：u 指向第一个不重合顶点，w = n × u
        ux = uy = uz = 0.0
        for i in idx:
            dx, dy, dz = verts[i][0] - fx, verts[i][1] - fy, verts[i][2] - fz
            if math.sqrt(dx * dx + dy * dy + dz * dz) > 1e-12:
                d = math.sqrt(dx * dx + dy * dy + dz * dz)
                ux, uy, uz = dx / d, dy / d, dz / d
                break
        wx = hy * uz - hz * uy
        wy = hz * ux - hx * uz
        wz = hx * uy - hy * ux
        # 按面内极角排序 → 正确环序（凸多边形）
        def _ang(i):
            dx, dy, dz = verts[i][0] - fx, verts[i][1] - fy, verts[i][2] - fz
            return math.atan2(dx * wx + dy * wy + dz * wz, dx * ux + dy * uy + dz * uz)
        idx = sorted(idx, key=_ang)
        # 外向：法向应背离体内一点（顶点质心）
        nx2, ny2, nz2 = _newell_normal(verts, idx)
        if nx2 * (fx - cx) + ny2 * (fy - cy) + nz2 * (fz - cz) < 0:
            idx.reverse()
        out.append(idx)
    return out


def _mesh_volume(data) -> float:
    """闭合三角网格体积：Σ det(a,b,c)/6（面片环绕一致，取绝对值兜底）。"""
    vs = data.get("verts") or []
    V = 0.0
    for face in data.get("faces") or []:
        if len(face) < 3:
            continue
        a = vs[face[0]]
        for i in range(1, len(face) - 1):
            b, c = vs[face[i]], vs[face[i + 1]]
            V += (a[0] * (b[1] * c[2] - b[2] * c[1])
                  - a[1] * (b[0] * c[2] - b[2] * c[0])
                  + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return abs(V) / 6.0


def _mesh_area(data) -> float:
    """闭合网格表面积：各面三角扇面积之和。"""
    vs = data.get("verts") or []
    A = 0.0
    for face in data.get("faces") or []:
        if len(face) < 3:
            continue
        a = vs[face[0]]
        for i in range(1, len(face) - 1):
            b, c = vs[face[i]], vs[face[i + 1]]
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            A += 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)
    return A


def _solid_volume(el) -> float:
    d = getattr(el, "data", None) or {}
    an = d.get("analytic") or {}
    t = an.get("type")
    if t == "cone":
        return math.pi * an["r"] ** 2 * an["h"] / 3.0
    if t == "cylinder":
        return math.pi * an["r"] ** 2 * an["h"]
    if t == "infinite_cone":
        raise GeoError("无限圆锥没有有限体积")
    if getattr(el, "objtype", "") == "sphere":
        return 4.0 / 3.0 * math.pi * d["r"] ** 3
    if getattr(el, "solid", "") == "surface":
        raise GeoError("曲面没有体积（可用 Area 求曲面面积）")
    if "verts" in d:
        return _mesh_volume(d)
    raise GeoError("Volume 不支持该对象（需要球/圆锥/圆柱/棱柱/棱锥/正多面体）")


def _solid_area(el) -> float:
    d = getattr(el, "data", None) or {}
    an = d.get("analytic") or {}
    t = an.get("type")
    if t == "cone":
        r, h = an["r"], an["h"]
        return math.pi * r * (r + math.sqrt(r * r + h * h))     # 底 + 侧
    if t == "cylinder":
        r, h = an["r"], an["h"]
        return 2.0 * math.pi * r * (r + h)                      # 两侧盖 + 侧面
    if t == "infinite_cone":
        raise GeoError("无限圆锥没有有限表面积")
    if getattr(el, "objtype", "") == "sphere":
        return 4.0 * math.pi * d["r"] ** 2
    if "verts" in d:
        return _mesh_area(d)
    raise GeoError("Area 不支持该对象（需要多边形/圆/椭圆/函数或 3D 立体）")


def _cone_mesh_axis(apex, base_center, radius, N=48, cap=True):
    """由 顶点 / 底面中心 / 半径 构造有限圆锥网格（底面垂直于 顶点-底心 轴）。"""
    if radius <= 1e-12:
        raise GeoError("半径需为正")
    axis = [apex[0] - base_center[0], apex[1] - base_center[1], apex[2] - base_center[2]]
    u, v, _ = _frame_from_axis(axis)
    base = []
    for i in range(N):
        a = 2 * math.pi * i / N
        base.append([base_center[0] + radius * (math.cos(a) * u[0] + math.sin(a) * v[0]),
                     base_center[1] + radius * (math.cos(a) * u[1] + math.sin(a) * v[1]),
                     base_center[2] + radius * (math.cos(a) * u[2] + math.sin(a) * v[2])])
    verts = base + [list(apex)]
    faces = ([list(range(N))] if cap else []) + [[i, (i + 1) % N, N] for i in range(N)]
    edges = [[i, (i + 1) % N] for i in range(N)] + [[i, N] for i in range(N)]
    return _poly_state(verts, faces, edges)


def _cone_from_circle_state(cir, h):
    """Cone[圆, 高]：底面为该圆（xy 平面），沿 +z 方向高度 h。"""
    if getattr(cir, "error", None):
        raise GeoError("底面圆无效：" + str(cir.error))
    if cir.kind == "conic":
        cx, cy, r = cir.cx, cir.cy, cir.semi_a
    else:
        cx, cy, r = cir.cx, cir.cy, cir.r
    if h <= 1e-12:
        raise GeoError("高度需为正")
    return _with_analytic(_cone_mesh_axis([cx, cy, h], [cx, cy, 0.0], r), type="cone", r=r, h=h)


def _cone_apex_center_radius_state(apex, base_center, radius):
    """Cone[顶点, 底心, 半径]。"""
    h = math.sqrt(sum((apex[i] - base_center[i]) ** 2 for i in range(3)))
    return _with_analytic(_cone_mesh_axis(apex, base_center, radius), type="cone", r=radius, h=h)


def _infinite_cone_state(apex, dirv, ang_deg, N=36):
    """Cone[顶点, 方向向量, 角]：以顶点为公共点的无限双圆锥（半角为 ang_deg°）。"""
    if not (0.0 < ang_deg < 90.0):
        raise GeoError("圆锥半角需在 (0°, 90°) 之间")
    u, v, n = _frame_from_axis(dirv)
    t = math.tan(math.radians(ang_deg))
    levels = [0.6, 1.2, 2.4, 4.8, 9.6, 18.0]
    verts = [list(apex)]
    faces = []
    edges = []
    for s in (1.0, -1.0):
        prev = None
        for L in levels:
            r = L * t
            start = len(verts)
            for i in range(N):
                a = 2 * math.pi * i / N
                verts.append([apex[0] + s * n[0] * L + r * (math.cos(a) * u[0] + math.sin(a) * v[0]),
                              apex[1] + s * n[1] * L + r * (math.cos(a) * u[1] + math.sin(a) * v[1]),
                              apex[2] + s * n[2] * L + r * (math.cos(a) * u[2] + math.sin(a) * v[2])])
            idx = list(range(start, start + N))
            if prev is None:
                for i in range(N):
                    faces.append([0, idx[i], idx[(i + 1) % N]])
            else:
                for i in range(N):
                    j = (i + 1) % N
                    faces.append([prev[i], prev[j], idx[j], idx[i]])
            for i in range(N):
                edges.append([idx[i], idx[(i + 1) % N]])
            prev = idx
        step = max(1, N // 12)
        for i in range(0, N, step):
            edges.append([0, prev[i]])
    return _with_analytic(_poly_state(verts, faces, edges), type="infinite_cone")


def _cmd_cone(cons, defn, args):
    """Cone[圆, 高] / Cone[顶点, 底心, 半径] / Cone[顶点, 方向向量, 角] / Cone[三点]。

    三点（兼容原语义）：A 底面中心、B 底面半径点、C 顶点。
    """
    if len(args) == 2:
        first = _lookup(cons, args[0])
        if first is not None and (first.kind == "circle" or
                                  (first.kind == "conic" and getattr(first, "ctype", "") == "circle")):
            h_el, h_val = _number_arg(cons, args[1])
            deps = [first] + ([h_el] if h_el is not None else [])

            def fn_h(d):
                hv = d[1].value if h_el is not None else h_val
                return _cone_from_circle_state(d[0], hv)
            return _tag3d(_mk(cons, Geo3D, "geo3d", defn, deps, fn_h), "cone")
        raise GeoError("Cone[圆, 高] 需要 圆 与高度")
    if len(args) == 3:
        a_el = _lookup(cons, args[0])
        if a_el is not None and a_el.kind == "point":
            # 顶点 + 方向向量 + 半角
            vec = _vector3_arg(cons, args[1])
            if vec is not None:
                ang_el, ang_val = _number_arg(cons, args[2])
                deps = [a_el] + ([ang_el] if ang_el is not None else [])

                def fn_v(d):
                    av = d[1].value if ang_el is not None else ang_val
                    apex = [d[0].x, d[0].y, d[0].z or 0]
                    return _infinite_cone_state(apex, [vec[0], vec[1], vec[2]], av)
                return _tag3d(_mk(cons, Geo3D, "geo3d", defn, deps, fn_v), "cone")
            b_el = _lookup(cons, args[1])
            if b_el is not None and b_el.kind == "point":
                c_el = _lookup(cons, args[2])
                if c_el is None or c_el.kind in ("number", "angle"):
                    r_el, r_val = _number_arg(cons, args[2])
                    deps = [a_el, b_el] + ([r_el] if r_el is not None else [])

                    def fn_r(d):
                        rv = d[2].value if r_el is not None else r_val
                        apex = [d[0].x, d[0].y, d[0].z or 0]
                        base = [d[1].x, d[1].y, d[1].z or 0]
                        return _cone_apex_center_radius_state(apex, base, rv)
                    return _tag3d(_mk(cons, Geo3D, "geo3d", defn, deps, fn_r), "cone")
        # 经典三点：底心 A、半径点 B、顶点 C
        a, b, c = _poly3_points(cons, args, 3, "Cone")
        return _poly_register(cons, defn, [a, b, c], lambda d: _cone_state(d[0], d[1], d[2]), "cone")
    raise GeoError("Cone 支持 Cone[圆,高] / Cone[顶点,底心,半径] / Cone[顶点,方向向量,角] / Cone[三点]")


def _cone_state(a, b, c):
    """A 底面中心、B 底面半径点（半径 = |AB|）、C 顶点；底面垂直于轴 AC。"""
    r = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + ((b.z or 0) - (a.z or 0)) ** 2)
    h = math.sqrt((c.x - a.x) ** 2 + (c.y - a.y) ** 2 + ((c.z or 0) - (a.z or 0)) ** 2)
    return _with_analytic(_cone_mesh_axis([c.x, c.y, c.z or 0], [a.x, a.y, a.z or 0], r),
                          type="cone", r=r, h=h)


def _cyl_mesh_axis(base_center, axis, radius, N=48):
    """由 底面中心 / 轴向向量（长度=高）/ 半径 构造圆柱网格。"""
    if radius <= 1e-12:
        raise GeoError("半径需为正")
    h = [axis[0], axis[1], axis[2]]
    if math.sqrt(h[0] ** 2 + h[1] ** 2 + h[2] ** 2) < 1e-12:
        raise GeoError("圆柱高度退化")
    u, v, _n = _frame_from_axis(h)
    verts, edges, faces = [], [], []
    for i in range(N):
        ang = 2 * math.pi * i / N
        x0 = radius * math.cos(ang)
        y0 = radius * math.sin(ang)
        bx = base_center[0] + x0 * u[0] + y0 * v[0]
        by = base_center[1] + x0 * u[1] + y0 * v[1]
        bz = base_center[2] + x0 * u[2] + y0 * v[2]
        verts.append([bx, by, bz])
        verts.append([bx + h[0], by + h[1], bz + h[2]])
    for i in range(N):
        j = (i + 1) % N
        faces.append([2 * i, 2 * j, 2 * j + 1, 2 * i + 1])   # 侧面四边形
        edges.append([2 * i, 2 * j])
        edges.append([2 * i + 1, 2 * j + 1])
        edges.append([2 * i, 2 * i + 1])
    faces.append([2 * i for i in range(N)])                  # 底面
    faces.append([2 * i + 1 for i in range(N)])              # 顶面
    return _poly_state(verts, faces, edges)


def _cylinder_from_circle_state(cir, h):
    """Cylinder[圆, 高]：底面为该圆（z=0 平面），沿 +z 方向高 h。"""
    if getattr(cir, "error", None):
        raise GeoError("底面圆无效：" + str(cir.error))
    if cir.kind == "conic":
        cx, cy, r = cir.cx, cir.cy, cir.semi_a
    else:
        cx, cy, r = cir.cx, cir.cy, cir.r
    if h <= 1e-12:
        raise GeoError("高度需为正")
    return _with_analytic(_cyl_mesh_axis([cx, cy, 0.0], [0.0, 0.0, h], r), type="cylinder", r=r, h=h)


def _cylinder_centers_radius_state(base_center, top_center, radius):
    """Cylinder[底心, 顶心, 半径]。"""
    axis = [top_center[0] - base_center[0], top_center[1] - base_center[1], top_center[2] - base_center[2]]
    h = math.sqrt(sum(v * v for v in axis))
    return _with_analytic(_cyl_mesh_axis(base_center, axis, radius), type="cylinder", r=radius, h=h)


def _cmd_cylinder(cons, defn, args):
    """Cylinder[圆, 高] / Cylinder[底心, 顶心, 半径] / Cylinder[三点]。

    三点（兼容原语义）：A 底面中心、B 底面半径点、C 顶面中心。
    """
    if len(args) == 2:
        first = _lookup(cons, args[0])
        if first is not None and (first.kind == "circle" or
                                  (first.kind == "conic" and getattr(first, "ctype", "") == "circle")):
            h_el, h_val = _number_arg(cons, args[1])
            deps = [first] + ([h_el] if h_el is not None else [])

            def fn_h(d):
                hv = d[1].value if h_el is not None else h_val
                return _cylinder_from_circle_state(d[0], hv)
            return _tag3d(_mk(cons, Geo3D, "geo3d", defn, deps, fn_h), "cylinder")
        raise GeoError("Cylinder[圆, 高] 需要 圆 与高度")
    if len(args) == 3:
        a_el = _lookup(cons, args[0])
        b_el = _lookup(cons, args[1])
        c_el = _lookup(cons, args[2])
        if (a_el is not None and a_el.kind == "point" and
                b_el is not None and b_el.kind == "point" and
                (c_el is None or c_el.kind in ("number", "angle"))):
            r_el, r_val = _number_arg(cons, args[2])
            deps = [a_el, b_el] + ([r_el] if r_el is not None else [])

            def fn_r(d):
                rv = d[2].value if r_el is not None else r_val
                p1 = [d[0].x, d[0].y, d[0].z or 0]
                p2 = [d[1].x, d[1].y, d[1].z or 0]
                return _cylinder_centers_radius_state(p1, p2, rv)
            return _tag3d(_mk(cons, Geo3D, "geo3d", defn, deps, fn_r), "cylinder")
        a, b, c = _poly3_points(cons, args, 3, "Cylinder")
        return _poly_register(cons, defn, [a, b, c], lambda d: _cylinder_state(d[0], d[1], d[2]), "cylinder")
    raise GeoError("Cylinder 支持 Cylinder[圆,高] / Cylinder[底心,顶心,半径] / Cylinder[三点]")


def _cylinder_state(a, b, c):
    """A 底面中心、B 底面半径点（半径 = |AB|）、C 顶面中心；底面垂直于轴 AC。"""
    r = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + ((b.z or 0) - (a.z or 0)) ** 2)
    axis = [c.x - a.x, c.y - a.y, (c.z or 0) - (a.z or 0)]
    h = math.sqrt(sum(v * v for v in axis))
    return _with_analytic(_cyl_mesh_axis([a.x, a.y, a.z or 0], axis, r), type="cylinder", r=r, h=h)


def _cmd_prism(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Prism")
    return _poly_register(cons, defn, [a, b, c], lambda d: _prism_state(d[0], d[1], d[2]), "prism")


def _prism_state(a, b, c):
    u, v, n = _ortho_frame(a, b, c)
    L = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + ((b.z or 0) - (a.z or 0)) ** 2)
    hgt = L   # 高度 = 底边 AB 长度
    base = [[a.x, a.y, a.z or 0], [b.x, b.y, b.z or 0], [c.x, c.y, c.z or 0]]
    top = [[p[0] + hgt * n[0], p[1] + hgt * n[1], p[2] + hgt * n[2]] for p in base]
    verts = base + top
    faces = [[0, 1, 2], [3, 5, 4], [0, 1, 4, 3], [1, 2, 5, 4], [2, 0, 3, 5]]
    edges = [[0, 1], [1, 2], [2, 0], [3, 4], [4, 5], [5, 3], [0, 3], [1, 4], [2, 5]]
    return _poly_state(verts, faces, edges)


def _cmd_pyramid(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Pyramid")
    return _poly_register(cons, defn, [a, b, c], lambda d: _pyramid_state(d[0], d[1], d[2]), "pyramid")


def _pyramid_state(a, b, c):
    u, v, n = _ortho_frame(a, b, c)
    L = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + ((b.z or 0) - (a.z or 0)) ** 2)
    cx = (a.x + b.x + c.x) / 3
    cy = (a.y + b.y + c.y) / 3
    cz = ((a.z or 0) + (b.z or 0) + (c.z or 0)) / 3
    apex = [cx + L * n[0], cy + L * n[1], cz + L * n[2]]
    base = [[a.x, a.y, a.z or 0], [b.x, b.y, b.z or 0], [c.x, c.y, c.z or 0]]
    verts = base + [apex]
    faces = [[0, 1, 2], [0, 1, 3], [1, 2, 3], [2, 0, 3]]
    edges = [[0, 1], [1, 2], [2, 0], [0, 3], [1, 3], [2, 3]]
    return _poly_state(verts, faces, edges)


def _cmd_tetrahedron(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Tetrahedron")
    return _poly_register(cons, defn, [a, b, c], lambda d: _tetrahedron_state(d[0], d[1], d[2]), "tetrahedron")


def _tetrahedron_state(a, b, c):
    """正四面体：AB 为棱，C 决定朝向（C 所在侧）。"""
    u, v, n = _ortho_frame(a, b, c)
    L = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + ((b.z or 0) - (a.z or 0)) ** 2)
    ax, ay, az = a.x, a.y, a.z or 0
    # 等边底第三点 P = A + L/2·u + √3/2·L·v
    p = [ax + L / 2 * u[0] + L * math.sqrt(3) / 2 * v[0],
         ay + L / 2 * u[1] + L * math.sqrt(3) / 2 * v[1],
         az + L / 2 * u[2] + L * math.sqrt(3) / 2 * v[2]]
    # 顶点 D = A + L/2·u + L/(2√3)·v + L·√(2/3)·n
    d = [ax + L / 2 * u[0] + L / (2 * math.sqrt(3)) * v[0] + L * math.sqrt(2.0 / 3.0) * n[0],
         ay + L / 2 * u[1] + L / (2 * math.sqrt(3)) * v[1] + L * math.sqrt(2.0 / 3.0) * n[1],
         az + L / 2 * u[2] + L / (2 * math.sqrt(3)) * v[2] + L * math.sqrt(2.0 / 3.0) * n[2]]
    verts = [[ax, ay, az], [b.x, b.y, b.z or 0], p, d]
    faces = [[0, 1, 2], [0, 1, 3], [1, 2, 3], [2, 0, 3]]
    edges = [[0, 1], [1, 2], [2, 0], [0, 3], [1, 3], [2, 3]]
    return _poly_state(verts, faces, edges)


def _regular_polyhedron(center, radius, u, v, n, unit_verts, faces, edges):
    """按正交基把单位正多面体顶点缩放/旋转到以 center 为中心、radius 为外接半径。"""
    verts = []
    for p in unit_verts:
        verts.append([center[0] + radius * (p[0] * u[0] + p[1] * v[0] + p[2] * n[0]),
                      center[1] + radius * (p[0] * u[1] + p[1] * v[1] + p[2] * n[1]),
                      center[2] + radius * (p[0] * u[2] + p[1] * v[2] + p[2] * n[2])])
    return _poly_state(verts, faces, edges)


_PHI = (1 + math.sqrt(5)) / 2


def _cmd_octahedron(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Octahedron")
    return _poly_register(cons, defn, [a, b, c], lambda d: _octahedron_state(d[0], d[1], d[2]), "octahedron")


def _octahedron_state(a, b, c):
    u, v, n = _ortho_frame(a, b, c)
    r = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + ((b.z or 0) - (a.z or 0)) ** 2)
    unit = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]
    faces = [[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4], [0, 3, 5], [3, 1, 5], [1, 2, 5], [2, 0, 5]]
    edges = [[0, 2], [0, 4], [0, 3], [2, 1], [2, 4], [1, 4], [1, 3], [3, 4], [3, 5], [1, 5], [2, 5], [0, 5]]
    return _regular_polyhedron([a.x, a.y, a.z or 0], r, u, v, n, unit, faces, edges)


def _cmd_hexahedron(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Hexahedron")
    return _poly_register(cons, defn, [a, b, c], lambda d: _hexahedron_state(d[0], d[1], d[2]), "hexahedron")


def _hexahedron_state(a, b, c):
    """正六面体（立方体）：8 个标准顶点 (±1,±1,±1) 归一化，6 正方形面、12 边。"""
    u, v, n = _ortho_frame(a, b, c)
    r = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + ((b.z or 0) - (a.z or 0)) ** 2)
    unit = [[s1, s2, s3] for s1 in (-1, 1) for s2 in (-1, 1) for s3 in (-1, 1)]
    norm = math.sqrt(3)
    unit = [[p[0] / norm, p[1] / norm, p[2] / norm] for p in unit]
    # 顶点索引（s1 外层循环生成）：0=(-,-,-) 1=(-,-,+) 2=(-,+,-) 3=(-,+,+) 4=(+,-,-) 5=(+,-,+) 6=(+,+,-) 7=(+,+,+)
    faces = [[0, 2, 6, 4], [1, 3, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 1, 3, 2], [4, 5, 7, 6]]
    edges = [[0, 2], [2, 6], [6, 4], [4, 0], [1, 3], [3, 7], [7, 5], [5, 1],
             [0, 1], [2, 3], [4, 5], [6, 7]]
    return _regular_polyhedron([a.x, a.y, a.z or 0], r, u, v, n, unit, faces, edges)


def _cmd_icosahedron(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Icosahedron")
    return _poly_register(cons, defn, [a, b, c], lambda d: _icosahedron_state(d[0], d[1], d[2]), "icosahedron")


def _icosahedron_state(a, b, c):
    """正二十面体：标准 12 顶点（黄金比），面/边由最短邻接自动生成（保证全等边长）。"""
    u, v, n = _ortho_frame(a, b, c)
    r = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + ((b.z or 0) - (a.z or 0)) ** 2)
    ph = _PHI
    unit = [[0, 1, ph], [0, -1, ph], [0, 1, -ph], [0, -1, -ph],
            [1, ph, 0], [-1, ph, 0], [1, -ph, 0], [-1, -ph, 0],
            [ph, 0, 1], [-ph, 0, 1], [ph, 0, -1], [-ph, 0, -1]]
    norm = math.sqrt(1 + ph * ph)
    unit = [[p[0] / norm, p[1] / norm, p[2] / norm] for p in unit]
    # 自动邻接：最短顶点对距离 = 边长
    def _d3(i, j):
        return math.sqrt(sum((unit[i][k] - unit[j][k]) ** 2 for k in range(3)))
    dmin = min(_d3(i, j) for i in range(12) for j in range(i + 1, 12))
    adj = {i: [j for j in range(12) if j != i and _d3(i, j) < dmin * 1.05] for i in range(12)}
    # 面：每条边 (i,j) 的公共邻居 k → 三角形 (i,j,k)，去重
    faces_set = set()
    for i in range(12):
        for j in adj[i]:
            for k in adj[i]:
                if k in adj[j]:
                    faces_set.add(tuple(sorted((i, j, k))))
    faces = [list(fc) for fc in sorted(faces_set)]
    # 边：面边去重
    seen = set()
    edges = []
    for fc in faces:
        for i2 in range(len(fc)):
            e0, e1 = fc[i2], fc[(i2 + 1) % len(fc)]
            key = (min(e0, e1), max(e0, e1))
            if key not in seen:
                seen.add(key)
                edges.append([key[0], key[1]])
    return _regular_polyhedron([a.x, a.y, a.z or 0], r, u, v, n, unit, faces, edges)


def _cmd_dodecahedron(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Dodecahedron")
    return _poly_register(cons, defn, [a, b, c], lambda d: _dodecahedron_state(d[0], d[1], d[2]), "dodecahedron")


def _dodecahedron_state(a, b, c):
    """正十二面体：作为正二十面体的对偶（面心 → 顶点，顶点周围面环 → 五边形面）。"""
    u, v, n = _ortho_frame(a, b, c)
    r = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + ((b.z or 0) - (a.z or 0)) ** 2)
    # 正二十面体单位顶点与面（与 _icosahedron_state 一致）
    ph = _PHI
    unit = [[0, 1, ph], [0, -1, ph], [0, 1, -ph], [0, -1, -ph],
            [1, ph, 0], [-1, ph, 0], [1, -ph, 0], [-1, -ph, 0],
            [ph, 0, 1], [-ph, 0, 1], [ph, 0, -1], [-ph, 0, -1]]
    norm = math.sqrt(1 + ph * ph)
    unit = [[p[0] / norm, p[1] / norm, p[2] / norm] for p in unit]
    # 正二十面体面：最短邻接自动生成（与 _icosahedron_state 一致，保证正确）
    def _d3b(i, j):
        return math.sqrt(sum((unit[i][k] - unit[j][k]) ** 2 for k in range(3)))
    dmin = min(_d3b(i, j) for i in range(12) for j in range(i + 1, 12))
    adjb = {i: [j for j in range(12) if j != i and _d3b(i, j) < dmin * 1.05] for i in range(12)}
    faces_setb = set()
    for i in range(12):
        for j in adjb[i]:
            for k in adjb[i]:
                if k in adjb[j]:
                    faces_setb.add(tuple(sorted((i, j, k))))
    ifaces = [list(fc) for fc in sorted(faces_setb)]
    # 对偶：正十二面体顶点 = 二十面体每个面的质心（20 个）
    face_centers = []
    for fc in ifaces:
        c0 = [0.0, 0.0, 0.0]
        for idx in fc:
            c0[0] += unit[idx][0]; c0[1] += unit[idx][1]; c0[2] += unit[idx][2]
        c0 = [c0[0] / 3, c0[1] / 3, c0[2] / 3]
        ln = math.sqrt(c0[0] ** 2 + c0[1] ** 2 + c0[2] ** 2) or 1
        face_centers.append([c0[0] / ln, c0[1] / ln, c0[2] / ln])
    # 每个二十面体顶点周围的面环 → 一个五边形面（5 个面心）
    # 用扇环行走保证循环顺序一致：相邻面共享含 vi 的边
    vert_faces = {}
    for fi, fc in enumerate(ifaces):
        for vi in fc:
            vert_faces.setdefault(vi, []).append(fi)
    face_edge = {}
    for fi, fc in enumerate(ifaces):
        for i in range(len(fc)):
            e0, e1 = fc[i], fc[(i + 1) % len(fc)]
            face_edge.setdefault((min(e0, e1), max(e0, e1)), []).append(fi)
    dodeca_faces = []
    for vi in range(12):
        ring = vert_faces[vi]
        if len(ring) != 5:
            continue
        # 扇环行走：从 ring 任一面开始，每次找共享"含 vi 边"的下一面
        ordered = [ring[0]]
        visited = {ring[0]}
        while len(ordered) < 5:
            cur = ordered[-1]
            # 当前三角形含 vi 的两条边（边也含 vi）
            fc_cur = ifaces[cur]
            cand = None
            for i in range(3):
                e0, e1 = fc_cur[i], fc_cur[(i + 1) % 3]
                if vi not in (e0, e1):
                    continue
                for nf in face_edge.get((min(e0, e1), max(e0, e1)), []):
                    if nf != cur and nf in vert_faces[vi] and nf not in visited:
                        cand = nf
                        break
                if cand is not None:
                    break
            if cand is None:
                break
            ordered.append(cand)
            visited.add(cand)
        if len(ordered) == 5:
            dodeca_faces.append(ordered)
    # 边：由二十面体边直接构造（每条二十面体边 ↔ 一条十二面体边：两个共享该边的面心）
    face_of_edge = {}
    for fi, fc in enumerate(ifaces):
        for i in range(len(fc)):
            e0, e1 = fc[i], fc[(i + 1) % len(fc)]
            key = (min(e0, e1), max(e0, e1))
            face_of_edge.setdefault(key, []).append(fi)
    seen = set()
    edges = []
    for key, fpair in face_of_edge.items():
        if len(fpair) == 2:
            e0, e1 = min(fpair), max(fpair)
            if (e0, e1) not in seen:
                seen.add((e0, e1))
                edges.append([e0, e1])
    # 若面环不完整导致缺边，补充：同一面的相邻面心也连边（保证封闭）
    for fc in dodeca_faces:
        for i in range(len(fc)):
            e0, e1 = fc[i], fc[(i + 1) % len(fc)]
            key = (min(e0, e1), max(e0, e1))
            if key not in seen:
                seen.add(key)
                edges.append([e0, e1])
    return _regular_polyhedron([a.x, a.y, a.z or 0], r, u, v, n, face_centers, dodeca_faces, edges)


# ---------------------------------------------------------------------------
# P4：定理证明 / 序列 / 回归 / 脚本
# ---------------------------------------------------------------------------

def _prove_cmd(cons, defn, args, kind, n):
    """Are* 命令：构造布尔元素，一次性符号证明（避免拖拽重跑 sympy）。"""
    if len(args) != n:
        raise GeoError("该命题需要 " + str(n) + " 个参数")
    from .prover import SymbolicGeo
    el = GeoBoolean(label_of(defn), defn)
    el.free = False
    el._prove_args = (kind, list(args))
    sg = SymbolicGeo(cons)
    res = sg.prove(kind, args)
    el.value = res.value
    el.detail = res.detail
    return cons.add(el)


def _cmd_areparallel(cons, defn, args):
    return _prove_cmd(cons, defn, args, "parallel", 2)


def _cmd_areperpendicular(cons, defn, args):
    return _prove_cmd(cons, defn, args, "perpendicular", 2)


def _cmd_arecollinear(cons, defn, args):
    return _prove_cmd(cons, defn, args, "collinear", 3)


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


def _cmd_sequence(cons, defn, args):
    """Sequence[expr, var, a, b] → 数值列表（可带步长）。"""
    if len(args) not in (4, 5):
        raise GeoError("Sequence 需要 表达式、变量、起点、终点（可选步长）")
    expr_s, var_s, a_s, b_s = args[0], args[1], args[2], args[3]
    step = eval_number(cons, args[4]) if len(args) == 5 else 1.0
    a = eval_number(cons, a_s)
    b = eval_number(cons, b_s)
    if step == 0:
        raise GeoError("步长不能为 0")
    import sympy
    import numpy as np
    var = sympy.Symbol(var_s)
    e = _parse_sympy(expr_s, {var_s: var}, cons)
    lam = sympy.lambdify(var, e, "numpy")
    vals = []
    point_mode = False
    i = a
    while i <= b + 1e-9:
        try:
            v = np.asarray(lam(i), dtype=float)
        except Exception:
            raise GeoError("序列元素无法求值")
        if v.ndim == 1 and v.shape[0] == 2:
            point_mode = True
            vals.append((float(v[0]), float(v[1])))
        else:
            vals.append(float(v))
        i += step
    el = GeoList(label_of(defn), defn, vals, "point" if point_mode else "number")
    el.free = False
    return cons.add(el)


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
            p0 = [(ys.max() - ys.min()) / 2, 2 * np.pi / max(xs.max() - xs.min(), 1e-9), 0, ys.mean()]
            popt, _ = curve_fit(model, xs, ys, p0=p0, maxfev=20000)
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


def _cmd_setcoords(cons, defn, args):
    """SetCoords[A, x, y] / SetCoords[A, x, y, z]：程序化移动自由点（脚本）。"""
    if len(args) not in (3, 4):
        raise GeoError("SetCoords 需要 点、x、y（或 x、y、z）")
    pt = _resolve(cons, args[0], ("point",))
    if not pt.free:
        raise GeoError(pt.label + " 是派生对象，不能移动")
    x = eval_number(cons, args[1])
    y = eval_number(cons, args[2])
    pt.x, pt.y = x, y
    if len(args) == 4:
        z = eval_number(cons, args[3])
        pt.z = z
        pt.defn = pt.label + "=(" + _fmt(x) + "," + _fmt(y) + "," + _fmt(z) + ")"
    else:
        if pt.z is not None:
            pt.defn = pt.label + "=(" + _fmt(x) + "," + _fmt(y) + "," + _fmt(pt.z) + ")"
        else:
            pt.defn = pt.label + "=(" + _fmt(x) + "," + _fmt(y) + ")"
    cons._recompute(pt)
    return []


def _cmd_setvalue(cons, defn, args):
    """SetValue[n, v]：设置数值对象（脚本）。"""
    if len(args) != 2:
        raise GeoError("SetValue 需要 数值对象 和 值")
    num = _resolve(cons, args[0], ("number",))
    v = eval_number(cons, args[1])
    num.value = v
    num.defn = num.label + "=" + _fmt(v)
    cons._recompute(num)
    return []


# ---------------------------------------------------------------------------
# 变换辅助：函数变换 / 圆锥曲线变换 / Dilate 命令
# ---------------------------------------------------------------------------

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
    if norm < EPS:
        raise GeoError("退化的直线")
    p0x = -a0 * c0 / (norm * norm)
    p0y = -b0 * c0 / (norm * norm)
    dx, dy = -b0 / norm, a0 / norm
    p1 = _dilate_pt(p0x, p0y, k, cxp, cyp)
    p2 = _dilate_pt(p0x + dx, p0y + dy, k, cxp, cyp)
    return _line_state(*_line_through(p1[0], p1[1], p2[0], p2[1]))


def _inv_map(px, py, ox, oy, r):
    """点 (px,py) 关于反演圆 (O,r) 的像：OP·OP' = r²，像与原像同向。"""
    dx, dy = px - ox, py - oy
    d2 = dx * dx + dy * dy
    if d2 < 1e-18:
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
    if abs(den) < 1e-9:
        # 过反演圆心：像为直线 (q-O)·(C-O) = r²/2
        A = dx
        B = dy
        C = -(dx * ox + dy * oy) - r * r / 2.0
        return _inv_linear_state(A, B, C)
    k = r * r / den
    ncx = ox + dx * k
    ncy = oy + dy * k
    nr = abs(k) * rr
    if nr < 1e-12:
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
    if n < EPS:
        raise GeoError("退化直线")
    dist = (a * ox + b * oy + c) / n
    if abs(dist) < 1e-12:
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
        if n < EPS:
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
    if n2 < 1e-18:
        return math.hypot(ox - ax, oy - ay) < 1e-12
    t = ((ox - ax) * dx + (oy - ay) * dy) / n2
    if t < -1e-9 or t > 1 + 1e-9:
        return False
    px, py = ax + dx * t, ay + dy * t
    return math.hypot(ox - px, oy - py) < 1e-9 * max(1.0, math.hypot(dx, dy))


def _cmd_image(cons, defn, args):
    """Image[基点A, 基点B, 图片ID] — 以两点定位/缩放的图片（保持原始长宽比）。"""
    if len(args) != 3:
        raise GeoError("Image 需要 基点A、基点B 和图片ID")
    a = _point_arg(cons, args[0])
    b = _point_arg(cons, args[1])
    from . import image_store
    iid = args[2].strip().strip('"').strip("'")
    rec = image_store.get(iid)
    if rec is None:
        raise GeoError("图片不存在或已失效: " + iid)
    el = GeoImage(_label_of(defn), defn)
    el.free = False
    el.imgid = iid
    el.iw = int(rec.get("w", 0) or 0)
    el.ih = int(rec.get("h", 0) or 0)
    el.set_deps([a, b], lambda d: {"ax": d[0].x, "ay": d[0].y, "bx": d[1].x, "by": d[1].y})
    return cons.add(el)


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
        if n < EPS:
            raise GeoError("退化射线")
        ux, uy = el.dx / n, el.dy / n
        dx0, dy0 = el.ox - ox, el.oy - oy
        perp = abs(dx0 * uy - dy0 * ux)
        pole_t = -(dx0 * ux + dy0 * uy)
        if perp < 1e-9 * max(1.0, math.hypot(dx0, dy0)) and pole_t > -1e-9:
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
        if abs(dc - rr) < 1e-9:
            aO = math.atan2(oy - cy, ox - cx)
            dO = (aO - el.ang1) % (2 * math.pi)
            if dO <= sweep + 1e-9:
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


# ---------------------------------------------------------------------------
# 第二优先级：分布 / 直方图 / 文本 / 圆上点 / 轨迹
# ---------------------------------------------------------------------------

def _cmd_normal(cons, defn, args):
    """Normal[μ, σ, x] → 正态分布密度值。"""
    if len(args) != 3:
        raise GeoError("Normal 需要 均值、标准差、x 值")
    mu = eval_number(cons, args[0])
    sigma = eval_number(cons, args[1])
    if sigma <= 0:
        raise GeoError("标准差必须 > 0")
    x_el = _lookup(cons, args[2])
    if x_el is not None and x_el.kind in ("number", "angle"):
        deps = [x_el]
        fixed = None
    else:
        deps = []
        fixed = eval_number(cons, args[2])
    from scipy.stats import norm

    def fn(d):
        xv = fixed if fixed is not None else d[0].value
        return {"value": float(norm.pdf(xv, mu, sigma))}
    return _mk(cons, GeoNumber, "number", defn, deps, fn)


def _cmd_normaldist(cons, defn, args):
    """NormalDist[μ, σ] → 正态密度函数（可绘图/积分）。"""
    if len(args) != 2:
        raise GeoError("NormalDist 需要 均值、标准差")
    mu = eval_number(cons, args[0])
    sigma = eval_number(cons, args[1])
    if sigma <= 0:
        raise GeoError("标准差必须 > 0")
    import sympy
    el = GeoFunction(label_of(defn), defn)
    el.free = False
    x = sympy.Symbol("x")

    def fn(d):
        return {"expr": 1 / (sigma * sympy.sqrt(2 * sympy.pi)) * sympy.exp(-(x - mu) ** 2 / (2 * sigma ** 2)),
                "xsym": x, "body": "", "_lamb": None}
    el.set_deps([], fn)
    el.compute()
    return cons.add(el)



def _cmd_histogram(cons, defn, args):
    """Histogram[数据列表] / Histogram[数据列表, 组数] → 分组频数直方图。数据可为 {..} 内联、列表标签或多值。"""
    nbin = None
    if len(args) >= 2:
        nbin = int(eval_number(cons, args[1]))
    first = args[0].strip()
    if first.startswith("{") or first.startswith("[") or first in cons.elements:
        L = _list_arg(cons, args[0])
        if L.itemkind != "number":
            raise GeoError("Histogram 需要数值数据")
        items = list(L.items)
        deps = [L]
    else:
        items = [eval_number(cons, a) for a in args]
        deps = []
    if not items:
        raise GeoError("空数据")
    import numpy as np
    arr = np.array(items, dtype=float)
    lo, hi = float(arr.min()), float(arr.max())
    if hi - lo < 1e-12:
        raise GeoError("数据无变化（无法分组）")
    if nbin is None:
        nbin = max(2, min(15, int(np.ceil(np.log2(len(arr)) + 1))))  # Sturges
    if nbin < 1 or nbin > 100:
        raise GeoError("组数需在 1..100")
    edges = list(np.linspace(lo, hi, nbin + 1))
    counts, _ = np.histogram(arr, bins=edges)
    el = GeoBarChart(label_of(defn), defn)
    el.free = False

    def fn(d):
        items2 = list(d[0].items) if d else items
        arr2 = np.array(items2, dtype=float)
        c2, _ = np.histogram(arr2, bins=edges)
        return {"hist": True, "edges": edges, "counts": [int(v) for v in c2],
                "width": (hi - lo) / nbin, "bins": edges[:-1]}

    el.set_deps(deps, fn)
    el.compute()
    return cons.add(el)


def _num_list_items(cons, args):
    first = args[0].strip()
    if first.startswith("{") or first.startswith("[") or first in cons.elements:
        L = _list_arg(cons, args[0])
        if L.itemkind != "number":
            raise GeoError("需要数值列表")
        return list(L.items), [L]
    items = [eval_number(cons, a) for a in args]
    return items, []


def _cmd_q1(cons, defn, args):
    items, deps = _num_list_items(cons, args)
    if len(items) < 1:
        raise GeoError("空数据")
    import numpy as np
    v = float(np.percentile(np.array(items, dtype=float), 25))
    return _mk(cons, GeoNumber, "number", defn, deps,
               lambda d, its=items: {"value": float(np.percentile(np.array(list(d[0].items) if d else its, dtype=float), 25))})


def _cmd_q3(cons, defn, args):
    items, deps = _num_list_items(cons, args)
    if len(items) < 1:
        raise GeoError("空数据")
    import numpy as np
    return _mk(cons, GeoNumber, "number", defn, deps,
               lambda d, its=items: {"value": float(np.percentile(np.array(list(d[0].items) if d else its, dtype=float), 75))})


def _cmd_iqr(cons, defn, args):
    items, deps = _num_list_items(cons, args)
    if len(items) < 1:
        raise GeoError("空数据")
    import numpy as np
    return _mk(cons, GeoNumber, "number", defn, deps,
               lambda d, its=items: {"value": float(np.percentile(np.array(list(d[0].items) if d else its, dtype=float), 75)
                                               - np.percentile(np.array(list(d[0].items) if d else its, dtype=float), 25))})


def _cmd_boxplot(cons, defn, args):
    """BoxPlot[数据列表] → 箱线图（五数概括）。"""
    items, deps = _num_list_items(cons, args)
    if len(items) < 2:
        raise GeoError("箱线图至少需要 2 个数据")
    import numpy as np

    def calc(d):
        its = list(d[0].items) if d else items
        a = np.array(its, dtype=float)
        return [float(a.min()), float(np.percentile(a, 25)), float(np.median(a)),
                float(np.percentile(a, 75)), float(a.max())], len(a)

    el = GeoBoxPlot(label_of(defn), defn)
    el.free = False

    def fn(d):
        five, n = calc(d)
        el.five = five
        el.n = n
        return {}

    el.set_deps(deps, fn)
    el.compute()
    return cons.add(el)


def _cmd_barchart(cons, defn, args):
    """BarChart[列表] 或 BarChart[数据...] → 直方图（按值分类统计频数）。"""
    if len(args) >= 1 and args[0].strip().startswith("["):
        L = _list_arg(cons, args[0])
        if L.itemkind == "point":
            raise GeoError("BarChart 需要数值列表")
        items = list(L.items)
        deps = [L]
    else:
        # 直接数据：BarChart[1,2,2,3]
        items = [eval_number(cons, a) for a in args]
        deps = []
    if not items:
        raise GeoError("空数据")
    el = GeoBarChart(label_of(defn), defn)
    el.free = False
    el.set_deps(deps, lambda d: _barchart_state(d[0] if d else _anon_list(items)))
    return cons.add(el)


def _anon_list(items):
    """临时列表容器（直接数据模式，无构造对象）。"""
    class _L:
        pass
    L = _L()
    L.items = items
    L.itemkind = "number"
    return L


def _barchart_state(L):
    from collections import Counter
    items = L.items
    if not items:
        raise GeoError("空列表")
    vals = sorted(set(items))
    counts = [items.count(v) for v in vals]
    width = 0.8 * (vals[1] - vals[0]) if len(vals) > 1 else 1.0
    return {"bins": vals, "counts": counts, "width": width}


_REF_X = re.compile(r"^([xyXY])\((.+)\)$")
_REF_DOT = re.compile(r"^(.+)\.([xyXY])$")


def _txt_num(v: float) -> str:
    s = ("%.6f" % float(v)).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _dyn_text_segments(content: str):
    """文本模板 → [('lit', 文字) | ('ref', token)]：支持 "..." 字面与 + 拼接对象引用。"""
    segs = []
    i, n = 0, len(content)
    while i < n:
        if content[i] == '"':
            j = i + 1
            buf = []
            while j < n and content[j] != '"':
                if content[j] == "\\" and j + 1 < n:
                    buf.append(content[j + 1])
                    j += 2
                else:
                    buf.append(content[j])
                    j += 1
            segs.append(("lit", "".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and content[j] != '"':
                j += 1
            for part in re.split(r"\+", content[i:j]):
                p = part.strip()
                if p:
                    segs.append(("ref", p))
            i = j
    return segs


def _ref_text(m, tok: str) -> str:
    """按引用 token 生成当前文本：对象标签 / x(A) / A.x。m: label → 元素。"""
    md = _REF_DOT.match(tok)
    if md:
        o = m.get(md.group(1).strip())
        if o is not None and o.kind == "point":
            return _txt_num(o.x if md.group(2) in ("x", "X") else o.y)
        raise GeoError("文本引用需要点对象: " + tok)
    mx = _REF_X.match(tok)
    if mx:
        o = m.get(mx.group(2).strip())
        if o is not None and o.kind == "point":
            return _txt_num(o.x if mx.group(1) in ("x", "X") else o.y)
        raise GeoError("x(A)/y(A) 需要点: " + tok)
    o = m.get(tok)
    if o is None:
        raise GeoError("文本引用了不存在的对象: " + tok)
    if o.kind == "number":
        return _txt_num(o.value)
    if o.kind == "angle":
        return _txt_num(o.value) + "°"
    if o.kind == "point":
        return "(" + _txt_num(o.x) + ", " + _txt_num(o.y) + ")"
    raise GeoError("文本仅支持引用 数值/角度/点: " + tok)


def _dyn_text_compute(deps, segs, anchor_pt, anchor_xy):
    m = {d.label: d for d in deps}
    buf = []
    for kind, v in segs:
        buf.append(v if kind == "lit" else _ref_text(m, v))
    content = "".join(buf)
    st = {"content": content}
    if anchor_pt is not None:
        ap = m.get(anchor_pt.label, anchor_pt)
        st["x"], st["y"] = ap.x, ap.y
        st["anchor_is_point"] = True
    else:
        st["x"], st["y"] = anchor_xy
        st["anchor_is_point"] = False
    return st


def _cmd_text(cons, defn, args):
    """Text[模板, 点或坐标] → 文本标注。
    模板支持动态引用："AB = " + d / x(A) / A.x / A（+ 拼接对象），拖动时实时更新。"""
    if len(args) != 2:
        raise GeoError('Text 需要 文字 和 位置（点或 (x,y)）')
    content_s = args[0].strip()
    segs = _dyn_text_segments(content_s)
    ref_objs = []
    seen = set()
    for kind, v in segs:
        if kind == "lit":
            continue
        name = v
        mdot = _REF_DOT.match(v)
        mx = _REF_X.match(v)
        if mdot:
            name = mdot.group(1).strip()
        elif mx:
            name = mx.group(2).strip()
        o = cons.elements.get(name)
        if o is None:
            raise GeoError("文本引用了不存在的对象: " + v)
        if o.kind not in ("number", "angle", "point"):
            raise GeoError("文本仅支持引用 数值/角度/点: " + v)
        if o.label not in seen:
            seen.add(o.label)
            ref_objs.append(o)
    pos = args[1].strip()
    el = GeoText(label_of(defn), defn)
    el.free = False
    el.content = ""
    deps = list(ref_objs)
    anchor_pt = None
    anchor_xy = (0.0, 0.0)
    pt = cons.elements.get(pos)
    if pt is not None and pt.kind == "point":
        anchor_pt = pt
        if pt.label not in seen:
            seen.add(pt.label)
            deps.append(pt)
    elif pos.startswith("("):
        parts = _tuple_parts(pos)
        anchor_xy = (eval_number(cons, parts[0]), eval_number(cons, parts[1]))
    else:
        raise GeoError("Text 位置需要 点 或 (x,y)")
    el.set_deps(deps, lambda d: _dyn_text_compute(d, segs, anchor_pt, anchor_xy))
    el.compute()
    return cons.add(el)


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
        if denom < 1e-12:
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
        if span < 1e-9:
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
        if total < 1e-12:
            raise GeoError("多边形退化")
        d = tv * total
        acc = 0.0
        for (x1, y1, x2, y2, ln) in segs:
            if ln < 1e-12:
                continue
            if d <= acc + ln:
                tt = (d - acc) / ln
                return {"x": x1 + tt * (x2 - x1), "y": y1 + tt * (y2 - y1)}
            acc += ln
        return {"x": segs[-1][2], "y": segs[-1][3]}
    raise GeoError("该对象暂不支持动点")


def _poc_state(c, th):
    return {"x": c.cx + c.r * math.cos(th.value), "y": c.cy + c.r * math.sin(th.value)}


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
    if r < 1e-12:
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
    ra = math.hypot(a.x - c.x, a.y - c.y)
    rb = math.hypot(b.x - c.x, b.y - c.y)
    r = (ra + rb) / 2.0
    if r < 1e-12:
        raise GeoError("退化圆弧")
    ang1 = math.atan2(a.y - c.y, a.x - c.x)
    ang2 = math.atan2(b.y - c.y, b.x - c.x)
    return {"sector": sector, "cx": c.x, "cy": c.y, "r": r, "ang1": ang1, "ang2": ang2}


def _cmd_solveineq(cons, defn, args):
    """SolveIneq[expr, 变量] → 解集（文本）。支持 x^2<4、x>2 等。"""
    if len(args) not in (1, 2):
        raise GeoError("SolveIneq 需要 不等式（可选变量）")
    import sympy
    from sympy.core.relational import Relational
    expr_s = args[0]
    var_s = args[1] if len(args) == 2 else "x"
    var = sympy.Symbol(var_s)
    expr = _parse_sympy(expr_s, {var_s: var}, cons)
    if not isinstance(expr, Relational):
        raise GeoError("SolveIneq 需要一个不等式，如 x^2<4")
    try:
        sol = sympy.reduce_inequalities(expr, var)
    except Exception as e:
        raise GeoError("无法求解该不等式: " + repr(e))
    el = GeoResult(label_of(defn), defn)
    el.free = False
    el.text = _fmt_sol(sol, var)
    return cons.add(el)


def _fmt_sol(sol, x) -> str:
    """解集 → 区间表示：(-2 < x) & (x < 2) → (-2, 2)；x > 2 → (2, +∞)。"""
    import sympy
    from sympy.core.relational import Relational
    if isinstance(sol, sympy.Or):
        parts = [_fmt_sol(a, x) for a in sol.args]
        parts.sort(key=_sol_lo)
        return " ∪ ".join(parts)
    if isinstance(sol, sympy.And):
        ineqs = list(sol.args)
    elif isinstance(sol, Relational):
        ineqs = [sol]
    else:
        return str(sol).replace("**", "^")
    lo, hi = -sympy.oo, sympy.oo
    lo_open = hi_open = True
    for r in ineqs:
        if not isinstance(r, Relational):
            continue
        op = r.rel_op
        if r.lhs == x:
            val = r.rhs
            if op in ("<", "<="):
                hi = sympy.Min(hi, val)
                hi_open = (op == "<")
            else:
                lo = sympy.Max(lo, val)
                lo_open = (op == ">")
        elif r.rhs == x:
            val = r.lhs
            if op in ("<", "<="):
                lo = sympy.Max(lo, val)
                lo_open = (op == "<")
            else:
                hi = sympy.Min(hi, val)
                hi_open = (op == ">")
    lo_v = "-∞" if lo == -sympy.oo else _fmt_sol_num(lo)
    hi_v = "+∞" if hi == sympy.oo else _fmt_sol_num(hi)
    return ("(" if lo_open else "[") + lo_v + ", " + hi_v + (")" if hi_open else "]")


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


def _fmt_sol_num(v) -> str:
    try:
        f = float(sympy.N(v))
        s = ("%.4g" % f)
        return s
    except Exception:
        return str(v).replace("**", "^")


def _cmd_setlocked(cons, defn, args):
    """SetLocked[对象, true/false]：锁定/解锁对象。"""
    if len(args) != 2:
        raise GeoError("SetLocked 需要 对象 和 true/false")
    el = _resolve(cons, args[0])
    v = args[1].strip().lower()
    if v in ("true", "1", "yes", "锁定"):
        el.locked = True
    elif v in ("false", "0", "no", "解锁"):
        el.locked = False
    else:
        raise GeoError("SetLocked 需要 true 或 false")
    return []


# ---------------------------------------------------------------------------
# 编辑命令：Delete / Rename / Redefine / SetColor / SetVisible
# ---------------------------------------------------------------------------

_COLOR_NAMES = {
    "red": "#e11d48", "blue": "#2563eb", "green": "#059669", "purple": "#7c3aed",
    "orange": "#ea580c", "teal": "#0d9488", "yellow": "#ca8a04", "gray": "#6b7280",
    "black": "#1a1a1a", "pink": "#db2777", "brown": "#92400e",
}


def _parse_color(s: str) -> str:
    s = s.strip().lower()
    if s in _COLOR_NAMES:
        return _COLOR_NAMES[s]
    if re.match(r"^#[0-9a-f]{6}$", s):
        return s
    raise GeoError("未知颜色: " + s + "（可用 red/blue/green/purple/orange/teal/yellow/gray/black 或 #rrggbb）")


def _cmd_delete(cons, defn, args):
    if not args:
        raise GeoError("Delete 需要至少一个对象")
    for a in args:
        el = _resolve(cons, a)
        cons.delete(el.label)
    return []


def _cmd_rename(cons, defn, args):
    if len(args) != 2:
        raise GeoError("Rename 需要 对象 和 新标签")
    old = _resolve(cons, args[0]).label
    new = args[1].strip()
    cons.rename(old, new)
    return []


def _cmd_redefine(cons, defn, args):
    if len(args) != 2:
        raise GeoError("Redefine 需要 对象 和 新定义（如 A=(3,4)）")
    label = _resolve(cons, args[0]).label
    newdefn = args[1].strip()
    cons.redefine(label, newdefn)
    return []


def _cmd_setcolor(cons, defn, args):
    if len(args) != 2:
        raise GeoError("SetColor 需要 对象 和 颜色")
    el = _resolve(cons, args[0])
    el.color = _parse_color(args[1])
    return []


def _cmd_setvisible(cons, defn, args):
    if len(args) != 2:
        raise GeoError("SetVisible 需要 对象 和 true/false")
    el = _resolve(cons, args[0])
    v = args[1].strip().lower()
    if v in ("true", "1", "yes", "显示"):
        el.visible = True
    elif v in ("false", "0", "no", "隐藏"):
        el.visible = False
    else:
        raise GeoError("SetVisible 需要 true 或 false")
    return []


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


def _cmd_macrodelete(cons, defn, args):
    if len(args) != 1:
        raise GeoError("MacroDelete 需要 宏名")
    from . import macro
    if macro.delete_macro(args[0].strip()):
        return []
    raise GeoError("宏不存在: " + args[0])


def _cmd_macrolist(cons, defn, args):
    from . import macro
    ms = macro.list_macros()
    if not ms:
        raise GeoError("暂无宏")
    return []


# ---------------------------------------------------------------------------
# 中文命令别名（GGB 中文版风格）
# ---------------------------------------------------------------------------

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

def _result_kind(name: str) -> str:
    table = {
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
    return table.get(name, "point")


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
    "mesh": _cmd_mesh,
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
        if name in macro.MACROS:
            created = macro.run_macro(cons, name, args, label)
            if created is None:
                raise GeoError("宏执行失败: " + name)
            return created
        raise GeoError("未知命令: " + name + "（支持: " + ", ".join(sorted(COMMANDS)) + "）")
    if label is None:
        # 自动标签：需要知道结果类型 → 预注册占位
        kind_hint = _result_kind(lname)
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