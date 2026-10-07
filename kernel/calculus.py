"""微积分与符号计算命令（P2 结构拆分：从 commands.py 抽出）。

覆盖：Derivative / Integral / Root / Extremum / Limit 风格求解、SolveIneq、
序列与数论（Sequence / IsPrime / Divisors / FactorsList）、正态分布、
黎曼和（SumRect）、FitExpr 及解法格式化助手。

依赖 `cmd_util`（参数解析/元素构造）与 `elements`/`parser`/`tolerance`；
**不依赖命令注册表**；`commands.py` 通过 re-export 与命令表引用这些实现。
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .elements import GeoBoolean, GeoError, GeoFunction, GeoList, GeoNumber, GeoPoint, GeoResult, GeoSumRect
from .tolerance import COARSE, COORD, LOOSE, ROOT_TOL
from .parser import eval_number
from .cmd_util import (label_of, _NESTED_CALL_RE, _NESTED_MAX_DEPTH, _auto, _elem_or_point, _is_segment_el, _label_of, _list_arg, _lookup, _mk, _nested_depth, _num_deps, _num_list_items, _num_series, _point_arg, _resolve, _tuple_parts_any)


__all__ = [
    "_fmt",
    "_feval",
    "_roots_1d",
    "_cmd_of",
    "_cmd_derivative",
    "_cmd_integral",
    "_cmd_root",
    "_root_state",
    "_cmd_extremum",
    "_cmd_rectsum",
    "_int_values",
    "_cmd_isprime",
    "_cmd_divisors",
    "_cmd_factorslist",
    "_parse_sympy",
    "_fit_expr",
    "_cmd_fitexpr",
    "_cmd_sequence",
    "_cmd_normaldist",
    "_cmd_solveineq",
    "_fmt_sol",
    "_fmt_sol_num",
]


def _fmt(v: float) -> str:
    s = ("%.6f" % v).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"

def _feval(f, xi: float):
    """函数 f 在 xi 处的数值。"""
    return f._eval1(xi)

def _roots_1d(expr, x, xmin: float = -60.0, xmax: float = 60.0, n: int = 900):
    """求 expr(x)=0 在区间内的全部实根（符号优先，数值兜底）。返回排序后的 x 列表。"""
    import sympy
    roots: List[float] = []
    # 符号解（多项式等）
    try:
        sol = sympy.solve(expr, x)
        for s in sol:
            v = complex(sympy.N(s))
            if abs(v.imag) < COORD and xmin - COARSE <= v.real <= xmax + COARSE:
                roots.append(float(v.real))
    except Exception:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
        pass
    if roots:
        roots = sorted(set(round(r, 9) for r in roots))
        return roots
    # 数值扫描 + 二分
    import numpy as np
    try:
        lam = sympy.lambdify(x, expr, "numpy")
        xs = np.linspace(xmin, xmax, n)
        ys = lam(xs)
    except Exception:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
        return []
    for i in range(n - 1):
        y1, y2 = ys[i], ys[i + 1]
        if not (np.isfinite(y1) and np.isfinite(y2)):
            continue
        if y1 == 0.0:
            roots.append(float(xs[i]))
        elif y1 * y2 < 0.0:
            a, b = float(xs[i]), float(xs[i + 1])
            fa = y1
            for _ in range(60):
                mid = (a + b) / 2.0
                fm = float(lam(mid))
                if not np.isfinite(fm):
                    break
                if fa * fm <= 0.0:
                    b, fb = mid, fm
                else:
                    a, fa = mid, fm
                if abs(b - a) < ROOT_TOL:
                    break
            roots.append((a + b) / 2.0)
    # 去重
    dedup: List[float] = []
    for r in sorted(roots):
        if not dedup or abs(r - dedup[-1]) > LOOSE:
            dedup.append(r)
    return dedup

def _cmd_of(defn: str) -> str:
    """从 defn（label=cmd）中取出 cmd 部分。"""
    idx = defn.find("=")
    if idx == -1:
        idx = defn.find(":")
    return defn[idx + 1:].strip() if idx != -1 else defn

def _cmd_derivative(cons, defn, args):
    if len(args) not in (1, 2):
        raise GeoError("Derivative 需要 函数 和 可选的阶数")
    f = _resolve(cons, args[0], ("function",))
    n = 1
    if len(args) == 2:
        n = int(eval_number(cons, args[1]))
        if n < 1:
            raise GeoError("导数阶数必须 >= 1")
    return _mk(cons, GeoFunction, "function", defn, [f],
               lambda d: {"expr": __import__("sympy").diff(d[0].expr, d[0].xsym, n)})

def _cmd_integral(cons, defn, args):
    if len(args) == 1:
        f = _resolve(cons, args[0], ("function",))
        return _mk(cons, GeoFunction, "function", defn, [f],
                   lambda d: {"expr": __import__("sympy").integrate(d[0].expr, d[0].xsym)})
    if len(args) == 3:
        f = _resolve(cons, args[0], ("function",))
        dyn = []
        a_fixed = b_fixed = None
        a_el = _lookup(cons, args[1])
        b_el = _lookup(cons, args[2])
        if a_el is not None and a_el.kind == "number":
            dyn.append(a_el)
        else:
            a_fixed = eval_number(cons, args[1])
        if b_el is not None and b_el.kind == "number":
            dyn.append(b_el)
        else:
            b_fixed = eval_number(cons, args[2])
        deps = [f] + dyn

        def fn(d):
            import sympy
            fn0 = d[0]
            x = fn0.xsym
            i = 1
            a = a_fixed if a_fixed is not None else d[i].value if i < len(d) else a_fixed
            if a_fixed is None:
                a = d[i].value
                i += 1
            b = b_fixed if b_fixed is not None else d[i].value
            try:
                v = sympy.integrate(fn0.expr, (x, a, b))
                return {"value": float(sympy.N(v))}
            except Exception:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
                raise GeoError("定积分无法计算")
        return _mk(cons, GeoNumber, "number", defn, deps, fn)
    raise GeoError("Integral 需要 函数 或 函数+上下限")

def _cmd_root(cons, defn, args):
    f = _resolve(cons, args[0], ("function",))
    if len(args) == 1:
        # 全部根中最小的一个
        return _mk(cons, GeoPoint, "point", defn, [f], lambda d: _root_state(d[0], None, None))
    if len(args) == 2:
        a = eval_number(cons, args[1])
        return _mk(cons, GeoPoint, "point", defn, [f], lambda d: _root_state(d[0], a, None))
    if len(args) == 3:
        a = eval_number(cons, args[1])
        b = eval_number(cons, args[2])
        return _mk(cons, GeoPoint, "point", defn, [f], lambda d: _root_state(d[0], a, b))
    raise GeoError("Root 需要 函数 或 函数+起点 或 函数+区间")

def _root_state(f, a, b):
    import sympy
    x = f.xsym
    roots = _roots_1d(f.expr, x)
    if a is not None and b is not None:
        cand = [r for r in roots if a - COORD <= r <= b + COORD]
        if not cand:
            raise GeoError("区间内没有根")
        r = cand[0]
    elif a is not None:
        if not roots:
            raise GeoError("没有根")
        r = min(roots, key=lambda t: abs(t - a))
    else:
        if not roots:
            raise GeoError("没有根")
        r = roots[0]
    y = _feval(f, r)
    if y is None:
        raise GeoError("根处函数未定义")
    return {"x": r, "y": y}

def _cmd_extremum(cons, defn, args, idx=None):
    if len(args) != 3:
        raise GeoError("Extremum 需要 函数 和 区间端点")
    f = _resolve(cons, args[0], ("function",))
    a = eval_number(cons, args[1])
    b = eval_number(cons, args[2])

    def build(i: int) -> GeoPoint:
        el = GeoPoint("", defn)
        el.free = False
        el._i = i

        def compute(deps):
            import sympy
            fn0 = deps[0]
            x = fn0.xsym
            diff = sympy.diff(fn0.expr, x)
            roots = [r for r in _roots_1d(diff, x, a, b) if a - COORD <= r <= b + COORD]
            if el._i >= len(roots):
                raise GeoError("极值点数量不足")
            r = roots[el._i]
            y = _feval(fn0, r)
            if y is None:
                raise GeoError("极值点处函数未定义")
            return {"x": r, "y": y}
        el.set_deps([f], compute)
        return el

    import sympy
    roots = [r for r in _roots_1d(sympy.diff(f.expr, f.xsym), f.xsym, a, b) if a - COORD <= r <= b + COORD]
    if not roots:
        raise GeoError("区间内没有极值点")
    if idx is not None:
        el = build(idx)
        el.label = _label_of(defn)
        el.defn = defn + "#" + str(idx)
        return cons.add(el)
    label = _label_of(defn)
    cmd = _cmd_of(defn)
    created = []
    for i in range(len(roots)):
        li = label if i == 0 else label + str(i)
        d = li + "=" + cmd + "#" + str(i)
        el = build(i)
        el.label = li
        el.defn = d
        created.append(cons.add(el))
    return created

def _cmd_rectsum(cons, defn, args, variant):
    """矩形/梯形逼近：参数 函数, a, b, n（n 可为滑块引用）[, 采样 left/right/mid/0..1]。variant 见命令。"""
    if len(args) not in (4, 5):
        raise GeoError("黎曼和需要 函数, 下限, 上限, 分割数 n（可选 采样位置 left/right/mid/0..1）")
    f = _resolve(cons, args[0], ("function",))
    a = eval_number(cons, args[1])
    b = eval_number(cons, args[2])
    if b <= a:
        raise GeoError("上限必须大于下限")
    deps = [f]
    n_el = None
    n_txt = args[3].strip()
    if n_txt in cons.elements and cons.elements[n_txt].kind == "number":
        n_el = cons.elements[n_txt]
        deps.append(n_el)
        n_val = 1
    else:
        n_val = int(eval_number(cons, n_txt))
        if n_val < 1 or n_val > 1000:
            raise GeoError("分割数 n 需在 1..1000")
    pos = None
    if len(args) == 5:
        p = args[4].strip()
        if p == "left":
            pos = 0.0
        elif p == "right":
            pos = 1.0
        elif p == "mid":
            pos = 0.5
        else:
            pos = float(eval_number(cons, p))
            if not (0.0 <= pos <= 1.0):
                raise GeoError("采样位置需在 0..1（或 left/right/mid）")
    if variant == "rect":
        mode = "left"
        use_pos = None
        if len(args) == 5 and pos is not None:
            if abs(pos - 0.5) < COORD:
                mode = "mid"
            elif abs(pos - 1.0) < COORD:
                mode = "right"
            elif abs(pos) < COORD:
                mode = "left"
            else:
                mode = "pos"
                use_pos = pos
    else:
        mode = variant
        use_pos = None
    el = GeoSumRect(label_of(defn), defn)
    el.free = False
    el.mode = mode

    def fn(d):
        import numpy as np
        n = int(round(d[1].value)) if n_el is not None else n_val
        n = max(1, min(1000, n))
        w = (b - a) / n

        def ev(x):
            return d[0]._eval1(x)
        rects = []
        total = 0.0
        for i in range(n):
            x0 = a + i * w
            x1 = x0 + w
            if variant == "trap":
                y0 = ev(x0)
                y1 = ev(x1)
                if y0 is None or y1 is None:
                    continue
                rects.append([x0, x1, y0, y1])
                total += w * (y0 + y1) / 2.0
            elif variant in ("lower", "upper"):
                ys = [ev(float(x)) for x in np.linspace(x0, x1, 9)]
                ys = [v for v in ys if v is not None]
                if not ys:
                    continue
                y = min(ys) if variant == "lower" else max(ys)
                rects.append([x0, x1, y])
                total += w * y
            else:
                if mode == "left":
                    xi = x0
                elif mode == "right":
                    xi = x1
                elif mode == "mid":
                    xi = (x0 + x1) / 2.0
                else:
                    xi = x0 + (x1 - x0) * use_pos
                y = ev(xi)
                if y is None:
                    continue
                rects.append([x0, x1, y])
                total += w * y
        # 返回完整 state（不能只写 el 后 return {}，否则计算记忆命中时新构造会空 ✗）
        return {"rects": rects, "value": float(total), "n": n, "a": a, "b": b}

    el.set_deps(deps, fn)
    el.compute()
    return cons.add(el)

def _int_values(cons, args):
    """数论输入：支持多值或 {列表} → 整数列表。"""
    items = []
    for a in args:
        s = a.strip()
        if s.startswith("{"):
            L = _list_arg(cons, a)
            items.extend(int(round(float(v))) for v in L.items)
        elif s in cons.elements and cons.elements[s].kind == "list":
            items.extend(int(round(float(v))) for v in cons.elements[s].items)
        else:
            items.append(int(round(eval_number(cons, a))))
    return items

def _cmd_isprime(cons, defn, args):
    vals = _int_values(cons, args)
    if len(vals) != 1:
        raise GeoError("IsPrime 需要一个整数")
    import sympy
    el = GeoBoolean(label_of(defn), defn)
    el.free = False
    el.value = bool(sympy.isprime(vals[0]))
    el.detail = ""
    return cons.add(el)

def _cmd_divisors(cons, defn, args):
    vals = _int_values(cons, args)
    if len(vals) != 1 or vals[0] < 1:
        raise GeoError("Divisors 需要正整数")
    import sympy
    ds = sorted(sympy.divisors(vals[0]))
    el = GeoList(label_of(defn), defn, [float(v) for v in ds], "number")
    el.free = False
    return cons.add(el)

def _cmd_factorslist(cons, defn, args):
    """FactorsList[n]：质因数（含重数）列表，如 420 → {2,2,3,5,7}。"""
    vals = _int_values(cons, args)
    if len(vals) != 1 or vals[0] < 2:
        raise GeoError("FactorsList 需要 ≥2 的整数")
    import sympy
    out = []
    for p, e in sorted(sympy.factorint(vals[0]).items()):
        out.extend([float(p)] * e)
    el = GeoList(label_of(defn), defn, out, "number")
    el.free = False
    return cons.add(el)

def _parse_sympy(body, symbols, cons=None):
    """sympy 解析（^ 与隐式乘法），可引用绘图区数值对象。"""
    import sympy
    ld = dict(symbols)
    ld.update({"e": sympy.E, "pi": sympy.pi, "π": sympy.pi,
               "ln": sympy.log, "log": sympy.log, "log10": lambda a: sympy.log(a, 10),
               "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan, "exp": sympy.exp,
               "sqrt": sympy.sqrt, "abs": sympy.Abs})
    if cons is not None:
        for lab, el in cons.elements.items():
            if el.kind == "number":
                ld[lab] = sympy.Float(el.value)
    return sympy.parsing.sympy_parser.parse_expr(
        body, local_dict=ld,
        transformations=(sympy.parsing.sympy_parser.standard_transformations
                         + (sympy.parsing.sympy_parser.implicit_multiplication_application,
                            sympy.parsing.sympy_parser.convert_xor)))

def _fit_expr(cons, defn, body):
    """Desmos 风格回归：y~a*x+b。数据 = 绘图区所有自由点，最小二乘拟合。"""
    import sympy
    m = re.match(r"^\s*y\s*~\s*(.+)$", body)
    if not m:
        raise GeoError("回归需形如 y~a*x+b")
    expr_str = m.group(1)
    x = sympy.Symbol("x")
    # 独立解析：回归参数（a,b,c…）必须是自由符号，不把已有数值对象当常量
    expr = sympy.parsing.sympy_parser.parse_expr(
        expr_str, local_dict={"x": x},
        transformations=(sympy.parsing.sympy_parser.standard_transformations
                         + (sympy.parsing.sympy_parser.implicit_multiplication_application,
                            sympy.parsing.sympy_parser.convert_xor)))
    params = sorted(expr.free_symbols - {x}, key=str)
    if not params:
        raise GeoError("回归表达式中未发现参数（如 a, b）")
    data = [(e.x, e.y) for lab, e in cons.elements.items()
            if e.kind == "point" and e.free and not lab.startswith("_")]
    if len(data) < 2:
        raise GeoError("至少需要两个自由点作为拟合数据（先创建点，如 A=(1,2) B=(2,4)）")
    import numpy as np
    try:
        import scipy.optimize as opt
    except Exception:  # 可选依赖缺失：功能降级
        raise GeoError("缺少 scipy，无法拟合")
    f_num = sympy.lambdify((x,) + tuple(params), expr, "numpy")
    xs = np.array([p[0] for p in data])
    ys = np.array([p[1] for p in data])

    def resid(pvals):
        return f_num(xs, *pvals) - ys

    best = None
    for guess in ([1.0] * len(params), [0.0] * len(params)):
        try:
            res = opt.least_squares(resid, guess)
            if best is None or res.cost < best.cost:
                best = res
        except Exception:  # 防御性捕获：该分支失败不应中断用户操作
            continue
    if best is None:
        raise GeoError("拟合失败")
    vals = dict(zip(params, best.x))
    expr_sub = expr.subs(vals)
    label = label_of(defn) if defn and ("=" in defn or ":" in defn) else ""
    if not label:
        label = cons.auto_label("function")
    fdefn = label + "(x)=" + sympy.sstr(expr_sub)
    f_el = GeoFunction(label, fdefn)
    try:
        f_el.configure(cons, sympy.sstr(expr_sub), [])
    except Exception:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
        raise GeoError("无法解析拟合表达式: " + expr_str)
    f_el.fit_msg = "拟合 " + expr_str + "：" + ", ".join(
        "%s=%s" % (pname, _fmt(float(vals[pname]))) for pname in params)
    created = [cons.add(f_el)]
    for pname in params:
        plab = str(pname)
        if plab in cons.elements:
            continue
        created.append(cons.add(GeoNumber(plab, plab + "=" + _fmt(float(vals[pname])), float(vals[pname]))))
    return created

def _cmd_fitexpr(cons, defn, args):
    """FitExp[y~a*x+b]：命令形式的回归拟合。"""
    if len(args) != 1:
        raise GeoError("FitExpr 需要如 y~a*x+b 的表达式（数据取当前所有自由点）")
    return _fit_expr(cons, defn, args[0])

def _cmd_sequence(cons, defn, args):
    """Sequence[expr, var, a, b] → 数值列表（可带步长）。"""
    if len(args) not in (4, 5):
        raise GeoError("Sequence 需要 表达式、变量、起点、终点（可选步长）")
    expr_s, var_s, a_s, b_s = args[0], args[1], args[2], args[3]
    step = eval_number(cons, args[4]) if len(args) == 5 else 1.0
    a = eval_number(cons, a_s)
    b = eval_number(cons, b_s)
    if step == 0:
        raise GeoError("步长不能为 0")
    import sympy
    import numpy as np
    var = sympy.Symbol(var_s)
    e = _parse_sympy(expr_s, {var_s: var}, cons)
    lam = sympy.lambdify(var, e, "numpy")
    vals = []
    point_mode = False
    i = a
    while i <= b + COORD:
        try:
            v = np.asarray(lam(i), dtype=float)
        except Exception:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
            raise GeoError("序列元素无法求值")
        if v.ndim == 1 and v.shape[0] == 2:
            point_mode = True
            vals.append((float(v[0]), float(v[1])))
        else:
            vals.append(float(v))
        i += step
    el = GeoList(label_of(defn), defn, vals, "point" if point_mode else "number")
    el.free = False
    return cons.add(el)

def _cmd_normaldist(cons, defn, args):
    """NormalDist[μ, σ] → 正态密度函数（可绘图/积分）。"""
    if len(args) != 2:
        raise GeoError("NormalDist 需要 均值、标准差")
    mu = eval_number(cons, args[0])
    sigma = eval_number(cons, args[1])
    if sigma <= 0:
        raise GeoError("标准差必须 > 0")
    import sympy
    el = GeoFunction(label_of(defn), defn)
    el.free = False
    x = sympy.Symbol("x")

    def fn(d):
        return {"expr": 1 / (sigma * sympy.sqrt(2 * sympy.pi)) * sympy.exp(-(x - mu) ** 2 / (2 * sigma ** 2)),
                "xsym": x, "body": "", "_lamb": None}
    el.set_deps([], fn)
    el.compute()
    return cons.add(el)

def _cmd_solveineq(cons, defn, args):
    """SolveIneq[expr, 变量] → 解集（文本）。支持 x^2<4、x>2 等。"""
    if len(args) not in (1, 2):
        raise GeoError("SolveIneq 需要 不等式（可选变量）")
    import sympy
    from sympy.core.relational import Relational
    expr_s = args[0]
    var_s = args[1] if len(args) == 2 else "x"
    var = sympy.Symbol(var_s)
    expr = _parse_sympy(expr_s, {var_s: var}, cons)
    if not isinstance(expr, Relational):
        raise GeoError("SolveIneq 需要一个不等式，如 x^2<4")
    try:
        sol = sympy.reduce_inequalities(expr, var)
    except Exception as e:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
        raise GeoError("无法求解该不等式: " + repr(e))
    el = GeoResult(label_of(defn), defn)
    el.free = False
    el.text = _fmt_sol(sol, var)
    return cons.add(el)

def _fmt_sol(sol, x) -> str:
    """解集 → 区间表示：(-2 < x) & (x < 2) → (-2, 2)；x > 2 → (2, +∞)。"""
    import sympy
    from sympy.core.relational import Relational
    if isinstance(sol, sympy.Or):
        parts = [_fmt_sol(a, x) for a in sol.args]
        parts.sort(key=_sol_lo)
        return " ∪ ".join(parts)
    if isinstance(sol, sympy.And):
        ineqs = list(sol.args)
    elif isinstance(sol, Relational):
        ineqs = [sol]
    else:
        return str(sol).replace("**", "^")
    lo, hi = -sympy.oo, sympy.oo
    lo_open = hi_open = True
    for r in ineqs:
        if not isinstance(r, Relational):
            continue
        op = r.rel_op
        if r.lhs == x:
            val = r.rhs
            if op in ("<", "<="):
                hi = sympy.Min(hi, val)
                hi_open = (op == "<")
            else:
                lo = sympy.Max(lo, val)
                lo_open = (op == ">")
        elif r.rhs == x:
            val = r.lhs
            if op in ("<", "<="):
                lo = sympy.Max(lo, val)
                lo_open = (op == "<")
            else:
                hi = sympy.Min(hi, val)
                hi_open = (op == ">")
    lo_v = "-∞" if lo == -sympy.oo else _fmt_sol_num(lo)
    hi_v = "+∞" if hi == sympy.oo else _fmt_sol_num(hi)
    return ("(" if lo_open else "[") + lo_v + ", " + hi_v + (")" if hi_open else "]")

def _fmt_sol_num(v) -> str:
    try:
        f = float(sympy.N(v))
        s = ("%.4g" % f)
        return s
    except Exception:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
        return str(v).replace("**", "^")
