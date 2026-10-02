"""区间算术（P1）。

用于函数绘图的可靠性：
- 检测定义域外（sqrt/log 的负参数、除零）→ 该点未定义
- 检测垂直渐近线（tan、1/x 在极点附近区间发散）→ 断开曲线
- 支撑 Adaptive sampling 的中间值校验

实现：Intervals 类 + 对 SymPy 表达式的区间求值 eval_expr。
常见函数（sin/cos/tan/exp/log/sqrt/abs/幂）精确处理；未知函数退化到采样包络。
"""

from __future__ import annotations

import math
from typing import Optional

import sympy
from .tolerance import NEGLIGIBLE  # 统一数值容差（见 kernel/tolerance.py）


class Interval:
    __slots__ = ("lo", "hi")

    def __init__(self, lo: float, hi: float) -> None:
        self.lo = float(lo)
        self.hi = float(hi)

    @staticmethod
    def empty() -> "Interval":
        iv = Interval(math.inf, -math.inf)
        return iv

    def is_empty(self) -> bool:
        return self.lo > self.hi

    def is_finite(self) -> bool:
        return math.isfinite(self.lo) and math.isfinite(self.hi)

    def contains_zero(self) -> bool:
        return self.lo <= 0.0 <= self.hi

    def __add__(self, o):
        if isinstance(o, Interval):
            return Interval(self.lo + o.lo, self.hi + o.hi)
        return Interval(self.lo + o, self.hi + o)

    __radd__ = __add__

    def __sub__(self, o):
        if isinstance(o, Interval):
            return Interval(self.lo - o.hi, self.hi - o.lo)
        return Interval(self.lo - o, self.hi - o)

    def __rsub__(self, o):
        return Interval(o - self.hi, o - self.lo)

    def __mul__(self, o):
        if isinstance(o, Interval):
            a = self.lo * o.lo
            b = self.lo * o.hi
            c = self.hi * o.lo
            d = self.hi * o.hi
            return Interval(min(a, b, c, d), max(a, b, c, d))
        if o >= 0:
            return Interval(self.lo * o, self.hi * o)
        return Interval(self.hi * o, self.lo * o)

    __rmul__ = __mul__

    def __truediv__(self, o):
        if isinstance(o, Interval):
            if o.contains_zero():
                if abs(o.lo) < NEGLIGIBLE and abs(o.hi) < NEGLIGIBLE:
                    return Interval.empty()
                # 分母跨零：结果为两个无穷区间的并 → 用 ±inf 表示（视为发散）
                return Interval(-math.inf, math.inf)
            return self * Interval(1.0 / o.hi, 1.0 / o.lo)
        if abs(o) < NEGLIGIBLE:
            return Interval.empty()
        return Interval(self.lo / o, self.hi / o)

    def __neg__(self):
        return Interval(-self.hi, -self.lo)

    def __repr__(self):
        return "[" + _f(self.lo) + ", " + _f(self.hi) + "]"


def _f(v: float) -> str:
    if math.isinf(v):
        return "-inf" if v < 0 else "inf"
    return ("%.6g" % v)


def power(iv: Interval, n) -> Interval:
    """x^n，n 为整数。"""
    if n == 0:
        return Interval(1.0, 1.0)
    if n == 1:
        return iv
    if n % 2 == 0:
        if iv.contains_zero():
            return Interval(0.0, max(iv.lo ** n, iv.hi ** n))
        return Interval(min(iv.lo ** n, iv.hi ** n), max(iv.lo ** n, iv.hi ** n))
    return Interval(iv.lo ** n, iv.hi ** n)


def sin(iv: Interval) -> Interval:
    if not iv.is_finite():
        return Interval(-1.0, 1.0)
    lo, hi = iv.lo, iv.hi
    mn, mx = min(math.sin(lo), math.sin(hi)), max(math.sin(lo), math.sin(hi))
    # 极值点 π/2 + kπ：偶 k → 最大值 1，奇 k → 最小值 -1
    k0 = math.ceil(lo / math.pi - 0.5)
    k1 = math.floor(hi / math.pi - 0.5)
    for k in range(max(k0, -10000), min(k1, 10000) + 1):
        xk = math.pi / 2 + k * math.pi
        if lo <= xk <= hi:
            if k % 2 == 0:
                mx = max(mx, 1.0)
            else:
                mn = min(mn, -1.0)
    return Interval(mn, mx)


def cos(iv: Interval) -> Interval:
    if not iv.is_finite():
        return Interval(-1.0, 1.0)
    lo, hi = iv.lo, iv.hi
    mn, mx = min(math.cos(lo), math.cos(hi)), max(math.cos(lo), math.cos(hi))
    # 极值点 kπ：偶 k → 1，奇 k → -1
    k0 = math.ceil(lo / math.pi)
    k1 = math.floor(hi / math.pi)
    for k in range(max(k0, -10000), min(k1, 10000) + 1):
        xk = k * math.pi
        if lo <= xk <= hi:
            if k % 2 == 0:
                mx = max(mx, 1.0)
            else:
                mn = min(mn, -1.0)
    return Interval(mn, mx)


def tan(iv: Interval) -> Interval:
    if not iv.is_finite():
        return Interval(-math.inf, math.inf)
    # 极点 π/2 + kπ 在区间内 → 发散
    k_lo = math.floor(iv.lo / math.pi + 0.5)
    k_hi = math.ceil(iv.hi / math.pi - 0.5)
    if k_lo <= k_hi:
        return Interval(-math.inf, math.inf)
    return Interval(math.tan(iv.lo), math.tan(iv.hi))


def exp(iv: Interval) -> Interval:
    return Interval(math.exp(iv.lo), math.exp(iv.hi))


def logn(iv: Interval) -> Interval:
    if iv.hi <= 0.0:
        return Interval.empty()
    lo = -math.inf if iv.lo <= 0.0 else math.log(iv.lo)
    return Interval(lo, math.log(iv.hi))


def sqrt(iv: Interval) -> Interval:
    if iv.hi < 0.0:
        return Interval.empty()
    lo = 0.0 if iv.lo <= 0.0 else math.sqrt(iv.lo)
    return Interval(lo, math.sqrt(iv.hi))


def absv(iv: Interval) -> Interval:
    if iv.contains_zero():
        return Interval(0.0, max(abs(iv.lo), abs(iv.hi)))
    return Interval(min(abs(iv.lo), abs(iv.hi)), max(abs(iv.lo), abs(iv.hi)))


# 带副作用的包络退化（用于不支持的函数）
def _envelope(xiv: Interval, fn, n: int = 12) -> Interval:
    lo, hi = math.inf, -math.inf
    for i in range(n + 1):
        t = xiv.lo + (xiv.hi - xiv.lo) * i / n
        try:
            v = float(fn(t))
        except Exception:
            return Interval(-math.inf, math.inf)
        if math.isnan(v):
            return Interval(-math.inf, math.inf)
        lo = min(lo, v)
        hi = max(hi, v)
    return Interval(lo, hi)


_X = sympy.Symbol("x", real=True)


def eval_expr(expr, xiv: Interval) -> Interval:
    """对 SymPy 表达式在区间 xiv 上做区间求值。"""
    xiv = Interval(xiv.lo, xiv.hi)
    try:
        return _eval(expr, xiv)
    except Exception:
        return Interval(-math.inf, math.inf)


def _eval(e, xiv: Interval) -> Interval:
    if e.is_Number:
        return Interval(float(e), float(e))
    if e is _X or (isinstance(e, sympy.Symbol) and e.name == "x"):
        return xiv
    if isinstance(e, sympy.Add):
        iv = _eval(e.args[0], xiv)
        for a in e.args[1:]:
            iv = iv + _eval(a, xiv)
        return iv
    if isinstance(e, sympy.Mul):
        iv = _eval(e.args[0], xiv)
        for a in e.args[1:]:
            iv = iv * _eval(a, xiv)
        return iv
    if isinstance(e, sympy.Pow):
        base = _eval(e.args[0], xiv)
        ex = e.args[1]
        if ex.is_Integer:
            n = int(ex)
            if n < 0:
                return power(Interval(1.0, 1.0) / base, -n) if n != 0 else Interval(1.0, 1.0)
            return power(base, n)
        # 非整数幂：定义域 x>0
        if base.hi <= 0.0:
            return Interval.empty()
        lo = -math.inf if base.lo <= 0.0 else base.lo ** float(ex)
        return Interval(lo, base.hi ** float(ex))
    fn = getattr(e, "func", None)
    if fn is sympy.sin:
        return sin(_eval(e.args[0], xiv))
    if fn is sympy.cos:
        return cos(_eval(e.args[0], xiv))
    if fn is sympy.tan:
        return tan(_eval(e.args[0], xiv))
    if fn is sympy.exp:
        return exp(_eval(e.args[0], xiv))
    if fn is sympy.log:
        return logn(_eval(e.args[0], xiv))
    if fn is sympy.sqrt:
        return sqrt(_eval(e.args[0], xiv))
    if fn is sympy.Abs:
        return absv(_eval(e.args[0], xiv))
    # 未知函数 → 包络退化
    name = str(fn)
    if e.args:
        inner = _eval(e.args[0], xiv)
        lam = sympy.lambdify(_X, e, "math")
        return _envelope(inner, lambda t: lam(t), 12)
    return Interval(-math.inf, math.inf)


def undefined(xiv: Interval) -> bool:
    """区间求值为空 → 该点定义域外。"""
    return xiv.is_empty()


def divergent(xiv: Interval) -> bool:
    """区间求值含无穷 → 该点邻域发散（渐近线）。"""
    return (not xiv.is_empty()) and (not xiv.is_finite())


def sample_ok(expr, xi: float, half_width: float):
    """判断 x=xi 处是否可绘（定义域内且不发散）。返回 (ok, interval)。"""
    iv = eval_expr(expr, Interval(xi - half_width, xi + half_width))
    if undefined(iv):
        return False, None
    return True, iv
