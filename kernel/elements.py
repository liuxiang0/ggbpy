"""几何对象模型（P0）。

设计：所有元素统一为 GeoElement 子类。
- free 元素：用户直接给出数值（点/数值/向量/函数），可被拖拽或重定义。
- derived 元素：由命令创建，持有 deps（输入元素引用）+ compute_fn(deps)->state 闭包，
  拖动自由元素时由 Construction 按依赖深度增量重算。

state 是 plain dict（如 {"x":..,"y":..}），compute 后写回自身属性。
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from .tolerance import EPSILON, COORD  # 统一数值容差（见 kernel/tolerance.py）



def _fmt(v: float) -> str:
    """紧凑数值格式化。"""
    s = ("%.6f" % v).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


class GeoError(Exception):
    """输入/命令错误，携带中文提示。"""


# ---------------------------------------------------------------------------
# 线裁剪工具（用于把无穷线/射线裁剪到视口矩形）
# ---------------------------------------------------------------------------

def clip_segment(
    x1: float, y1: float, x2: float, y2: float, view: Tuple[float, float, float, float]
) -> Optional[Tuple[float, float, float, float]]:
    """Liang-Barsky 线段裁剪。view = (xmin, xmax, ymin, ymax)。"""
    xmin, xmax, ymin, ymax = view
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - xmin), (dx, xmax - x1), (-dy, y1 - ymin), (dy, ymax - y1)):
        if abs(p) < EPSILON:
            if q < 0:
                return None
        else:
            r = q / p
            if p < 0:
                if r > t1:
                    return None
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return None
                if r < t1:
                    t1 = r
    return (x1 + t0 * dx, y1 + t0 * dy, x1 + t1 * dx, y1 + t1 * dy)


def clip_infinite_line(
    a: float, b: float, c: float, view: Tuple[float, float, float, float]
) -> Optional[Tuple[float, float, float, float]]:
    """把直线 ax+by+c=0 裁剪为视口内线段。"""
    norm = math.hypot(a, b)
    if norm < EPSILON:
        return None
    # 线上一点（到原点最近点）
    x0 = -a * c / (norm * norm)
    y0 = -b * c / (norm * norm)
    dx, dy = -b / norm, a / norm
    # 用足够大的参数把线扩展到视口外
    xmin, xmax, ymin, ymax = view
    span = max(abs(xmax - xmin), abs(ymax - ymin)) * 2 + 1.0
    return clip_segment(x0 - dx * span, y0 - dy * span, x0 + dx * span, y0 + dy * span, view)


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------

class GeoElement:
    """所有几何对象的基类。"""

    kind: str = "element"

    def __init__(self, label: str, defn: str, free: bool = True) -> None:
        self.label = label
        self.defn = defn            # 原始输入串（保存/撤销/重放用）
        self.free = free            # 自由对象可拖拽/编辑
        self.locked = False         # 锁定对象不可移动/删除/重定义
        self.visible = True
        self.color = "#1a1a1a"
        self.depth = 0              # 依赖深度（增量重算的拓扑序）
        self.deps: List[GeoElement] = []
        self.dependents: set = set()
        self.error: Optional[str] = None
        self._fn: Optional[Callable[[List[GeoElement]], Dict[str, Any]]] = None

    # ---- 依赖图 ----
    def set_deps(self, deps: Sequence[GeoElement],
                 fn: Optional[Callable[[List[GeoElement]], Dict[str, Any]]] = None) -> None:
        self.deps = list(deps)
        self._fn = fn
        self.depth = max((d.depth for d in self.deps), default=-1) + 1
        for d in self.deps:
            d.dependents.add(self)

    def compute(self) -> None:
        """按 deps 当前状态重算自身；free 元素为 no-op。

        重算前先查计算记忆（kernel.memo）：键 = defn + 各依赖的几何状态签名。
        撤销/重做/快照回放时依赖未变 → 直接复用上次结果，避免重算大网格。
        """
        if self.free or self._fn is None:
            return
        mkey = None
        try:
            from . import memo as _memo
            mkey = _memo.key_for(self)
            cached = _memo.get(mkey)
        except Exception:
            _memo = None
            cached = None
        if cached is not None:
            try:
                self.apply_state(cached)
                self.error = None
                return
            except Exception:
                pass
        try:
            state = self._fn(self.deps)
            self.apply_state(state)
            self.error = None
            if _memo is not None:
                try:
                    _memo.put(mkey, state)
                except Exception:
                    pass
        except GeoError as e:
            self.error = str(e)
        except Exception as e:  # 数值失败保留旧状态
            self.error = repr(e)

    def apply_state(self, state: Dict[str, Any]) -> None:
        for k, v in state.items():
            setattr(self, k, v)

    # ---- 序列化（供前端渲染） ----
    def draw(self, view: Tuple[float, float, float, float]) -> Optional[Dict[str, Any]]:
        if not self.visible:
            return None
        base = {
            "label": self.label,
            "kind": self.kind,
            "defn": self.defn,
            "free": self.free,
            "locked": self.locked,
            "color": self.color,
            "error": self.error,
        }
        return base

    def __repr__(self) -> str:
        return "<" + self.kind + " " + self.label + ">"


# ---------------------------------------------------------------------------
# 具体类型
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GeoGebra If[..] → SymPy Piecewise 文本翻译（分段函数支持）
# ---------------------------------------------------------------------------

def _split_top_level(s: str, sep: str = ",") -> List[str]:
    """按顶层分隔符切分（忽略括号/方括号/花括号内部）。"""
    out: List[str] = []
    cur: List[str] = []
    depth = 0
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur).strip())
    return out


def _split_bool_top(s: str) -> Tuple[List[str], List[str]]:
    """顶层按 & 与 | 切分，返回 (段, 操作符)。"""
    segs: List[str] = []
    ops: List[str] = []
    buf: List[str] = []
    depth = 0
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch in "&|" and depth == 0:
            segs.append("".join(buf).strip())
            ops.append(ch)
            buf = []
        else:
            buf.append(ch)
    segs.append("".join(buf).strip())
    return segs, ops


def _ggb_cond(c: str) -> str:
    """把 GeoGebra 条件转成 sympy 可解析文本（== → Eq、!= → Ne、逻辑词 → & |）。"""
    c = c.strip()
    if not c:
        raise GeoError("If 条件为空")
    c = c.replace("&&", " & ").replace("||", " | ")
    c = c.replace(" and ", " & ").replace(" or ", " | ")
    segs, ops = _split_bool_top(c)

    def one(p: str) -> str:
        p = p.strip()
        # 顶层 == / != → Eq / Ne（split 用单字符串分隔符，避免嵌套函数调用误伤）
        if p.find("==") != -1:
            a, b = p.split("==", 1)
            return "Eq(" + a.strip() + ", " + b.strip() + ")"
        if p.find("!=") != -1:
            a, b = p.split("!=", 1)
            return "Ne(" + a.strip() + ", " + b.strip() + ")"
        if any(op in p for op in ("<", ">")):
            return "(" + p + ")"
        return p

    parts = [one(s) for s in segs]
    buf = parts[0]
    for i, op in enumerate(ops):
        buf += " & " if op == "&" else " | "
        buf += parts[i + 1]
    return buf


def _ggb_if_forms(text: str) -> str:
    """把文本中的 If[..]（可嵌套）翻译为 Piecewise((..)) 形式；不含 If 时原样返回。"""
    if "If[" not in text:
        return text
    out: List[str] = []
    i = 0
    n = len(text)
    while True:
        j = text.find("If[", i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        k = j + 3
        depth = 1
        while k < n and depth > 0:
            ch = text[k]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            k += 1
        if depth != 0:
            raise GeoError("If 括号不匹配")
        inner = text[j + 3:k - 1]
        items = [p for p in _split_top_level(inner) if p]
        if len(items) < 2:
            raise GeoError("If 需要 条件 与 结果")
        branches = []
        else_v = None
        if len(items) == 3:
            # If[cond, then, else]
            branches = [(items[1], items[0])]
            else_v = items[2]
        elif len(items) == 2 or len(items) == 4:
            # If[c, v] / If[c1, v1, c2, v2]（无 else）
            branches = [(items[x + 1], items[x]) for x in range(0, len(items), 2)]
        else:
            # 5+ 项：If[c1,v1,c2,v2,...,else]（奇数带末项 else）
            if len(items) % 2 == 1:
                else_v = items[-1]
                pairs = range(0, len(items) - 1, 2)
            else:
                pairs = range(0, len(items), 2)
            branches = [(items[x + 1], items[x]) for x in pairs]
        pieces = []
        for v, c in branches:
            pieces.append("(" + _ggb_if_forms(v) + ", " + _ggb_cond(c) + ")")
        if else_v is not None:
            pieces.append("(" + _ggb_if_forms(else_v) + ", True)")
        out.append("Piecewise(" + ", ".join(pieces) + ")")
        i = k
    return "".join(out)


class GeoComplex(GeoElement):
    """复数 a+bi（复平面上的点 (re, im)）。"""
    kind = "complex"

    def __init__(self, label: str, defn: str, re: float = 0.0, im: float = 0.0,
                 free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.re = float(re)
        self.im = float(im)

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["x"], d["y"] = self.re, self.im
        d["value"] = _cmplx_fmt(self.re, self.im)
        return d


def _cmplx_fmt(a: float, b: float) -> str:
    ta = _fmt(a)
    if abs(b) < EPSILON:
        return ta if abs(a) > EPSILON else "0"
    tb = _fmt(abs(b))
    if abs(a) < EPSILON:
        return ("-" if b < 0 else "") + tb + "i"
    return ta + (" - " if b < 0 else " + ") + tb + "i"


class GeoPoint(GeoElement):
    kind = "point"

    def __init__(self, label: str, defn: str, x: float = 0.0, y: float = 0.0,
                 free: bool = True, z: float = None) -> None:
        super().__init__(label, defn, free)
        self.x = float(x)
        self.y = float(y)
        self.z = None if z is None else float(z)

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["x"], d["y"] = self.x, self.y
        if self.z is not None:
            d["z"] = self.z
            d["value"] = "(" + _fmt(self.x) + ", " + _fmt(self.y) + ", " + _fmt(self.z) + ")"
        else:
            d["value"] = "(" + _fmt(self.x) + ", " + _fmt(self.y) + ")"
        return d


class GeoNumber(GeoElement):
    kind = "number"

    def __init__(self, label: str, defn: str, value: float = 0.0, free: bool = True) -> None:
        super().__init__(label, defn, free)
        self.value = float(value)
        self.min = None      # 滑动条范围（None = 普通数值）
        self.max = None
        self.step = None

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["val"] = self.value
        d["value"] = "= " + _fmt(self.value)
        if self.min is not None:
            d["min"], d["max"], d["step"] = self.min, self.max, self.step
        return d


class GeoVector(GeoElement):
    kind = "vector"

    def __init__(self, label: str, defn: str, dx: float = 0.0, dy: float = 0.0,
                 free: bool = True) -> None:
        super().__init__(label, defn, free)
        self.dx = float(dx)
        self.dy = float(dy)
        self.sx = 0.0   # 起点（两点模式 Vector[A,B] 用 A；自由向量为原点）
        self.sy = 0.0

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["dx"], d["dy"] = self.dx, self.dy
        d["sx"], d["sy"] = self.sx, self.sy
        d["value"] = "(" + _fmt(self.dx) + ", " + _fmt(self.dy) + ")"
        return d


class GeoLine(GeoElement):
    kind = "line"

    def __init__(self, label: str, defn: str, a: float = 1.0, b: float = 0.0,
                 c: float = 0.0, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.a, self.b, self.c = float(a), float(b), float(c)

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        clip = clip_infinite_line(self.a, self.b, self.c, view)
        d["a"], d["b"], d["c"] = self.a, self.b, self.c
        if clip is None:
            d["seg"] = None
        else:
            d["seg"] = list(clip)
        if abs(self.b) > COORD:
            m = -self.a / self.b
            n = -self.c / self.b
            d["value"] = "y = " + _fmt(m) + "x " + ("+ " if n >= 0 else "- ") + _fmt(abs(n))
        else:
            d["value"] = "x = " + _fmt(-self.c / self.a) if abs(self.a) > COORD else "退化直线"
        return d


class GeoSegment(GeoElement):
    kind = "segment"

    def __init__(self, label: str, defn: str, x1: float = 0.0, y1: float = 0.0,
                 x2: float = 1.0, y2: float = 1.0, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.x1, self.y1, self.x2, self.y2 = float(x1), float(y1), float(x2), float(y2)

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["x1"], d["y1"], d["x2"], d["y2"] = self.x1, self.y1, self.x2, self.y2
        d["value"] = "长 = " + _fmt(math.hypot(self.x2 - self.x1, self.y2 - self.y1))
        return d


class GeoRay(GeoElement):
    kind = "ray"

    def __init__(self, label: str, defn: str, ox: float = 0.0, oy: float = 0.0,
                 dx: float = 1.0, dy: float = 0.0, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.ox, self.oy = float(ox), float(oy)
        self.dx, self.dy = float(dx), float(dy)

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        norm = math.hypot(self.dx, self.dy)
        ux, uy = (self.dx / norm, self.dy / norm) if norm > EPSILON else (1.0, 0.0)
        xmin, xmax, ymin, ymax = view
        span = max(abs(xmax - xmin), abs(ymax - ymin)) * 2 + 1.0
        clip = clip_segment(self.ox, self.oy, self.ox + ux * span, self.oy + uy * span, view)
        d["ox"], d["oy"], d["ux"], d["uy"] = self.ox, self.oy, ux, uy
        d["seg"] = list(clip) if clip else None
        d["value"] = "(" + _fmt(self.ox) + ", " + _fmt(self.oy) + ") → 方向 (" + _fmt(ux) + ", " + _fmt(uy) + ")"
        return d


class GeoCircle(GeoElement):
    kind = "circle"

    def __init__(self, label: str, defn: str, cx: float = 0.0, cy: float = 0.0,
                 r: float = 1.0, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.cx, self.cy, self.r = float(cx), float(cy), float(r)

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["cx"], d["cy"], d["r"] = self.cx, self.cy, self.r
        d["value"] = "(x " + ("- " if self.cx >= 0 else "+ ") + _fmt(abs(self.cx)) + ")^2 + (y " + ("- " if self.cy >= 0 else "+ ") + _fmt(abs(self.cy)) + ")^2 = " + _fmt(self.r * self.r)
        return d


class GeoPolyline(GeoElement):
    """折线：依次连接多个点。"""
    kind = "polyline"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.xs: List[float] = []
        self.ys: List[float] = []

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["pts"] = [[x, y] for x, y in zip(self.xs, self.ys)]
        length = 0.0
        for i in range(1, len(self.xs)):
            length += math.hypot(self.xs[i] - self.xs[i - 1], self.ys[i] - self.ys[i - 1])
        d["value"] = "长 = " + _fmt(length)
        return d


class GeoPolygon(GeoElement):
    kind = "polygon"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.xs: List[float] = []
        self.ys: List[float] = []
        self.rigid = False   # 刚性多边形：仅两可见手柄；拖首点平移、拖第二点绕首点旋转（保距保形）

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["pts"] = [[x, y] for x, y in zip(self.xs, self.ys)]
        d["rigid"] = getattr(self, "rigid", False)
        n = len(self.xs)
        if n >= 3:
            s = 0.0
            for i in range(n):
                j = (i + 1) % n
                s += self.xs[i] * self.ys[j] - self.xs[j] * self.ys[i]
            d["value"] = "面积 = " + _fmt(abs(s) / 2.0)
        else:
            d["value"] = ""
        return d


class GeoFunction(GeoElement):
    kind = "function"

    def __init__(self, label: str, defn: str, free: bool = True) -> None:
        super().__init__(label, defn, free)
        self.body = ""
        self.expr = None            # sympy 表达式（关于符号 x）
        self.xsym = None
        self._lamb = None

    # ---- 配置：解析表达式，绑定依赖 ----
    def configure(self, cons, body: str, refs) -> None:
        """refs：函数体中引用的已有元素（数值/函数）。"""
        import sympy
        self.body = body
        x = sympy.Symbol("x")
        ld = {"x": x, "e": sympy.E, "pi": sympy.pi, "π": sympy.pi}
        fmap = {}
        for d in refs:
            if d.kind == "function":
                ld[d.label] = sympy.Function(d.label)
                fmap[d.label] = d
            elif d.kind == "number":
                ld[d.label] = sympy.Float(d.value)
        expr = sympy.parsing.sympy_parser.parse_expr(
            _ggb_if_forms(body),
            local_dict=ld,
            transformations=(
                sympy.parsing.sympy_parser.standard_transformations
                + (sympy.parsing.sympy_parser.implicit_multiplication_application,
                   sympy.parsing.sympy_parser.convert_xor)
            ),
        )
        for lab, dep in fmap.items():
            expr = expr.replace(sympy.Function(lab)(x), dep.expr)
        free = expr.free_symbols - {x}
        if free:
            raise GeoError("函数中出现未知变量: " + ", ".join(sorted(str(s) for s in free)))
        self.expr = expr
        self.xsym = x
        self._lamb = None
        self._samp_key = None
        if refs:
            self.free = False
            self.set_deps(list(refs))

    def _recompile(self) -> None:
        """依赖变化后按当前数值重新编译（引用数值对象的函数）。"""
        import sympy
        if not self.body:
            return
        x = self.xsym
        ld = {"x": x, "e": sympy.E, "pi": sympy.pi, "π": sympy.pi}
        fmap = {}
        for d in self.deps:
            if d.kind == "function":
                ld[d.label] = sympy.Function(d.label)
                fmap[d.label] = d
            elif d.kind == "number":
                ld[d.label] = sympy.Float(d.value)
        expr = sympy.parsing.sympy_parser.parse_expr(
            _ggb_if_forms(self.body),
            local_dict=ld,
            transformations=(
                sympy.parsing.sympy_parser.standard_transformations
                + (sympy.parsing.sympy_parser.implicit_multiplication_application,
                   sympy.parsing.sympy_parser.convert_xor)
            ),
        )
        for lab, dep in fmap.items():
            expr = expr.replace(sympy.Function(lab)(x), dep.expr)
        self.expr = expr
        self._lamb = None
        self._samp_key = None

    def compute(self) -> None:
        if self.free:
            return
        if self._fn is not None:
            state = self._fn(self.deps)
            self.expr = state["expr"]
            # 应用状态里的其余字段（尤其 xsym）：拟合类函数依赖是点列表，
            # 无法像导数/积分那样从"函数依赖"继承自变量，原先漏掉会导致
            # lambdify 失败 → 函数不可求值、绘图样本全为 NaN。
            for k, v in state.items():
                if k != "expr":
                    setattr(self, k, v)
            if self.xsym is None and self.deps and self.deps[0].kind == "function":
                self.xsym = self.deps[0].xsym
            self._lamb = None
            self._samp_key = None
        elif self.body:
            self._recompile()

    # ---- 数值求值 ----
    def _eval1(self, xi: float):
        try:
            if self._lamb is None:
                import numpy as np
                import sympy as sp
                self._lamb = sp.lambdify((self.xsym,), self.expr, "numpy")
            v = self._lamb(xi)
            import numpy as np
            return float(v) if np.isfinite(v) else None
        except Exception:
            return None

    @staticmethod
    def _may_have_singularity(expr, x) -> bool:
        """表达式是否可能含奇点（tan/倒数/根号/log）——决定是否需要逐点区间检测。"""
        import sympy
        for a in sympy.preorder_traversal(expr):
            if isinstance(a, (sympy.tan, sympy.cot, sympy.sec, sympy.csc, sympy.log)):
                return True
            if isinstance(a, sympy.Pow) and a.base.has(x):
                if a.exp.is_negative or not a.exp.is_integer:
                    return True
        return False

    # ---- 采样：区间检测 + 自适应细分 ----
    def sample(self, xmin: float, xmax: float, n: int = 400) -> List[List[float]]:
        """对可见区间采样。未定义/发散点以 NaN 分隔，曲线在此断开。
        采样结果按 (xmin, xmax, n) 缓存：视口不变时跨请求复用（依赖变化经 compute 失效）。"""
        from .interval import sample_ok
        if self.expr is None or xmax <= xmin:
            return []
        key = (round(xmin, 6), round(xmax, 6), n)
        if getattr(self, "_samp_key", None) == key and self._samp_pts is not None:
            return self._samp_pts
        need_iv = getattr(self, "_need_iv", None)
        if need_iv is None:
            need_iv = self._may_have_singularity(self.expr, self.xsym)
            self._need_iv = need_iv
        import numpy as np
        dx = (xmax - xmin) / n
        hw = dx / 4.0
        xs = list(np.linspace(xmin, xmax, n))
        refined: List[float] = []

        def add(xi: float) -> None:
            if not refined or xi > refined[-1] + EPSILON:
                refined.append(xi)

        def refine(a: float, b: float, depth: int) -> None:
            mid = (a + b) / 2.0
            if depth <= 0:
                add(mid)
                return
            ya, yb = self._eval1(a), self._eval1(b)
            ym = self._eval1(mid)
            if ya is not None and yb is not None and ym is not None:
                tol = 0.02 * (1.0 + abs(ya) + abs(yb))
                if abs(ym - (ya + yb) / 2.0) > tol:
                    refine(a, mid, depth - 1)
                    refine(mid, b, depth - 1)
                    return
            add(mid)

        for i in range(n - 1):
            add(xs[i])
            refine(xs[i], xs[i + 1], 3)
        add(xs[n - 1])

        # 批量求值（numpy 向量化一次调用），仅对非有限点做 interval 断点验证
        out: List[List[float]] = []
        try:
            if self._lamb is None:
                import sympy as sp
                self._lamb = sp.lambdify((self.xsym,), self.expr, "numpy")
            ys = np.asarray(self._lamb(np.array(refined, dtype=float)), dtype=float)
            if ys.ndim == 0:  # 常量函数返回标量
                ys = np.full(len(refined), float(ys))
        except Exception:
            ys = np.array([np.nan] * len(refined))
        for ki, xi in enumerate(refined):
            y = float(ys[ki])
            if math.isfinite(y):
                if need_iv:
                    # 可能含奇点：用区间算术检测区间内无定义（tan 极点等）
                    ok_flag, _ = sample_ok(self.expr, xi, hw)
                    out.append([float(xi), y if ok_flag else float("nan")])
                else:
                    out.append([float(xi), y])
            else:
                ok_flag, _ = sample_ok(self.expr, xi, hw)
                out.append([float(xi), float("nan") if not ok_flag else y])
        self._samp_key = key
        self._samp_pts = out
        return out

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        xmin, xmax, _, _ = view
        d["expr"] = str(self.expr) if self.expr is not None else ""
        d["samples"] = self.sample(xmin, xmax, 400)
        return d


# ---------------------------------------------------------------------------
# P3 元素：圆锥曲线 / 列表 / 不等式 / 3D 对象
# ---------------------------------------------------------------------------

class GeoConic(GeoElement):
    """一般圆锥曲线 ax²+bxy+cy²+dx+ey+f=0，附带规范参数用于绘制。"""
    kind = "conic"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.a = self.b = self.c = self.d = self.e = self.f = 0.0
        self.ctype = "general"      # circle | ellipse | hyperbola | parabola | general
        self.cx = self.cy = 0.0
        self.semi_a = self.semi_b = 0.0
        self.angle = 0.0            # 长轴方向（弧度）
        self.focus = None           # 抛物线焦点 (fx, fy)
        self.directrix = None       # 抛物线准线 (a, b, c)

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["ctype"] = self.ctype
        d["coeffs"] = [self.a, self.b, self.c, self.d, self.e, self.f]
        d["cx"], d["cy"] = self.cx, self.cy
        d["semi_a"], d["semi_b"] = self.semi_a, self.semi_b
        d["angle"] = self.angle
        if self.focus is not None:
            d["focus"] = list(self.focus)
        if self.directrix is not None:
            d["directrix"] = list(self.directrix)
        if self.ctype == "parabola":
            d["value"] = "抛物线（焦点 (" + _fmt(self.focus[0]) + ", " + _fmt(self.focus[1]) + ")）"
        elif self.ctype == "circle":
            d["value"] = "圆：半径 r=" + _fmt(self.semi_a)
        elif self.ctype == "ellipse":
            d["value"] = "椭圆：a=" + _fmt(self.semi_a) + " b=" + _fmt(self.semi_b)
        elif self.ctype == "hyperbola":
            d["value"] = "双曲线：a=" + _fmt(self.semi_a) + " b=" + _fmt(self.semi_b)
        else:
            d["value"] = "圆锥曲线"
        if self.ctype == "general":
            # 一般圆锥曲线：marching squares 等值线段
            from .geom_util import marching_squares
            xmin, xmax, ymin, ymax = view
            f = lambda x, y: self.a * x * x + self.b * x * y + self.c * y * y + self.d * x + self.e * y + self.f
            segs = marching_squares(f, xmin, xmax, ymin, ymax, 90, 70)
            d["segs"] = [[s[0][0], s[0][1], s[1][0], s[1][1]] for s in segs]
        return d


class GeoList(GeoElement):
    """数值或点的列表，如 L = {1,2,3} 或 L = {(1,2),(3,4)}。"""
    kind = "list"

    def __init__(self, label: str, defn: str, items=None, itemkind: str = "number",
                 free: bool = True) -> None:
        super().__init__(label, defn, free)
        self.items = items if items is not None else []
        self.itemkind = itemkind

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["itemkind"] = self.itemkind
        if self.itemkind == "point":
            d["items"] = [[a, b] for a, b in self.items]
            d["value"] = "{" + ", ".join("(" + _fmt(a) + ", " + _fmt(b) + ")" for a, b in self.items) + "}"
        elif self.itemkind == "point3d":
            d["items"] = [[a, b, c] for a, b, c in self.items]
            d["value"] = "{" + ", ".join("(" + _fmt(a) + ", " + _fmt(b) + ", " + _fmt(c) + ")" for a, b, c in self.items) + "}"
        else:
            d["items"] = list(self.items)
            d["value"] = "{" + ", ".join(_fmt(v) for v in self.items) + "}"
        return d


class GeoInequality(GeoElement):
    """不等式区域：y < f(x) 形式，或一般 f(x,y) < 0 形式。"""
    kind = "inequality"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.form = "y"            # "y"（y 与函数比较）| "general"（f(x,y)<0）
        self.yside = 1             # y>f: +1, y<f: -1
        self.strict = True         # 是否严格不等
        self.expr = None           # sympy 表达式
        self.xsym = None
        self.ysym = None

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        xmin, xmax, ymin, ymax = view
        d["form"] = self.form
        if self.form == "y":
            # 边界曲线采样
            d["yside"] = self.yside
            d["strict"] = self.strict
            d["boundary"] = self._sample_boundary(xmin, xmax)
        else:
            from .geom_util import marching_squares, assemble_loops
            import numpy as np
            try:
                lam = __import__("sympy").lambdify((self.xsym, self.ysym), self.expr, "numpy")
            except Exception:
                lam = None

            def f(x, y):
                if lam is None:
                    return float(self.expr.subs({self.xsym: x, self.ysym: y}))
                try:
                    v = lam(x, y)
                    return float(v) if np.isfinite(v) else 0.0
                except Exception:
                    return 0.0
            segs = marching_squares(f, xmin, xmax, ymin, ymax, 160, 120)
            d["loops"] = assemble_loops(segs)
        return d

    def _sample_boundary(self, xmin: float, xmax: float, n: int = 300):
        import numpy as np
        xs = np.linspace(xmin, xmax, n)
        try:
            lam = __import__("sympy").lambdify((self.xsym,), self.expr, "numpy")
            ys = lam(xs)
            out = []
            for i in range(len(xs)):
                v = float(ys[i]) if np.isfinite(ys[i]) else float("nan")
                out.append([float(xs[i]), v])
            return out
        except Exception:
            return []


class GeoAngle(GeoElement):
    """角度对象：∠ABC 的数值 + 可视化（扇形弧）。"""
    kind = "angle"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.value = 0.0          # 度数 0..360
        self.rad = 0.0            # 弧度
        self.cx = self.cy = 0.0   # 顶点 B
        self.ang1 = 0.0           # 边 BA 方向角（弧度）
        self.ang2 = 0.0           # 边 BC 方向角（弧度）

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["value"] = _fmt(self.value) + "°"
        d["deg"] = self.value
        d["rad"] = self.rad
        d["cx"], d["cy"] = self.cx, self.cy
        d["ang1"], d["ang2"] = self.ang1, self.ang2
        xmin, xmax, ymin, ymax = view
        d["arc_r"] = min(abs(xmax - xmin), abs(ymax - ymin)) * 0.07
        return d


class GeoBoolean(GeoElement):
    """布尔/命题元素（证明器输出）：value ∈ {True, False, None}。"""
    kind = "boolean"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.value = None
        self.detail = ""

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        if self.value is True:
            d["value"] = "true"
        elif self.value is False:
            d["value"] = "false"
        else:
            d["value"] = "未知"
        d["detail"] = self.detail
        return d


class Geo3D(GeoElement):
    """3D 对象（点/线段/平面/球/立方体）。kind 恒为 geo3d，objtype 区分。"""
    kind = "geo3d"

    def __init__(self, label: str, defn: str, objtype: str = "point", free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.objtype = objtype
        # 具体立体类型（cube/cone/cylinder/prism/pyramid/tetrahedron/…）。
        # objtype 历史上对多面体统一为 "polyhedron"（向后兼容），故另设 solid 字段区分；
        # 两者都为空的旧对象回退为 objtype。
        self.solid = ""
        self.data: Dict[str, Any] = {}
        self.wire = False   # 线框显示模式（仅 3D 物体）

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["objtype"] = self.objtype
        d["solid"] = self.solid or self.objtype
        d["wire"] = self.wire
        d["data"] = self.data
        return d



# ---------------------------------------------------------------------------
# 第二优先级补充：直方图 / 文本 / 轨迹
# ---------------------------------------------------------------------------

class GeoBarChart(GeoElement):
    """条形/直方图：离散值频数（count 模式）或分组区间频数（hist 模式）。"""
    kind = "barchart"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.bins: List[float] = []
        self.counts: List[int] = []
        self.width = 1.0
        self.hist = False          # hist 模式：bins/edges 为区间左边界，width 为真实组宽
        self.edges: List[float] = []

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["bins"] = self.bins
        d["counts"] = self.counts
        d["width"] = self.width
        d["hist"] = self.hist
        d["edges"] = self.edges
        total = sum(self.counts)
        d["value"] = "n = " + str(total)
        return d


class GeoBoxPlot(GeoElement):
    """箱线图：数据五数概括（min, Q1, 中位, Q3, max）。"""
    kind = "boxplot"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.five: List[float] = [0.0, 0.0, 0.0, 0.0, 0.0]
        self.n = 0

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        xmin, xmax, ymin, ymax = view
        d["five"] = self.five
        d["n"] = self.n
        # 箱线图放视口下部（基线 y0，箱高 span）
        d["base_y"] = ymin + (ymax - ymin) * 0.22
        d["box_h"] = (ymax - ymin) * 0.08
        d["value"] = "[" + ", ".join(_fmt(v) for v in self.five) + "]"
        return d


class GeoSumRect(GeoElement):
    """黎曼和（矩形/梯形条带）：对函数在 [a,b] 上的分割逼近。mode: left/right/mid/lower/upper/trap。"""
    kind = "sumrect"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.rects: List[List[float]] = []   # [x0,x1,y]（矩形高自 x 轴）或 [x0,x1,y0,y1]（梯形）
        self.mode = "left"
        self.value = 0.0
        self.n = 0
        self.a = 0.0
        self.b = 0.0

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["rects"] = self.rects
        d["mode"] = self.mode
        d["a"], d["b"], d["n"] = self.a, self.b, self.n
        d["value"] = "Σ ≈ " + _fmt(self.value)
        return d


class GeoPie(GeoElement):
    """饼图：分类数值占比。"""
    kind = "piechart"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.items: List[float] = []
        self.total = 0.0

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["items"] = self.items
        d["total"] = self.total
        d["value"] = "共 " + _fmt(self.total)
        return d


class GeoText(GeoElement):
    """文本标注：内容 + 锚点坐标。"""
    kind = "text"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.content = ""
        self.x = 0.0
        self.y = 0.0
        self.anchor_is_point = False

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["content"] = self.content
        d["x"], d["y"] = self.x, self.y
        d["anchor_is_point"] = self.anchor_is_point
        d["value"] = "“" + self.content + "”"
        return d


class GeoLocus(GeoElement):
    """轨迹：被驱动点在参数扫描下的位置序列。"""
    kind = "locus"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.pts: List[List[float]] = []

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["pts"] = self.pts
        d["value"] = "轨迹 " + str(len(self.pts)) + " 点"
        return d



class GeoImage(GeoElement):
    """图片对象：由两个基点 A（左下角）与 B（右下角）定位与缩放，保持原始长宽比。

    图像沿 A→B 为底边，高度 h = |AB| · (像素高/像素宽)，向 A→B 的逆时针法向延伸。
    """

    kind = "image"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.imgid = ""            # image_store 中的 id
        self.iw = 0                # 原始像素宽
        self.ih = 0                # 原始像素高
        self.ax = self.ay = 0.0    # 基点 A（左下）
        self.bx = self.by = 0.0    # 基点 B（右下）

    def corners(self):
        """四个世界坐标角点：左下、右下、右上、左上。"""
        w = math.hypot(self.bx - self.ax, self.by - self.ay)
        if w < EPSILON:
            return [[self.ax, self.ay], [self.bx, self.by], [self.bx, self.by], [self.ax, self.ay]]
        ux, uy = (self.bx - self.ax) / w, (self.by - self.ay) / w
        ratio = (self.ih / self.iw) if self.iw > 0 else 1.0
        h = w * ratio
        vx, vy = -uy, ux          # 逆时针 90°法向
        return [[self.ax, self.ay], [self.bx, self.by],
                [self.bx + h * vx, self.by + h * vy],
                [self.ax + h * vx, self.ay + h * vy]]

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["imgid"] = self.imgid
        d["imgurl"] = "/api/image/" + self.imgid
        d["corners"] = self.corners()
        d["iw"], d["ih"] = self.iw, self.ih
        d["value"] = "图片"
        return d


class GeoArc(GeoElement):
    """圆弧/扇形：圆心 C + 起点 A + 终点 B。"""
    kind = "arc"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.sector = False       # True = 扇形（含半径与填充）
        self.semicircle = False   # True = 半圆（直径端点创建）
        self.cx = self.cy = 0.0   # 圆心 C
        self.r = 0.0
        self.ang1 = 0.0           # 起点方向角
        self.ang2 = 0.0           # 终点方向角

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["sector"] = self.sector
        d["semicircle"] = self.semicircle
        d["cx"], d["cy"] = self.cx, self.cy
        d["r"] = self.r
        d["ang1"], d["ang2"] = self.ang1, self.ang2
        d["value"] = ("半圆" if self.semicircle else "扇形" if self.sector else "圆弧") + " r=" + _fmt(self.r)
        return d


class GeoMatrix(GeoElement):
    """数值矩阵（numpy 封装）。"""
    kind = "matrix"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.data = None        # numpy 2D array

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        if self.data is None:
            d["value"] = "空矩阵"
        else:
            rows = []
            for row in self.data:
                rows.append("[" + ", ".join(_fmt(float(v)) for v in row) + "]")
            d["value"] = "[" + ", ".join(rows) + "]"
            d["rows"], d["cols"] = int(self.data.shape[0]), int(self.data.shape[1])
        return d


class GeoResult(GeoElement):
    """计算结果（解集等纯文本，画布不绘制，仅列表显示）。"""
    kind = "result"

    def __init__(self, label: str, defn: str, free: bool = False) -> None:
        super().__init__(label, defn, free)
        self.text = ""

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["text"] = self.text
        d["value"] = self.text
        return d


class GeoCurve(GeoElement):
    """参数曲线：Parametric[x(t), y(t), t, a, b]。draw 时按当前依赖数值采样。"""
    kind = "parametric"

    def __init__(self, label: str, defn: str, xb: str, yb: str, pname: str,
                 t0: float, t1: float) -> None:
        super().__init__(label, defn, False)
        self.xb, self.yb, self.pname = xb, yb, pname
        self.t0, self.t1 = float(t0), float(t1)
        self.x_expr = None
        self.y_expr = None

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["pts"] = self._sample()
        d["value"] = "t∈[" + _fmt(self.t0) + "," + _fmt(self.t1) + "]"
        return d

    def _sample(self):
        if self.x_expr is None or self.y_expr is None:
            return []
        try:
            import numpy as np
            import sympy
            fx = sympy.lambdify(self.pname, self.x_expr, "numpy")
            fy = sympy.lambdify(self.pname, self.y_expr, "numpy")
            ts = np.linspace(self.t0, self.t1, 400)   # numpy 数组（list 不支持下标运算）
            xs, ys = fx(ts), fy(ts)
            pts = []
            for k in range(len(ts)):
                x, y = float(xs[k]), float(ys[k])
                if math.isfinite(x) and math.isfinite(y):
                    pts.append([round(x, 6), round(y, 6)])
            return pts
        except Exception:
            return []


class GeoPolar(GeoElement):
    """极坐标曲线：Polar[r(θ)]，θ ∈ [0, 2π]。"""
    kind = "polar"

    def __init__(self, label: str, defn: str, rb: str, pname: str = "theta") -> None:
        super().__init__(label, defn, False)
        self.rb, self.pname = rb, pname
        self.r_expr = None

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        d["pts"] = self._sample()
        d["value"] = "r=" + self.rb
        return d

    def _sample(self):
        if self.r_expr is None:
            return []
        try:
            import numpy as np
            import sympy
            fr = sympy.lambdify(self.pname, self.r_expr, "numpy")
            ts = np.linspace(0, 2 * np.pi, 400)   # numpy 数组（list 不支持下标运算）
            rs = fr(ts)
            pts = []
            for k in range(len(ts)):
                r, th = float(rs[k]), float(ts[k])
                if math.isfinite(r):
                    x, y = r * math.cos(th), r * math.sin(th)
                    if math.isfinite(x) and math.isfinite(y):
                        pts.append([round(x, 6), round(y, 6)])
            return pts
        except Exception:
            return []


class GeoImplicit(GeoElement):
    """隐式方程：Implicit[F(x,y)=0]，用 marching squares 画等值线。"""
    kind = "implicit"

    def __init__(self, label: str, defn: str, fbody: str) -> None:
        super().__init__(label, defn, False)
        self.fbody = fbody
        self.f_expr = None

    def draw(self, view):
        d = super().draw(view)
        if d is None:
            return None
        segs = []
        if self.f_expr is not None:
            try:
                import sympy
                from .geom_util import marching_squares
                f = sympy.lambdify((sympy.Symbol("x"), sympy.Symbol("y")),
                                   self.f_expr, "numpy")
                xmin, xmax, ymin, ymax = view
                segs = marching_squares(f, xmin, xmax, ymin, ymax, 80, 60)
            except Exception:
                segs = []
        d["segs"] = [[s[0][0], s[0][1], s[1][0], s[1][1]] for s in segs]
        d["value"] = "F(x,y)=0"
        return d
