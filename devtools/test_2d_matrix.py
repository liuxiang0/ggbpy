#!/usr/bin/env python3
"""ggbpy 2D 内核检测矩阵（第十三批 P0-C：补上 2D 回归可复现能力）

覆盖 REVIEW_12_BATCHES.md 中「从未被任何脚本引用」的 2D 命令：
变换 / 圆锥曲线 / 微积分 / 统计与回归 / 线代与复数 / 编辑 / 宏 / 布尔判定。

用法：
    python3 -B devtools/test_2d_matrix.py        # 内核层，无需服务
退出码：0 = 全部通过，1 = 有失败。
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.construction import Construction  # noqa: E402

PASS = 0
FAIL = 0
FAILED = []
PROBLEMS = []


def section(title: str) -> None:
    print("\n=== " + title + " ===")


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  OK   " + name + (("  [" + detail + "]") if detail else ""))
    else:
        FAIL += 1
        FAILED.append(name)
        print("  FAIL " + name + "  " + detail)


def close(a, b, eps: float = 1e-9) -> bool:
    try:
        return abs(float(a) - float(b)) < eps
    except Exception:
        return False


def build(lines):
    """构造一批命令，返回 (cons, 首个错误)。"""
    c = Construction()
    for ln in lines:
        msg = c.process(ln)
        if not msg.startswith("OK"):
            return c, msg
    return c, None


def el_of(c, label):
    return c.elements.get(label)


def drawn(c, label, view=(-10, 10, -10, 10)):
    el = c.elements.get(label)
    if el is None:
        return None
    try:
        return el.draw(view)
    except Exception:
        return None


# ---------------------------------------------------------------------------
section("A. 变换与几何构造")
c, err = build([
    "A=(0,0)", "B=(4,0)", "C=(0,3)", "D=(2,2)", "E=(6,0)",
    "ax=Line[(0,0),(1,0)]", "cir=Circle[A,2]", "poly=Polygon[A,B,C]",
    "t0=0.5", "t90=1.5707963267948966",
    "d1=Dilate[C,2,A]", "d2=Dilate[C,2]", "r1=Reflect[C,ax]", "r2=Reflect[C,A]",
    "onp=PointOnPath[cir]", "onc=PointOnCircle[cir,t90]",
    "reg=RegularPolygon[A,B,5]",
    "per=PerpendicularLine[D,ax]", "pb=PerpendicularBisector[A,B]",
    "ab=AngleBisector[A,B,C]", "ft=Foot[D,ax]",
    "cc=Circumcircle[poly]", "ic=Incenter[poly]", "icr=Incircle[poly]",
    "sl=Slope[Line[(0,0),(1,2)]]", "tg=Tangent[E,cir]", "poly2=Polygon[B,C,D]",
])
check("几何用例构造", err is None, str(err))
if err is None:
    d1, d2 = el_of(c, "d1"), el_of(c, "d2")
    check("Dilate[C,2,A] = (0,6)", close(d1.x, 0, 1e-9) and close(d1.y, 6, 1e-9), "(%s,%s)" % (d1.x, d1.y))
    check("Dilate[C,2]（绕原点）= (0,6)", close(d2.x, 0, 1e-9) and close(d2.y, 6, 1e-9), "(%s,%s)" % (d2.x, d2.y))
    r1, r2 = el_of(c, "r1"), el_of(c, "r2")
    check("Reflect[C, x轴] = (0,−3)", close(r1.x, 0, 1e-9) and close(r1.y, -3, 1e-9), "(%s,%s)" % (r1.x, r1.y))
    check("Reflect[C,A]（点对称）= (0,−3)", close(r2.x, 0, 1e-9) and close(r2.y, -3, 1e-9), "(%s,%s)" % (r2.x, r2.y))
    onp = el_of(c, "onp")
    check("PointOnPath[圆] 落在圆上", close(math.hypot(onp.x, onp.y), 2, 1e-9), "r=%.9f" % math.hypot(onp.x, onp.y))
    onc = el_of(c, "onc")
    check("PointOnCircle[圆,π/2] = (0,2)", close(onc.x, 0, 1e-9) and close(onc.y, 2, 1e-9), "(%s,%s)" % (onc.x, onc.y))
    reg_d = drawn(c, "reg")
    pts_reg = reg_d.get("pts") if reg_d else None
    check("RegularPolygon 顶点数 = 5", bool(pts_reg) and len(pts_reg) == 5,
          "n=%s" % (len(pts_reg) if pts_reg else None))
    if pts_reg:
        sides = [math.dist(pts_reg[i], pts_reg[(i + 1) % 5]) for i in range(5)]
        check("正五边形各边等长（=4）", max(sides) - min(sides) < 1e-9 and close(sides[0], 4, 1e-9),
              "%.6f..%.6f" % (min(sides), max(sides)))
    per_d = drawn(c, "per")
    check("PerpendicularLine[D,x轴] = 直线 x=2",
          per_d is not None and close(per_d["a"] * 2, -per_d["c"], 1e-9) and close(per_d["b"], 0, 1e-9),
          per_d.get("value") if per_d else "None")
    pb_d = drawn(c, "pb")
    check("PerpendicularBisector 为 x=2（过中点且竖直）",
          pb_d is not None and close(pb_d["b"], 0, 1e-9) and close(pb_d["a"] * 2 + pb_d["c"], 0, 1e-9),
          pb_d.get("value") if pb_d else "None")
    ab_d = drawn(c, "ab")
    check("AngleBisector 过顶点 B(4,0)",
          ab_d is not None and close(ab_d["a"] * 4 + ab_d["c"], 0, 1e-9),
          ab_d.get("value") if ab_d else "None")
    ft = el_of(c, "ft")
    check("Foot[D, x轴] = (2,0)", close(ft.x, 2, 1e-9) and close(ft.y, 0, 1e-9), "(%s,%s)" % (ft.x, ft.y))
    cc_d = drawn(c, "cc")
    check("Circumcircle 圆心到三点等距",
          cc_d is not None and close(math.hypot(cc_d["cx"] - 0, cc_d["cy"] - 0), cc_d["r"], 1e-9)
          and close(math.hypot(cc_d["cx"] - 4, cc_d["cy"] - 0), cc_d["r"], 1e-9)
          and close(math.hypot(cc_d["cx"] - 0, cc_d["cy"] - 3), cc_d["r"], 1e-9),
          "c=(%.6f,%.6f) r=%.6f" % (cc_d["cx"], cc_d["cy"], cc_d["r"]) if cc_d else "None")
    ic = el_of(c, "ic")
    check("Incenter[(0,0),(4,0),(0,3)] = (1,1)", close(ic.x, 1, 1e-9) and close(ic.y, 1, 1e-9),
          "(%s,%s)" % (ic.x, ic.y))
    icr_d = drawn(c, "icr")
    check("Incircle 半径 = 1（r=(a+b−c)/2）", icr_d is not None and close(icr_d.get("r", 0), 1, 1e-9),
          "r=%s" % (icr_d.get("r") if icr_d else None))
    check("Slope[Line[(0,0),(1,2)]] = 2", close(el_of(c, "sl").value, 2, 1e-9),
          str(el_of(c, "sl").value))
    tg_d = drawn(c, "tg")
    if tg_d:
        dd = abs(tg_d["c"]) / max(1e-12, math.hypot(tg_d["a"], tg_d["b"]))
        check("Tangent[圆外点, 圆] 到圆心距离 = r", close(dd, 2, 1e-9), "d=%.9f（%s）" % (dd, tg_d.get("value")))
    else:
        check("Tangent[圆外点, 圆] 到圆心距离 = r", False, "无法取切线")

    # 轨迹 / 逆矩阵
    c.process("driver=PointOnCircle[cir,t0]")
    c.process("mid=Midpoint[A,driver]")
    c.process("loc=Locus[mid,driver]")
    loc_d = drawn(c, "loc")
    check("Locus[依赖点, 圆上动点] 生成轨迹点", loc_d is not None and len(loc_d.get("pts", [])) > 5,
          "n=%s" % (len(loc_d.get("pts", [])) if loc_d else None))
    c.process("mx=Matrix[{{1,2},{3,4}}]")
    c.process("inv=Inverse[mx]")
    inv = el_of(c, "inv")
    inv_data = inv.data if inv is not None else None
    ok_inv = inv_data is not None and close(inv_data[0][0], -2, 1e-9) and close(inv_data[0][1], 1, 1e-9) \
        and close(inv_data[1][0], 1.5, 1e-9) and close(inv_data[1][1], -0.5, 1e-9)
    check("Inverse[矩阵] = [[−2,1],[1.5,−0.5]]", ok_inv, str(inv_data.tolist() if inv_data is not None else None))

# ---------------------------------------------------------------------------
section("B. 圆锥曲线")
c, err = build([
    "F1=(-2,0)", "F2=(2,0)", "P=(0,3)",
    "el1=Ellipse[F1,F2,P]", "pb=Parabola[(0,2),Line[(-2,-2),(2,-2)]]",
    "hy=Hyperbola[(-4,0),(4,0),(3,1)]", "co=Conic[(0,0),(2,0),(2,2),(0,2),(1,3)]",
])
check("圆锥曲线用例构造", err is None, str(err))
if err is None:
    el1 = drawn(c, "el1")
    check("Ellipse ctype=ellipse 且 a=√13、b=3",
          el1 is not None and el1.get("ctype") == "ellipse" and close(el1["semi_a"], math.sqrt(13), 1e-9)
          and close(el1["semi_b"], 3, 1e-9),
          "a=%s b=%s" % (el1.get("semi_a") if el1 else None, el1.get("semi_b") if el1 else None))
    pb = drawn(c, "pb")
    check("Parabola 焦点/准线字段齐全",
          pb is not None and pb.get("ctype") == "parabola" and len(pb.get("focus", [])) == 2
          and len(pb.get("directrix", [])) == 3,
          str({k: pb.get(k) for k in ("ctype", "focus", "directrix")}) if pb else "None")
    hy = el_of(c, "hy")
    check("Hyperbola（非退化）建成", hy is not None and not hy.error, str(hy.error) if hy else None)
    co = el_of(c, "co")
    check("Conic[五点] 建成", co is not None and not co.error, str(co.error) if co else None)
    c.process("fo=Focus[Ellipse[(-1,0),(1,0),(0,2)]]")
    fo = el_of(c, "fo")
    check("Focus[椭圆] 返回焦点（±1 之一）",
          fo is not None and (close(abs(fo.x), 1, 1e-6) and close(fo.y, 0, 1e-6)),
          "(%s,%s)" % (fo.x, fo.y) if fo is not None else None)
    c.process("badhy=Hyperbola[(0,0),(4,0),(2,0)]")
    check("退化为直线的双曲线 → 明确报错", bool(el_of(c, "badhy").error), str(el_of(c, "badhy").error))

# ---------------------------------------------------------------------------
section("C. 微积分与迭代")
c, err = build([
    "g(x)=x^2-2x", "q(x)=x^2-4",
    "r1=Root[q]", "r2=Root[q,10]", "ex=Extremum[g,-1,3]",
    "d1=Derivative[g]", "d2=Derivative[g,2]",
    "i1=Integral[g]", "i2=Integral[g,0,2]",
    "sq(x)=x^2", "it0=Iteration[g,3,2]", "it1=Iteration[sq,2,2]", "itl=IterationList[g,3,3]",
])
check("微积分用例构造", err is None, str(err))
if err is None:
    check("Root[x²−4] = 最小根 −2", close(el_of(c, "r1").x, -2, 1e-9), str(el_of(c, "r1").x))
    check("Root[x²−4, 起点10] = 2", close(el_of(c, "r2").x, 2, 1e-9), str(el_of(c, "r2").x))
    ex = el_of(c, "ex")
    check("Extremum[x²−2x, [−1,3]] = (1,−1)", close(ex.x, 1, 1e-9) and close(ex.y, -1, 1e-9),
          "(%s,%s)" % (ex.x, ex.y))
    d1 = el_of(c, "d1")
    check("Derivative[x²−2x] 在 x=3 取值 = 4", close(d1._eval1(3) if hasattr(d1, "_eval1") else None, 4, 1e-9),
          str(d1._eval1(3) if hasattr(d1, "_eval1") else None))
    d2 = el_of(c, "d2")
    check("Derivative[x²−2x, 2] = 2（二阶导为常数）",
          close(d2._eval1(0), 2, 1e-9) and close(d2._eval1(5), 2, 1e-9),
          "%s/%s" % (d2._eval1(0), d2._eval1(5)))
    i1 = el_of(c, "i1")
    f2, f0 = i1._eval1(2), i1._eval1(0)
    check("Integral[x²−2x] 原函数 F(2)−F(0) = 8/3 − 4 = −4/3", close(f2 - f0, -4 / 3, 1e-9),
          "%.9f" % (f2 - f0))
    check("Integral[x²−2x, 0, 2] = −4/3", close(el_of(c, "i2").value, -4 / 3, 1e-9),
          "%.9f" % el_of(c, "i2").value)
    check("Iteration[g,3,2]（g(x)=x²−2x，3 是不动点）= 3",
          close(el_of(c, "it0").value, 3, 1e-9), str(el_of(c, "it0").value))
    check("Iteration[x²,2,2] = ((2²)²) = 16", close(el_of(c, "it1").value, 16, 1e-9),
          str(el_of(c, "it1").value))
    itl = el_of(c, "itl")
    check("IterationList[g,3,3] 含 4 项且首项 3", len(itl.items) == 4 and close(itl.items[0], 3, 1e-9),
          str([round(x, 4) for x in itl.items]))
    c.process("ineq=SolveIneq[x^2<4]")
    check("SolveIneq[x²<4] 给出解集", el_of(c, "ineq") is not None and not el_of(c, "ineq").error,
          str(el_of(c, "ineq").error if el_of(c, "ineq") else None))

# ---------------------------------------------------------------------------
section("D. 圆弧 / 扇形 / 半圆")
c, err = build([
    "O=(0,0)", "A=(2,0)", "B=(0,2)", "P=(4,0)", "Q=(0,3)",
    "arc=Arc[A,B,O]", "sec=Sector[A,B,O]", "sc=Semicircle[P,Q]", "cir=Circle[O,2]",
])
check("圆弧用例构造", err is None, str(err))
if err is None:
    arc_d = drawn(c, "arc")
    check("Arc[A,B,O]：圆心 O、半径 = |OA| = 2", close(arc_d.get("r", 0), 2, 1e-9)
          and close(arc_d.get("cx", 9), 0, 1e-9) and close(arc_d.get("cy", 9), 0, 1e-9),
          "r=%s" % (arc_d.get("r") if arc_d else None))
    check("Arc 端点角度 0 → π/2（弧过 A、B）",
          close(arc_d.get("ang1", 9), 0, 1e-9) and close(arc_d.get("ang2", 9), math.pi / 2, 1e-9),
          "%.6f → %.6f" % (arc_d.get("ang1", 0), arc_d.get("ang2", 0)))
    sec_d = drawn(c, "sec")
    check("Sector 标记 sector=True 且 r=2", sec_d.get("sector") is True and close(sec_d.get("r", 0), 2, 1e-9),
          str({k: sec_d.get(k) for k in ("sector", "r")}))
    sc_d = drawn(c, "sc")
    check("Semicircle 半径 = |PQ|/2 = 2.5、圆心为中点 (2,1.5)",
          sc_d is not None and close(sc_d.get("r", 0), 2.5, 1e-9)
          and close(sc_d.get("cx", 9), 2, 1e-9) and close(sc_d.get("cy", 9), 1.5, 1e-9),
          "r=%s c=(%s,%s)" % (sc_d.get("r"), sc_d.get("cx"), sc_d.get("cy")) if sc_d else "None")
    msg_cf = c.process("cf=Circumference[cir]")
    cf = el_of(c, "cf")
    check("Circumference[圆 r=2] = 4π", msg_cf.startswith("OK") and cf is not None
          and close(cf.value, 4 * math.pi, 1e-9), str(cf.value) if cf else msg_cf[:40])
    # 圆心非等距 → 明确报错（本轮修复回归）
    c.process("M=(0,3)")
    c.process("badarc=Arc[O,P,M]")
    check("圆心与两端点不等距 → 明确报错（不再静默给平均半径）",
          bool(el_of(c, "badarc").error) and "等距" in el_of(c, "badarc").error,
          str(el_of(c, "badarc").error))

# ---------------------------------------------------------------------------
section("E. 折线 / 射线 / 刚性多边形")
c, err = build([
    "A=(0,0)", "B=(4,0)", "C=(0,3)",
    "pl=Polyline[A,B,C]", "ry=Ray[A,B]", "rp=RigidPolygon[A,B,C]",
])
check("折线用例构造", err is None, str(err))
if err is None:
    pl_d = drawn(c, "pl")
    check("Polyline 含 3 点且总长 9（4+5）", pl_d is not None and len(pl_d.get("pts", [])) == 3
          and close(pl_d.get("len", 9), 9, 1e-6), str(pl_d.get("len") if pl_d else None))
    ry_d = drawn(c, "ry")
    check("Ray[A,B] 起点 A、方向 (1,0)",
          ry_d is not None and close(ry_d["ox"], 0, 1e-9) and close(ry_d["oy"], 0, 1e-9)
          and close(ry_d["ux"], 1, 1e-9) and close(ry_d["uy"], 0, 1e-9),
          ry_d.get("value") if ry_d else "None")
    rp_d = drawn(c, "rp")
    check("RigidPolygon 标记 rigid 且面积 = 6",
          rp_d is not None and rp_d.get("rigid") and "6" in str(rp_d.get("value")),
          "%s / %s" % (rp_d.get("rigid") if rp_d else None, rp_d.get("value") if rp_d else None))
    # 移动一个顶点后边长必须保持（刚性语义）
    before = [math.dist(rp_d["pts"][i], rp_d["pts"][(i + 1) % 3]) for i in range(3)]
    c.move("A", 1.5, 1.5)
    after_d = drawn(c, "rp")
    after = [math.dist(after_d["pts"][i], after_d["pts"][(i + 1) % 3]) for i in range(3)]
    check("RigidPolygon 顶点移动后边长保持不变",
          all(close(before[i], after[i], 1e-9) for i in range(3)),
          "before=%s after=%s" % ([round(x, 4) for x in before], [round(x, 4) for x in after]))

# ---------------------------------------------------------------------------
section("F. 统计与数值")
c, err = build([
    "L={1,2,3,4,5,6,7,8,9,10}", "L2={1,2,2,3}",
    "s1=Sum[L]", "s2=Mean[L]", "s3=Median[L]", "s4=Mode[L2]",
    "s5=Min[L]", "s6=Max[L]", "s7=Stdev[L]", "s8=Variance[L]",
    "s9=Sort[{3,1,2}]", "s10=Normal[0,1,0]", "s11=NormalDist[0,1]",
    "s12=Q1[L]", "s13=Q3[L]", "s14=IQR[L]", "s15=BoxPlot[L]",
    "s16=Histogram[L]", "s17=BarChart[L2]", "s18=BarChart[{1,2,2,3}]", "s19=BarChart[1,2,2,3]",
    "s20=GCD[12,18]", "s21=LCM[4,6]", "s22=IsPrime[17]", "s23=IsPrime[18]",
    "s24=Divisors[12]", "s25=FactorsList[12]", "s26=nCr[5,2]", "s27=nPr[5,2]",
])
check("统计用例构造", err is None, str(err))
if err is None:
    vals = {k: el_of(c, k).value for k in ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8",
                                           "s12", "s13", "s14", "s20", "s21", "s26", "s27"]}
    check("Sum[1..10] = 55", close(vals["s1"], 55, 1e-9), str(vals["s1"]))
    check("Mean = 5.5 / Median = 5.5 / Mode[{1,2,2,3}] = 2",
          close(vals["s2"], 5.5, 1e-9) and close(vals["s3"], 5.5, 1e-9) and close(vals["s4"], 2, 1e-9),
          "%s/%s/%s" % (vals["s2"], vals["s3"], vals["s4"]))
    check("Min = 1 / Max = 10", close(vals["s5"], 1, 1e-9) and close(vals["s6"], 10, 1e-9),
          "%s/%s" % (vals["s5"], vals["s6"]))
    check("Variance = 8.25（总体方差）", close(vals["s8"], 8.25, 1e-9), str(vals["s8"]))
    check("Stdev = √8.25", close(vals["s7"], math.sqrt(8.25), 1e-9), str(vals["s7"]))
    check("Sort[{3,1,2}] 升序", [round(x, 6) for x in el_of(c, "s9").items] == [1.0, 2.0, 3.0],
          str(el_of(c, "s9").items))
    check("Normal[0,1,0] = 1/√(2π)", close(vals["s10"] if "s10" in vals else el_of(c, "s10").value,
                                         1 / math.sqrt(2 * math.pi), 1e-9), str(el_of(c, "s10").value))
    check("NormalDist 返回函数元素", el_of(c, "s11").kind == "function", el_of(c, "s11").kind)
    check("Q1 = 3.25 / Q3 = 7.75 / IQR = 4.5",
          close(vals["s12"], 3.25, 1e-9) and close(vals["s13"], 7.75, 1e-9) and close(vals["s14"], 4.5, 1e-9),
          "%s/%s/%s" % (vals["s12"], vals["s13"], vals["s14"]))
    check("BoxPlot / Histogram 建成",
          el_of(c, "s15").kind == "boxplot" and el_of(c, "s16").kind == "barchart",
          "%s/%s" % (el_of(c, "s15").kind, el_of(c, "s16").kind))
    for lab, form in [("s17", "列表元素"), ("s18", "{} 内联列表"), ("s19", "变参")]:
        check("BarChart 支持 " + form, el_of(c, lab).kind == "barchart" and not el_of(c, lab).error,
              "%s err=%s" % (el_of(c, lab).kind, el_of(c, lab).error))
    check("GCD = 6 / LCM = 12", close(vals["s20"], 6, 1e-9) and close(vals["s21"], 12, 1e-9),
          "%s/%s" % (vals["s20"], vals["s21"]))
    check("IsPrime[17]=true / IsPrime[18]=false",
          el_of(c, "s22").value is True and el_of(c, "s23").value is False,
          "%s/%s" % (el_of(c, "s22").value, el_of(c, "s23").value))
    check("Divisors[12] 有 6 个（1,2,3,4,6,12）", len(el_of(c, "s24").items) == 6,
          str(el_of(c, "s24").items))
    check("FactorsList[12] = {2,2,3}", [int(x) for x in el_of(c, "s25").items] == [2, 2, 3],
          str(el_of(c, "s25").items))
    check("nCr[5,2] = 10 / nPr[5,2] = 20", close(vals["s26"], 10, 1e-9) and close(vals["s27"], 20, 1e-9),
          "%s/%s" % (vals["s26"], vals["s27"]))

# ---------------------------------------------------------------------------
section("G. 线代与复数")
c, err = build([
    "m=Matrix[{{1,2},{3,4}}]", "d=Det[m]", "tr=Transpose[m]",
    "z1=3+4i", "cz=conj[z1]",
])
check("线代用例构造", err is None, str(err))
if err is None:
    check("Det[[1,2],[3,4]] = −2", close(el_of(c, "d").value, -2, 1e-9), str(el_of(c, "d").value))
    tr = el_of(c, "tr").data
    check("Transpose 正确", tr is not None and tr[0][1] == 3 and tr[1][0] == 2, str(tr.tolist() if tr is not None else None))
    cz = el_of(c, "cz")
    check("conj[3+4i] = 3−4i", close(cz.re, 3, 1e-9) and close(cz.im, -4, 1e-9), "%.1f%+.1fi" % (cz.re, cz.im))

# ---------------------------------------------------------------------------
section("H. 回归拟合")
c, err = build([
    "P1=(0,1)", "P2=(1,2)", "P3=(2,5)", "P4=(3,10)", "P5=(4,17)",
    "Pp={(1,2),(2,4),(3,6),(4,8)}",
    "fp=FitPoly[Pp,1]", "fe=FitExp[Pp]", "fl=FitLog[Pp]", "fw=FitPow[Pp]", "fs=FitSin[Pp]",
    "pm=PMCC[Pp]",
])
check("拟合用例构造", err is None, str(err))
if err is None:
    fp = el_of(c, "fp")
    check("FitPoly[线性点,1] 得 y≈2x（可求值）", close(fp._eval1(5), 10, 1e-6), "f(5)=%s" % fp._eval1(5))
    fp_d = fp.draw((-10, 10, -10, 10))
    samples = [p[1] for p in (fp_d or {}).get("samples", [])]
    finite = [v for v in samples if v == v]
    check("拟合函数可绘制（绘图样本全部有限）",
          bool(samples) and len(finite) == len(samples) and len(finite) > 100,
          "finite=%d/%d" % (len(finite), len(samples)))
    check("PMCC[完全线性点] = 1", close(el_of(c, "pm").value, 1, 1e-9), str(el_of(c, "pm").value))
    for lab, nm in [("fe", "FitExp"), ("fl", "FitLog"), ("fw", "FitPow"), ("fs", "FitSin")]:
        check(nm + " 返回函数元素", el_of(c, lab).kind == "function", el_of(c, lab).kind)
    # FitExpr：数据取当前所有自由点
    c2, e2 = build(["Q1=(0,1)", "Q2=(1,2)", "Q3=(2,3)", "Q4=(3,4)", "fx=FitExpr[y~a*x+b]"])
    check("FitExpr[y~a*x+b] 用自由点拟合", e2 is None and el_of(c2, "fx") is not None
          and close(el_of(c2, "fx")._eval1(10), 11, 1e-4),
          "f(10)=%s" % (el_of(c2, "fx")._eval1(10) if el_of(c2, "fx") else None))
    c3, _ = build([])
    m3 = c3.process("bad=FitExpr[L,y~a*x+b]")
    check("FitExpr 报错信息指明命令名与数据来源（本轮修复）",
          "FitExpr" in m3 and "自由点" in m3, m3[:60])

# ---------------------------------------------------------------------------
section("I. 编辑命令")
c, err = build([
    "A=(0,0)", "B=(4,0)", "C=(0,3)", "D=(2,2)",
    "k=2", "dep=Circle[A,k]",
])
check("编辑用例构造", err is None, str(err))
if err is None:
    c.process("SetValue[k,3]")
    check("SetValue 改变滑块并驱动依赖重算（圆半径 2→3）",
          close(el_of(c, "k").value, 3, 1e-9) and close(drawn(c, "dep").get("r", 0), 3, 1e-9),
          "k=%s r=%s" % (el_of(c, "k").value, drawn(c, "dep").get("r")))
    c.process("SetVisible[C,false]")
    check("SetVisible[C,false] 生效", el_of(c, "C").visible is False)
    c.process("SetColor[C,red]")
    check("SetColor[C,red] 应用调色板颜色", el_of(c, "C").color == "#e11d48", el_of(c, "C").color)
    c.process('SetColor[C,"#00ff00"]')
    check("SetColor[C,\"#00ff00\"]（带引号十六进制）生效", el_of(c, "C").color == "#00ff00", el_of(c, "C").color)
    c.process("SetColor[C,#0000ff]")
    check("SetColor[C,#0000ff]（无引号十六进制）生效", el_of(c, "C").color == "#0000ff", el_of(c, "C").color)
    c.process("SetCoords[C,5,5]")
    check("SetCoords[C,5,5] 生效", close(el_of(c, "C").x, 5, 1e-9) and close(el_of(c, "C").y, 5, 1e-9),
          "(%s,%s)" % (el_of(c, "C").x, el_of(c, "C").y))
    c.process("Rename[D,D2]")
    check("Rename 生效（D→D2，旧标签消失）",
          el_of(c, "D2") is not None and el_of(c, "D") is None)
    c.process("Redefine[D2,(9,9)]")
    check("Redefine 生效", close(el_of(c, "D2").x, 9, 1e-9) and close(el_of(c, "D2").y, 9, 1e-9),
          "(%s,%s)" % (el_of(c, "D2").x, el_of(c, "D2").y))
    c.process("Delete[B]")
    check("Delete 删除对象", el_of(c, "B") is None)
    msg_bad = c.process('SetValue[k,"abc"]')
    check("SetValue 非法值 → 明确报错", not msg_bad.startswith("OK"), msg_bad[:56])

# ---------------------------------------------------------------------------
section("J. 宏")
c, err = build([
    "A=(0,0)", "B=(4,0)", "C=(0,3)", "tri=Polygon[A,B,C]", "cen=Centroid[tri]",
])
check("宏用例构造", err is None, str(err))
if err is None:
    msg = c.process("MacroCreate[tri6,{A,B,C},{tri,cen}]")
    check("MacroCreate 成功", msg.startswith("OK"), msg[:60])
    for _ln in ("P1=(0,0)", "P2=(2,0)", "P3=(0,2)"):
        c.process(_ln)
    msg2 = c.process("mm=tri6[P1,P2,P3]")
    check("宏执行成功", msg2.startswith("OK"), msg2[:60])
    from kernel import macro as _macro
    check("MacroList 含新宏", "tri6" in _macro.MACROS, str(sorted(_macro.MACROS.keys())))
    msg3 = c.process("MacroDelete[tri6]")
    check("MacroDelete 成功", msg3.startswith("OK") and "tri6" not in _macro.MACROS, msg3[:40])

# ---------------------------------------------------------------------------
section("K. 布尔判定（符号证明 + 数值兜底）")
c, err = build([
    "A=(0,0)", "B=(4,0)", "C=(0,3)", "D=(2,2)", "E=(1,1)",
    "l1=Line[A,B]", "l2=Line[(0,5),(1,5)]", "l3=Line[C,D]",
    "b1=AreParallel[l1,l2]", "b2=AreParallel[l1,l3]",
    "b3=ArePerpendicular[l1,Line[(0,0),(0,2)]]", "b4=ArePerpendicular[l1,l2]",
    "b5=AreCollinear[A,B,(2,0)]", "b6=AreCollinear[A,B,D]",
    "b7=AreConcurrent[Line[(0,0),(1,1)],Line[(0,0),(1,-1)],Line[(0,0),(2,1)]]",
    "b8=AreConcurrent[Line[(0,0),(1,1)],Line[(0,1),(1,2)],Line[(0,0),(1,2)]]",
    "b9=AreConcyclic[(0,0),(2,0),(2,2),(0,2)]",
    "b10=AreConcyclic[A,B,C,E]",
    "b11=AreCongruent[Segment[(0,0),(3,4)],Segment[(1,1),(4,5)]]",
    "b12=AreCongruent[Segment[A,B],Segment[C,D]]",
])
check("布尔判定用例构造", err is None, str(err))
if err is None:
    exp = [("b1", True, "两水平线平行"), ("b2", False, "y=0 与 CD 不平行"),
           ("b3", True, "x 轴与竖直线垂直"), ("b4", False, "x 轴与水平线不垂直"),
           ("b5", True, "(0,0),(4,0),(2,0) 共线"), ("b6", False, "(0,0),(4,0),(2,2) 不共线"),
           ("b7", True, "三线共点（过原点）"), ("b8", False, "两平行线 + 第三条 → 不共点"),
           ("b9", True, "正方形四顶点共圆"), ("b10", False, "四点不共圆"),
           ("b11", True, "两条长度都是 5 的线段"), ("b12", False, "|AB|=4 vs |CD|=√13")]
    for lab, want, desc in exp:
        el = el_of(c, lab)
        check("Are* %s：%s = %s" % (lab, desc, want),
              el is not None and el.value is want, "%r（%s）" % (getattr(el, "value", None),
                                                               getattr(el, "detail", "")[:38]))

# ---------------------------------------------------------------------------
section("L. 本轮修复回归（写矩阵时发现的 bug）")
# 1) Arc/Sector 半径：圆心等距时用 |CA|（此前取平均 → 两端都不在弧上）
c, err = build(["O=(0,0)", "A=(2,0)", "B=(0,2)", "M=(0,3)", "P=(4,0)",
                "arc=Arc[A,B,O]", "sect=Sector[A,B,O]"])
check("修复用例构造", err is None, str(err))
if err is None:
    a_d = drawn(c, "arc")
    s_d = drawn(c, "sect")
    check("Arc 半径 = |CA|（此前为平均半径的错误值）", close(a_d["r"], 2, 1e-12) and close(s_d["r"], 2, 1e-12),
          "arc r=%s / sector r=%s" % (a_d["r"], s_d["r"]))
    check("弧端点角度与 A、B 一致（弧确实过两端点）",
          close(a_d["ang1"], 0, 1e-12) and close(a_d["ang2"], math.pi / 2, 1e-12),
          "%.9f → %.9f" % (a_d["ang1"], a_d["ang2"]))
    c.process("bad=Arc[O,P,M]")
    check("圆心不等距 → 明确报错（不再静默给错半径）",
          bool(el_of(c, "bad").error) and "等距" in el_of(c, "bad").error, str(el_of(c, "bad").error))
# 2) BarChart 三形态
c2, e2 = build(["L={1,2,2,3}", "b1=BarChart[L]", "b2=BarChart[{1,2,2,3}]", "b3=BarChart[1,2,2,3]"])
check("BarChart[列表元素] 可用（此前误判 '[' 而报错）",
      e2 is None and el_of(c2, "b1").kind == "barchart", str(e2))
check("BarChart[{内联列表}] 可用（GeoGebra 用 {} 而非 []）",
      el_of(c2, "b2") is not None and el_of(c2, "b2").kind == "barchart",
      el_of(c2, "b2").kind if el_of(c2, "b2") else None)
# 3) 颜色引号
c3, _ = build(["A=(1,1)"])
c3.process('SetColor[A,"#059669"]')
c3.process('SetColor[A,"red"]')
check("SetColor 接受带引号的颜色（此前报未知颜色）", el_of(c3, "A").color == "#e11d48",
      el_of(c3, "A").color)
# 4) FitExpr 报错文案
c4, _ = build([])
m4 = c4.process("bad=FitExpr[L,y~a*x+b]")
check("FitExpr 报错写明命令名与数据来源", "FitExpr" in m4 and "自由点" in m4, m4[:56])
# 5) 拟合函数可求值（GeoFunction.compute 丢失 xsym）
c5, e5 = build(["Pp={(1,2),(2,4),(3,6),(4,8)}", "fp=FitPoly[Pp,1]", "fe=FitExp[Pp]",
                "fl=FitLog[Pp]", "fw=FitPow[Pp]", "fs=FitSin[Pp]"])
check("拟合用例构造（回归）", e5 is None, str(e5))
if e5 is None:
    vals_ok = all(el_of(c5, k)._eval1(2) is not None for k in ("fp", "fe", "fl", "fw", "fs"))
    check("FitPoly/FitExp/FitLog/FitPow/FitSin 均可求值（此前 xsym=None → 全部不可求值）", vals_ok,
          str({k: el_of(c5, k)._eval1(2) for k in ("fp", "fe", "fl", "fw", "fs")}))

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("2D 内核检测矩阵：%d 项断言，%d 失败" % (PASS + FAIL, FAIL))
if FAILED:
    for nm in FAILED:
        print("  FAILED: " + nm)
    print("结果: FAILED")
    sys.exit(1)
print("结果: ALL PASS")
sys.exit(0)
