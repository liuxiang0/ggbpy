"""矩阵与复数命令（矩阵/行列式/转置/逆/点积/复数运算，P2 结构拆分：从 commands.py 抽出）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .cmd_util import _lookup, _mk, _resolve, label_of
from .io_cmds import _tuple_parts
from .numeric import _resolve_complex
from .elements import GeoComplex, GeoError, GeoMatrix, GeoNumber
from .parser import _split_brace, eval_number, tokenize


__all__ = [
    "_vec2_arg",
    "_vec_arg_objs",
    "_cmd_dot",
    "_cmd_conj",
    "_cmd_re",
    "_cmd_im",
    "_cmd_arg",
    "_arg_deg",
    "_parse_matrix_arg",
    "_cmd_matrix",
    "_cmd_det",
    "_det_state",
    "_cmd_transpose",
    "_transpose_state",
    "_cmd_inverse",
    "_inverse_state",
]


def _vec2_arg(cons, s):
    """向量参数：向量/点对象 或 (a,b) 元组 → (dx, dy)。"""
    s = s.strip()
    if s.startswith("("):
        parts = _tuple_parts(s)
        return eval_number(cons, parts[0]), eval_number(cons, parts[1])
    el = _lookup(cons, s)
    if el is None:
        raise GeoError("找不到对象 " + s)
    if el.kind == "vector":
        return el.dx, el.dy
    if el.kind == "point":
        return el.x, el.y
    raise GeoError("Dot/Angle 需要 向量或点: " + s)

def _vec_arg_objs(cons, args):
    """Dot/Angle 两参数中引用的对象（向量/点）→ 依赖列表。"""
    objs = []
    for a in args:
        s = a.strip()
        if not s.startswith("("):
            e = _lookup(cons, s)
            if e is not None and e.kind in ("vector", "point") and e not in objs:
                objs.append(e)
    return objs

def _cmd_dot(cons, defn, args):
    """Dot[u, v]：两向量/点（或元组）的点积。"""
    if len(args) != 2:
        raise GeoError("Dot 需要 两个向量或点")
    objs = _vec_arg_objs(cons, args)

    def fn(d):
        def comp(txt):
            txt = txt.strip()
            if txt.startswith("("):
                return _vec2_arg(cons, txt)
            for i, o in enumerate(objs):
                if o.label == txt:
                    o2 = d[i]
                    return (o2.dx, o2.dy) if o2.kind == "vector" else (o2.x, o2.y)
            raise GeoError("Dot 参数未解析: " + txt)
        u = comp(args[0])
        v = comp(args[1])
        return {"value": u[0] * v[0] + u[1] * v[1]}

    return _mk(cons, GeoNumber, "number", defn, objs, fn)

def _cmd_conj(cons, defn, args):
    if len(args) != 1:
        raise GeoError("conj 需要一个复数")
    z = _resolve_complex(cons, args[0])
    return _mk(cons, GeoComplex, "complex", defn, [z],
               lambda d: {"re": d[0].re, "im": -d[0].im})

def _cmd_re(cons, defn, args):
    z = _resolve_complex(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [z], lambda d: {"value": d[0].re})

def _cmd_im(cons, defn, args):
    z = _resolve_complex(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [z], lambda d: {"value": d[0].im})

def _cmd_arg(cons, defn, args):
    z = _resolve_complex(cons, args[0])
    return _mk(cons, GeoNumber, "number", defn, [z],
               lambda d: {"value": _arg_deg(d[0].re, d[0].im)})

def _arg_deg(a, b):
    import math as _m
    ang = _m.degrees(_m.atan2(b, a))
    if ang < 0:
        ang += 360.0
    return ang

def _parse_matrix_arg(cons, s: str):
    """解析 {{1,2},{3,4}} → numpy 数组。"""
    import numpy as np
    from .parser import _split_brace, tokenize
    s = s.strip()
    if not (s.startswith("{") and s.endswith("}")):
        raise GeoError("矩阵需要 {{...},{...}} 形式")
    rows = _split_brace(tokenize(s))
    data = []
    for row in rows:
        if not (row.startswith("{") and row.endswith("}")):
            raise GeoError("矩阵行需要 {...} 形式: " + row)
        vals = [eval_number(cons, v) for v in _split_brace(tokenize(row))]
        data.append(vals)
    if not data:
        raise GeoError("空矩阵")
    n = len(data[0])
    for r in data:
        if len(r) != n:
            raise GeoError("矩阵各行长度必须一致")
    return np.array(data, dtype=float)

def _cmd_matrix(cons, defn, args):
    if len(args) != 1:
        raise GeoError("Matrix 需要 {{1,2},{3,4}} 形式")
    data = _parse_matrix_arg(cons, args[0])
    el = GeoMatrix(label_of(defn), defn)
    el.free = False
    el.data = data
    return cons.add(el)

def _cmd_det(cons, defn, args):
    m = _resolve(cons, args[0], ("matrix",))
    return _mk(cons, GeoNumber, "number", defn, [m], lambda d: _det_state(d[0]))

def _det_state(m):
    import numpy as np
    if m.data is None:
        raise GeoError("空矩阵")
    if m.data.shape[0] != m.data.shape[1]:
        raise GeoError("行列式需要方阵")
    return {"value": float(np.linalg.det(m.data))}

def _cmd_transpose(cons, defn, args):
    m = _resolve(cons, args[0], ("matrix",))
    return _mk(cons, GeoMatrix, "matrix", defn, [m], lambda d: _transpose_state(d[0]))

def _transpose_state(m):
    if m.data is None:
        raise GeoError("空矩阵")
    return {"data": m.data.T}

def _cmd_inverse(cons, defn, args):
    m = _resolve(cons, args[0], ("matrix",))
    return _mk(cons, GeoMatrix, "matrix", defn, [m], lambda d: _inverse_state(d[0]))

def _inverse_state(m):
    import numpy as np
    if m.data is None:
        raise GeoError("空矩阵")
    if m.data.shape[0] != m.data.shape[1]:
        raise GeoError("逆矩阵需要方阵")
    try:
        inv = np.linalg.inv(m.data)
    except np.linalg.LinAlgError:
        raise GeoError("矩阵不可逆（奇异）")
    return {"data": inv}
