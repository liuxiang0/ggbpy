"""CAS 算子的构造命令：把 CAS 面板已有的能力提升为**可参与 DAG 的构造命令**。

CAS 引擎（``kernel/cas.py::CASEngine``）已实现 Expand/Factor/Simplify/Solve/NSolve/Limit/
Derivative/Integral/SolveODE/PartialFractions/Substitute。本模块把其中**语义确定**的算子接线到
命令层，于是它们的结果能被其它命令引用、能随依赖（滑块/点）重算、能随 ``.ggk``/``.ggb`` 往返。

返回类型（同时见 README「2D 限制」）：
- ``Solve[方程, 变量?]``            → 数值解列表（``list``）；解含自由符号时退回文本（``result``）
- ``NSolve[方程, 变量?]``           → 实根数值列表（``list``；符号优先 + 扫描二分兜底）
- ``Limit[表达式|函数, x0]``（或 ``[表达式, 变量, x0]``）→ 数值（有限时；∞/不存在给明确错误）
- ``PartialFractions[表达式|函数, 变量?]`` → 函数
- ``Substitute[表达式|函数, 变量, 值]``    → 无自由变量时数值，否则函数
- ``SolveODE[微分方程, 自变量?]``   → 文本（sympy ``dsolve`` 通解；暂不支持初值条件）

设计约定：所有命令都用 ``_mk`` 声明依赖，因此表达式里引用滑块/数值元素时会自动重算。
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .elements import (GeoBoolean, GeoError, GeoFunction, GeoList, GeoNumber,
                       GeoResult)
from .cmd_util import label_of, _lookup, _mk
from .tolerance import COORD
from .parser import eval_number

# 名称 → 该命令可接受的“无解”表述（供测试与报错文案统一）
_NO_SOLUTION = "无解"


def _split_eq(body: str) -> Tuple[str, str]:
    """把 ``a=b`` 拆成 ``(a, b)``；无等号时视为 ``(body, 0)``。"""
    s = body.strip()
    if "=" in s:
        a, b = s.split("=", 1)
        if a.strip():
            return a, b
    return s, "0"


def _expr_of(cons, body: str, var_s: str = "x") -> Tuple[Any, Any, List, bool]:
    """把参数解析为 ``(sympy 表达式, 符号, 依赖元素, 是否来自函数元素)``。

    参数既可以是已定义的**函数元素**（取它的 expr/xsym），也可以是**表达式字符串**
    （用 ``_parse_sympy`` 解析，并收集其中引用的数值元素作为依赖）。
    """
    import sympy

    from .calculus import _parse_sympy

    lab = body.strip()
    el = cons.elements.get(lab) if lab else None
    if el is not None and el.kind == "function":
        return el.expr, el.xsym, [el], True
    var = sympy.Symbol(var_s)
    from .cas import _function_refs
    return _parse_sympy(body, {var_s: var}, cons), var, _function_refs(cons, body), False


def _float_or_none(v) -> Optional[float]:
    """sympy 值 → float（复数或无法数值化时返回 None）。"""
    import sympy
    try:
        c = complex(sympy.N(v))
    except (TypeError, ValueError, AttributeError, ArithmeticError):
        # 符号量无法数值化（含自由符号）：由调用方退回文本
        return None
    if abs(c.imag) > COORD:
        return None
    return float(c.real)


def _num_list_element(cons, defn: str, vals: List[float], deps: List) -> Any:
    """构造数值列表元素（``_mk`` 声明依赖 → 引用滑块变化时自动重算）。"""
    def _state(d):
        return {"items": list(vals), "itemkind": "number"}
    return _mk(cons, GeoList, "list", defn, deps, _state)


def _text_element(cons, defn: str, text: str, deps: Optional[List] = None) -> Any:
    return _mk(cons, GeoResult, "result", defn, deps or [], lambda d: {"text": text})


# ---------------------------------------------------------------------------
# Solve / NSolve
# ---------------------------------------------------------------------------

def _cmd_solve(cons, defn, args):
    """``Solve[方程, 变量?]`` → 数值解列表；解含自由符号时退回文本，无解给空列表。"""
    if len(args) not in (1, 2):
        raise GeoError("Solve 需要 方程（可选变量），如 Solve[x^2=4, x]")
    import sympy

    var_s = args[1].strip() if len(args) == 2 else "x"
    var = sympy.Symbol(var_s)
    lhs, rhs = _split_eq(args[0])
    from .calculus import _parse_sympy
    e = _parse_sympy(lhs, {var_s: var}, cons) - _parse_sympy(rhs, {var_s: var}, cons)
    try:
        sols = sympy.solve(e, var)
    except Exception as ex:  # 符号求解失败：明确报错而不是静默给错解
        raise GeoError("Solve 无法求解该方程：" + str(ex)[:60])
    if not isinstance(sols, list):
        sols = [] if sols is None else [sols]

    vals: List[float] = []
    symbolic: List[Any] = []
    for s in sols:
        if isinstance(s, dict):                     # 多变量解集不属本命令范围
            symbolic.append(s)
            continue
        f = _float_or_none(s)
        if f is None:
            symbolic.append(s)
        else:
            vals.append(f)
    from .cas import _function_refs
    deps = _function_refs(cons, args[0])
    if symbolic and not vals:
        body = "{" + ", ".join("%s = %s" % (var_s, sympy.sstr(s)) for s in symbolic) + "}"
        return _text_element(cons, defn, body, deps)
    def _state(d):
        e2 = _parse_sympy(lhs, {var_s: var}, cons) - _parse_sympy(rhs, {var_s: var}, cons)
        out = []
        for s2 in sympy.solve(e2, var) if isinstance(sympy.solve(e2, var), list) else [sympy.solve(e2, var)]:
            f2 = _float_or_none(s2)
            if f2 is not None:
                out.append(f2)
        return {"items": sorted(set(round(v, 12) for v in out)), "itemkind": "number"}
    return _mk(cons, GeoList, "list", defn, deps, _state)


def _cmd_nsolve(cons, defn, args):
    """``NSolve[方程, 变量?]`` → 实根数值列表（符号优先，数值扫描+二分兜底）。"""
    if len(args) not in (1, 2):
        raise GeoError("NSolve 需要 方程（可选变量），如 NSolve[cos(x)=x, x]")
    import sympy

    from .calculus import _parse_sympy, _roots_1d
    var_s = args[1].strip() if len(args) == 2 else "x"
    var = sympy.Symbol(var_s)
    lhs, rhs = _split_eq(args[0])
    e = _parse_sympy(lhs, {var_s: var}, cons) - _parse_sympy(rhs, {var_s: var}, cons)
    roots = _roots_1d(e, var)
    if not roots:
        raise GeoError("NSolve 在默认区间内没有找到实根（可改用 Solve 看符号解）")
    from .cas import _function_refs

    def _state(d):
        e2 = _parse_sympy(lhs, {var_s: var}, cons) - _parse_sympy(rhs, {var_s: var}, cons)
        rs = _roots_1d(e2, var)
        if not rs:
            raise GeoError("NSolve 在默认区间内没有找到实根（可改用 Solve 看符号解）")
        return {"items": sorted(set(round(r, 12) for r in rs)), "itemkind": "number"}
    return _mk(cons, GeoList, "list", defn, _function_refs(cons, args[0]), _state)


# ---------------------------------------------------------------------------
# Limit
# ---------------------------------------------------------------------------

def _cmd_limit(cons, defn, args):
    """``Limit[表达式|函数, x0]`` 或 ``Limit[表达式, 变量, x0]`` → 数值（有限时）。"""
    if len(args) == 2:
        body, var_s, x0_s = args[0], "x", args[1]
    elif len(args) == 3:
        body, var_s, x0_s = args[0], args[1].strip() or "x", args[2]
    else:
        raise GeoError("Limit 需要 表达式/函数 与取值，如 Limit[sin(x)/x, 0]")

    import sympy

    from .calculus import _parse_sympy
    expr, var, deps, _is_fn = _expr_of(cons, body, var_s)
    from .cas import _function_refs
    for extra in _function_refs(cons, x0_s):        # 取值若引用数值元素，也要作为依赖
        if extra not in deps:
            deps.append(extra)

    def _point():
        """取值：经构造解析（引用元素取其当前值；支持 ∞/oo）。"""
        try:
            return _parse_sympy(x0_s.replace("∞", "oo"), {var_s: var}, cons)
        except (SyntaxError, TypeError, ValueError, AttributeError, KeyError):
            return eval_number(cons, x0_s)

    def _state(d):
        e2, v2, _dp, _fn = _expr_of(cons, body, var_s)
        try:
            res2 = sympy.limit(e2, v2, _point())
        except Exception as ex:  # sympy 极限失败类型不可枚举（NotImplementedError/PoleError 等）：明确报错
            raise GeoError("Limit 无法求解该极限：" + str(ex)[:60])
        val2 = _float_or_none(res2)
        if val2 is None or not math.isfinite(val2):
            raise GeoError("Limit 的极限不存在或为无穷（当前值 %s）" % str(res2)[:40])
        return {"value": val2}

    _state(None)                                    # 创建时先校验一次（失败则命令直接报错）
    return _mk(cons, GeoNumber, "number", defn, deps, _state)


# ---------------------------------------------------------------------------
# PartialFractions / Substitute
# ---------------------------------------------------------------------------

def _cmd_partialfractions(cons, defn, args):
    """``PartialFractions[表达式|函数, 变量?]`` → 部分分式（函数）。"""
    if len(args) not in (1, 2):
        raise GeoError("PartialFractions 需要 表达式/函数（可选变量），如 PartialFractions[(x^2+1)/(x-1)]")
    import sympy
    var_s = args[1].strip() if len(args) == 2 else "x"
    expr, var, deps, _is_fn = _expr_of(cons, args[0], var_s)
    try:
        res = sympy.apart(expr, var)
    except Exception as ex:  # sympy apart 失败类型不可枚举：明确报错
        raise GeoError("PartialFractions 无法分解：" + str(ex)[:60])

    def _state(d):
        e2, v2, _dp, _fn = _expr_of(cons, args[0], var_s)
        return {"expr": sympy.apart(e2, v2), "xsym": v2}
    return _mk(cons, GeoFunction, "function", defn, deps, _state)


def _cmd_substitute(cons, defn, args):
    """``Substitute[表达式|函数, 变量, 值]`` → 无自由变量时数值，否则函数。"""
    if len(args) != 3:
        raise GeoError("Substitute 需要 表达式/函数、变量、值，如 Substitute[x^2, x, 3]")
    import sympy

    from .calculus import _parse_sympy
    var_s = args[1].strip() or "x"
    expr, var, deps, _is_fn = _expr_of(cons, args[0], var_s)
    from .cas import _function_refs
    for extra in _function_refs(cons, args[2]):      # 值若引用数值元素（如 Substitute[x^2,x,n]）
        if extra not in deps:                        # 既作为依赖，也在 state 里按当前值解析
            deps.append(extra)

    def _parsed():
        e2, v2, _dp, _fn = _expr_of(cons, args[0], var_s)
        try:
            val2 = _parse_sympy(args[2].replace("∞", "oo"), {var_s: v2}, cons)
        except (SyntaxError, TypeError, ValueError, AttributeError, KeyError):
            val2 = eval_number(cons, args[2])
        return e2.subs(v2, val2), v2

    res, _v = _parsed()
    f = _float_or_none(res)
    if f is not None:                                # 类型在创建时确定（数值 vs 函数），值随依赖刷新
        def _state_num(d):
            r2, _v2 = _parsed()
            f2 = _float_or_none(r2)
            if f2 is None:
                raise GeoError("Substitute 结果不再是数值（依赖已变化）")
            return {"value": f2}
        return _mk(cons, GeoNumber, "number", defn, deps, _state_num)

    def _state_fn(d):
        r2, v2 = _parsed()
        return {"expr": sympy.simplify(r2), "xsym": v2}
    return _mk(cons, GeoFunction, "function", defn, deps, _state_fn)


# ---------------------------------------------------------------------------
# SolveODE（复用 CAS 引擎的预处理与 dsolve）
# ---------------------------------------------------------------------------

def _cmd_solveode(cons, defn, args):
    """``SolveODE[微分方程, 自变量?]`` → 通解文本（复用 CAS 引擎的实现）。"""
    if not 1 <= len(args) <= 3:
        raise GeoError("SolveODE 需要 微分方程（可选自变量），如 SolveODE[y'=y]")
    from .cas import CASEngine
    try:
        text, _val = CASEngine(cons)._c_solveode(list(args))
    except GeoError:
        raise
    except Exception as ex:  # 求解失败：明确报错
        raise GeoError("SolveODE 无法求解：" + str(ex)[:60])
    return _text_element(cons, defn, text)
