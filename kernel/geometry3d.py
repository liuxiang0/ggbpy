"""3D 几何算法层（从 kernel/commands.py 抽出，P2 结构拆分）。

只依赖 math / numpy 与 elements（Geo3D/GeoError），**不依赖命令层**
（不引用 _resolve/_mk/eval_number 等），因此可独立导入与单测。

包含：网格规范化与体积/面积、凸多面体半空间裁剪、各类 3D 求交
（面×面、线×面、平面×立体、球×平面/球/空间圆/立体/直线、立体×直线、立体×立体）、
空间圆基向量、射线-三角形、解二元一次方程、多面体状态打包。
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from . import mesh_store
from . import schemas
from .elements import Geo3D, GeoError
from .tolerance import EPSILON, COORD, ZERO_SQ, LOOSE, COARSE  # 统一数值容差（见 kernel/tolerance.py）

__all__ = [
    "_tag3d",
    "_z_of",
    "_has_z",
    "_dist3",
    "_solve2",
    "_line_ends",
    "_circle3d_basis",
    "_ray_triangle",
    "_frame_from_axis",
    "_normalize_mesh",
    "_newell_normal",
    "_mesh_volume",
    "_mesh_area",
    "_solid_volume",
    "_solid_area",
    "_is_solid_el",
    "_solid_planes",
    "_clip_polyhedron",
    "_ix_plane_plane",
    "_ix_line_plane",
    "_ix_line3d_plane",
    "_ix_solid_plane",
    "_ix_sphere_sphere",
    "_ix_sphere_circle3d",
    "_ix_circle3d_circle3d",
    "_ix_circle3d_plane",
    "_ix_circle3d_solid",
    "_ix_sphere_solid",
    "_ix_sphere_plane",
    "_ix_solid_solid",
    "_ix_solid_line",
    "_ix_sphere_line",
    "_poly_state",
]


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

def _solve2(a, b, e, c, f, g):
    """解 ax+by=e, cx+fy=g。"""
    det = a * f - c * b
    if abs(det) < EPSILON:
        raise GeoError("退化方程组")
    return (e * f - b * g) / det, (a * g - e * c) / det

def _line_ends(el):
    d = el.data
    return ([d["x1"], d["y1"], d["z1"]], [d["x2"], d["y2"], d["z2"]])

def _circle3d_basis(d):
    """空间圆的 (圆心, 半径, 法向, 基 u, 基 v)。"""
    return ([d["cx"], d["cy"], d["cz"]], d["r"], d["normal"], d["u"], d["v"])

def _ray_triangle(orig, dirv, a, b, c):
    """Möller–Trumbore：射线 orig + t·dirv 与三角形求交，返回 t 或 None。"""
    e1 = [b[k] - a[k] for k in range(3)]
    e2 = [c[k] - a[k] for k in range(3)]
    h = [dirv[1] * e2[2] - dirv[2] * e2[1],
         dirv[2] * e2[0] - dirv[0] * e2[2],
         dirv[0] * e2[1] - dirv[1] * e2[0]]
    det = e1[0] * h[0] + e1[1] * h[1] + e1[2] * h[2]
    if abs(det) < EPSILON:
        return None
    inv = 1.0 / det
    s = [orig[k] - a[k] for k in range(3)]
    u = (s[0] * h[0] + s[1] * h[1] + s[2] * h[2]) * inv
    if u < -COORD or u > 1 + COORD:
        return None
    q = [s[1] * e1[2] - s[2] * e1[1], s[2] * e1[0] - s[0] * e1[2], s[0] * e1[1] - s[1] * e1[0]]
    v = (dirv[0] * q[0] + dirv[1] * q[1] + dirv[2] * q[2]) * inv
    if v < -COORD or u + v > 1 + COORD:
        return None
    t = (e2[0] * q[0] + e2[1] * q[1] + e2[2] * q[2]) * inv
    # 容差：起点恰在面上（t=0）也算命中；由调用方按线段范围过滤
    return t if t > -COORD else None

def _frame_from_axis(d):
    """由轴向构造正交基 (u, v, n)：n 为单位轴，u/v 为垂直平面的基。"""
    n = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
    if n < EPSILON:
        raise GeoError("方向向量退化")
    n = [d[0] / n, d[1] / n, d[2] / n]
    ref = [0.0, 0.0, 1.0]
    if abs(n[2]) > 0.9:
        ref = [1.0, 0.0, 0.0]
    dot = ref[0] * n[0] + ref[1] * n[1] + ref[2] * n[2]
    u = [ref[0] - dot * n[0], ref[1] - dot * n[1], ref[2] - dot * n[2]]
    ln = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
    if ln < EPSILON:
        ref = [0.0, 1.0, 0.0]
        dot = ref[0] * n[0] + ref[1] * n[1] + ref[2] * n[2]
        u = [ref[0] - dot * n[0], ref[1] - dot * n[1], ref[2] - dot * n[2]]
        ln = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
    u = [u[0] / ln, u[1] / ln, u[2] / ln]
    v = [n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0]]
    return u, v, n

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
        if ln < EPSILON and len(idx) < 3:
            continue
        if ln < EPSILON:
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
            if best[0] < EPSILON:
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
            if math.sqrt(dx * dx + dy * dy + dz * dz) > EPSILON:
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

def _is_solid_el(el) -> bool:
    """网格立体（立方体/多面体/锥/柱：objtype 为 cube 或 polyhedron）。"""
    return getattr(el, "objtype", "") in ("cube", "polyhedron")

def _solid_planes(el):
    """把凸立体转成外向半空间列表 [(n, d)]：内部满足 n·x + d ≤ 0。"""
    vs = el.data["verts"]
    faces = el.data["faces"]
    planes = []
    for f in faces:
        nx, ny, nz = _newell_normal(vs, f)
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        if ln < EPSILON:
            continue
        nx, ny, nz = nx / ln, ny / ln, nz / ln
        p = vs[f[0]]
        planes.append(((nx, ny, nz), -(nx * p[0] + ny * p[1] + nz * p[2])))
    return planes

def _clip_polyhedron(verts, faces, plane):
    """用一个半空间 n·x + d ≤ 0 裁剪凸多面体（顶点/面表），返回新的 (verts, faces)。"""
    n, d = plane

    def inside(p):
        return n[0] * p[0] + n[1] * p[1] + n[2] * p[2] + d <= EPSILON

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
            if not dedup or math.dist(p, dedup[-1]) > COORD:
                dedup.append(p)
        if len(dedup) >= 3:
            if math.dist(dedup[0], dedup[-1]) < COORD:
                dedup.pop()
            out_faces.append(dedup)
    if not out_faces:
        return [], []
    # 顶点表（按坐标去重）
    new_verts = []
    for f in out_faces:
        for p in f:
            if not any(math.dist(p, q) < COORD for q in new_verts):
                new_verts.append(p)
    idx_faces = [[next(i for i, q in enumerate(new_verts) if math.dist(p, q) < COORD) for p in f] for f in out_faces]
    # 截面封盖：把裁剪产生的点按平面内极角排序
    if len(cut_pts) >= 3:
        uniq = []
        for p in cut_pts:
            if not any(math.dist(p, q) < COORD for q in uniq):
                uniq.append(p)
        if len(uniq) >= 3:
            ctr = [sum(p[k] for p in uniq) / len(uniq) for k in range(3)]
            ux = uy = uz = 0.0
            for p in uniq:
                dx, dy, dz = p[0] - ctr[0], p[1] - ctr[1], p[2] - ctr[2]
                dd = math.sqrt(dx * dx + dy * dy + dz * dz)
                if dd > EPSILON:
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
                if not any(math.dist(p, q) < COORD for q in [new_verts[i] for i in range(len(new_verts))]):
                    new_verts.append(p)
                cap.append(next(i for i, q in enumerate(new_verts) if math.dist(p, q) < COORD))
            idx_faces.append(cap)
    return new_verts, idx_faces

def _ix_plane_plane(p1, p2):
    """两面交线：方向 = 法向叉积；线上一点解 2x2。"""
    a1, b1, c1, d1 = p1.data["a"], p1.data["b"], p1.data["c"], p1.data["d"]
    a2, b2, c2, d2 = p2.data["a"], p2.data["b"], p2.data["c"], p2.data["d"]
    dx = b1 * c2 - c1 * b2
    dy = c1 * a2 - a1 * c2
    dz = a1 * b2 - b1 * a2
    ln = math.sqrt(dx * dx + dy * dy + dz * dz)
    if ln < EPSILON:
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
    return schemas.line3d(px - dx / ln * L, py - dy / ln * L, pz - dz / ln * L,
                          px + dx / ln * L, py + dy / ln * L, pz + dz / ln * L)

def _ix_line_plane(seg, pl):
    """线段与平面交点。"""
    d = seg.data
    x1, y1, z1 = d["x1"], d["y1"], d["z1"]
    x2, y2, z2 = d["x2"], d["y2"], d["z2"]
    a, b, c, dd = pl.data["a"], pl.data["b"], pl.data["c"], pl.data["d"]
    ux, uy, uz = x2 - x1, y2 - y1, z2 - z1
    denom = a * ux + b * uy + c * uz
    if abs(denom) < EPSILON:
        raise GeoError("线段与平面平行")
    t = -(a * x1 + b * y1 + c * z1 + dd) / denom
    if t < -COORD or t > 1 + COORD:
        raise GeoError("交点不在线段上")
    return {"x": x1 + t * ux, "y": y1 + t * uy, "z": z1 + t * uz}

def _ix_line3d_plane(lin, pl):
    """三维直线（无限）与平面交点。"""
    p, q = _line_ends(lin)
    a, b, c, dd = pl.data["a"], pl.data["b"], pl.data["c"], pl.data["d"]
    ux, uy, uz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
    denom = a * ux + b * uy + c * uz
    if abs(denom) < EPSILON:
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
        if abs(fp) < COORD and abs(fq) < COORD:
            continue                      # 整条边落在平面上：该面本身在平面内，交由其它边给出顶点
        if abs(fp) < COORD:
            pts.append([p[0], p[1], p[2]])
            continue                      # 端点恰在平面上（如平面正好切过顶面）
        if abs(fq) < COORD:
            pts.append([q[0], q[1], q[2]])
            continue
        if (fp > 0) == (fq > 0):
            continue
        t = fp / (fp - fq)
        pts.append([p[k] + t * (q[k] - p[k]) for k in range(3)])
    uniq = []
    for p in pts:
        if not any(math.dist(p, q) < COORD for q in uniq):
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
        if d > EPSILON:
            ux, uy, uz = dx / d, dy / d, dz / d
            break
    wx = ny * uz - nz * uy
    wy = nz * ux - nx * uz
    wz = nx * uy - ny * ux

    def _ang(p):
        dx, dy, dz = p[0] - ctr[0], p[1] - ctr[1], p[2] - ctr[2]
        return math.atan2(dx * wx + dy * wy + dz * wz, dx * ux + dy * uy + dz * uz)

    uniq.sort(key=_ang)
    return schemas.section(uniq, [nx, ny, nz])

def _ix_sphere_sphere(s1, s2):
    """两球求交 → 交圆（空间圆）：交平面垂直于连心线，半径 √(r1²−a²)。"""
    a1, b1, c1, r1 = s1.data["cx"], s1.data["cy"], s1.data["cz"], s1.data["r"]
    a2, b2, c2, r2 = s2.data["cx"], s2.data["cy"], s2.data["cz"], s2.data["r"]
    dx, dy, dz = a2 - a1, b2 - b1, c2 - c1
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    if dist < COORD:
        raise GeoError("同心球没有交线（球面重合或内含）")
    if dist > r1 + r2 + COORD:
        raise GeoError("两球相离，无交线")
    if dist < abs(r1 - r2) - COORD:
        raise GeoError("一球完全在另一球内部，无交线")
    ux, uy, uz = dx / dist, dy / dist, dz / dist
    t = (dist * dist + r1 * r1 - r2 * r2) / (2 * dist)      # 交平面到球心 1 的距离
    rr2 = r1 * r1 - t * t
    if rr2 <= ZERO_SQ:
        raise GeoError("两球相切（交线退化为一点）")
    ox, oy, oz = a1 + t * ux, b1 + t * uy, c1 + t * uz
    u, v, _n = _frame_from_axis([ux, uy, uz])
    return schemas.circle3d(ox, oy, oz, math.sqrt(rr2), [ux, uy, uz], u, v)

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
    if R0 < EPSILON:
        if abs(D) < COORD:
            raise GeoError("圆在球面上（无穷多交点）")
        raise GeoError("圆与球不相交")
    if abs(D) > R0 + EPSILON:
        raise GeoError("圆与球不相交")
    phi = math.atan2(wv, wu)
    delta = math.acos(max(-1.0, min(1.0, D / R0)))
    ts = sorted([phi + delta, phi - delta])
    if len(ts) == 2 and abs(ts[0] - ts[1]) < EPSILON:
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
    same_plane = abs(abs(dot_n) - 1.0) < COORD and abs(plane_gap) < LOOSE

    if same_plane:
        # 平面内两圆（经典 2D 情形），以 c1 为原点、u1/v1 为基
        px = dvec[0] * u1[0] + dvec[1] * u1[1] + dvec[2] * u1[2]
        py = dvec[0] * v1[0] + dvec[1] * v1[1] + dvec[2] * v1[2]
        dist = math.sqrt(px * px + py * py)
        if dist < COORD:
            if abs(r1 - r2) < COORD:
                raise GeoError("两圆重合（无穷多交点）")
            raise GeoError("同心圆无交点")
        if dist > r1 + r2 + EPSILON or dist < abs(r1 - r2) - EPSILON:
            raise GeoError("两圆不相交")
        a = (dist * dist + r1 * r1 - r2 * r2) / (2 * dist)
        h2 = r1 * r1 - a * a
        ux, uy = px / dist, py / dist
        bx = c1[0] + a * ux * u1[0] + a * uy * v1[0]
        by = c1[1] + a * ux * u1[1] + a * uy * v1[1]
        bz = c1[2] + a * ux * u1[2] + a * uy * v1[2]
        if h2 <= ZERO_SQ:
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
        if math.sqrt(nx * nx + ny * ny + nz * nz) < COORD:
            raise GeoError("两圆所在平面平行，无交点")
        dvec2 = [c2[i] - c1[i] for i in range(3)]
        E = n1[0] * dvec2[0] + n1[1] * dvec2[1] + n1[2] * dvec2[2]
        A = r2 * (n1[0] * u2[0] + n1[1] * u2[1] + n1[2] * u2[2])
        B = r2 * (n1[0] * v2[0] + n1[1] * v2[1] + n1[2] * v2[2])
        R0 = math.sqrt(A * A + B * B)
        if abs(E) > R0 + EPSILON:
            raise GeoError("两圆不相交")
        phi = math.atan2(B, A)
        delta = math.acos(max(-1.0, min(1.0, -E / R0)))
        ts = sorted([phi + delta, phi - delta])
        if len(ts) == 2 and abs(ts[0] - ts[1]) < EPSILON:
            ts = [ts[0]]

        def _p2(t):
            return [c2[0] + r2 * (math.cos(t) * u2[0] + math.sin(t) * v2[0]),
                    c2[1] + r2 * (math.cos(t) * u2[1] + math.sin(t) * v2[1]),
                    c2[2] + r2 * (math.cos(t) * u2[2] + math.sin(t) * v2[2])]

        pts = []
        for t in ts:
            p = _p2(t)
            ddx, ddy, ddz = p[0] - c1[0], p[1] - c1[1], p[2] - c1[2]
            if abs(math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz) - r1) < LOOSE:
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
    if ln < EPSILON:
        raise GeoError("平面退化")
    nx, ny, nz = a / ln, b / ln, cc / ln
    dpl = dd / ln
    E = nx * c[0] + ny * c[1] + nz * c[2] + dpl          # 圆心到平面的有符号距离
    A = r * (nx * u[0] + ny * u[1] + nz * u[2])
    B = r * (nx * v[0] + ny * v[1] + nz * v[2])
    R = math.sqrt(A * A + B * B)
    if R < EPSILON:
        if abs(E) < COORD:
            raise GeoError("圆与平面共面（交线为整个圆）")
        raise GeoError("圆所在平面与给定平面平行，无交点")
    if abs(E) > R + EPSILON:
        raise GeoError("平面与圆不相交")
    phi = math.atan2(B, A)
    delta = math.acos(max(-1.0, min(1.0, -E / R)))
    ts = [phi + delta, phi - delta]
    ts.sort()
    if len(ts) == 2 and abs(ts[0] - ts[1]) < EPSILON:
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
        return all(n[0] * p[0] + n[1] * p[1] + n[2] * p[2] + dd <= COORD for n, dd in planes)

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
        if best is not None and best[0] < COARSE:
            crossings = [best[1]]
        else:
            raise GeoError("圆与立体无交点（整圆在立体内部或外部）")
    # 去重（相切会成对出现）
    uniq = []
    for t in sorted(crossings):
        if not uniq or abs(t - uniq[-1]) > COARSE:
            uniq.append(t)
    k = idx or 1
    if k > len(uniq):
        raise GeoError("交点只有 " + str(len(uniq)) + " 个（请求第 " + str(k) + " 个）")
    return dict(zip(("x", "y", "z"), pt(uniq[k - 1])))

def _ix_sphere_solid(sph, solid):
    """球面 ∩ 凸立体 → 交线（objtype=curve3d：按立体各面分段的折线集合）。

    用 numpy 一次性对所有半空间做内点判定（此前逐点 Python 循环是 O(面数²)）。
    """
    import numpy as np
    d = sph.data
    c = np.array([float(d["cx"]), float(d["cy"]), float(d["cz"])])
    r = float(d["r"])
    planes = _solid_planes(solid)
    faces = solid.data["faces"]
    if len(planes) > 4000:
        raise GeoError("立体的面数过多（%d > 4000），球×复杂网格暂不支持；请改用凸多面体或降低网格分辨率"
                       % len(planes))
    N = 180
    P = np.array([p[0] for p in planes], dtype=float)
    Q = np.array([p[1] for p in planes], dtype=float)
    th = np.linspace(0.0, 2 * math.pi, N, endpoint=False)
    ct, st = np.cos(th), np.sin(th)
    segs = []
    for (n, dd), face in zip(planes, faces):
        nv = np.asarray(n, dtype=float)
        sdist = float(nv @ c + dd)
        if abs(sdist) > r - COORD:
            continue                      # 平面与球不相交/相切
        rr = math.sqrt(max(0.0, r * r - sdist * sdist))
        cen = c - sdist * nv
        u, v, _nn = _frame_from_axis(list(nv))
        U = np.asarray(u, dtype=float)
        V = np.asarray(v, dtype=float)
        pts = cen[None, :] + rr * (ct[:, None] * U[None, :] + st[:, None] * V[None, :])
        maxv = (pts @ P.T + Q[None, :]).max(axis=1)      # 到所有半空间的最大值 ≤ 0 → 在体内
        keep = pts[maxv <= LOOSE]
        if len(keep) < 2:
            continue
        for k in range(len(keep) - 1):
            segs.append([list(keep[k]), list(keep[k + 1])])
    if not segs:
        raise GeoError("球面与立体不相交（或交线退化）")
    return schemas.curve3d(segs)

def _ix_sphere_plane(sph, pl):
    """球 ∩ 平面 → 3D 圆（objtype=circle3d，带圆心/半径/所在平面法向与基）。"""
    d = sph.data
    cx, cy, cz, r = d["cx"], d["cy"], d["cz"], d["r"]
    a, b, c, dd = pl.data["a"], pl.data["b"], pl.data["c"], pl.data["d"]
    ln = math.sqrt(a * a + b * b + c * c)
    if ln < EPSILON:
        raise GeoError("平面退化")
    nx, ny, nz = a / ln, b / ln, c / ln
    sdist = nx * cx + ny * cy + nz * cz + dd / ln          # 球心到平面的有符号距离（平面：n·x+d=0）
    if abs(sdist) > r + COORD:
        raise GeoError("平面与球不相交（球心距 %.6f > 半径 %.6f）" % (abs(sdist), r))
    rr = math.sqrt(max(0.0, r * r - sdist * sdist))
    if rr < COORD:
        raise GeoError("平面与球相切（交线退化为一点）")
    ox, oy, oz = cx - sdist * nx, cy - sdist * ny, cz - sdist * nz   # 圆心 = 球心在平面上的投影
    u, v, _n = _frame_from_axis([nx, ny, nz])
    return schemas.circle3d(ox, oy, oz, rr, [nx, ny, nz], u, v)

def _ix_solid_solid(s1, s2):
    """两个凸立体求交 → 凸多面体（半空间裁剪）。"""
    verts = [list(v) for v in s1.data["verts"]]
    faces = [list(f) for f in s1.data["faces"]]
    for pl in _solid_planes(s1) + _solid_planes(s2):
        verts, faces = _clip_polyhedron(verts, faces, pl)
        if len(verts) < 4 or not faces:
            raise GeoError("两个立体的交集为空或退化为面/点")
    # 由面表恢复边表（统一用 mesh_store.edges_of，见 REVIEW 第 10 条）
    edges = mesh_store.edges_of(faces)
    if not edges:
        raise GeoError("两个立体的交集退化")
    mesh = {"verts": [list(v) for v in verts], "faces": [list(f) for f in faces], "edges": edges}
    if _mesh_volume(mesh) < COORD:
        raise GeoError("两个立体的交集退化为零体积（面/点接触）")
    return schemas.polyhedron(mesh=mesh)

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
            if bounded and (t < -COORD or t > 1 + COORD):
                continue
            ts.append(min(1.0, max(0.0, t)) if bounded else t)
    if not ts:
        raise GeoError("线段与立体无交点（整段在立体内部或外部）" if bounded else "直线与立体不相交")
    ts.sort()
    uniq = []
    for t in ts:
        if not uniq or abs(t - uniq[-1]) > LOOSE:
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
    if A < ZERO_SQ:
        raise GeoError("直线退化")
    B = 2 * (fx * dx + fy * dy + fz * dz)
    C = fx * fx + fy * fy + fz * fz - r * r
    disc = B * B - 4 * A * C
    if disc < -EPSILON:
        raise GeoError("直线与球不相交")
    disc = max(0.0, disc)
    sq = math.sqrt(disc)
    ts = [(-B - sq) / (2 * A), (-B + sq) / (2 * A)]
    ts = [t for t in ts if (not bounded) or (-COORD <= t <= 1 + COORD)]
    if not ts:
        raise GeoError("交点不在线段上")
    ts.sort()
    if len(ts) == 2 and abs(ts[0] - ts[1]) < COORD:
        ts = [ts[0]]          # 相切：判别式≈0 时两根重合，只算一个交点
    k = (idx or 1)
    if k > len(ts):
        raise GeoError("交点只有 " + str(len(ts)) + " 个（请求第 " + str(k) + " 个）")
    t = ts[k - 1]
    return {"x": p[0] + t * dx, "y": p[1] + t * dy, "z": p[2] + t * dz}

def _poly_state(verts, faces, edges):
    return schemas.polyhedron(verts, _normalize_mesh(verts, faces), edges)
