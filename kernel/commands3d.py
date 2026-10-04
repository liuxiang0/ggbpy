"""三维命令（P2 结构拆分：从 commands.py 抽出）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .cmd_util import _elem_or_point, _is_segment_el, _list_arg, _lookup, _mk, _num_deps, _point_arg, _resolve, _tuple_parts_any, label_of
from .stats import _fitplane_state, _fitsphere_state
from .geometry3d import _frame_from_axis, _normalize_mesh, _poly_state, _solid_area, _solid_volume, _tag3d, _z_of
from .solids import _cone_apex_center_radius_state, _cone_from_circle_state, _cone_state, _cube_from_edge, _cube_from_poly, _cube_seg_pts, _cube_state, _cube_state2, _cylinder_centers_radius_state, _cylinder_from_circle_state, _cylinder_state, _dodecahedron_state, _hexahedron_state, _icosahedron_state, _octahedron_state, _prism_state, _pyramid_state, _sphere_state, _sphere_state_fixed, _sphere_state_r, _tetrahedron_state, _with_analytic
from .elements import Geo3D, GeoError, GeoMatrix, GeoNumber, GeoPoint
from .tolerance import COARSE, COORD, EPSILON, OPT_FATOL, OPT_XATOL, TIGHT
from . import mesh_store
from . import schemas
from .parser import eval_number


__all__ = [
    "_cmd_bbox",
    "_bbox_state",
    "_cmd_covariance",
    "_cmd_convexhull",
    "_convexhull_state",
    "_surface_eval",
    "_cmd_surfacepoint",
    "_surfacepoint_state",
    "_cmd_surfaceproject",
    "_surfaceproject_state",
    "_cmd_fitsphere",
    "_polygon_area",
    "_cmd_area",
    "_cmd_volume",
    "_cmd_surface",
    "_surface_compute",
    "_cmd_mesh",
    "_cmd_surface_param",
    "_surface_param_compute",
    "_cmd_implicit_surface",
    "_implicit_surface_compute",
    "_cmd_fitplane",
    "_cmd_sphere",
    "_cmd_plane",
    "_plane_state",
    "_cmd_cube",
    "_poly3_points",
    "_poly_register",
    "_number_arg",
    "_vector3_arg",
    "_infinite_cone_state",
    "_cmd_cone",
    "_cmd_cylinder",
    "_cmd_prism",
    "_cmd_pyramid",
    "_cmd_tetrahedron",
    "_cmd_octahedron",
    "_cmd_hexahedron",
    "_cmd_icosahedron",
    "_cmd_dodecahedron",
]


def _cmd_bbox(cons, defn, args):
    """BoundingBox[点列表]：点云轴对齐包围盒（8 顶点/6 面/12 棱，可求体积/面积）。"""
    if len(args) != 1:
        raise GeoError("BoundingBox 需要三维点列表")
    L = _list_arg(cons, args[0])
    if L.itemkind not in ("point", "point3d"):
        raise GeoError("BoundingBox 需要点列表")
    return _mk(cons, Geo3D, "geo3d", defn, [L], lambda d: _bbox_state(d[0].items))

def _bbox_state(items):
    import numpy as np
    if not items:
        raise GeoError("点列表为空")
    pts = np.array([[float(p[0]), float(p[1]), float(p[2] if len(p) > 2 else 0.0)] for p in items])
    lo = pts.min(axis=0)
    hi = pts.max(axis=0)
    if bool(np.all(hi - lo < EPSILON)):
        raise GeoError("点云退化为一点，无法构成包围盒")
    corners = [[float(lo[0]) if i & 1 == 0 else float(hi[0]),
                float(lo[1]) if i & 2 == 0 else float(hi[1]),
                float(lo[2]) if i & 4 == 0 else float(hi[2])] for i in range(8)]
    faces = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 1, 5, 4], [1, 3, 7, 5], [3, 2, 6, 7], [2, 0, 4, 6]]
    edges = [[0, 1], [1, 3], [3, 2], [2, 0], [4, 5], [5, 7], [7, 6], [6, 4],
             [0, 4], [1, 5], [3, 7], [2, 6]]
    return schemas.polyhedron(corners, _normalize_mesh(corners, faces), edges, solid="box",
                              lo=[float(v) for v in lo], hi=[float(v) for v in hi])

def _cmd_covariance(cons, defn, args):
    """Covariance[点列表]：总体协方差矩阵（二维列表 → 2×2，三维列表 → 3×3）。"""
    if len(args) != 1:
        raise GeoError("Covariance 需要点列表")
    L = _list_arg(cons, args[0])
    if L.itemkind not in ("point", "point3d"):
        raise GeoError("Covariance 需要点列表")
    three = L.itemkind == "point3d"

    def fn(d):
        import numpy as np
        items = d[0].items
        if len(items) < 2:
            raise GeoError("Covariance 至少需要两个点")
        if three:
            pts = np.array([[float(p[0]), float(p[1]), float(p[2])] for p in items])
        else:
            pts = np.array([[float(p[0]), float(p[1])] for p in items])
        q = pts - pts.mean(axis=0)
        return {"data": (q.T @ q) / len(pts)}
    return _mk(cons, GeoMatrix, "matrix", defn, [L], fn)

def _cmd_convexhull(cons, defn, args):
    """ConvexHull[点列表]：三维点云凸包（scipy Qhull），输出可渲染/可求体积的凸多面体。"""
    if len(args) != 1:
        raise GeoError("ConvexHull 需要三维点列表")
    L = _list_arg(cons, args[0])
    if L.itemkind not in ("point", "point3d"):
        raise GeoError("ConvexHull 需要三维点列表")
    return _mk(cons, Geo3D, "geo3d", defn, [L], lambda d: _convexhull_state(d[0].items))

def _convexhull_state(items):
    import numpy as np
    from scipy.spatial import ConvexHull, QhullError
    if len(items) < 4:
        raise GeoError("三维凸包至少需要 4 个点")
    pts = np.array([[float(p[0]), float(p[1]), float(p[2] if len(p) > 2 else 0.0)] for p in items])
    try:
        hull = ConvexHull(pts)
    except QhullError as e:
        raise GeoError("点云退化（共面/共线/重合），无法构成三维凸包：" + str(e)[:60])
    keep = [int(i) for i in hull.vertices]
    remap = {old: k for k, old in enumerate(keep)}
    verts = [[float(pts[i][0]), float(pts[i][1]), float(pts[i][2])] for i in keep]
    faces = []
    for tri in hull.simplices:
        f = [remap[int(tri[0])], remap[int(tri[1])], remap[int(tri[2])]]
        if f not in faces:
            faces.append(f)
    edges = mesh_store.edges_of(faces)      # 统一派生（REVIEW 第 10 条：不再内联去重循环）
    return schemas.polyhedron(verts, _normalize_mesh(verts, faces), edges, solid="hull",
                              points=int(len(pts)))

def _surface_eval(d):
    """由曲面 data 构造 (x,y,z) 求值函数 + 参数域 + 参数名。"""
    import sympy
    if d.get("param"):
        xb, yb, zb, sname, tname, smin, smax, tmin, tmax = d["param"]
        su, tu = sympy.symbols(sname + " " + tname)
        loc = {sname: su, tname: tu, "pi": sympy.pi, "e": sympy.E}
        fns = [sympy.lambdify((su, tu), sympy.sympify(b.replace("^", "**"), locals=loc), "numpy")
               for b in (xb, yb, zb)]

        def f(u, v):
            out = []
            for fn in fns:
                val = fn(u, v)
                out.append(float(val) if not hasattr(val, "__len__") else float(val[0]))
            return out
        return f, [(smin, smax), (tmin, tmax)], (sname, tname)
    if d.get("expr"):
        xmin, xmax, ymin, ymax = d["ranges"]
        pf = sympy.lambdify(sympy.symbols("x y"),
                            sympy.sympify(str(d["expr"]).replace("^", "**"),
                                          locals={"pi": sympy.pi, "e": sympy.E}), "numpy")

        def f(u, v):
            z = pf(u, v)
            z = float(z) if not hasattr(z, "__len__") else float(z[0])
            return [float(u), float(v), z]
        return f, [(xmin, xmax), (ymin, ymax)], ("x", "y")
    raise GeoError("该曲面不支持参数取点（需要 Surface / SurfaceParam）")

def _cmd_surfacepoint(cons, defn, args):
    """SurfacePoint[曲面, u, v]：曲面在给定参数处的点（三维点）。"""
    if len(args) != 3:
        raise GeoError("SurfacePoint 需要 曲面, u, v")
    surf = _resolve(cons, args[0], ("geo3d",))
    u = eval_number(cons, args[1])
    v = eval_number(cons, args[2])
    return _mk(cons, GeoPoint, "point", defn, [surf], lambda d: _surfacepoint_state(d[0], u, v))

def _surfacepoint_state(surf, u, v):
    f, dom, names = _surface_eval(surf.data or {})
    for k, (lo, hi) in enumerate(dom):
        val = u if k == 0 else v
        if not (lo - COORD <= val <= hi + COORD):
            raise GeoError("参数 %s=%s 超出定义域 [%s, %s]" % (names[k], val, lo, hi))
    p = f(u, v)
    if not all(math.isfinite(c) for c in p):
        raise GeoError("该参数处取值非有限（可能为奇点）")
    return {"x": p[0], "y": p[1], "z": p[2]}

def _cmd_surfaceproject(cons, defn, args):
    """SurfaceProject[点, 曲面]：点在曲面上的最近点（数值最小化）。"""
    if len(args) != 2:
        raise GeoError("SurfaceProject 需要 点, 曲面")
    pt = _point_arg(cons, args[0])
    surf = _resolve(cons, args[1], ("geo3d",))
    return _mk(cons, GeoPoint, "point", defn, [pt, surf],
               lambda d: _surfaceproject_state(d[0], d[1]))

def _surfaceproject_state(pt, surf):
    import numpy as np
    from scipy.optimize import minimize
    f, dom, _names = _surface_eval(surf.data or {})
    target = np.array([pt.x, pt.y, _z_of(pt)])

    def dist2(x):
        p = np.array(f(float(x[0]), float(x[1])))
        if not np.all(np.isfinite(p)):
            return 1e12
        return float(np.sum((p - target) ** 2))

    best = None
    lo0, hi0 = dom[0]
    lo1, hi1 = dom[1]
    for i in range(9):
        for j in range(9):
            u = lo0 + (hi0 - lo0) * i / 8.0
            v = lo1 + (hi1 - lo1) * j / 8.0
            d0 = dist2((u, v))
            if best is None or d0 < best[0]:
                best = (d0, u, v)
    res = minimize(dist2, [best[1], best[2]], method="Nelder-Mead",
                   options={"xatol": OPT_XATOL, "fatol": OPT_FATOL, "maxiter": 800})
    u, v = float(res.x[0]), float(res.x[1])
    u = min(max(u, lo0), hi0)
    v = min(max(v, lo1), hi1)
    p = f(u, v)
    if not all(math.isfinite(c) for c in p):
        raise GeoError("最近点求解失败（曲面在该处奇异）")
    return {"x": p[0], "y": p[1], "z": p[2]}

def _cmd_fitsphere(cons, defn, args):
    """FitSphere[点列表]：最小二乘球拟合（代数拟合，需 ≥4 点）。"""
    if len(args) != 1:
        raise GeoError("FitSphere 需要三维点列表，如 {(0,0,0),(2,0,0),(0,2,0),(0,0,2)}")
    L = _list_arg(cons, args[0])
    if L.itemkind not in ("point", "point3d"):
        raise GeoError("FitSphere 需要三维点列表")
    return _mk(cons, Geo3D, "geo3d", defn, [L], lambda d: _fitsphere_state(d[0].items))

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
        except Exception as ex:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
            raise GeoError("曲面表达式无法求值：" + str(ex)[:80])
        return schemas.surface(verts, faces, edges, n, expr=expr,
                               ranges=[xmin, xmax, ymin, ymax])
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
             lambda d: schemas.polyhedron(solid="mesh", mesh=data))
    el.meshid = mid
    return el

def _cmd_surface_param(cons, defn, args):
    """SurfaceParam[x(s,t), y(s,t), z(s,t), s, t, smin, smax, tmin, tmax, 网格数?]

    参数曲面 → (n+1)² 网格；表达式可引用滑块。
    """
    if len(args) not in (9, 10):
        raise GeoError("SurfaceParam 需要 x(s,t), y(s,t), z(s,t), s, t, smin, smax, tmin, tmax[, 网格数]")
    xb, yb, zb, sname, tname = args[0], args[1], args[2], args[3].strip(), args[4].strip()
    for nm in (sname, tname):
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", nm):
            raise GeoError("非法参数名: " + nm)
    if sname == tname:
        raise GeoError("两个参数名不能相同")
    smin, smax = eval_number(cons, args[5]), eval_number(cons, args[6])
    tmin, tmax = eval_number(cons, args[7]), eval_number(cons, args[8])
    n = int(eval_number(cons, args[9])) if len(args) == 10 else 24
    if smax <= smin or tmax <= tmin:
        raise GeoError("SurfaceParam 的范围需满足 max > min")
    n = max(2, min(n, 96))
    el = Geo3D(label_of(defn), defn)
    el.objtype = "polyhedron"
    el.solid = "surface"
    el.set_deps(_num_deps(cons, defn),
                _surface_param_compute(xb, yb, zb, sname, tname, smin, smax, tmin, tmax, n))
    return cons.add(el)

def _surface_param_compute(xb, yb, zb, sname, tname, smin, smax, tmin, tmax, n):
    import sympy

    def fn(deps):
        vals = {d.label: d.value for d in deps if hasattr(d, "value")}
        try:
            su, tu = sympy.symbols(sname + " " + tname)
            loc = {**vals, "pi": sympy.pi, "e": sympy.E, sname: su, tname: tu}
            fns = [sympy.lambdify((su, tu), sympy.sympify(b.replace("^", "**"), locals=loc), "numpy")
                   for b in (xb, yb, zb)]
            verts, faces, edges = [], [], []
            for j in range(n + 1):
                tv = tmin + (tmax - tmin) * j / n
                for i in range(n + 1):
                    sv = smin + (smax - smin) * i / n
                    p = []
                    for f in fns:
                        v = f(sv, tv)
                        v = float(v) if not hasattr(v, "__len__") else float(v[0])
                        if not math.isfinite(v):
                            raise GeoError("参数曲面在 (%.3f,%.3f) 取值非有限" % (sv, tv))
                        p.append(v)
                    verts.append(p)
        except GeoError:
            raise
        except Exception as ex:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
            raise GeoError("参数曲面表达式无法求值：" + str(ex)[:80])

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
        return schemas.surface(verts, faces, edges, n,
                               param=[xb, yb, zb, sname, tname, smin, smax, tmin, tmax])
    return fn

def _cmd_implicit_surface(cons, defn, args):
    """ImplicitSurface[f(x,y,z)=0, xmin, xmax, ymin, ymax, zmin, zmax, 分辨率?]

    marching tetrahedra 抽取等值面 → 三角网格（solid=surface）。
    """
    if len(args) not in (7, 8):
        raise GeoError("ImplicitSurface 需要 f(x,y,z)=0, xmin, xmax, ymin, ymax, zmin, zmax[, 分辨率]")
    expr = args[0]
    if "=" in expr:
        lhs, rhs = expr.split("=", 1)
        expr = "(" + lhs + ")-(" + rhs + ")"
    xmin, xmax = eval_number(cons, args[1]), eval_number(cons, args[2])
    ymin, ymax = eval_number(cons, args[3]), eval_number(cons, args[4])
    zmin, zmax = eval_number(cons, args[5]), eval_number(cons, args[6])
    n = int(eval_number(cons, args[7])) if len(args) == 8 else 20
    if xmax <= xmin or ymax <= ymin or zmax <= zmin:
        raise GeoError("ImplicitSurface 的范围需满足 max > min")
    n = max(4, min(n, 48))     # 分辨率上限：n=48 实测约 3 s，再大就不可交互
    el = Geo3D(label_of(defn), defn)
    el.objtype = "polyhedron"
    el.solid = "surface"
    el.set_deps(_num_deps(cons, defn),
                _implicit_surface_compute(expr, xmin, xmax, ymin, ymax, zmin, zmax, n))
    return cons.add(el)

def _implicit_surface_compute(expr, xmin, xmax, ymin, ymax, zmin, zmax, n):
    import sympy
    import numpy as np
    import time as _time

    import os as _os
    _t0 = _time.time()
    # 单个等值面抽取的时间预算（秒），超时给出可操作错误而不是长时间卡住；测试可用环境变量收紧
    try:
        _budget = float(_os.environ.get("GGBPY_IMPLICIT_BUDGET", "8.0"))
    except (ValueError, TypeError):  # 环境变量非法（非数字）：回退默认预算 8.0
        _budget = 8.0

    # 立方体 6 个四面体（沿主对角线 0-7 的 Kuhn 分解）
    TETRA = [(0, 1, 3, 7), (0, 3, 2, 7), (0, 2, 6, 7), (0, 6, 4, 7), (0, 4, 5, 7), (0, 5, 1, 7)]

    def fn(deps):
        vals = {d.label: d.value for d in deps if hasattr(d, "value")}
        try:
            xs_, ys_, zs_ = sympy.symbols("x y z")
            loc = {**vals, "pi": sympy.pi, "e": sympy.E}
            f = sympy.lambdify((xs_, ys_, zs_), sympy.sympify(expr.replace("^", "**"), locals=loc), "numpy")
        except Exception as ex:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
            raise GeoError("隐式曲面表达式无法求值：" + str(ex)[:80])
        gx = [xmin + (xmax - xmin) * i / n for i in range(n + 1)]
        gy = [ymin + (ymax - ymin) * j / n for j in range(n + 1)]
        gz = [zmin + (zmax - zmin) * k / n for k in range(n + 1)]
        X, Y, Z = np.meshgrid(gx, gy, gz, indexing="ij")
        try:
            F = np.asarray(f(X, Y, Z), dtype=float)
        except Exception as ex:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
            raise GeoError("隐式曲面取值失败：" + str(ex)[:80])
        if not np.all(np.isfinite(F)):
            raise GeoError("隐式曲面在该范围内取值非有限（可能存在奇点）")

        verts = []
        vindex = {}

        def _vid(p):
            key = (round(p[0], 7), round(p[1], 7), round(p[2], 7))
            i = vindex.get(key)
            if i is None:
                i = len(verts)
                vindex[key] = i
                verts.append([p[0], p[1], p[2]])
            return i

        def _corner(i, j, k):
            return np.array([gx[i], gy[j], gz[k]])

        faces = []
        for i in range(n):
            if _time.time() - _t0 > _budget:
                raise GeoError("隐式曲面计算量过大（超过 %.0f 秒）：请降低分辨率 n（当前 %d）或缩小范围"
                               % (_budget, n))
            for j in range(n):
                for k in range(n):
                    corners = {}
                    for di in (0, 1):
                        for dj in (0, 1):
                            for dk in (0, 1):
                                idx = di + 2 * dj + 4 * dk
                                corners[idx] = (_corner(i + di, j + dj, k + dk), F[i + di, j + dj, k + dk])
                    for t in TETRA:
                        pts = [corners[c] for c in t]
                        inside = [p[1] < 0 for p in pts]
                        cnt = sum(inside)
                        if cnt == 0 or cnt == 4:
                            continue
                        segs = []
                        for a in range(4):
                            for b in range(a + 1, 4):
                                if inside[a] != inside[b]:
                                    pa, fa = pts[a]
                                    pb, fb = pts[b]
                                    tt = fa / (fa - fb)
                                    segs.append(pa + tt * (pb - pa))
                        if cnt == 1 or cnt == 3:
                            if len(segs) >= 3:
                                faces.append([_vid(segs[0]), _vid(segs[1]), _vid(segs[2])])
                        else:
                            if len(segs) >= 4:
                                faces.append([_vid(segs[0]), _vid(segs[1]), _vid(segs[2])])
                                faces.append([_vid(segs[0]), _vid(segs[2]), _vid(segs[3])])
        if not faces:
            raise GeoError("该范围内没有 f=0 的等值面（请扩大范围或调整分辨率）")
        # 朝向：法向指向 f 增大方向（外部）
        eps = COARSE * max(xmax - xmin, ymax - ymin, zmax - zmin)
        fixed = []
        for f3 in faces:
            a, b, c = (np.array(verts[i]) for i in f3)
            nvec = np.cross(b - a, c - a)
            ln = float(np.linalg.norm(nvec))
            if ln < TIGHT:
                continue
            nvec = nvec / ln
            try:
                f_plus = float(f(*(a + eps * nvec)))
                f_minus = float(f(*(a - eps * nvec)))
            except Exception:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
                fixed.append(list(f3))
                continue
            fixed.append(list(f3) if f_plus > f_minus else [f3[0], f3[2], f3[1]])
        edges = set()
        for f3 in fixed:
            for m in range(3):
                p, q = f3[m], f3[(m + 1) % 3]
                edges.add((min(p, q), max(p, q)))
        return schemas.surface([list(v) for v in verts], fixed,
                               [[a, b] for a, b in sorted(edges)], n)
    return fn

def _cmd_fitplane(cons, defn, args):
    """FitPlane[点列表]：三维点云最小二乘拟合平面（法向 = 协方差最小特征向量）。"""
    if len(args) != 1:
        raise GeoError("FitPlane 需要点列表，如 {(0,0,0),(1,0,0),(0,1,1),(1,1,1)}")
    L = _list_arg(cons, args[0])
    if L.itemkind not in ("point", "point3d"):
        raise GeoError("FitPlane 需要点列表（三维点，如 {(0,0,0),(1,0,0),(0,1,1)}）")
    return _mk(cons, Geo3D, "geo3d", defn, [L], lambda d: _fitplane_state(d[0].items))

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
    if ln < EPSILON:
        raise GeoError("三点共线，无法确定平面")
    nx, ny, nz = n[0] / ln, n[1] / ln, n[2] / ln
    dd = -(nx * ax + ny * ay + nz * az)
    return schemas.plane(nx, ny, nz, dd, ax, ay, az, ux, uy, uz, vx, vy, vz)

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
        ok3 = (abs(d01 - d02) < COORD and d01 < d12) or               (abs(d01 - d12) < COORD and d01 < d02) or               (abs(d02 - d12) < COORD and d02 < d01)
        if not ok3:
            raise GeoError("Cube 三点需构成正方形底面（两点距离相等为边）")
        return _mk(cons, Geo3D, "geo3d", defn, [a, b, c], lambda d: _cube_state(d[0], d[1], d[2]))
    raise GeoError("Cube 需要 两点 / 三点 / 线段 / 线段+点 / 正方形")

def _poly3_points(cons, args, n, name):
    if len(args) != n:
        raise GeoError(name + " 需要 " + str(n) + " 个点")
    return [_point_arg(cons, a) for a in args]

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

def _cmd_prism(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Prism")
    return _poly_register(cons, defn, [a, b, c], lambda d: _prism_state(d[0], d[1], d[2]), "prism")

def _cmd_pyramid(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Pyramid")
    return _poly_register(cons, defn, [a, b, c], lambda d: _pyramid_state(d[0], d[1], d[2]), "pyramid")

def _cmd_tetrahedron(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Tetrahedron")
    return _poly_register(cons, defn, [a, b, c], lambda d: _tetrahedron_state(d[0], d[1], d[2]), "tetrahedron")

def _cmd_octahedron(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Octahedron")
    return _poly_register(cons, defn, [a, b, c], lambda d: _octahedron_state(d[0], d[1], d[2]), "octahedron")

def _cmd_hexahedron(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Hexahedron")
    return _poly_register(cons, defn, [a, b, c], lambda d: _hexahedron_state(d[0], d[1], d[2]), "hexahedron")

def _cmd_icosahedron(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Icosahedron")
    return _poly_register(cons, defn, [a, b, c], lambda d: _icosahedron_state(d[0], d[1], d[2]), "icosahedron")

def _cmd_dodecahedron(cons, defn, args):
    a, b, c = _poly3_points(cons, args, 3, "Dodecahedron")
    return _poly_register(cons, defn, [a, b, c], lambda d: _dodecahedron_state(d[0], d[1], d[2]), "dodecahedron")
