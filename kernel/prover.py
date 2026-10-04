"""自动定理证明器（P4）：Botana 坐标法 + 符号归约。

原理：把几何构造翻译为符号坐标（自由点 → 独立符号，派生点 → 由命令符号推导），
结论写成多项式（应恒为零）。对结论多项式做 sympy.simplify / 有理归约：
余式为 0 → 命题真；非零 → 命题假（或依赖非退化条件，给出 NDG 提示）。

支持结论：平行 / 垂直 / 共线 / 共圆 / 线段相等 / 三线共点。
支持推导：Midpoint、Line/线段（两定点）、直线-直线交点、Translate/Reflect/Rotate、
Circle(圆心+半径, 三点外接圆)、Polygon 顶点等。
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

import sympy

from .elements import GeoError
from .tolerance import COARSE  # 统一数值容差（见 kernel/tolerance.py）


class ProverResult:
    def __init__(self, value: Optional[bool], detail: str) -> None:
        self.value = value        # True / False / None(未知)
        self.detail = detail

    def __repr__(self) -> str:
        return "<ProverResult " + str(self.value) + ": " + self.detail + ">"


# ---------------------------------------------------------------------------
# 符号坐标推导
# ---------------------------------------------------------------------------

def _cmd_of(defn: str) -> str:
    idx = defn.find("=")
    if idx == -1:
        idx = defn.find(":")
    return defn[idx + 1:].strip() if idx != -1 else defn


def _args_of(cmd: str) -> List[str]:
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\[(.*)\]$", cmd)
    if not m:
        return []
    inner = m.group(2)
    parts, depth, cur = [], 0, ""
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


def _solve_linear(a1, b1, c1, a2, b2, c2):
    """符号求解两直线 a1x+b1y+c1=0, a2x+b2y+c2=0。返回 (x, y, det)。"""
    det = a1 * b2 - a2 * b1
    if det == 0:
        return None, None, det
    x = (b1 * c2 - b2 * c1) / det
    y = (c1 * a2 - c2 * a1) / det
    return x, y, det


class SymbolicGeo:
    """把构造对象映射为符号坐标/方程。"""

    def __init__(self, cons) -> None:
        self.cons = cons
        self.pt_cache: Dict[str, Optional[Tuple[Any, Any]]] = {}
        self.line_cache: Dict[str, Optional[Tuple[Any, Any, Any]]] = {}
        self.ndg: List[str] = []

    def point(self, label: str) -> Optional[Tuple[Any, Any]]:
        """返回点的符号坐标 (sx, sy) 或 None。"""
        if label in self.pt_cache:
            return self.pt_cache[label]
        el = self.cons.elements.get(label)
        if el is None or el.kind != "point":
            self.pt_cache[label] = None
            return None
        res = self._point_el(el)
        self.pt_cache[label] = res
        return res

    def _point_el(self, el) -> Optional[Tuple[Any, Any]]:
        if el.free:
            return (sympy.Symbol(el.label + "x"), sympy.Symbol(el.label + "y"))
        cmd = _cmd_of(el.defn)
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\[", cmd)
        if not m:
            return None
        name = m.group(1).lower()
        args = _args_of(cmd)
        try:
            if name == "midpoint":
                if len(args) == 2:
                    a = self.point(args[0])
                    b = self.point(args[1])
                    if a and b:
                        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                if len(args) == 1:  # 线段中点
                    el1 = self.cons.elements.get(args[0])
                    if el1 and el1.kind == "segment":
                        sa = self.point(el1.defn.split("=")[0]) if False else None
                        # 线段由两点定义，取线段的定义
                        cm = _cmd_of(el1.defn)
                        am = _args_of(cm)
                        if len(am) == 2:
                            a = self.point(am[0])
                            b = self.point(am[1])
                            if a and b:
                                return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if name == "intersect":
                if len(args) == 2:
                    l1 = self.line(args[0])
                    l2 = self.line(args[1])
                    if l1 and l2:
                        x, y, det = _solve_linear(l1[0], l1[1], l1[2], l2[0], l2[1], l2[2])
                        if det != 0:
                            return (x, y)
            if name == "translate":
                if len(args) == 2:
                    a = self.point(args[0])
                    if not a:
                        return None
                    v = self.cons.elements.get(args[1])
                    if v and v.kind == "vector":
                        # 符号化向量：Vector[p,q] → q - p
                        cm = _cmd_of(v.defn)
                        am = _args_of(cm)
                        if len(am) == 2:
                            p = self.point(am[0])
                            q = self.point(am[1])
                            if p and q:
                                return (a[0] + q[0] - p[0], a[1] + q[1] - p[1])
                        return None
                    if args[1].startswith("("):
                        parts = args[1][1:-1].split(",")
                        if len(parts) == 2:
                            try:
                                return (a[0] + float(parts[0]), a[1] + float(parts[1]))
                            except ValueError:
                                return None
            if name == "reflect":
                if len(args) == 2:
                    a = self.point(args[0])
                    if not a:
                        return None
                    mir = self.cons.elements.get(args[1])
                    if mir and mir.kind == "point":
                        m = self.point(args[1])
                        if m:
                            return (2 * m[0] - a[0], 2 * m[1] - a[1])
                    if mir and mir.kind in ("line", "segment", "ray"):
                        l = self.line(args[1])
                        if l:
                            al, bl, cl = l
                            d = al * al + bl * bl
                            k = 2 * (al * a[0] + bl * a[1] + cl) / d
                            return (a[0] - al * k, a[1] - bl * k)
            if name == "rotate":
                if len(args) in (2, 3):
                    a = self.point(args[0])
                    if not a:
                        return None
                    ang = float(args[1].replace("deg", "")) if args[1].strip().replace(".", "").isdigit() else None
                    if ang is None:
                        return None
                    th = math.radians(ang)
                    # 取整消除浮点噪声（cos90°≈6e-17 → 0）
                    cv = round(math.cos(th), 12)
                    sv = round(math.sin(th), 12)
                    cxp = cyp = sympy.S.Zero
                    if len(args) == 3:
                        c = self.point(args[2])
                        if c:
                            cxp, cyp = c
                    dx = a[0] - cxp
                    dy = a[1] - cyp
                    return (cxp + dx * cv - dy * sv,
                            cyp + dx * sv + dy * cv)
        except Exception:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
            return None
        return None

    def line(self, label: str) -> Optional[Tuple[Any, Any, Any]]:
        """返回直线/线段/射线符号方程 ax+by+c=0 或 None。"""
        if label in self.line_cache:
            return self.line_cache[label]
        el = self.cons.elements.get(label)
        if el is None:
            self.line_cache[label] = None
            return None
        res = None
        if el.kind in ("line", "segment", "ray"):
            if el.free:
                res = (sympy.Rational(el.a), sympy.Rational(el.b), sympy.Rational(el.c))
            else:
                cmd = _cmd_of(el.defn)
                m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\[", cmd)
                if m:
                    name = m.group(1).lower()
                    args = _args_of(cmd)
                    if name in ("line", "segment", "ray") and len(args) == 2:
                        p = self.point(args[0])
                        q = self.point(args[1])
                        if p and q:
                            res = self._line_through(p, q)
        self.line_cache[label] = res
        return res

    def _line_through(self, p, q):
        x1, y1 = p
        x2, y2 = q
        a = y1 - y2
        b = x2 - x1
        c = x1 * y2 - x2 * y1
        return (a, b, c)

    def circle(self, label: str) -> Optional[Dict[str, Any]]:
        """圆/圆锥曲线的符号方程：返回 (a,b,c,d,e,f) 或 None。"""
        el = self.cons.elements.get(label)
        if el is None:
            return None
        if el.kind == "circle":
            if el.free:
                cx, cy, r = el.cx, el.cy, el.r
                return (sympy.S.One, sympy.S.Zero, sympy.S.One,
                        -2 * cx, -2 * cy, cx * cx + cy * cy - r * r)
            cmd = _cmd_of(el.defn)
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\[", cmd)
            if m:
                name = m.group(1).lower()
                args = _args_of(cmd)
                if name == "circle" and len(args) == 2:
                    c = self.point(args[0])
                    p = self.point(args[1])
                    if c and p:
                        return (sympy.S.One, sympy.S.Zero, sympy.S.One,
                                -2 * c[0], -2 * c[1],
                                c[0] * c[0] + c[1] * c[1]
                                - (p[0] - c[0]) ** 2 - (p[1] - c[1]) ** 2)
                if name == "circle" and len(args) == 3:  # 外接圆（三点）
                    a = self.point(args[0])
                    b = self.point(args[1])
                    c = self.point(args[2])
                    if a and b and c:
                        return self._circumcircle(a, b, c)
        return None

    def _circumcircle(self, a, b, c):
        x1, y1 = a
        x2, y2 = b
        x3, y3 = c
        d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        if d == 0:
            return None
        ux = ((x1 ** 2 + y1 ** 2) * (y2 - y3) + (x2 ** 2 + y2 ** 2) * (y3 - y1)
              + (x3 ** 2 + y3 ** 2) * (y1 - y2)) / d
        uy = ((x1 ** 2 + y1 ** 2) * (x3 - x2) + (x2 ** 2 + y2 ** 2) * (x1 - x3)
              + (x3 ** 2 + y3 ** 2) * (x2 - x1)) / d
        r2 = (ux - x1) ** 2 + (uy - y1) ** 2
        return (sympy.S.One, sympy.S.Zero, sympy.S.One, -2 * ux, -2 * uy, ux ** 2 + uy ** 2 - r2)

    # ------------------------------------------------------------------
    # 结论多项式
    # ------------------------------------------------------------------
    def conclusion(self, kind: str, labels: List[str]) -> Optional[Any]:
        """返回结论多项式（期望恒为零）或 None。"""
        if kind in ("parallel", "perpendicular"):
            l1 = self.line(labels[0])
            l2 = self.line(labels[1])
            if not l1 or not l2:
                return None
            if kind == "parallel":
                return sympy.expand(l1[0] * l2[1] - l1[1] * l2[0])
            return sympy.expand(l1[0] * l2[0] + l1[1] * l2[1])
        if kind == "collinear":
            a = self.point(labels[0])
            b = self.point(labels[1])
            c = self.point(labels[2])
            if not (a and b and c):
                return None
            return sympy.expand((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        if kind == "concyclic":
            pts = [self.point(l) for l in labels]
            if not all(pts):
                return None
            # 四点共圆：行列式 |x²+y², x, y, 1| = 0
            rows = [[p[0] ** 2 + p[1] ** 2, p[0], p[1], 1] for p in pts]
            det = rows[0][0] * (rows[1][1] * (rows[2][2] * rows[3][3] - rows[2][3] * rows[3][2])
                                - rows[1][2] * (rows[2][1] * rows[3][3] - rows[2][3] * rows[3][1])
                                + rows[1][3] * (rows[2][1] * rows[3][2] - rows[2][2] * rows[3][1]))
            det -= rows[0][1] * (rows[1][0] * (rows[2][2] * rows[3][3] - rows[2][3] * rows[3][2])
                                 - rows[1][2] * (rows[2][0] * rows[3][3] - rows[2][3] * rows[3][0])
                                 + rows[1][3] * (rows[2][0] * rows[3][2] - rows[2][2] * rows[3][0]))
            det += rows[0][2] * (rows[1][0] * (rows[2][1] * rows[3][3] - rows[2][3] * rows[3][1])
                                 - rows[1][1] * (rows[2][0] * rows[3][3] - rows[2][3] * rows[3][0])
                                 + rows[1][3] * (rows[2][0] * rows[3][1] - rows[2][1] * rows[3][0]))
            det -= rows[0][3] * (rows[1][0] * (rows[2][1] * rows[3][2] - rows[2][2] * rows[3][1])
                                 - rows[1][1] * (rows[2][0] * rows[3][2] - rows[2][2] * rows[3][0])
                                 + rows[1][2] * (rows[2][0] * rows[3][1] - rows[2][1] * rows[3][0]))
            return sympy.expand(det)
        if kind == "congruent":
            s1 = self.cons.elements.get(labels[0])
            s2 = self.cons.elements.get(labels[1])
            if not (s1 and s2 and s1.kind == "segment" and s2.kind == "segment"):
                return None
            c1 = _cmd_of(s1.defn)
            a1 = _args_of(c1)
            c2 = _cmd_of(s2.defn)
            a2 = _args_of(c2)
            if len(a1) != 2 or len(a2) != 2:
                return None
            p = self.point(a1[0])
            q = self.point(a1[1])
            r = self.point(a2[0])
            s = self.point(a2[1])
            if not (p and q and r and s):
                return None
            return sympy.expand((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                                - (r[0] - s[0]) ** 2 - (r[1] - s[1]) ** 2)
        if kind == "concurrent":
            l1 = self.line(labels[0])
            l2 = self.line(labels[1])
            l3 = self.line(labels[2])
            if not (l1 and l2 and l3):
                return None
            a1, b1, c1 = l1
            a2, b2, c2 = l2
            a3, b3, c3 = l3
            return sympy.expand(a1 * (b2 * c3 - b3 * c2) - b1 * (a2 * c3 - a3 * c2)
                                + c1 * (a2 * b3 - a3 * b2))
        return None

    # ------------------------------------------------------------------
    # 证明主入口
    # ------------------------------------------------------------------
    def prove(self, kind: str, labels: List[str]) -> ProverResult:
        conclusion = self.conclusion(kind, labels)
        if conclusion is None:
            return ProverResult(None, "无法符号化该命题（缺少符号坐标推导）")
        if conclusion == 0:
            return ProverResult(True, "结论多项式恒为零：命题成立")
        try:
            simp = sympy.simplify(conclusion)
        except Exception:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
            simp = conclusion
        if simp == 0:
            return ProverResult(True, "化简后恒为零：命题成立")
        # 清除分母（交点坐标引入的有理式）
        num = sympy.together(simp).as_numer_denom()[0]
        num = sympy.expand(num)
        if num == 0:
            return ProverResult(True, "通分后分子恒为零：命题成立")
        # 非退化/反例检查：分子 ≠ 0 但含自由符号时，用数值采样区分
        # "确实存在反例（恒假）" 与 "未化简的恒真 / 依赖特殊位置（退化敏感）"。
        syms = list(num.free_symbols)
        if syms:
            import random
            worst = None
            for _ in range(8):
                subs = {}
                for sv in syms:
                    if random.random() < 0.3:
                        subs[sv] = random.choice([-2.0, -1.0, 0.0, 1.0, 2.0])
                    else:
                        subs[sv] = random.uniform(-3.0, 3.0)
                try:
                    val = float(num.evalf(subs=subs))
                except Exception:  # 数值/符号求值失败：本对象降级为 error/保持旧状态，不中断其余对象
                    continue
                if abs(val) > COARSE:
                    worst = val
                    break
            if worst is not None:
                return ProverResult(False, "命题不成立（存在反例；结论表达式 = " + str(num)[:70] + "）")
            return ProverResult(None, "无法判为恒假：数值采样均接近零，命题或成立、或仅在退化/特殊位置失效（结论表达式 = "
                                + str(num)[:70] + "），可补充非退化假设后重证")
        return ProverResult(False, "命题不成立（常数非零）")
