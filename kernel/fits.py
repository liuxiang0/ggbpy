"""拟合与相关命令（指数/对数/多项式/幂/正弦拟合、PMCC、协方差椭球，P2 结构拆分）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .cmd_util import _list_arg, _mk, label_of
from .stats import _fit_silent_fit
from .elements import Geo3D, GeoError, GeoFunction, GeoNumber
from .tolerance import COORD, EPSILON
from .parser import eval_number
from . import schemas


__all__ = [
    "_cmd_cov_ellipsoid",
    "_cov_ellipsoid_state",
    "_cmd_pmcc",
    "_cmd_fitpoly",
    "_fit_cmd",
    "_cmd_fitexp",
    "_cmd_fitlog",
    "_cmd_fitpow",
    "_cmd_fitsin",
]


def _cmd_cov_ellipsoid(cons, defn, args):
    """CovarianceEllipsoid[点列表, 倍数?]：协方差椭球（特征向量为轴，半轴 = k√λ）。"""
    if len(args) not in (1, 2):
        raise GeoError("CovarianceEllipsoid 需要点列表[, 倍数]")
    L = _list_arg(cons, args[0])
    if L.itemkind not in ("point", "point3d"):
        raise GeoError("CovarianceEllipsoid 需要三维点列表")
    k = eval_number(cons, args[1]) if len(args) == 2 else 2.0
    return _mk(cons, Geo3D, "geo3d", defn, [L], lambda d: _cov_ellipsoid_state(d[0].items, k))

def _cov_ellipsoid_state(items, k):
    import numpy as np
    if len(items) < 2:
        raise GeoError("协方差椭球至少需要两个点")
    pts = np.array([[float(p[0]), float(p[1]), float(p[2] if len(p) > 2 else 0.0)] for p in items])
    ctr = pts.mean(axis=0)
    q = pts - ctr
    cov = (q.T @ q) / len(pts)
    w, v = np.linalg.eigh(cov)          # 升序：w[i] 对应 v[:,i]
    axes = [float(k) * math.sqrt(max(0.0, float(w[i]))) for i in range(3)]
    if max(axes) < EPSILON:
        raise GeoError("点云退化（方差为 0），无法构成椭球")
    n = 20
    verts, faces, edges = [], [], []
    for j in range(n + 1):
        phi = math.pi * j / n
        for i in range(n + 1):
            th = 2 * math.pi * i / n
            u = [math.sin(phi) * math.cos(th), math.sin(phi) * math.sin(th), math.cos(phi)]
            p = [float(ctr[t]) for t in range(3)]
            for a in range(3):
                coef = axes[a] * sum(u[b] * float(v[b, a]) for b in range(3))
                for t in range(3):
                    p[t] += coef * float(v[t, a])
            verts.append(p)

    def vid(i, j):
        return j * (n + 1) + i

    for j in range(n):
        for i in range(n):
            faces.append([vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)])
            edges.append([vid(i, j), vid(i + 1, j)])
            edges.append([vid(i, j), vid(i, j + 1)])
    return schemas.surface(verts, faces, edges, n,
                           center=[float(c) for c in ctr], axes=axes)

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
            p0 = [(ys.max() - ys.min()) / 2, 2 * np.pi / max(xs.max() - xs.min(), COORD), 0, ys.mean()]
            popt, _ = _fit_silent_fit(model, xs, ys, p0=p0, maxfev=20000)
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
