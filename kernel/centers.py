"""三角形四心命令（外心/垂心/旁心，P2 结构拆分）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .cmd_util import _mk, _point_arg, _resolve
from .primitives import _circumcircle, _dist
from .elements import GeoError, GeoPoint
from .tolerance import EPSILON


__all__ = [
    "_tri_points",
    "_cmd_orthocenter",
    "_orthocenter_state",
    "_cmd_circumcenter",
    "_circumcenter_state",
    "_cmd_excenter",
    "_excenter_state",
]


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
