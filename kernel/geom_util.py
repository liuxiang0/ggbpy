"""通用几何算法（P3）：marching squares 等值线、多边形装配、圆锥曲线判定。

用途：
- 一般圆锥曲线（五点）与隐式不等式区域的绘制
- 线段装配为闭合多边形（不等式填充）
"""

from __future__ import annotations

import math
from typing import Callable, List, Optional, Tuple
from .tolerance import EPSILON, TIGHT, COORD, COARSE  # 统一数值容差（见 kernel/tolerance.py）

# 兼容既有调用：EPSILON 指向统一容差表里的 COORD


# ---------------------------------------------------------------------------
# Marching squares：隐式曲线 f(x,y)=0 的等值线段
# ---------------------------------------------------------------------------

# 16 种 case 的边交点表（扁平边索引，两两成段）。
# 角点：bit0=左下, bit1=右下, bit2=右上, bit3=左上
# 边：0=左, 1=下, 2=右, 3=上
_CASES = {
    0: [],
    1: [0, 1],
    2: [1, 2],
    3: [0, 2],
    4: [2, 3],
    5: [0, 1, 2, 3],   # 鞍点（对角连线）
    6: [1, 3],
    7: [0, 3],
    8: [3, 0],
    9: [1, 3],
    10: [1, 2, 3, 0],  # 鞍点（对角连线）
    11: [2, 3],
    12: [2, 0],
    13: [1, 2],
    14: [1, 0],
    15: [],
}


def marching_squares(
    f: Callable[[float, float], float],
    xmin: float, xmax: float, ymin: float, ymax: float,
    nx: int = 90, ny: int = 70,
) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """返回 f(x,y)=0 等值线的线段列表（世界坐标）。"""
    segs: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    xs = [xmin + (xmax - xmin) * i / nx for i in range(nx + 1)]
    ys = [ymin + (ymax - ymin) * i / ny for i in range(ny + 1)]
    def _safe(x, y):
        try:
            v = f(x, y)
            v = float(v)
            return v if math.isfinite(v) else float("nan")
        except Exception:
            return float("nan")   # 奇点/除零：该网格点视为无效，仅影响邻近单元
    try:
        vals = [[_safe(x, y) for x in xs] for y in ys]
    except Exception:
        return segs
    for j in range(ny):
        for i in range(nx):
            v00 = vals[j][i]          # 左下
            v10 = vals[j][i + 1]      # 右下
            v11 = vals[j + 1][i + 1]  # 右上
            v01 = vals[j + 1][i]      # 左上
            code = 0
            if v00 < 0: code |= 1
            if v10 < 0: code |= 2
            if v11 < 0: code |= 4
            if v01 < 0: code |= 8
            case_segs = _CASES.get(code, [])
            if not case_segs:
                continue
            x0, x1, y0, y1 = xs[i], xs[i + 1], ys[j], ys[j + 1]

            def edge_pt(e: int):
                # 边：0=左, 1=下, 2=右, 3=上
                if e == 0:
                    t = v00 / (v00 - v01) if abs(v00 - v01) > EPSILON else 0.5
                    return (x0, y0 + t * (y1 - y0))
                if e == 1:
                    t = v00 / (v00 - v10) if abs(v00 - v10) > EPSILON else 0.5
                    return (x0 + t * (x1 - x0), y0)
                if e == 2:
                    t = v10 / (v10 - v11) if abs(v10 - v11) > EPSILON else 0.5
                    return (x1, y0 + t * (y1 - y0))
                t = v01 / (v01 - v11) if abs(v01 - v11) > EPSILON else 0.5
                return (x0 + t * (x1 - x0), y1)

            pts = [edge_pt(e) for e in case_segs]
            for k in range(0, len(pts), 2):
                segs.append((pts[k], pts[k + 1]))
    return segs


def assemble_loops(
    segs: List[Tuple[Tuple[float, float], Tuple[float, float]]],
    tol: float = COARSE,
) -> List[List[Tuple[float, float]]]:
    """把等值线段首尾相接装配为闭合多边形。返回多边形列表（每个为点列表）。"""
    segs = [list(s) for s in segs]
    loops: List[List[Tuple[float, float]]] = []

    def close(a, b) -> bool:
        return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol

    while segs:
        current = segs.pop(0)
        loop = [current[0], current[1]]
        extended = True
        while extended and segs:
            extended = False
            tail = loop[-1]
            best_idx = -1
            best = None
            for idx, s in enumerate(segs):
                if close(s[0], tail):
                    best = s[1]
                    best_idx = idx
                    break
                if close(s[1], tail):
                    best = s[0]
                    best_idx = idx
                    break
            if best_idx >= 0:
                loop.append(best)
                segs.pop(best_idx)
                extended = True
        if loop and close(loop[0], loop[-1]):
            loop.pop()
        if len(loop) >= 3:
            loops.append(loop)
    return loops


# ---------------------------------------------------------------------------
# 圆锥曲线
# ---------------------------------------------------------------------------

def conic_from_five_points(pts: List[Tuple[float, float]]) -> Optional[Tuple[float, float, float, float, float, float]]:
    """五点确定一般圆锥曲线 ax²+bxy+cy²+dx+ey+f=0。
    选绝对值最大的系数归一化以保证数值稳定。返回系数元组或 None。"""
    if len(pts) != 5:
        return None
    rows = []
    for (x, y) in pts:
        rows.append([x * x, x * y, y * y, x, y, 1.0])
    # 高斯消元：Ax = 0 的零空间（固定一个系数为 1）
    best = None
    for fix in range(6):
        A = [r[:fix] + r[fix + 1:] for r in rows]
        b = [-r[fix] for r in rows]
        sol = _solve5(A, b)
        if sol is None:
            continue
        coeffs = sol[:fix] + [1.0] + sol[fix:]
        best = coeffs
        break
    if best is None:
        return None
    # 归一化
    norm = max(abs(v) for v in best)
    if norm < EPSILON:
        return None
    return tuple(v / norm for v in best)


def _solve5(A: List[List[float]], b: List[float]) -> Optional[List[float]]:
    """5x5 高斯消元。"""
    n = 5
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < EPSILON:
            return None
        M[col], M[piv] = M[piv], M[col]
        for r in range(n):
            if r != col and abs(M[r][col]) > TIGHT:
                f = M[r][col] / M[col][col]
                for c in range(col, n + 1):
                    M[r][c] -= f * M[col][c]
    x = [0.0] * n
    for i in range(n):
        x[i] = M[i][n] / M[i][i]
    return x


def conic_canonical(coeffs):
    """一般系数 (a,b,c,d,e,f) → 规范参数 (cx, cy, semi_a, semi_b, angle, ctype)。

    椭圆/圆：semi_a 为长轴半轴，angle 指向长轴方向；
    双曲线：semi_a 为实半轴，angle 指向实轴方向。
    退化、抛物线或无法参数化时返回 None。
    """
    a, b, c, d, e, f = coeffs
    det2 = 4 * a * c - b * b
    if abs(det2) < COORD:
        return None
    # 中心：解 [2a b; b 2c]·(cx,cy) = (-d,-e)
    x0 = (b * e - 2 * c * d) / det2
    y0 = (b * d - 2 * a * e) / det2
    k = a * x0 * x0 + b * x0 * y0 + c * y0 * y0 + d * x0 + e * y0 + f
    if abs(k) < COORD:
        return None
    if k > 0:                       # 整体缩放符号，令中心值 k<0（实曲线保证）
        a, b, c, d, e, f = -a, -b, -c, -d, -e, -f
        k = -k
    th0 = 0.5 * math.atan2(b, a - c)
    cth, sth = math.cos(th0), math.sin(th0)
    A = a * cth * cth + b * cth * sth + c * sth * sth
    C = a * sth * sth - b * cth * sth + c * cth * cth
    if det2 > 0:                    # 椭圆 / 圆（k<0 ⇒ A,C>0）
        if A > C:                   # 长轴在 θ0+90° 方向
            ang = th0 + math.pi / 2
            sa, sb = math.sqrt(-k / C), math.sqrt(-k / A)
        else:
            ang = th0
            sa, sb = math.sqrt(-k / A), math.sqrt(-k / C)
        ct = "circle" if abs(sa - sb) < COARSE * max(sa, sb) else "ellipse"
        return (x0, y0, sa, sb, ang, ct)
    # 双曲线：实轴沿系数与 k 异号的轴方向
    if A > 0:
        return (x0, y0, math.sqrt(-k / A), math.sqrt(k / C), th0, "hyperbola")
    return (x0, y0, math.sqrt(-k / C), math.sqrt(k / A), th0 + math.pi / 2, "hyperbola")


def conic_classify(a, b, c, d, e, f):
    """判定圆锥曲线类型：disc = b²-4ac。返回 ('ellipse'|'hyperbola'|'parabola'|'circle'|'degenerate')。"""
    disc = b * b - 4 * a * c
    if abs(disc) < COORD and abs(a) < COORD and abs(c) < COORD and abs(b) < COORD:
        return "degenerate"   # 线性（退化为直线/点/空）
    if abs(disc) < COORD:
        return "parabola"
    if abs(a - c) < COORD and abs(b) < COORD and abs(a) > COORD:
        return "circle"
    if disc < 0:
        return "ellipse"
    return "hyperbola"


def line_conic_intersect(px, py, dx, dy, coeffs, seg=None, ray=None):
    """直线（点+方向）与圆锥曲线求交。返回交点列表（0/1/2 个）。"""
    a, b, c, d, e, f = coeffs
    A = a * dx * dx + b * dx * dy + c * dy * dy
    B = 2 * a * px * dx + b * (px * dy + py * dx) + 2 * c * py * dy + d * dx + e * dy
    C = a * px * px + b * px * py + c * py * py + d * px + e * py + f
    pts: List[Tuple[float, float]] = []
    if abs(A) < EPSILON:
        if abs(B) < EPSILON:
            return pts
        t = -C / B
        pts.append((px + t * dx, py + t * dy))
        return pts
    disc = B * B - 4 * A * C
    if disc < -COORD:
        return pts
    if disc < 0:
        disc = 0.0
    sq = math.sqrt(disc)
    for t in ((-B + sq) / (2 * A), (-B - sq) / (2 * A)):
        pts.append((px + t * dx, py + t * dy))
    return pts
