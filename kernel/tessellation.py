"""二维剖分命令：Delaunay 三角剖分 / Voronoi 泰森多边形。

- ``Delaunay[点列表]``：scipy Qhull（与 ``ConvexHull`` 相同的依赖策略：缺 scipy 时给明确错误）
- ``Voronoi[点列表]``：**不依赖 scipy** —— 每个元胞 = 包围盒（点集范围外扩 15%）∩ 与所有其它点的
  垂直平分半平面，用 Sutherland–Hodgman 逐步裁剪。因此每个元胞都是**有界凸多边形**
  （刻意规避「无界元胞」这一经典麻烦），便于渲染、拖动与面积计算。

两者都返回 ``itemkind="polygon"`` 的列表元素：``items`` 为若干多边形顶点数组 ``[[x, y], ...]``（逆时针）。
依赖声明在 ``_mk`` 中，因此拖动点/调用 ``SetCoords`` 会让剖分自动重算。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .cmd_util import _list_arg, _lookup, _mk
from .elements import GeoError, GeoList
from .tolerance import COORD

Box = Tuple[float, float, float, float]
Poly = List[Tuple[float, float]]


def _point_pairs(items) -> List[Tuple[float, float]]:
    """点列表元素 → [(x, y)]（缺坐标或非有限值 → 明确报错）。"""
    import math
    pts: List[Tuple[float, float]] = []
    for p in items:
        if not p or len(p) < 2:
            raise GeoError("点列表里有点缺少坐标")
        x, y = float(p[0]), float(p[1])
        if not (math.isfinite(x) and math.isfinite(y)):
            raise GeoError("点列表里有非有限坐标")
        pts.append((x, y))
    return pts


def _bounding_box(pts: List[Tuple[float, float]], pad_ratio: float = 0.15) -> Box:
    """点集包围盒，外扩 max(宽, 高) 的 15%（至少 1 个单位）→ 元胞有界。"""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    pad = span * pad_ratio
    return (min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad)


def _signed_area(poly: Poly) -> float:
    s = 0.0
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        s += poly[i][0] * poly[j][1] - poly[j][0] * poly[i][1]
    return s / 2.0


def _clip_half(poly: Poly, mx: float, my: float, dx: float, dy: float) -> Poly:
    """Sutherland–Hodgman：保留满足 ``(p - m)·d <= 0`` 的一侧（即离 i 更近的一侧）。

    m = i、j 的中点，d = j - i；由 |p-i|² ≤ |p-j|² 展开即得该半平面。
    """
    out: Poly = []
    n = len(poly)
    for k in range(n):
        ax, ay = poly[k]
        bx, by = poly[(k + 1) % n]
        fa = (ax - mx) * dx + (ay - my) * dy
        fb = (bx - mx) * dx + (by - my) * dy
        if fa <= COORD:
            out.append((ax, ay))
        if (fa > COORD) != (fb > COORD):
            t = fa / (fa - fb)
            out.append((ax + t * (bx - ax), ay + t * (by - ay)))
    return out


def _dedupe(poly: Poly) -> Poly:
    """去掉连续重复（含首尾）顶点：半平面裁剪会在顶点处留下重合点。"""
    out: Poly = []
    for x, y in poly:
        if out and abs(out[-1][0] - x) <= COORD and abs(out[-1][1] - y) <= COORD:
            continue
        out.append((x, y))
    while len(out) >= 2 and abs(out[0][0] - out[-1][0]) <= COORD and abs(out[0][1] - out[-1][1]) <= COORD:
        out.pop()
    return out


def _polygon_state(polys: List[Poly]) -> Dict[str, Any]:
    cleaned = [_dedupe(p) for p in polys]
    cleaned = [p for p in cleaned if len(p) >= 3]
    if not cleaned:
        raise GeoError("剖分结果为空（点集退化？）")
    return {"items": [[[x, y] for x, y in poly] for poly in cleaned], "itemkind": "polygon"}


# ---------------------------------------------------------------------------
# Delaunay（scipy Qhull）
# ---------------------------------------------------------------------------

def _cmd_delaunay(cons, defn, args):
    """``Delaunay[点列表]`` / ``Delaunay[多边形]`` / ``Delaunay[A, B, C, ...]`` → 三角剖分。

    后两种入参是**动态**的：多边形或点元素变化时自动重算。
    """
    if not args:
        raise GeoError("Delaunay 需要点列表、多边形或若干点，如 Delaunay[{(0,0),(1,0),(0,1),(1,1)}]")
    mode, deps = _source(cons, args, "Delaunay", 3)
    return _mk(cons, GeoList, "list", defn, deps,
               lambda d: _delaunay_state(_coords(mode, d)))


def _delaunay_state(items) -> Dict[str, Any]:
    pts = _point_pairs(items)
    if len(pts) < 3:
        raise GeoError("Delaunay 至少需要 3 个点")
    try:
        import numpy as np
        from scipy.spatial import Delaunay, QhullError
    except ImportError as ex:  # 可选依赖缺失：功能降级并说明原因
        raise GeoError("缺少 scipy，无法做三角剖分：" + str(ex)[:40])
    try:
        tri = Delaunay(np.array(pts))
    except QhullError as ex:  # 点集退化（共线/重合）
        raise GeoError("点集退化（共线或重合），无法三角剖分：" + str(ex)[:60])
    polys: List[Poly] = []
    for s in tri.simplices:
        poly = [pts[int(i)] for i in s]
        if _signed_area(poly) < 0:      # 统一逆时针，便于渲染与面积符号一致
            poly.reverse()
        polys.append(poly)
    polys.sort(key=lambda p: (round(p[0][0], 9), round(p[0][1], 9)))   # 稳定顺序（快照/撤销可复现）
    return _polygon_state(polys)


# ---------------------------------------------------------------------------
# Voronoi（半平面裁剪，无 scipy 依赖）
# ---------------------------------------------------------------------------

def _cmd_voronoi(cons, defn, args):
    """``Voronoi[点列表]`` / ``Voronoi[多边形]`` / ``Voronoi[A, B, C, ...]`` → 泰森多边形（元胞均有界）。"""
    if not args:
        raise GeoError("Voronoi 需要点列表、多边形或若干点，如 Voronoi[{(0,0),(2,0),(1,2)}]")
    mode, deps = _source(cons, args, "Voronoi", 2)
    return _mk(cons, GeoList, "list", defn, deps,
               lambda d: _voronoi_state(_coords(mode, d)))


def _voronoi_state(items) -> Dict[str, Any]:
    pts = _point_pairs(items)
    if len(pts) < 2:
        raise GeoError("Voronoi 至少需要 2 个点")
    # 重合点无法定义元胞 → 明确报错（比给出错误图形好）
    seen = set()
    for x, y in pts:
        key = (round(x, 9), round(y, 9))
        if key in seen:
            raise GeoError("Voronoi 需要互不重合的点（发现重复点）")
        seen.add(key)
    x0, x1, y0, y1 = _bounding_box(pts)
    box: Poly = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]     # 逆时针
    polys: List[Poly] = []
    for i, (px, py) in enumerate(pts):
        poly = list(box)
        for j, (qx, qy) in enumerate(pts):
            if i == j:
                continue
            poly = _clip_half(poly, (px + qx) / 2.0, (py + qy) / 2.0, qx - px, qy - py)
            if len(poly) < 3:
                break
        if len(poly) >= 3:
            polys.append(poly)
    if len(polys) != len(pts):
        raise GeoError("Voronoi 元胞退化（点可能重合或共线过密）")
    return _polygon_state(polys)


# ---------------------------------------------------------------------------
# 参数形态（决定“动态性”）
# ---------------------------------------------------------------------------
# - 内联点列表  Delaunay[{(0,0),(1,0),(0,1)}]   → 值快照（列表依赖）
# - 多边形      Delaunay[Poly1]                 → 取顶点，随多边形变化重算（**动态**）
# - 变参点元素  Delaunay[A, B, C]               → 随点拖动重算（**动态**）
MODE_LIST = "list"
MODE_POLY = "polygon"
MODE_PTS = "points"


def _source(cons, args, cmd: str, least: int):
    """参数 → ``(模式, 依赖元素)``；坐标在 state 里按依赖的**当前值**取，保证拖动后重算。"""
    from .cmd_util import _resolve
    if len(args) == 1:
        lab = args[0].strip()
        el = _lookup(cons, lab)
        if el is not None and el.kind == "polygon":
            return MODE_POLY, [el]
        L = _list_arg(cons, lab)
        if L.itemkind != "point":
            raise GeoError("%s 需要二维点列表或多边形" % cmd)
        if len(L.items) < least:
            raise GeoError("%s 至少需要 %d 个点" % (cmd, least))
        return MODE_LIST, [L]
    if len(args) < least:
        raise GeoError("%s 至少需要 %d 个点（或一个点列表/多边形）" % (cmd, least))
    deps = [_resolve(cons, a, ("point",)) for a in args]
    return MODE_PTS, deps


def _coords(mode: str, deps) -> List[Tuple[float, float]]:
    """按模式从依赖的当前值取坐标（state 内调用 → 拖动/SetCoords 后自动刷新）。"""
    if mode == MODE_PTS:
        return [(float(e.x), float(e.y)) for e in deps]
    if mode == MODE_POLY:
        el = deps[0]
        return [(float(x), float(y)) for x, y in zip(el.xs, el.ys)]
    return [(float(p[0]), float(p[1])) for p in deps[0].items]
