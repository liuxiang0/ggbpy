"""迭代与轨迹命令（Iteration/IterationList/Locus，P2 结构拆分）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .cmd_util import _mk, _resolve, label_of
from .elements import GeoError, GeoList, GeoLocus, GeoNumber
import re
from .parser import eval_number


__all__ = [
    "_iter_setup",
    "_cmd_iteration",
    "_cmd_iterationlist",
    "_cmd_locus",
    "_locus_state",
]


def _iter_setup(cons, args):
    """Iteration/IterationList 公共解析 → (f, x0, deps, n_el, n_fix)。"""
    if len(args) != 3:
        raise GeoError("需要 函数, 初值, 次数")
    f = _resolve(cons, args[0], ("function",))
    x0 = eval_number(cons, args[1])
    deps = [f]
    n_el = None
    n_txt = args[2].strip()
    if n_txt in cons.elements and cons.elements[n_txt].kind == "number":
        n_el = cons.elements[n_txt]
        deps.append(n_el)
        n_fix = 1
    else:
        n_fix = int(eval_number(cons, n_txt))
        if n_fix < 0 or n_fix > 100000:
            raise GeoError("迭代次数需在 0..100000")
    return f, x0, deps, n_el, n_fix

def _cmd_iteration(cons, defn, args):
    """Iteration[函数, 初值, 次数]：迭代末值（数列第 n 项）。"""
    f, x0, deps, n_el, n_fix = _iter_setup(cons, args)

    def fn(d):
        n = int(round(d[1].value)) if n_el is not None else n_fix
        n = max(0, min(100000, n))
        v = x0
        for _ in range(n):
            nv = f._eval1(v)
            if nv is None:
                raise GeoError("迭代在 x=" + str(v) + " 处发散")
            v = nv
        return {"value": float(v)}

    return _mk(cons, GeoNumber, "number", defn, deps, fn)

def _cmd_iterationlist(cons, defn, args):
    """IterationList[函数, 初值, 次数]：含初值的迭代序列（递推数列可视化）。"""
    f, x0, deps, n_el, n_fix = _iter_setup(cons, args)

    def fn(d):
        n = int(round(d[1].value)) if n_el is not None else n_fix
        n = max(0, min(100000, n))
        items = [x0]
        v = x0
        for _ in range(n):
            nv = f._eval1(v)
            if nv is None:
                raise GeoError("迭代在 x=" + str(v) + " 处发散")
            v = nv
            items.append(v)
        return {"items": items, "itemkind": "number"}

    el = GeoList(label_of(defn), defn, None, "number")
    el.free = False
    el.set_deps(deps, fn)
    el.compute()
    return cons.add(el)

def _cmd_locus(cons, defn, args):
    """Locus[Q, P]：P 为圆上点（PointOnCircle），Q 依赖 P → 轨迹。"""
    if len(args) != 2:
        raise GeoError("Locus 需要 被驱动点 和 驱动点（圆上点）")
    q = _resolve(cons, args[0], ("point",))
    p = _resolve(cons, args[1], ("point",))
    el = GeoLocus(label_of(defn), defn)
    el.free = False
    el.set_deps([q, p], lambda d: _locus_state(cons, d[0], d[1]))
    return cons.add(el)

def _locus_state(cons, q, p):
    """扫描 P 的路径参数，记录 Q 的位置序列。"""
    import numpy as np
    import re
    mpoc = re.match(r"^[A-Za-z_][A-Za-z0-9_]*=PointOnCircle\[([^,]+),([^\]]+)\]", p.defn.strip())
    mpop = re.match(r"^[A-Za-z_][A-Za-z0-9_]*=PointOnPath\[([^,]+),([^\]]+)\]", p.defn.strip())
    if mpoc:
        plab, tlab = mpoc.group(1).strip(), mpoc.group(2).strip()
        lo, hi = 0.0, 2 * math.pi
    elif mpop:
        plab, tlab = mpop.group(1).strip(), mpop.group(2).strip()
        lo, hi = 0.0, 1.0
    else:
        raise GeoError("Locus 需要驱动点 P 是 PointOnCircle 或 PointOnPath 上的动点")
    c = cons.elements.get(plab)
    th = cons.elements.get(tlab)
    if c is None or th is None or th.kind != "number":
        raise GeoError("无法解析驱动点路径")
    # Q 的传递上游（含 P），按深度排序
    upstream = set()
    stack = [q]
    while stack:
        e = stack.pop()
        if e in upstream:
            continue
        upstream.add(e)
        stack.extend(e.deps)
    ordered = sorted(upstream, key=lambda e: e.depth)
    orig = th.value
    pts = []
    try:
        for t in np.linspace(lo, hi, 200):
            th.value = float(t)
            for e in ordered:
                if not e.free:
                    e.compute()
            if q.error is None:
                pts.append([q.x, q.y])
    finally:
        th.value = orig
        for e in ordered:
            if not e.free:
                e.compute()
    return {"pts": pts}
