"""统计与拟合算法（从 kernel/commands.py 抽出，P2 结构拆分）。

只依赖 math / re / tolerance，不依赖命令层：
- 基本统计：_median / _mode / _variance
- 拟合状态：_fitline_state（最小二乘直线）、_fit_silent_fit（静默调用 scipy，避免 OptimizeWarning）
- 条形图：_barchart_state（解析 x(y)=v 形式的标签，引用 _REF_X/_REF_DOT）
- 3D 统计：_fitsphere_state（最小二乘球）、_fitplane_state（最小二乘平面）
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple

from .tolerance import COARSE, COORD, EPSILON

from .geo2d import _line_state

# 拟合表达式里的引用标记：x(2) 与 A.x 形式（_barchart_state 用）
_REF_X = re.compile(r"^([xyXY])\((.+)\)$")
_REF_DOT = re.compile(r"^(.+)\.([xyXY])$")

__all__ = [
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
    return {"objtype": "sphere", "solid": "sphere",
            "data": {"cx": cx, "cy": cy, "cz": cz, "r": r}}

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
    return {"objtype": "plane", "solid": "plane",
            "data": {"a": nx, "b": ny, "c": nz, "d": dd,
                     "ax": float(ctr[0]), "ay": float(ctr[1]), "az": float(ctr[2]),
                     "ux": ux, "uy": uy, "uz": uz, "vx": vx, "vy": vy, "vz": vz,
                     "fit": True}}
