"""数值与统计命令（求和/均值/方差/排序/四分位/组合数/取整等，P2 结构拆分：从 commands.py 抽出）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .calculus import _int_values
from .cmd_util import _list_arg, _lookup, _mk, _num_list_items, _resolve, label_of
from .stats import _median, _mode, _variance
from .elements import GeoError, GeoList, GeoNumber
from .parser import eval_number


__all__ = [
    "_cmd_npr",
    "_cmd_ncr",
    "_cmd_gcd",
    "_cmd_lcm",
    "_resolve_complex",
    "_cmd_complex_abs",
    "_cmd_sum",
    "_cmd_mean",
    "_cmd_median",
    "_cmd_mode",
    "_cmd_variance",
    "_cmd_stdev",
    "_cmd_min",
    "_cmd_max",
    "_cmd_sort",
    "_cmd_normal",
    "_cmd_q1",
    "_cmd_q3",
    "_cmd_iqr",
]


def _cmd_npr(cons, defn, args):
    """nPr[n, r]：排列数。"""
    if len(args) != 2:
        raise GeoError("nPr 需要 n, r")
    n = int(eval_number(cons, args[0]))
    r = int(eval_number(cons, args[1]))
    if n < 0 or r < 0 or r > n:
        raise GeoError("需要 0 ≤ r ≤ n")
    try:
        v = math.perm(n, r)
    except (OverflowError, ValueError):
        raise GeoError("结果过大")
    el = GeoNumber(label_of(defn), defn, float(v))
    el.free = False
    return cons.add(el)

def _cmd_ncr(cons, defn, args):
    """nCr[n, r]：组合数。"""
    if len(args) != 2:
        raise GeoError("nCr 需要 n, r")
    n = int(eval_number(cons, args[0]))
    r = int(eval_number(cons, args[1]))
    if n < 0 or r < 0 or r > n:
        raise GeoError("需要 0 ≤ r ≤ n")
    try:
        v = math.comb(n, r)
    except (OverflowError, ValueError):
        raise GeoError("结果过大")
    el = GeoNumber(label_of(defn), defn, float(v))
    el.free = False
    return cons.add(el)

def _cmd_gcd(cons, defn, args):
    vals = _int_values(cons, args)
    if not vals:
        raise GeoError("GCD 需要数值")
    import math
    if any(v < 0 for v in vals):
        raise GeoError("GCD 需要非负整数")
    g = 0
    for v in vals:
        g = math.gcd(g, v)
    el = GeoNumber(label_of(defn), defn, float(g))
    el.free = False
    return cons.add(el)

def _cmd_lcm(cons, defn, args):
    vals = _int_values(cons, args)
    if not vals:
        raise GeoError("LCM 需要数值")
    import math
    if any(v < 0 for v in vals):
        raise GeoError("LCM 需要非负整数")
    l = 1
    for v in vals:
        l = l * v // math.gcd(l, v)
    el = GeoNumber(label_of(defn), defn, float(l))
    el.free = False
    return cons.add(el)

def _resolve_complex(cons, s):
    z = _resolve(cons, s, ("complex",))
    return z

def _cmd_complex_abs(cons, defn, args):
    z = _resolve_complex(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [z],
               lambda d: {"value": math.hypot(d[0].re, d[0].im)})

def _cmd_sum(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L],
               lambda d: {"value": float(sum(d[0].items))})

def _cmd_mean(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L],
               lambda d: {"value": float(sum(d[0].items)) / len(d[0].items) if d[0].items else 0.0})

def _cmd_median(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L], lambda d: {"value": _median(d[0].items)})

def _cmd_mode(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L], lambda d: {"value": _mode(d[0].items)})

def _cmd_variance(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L], lambda d: {"value": _variance(d[0].items)})

def _cmd_stdev(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L], lambda d: {"value": math.sqrt(_variance(d[0].items))})

def _cmd_min(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L], lambda d: {"value": float(min(d[0].items)) if d[0].items else 0.0})

def _cmd_max(cons, defn, args):
    L = _list_arg(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [L], lambda d: {"value": float(max(d[0].items)) if d[0].items else 0.0})

def _cmd_sort(cons, defn, args):
    L = _list_arg(cons, args[0])
    el = GeoList(label_of(defn), defn, None, "number")
    el.free = False
    el.set_deps([L], lambda d: {"items": sorted(d[0].items), "itemkind": "number"})
    return cons.add(el)

def _cmd_normal(cons, defn, args):
    """Normal[μ, σ, x] → 正态分布密度值。"""
    if len(args) != 3:
        raise GeoError("Normal 需要 均值、标准差、x 值")
    mu = eval_number(cons, args[0])
    sigma = eval_number(cons, args[1])
    if sigma <= 0:
        raise GeoError("标准差必须 > 0")
    x_el = _lookup(cons, args[2])
    if x_el is not None and x_el.kind in ("number", "angle"):
        deps = [x_el]
        fixed = None
    else:
        deps = []
        fixed = eval_number(cons, args[2])
    from scipy.stats import norm

    def fn(d):
        xv = fixed if fixed is not None else d[0].value
        return {"value": float(norm.pdf(xv, mu, sigma))}
    return _mk(cons, GeoNumber, "number", defn, deps, fn)

def _cmd_q1(cons, defn, args):
    items, deps = _num_list_items(cons, args)
    if len(items) < 1:
        raise GeoError("空数据")
    import numpy as np
    v = float(np.percentile(np.array(items, dtype=float), 25))
    return _mk(cons, GeoNumber, "number", defn, deps,
               lambda d, its=items: {"value": float(np.percentile(np.array(list(d[0].items) if d else its, dtype=float), 25))})

def _cmd_q3(cons, defn, args):
    items, deps = _num_list_items(cons, args)
    if len(items) < 1:
        raise GeoError("空数据")
    import numpy as np
    return _mk(cons, GeoNumber, "number", defn, deps,
               lambda d, its=items: {"value": float(np.percentile(np.array(list(d[0].items) if d else its, dtype=float), 75))})

def _cmd_iqr(cons, defn, args):
    items, deps = _num_list_items(cons, args)
    if len(items) < 1:
        raise GeoError("空数据")
    import numpy as np
    return _mk(cons, GeoNumber, "number", defn, deps,
               lambda d, its=items: {"value": float(np.percentile(np.array(list(d[0].items) if d else its, dtype=float), 75)
                                               - np.percentile(np.array(list(d[0].items) if d else its, dtype=float), 25))})
