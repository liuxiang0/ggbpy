"""CAS 单元表引擎（P2）。

功能：
- 单元表：每条输入一个单元格（#N 引用前序单元结果，# 引用上一个）
- 符号命令：Expand / Factor / Simplify / Solve / NSolve / Limit /
           Derivative / Integral / SolveODE / PartialFractions / Substitute
- 命名空间：a := 5（数值，联动创建 GeoNumber）、f(x) := x^2（联动创建 GeoFunction）
- 任意常数：定积分补 +c1；ODE 解 C1→c1、C2→c2
- 引用绘图区对象：函数 f(x)、数值 r 可直接出现在 CAS 表达式中

实现：SymPy 符号计算 + 与 Construction 的双向联动。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import sympy

from .elements import GeoError, GeoFunction, GeoNumber
from .tolerance import EPSILON  # 统一数值容差（见 kernel/tolerance.py）

_X = sympy.Symbol("x", real=True)

_TRANS = (
    sympy.parsing.sympy_parser.standard_transformations
    + (sympy.parsing.sympy_parser.implicit_multiplication_application,
       sympy.parsing.sympy_parser.convert_xor,
       sympy.parsing.sympy_parser.convert_equals_signs)
)


def _fmt(e) -> str:
    """sympy 结果 → 展示字符串：Eq → =，** → ^，C1 → c1。"""
    if isinstance(e, sympy.Eq):
        return _fmt(e.lhs) + " = " + _fmt(e.rhs)
    if isinstance(e, (list, tuple)):
        return "{" + ", ".join(_fmt(x) for x in e) + "}"
    s = str(e)
    s = s.replace("**", "^")
    s = re.sub(r"\bC(\d+)\b", lambda m: "c" + m.group(1), s)
    return s


def _num_fmt(v: float) -> str:
    if abs(v) < EPSILON:
        return "0"
    s = ("%.10g" % v)
    return s


def _split_args(inner: str) -> List[str]:
    """按顶层逗号切分命令参数（跟踪括号嵌套）。"""
    parts: List[str] = []
    depth = 0
    cur = ""
    for ch in inner:
        if ch in "([":
            depth += 1
            cur += ch
        elif ch in ")]":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


class CASEngine:
    def __init__(self, cons) -> None:
        self.cons = cons
        self.cells: List[Dict[str, Any]] = []
        self.names: Dict[str, Any] = {}   # CAS 命名空间：name -> sympy 表达式

    def clear(self) -> None:
        self.cells = []
        self.names = {}

    # ------------------------------------------------------------------
    # 解析辅助
    # ------------------------------------------------------------------
    def _local_dict(self) -> Tuple[dict, dict]:
        """构造 sympy 解析命名空间。返回 (local_dict, function_map)。"""
        ld: Dict[str, Any] = {
            "x": _X, "e": sympy.E, "pi": sympy.pi,
            "ln": sympy.log, "log": sympy.log,
            "log10": lambda a: sympy.log(a, 10),
            "diff": sympy.diff, "sqrt": sympy.sqrt,
            "abs": sympy.Abs, "sin": sympy.sin, "cos": sympy.cos,
            "tan": sympy.tan, "exp": sympy.exp,
            "asin": sympy.asin, "acos": sympy.acos, "atan": sympy.atan,
            "sinh": sympy.sinh, "cosh": sympy.cosh, "tanh": sympy.tanh,
            "floor": sympy.floor, "ceil": sympy.ceiling, "sign": sympy.sign,
        }
        for k, v in self.names.items():
            ld[k] = v
        fmap: Dict[str, Any] = {}
        for lab, el in self.cons.elements.items():
            if el.kind == "number":
                ld[lab] = sympy.Float(el.value)
            elif el.kind == "function":
                ld[lab] = sympy.Function(lab)
                fmap[lab] = el
        return ld, fmap

    def _parse(self, s: str) -> Any:
        """解析 CAS 表达式（含 CAS 命名空间与绘图区对象引用）。"""
        s = s.strip()
        if not s:
            raise GeoError("空表达式")
        ld, fmap = self._local_dict()
        expr = sympy.parsing.sympy_parser.parse_expr(s, local_dict=ld, transformations=_TRANS)
        for lab, el in fmap.items():
            fn = sympy.Function(lab)
            expr = expr.replace(fn, sympy.Lambda(el.xsym, el.expr))
            if expr == fn:
                expr = el.expr
        return expr

    def _resolve_refs(self, text: str) -> str:
        """把 #N / # 替换为前序单元格的输出表达式。"""
        def rep_abs(m):
            n = int(m.group(1))
            if n < 1 or n > len(self.cells):
                raise GeoError("引用的单元格 #" + str(n) + " 不存在")
            cell = self.cells[n - 1]
            if cell.get("sym") is None:
                raise GeoError("单元格 #" + str(n) + " 没有可用结果")
            if isinstance(cell["sym"], (list, tuple, sympy.Tuple)):
                raise GeoError("单元格 #" + str(n) + " 是解集，不能直接引用")
            return "(" + _fmt(cell["sym"]) + ")"
        text = re.sub(r"#(\d+)", rep_abs, text)
        if "#" in text:
            if not self.cells or self.cells[-1].get("sym") is None:
                raise GeoError("没有上一个单元格的结果")
            if isinstance(self.cells[-1]["sym"], (list, tuple, sympy.Tuple)):
                raise GeoError("上一个单元格是解集，不能直接引用")
            text = text.replace("#", "(" + _fmt(self.cells[-1]["sym"]) + ")")
        return text

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def evaluate(self, text: str) -> Dict[str, Any]:
        """执行一条 CAS 输入，追加单元格并返回该单元格。"""
        cell: Dict[str, Any] = {"id": len(self.cells) + 1, "input": text.strip(), "output": "", "error": None, "sym": None}
        self.cells.append(cell)
        try:
            out, sym = self._run(text)
            cell["output"] = out
            cell["sym"] = sym
        except GeoError as e:
            cell["error"] = str(e)
        except Exception as e:  # 防御性捕获：该分支失败不应中断用户操作
            cell["error"] = "错误: " + repr(e)
        return cell

    def _run(self, text: str) -> Tuple[str, Any]:
        text = text.strip()
        text = self._resolve_refs(text)
        if not text:
            raise GeoError("空输入")

        # 1) 函数赋值：f(x) := expr（先于普通赋值判断）
        fm = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*x\s*\)\s*(:=|=)\s*(.+)$", text, re.S)
        if fm:
            fname, body = fm.group(1), fm.group(3)
            expr = self._parse(body)
            free = expr.free_symbols - {_X}
            if free:
                raise GeoError("函数中出现未知变量: " + ", ".join(sorted(str(s) for s in free)))
            # 联动：在绘图区创建函数对象（入撤销历史）
            if fname in self.cons.elements:
                raise GeoError("绘图区已存在对象 " + fname)
            self.cons.push_history()
            el = GeoFunction(fname, fname + "(x)=" + body)
            el.configure(self.cons, body, _function_refs(self.cons, body))
            self.cons.add(el)
            self.names[fname] = sympy.Lambda(_X, expr)
            return "已创建函数 " + fname + "(x) := " + body, el.expr

        # 2) 赋值：name := expr / name = expr
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(:=|=)\s*(.+)$", text, re.S)
        if m:
            name, op, rhs = m.group(1), m.group(2), m.group(3)
            expr = self._parse(rhs)
            if op == "=" and name == "x":
                # x=... 视为方程，不赋值
                return _fmt(expr), expr
            self.names[name] = expr
            out = _fmt(expr)
            # 联动：无自由变量的数值 → 绘图区创建 GeoNumber（入撤销历史）
            if not expr.free_symbols and name not in self.cons.elements:
                try:
                    v = float(sympy.N(expr))
                    self.cons.push_history()
                    self.cons.add(GeoNumber(name, name + "=" + _num_fmt(v), v))
                    out += "   已创建数值 " + name
                except Exception:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
                    pass
            return out, expr

        # 2) 命令调用
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\[(.*)\]$", text, re.S)
        if m:
            name, inner = m.group(1), m.group(2)
            args = _split_args(inner)
            return self._command(name, args)

        # 3) 裸表达式
        expr = self._parse(text)
        if not expr.free_symbols:
            try:
                v = float(sympy.N(expr))
                return _num_fmt(v), expr
            except Exception:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
                pass
        return _fmt(expr), expr

    # ------------------------------------------------------------------
    # 符号命令
    # ------------------------------------------------------------------
    def _command(self, name: str, args: List[str]) -> Tuple[str, Any]:
        cname = name.lower()
        if cname == "expand":
            return self._c_expand(args)
        if cname == "factor":
            return self._c_factor(args)
        if cname in ("simplify", "simpl"):
            return self._c_simplify(args)
        if cname == "solve":
            return self._c_solve(args)
        if cname == "nsolve":
            return self._c_nsolve(args)
        if cname == "limit":
            return self._c_limit(args)
        if cname == "derivative":
            return self._c_derivative(args)
        if cname == "integral":
            return self._c_integral(args)
        if cname == "solveode":
            return self._c_solveode(args)
        if cname == "partialfractions":
            return self._c_apart(args)
        if cname == "substitute":
            return self._c_substitute(args)
        raise GeoError("未知 CAS 命令: " + name + "（支持: Expand Factor Simplify Solve NSolve Limit Derivative Integral SolveODE PartialFractions Substitute）")

    def _arg(self, args: List[str], i: int, what: str) -> str:
        if i >= len(args) or not args[i]:
            raise GeoError(what + " 参数缺失")
        return args[i]

    def _c_expand(self, args: List[str]):
        expr = self._parse(self._arg(args, 0, "Expand"))
        return _fmt(sympy.expand(expr)), sympy.expand(expr)

    def _c_factor(self, args: List[str]):
        expr = self._parse(self._arg(args, 0, "Factor"))
        return _fmt(sympy.factor(expr)), sympy.factor(expr)

    def _c_simplify(self, args: List[str]):
        expr = self._parse(self._arg(args, 0, "Simplify"))
        return _fmt(sympy.simplify(expr)), sympy.simplify(expr)

    def _c_solve(self, args: List[str]):
        eq_s = self._arg(args, 0, "Solve")
        var = _X
        if len(args) >= 2:
            var = self._parse(args[1])
        eq = self._parse_eq(eq_s)
        try:
            sols = sympy.solve(eq, var)
        except Exception:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
            raise GeoError("Solve 无法求解该方程")
        if sols is None or len(sols) == 0:
            return "{ }", sols
        if not isinstance(sols, list):
            sols = [sols]
        out = ", ".join(_fmt(var) + " = " + _fmt(s) for s in sols)
        return "{" + out + "}", sols

    def _parse_eq(self, s: str):
        s = s.strip()
        m = re.match(r"^(.*?)=(.*)$", s)
        if m and m.group(1).strip() != "":
            lhs = self._parse(m.group(1))
            rhs = self._parse(m.group(2))
            return sympy.Eq(lhs, rhs)
        return self._parse(s)

    def _c_nsolve(self, args: List[str]):
        eq_s = self._arg(args, 0, "NSolve")
        eq = self._parse_eq(eq_s)
        diff = sympy.expand(eq.lhs - eq.rhs) if isinstance(eq, sympy.Eq) else eq
        from .commands import _roots_1d
        roots = _roots_1d(diff, _X)
        if not roots:
            raise GeoError("没有找到实根")
        out = "; ".join("x ≈ " + _num_fmt(r) for r in roots)
        return out, roots

    def _c_limit(self, args: List[str]):
        expr = self._parse(self._arg(args, 0, "Limit"))
        var = _X
        if len(args) >= 2:
            var = self._parse(args[1])
        a = self._parse(self._arg(args, 2, "Limit 的取值"))
        res = sympy.limit(expr, var, a)
        return _fmt(res), res

    def _c_derivative(self, args: List[str]):
        expr = self._parse(self._arg(args, 0, "Derivative"))
        var = _X
        if len(args) >= 2:
            var = self._parse(args[1])
        n = 1
        if len(args) >= 3:
            n = int(self._parse(args[2]))
        res = sympy.diff(expr, var, n)
        return _fmt(res), res

    def _c_integral(self, args: List[str]):
        expr = self._parse(self._arg(args, 0, "Integral"))
        var = _X
        if len(args) >= 2:
            var = self._parse(args[1])
        if len(args) >= 4:
            a = self._parse(args[2])
            b = self._parse(args[3])
            res = sympy.integrate(expr, (var, a, b))
            return _fmt(res), res
        res = sympy.integrate(expr, var)
        # 不定积分补任意常数 c1
        return _fmt(res) + " + c1", res

    def _c_solveode(self, args: List[str]):
        eq_s = self._arg(args, 0, "SolveODE")
        # y' = f(x,y) 预处理：y' → diff(y(x),x)，y'' → diff(diff(...))，裸 y → y(x)
        def _deriv_repl(m):
            var = m.group(1)
            inner = var + "(x)"
            for _ in range(len(m.group(2))):
                inner = "diff(" + inner + ",x)"
            return inner
        pre = re.sub(r"([A-Za-z])(\'+)", _deriv_repl, eq_s)
        pre = re.sub(r"\by(?!\()", "y(x)", pre)
        var = _X
        if len(args) >= 3:
            var = self._parse(args[2])
        elif len(args) >= 2:
            var = self._parse(args[1])
        ld, _fmap = self._local_dict()
        ld["diff"] = sympy.diff
        y_sym = sympy.Function("y")
        ld2 = dict(ld)
        ld2["y"] = y_sym
        # ODE 解析禁用隐式乘法（避免 diff( 被当作乘法）
        trans_ode = (sympy.parsing.sympy_parser.standard_transformations
                     + (sympy.parsing.sympy_parser.convert_xor,
                        sympy.parsing.sympy_parser.convert_equals_signs))
        eq = sympy.parsing.sympy_parser.parse_expr(pre, local_dict=ld2, transformations=trans_ode)
        if isinstance(eq, sympy.Eq):
            pass
        else:
            eq = sympy.Eq(eq, 0)
        try:
            sol = sympy.dsolve(eq, y_sym(var))
        except Exception as e:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
            raise GeoError("SolveODE 无法求解: " + repr(e))
        return _fmt(sol), sol

    def _c_apart(self, args: List[str]):
        expr = self._parse(self._arg(args, 0, "PartialFractions"))
        var = _X
        if len(args) >= 2:
            var = self._parse(args[1])
        res = sympy.apart(expr, var)
        return _fmt(res), res

    def _c_substitute(self, args: List[str]):
        expr = self._parse(self._arg(args, 0, "Substitute"))
        var = self._parse(self._arg(args, 1, "Substitute 的变量"))
        val = self._parse(self._arg(args, 2, "Substitute 的值"))
        res = expr.subs(var, val)
        return _fmt(res), res


def _function_refs(cons, body: str) -> List:
    """函数体中引用的已有元素（与 commands 模块一致）。"""
    refs = []
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", body):
        if tok in ("x", "e", "pi", "sin", "cos", "tan", "exp", "log", "ln", "sqrt", "abs",
                   "log10", "asin", "acos", "atan", "sinh", "cosh", "tanh", "floor", "ceil", "round", "sign"):
            continue
        el = cons.elements.get(tok)
        if el is not None and el.kind in ("number", "function") and el not in refs:
            refs.append(el)
    return refs
