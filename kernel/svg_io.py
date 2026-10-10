"""SVG 导出（P4）：把 2D 构造渲染为矢量图（课件/试卷素材）。

坐标系统：世界坐标 → SVG viewBox（y 轴翻转）。
"""

from __future__ import annotations

import math
import re
from typing import List, Tuple

from .elements import _fmt as _f
from .tolerance import COARSE  # 统一数值容差（见 kernel/tolerance.py）


def export_svg(cons, view: Tuple[float, float, float, float], width: int = 1000,
               height: int = 620) -> str:
    xmin, xmax, ymin, ymax = view
    w, h = width, height
    s = min(w / (xmax - xmin), h / (ymax - ymin))
    ox = -xmin * s
    oy = ymax * s

    def X(x): return round(x * s + ox, 2)

    def Y(y): return round(oy - y * s, 2)

    out: List[str] = []
    out.append('<?xml version="1.0" encoding="utf-8"?>')
    out.append('<svg xmlns="http://www.w3.org/2000/svg" width="' + str(w) + '" height="' + str(h)
               + '" viewBox="0 0 ' + str(w) + ' ' + str(h) + '">')
    out.append('  <rect width="100%" height="100%" fill="#ffffff"/>')

    # 网格与坐标轴
    step = 1.0
    raw = 60 / s
    pow10 = 10 ** math.floor(math.log10(raw))
    m = raw / pow10
    step = (1 if m < 1.5 else 2 if m < 3.5 else 5 if m < 7.5 else 10) * pow10
    out.append('  <g stroke="#f3f4f6" stroke-width="1">')
    x = math.ceil(xmin / step) * step
    while x <= xmax:
        out.append('    <line x1="' + str(X(x)) + '" y1="0" x2="' + str(X(x)) + '" y2="' + str(h) + '"/>')
        x += step
    y = math.ceil(ymin / step) * step
    while y <= ymax:
        out.append('    <line x1="0" y1="' + str(Y(y)) + '" x2="' + str(w) + '" y2="' + str(Y(y)) + '"/>')
        y += step
    out.append('  </g>')
    out.append('  <g stroke="#9ca3af" stroke-width="1.5">')
    out.append('    <line x1="0" y1="' + str(Y(0)) + '" x2="' + str(w) + '" y2="' + str(Y(0)) + '"/>')
    out.append('    <line x1="' + str(X(0)) + '" y1="0" x2="' + str(X(0)) + '" y2="' + str(h) + '"/>')
    out.append('  </g>')

    colors = {"line": "#2563eb", "segment": "#059669", "ray": "#0d9488", "circle": "#7c3aed",
              "polygon": "#3b82f6", "function": "#0f766e", "conic": "#7c3aed",
              "point": "#dc2626", "inequality": "#3b82f6"}

    def color(el):
        if el.color and el.color != "#1a1a1a":
            return el.color
        return colors.get(el.kind, "#374151")

    def path_pts(pts: List[List[float]], close: bool = False) -> str:
        d = "M " + str(X(pts[0][0])) + " " + str(Y(pts[0][1]))
        for p in pts[1:]:
            d += " L " + str(X(p[0])) + " " + str(Y(p[1]))
        if close:
            d += " Z"
        return d

    # 对象
    for lab in cons.order:
        el = cons.elements[lab]
        if not el.visible or el.kind in ("geo3d", "boolean", "number", "list", "barchart", "piechart"):
            continue
        if el.kind == "point":
            if getattr(el, "z", None) is not None:
                continue
            out.append('    <circle cx="' + str(X(el.x)) + '" cy="' + str(Y(el.y)) + '" r="4" fill="'
                       + color(el) + '"/>')
            out.append('    <text x="' + str(X(el.x) + 6) + '" y="' + str(Y(el.y) - 5)
                       + '" font-size="13" fill="#111827">' + _esc(el.label) + '</text>')
        elif el.kind == "segment":
            out.append('    <line x1="' + str(X(el.x1)) + '" y1="' + str(Y(el.y1)) + '" x2="'
                       + str(X(el.x2)) + '" y2="' + str(Y(el.y2)) + '" stroke="' + color(el)
                       + '" stroke-width="2"/>')
        elif el.kind == "line":
            clip = el.draw(view)
            seg = (clip or {}).get("seg")
            if seg:
                out.append('    <line x1="' + str(X(seg[0])) + '" y1="' + str(Y(seg[1])) + '" x2="'
                           + str(X(seg[2])) + '" y2="' + str(Y(seg[3])) + '" stroke="' + color(el)
                           + '" stroke-width="2"/>')
        elif el.kind == "ray":
            clip = el.draw(view)
            seg = (clip or {}).get("seg")
            if seg:
                out.append('    <line x1="' + str(X(seg[0])) + '" y1="' + str(Y(seg[1])) + '" x2="'
                           + str(X(seg[2])) + '" y2="' + str(Y(seg[3])) + '" stroke="' + color(el)
                           + '" stroke-width="2" marker-end="url(#arrow)"/>')
        elif el.kind == "circle":
            out.append('    <circle cx="' + str(X(el.cx)) + '" cy="' + str(Y(el.cy)) + '" r="'
                       + str(el.r * s) + '" fill="none" stroke="' + color(el) + '" stroke-width="2"/>')
        elif el.kind == "polygon":
            pts = [[x, y] for x, y in zip(el.xs, el.ys)]
            if len(pts) >= 3:
                # 填充跟随元素颜色（低透明度）；旧实现固定淡蓝，SetColor 只改描边 ✗
                _c = color(el)
                _fill = (_c + "1f") if re.fullmatch(r"#[0-9a-fA-F]{6}", _c or "") else "rgba(59,130,246,.12)"
                out.append('    <polygon points="' + " ".join(str(X(p[0])) + "," + str(Y(p[1])) for p in pts)
                           + '" fill="' + _fill + '" stroke="' + _c + '" stroke-width="2"/>')
        elif el.kind == "function":
            samples = el.sample(xmin, xmax, 300)
            segs_pts = _split_nan(samples)
            for sp in segs_pts:
                if len(sp) >= 2:
                    out.append('    <path d="' + path_pts(sp) + '" fill="none" stroke="' + color(el)
                               + '" stroke-width="2.2"/>')
        elif el.kind == "conic":
            d = el.draw(view)
            ctype = d.get("ctype", "general")
            if ctype in ("ellipse", "circle"):
                a, b, ang = el.semi_a, el.semi_b or el.semi_a, el.angle or 0
                ca, sa = math.cos(ang), math.sin(ang)
                pts = []
                for i in range(129):
                    t = i * math.pi * 2 / 128
                    pts.append([el.cx + a * math.cos(t) * ca - b * math.sin(t) * sa,
                                el.cy + a * math.cos(t) * sa + b * math.sin(t) * ca])
                out.append('    <path d="' + path_pts(pts, True) + '" fill="none" stroke="' + color(el)
                           + '" stroke-width="2"/>')
            elif ctype == "hyperbola":
                a, b, ang = el.semi_a, el.semi_b, el.angle or 0
                ca, sa = math.cos(ang), math.sin(ang)
                for sgn in (1, -1):
                    pts = []
                    for i in range(-50, 51):
                        t = i * 0.09
                        pts.append([el.cx + sgn * a * math.cosh(t) * ca - b * math.sinh(t) * sa,
                                    el.cy + sgn * a * math.cosh(t) * sa + b * math.sinh(t) * ca])
                    out.append('    <path d="' + path_pts(pts) + '" fill="none" stroke="' + color(el)
                               + '" stroke-width="2"/>')
            elif ctype == "parabola":
                p, ang = el.semi_a or 1, el.angle or 0
                ux, uy = math.cos(ang), math.sin(ang)
                vx, vy = -uy, ux
                span = max(abs(xmax - xmin), abs(ymax - ymin))
                tm = math.sqrt(span * p * 4) * 1.6
                pts = []
                for i in range(-120, 121):
                    t = i * tm / 120
                    pts.append([el.cx + t * vx + t * t / (4 * p) * ux,
                                el.cy + t * vy + t * t / (4 * p) * uy])
                out.append('    <path d="' + path_pts(pts) + '" fill="none" stroke="' + color(el)
                           + '" stroke-width="2"/>')
            else:
                for seg in d.get("segs", []):
                    out.append('    <line x1="' + str(X(seg[0])) + '" y1="' + str(Y(seg[1])) + '" x2="'
                               + str(X(seg[2])) + '" y2="' + str(Y(seg[3])) + '" stroke="' + color(el)
                               + '" stroke-width="2"/>')
        elif el.kind == "inequality":
            d = el.draw(view)
            if d.get("form") == "y" and d.get("boundary"):
                bd = d["boundary"]
                runs = _split_nan(bd)
                for run in runs:
                    if len(run) < 2:
                        continue
                    pts = list(run)
                    if d.get("yside", 1) > 0:
                        pts.append([run[-1][0], ymax])
                        pts.append([run[0][0], ymax])
                    else:
                        pts.append([run[-1][0], ymin])
                        pts.append([run[0][0], ymin])
                    out.append('    <path d="' + path_pts(pts, True) + '" fill="rgba(59,130,246,.16)"'
                               + ' stroke="#3b82f6" stroke-width="2"/>')
            elif d.get("loops"):
                for loop in d["loops"]:
                    if len(loop) >= 3:
                        out.append('    <path d="' + path_pts(loop, True) + '" fill="rgba(59,130,246,.16)"'
                                   + ' stroke="#3b82f6" stroke-width="2"/>')
        elif el.kind == "polyline":
            if len(el.xs) >= 2:
                pts = [[x, y] for x, y in zip(el.xs, el.ys)]
                out.append('    <path d="' + path_pts(pts) + '" fill="none" stroke="' + color(el)
                           + '" stroke-width="2"/>')
        elif el.kind == "vector":
            x0, y0, dx, dy = el.sx, el.sy, el.dx, el.dy
            norm = math.hypot(dx, dy) or 1
            ex, ey = x0 + dx, y0 + dy
            out.append('    <line x1="' + str(X(x0)) + '" y1="' + str(Y(y0)) + '" x2="' + str(X(ex))
                       + '" y2="' + str(Y(ey)) + '" stroke="' + color(el) + '" stroke-width="2"'
                       + ' marker-end="url(#arrow)"/>')
        elif el.kind == "arc":
            cxp, cyp, rr = el.cx, el.cy, el.r
            a1, a2 = el.ang1, el.ang2
            if el.semicircle:
                a2 = a1 + math.pi
            span = (a2 - a1) % (2 * math.pi)
            large = 1 if span > math.pi else 0
            sweep = 0 if (a2 - a1) > 0 else 1
            p1x, p1y = cxp + rr * math.cos(a1), cyp + rr * math.sin(a1)
            p2x, p2y = cxp + rr * math.cos(a2), cyp + rr * math.sin(a2)
            radpx = rr * s
            dpath = ('M ' + str(X(p1x)) + ' ' + str(Y(p1y)) + ' A ' + str(radpx) + ' ' + str(radpx)
                     + ' 0 ' + str(large) + ' ' + str(sweep) + ' ' + str(X(p2x)) + ' ' + str(Y(p2y)))
            if getattr(el, "sector", False):
                dpath += ' L ' + str(X(cxp)) + ' ' + str(Y(cyp)) + ' Z'
            out.append('    <path d="' + dpath + '" fill="none" stroke="' + color(el)
                       + '" stroke-width="2"/>')
        elif el.kind == "angle":
            cxp, cyp = el.cx, el.cy
            rr = min(abs(xmax - xmin), abs(ymax - ymin)) * 0.07
            a1 = el.ang1
            a2 = a1 + el.rad
            radpx = rr * s
            p1x, p1y = cxp + rr * math.cos(a1), cyp + rr * math.sin(a1)
            p2x, p2y = cxp + rr * math.cos(a2), cyp + rr * math.sin(a2)
            large = 1 if abs(el.rad) > math.pi else 0
            sweep = 0 if el.rad > 0 else 1
            out.append('    <path d="M ' + str(X(p1x)) + ' ' + str(Y(p1y)) + ' A ' + str(radpx) + ' '
                       + str(radpx) + ' 0 ' + str(large) + ' ' + str(sweep) + ' ' + str(X(p2x)) + ' '
                       + str(Y(p2y)) + '" fill="none" stroke="#7c3aed" stroke-width="2"/>')
            mid = a1 + el.rad / 2
            out.append('    <text x="' + str(X(cxp) + rr * 1.45 * math.cos(mid)) + '" y="'
                       + str(Y(cyp) - rr * 1.45 * math.sin(mid)) + '" font-size="13" fill="#7c3aed">'
                       + _esc(("%.0f" % el.value) + "°") + '</text>')
        elif el.kind == "text":
            out.append('    <text x="' + str(X(el.x)) + '" y="' + str(Y(el.y)) + '" font-size="15"'
                       + ' fill="#111827">' + _esc(el.content) + '</text>')
        elif el.kind in ("parametric", "polar"):
            # 参数曲线 / 极坐标曲线：内核 draw() 已给出采样点 pts（曾漏导出 → SVG 里曲线消失 ✗）
            d = el.draw(view) or {}
            pts = d.get("pts") or []
            if len(pts) >= 2:
                out.append('    <path d="' + path_pts(pts) + '" fill="none" stroke="' + color(el)
                           + '" stroke-width="2"/>')
        elif el.kind == "implicit":
            # 隐式曲线：draw() 给的是 marching squares 线段对 [x1,y1,x2,y2]
            d = el.draw(view) or {}
            for seg in d.get("segs", []):
                if len(seg) >= 4:
                    out.append('    <line x1="' + str(X(seg[0])) + '" y1="' + str(Y(seg[1]))
                               + '" x2="' + str(X(seg[2])) + '" y2="' + str(Y(seg[3]))
                               + '" stroke="' + color(el) + '" stroke-width="2"/>')
        elif el.kind == "locus":
            if len(el.pts) >= 2:
                out.append('    <path d="' + path_pts(el.pts) + '" fill="none" stroke="#dc2626"'
                           + ' stroke-width="2"/>')
        elif el.kind == "sumrect":
            for rc in el.rects:
                if len(rc) >= 4:
                    yHi, yLo = max(rc[2], rc[3]), min(rc[2], rc[3])
                else:
                    yHi, yLo = max(rc[2], 0), min(rc[2], 0)
                xw = X(rc[1]) - X(rc[0])
                yh = Y(yLo) - Y(yHi)
                out.append('    <rect x="' + str(X(rc[0])) + '" y="' + str(Y(yHi)) + '" width="'
                           + str(xw) + '" height="' + str(yh) + '" fill="rgba(15,118,110,.18)"'
                           + ' stroke="#0f766e" stroke-width="1.2"/>')

    out.append('  <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3"'
               + ' orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="#0d9488"/></marker></defs>')
    out.append('</svg>')
    return "\n".join(out)


def _split_nan(pts):
    runs = []
    cur = []
    for p in pts:
        if len(p) < 2 or not math.isfinite(p[1]):
            if cur:
                runs.append(cur)
                cur = []
        else:
            cur.append(p)
    if cur:
        runs.append(cur)
    return runs


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# 3D 投影导出（P2）：把 3D 场景按固定视角做正交投影，输出矢量图
# ---------------------------------------------------------------------------

# 3D 导出用的固定光照方向（世界坐标，左上前方）与明暗范围
_LIGHT = (-0.42, -0.55, 0.72)


def _lambert(verts, face) -> float:
    """按面法向与光照方向算一个填充不透明度（0.16–0.58），给正交投影一点体积感。

    只有网格面用它；平面/球等仍走各自的固定值。
    """
    try:
        a, b, c = verts[face[0]], verts[face[1]], verts[face[2]]
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        d = abs((nx * _LIGHT[0] + ny * _LIGHT[1] + nz * _LIGHT[2]) / nl)
    except Exception:  # 防御性捕获：顶点/面索引异常不应让整份 SVG 导出失败，退化为中等明暗
        d = 0.5
    return 0.74 + 0.26 * d


def _rot3(yaw: float, pitch: float):
    """返回 (x,y,z) → 相机坐标 (u, v, depth) 的旋转（先绕 z 偏航，再绕 x 俯仰）。"""
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)

    def f(p):
        x, y, z = float(p[0]), float(p[1]), float(p[2] or 0.0)
        # 绕 z 轴
        x1 = x * cy - y * sy
        y1 = x * sy + y * cy
        # 绕 x 轴（俯仰）
        y2 = y1 * cp - z * sp
        z2 = y1 * sp + z * cp
        return x1, y2, z2
    return f


def _scene_points(cons) -> List[List[float]]:
    """收集 3D 场景里所有几何点的世界坐标（用于自动取景与范围判断）。"""
    pts: List[List[float]] = []
    for lab in cons.order:
        el = cons.elements[lab]
        if el.visible is False:
            continue
        if el.kind == "point":
            pts.append([el.x, el.y, el.z if el.z is not None else 0.0])
            continue
        d = getattr(el, "data", None)
        if isinstance(d, dict):
            for v in (d.get("verts") or [])[:20000]:
                if isinstance(v, (list, tuple)) and len(v) >= 3:
                    pts.append([float(v[0]), float(v[1]), float(v[2])])
            for key, off in (("segs", 0), ("pts", 0)):
                for item in (d.get(key) or [])[:5000]:
                    if isinstance(item, (list, tuple)) and len(item) >= 3 and all(
                            isinstance(c, (int, float)) for c in item[:3]):
                        pts.append([float(item[0]), float(item[1]), float(item[2])])
        if getattr(el, "objtype", "") == "sphere" and isinstance(d, dict):
            cx, cy, cz, r = float(d.get("cx", 0)), float(d.get("cy", 0)), float(d.get("cz", 0)), float(d.get("r", 0))
            for k in range(8):
                th = 2 * math.pi * k / 8
                pts.append([cx + r * math.cos(th), cy + r * math.sin(th), cz])
                pts.append([cx, cy + r * math.cos(th), cz + r * math.sin(th)])
        if getattr(el, "objtype", "") == "plane" and isinstance(d, dict):
            # 平面按 a/u/v 展开为四边形，取景必须算上它的四个角点，否则四边形会越出画布 ✗
            a3 = [float(d.get(k, 0)) for k in ("ax", "ay", "az")]
            u3 = [float(d.get(k, 0)) for k in ("ux", "uy", "uz")]
            v3 = [float(d.get(k, 0)) for k in ("vx", "vy", "vz")]
            for su, sv in ((0, 0), (1, 0), (1, 1), (0, 1)):
                pts.append([a3[i] + su * u3[i] + sv * v3[i] for i in range(3)])
        if getattr(el, "objtype", "") == "circle3d" and isinstance(d, dict):
            # 空间圆没有 verts/segs，取景必须单独采样，否则导出会溢出画布（曾致 PNG 边框变大 ✗）
            cx3, cy3, cz3 = float(d.get("cx", 0)), float(d.get("cy", 0)), float(d.get("cz", 0))
            r3 = float(d.get("r", 0))
            u3 = d.get("u") or [1, 0, 0]
            v3 = d.get("v") or [0, 1, 0]
            for k in range(24):
                th = 2 * math.pi * k / 24
                pts.append([cx3 + r3 * (math.cos(th) * u3[i] + math.sin(th) * v3[i]) for i in range(3)])
    return pts


def export_svg3d(cons, width: int = 1000, height: int = 700, yaw: float = -0.62,
                 pitch: float = -0.52, face_budget: int = 4000) -> str:
    """把 3D 场景导出为 SVG（正交投影 + 画家算法）。

    注意俯仰号约定：`pitch > 0` 是**从下往上看**，`pitch < 0` 才是俯视 ——
    默认取 −0.52（俯视），与画布 3D 视图的默认机位观感一致。

    - 网格/多面体：按深度从远到近绘制多边形（超 face_budget 时只画面积最大的若干面）
    - 球：经纬线；直线/线段/射线/交线：折线；点：圆点 + 标签
    - 自动取景：按场景包围盒缩放到画布内
    """
    from .elements import GeoError

    w, h = width, height
    has3d = any(cons.elements[lab].kind == "geo3d" or
                (cons.elements[lab].kind == "point" and getattr(cons.elements[lab], "z", None) is not None)
                for lab in cons.order)
    if not has3d:
        raise GeoError("当前构造没有 3D 对象（3D 投影导出至少需要一个 3D 对象或三维点）")
    rot = _rot3(yaw, pitch)
    pts = _scene_points(cons)
    if not pts:
        raise GeoError("3D 场景为空（没有可投影的几何数据）")
    us = [rot(p)[0] for p in pts]
    vs = [rot(p)[1] for p in pts]
    umin, umax = min(us), max(us)
    vmin, vmax = min(vs), max(vs)
    pad = 0.08
    span_u = max(COARSE, umax - umin) * (1 + 2 * pad)
    span_v = max(COARSE, vmax - vmin) * (1 + 2 * pad)
    s = min((w - 40) / span_u, (h - 60) / span_v)
    cu = (umin + umax) / 2.0
    cv = (vmin + vmax) / 2.0

    def P(p):
        u, v, z = rot(p)
        return (round((u - cu) * s + w / 2.0, 2), round(h / 2.0 - (v - cv) * s, 2), z)

    polys: List[Tuple[float, str, str]] = []      # (depth, 多边形点串, 样式)
    lines: List[Tuple[float, str, str]] = []      # (depth, 折线点串, 样式)
    dots: List[Tuple[float, float, float, str]] = []   # (depth, x, y, 标签)

    for lab in cons.order:
        el = cons.elements[lab]
        if el.visible is False:
            continue
        col = getattr(el, "color", "#1a1a1a") or "#1a1a1a"
        if el.kind == "point":
            x, y, z = P([el.x, el.y, el.z if el.z is not None else 0.0])
            dots.append((z, x, y, lab))
            continue
        if el.kind != "geo3d":
            continue
        d = getattr(el, "data", None) or {}
        obj = getattr(el, "objtype", "")
        if obj in ("cube", "polyhedron") and isinstance(d.get("faces"), list):
            verts = d.get("verts") or []
            faces = d["faces"]
            idxs = list(range(len(faces)))
            if len(faces) > face_budget:
                def _area(f):
                    a0 = verts[f[0]]
                    tot = 0.0
                    for k in range(1, len(f) - 1):
                        b, c = verts[f[k]], verts[f[k + 1]]
                        ux, uy, uz = b[0] - a0[0], b[1] - a0[1], b[2] - a0[2]
                        vx, vy, vz = c[0] - a0[0], c[1] - a0[1], c[2] - a0[2]
                        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                        tot += 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)
                    return tot
                idxs = sorted(idxs, key=lambda i: -_area(faces[i]))[:face_budget]
            for fi in idxs:
                f = faces[fi]
                pr = [P(verts[i]) for i in f]
                zavg = sum(q[2] for q in pr) / max(1, len(pr))
                pts_s = " ".join("%s,%s" % (q[0], q[1]) for q in pr)
                polys.append((zavg, pts_s, col + "|" + "%.2f" % _lambert(verts, f)))
            for e2 in (d.get("edges") or [])[:20000]:
                a, b = verts[e2[0]], verts[e2[1]]
                pa, pb = P(a), P(b)
                lines.append(((pa[2] + pb[2]) / 2.0, "%s,%s %s,%s" % (pa[0], pa[1], pb[0], pb[1]), col))
        elif obj == "sphere":
            cx, cy, cz, r = (float(d.get("cx", 0)), float(d.get("cy", 0)), float(d.get("cz", 0)), float(d.get("r", 0)))
            for ring in range(1, 5):
                for axis in (0, 1):
                    seq = []
                    for k in range(37):
                        th = 2 * math.pi * k / 36
                        if axis == 0:
                            p3 = [cx + r * math.cos(th), cy + r * math.sin(th), cz + r * (ring - 2.5) / 3.5]
                        else:
                            p3 = [cx + r * (ring - 2.5) / 3.5, cy + r * math.cos(th), cz + r * math.sin(th)]
                        seq.append(P(p3))
                    avg = sum(q[2] for q in seq) / len(seq)
                    lines.append((avg, " ".join("%s,%s" % (q[0], q[1]) for q in seq), col))
        elif obj == "plane":
            a3 = [float(d.get("ax", 0)), float(d.get("ay", 0)), float(d.get("az", 0))]
            u3 = [float(d.get("ux", 1)), float(d.get("uy", 0)), float(d.get("uz", 0))]
            v3 = [float(d.get("vx", 0)), float(d.get("vy", 1)), float(d.get("vz", 0))]
            # 与画布端一致：a 是**角点**、u/v 是**整条边**（早前误当 ±1 半宽 → 四边形大出一倍 ✗）
            quad = [[a3[i] + su * u3[i] + sv * v3[i] for i in range(3)]
                    for su, sv in ((0, 0), (1, 0), (1, 1), (0, 1))]
            pr = [P(q) for q in quad]
            polys.append((sum(q[2] for q in pr) / 4.0,
                          " ".join("%s,%s" % (q[0], q[1]) for q in pr), col + "|0.30"))
        elif obj == "circle3d":
            # 空间圆：data 给 (cx,cy,cz,r,u,v)，采样 64 点画闭合折线（原先漏画 ✗）
            cx3, cy3, cz3 = float(d.get("cx", 0)), float(d.get("cy", 0)), float(d.get("cz", 0))
            r3 = float(d.get("r", 0))
            u3 = d.get("u") or [1, 0, 0]
            v3 = d.get("v") or [0, 1, 0]
            seq = []
            for k in range(65):
                th = 2 * math.pi * k / 64
                seq.append(P([cx3 + r3 * (math.cos(th) * u3[i] + math.sin(th) * v3[i]) for i in range(3)]))
            lines.append((sum(q[2] for q in seq) / len(seq),
                          " ".join("%s,%s" % (q[0], q[1]) for q in seq), col))
        elif isinstance(d.get("pts"), list) and len(d.get("pts") or []) >= 2:
            # 截面多边形（section）/ 交线（curve3d）：data.pts 为三维点序列（原先漏画 ✗）
            pr = [P(q) for q in d["pts"] if isinstance(q, (list, tuple)) and len(q) >= 3]
            zavg = sum(q[2] for q in pr) / max(1, len(pr))
            pts_s = " ".join("%s,%s" % (q[0], q[1]) for q in pr)
            if obj == "section":
                polys.append((zavg, pts_s, col + "|0.45"))
            else:
                lines.append((zavg, pts_s, col))
        else:
            # 线段/直线/射线/曲面等：用 segs 折线
            segs = d.get("segs")
            if isinstance(segs, list):
                for seg in segs[:6000]:
                    if (isinstance(seg, (list, tuple)) and len(seg) == 2
                            and all(isinstance(q, (list, tuple)) and len(q) >= 3 for q in seg)):
                        pa, pb = P(seg[0]), P(seg[1])
                        lines.append(((pa[2] + pb[2]) / 2.0,
                                      "%s,%s %s,%s" % (pa[0], pa[1], pb[0], pb[1]), col))

    polys.sort(key=lambda t: t[0])          # 远 → 近
    lines.sort(key=lambda t: t[0])
    out: List[str] = []
    out.append('<?xml version="1.0" encoding="utf-8"?>')
    out.append('<svg xmlns="http://www.w3.org/2000/svg" width="' + str(w) + '" height="' + str(h)
               + '" viewBox="0 0 ' + str(w) + ' ' + str(h) + '">')
    # 注意：desc 是 XML 文本，**不能出现裸 '<'**（`pitch<0` 会让 SVG 变成非法 XML ✗）
    out.append('  <desc>ggbpy 3D 投影导出（yaw=%.3f pitch=%.3f；pitch 取负值即俯视）</desc>' % (yaw, pitch))
    out.append('  <rect width="100%" height="100%" fill="#ffffff"/>')
    for _z, pts_s, col in polys:
        col, _, op = col.partition("|")   # 注意分隔符不能用 '#'（颜色本身就是 #rrggbb）
        out.append('  <polygon points="' + pts_s + '" fill="' + col
                   + '" fill-opacity="' + (op or "0.3") + '" stroke="' + col
                   + '" stroke-width="1.1" stroke-opacity="0.8"/>')
    for _z, pts_s, col in lines:
        out.append('  <polyline points="' + pts_s + '" fill="none" stroke="' + col
                   + '" stroke-width="1.2" stroke-opacity="0.85"/>')
    for z, x, y, lab in sorted(dots, key=lambda t: -t[0]):
        out.append('  <circle cx="%s" cy="%s" r="3.2" fill="#111827"/>' % (x, y))
        out.append('  <text x="%s" y="%s" font-size="12" fill="#111827">%s</text>'
                   % (round(x + 6, 1), round(y - 6, 1), _esc(lab)))
    out.append('</svg>')
    return "\n".join(out)
