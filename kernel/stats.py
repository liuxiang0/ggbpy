"""统计与拟合算法（从 kernel/commands.py 抽出，P2 结构拆分）。

只依赖 math / re / tolerance，不依赖命令层：
- 基本统计：_median / _mode / _variance
- 拟合状态：_fitline_state（最小二乘直线）、_fit_silent_fit（静默调用 scipy，避免 OptimizeWarning）
- 条形图：_barchart_state（解析 x(y)=v 形式的标签，引用 _REF_X/_REF_DOT）
- 3D 统计：_fitsphere_state（最小二乘球）、_fitplane_state（最小二乘平面）
- 统计图状态：_linechart_state（折线）/ _scatter_state（散点）/ _dotplot_state（点图）
- 三维统计图网格：_bars3d_mesh（柱）/ _scatter3d_mesh（散点标记）/ _surface3d_mesh（高度场）
  注：统计图网格**非凸**，不能用 _normalize_mesh（其按质心判外向），面序在此手工保证外向。
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple

from . import schemas
from .elements import GeoError
from .tolerance import COARSE, COORD, EPSILON

from .geo2d import _line_state

# 拟合表达式里的引用标记：x(2) 与 A.x 形式（_barchart_state 用）
_REF_X = re.compile(r"^([xyXY])\((.+)\)$")
_REF_DOT = re.compile(r"^(.+)\.([xyXY])$")

__all__ = [
    "_linechart_state",
    "_scatter_state",
    "_dotplot_state",
    "_bars3d_mesh",
    "_scatter3d_mesh",
    "_surface3d_mesh",
    "_median",
    "_mode",
    "_variance",
    "_fit_silent_fit",
    "_fitline_state",
    "_barchart_state",
    "_fitsphere_state",
    "_fitplane_state",
]


def _median(items):
    s = sorted(items)
    n = len(s)
    if n == 0:
        return 0.0
    if n % 2 == 1:
        return float(s[n // 2])
    return float((s[n // 2 - 1] + s[n // 2]) / 2.0)

def _mode(items):
    if not items:
        return 0.0
    from collections import Counter
    c = Counter(items)
    return float(max(c, key=c.get))

def _variance(items):
    n = len(items)
    if n == 0:
        return 0.0
    m = sum(items) / n
    return float(sum((v - m) ** 2 for v in items) / n)

def _fit_silent_fit(*a, **kw):
    """curve_fit 包装：参数协方差无法估计时的 OptimizeWarning 属正常噪声，不外泄到服务日志。"""
    import warnings
    from scipy.optimize import curve_fit as _cf
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _cf(*a, **kw)

def _fitline_state(items):
    import numpy as np
    xs = np.array([p[0] for p in items])
    ys = np.array([p[1] for p in items])
    if len(xs) < 2:
        raise GeoError("至少需要两个点")
    k, b = np.polyfit(xs, ys, 1)
    return _line_state(float(-k), 1.0, float(-b))

def _barchart_state(L):
    from collections import Counter
    items = L.items
    if not items:
        raise GeoError("空列表")
    vals = sorted(set(items))
    counts = [items.count(v) for v in vals]
    width = 0.8 * (vals[1] - vals[0]) if len(vals) > 1 else 1.0
    return {"bins": vals, "counts": counts, "width": width}

def _fitsphere_state(items):
    import numpy as np
    pts = np.array([[float(p[0]), float(p[1]), float(p[2] if len(p) > 2 else 0.0)] for p in items])
    if len(pts) < 4:
        raise GeoError("FitSphere 至少需要 4 个点")
    A = np.hstack([2.0 * pts, np.ones((len(pts), 1))])
    bvec = (pts ** 2).sum(axis=1)
    sol, *_ = np.linalg.lstsq(A, bvec, rcond=None)
    cx, cy, cz, dd = (float(v) for v in sol)
    r2 = dd + cx * cx + cy * cy + cz * cz
    if r2 <= EPSILON:
        raise GeoError("球拟合退化（点云过于集中）")
    r = math.sqrt(r2)
    # 残差检查：偏离球面过大说明点云不共球
    dev = float(np.max(np.abs(np.linalg.norm(pts - np.array([cx, cy, cz]), axis=1) - r)))
    if dev > COARSE * max(1.0, r):
        raise GeoError("点云不共球（最大偏差 %.6g）" % dev)
    return schemas.sphere(cx, cy, cz, r)

def _fitplane_state(items):
    import numpy as np
    pts = np.array([[float(p[0]), float(p[1]), float(p[2] if len(p) > 2 else 0.0)] for p in items])
    if len(pts) < 3:
        raise GeoError("FitPlane 至少需要 3 个点")
    ctr = pts.mean(axis=0)
    q = pts - ctr
    cov = q.T @ q
    w, v = np.linalg.eigh(cov)        # 升序：w[0] ≤ w[1] ≤ w[2]
    if w[2] <= EPSILON:
        raise GeoError("点云重合，无法确定平面")
    if w[1] <= COORD * w[2]:
        raise GeoError("点云共线（秩 1），无法确定平面")
    nrm = v[:, 0]                     # 最小特征值对应法向
    ln = float(np.linalg.norm(nrm))
    if ln < EPSILON:
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
    return schemas.plane(nx, ny, nz, dd, float(ctr[0]), float(ctr[1]), float(ctr[2]),
                         ux, uy, uz, vx, vy, vz, fit=True)


# ---------------------------------------------------------------------------
# 统计图状态（LineChart / ScatterPlot / DotPlot）
# ---------------------------------------------------------------------------

def _linechart_state(el, d):
    """折线图状态：单序列（x 默认 1..n）或 x/y 双序列。

    注意：必须**返回**完整状态（而不是只改元素属性后返回 {}）——计算记忆命中时
    只会 apply_state(缓存字典)，不会再调用本函数，否则新元素的数据会空。
    """
    if not d:
        return {}
    if len(d) == 1:
        ys = [float(v) for v in d[0].items]
        xs = [float(i + 1) for i in range(len(ys))]
    else:
        xs = [float(v) for v in d[0].items]
        ys = [float(v) for v in d[1].items]
    if not xs or len(xs) != len(ys):
        raise GeoError("LineChart 的 x/y 序列长度须相同且非空")
    return {"xs": xs, "ys": ys}


def _scatter_state(el, d):
    """散点图状态：d[0] 为点列表（取前两维）或数值列表（x 用序号）。"""
    if not d:
        return {}
    src = d[0]
    if getattr(src, "itemkind", "") in ("number", "angle"):
        return {"pts": [[float(i + 1), float(v)] for i, v in enumerate(src.items)]}
    pts = []
    for p in src.items:
        if p is None or len(p) < 2:
            raise GeoError("ScatterPlot 需要点列表")
        pts.append([float(p[0]), float(p[1])])
    return {"pts": pts}


def _dotplot_state(el, d):
    """点图状态：同一取值重复出现时向上叠点（值相同 → 同一列）。"""
    if not d:
        return {}
    vals = sorted(float(v) for v in d[0].items)
    stacks = []
    for v in vals:
        level = 0
        while any(abs(sx - v) <= COORD and sl == level for sx, sl in stacks):
            level += 1
        stacks.append([v, level])
    return {"values": vals, "stacks": stacks}


# ---------------------------------------------------------------------------
# 三维统计图网格（非凸：面序手工保证外向）
# ---------------------------------------------------------------------------

def _box_faces(verts, x0, x1, y0, y1, z0, z1):
    """向 verts 追加一个轴对齐长方体（8 顶点），返回 6 个外向面（CCW）。"""
    b = len(verts)
    verts.extend([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])
    return [[b + 0, b + 3, b + 2, b + 1],   # 底 (−z)
            [b + 4, b + 5, b + 6, b + 7],   # 顶 (+z)
            [b + 0, b + 1, b + 5, b + 4],   # 前 (−y)
            [b + 1, b + 2, b + 6, b + 5],   # 右 (+x)
            [b + 2, b + 3, b + 7, b + 6],   # 后 (+y)
            [b + 3, b + 0, b + 4, b + 7]]   # 左 (−x)


def _bars3d_mesh(values, bar: float = 0.7, depth: float = 0.7, gap: float = 1.0):
    """柱状图网格：第 i 根柱高 values[i]，底边放在 z=0、类别轴 x、进深 y。"""
    verts, faces = [], []
    for i, v in enumerate(values):
        h = float(v)
        if h < 0:
            raise GeoError("BarChart3D 需要非负数据")
        x0 = i * gap
        faces.extend(_box_faces(verts, x0, x0 + bar, 0.0, depth, 0.0, h))
    return verts, faces


def _scatter3d_mesh(points, r: float = 0.12):
    """散点图网格：每个三维点放一个正八面体标记（6 顶点 / 8 面，外向）。"""
    verts, faces = [], []
    for x, y, z in points:
        b = len(verts)
        verts.extend([[x + r, y, z], [x - r, y, z], [x, y + r, z],
                      [x, y - r, z], [x, y, z + r], [x, y, z - r]])
        faces.extend([[b + 0, b + 2, b + 4], [b + 2, b + 1, b + 4],
                      [b + 1, b + 3, b + 4], [b + 3, b + 0, b + 4],
                      [b + 2, b + 0, b + 5], [b + 1, b + 2, b + 5],
                      [b + 3, b + 1, b + 5], [b + 0, b + 3, b + 5]])
    return verts, faces


def _surface3d_mesh(values, cols: int, cell: float = 1.0):
    """三维高度场网格：values 按行优先展开为 rows×cols 的 z 值。"""
    if cols < 2:
        raise GeoError("SurfaceChart3D 的列数须 ≥ 2")
    rows = int(math.ceil(len(values) / float(cols)))
    if rows < 2:
        raise GeoError("SurfaceChart3D 需要至少两行数据")
    verts = []
    for i in range(rows):
        for j in range(cols):
            k = i * cols + j
            z = float(values[k]) if k < len(values) else 0.0
            verts.append([j * cell, i * cell, z])
    faces = []
    for i in range(rows - 1):
        for j in range(cols - 1):
            a = i * cols + j
            faces.append([a, a + 1, a + cols + 1, a + cols])
    return verts, faces
