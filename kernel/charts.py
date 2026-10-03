"""统计图命令（P2 结构拆分：从 commands.py 抽出）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .cmd_util import _list_arg, _lookup, _mk, _num_list_items, _num_series, label_of
from .stats import _barchart_state, _bars3d_mesh, _dotplot_state, _linechart_state, _scatter3d_mesh, _scatter_state, _surface3d_mesh
from . import schemas
from .elements import (Geo3D, GeoBarChart, GeoBoxPlot, GeoDotPlot, GeoError, GeoLineChart,
                       GeoPie, GeoScatterPlot)
from .parser import eval_number
from .tolerance import COORD, EPSILON


__all__ = [
    "_cmd_piechart",
    "_cmd_histogram",
    "_cmd_boxplot",
    "_cmd_barchart",
    "_cmd_linechart",
    "_cmd_scatterplot",
    "_cmd_dotplot",
    "_cmd_barchart3d",
    "_cmd_scatterplot3d",
    "_cmd_surfacechart3d",
    "_anon_list",
]


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
        return {"items": items, "total": tot}

    el.set_deps([L], fn)
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
    if hi - lo < EPSILON:
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
        return {"five": five, "n": n}

    el.set_deps(deps, fn)
    el.compute()
    return cons.add(el)

def _cmd_barchart(cons, defn, args):
    """BarChart[列表] / BarChart[{数值列表}] / BarChart[数据...] → 直方图（按值分类统计频数）。"""
    L = None
    if len(args) >= 1:
        raw = args[0].strip()
        cand = _lookup(cons, raw)
        if raw.startswith("{") or (cand is not None and cand.kind == "list"):
            L = _list_arg(cons, raw)
    if L is not None:
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

def _cmd_linechart(cons, defn, args):
    """LineChart[数值列表] / LineChart[x列表, y列表] → 折线图（世界坐标折线，可整体拖动）。"""
    if not args:
        raise GeoError("LineChart 需要数值列表")
    if len(args) == 2:
        xs, dxs = _num_series(cons, [args[0]])
        ys, dys = _num_series(cons, [args[1]])
        deps = dxs + dys
        if not xs or len(xs) != len(ys):
            raise GeoError("LineChart 的 x/y 序列长度须相同且非空")
    elif len(args) == 1:
        ys, deps = _num_series(cons, args)
        xs = [float(i + 1) for i in range(len(ys))]
    else:
        ys, deps = _num_series(cons, list(args))
        xs = [float(i + 1) for i in range(len(ys))]
    if not ys:
        raise GeoError("LineChart 数据为空")
    if len(xs) != len(ys):
        raise GeoError("LineChart 的 x/y 序列长度须相同且非空")
    el = GeoLineChart(label_of(defn), defn)
    el.free = False
    if deps:
        el.set_deps(deps, lambda d: _linechart_state(el, d))
    else:
        el.xs, el.ys = xs, ys
    return cons.add(el)

def _cmd_scatterplot(cons, defn, args):
    """ScatterPlot[点列表] / ScatterPlot[数值列表] / ScatterPlot[x列表, y列表] → 散点图。"""
    if not args:
        raise GeoError("ScatterPlot 需要数据")
    pts, deps = [], []
    if len(args) == 1:
        raw = args[0].strip()
        cand = _lookup(cons, raw)
        if raw.startswith("{") or (cand is not None and cand.kind == "list"):
            L = _list_arg(cons, raw)
            deps = [L]
            if L.itemkind in ("point", "point3d"):
                pts = [[float(p[0]), float(p[1])] for p in L.items]
            elif L.itemkind in ("number", "angle"):
                pts = [[float(i + 1), float(v)] for i, v in enumerate(L.items)]
            else:
                raise GeoError("ScatterPlot 需要点列表或数值列表")
        else:
            pts = [[1.0, float(eval_number(cons, args[0]))]]
    elif len(args) == 2:
        xs, dxs = _num_series(cons, [args[0]])
        ys, dys = _num_series(cons, [args[1]])
        deps = dxs + dys
        if not xs or len(xs) != len(ys):
            raise GeoError("ScatterPlot 的 x/y 序列长度须相同且非空")
        pts = [[xs[i], ys[i]] for i in range(len(xs))]
    else:
        raise GeoError("ScatterPlot 需要点列表或 x/y 两个序列")
    if not pts:
        raise GeoError("ScatterPlot 数据为空")
    el = GeoScatterPlot(label_of(defn), defn)
    el.free = False
    if deps:
        el.set_deps(deps, lambda d: _scatter_state(el, d))
    else:
        el.pts = pts
    return cons.add(el)

def _cmd_dotplot(cons, defn, args):
    """DotPlot[数值列表] → 点图（相同取值向上叠点，可整体拖动）。"""
    vals, deps = _num_series(cons, args)
    if not vals:
        raise GeoError("DotPlot 需要数值数据")
    el = GeoDotPlot(label_of(defn), defn)
    el.free = False
    if deps:
        el.set_deps(deps, lambda d: _dotplot_state(el, d))
    else:
        vals = sorted(float(v) for v in vals)
        stacks = []
        for v in vals:
            level = 0
            while any(abs(sx - v) <= COORD and sl == level for sx, sl in stacks):
                level += 1
            stacks.append([v, level])
        el.values, el.stacks = vals, stacks
    return cons.add(el)

def _cmd_barchart3d(cons, defn, args):
    """BarChart3D[数值列表] → 三维柱状图（每根柱为长方体，合成为一个网格对象）。"""
    vals, deps = _num_series(cons, args)
    if not vals:
        raise GeoError("BarChart3D 需要数值数据")

    def state(d):
        values = [float(v) for v in d[0].items] if d else vals
        verts, faces = _bars3d_mesh(values)
        from . import mesh_store
        return schemas.chart3d("chart_bar3d", verts, faces, mesh_store.edges_of(faces))

    return _mk(cons, Geo3D, "geo3d", defn, deps, state)

def _cmd_scatterplot3d(cons, defn, args):
    """ScatterPlot3D[三维点列表] → 三维散点图（每个点放一个八面体标记）。"""
    if len(args) != 1:
        raise GeoError("ScatterPlot3D 需要三维点列表，如 {(1,2,3),(4,5,6)}")
    L = _list_arg(cons, args[0])
    if L.itemkind != "point3d":
        raise GeoError("ScatterPlot3D 需要三维点列表")

    def build(d):
        pts = [[float(p[0]), float(p[1]), float(p[2])] for p in d[0].items]
        verts, faces = _scatter3d_mesh(pts)
        from . import mesh_store
        return schemas.chart3d("chart_scatter3d", verts, faces, mesh_store.edges_of(faces))

    return _mk(cons, Geo3D, "geo3d", defn, [L], build)

def _cmd_surfacechart3d(cons, defn, args):
    """SurfaceChart3D[数值列表, 列数] → 三维高度场（统计曲面图，行优先填充）。"""
    if len(args) != 2:
        raise GeoError("SurfaceChart3D 需要数值列表与列数，如 SurfaceChart3D[{1,2,3,4}, 2]")
    vals, deps = _num_series(cons, [args[0]])
    cols = int(round(eval_number(cons, args[1])))
    if not vals:
        raise GeoError("SurfaceChart3D 数据为空")
    _surface3d_mesh(vals, cols)          # 提前校验行/列数

    def state(d):
        values = [float(v) for v in d[0].items] if d else vals
        verts, faces = _surface3d_mesh(values, cols)
        from . import mesh_store
        return schemas.chart3d("chart_surface3d", verts, faces, mesh_store.edges_of(faces))

    return _mk(cons, Geo3D, "geo3d", defn, deps, state)

def _anon_list(items):
    """临时列表容器（直接数据模式，无构造对象）。"""
    class _L:
        pass
    L = _L()
    L.items = items
    L.itemkind = "number"
    return L
