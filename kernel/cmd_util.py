"""命令层共享工具：参数解析 / 元素构造 / 标签解析（P2 结构拆分：从 commands.py 抽出）。

`commands.py` 与后续拆出的命令子模块（如 calculus）共用这些助手。本模块**不依赖命令
注册表**：`_lookup` 遇到嵌套命令 `Cmd[...]` 时通过 `set_nested_evaluator()` 注入的钩子
求值（`commands.py` 导入后把 `_eval_nested` 注入进来），从而避免循环导入。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import re

from .elements import GeoElement, GeoError, GeoList, GeoPoint
from .parser import eval_number

# 嵌套命令识别（_lookup 遇到 `Cmd[...]` 时走注入的求值钩子）
_NESTED_CALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\[(.*)\]$", re.S)
_NESTED_MAX_DEPTH = 4

# 表达式依赖助手已拆到 kernel/exprdeps.py（此处 re-export，保持调用方兼容）
from .exprdeps import _list_state_from_parts, _ref_deps, list_literal_state, numeric_expr_state, point_expr_state

# 嵌套命令求值钩子：由 commands.py 注入（见 set_nested_evaluator）
_nested_evaluator: Optional[Callable] = None


def set_nested_evaluator(fn: Optional[Callable]) -> None:
    """注入嵌套命令就地求值实现（commands._eval_nested）。"""
    global _nested_evaluator
    _nested_evaluator = fn


__all__ = [
    "label_of",
    "_NESTED_CALL_RE",
    "_NESTED_MAX_DEPTH",
    "_nested_depth",
    "_label_of",
    "_mk",
    "_auto",
    "_resolve",
    "_lookup",
    "_tuple_parts_any",
    "list_literal_state",
    "_list_arg",
    "_point_arg",
    "_num_deps",
    "_num_list_items",
    "_num_series",
    "_elem_or_point",
    "_is_segment_el",
]


def _nested_depth(cons) -> int:
    return int(getattr(cons, "_nested_depth", 0))

def label_of(defn: str) -> str:
    """从定义式 `A=(1,2)` 取出标签 A（`=` 或 `:` 之前的部分）。"""
    idx = defn.find("=")
    if idx == -1:
        idx = defn.find(":")
    return defn[:idx].strip()


def _label_of(defn: str) -> str:
    idx = defn.find("=")
    if idx == -1:
        idx = defn.find(":")
    return defn[:idx].strip() if idx != -1 else defn.strip()

def _mk(cons, cls, kind_for_label, defn, deps, fn):
    label = defn.split("=")[0].split(":")[0].strip()
    if not label or label[0].isdigit():
        raise GeoError("内部错误: 派生对象缺标签")
    el = cls(label, defn)
    el.free = False
    el.set_deps(deps, fn)
    return cons.add(el)

def _auto(cons, cls, kind, defn, deps, fn):
    label = cons.auto_label(kind)
    el = cls(label, defn)
    el.free = False
    el.set_deps(deps, fn)
    return cons.add(el)

def _resolve(cons, s: str, kinds: Optional[Tuple[str, ...]] = None):
    """把参数字符串解析为元素；kinds 非空时校验类型。"""
    s = s.strip()
    el = _lookup(cons, s)
    if el is None:
        raise GeoError("找不到对象 " + s)
    if kinds and el.kind not in kinds:
        raise GeoError(s + " 的类型是 " + el.kind + "，这里需要 " + "/".join(kinds))
    return el

def _lookup(cons, s: str):
    """按标签查元素；参数是嵌套命令时即时求值（匿名辅助，不注册）。查不到返回 None。

    嵌套求值由 commands.py 注入（`set_nested_evaluator(commands._eval_nested)`）——
    本模块不依赖命令注册表，避免循环导入。
    """
    key = s.strip()
    el = cons.elements.get(key)
    if el is not None:
        return el
    if _NESTED_CALL_RE.match(key) and _nested_evaluator is not None:
        return _nested_evaluator(cons, key)
    return None

def _tuple_parts_any(s: str) -> List[str]:
    """任意分量数的元组（2 或 3 个分量）。"""
    s = s.strip()
    if not (s.startswith("(") and s.endswith(")")):
        raise GeoError("需要 (a,b) 形式: " + s)
    inner = s[1:-1]
    parts = inner.split(",")
    if len(parts) not in (2, 3):
        raise GeoError("元组需要两个或三个分量: " + s)
    return [p.strip() for p in parts]

def _list_arg(cons, s):
    s = s.strip()
    el = _lookup(cons, s)
    if el is None and s.startswith("{"):
        # 内联列表 → 匿名列表（不注册，仅作依赖）
        from .parser import _list_point_items, _reject_mixed_point_list, _split_brace, tokenize
        parts = _split_brace(tokenize(s))
        if parts and parts[0].startswith("("):
            items = []
            kind3 = None
            for p in parts:
                tp = _tuple_parts_any(p)
                k = "point3d" if len(tp) == 3 else "point"
                if kind3 is None:
                    kind3 = k
                elif kind3 != k:
                    raise GeoError("列表元素分量数需一致（要么全是 (x,y)，要么全是 (x,y,z)）")
                items.append(tuple(eval_number(cons, q) for q in tp))
            el = GeoList("_hl", s, items, kind3)
        else:
            pt_items = _list_point_items(cons, parts)      # {A,B} / {A3,B3}
            if pt_items is not None:
                el = GeoList("_hl", s, pt_items[0], pt_items[1])
            else:
                _reject_mixed_point_list(cons, parts)
                items = [eval_number(cons, p) for p in parts]
                el = GeoList("_hl", s, items, "number")
        el.visible = False
        # 依赖化：内联列表含元素引用时随依赖重算（匿名列表也在依赖图中，会驱动下游命令刷新）
        deps, state_fn = _list_state_from_parts(cons, parts, el.itemkind)
        if deps and state_fn is not None:
            el.free = False
            el.set_deps(deps, state_fn)
        return el
    if el is None:
        raise GeoError("找不到对象 " + s)
    if el.kind != "list":
        raise GeoError(s + " 不是列表")
    return el

def _point_arg(cons, s: str):
    """命令参数中的点：可以是标签，也可以是 (x,y) 字面量（自动创建隐藏辅助点）。"""
    s = s.strip()
    el = _lookup(cons, s)
    if el is not None:
        if el.kind != "point":
            raise GeoError(s + " 不是点")
        return el
    if s.startswith("("):
        parts = _tuple_parts_any(s)
        vals = [eval_number(cons, p) for p in parts]
        z = vals[2] if len(vals) == 3 else None
        # 匿名辅助点：不注册进构造（不可见、不参与撤销/序列化），仅作依赖。
        # 分量引用已有元素（如 (s,0)）→ 挂依赖，随滑块重算（否则会固化成一次求值）。
        _deps = _ref_deps(cons, parts)
        el = GeoPoint("_h", s, vals[0], vals[1], True, z)
        el.visible = False
        if _deps:

            def _state(_d, _parts=parts):
                vs = [eval_number(cons, q) for q in _parts]
                return {"x": vs[0], "y": vs[1], "z": vs[2] if len(vs) == 3 else None}

            el.free = False
            el.set_deps(_deps, _state)
        return el
    raise GeoError("找不到点 " + s)

def _num_deps(cons, defn):
    """defn 中引用的 number 对象（滑块等）→ deps。"""
    return [e for lab, e in cons.elements.items()
            if e.kind == "number" and re.search(r"\b" + re.escape(lab) + r"\b", defn)]

def _num_list_items(cons, args):
    first = args[0].strip()
    if first.startswith("{") or first.startswith("[") or first in cons.elements:
        L = _list_arg(cons, args[0])
        if L.itemkind != "number":
            raise GeoError("需要数值列表")
        return list(L.items), [L]
    items = [eval_number(cons, a) for a in args]
    return items, []

def _num_series(cons, args):
    """解析数值序列：{..} 内联 / 数值列表标签 / 多个数值。返回 (values, deps)。"""
    if len(args) == 1:
        raw = args[0].strip()
        cand = _lookup(cons, raw)
        if raw.startswith("{") or (cand is not None and cand.kind == "list"):
            L = _list_arg(cons, raw)
            if L.itemkind not in ("number", "angle"):
                raise GeoError("需要数值列表")
            return [float(v) for v in L.items], [L]
    return [eval_number(cons, a) for a in args], []

def _elem_or_point(cons, s: str):
    """参数解析：优先按已有元素标签；否则尝试 (x,y) / (x,y,z) 字面量点。"""
    txt = s.strip()
    el = _lookup(cons, txt)
    if el is not None:
        return el
    if txt.startswith("("):
        return _point_arg(cons, txt)
    raise GeoError("找不到对象 " + txt)

def _is_segment_el(el) -> bool:
    return el.kind == "segment" or (el.kind == "geo3d" and getattr(el, "objtype", "") == "segment")



