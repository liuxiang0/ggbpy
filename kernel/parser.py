"""代数输入解析器（P0 子集）。

支持输入形式：
  A=(1,2)           自由点
  v=(2,3)           自由向量（小写标签 + 元组）
  r=3              自由数值（也支持 r=1+2*3）
  f(x)=x^2+2*x     自由函数（SymPy 解析，支持 ^ 与隐式乘法）
  M=Midpoint[A,B]  命令（标签可选，缺省自动命名）
  g: Line[A,B]     冒号写法
  2+3              裸表达式 → 自动数值（要求可求值）
  P=Intersect[c,g] 命令参数可引用任意已存在对象

返回 (label, value_kind, payload) 由 commands.process_line 分发。
value_kind: "point" | "vector" | "number" | "function" | "command"
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .elements import GeoError
from .tolerance import TIGHT  # 统一数值容差（见 kernel/tolerance.py）

# 函数定义：f(x) = 表达式
RE_FUNC = re.compile(r"^([A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*)?\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*=\s*(.+)$")

TOKEN_RE = re.compile(r"\s*(\d+\.?\d*|\.\d+|[A-Za-z_][A-Za-z0-9_]*|[()+\-*/^,=:<>])")


def tokenize(s: str) -> List[str]:
    toks: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch in " \t\r\n":
            i += 1
            continue
        if ch == '"':
            # 引号字符串作为整体 token（保留内部空格/符号），供 Text 等使用
            j = i + 1
            while j < n and s[j] != '"':
                j += 1
            toks.append(s[i:j + 1])
            i = j + 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and s[i + 1].isdigit()):
            j = i
            while j < n and (s[j].isdigit() or s[j] == "."):
                j += 1
            toks.append(s[i:j])
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (s[j].isalnum() or s[j] == "_"):
                j += 1
            toks.append(s[i:j])
            i = j
            continue
        toks.append(ch)
        i += 1
    return toks


# ---------------------------------------------------------------------------
# 数值表达式求值（+ - * / ^ 括号，可引用数值对象标签）
# ---------------------------------------------------------------------------

# 数值表达式内建函数与常数（主输入框/坐标可直接用，如 sin(pi/6)、2*pi*r、sqrt(2)）
import math as _math

_FN = {
    "sin": _math.sin, "cos": _math.cos, "tan": _math.tan,
    "asin": _math.asin, "acos": _math.acos, "atan": _math.atan,
    "exp": _math.exp, "sqrt": _math.sqrt, "abs": _math.fabs,
    "ln": _math.log, "log": _math.log10,
    "floor": _math.floor, "ceil": _math.ceil, "round": round,
    "sign": (lambda a: 1.0 if a > 0 else (-1.0 if a < 0 else 0.0)),
    "log2": (lambda a: _math.log(a, 2)),
}
_CONST = {"pi": _math.pi, "pi_": _math.pi}


class _NumParser:
    def __init__(self, toks: List[str], cons) -> None:
        self.toks = toks
        self.i = 0
        self.cons = cons

    def peek(self) -> Optional[str]:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def next(self) -> str:
        t = self.peek()
        if t is None:
            raise GeoError("表达式不完整")
        self.i += 1
        return t

    def parse(self) -> float:
        v = self.expr()
        if self.peek() is not None:
            raise GeoError("无法解析的表达式尾部: " + str(self.toks[self.i:]))
        return v

    def expr(self) -> float:
        v = self.term()
        while self.peek() in ("+", "-"):
            op = self.next()
            r = self.term()
            v = v + r if op == "+" else v - r
        return v

    def term(self) -> float:
        v = self.factor()
        while self.peek() in ("*", "/"):
            op = self.next()
            r = self.factor()
            if op == "*":
                v = v * r
            else:
                if abs(r) < TIGHT:
                    raise GeoError("除数为零")
                v = v / r
        return v

    def factor(self) -> float:
        t = self.peek()
        if t is None:
            raise GeoError("表达式不完整")
        if t == "(":
            self.next()
            v = self.expr()
            if self.next() != ")":
                raise GeoError("缺少右括号")
            return v
        if t == "-":
            self.next()
            return -self.factor()
        if t == "+":
            self.next()
            return self.factor()
        v = self.atom()
        if self.peek() == "^":
            self.next()
            e = self.factor()
            v = v ** e
        return v

    def atom(self) -> float:
        t = self.next()
        try:
            return float(t)
        except ValueError:
            pass
        if t == "π" or t == "pi":
            return _math.pi
        if t == "e":
            el = self.cons.elements.get("e")
            if el is not None and el.kind in ("number", "angle"):
                return el.value
            return _math.e
        if t in _FN:
            if self.peek() == "(":
                self.next()
                a = self.expr()
                if self.next() != ")":
                    raise GeoError("函数调用缺少右括号: " + t)
                return _FN[t](a)
            raise GeoError("函数需要括号: " + t)
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", t):
            el = self.cons.elements.get(t)
            if el is not None and el.kind in ("number", "angle"):
                return el.value
            raise GeoError("对象 " + t + " 不是数值")
        raise GeoError("无法解析的数值: " + t)


def eval_number(cons, text: str) -> float:
    toks = tokenize(text)
    if not toks:
        raise GeoError("空表达式")
    return _NumParser(toks, cons).parse()


# ---------------------------------------------------------------------------
# 主入口：把一行输入解析为 (label, kind, payload)
# ---------------------------------------------------------------------------

def parse_line(cons, line: str) -> Tuple[Optional[str], str, object]:
    line = line.strip()
    if not line:
        raise GeoError("空输入")

    # 1) 函数定义 f(x)=...；参数函数 f(t)=... → 参数曲线（Desmos 风格）
    m = RE_FUNC.match(line)
    if m:
        label, pname, body = m.group(1), m.group(2), m.group(3)
        if pname == "x":
            return label, "function", body
        bt = body.strip()
        if bt.startswith("(") and bt.endswith(")"):
            inner_parts = _split_commas(bt[1:-1])
            if len(inner_parts) == 2:
                return label, "parametric", (inner_parts[0], inner_parts[1], pname)
        return label, "parametric", (pname, bt, pname)

    toks = tokenize(line)

    # 2) 分离标签（先于不等式判断，支持 "ineq1: y > x^2"）
    label: Optional[str] = None
    if len(toks) >= 2 and toks[1] in ("=", ":"):
        if not re.match(r"^[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*$", toks[0]):
            raise GeoError("非法标签: " + toks[0])
        label = toks[0]
        toks = toks[2:]

    if not toks:
        raise GeoError("缺少表达式")

    # 3) 函数求值 f(2) / f(r)（IDENT 是已有函数且后跟圆括号）
    if re.match(r"^[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*$", toks[0]) and len(toks) >= 3 and toks[1] == "(" \
            and toks[0] in cons.elements and cons.elements[toks[0]].kind in ("function", "list"):
        # 找配对右括号
        depth = 1
        end = -1
        for i in range(2, len(toks)):
            if toks[i] == "(":
                depth += 1
            elif toks[i] == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            raise GeoError("括号不匹配")
        if end != len(toks) - 1:
            raise GeoError("函数求值后有多余内容")
        arg = _join_toks(toks[2:end])
        if cons.elements[toks[0]].kind == "list":
            return label, "list_index", (toks[0], arg)
        return label, "value", (toks[0], arg)

    # 3) 命令调用 Name[args]（可能是裸命令，无标签；命令名支持中文）
    if re.match(r"^[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*$", toks[0]) and len(toks) >= 2 and toks[1] == "[":
        name = toks[0]
        args, rest = _split_args(toks[2:])
        if rest:
            raise GeoError("命令后有多余内容")
        return label, "command", (name, args)

    # 3b) 不等式（命令优先，避免 SolveIneq[x<2] 的 < 被误判）
    if len(toks) >= 2 and toks[0] == "y" and toks[1] in ("<", ">", "<=", ">="):
        op = toks[1]
        rest = _join_toks(toks[2:])
        return label, "ineq_y", (op, rest)
    for i, t in enumerate(toks):
        if t in ("<", ">", "<=", ">="):
            lhs = _join_toks(toks[:i])
            rhs = _join_toks(toks[i + 1:])
            if lhs and rhs:
                return label, "ineq_general", (t, lhs, rhs)
            break

    # 3c) 裸极坐标 r=2*cos(theta) / 裸隐式 x^2+y^2=1 / y=x^2（Desmos 风格）
    if "=" in toks or (label == "r" and any(t in ("theta", "θ") for t in toks)) \
            or (label == "y" and any(t == "x" for t in toks)):
        if label is None and "=" in toks:
            eqi = toks.index("=")
            lhs = _join_toks(toks[:eqi])
            rhs = _join_toks(toks[eqi + 1:])
            if "theta" in toks or "θ" in toks:
                if not lhs:
                    raise GeoError("极坐标缺少左侧 r")
                return None, "polar", [rhs]
            if lhs and rhs:
                return None, "implicit", [lhs + "=" + rhs]
        elif label == "r" and any(t in ("theta", "θ") for t in toks):
            return label, "polar", [_join_toks(toks)]
        elif label == "y" and any(t == "x" for t in toks):
            return None, "implicit", ["y=" + _join_toks(toks)]

    # 4) 列表 {1,2,3} / {(1,2),(3,4)} / [1,2,3]
    if toks[0] == "[":
        parts = _split_bracket(toks)
        if label is None:
            raise GeoError("列表需要标签，例如 L=[1,2,3]")
        if not parts:
            return label, "list", ([], "number")
        if parts[0].startswith("("):
            items, kind3 = _list_tuple_items(cons, parts)
            return label, "list", (items, kind3)
        pt_items = _list_point_items(cons, parts)
        if pt_items is not None:
            return label, "list", pt_items
        _reject_mixed_point_list(cons, parts)
        items = [eval_number(cons, pp) for pp in parts]
        return label, "list", (items, "number")
    if toks[0] == "{":
        parts = _split_brace(toks)
        if label is None:
            raise GeoError("列表需要标签，例如 L={1,2,3}")
        if not parts:
            return label, "list", ([], "number")
        if parts[0].startswith("("):
            items, kind3 = _list_tuple_items(cons, parts)
            return label, "list", (items, kind3)
        pt_items = _list_point_items(cons, parts)
        if pt_items is not None:
            return label, "list", pt_items
        _reject_mixed_point_list(cons, parts)
        items = [eval_number(cons, p) for p in parts]
        return label, "list", (items, "number")

    # 5) 元组 (a,b) / (a,b,c) → 点或向量；含变量 → 参数曲线 (x(t), y(t))
    if toks[0] == "(":
        parts = _split_tuple(toks)
        if len(parts) not in (2, 3):
            raise GeoError("元组需要两个或三个分量")
        try:
            vals = [eval_number(cons, p) for p in parts]
        except GeoError:
            # 参数曲线：(cos(t), sin(t)) 等（分量含函数/变量，无法数值化）
            if len(parts) != 2:
                raise GeoError("参数曲线需要恰好两个分量")
            if label is None:
                label = cons.auto_label("parametric")
            return label, "parametric", (parts[0], parts[1])
        if len(parts) == 3:
            return label, "point", (vals[0], vals[1], vals[2])
        if label is not None and label[0].islower():
            return label, "vector", (vals[0], vals[1])
        return label, "point", (vals[0], vals[1])

    # 5.5) 复数：含独立虚数单位 i 的表达式 → a+bi（z=3+4i / 1-2i / i / -i）
    if any(t == "i" for t in toks):
        return label, "complex", (line if label is None else _join_toks(toks))

    # 6) 数值表达式
    v = eval_number(cons, line if label is None else _join_toks(toks))
    if label is None:
        # 裸数值：自动命名
        label = cons.auto_label("number")
    return label, "number", v


def _join_toks(toks: List[str]) -> str:
    s = ""
    for t in toks:
        if t in ("(", "[", "+", "-", "*", "/", "^", ",", "=", ":"):
            s += t
        else:
            if s and s[-1] not in ("(", "[", "+", "-", "*", "/", "^", ",", "=", ":"):
                s += " "
            s += t
    return s.strip()


def _list_point_items(cons, parts):
    """整份列表都是**点标签**（``{A,B}`` / ``{A3,B3}``）→ ``(items, itemkind)``；否则 ``None``。

    与 ``(x,y)`` 字面量同构（items 为坐标元组），因此渲染/序列化/依赖重算全部复用既有链路；
    坐标在此只做**初值**，真正的动态刷新由 ``cmd_util.list_literal_state`` 的依赖重算负责。
    """
    if not parts:
        return None
    objs = []
    for pp in parts:
        el = cons.elements.get(pp.strip())
        if el is None or el.kind not in ("point", "point3d"):
            return None
        objs.append(el)
    kind = None
    items = []
    for el in objs:
        z = getattr(el, "z", None)          # 三维点在元素层仍是 kind="point"，靠 z 区分
        k = "point3d" if z is not None else "point"
        if kind is None:
            kind = k
        elif kind != k:
            raise GeoError("列表元素分量数需一致（二维点与三维点不能混在同一列表）")
        if k == "point3d":
            items.append((float(el.x), float(el.y), float(z)))
        else:
            items.append((float(el.x), float(el.y)))
    return items, kind


def _list_tuple_items(cons, parts):
    """列表元素解析：支持 (x,y) 与 (x,y,z)，返回 (items, itemkind)。"""
    items = []
    kind = None
    for pp in parts:
        tp = _tuple_parts_str(pp)
        if len(tp) not in (2, 3):
            raise GeoError("列表元素需要 (x,y) 或 (x,y,z): " + pp)
        k = "point3d" if len(tp) == 3 else "point"
        if kind is None:
            kind = k
        elif kind != k:
            raise GeoError("列表元素分量数需一致（要么全是 (x,y)，要么全是 (x,y,z)）")
        items.append(tuple(eval_number(cons, q) for q in tp))
    return items, kind


def _reject_mixed_point_list(cons, parts) -> None:
    """列表里「有点标签、又有数值/坐标」时给明确指引（而不是“对象 A 不是数值”这种费解报错）。"""
    pts = [pp for pp in parts if (cons.elements.get(pp.strip()) is not None
                                  and cons.elements[pp.strip()].kind in ("point", "point3d"))]
    if pts:
        raise GeoError("列表元素要么全是点标签（如 {A,B}），要么全是坐标（如 {(1,2),(3,4)}）")


def _tuple_parts_str(s: str) -> List[str]:
    """从字符串 (a,b) 提取分量。"""
    s = s.strip()
    if not (s.startswith("(") and s.endswith(")")):
        raise GeoError("需要 (a,b) 形式: " + s)
    inner = s[1:-1]
    parts = []
    depth = 0
    cur = ""
    for ch in inner:
        if ch == "(":
            depth += 1
            cur += ch
        elif ch == ")":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    if len(parts) not in (2, 3):
        raise GeoError("元组需要两个或三个分量: " + s +
                       "（列表里写点请直接用 {A,B} 形式，不要加括号）")
    return parts


def _split_commas(s: str) -> List[str]:
    """按顶层逗号切分字符串（括号嵌套感知），用于参数曲线分量。"""
    parts = []
    depth = 0
    cur = ""
    for ch in s:
        if ch in "([{":
            depth += 1
            cur += ch
        elif ch in ")]}":
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


def _split_bracket(toks: List[str]) -> List[str]:
    """从 '[' 开始解析列表元素（顶层逗号分隔），返回元素子串列表。"""
    depth = 1
    parts: List[str] = []
    cur: List[str] = []
    i = 1
    n = len(toks)
    while i < n:
        t = toks[i]
        if t in ("[", "("):
            depth += 1
            cur.append(t)
        elif t == ")":
            depth -= 1
            cur.append(t)
        elif t == "]":
            depth -= 1
            if depth == 0:
                parts.append(" ".join(cur).strip())
                i += 1
                break
            cur.append(t)
        elif t == "," and depth == 1:
            parts.append(" ".join(cur).strip())
            cur = []
        else:
            cur.append(t)
        i += 1
    if depth != 0:
        raise GeoError("列表缺少右方括号 ]")
    if i < n:
        raise GeoError("列表后有多余内容")
    return [pp for pp in parts if pp]


def _split_brace(toks: List[str]) -> List[str]:
    """从 '{' 开始解析列表元素（顶层逗号分隔）。"""
    depth = 1
    parts: List[str] = []
    cur: List[str] = []
    i = 1
    n = len(toks)
    while i < n:
        t = toks[i]
        if t in ("{", "("):
            depth += 1
            cur.append(t)
        elif t == ")":
            depth -= 1
            cur.append(t)
        elif t == "}":
            depth -= 1
            if depth == 0:
                parts.append("".join(cur).strip())
                i += 1
                break
            cur.append(t)
        elif t == "," and depth == 1:
            parts.append(" ".join(cur).strip())
            cur = []
        else:
            cur.append(t)
        i += 1
    if depth != 0:
        raise GeoError("列表缺少右花括号 }")
    if i < n:
        raise GeoError("列表后有多余内容")
    return [p for p in parts if p]


def _split_tuple(toks: List[str]) -> List[str]:
    """从 '(' 开始解析元组，返回逗号分隔的若干子串（直到匹配的 ')'）。"""
    depth = 0
    parts: List[str] = []
    cur: List[str] = []
    i = 0
    n = len(toks)
    if i >= n or toks[i] != "(":
        raise GeoError("内部错误: 非元组")
    depth = 1
    i += 1
    while i < n:
        t = toks[i]
        if t == "(":
            depth += 1
            cur.append(t)
        elif t == ")":
            depth -= 1
            if depth == 0:
                parts.append(" ".join(cur).strip())
                i += 1
                break
            cur.append(t)
        elif t == "," and depth == 1:
            parts.append(" ".join(cur).strip())
            cur = []
        else:
            cur.append(t)
        i += 1
    if depth != 0:
        raise GeoError("括号不匹配")
    if i < n:
        raise GeoError("元组后有多余内容")
    return parts


def _split_args(toks: List[str]) -> Tuple[List[str], List[str]]:
    """从 '[' 之后开始解析命令参数，返回 (args, rest)。"""
    depth = 1
    parts: List[str] = []
    cur: List[str] = []
    i = 0
    n = len(toks)
    in_quote = False
    while i < n:
        t = toks[i]
        if t == '"':
            in_quote = not in_quote
            cur.append(t)
        elif in_quote:
            cur.append(t)
        elif t in ("[", "(", "{"):
            depth += 1
            cur.append(t)
        elif t in ("]", ")", "}"):
            depth -= 1
            if depth == 0:
                parts.append("".join(cur).strip())
                i += 1
                break
            cur.append(t)
        elif t == "," and depth == 1:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(t)
        i += 1
    if depth != 0:
        raise GeoError("命令缺少右括号 ]")
    return parts, toks[i:]
