"""表达式依赖：让引用已有元素的对象成为**受控对象**（自 cmd_util 拆出，见第 71/72 批）。

三类入口（语义一致：含元素引用 → 声明依赖并随依赖重算；纯常量 → 返回 ``([], None)``，调用方保持自由/静态语义）：
- ``point_expr_state``   ``A=(s,0)``  → 受控点（坐标分量可含表达式）
- ``numeric_expr_state`` ``n=s*2``    → 受控数值
- ``list_literal_state`` ``L={n, n*10+2}`` → 依赖驱动的列表字面量

``cmd_util`` 会 re-export 这些名字，历史调用点无需改动。
"""
from typing import Any, Dict, List, Optional, Tuple

from .elements import GeoError


def _tuple_parts(s: str) -> List[str]:
    """元组分量拆分：懒引用 cmd_util（避免 cmd_util ←→ exprdeps 模块级循环导入）。"""
    from .cmd_util import _tuple_parts_any
    return _tuple_parts_any(s)

def _list_state_from_parts(cons, parts, itemkind: str):
    """由**已拆分的列表项**构造 ``(deps, state_fn)``（赋值语句与命令内联列表共用）。

    - 依赖：整项是元素标签 → 依赖；表达式里引用的构造内元素 → 依赖（按出现顺序去重）
    - state_fn：重算时逐项重新求值（数值表达式 / 点标签 / (x,y[,z]) 元组）
    - 纯常量（无依赖）→ ``([], None)``，调用方保持静态语义
    """
    import re as _re

    from .parser import eval_number

    if not parts:
        return [], None

    deps: List = []
    seen = set()

    def _add(el) -> None:
        if el is not None and id(el) not in seen:
            seen.add(id(el))
            deps.append(el)

    for part in parts:
        pt = part.strip()
        _add(cons.elements.get(pt))
        frags = _tuple_parts(pt) if (pt.startswith("(") and pt.endswith(")")) else [pt]
        for frag in frags:
            for tok in _re.findall(r"[A-Za-z_][A-Za-z0-9_]*", frag):
                _add(cons.elements.get(tok))
    if not deps:
        return [], None

    def _value(part: str):
        pt = part.strip()
        el = cons.elements.get(pt)
        if el is not None and el.kind in ("point", "point3d"):
            if getattr(el, "z", None) is not None:
                return [float(el.x), float(el.y), float(el.z)]
            return [float(el.x), float(el.y)]
        if pt.startswith("(") and pt.endswith(")"):
            vals = [eval_number(cons, c) for c in (_tuple_parts(pt) or [])]
            return tuple(vals)
        if el is not None and el.kind == "number":
            return float(el.value)
        return eval_number(cons, pt)

    def state(_d):
        items = []
        for part in parts:
            try:
                items.append(_value(part))
            except GeoError:
                raise
            except Exception as ex:  # 依赖变化后无法求值：明确报错（元素转 error，不静默留旧值）
                raise GeoError("列表求值失败：" + str(ex)[:60])
        return {"items": items, "itemkind": itemkind}

    return deps, state


def list_literal_state(cons, line: str, itemkind: str):
    """列表字面量依赖化：``L={n, n*10+2}`` → ``(deps, state_fn)``。

    薄封装：从整行取出 ``{...}`` 后委托 ``_list_state_from_parts``（与命令内联列表共用核心）。
    纯常量列表返回 ``([], None)`` → 调用方保持原有静态快照语义。
    """
    import re as _re

    from .parser import _split_brace, tokenize

    m = _re.search(r"=\s*(\{.*\})\s*$", line, _re.S)
    if not m:
        return [], None
    return _list_state_from_parts(cons, _split_brace(tokenize(m.group(1))), itemkind)


def _ref_deps(cons, exprs):
    """从若干表达式里收集引用的已有元素（按出现顺序去重）。"""
    import re as _re
    deps, seen = [], set()
    for e in exprs:
        el = cons.elements.get(str(e).strip())
        if el is not None and id(el) not in seen:
            seen.add(id(el))
            deps.append(el)
        for tok in _re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(e)):
            el2 = cons.elements.get(tok)
            if el2 is not None and id(el2) not in seen:
                seen.add(id(el2))
                deps.append(el2)
    return deps


def point_expr_state(cons, line: str):
    """``A=(expr_x, expr_y[, expr_z])`` 分量引用已有元素 → ``(deps, state_fn)``；否则 ``([], None)``。

    GeoGebra 语义：``A=(s,0)`` 是**受控点**（随滑块移动、不可直接拖动）；
    ``A=(1,2)`` 仍是自由点（可拖动）。纯常量时不改变原行为。
    """
    import re as _re

    from .parser import _tuple_parts_str, eval_number

    m = _re.search(r"=\s*(\(.*\))\s*$", line, _re.S)
    if not m:
        return [], None
    try:
        parts = _tuple_parts_str(m.group(1))
    except GeoError:
        return [], None
    if len(parts) not in (2, 3):
        return [], None
    deps = _ref_deps(cons, parts)
    if not deps:
        return [], None

    def state(_d):
        vals = [eval_number(cons, q) for q in parts]
        if len(vals) == 3:
            return {"x": vals[0], "y": vals[1], "z": vals[2]}
        return {"x": vals[0], "y": vals[1]}

    return deps, state


def numeric_expr_state(cons, line: str):
    """``n=expr`` 且 expr 引用已有数值元素 → ``(deps, state_fn)``；否则 ``([], None)``。"""
    import re as _re

    from .parser import eval_number

    m = _re.search(r"=\s*(.+)$", line, _re.S)
    if not m:
        return [], None
    expr = m.group(1).strip()
    if not expr or expr.startswith(("(", "{")):      # 点/列表各有处理
        return [], None
    deps = [d for d in _ref_deps(cons, [expr]) if getattr(d, "kind", "") in ("number", "angle")]
    if not deps:
        return [], None

    def state(_d):
        return {"value": float(eval_number(cons, expr))}

    return deps, state
