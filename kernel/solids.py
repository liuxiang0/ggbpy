"""立体构造数学（从 kernel/commands.py 抽出，P2 结构拆分）。

只依赖 math / numpy 与 elements（GeoError），不依赖命令层：
立方体（边/多边形构造、两种状态）、正多面体（正四/六/八/十二/二十面体）、
棱柱/棱锥、圆锥/圆柱（圆心+半径 / 圆 / 轴向网格）、球（多种参数形式）、
正交基（_ortho_frame）与解析元数据标注（_with_analytic）。
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from . import schemas
from .elements import GeoError
# 与几何算法层的共用件（网格规范化/多面体状态/正交基）
from .geometry3d import _frame_from_axis, _normalize_mesh, _poly_state
from .tolerance import EPSILON, COORD, COARSE  # 统一数值容差（见 kernel/tolerance.py）

_PHI = (1.0 + 5.0 ** 0.5) / 2.0      # 黄金比（正十二面体/正二十面体用）

__all__ = [
    "_sphere_check",
    "_sphere_state",
    "_sphere_state_r",
    "_sphere_state_fixed",
    "_cube_seg_pts",
    "_cube_from_edge",
    "_cube_from_poly",
    "_cube_build",
    "_cube_state",
    "_cube_state2",
    "_ortho_frame",
    "_with_analytic",
    "_cone_mesh_axis",
    "_cone_from_circle_state",
    "_cone_apex_center_radius_state",
    "_cone_state",
    "_cyl_mesh_axis",
    "_cylinder_from_circle_state",
    "_cylinder_centers_radius_state",
    "_cylinder_state",
    "_prism_state",
    "_pyramid_state",
    "_tetrahedron_state",
    "_regular_polyhedron",
    "_octahedron_state",
    "_hexahedron_state",
    "_icosahedron_state",
    "_dodecahedron_state",
]


def _sphere_check(r):
    if r <= EPSILON:
        raise GeoError("球半径需为正")
    return r

def _sphere_state(c, p):
    r = math.sqrt((p.x - c.x) ** 2 + (p.y - c.y) ** 2 + ((p.z or 0) - (c.z or 0)) ** 2)
    return schemas.sphere(c.x, c.y, c.z or 0, _sphere_check(r))

def _sphere_state_r(c, r):
    return schemas.sphere(c.x, c.y, c.z or 0, _sphere_check(r.value))

def _sphere_state_fixed(c, r):
    return schemas.sphere(c.x, c.y, c.z or 0, _sphere_check(r))

def _cube_seg_pts(el):
    """取线段两端点（3D 元组），支持 2D 线段与 3D 线段。"""
    if el.kind == "segment":
        return (el.x1, el.y1, 0.0), (el.x2, el.y2, 0.0)
    if el.kind == "geo3d" and getattr(el, "objtype", "") == "segment":
        d = el.data
        return ((d.get("x1", 0.0), d.get("y1", 0.0), d.get("z1", 0.0)),
                (d.get("x2", 0.0), d.get("y2", 0.0), d.get("z2", 0.0)))
    raise GeoError("需要一个线段对象")

def _cube_from_edge(p1, p2, dirpt=None):
    """由一条棱 p1→p2 构建立方体；dirpt 为相邻顶点方向（可选，缺省系统自选）。

    - 2D 线段且未给方向点：底面在 xy 平面、AB 垂直方向补全，向 +z 挤出（与 Cube[A,B] 一致）；
    - 其它情况：把方向点（或 z 轴）对 AB 取垂直分量并缩放到边长，得到相邻棱方向。
    """
    u = [p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]]
    L = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
    if L < EPSILON:
        raise GeoError("线段退化，无法构建立方体")
    n = [u[0] / L, u[1] / L, u[2] / L]
    # 经典 2D 情形
    if dirpt is None and abs(p1[2]) < EPSILON and abs(p2[2]) < EPSILON:
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
    if lv < COORD:
        # 方向与棱共线：换参考轴
        ref = [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0]
        dot2 = ref[0] * n[0] + ref[1] * n[1] + ref[2] * n[2]
        v = [ref[0] - dot2 * n[0], ref[1] - dot2 * n[1], ref[2] - dot2 * n[2]]
        lv = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
        if lv < EPSILON:
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
    if ln < EPSILON:
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
    if min(lens) < COORD:
        raise GeoError("正方形边长退化")
    if max(lens) - min(lens) > COARSE * max(lens):
        raise GeoError("Cube[正方形] 的四边形边长不等，不是正方形")
    if abs(_dot(e[0], e[1])) > COARSE * (lens[0] * lens[1]):
        raise GeoError("Cube[正方形] 的相邻边不垂直，不是正方形")
    u, v = e[0], e[1]
    nv = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    ln = _norm(nv)
    if ln < EPSILON:
        raise GeoError("正方形退化")
    return _cube_build(pts, (nv[0] / ln, nv[1] / ln, nv[2] / ln), lens[0])

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
    return schemas.cube(verts, _normalize_mesh(verts, faces), edges)

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
    if abs(d01 - d02) < COORD and d01 < d12:
        corner = 0          # a 是角点
    elif abs(d01 - d12) < COORD and d01 < d02:
        corner = 1          # b 是角点
    elif abs(d02 - d12) < COORD and d02 < d01:
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
    if ln < EPSILON:
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
    if h < EPSILON:
        raise GeoError("两点重合，无法构成底面")
    # 底面正方形在 AB 的垂直方向补全：v = rot90(u)（xy 平面内）
    vx, vy, vz = -uy, ux, 0.0
    lv = math.sqrt(vx * vx + vy * vy)
    if lv < EPSILON:
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
    if ln < EPSILON:
        nx, ny, nz = 0.0, 0.0, 1.0
    else:
        nx, ny, nz = nx / ln, ny / ln, nz / ln
    return _cube_build(base, (nx, ny, nz), h)

def _ortho_frame(a, b, c):
    """由三点构造正交基 (u, v, n)：u 沿 B-A，v 在 ABC 平面内，n = u×v。"""
    u = [b.x - a.x, b.y - a.y, (b.z or 0) - (a.z or 0)]
    lu = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
    if lu < EPSILON:
        raise GeoError("基准两点重合，无法确定立体方向")
    u = [u[0] / lu, u[1] / lu, u[2] / lu]
    w = [c.x - a.x, c.y - a.y, (c.z or 0) - (a.z or 0)]
    n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]
    ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
    if ln < EPSILON:
        n = [0.0, 0.0, 1.0]
    else:
        n = [n[0] / ln, n[1] / ln, n[2] / ln]
    v = [n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0]]
    return u, v, n

def _with_analytic(state, **kw):
    """给网格状态附加解析参数，供 Volume/Area 取精确值（锥/柱为旋转体）。"""
    st = dict(state)
    data = dict(st.get("data", {}))
    data["analytic"] = kw
    st["data"] = data
    return st

def _cone_mesh_axis(apex, base_center, radius, N=48, cap=True):
    """由 顶点 / 底面中心 / 半径 构造有限圆锥网格（底面垂直于 顶点-底心 轴）。"""
    if radius <= EPSILON:
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
    if h <= EPSILON:
        raise GeoError("高度需为正")
    return _with_analytic(_cone_mesh_axis([cx, cy, h], [cx, cy, 0.0], r), type="cone", r=r, h=h)

def _cone_apex_center_radius_state(apex, base_center, radius):
    """Cone[顶点, 底心, 半径]。"""
    h = math.sqrt(sum((apex[i] - base_center[i]) ** 2 for i in range(3)))
    return _with_analytic(_cone_mesh_axis(apex, base_center, radius), type="cone", r=radius, h=h)

def _cone_state(a, b, c):
    """A 底面中心、B 底面半径点（半径 = |AB|）、C 顶点；底面垂直于轴 AC。"""
    r = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + ((b.z or 0) - (a.z or 0)) ** 2)
    h = math.sqrt((c.x - a.x) ** 2 + (c.y - a.y) ** 2 + ((c.z or 0) - (a.z or 0)) ** 2)
    return _with_analytic(_cone_mesh_axis([c.x, c.y, c.z or 0], [a.x, a.y, a.z or 0], r),
                          type="cone", r=r, h=h)

def _cyl_mesh_axis(base_center, axis, radius, N=48):
    """由 底面中心 / 轴向向量（长度=高）/ 半径 构造圆柱网格。"""
    if radius <= EPSILON:
        raise GeoError("半径需为正")
    h = [axis[0], axis[1], axis[2]]
    if math.sqrt(h[0] ** 2 + h[1] ** 2 + h[2] ** 2) < EPSILON:
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
    if h <= EPSILON:
        raise GeoError("高度需为正")
    return _with_analytic(_cyl_mesh_axis([cx, cy, 0.0], [0.0, 0.0, h], r), type="cylinder", r=r, h=h)

def _cylinder_centers_radius_state(base_center, top_center, radius):
    """Cylinder[底心, 顶心, 半径]。"""
    axis = [top_center[0] - base_center[0], top_center[1] - base_center[1], top_center[2] - base_center[2]]
    h = math.sqrt(sum(v * v for v in axis))
    return _with_analytic(_cyl_mesh_axis(base_center, axis, radius), type="cylinder", r=radius, h=h)

def _cylinder_state(a, b, c):
    """A 底面中心、B 底面半径点（半径 = |AB|）、C 顶面中心；底面垂直于轴 AC。"""
    r = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + ((b.z or 0) - (a.z or 0)) ** 2)
    axis = [c.x - a.x, c.y - a.y, (c.z or 0) - (a.z or 0)]
    h = math.sqrt(sum(v * v for v in axis))
    return _with_analytic(_cyl_mesh_axis([a.x, a.y, a.z or 0], axis, r), type="cylinder", r=r, h=h)

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

def _octahedron_state(a, b, c):
    u, v, n = _ortho_frame(a, b, c)
    r = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + ((b.z or 0) - (a.z or 0)) ** 2)
    unit = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]
    faces = [[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4], [0, 3, 5], [3, 1, 5], [1, 2, 5], [2, 0, 5]]
    edges = [[0, 2], [0, 4], [0, 3], [2, 1], [2, 4], [1, 4], [1, 3], [3, 4], [3, 5], [1, 5], [2, 5], [0, 5]]
    return _regular_polyhedron([a.x, a.y, a.z or 0], r, u, v, n, unit, faces, edges)

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
