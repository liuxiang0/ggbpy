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
    check("MacroList 含新宏（宏表随构造/会话隔离）",
          "tri6" in _macro.registry(c), str(sorted(_macro.registry(c).keys())))
    msg3 = c.process("MacroDelete[tri6]")
    check("MacroDelete 成功", msg3.startswith("OK") and "tri6" not in _macro.registry(c), msg3[:40])

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

    c_other = Construction()
    check("宏表随构造隔离（另一个构造看不到）", "tri6" not in _macro.registry(c_other),
          str(sorted(_macro.registry(c_other).keys())))

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
section("M. 反演结果命名（点=大写，其它图形=inv 前缀）")
c_m, err_m = build(["O=(0,0)", "k=Circle[O,2]", "P=(3,0)", "c2=Circle[(5,0),1]",
                    "L=Line[(0,1),(1,1)]", "s=Segment[(3,0),(4,1)]",
                    "poly=Polygon[(0,0),(0.6,0),(0.6,0.6)]", "f(x)=x^2"])
check("反演命名用例构造", err_m is None, str(err_m))


def auto_create(cons, text):
    """执行一条无标签语句，返回新建标签列表。"""
    before = set(cons.order)
    cons.process(text)
    return [x for x in cons.order if x not in before]


if err_m is None:
    new_pt = auto_create(c_m, "Invert[P,k]")
    check("点反演仍用点命名（大写字母）",
          len(new_pt) == 1 and new_pt[0][0].isupper() and c_m.elements[new_pt[0]].kind == "point",
          str(new_pt))
    seq = []
    for txt, want_kind in (("Invert[c2,k]", "conic"), ("Invert[L,k]", "conic"),
                           ("Invert[s,k]", "parametric"), ("Invert[poly,k]", "polygon"),
                           ("Invert[f,k]", "implicit")):
        got = auto_create(c_m, txt)
        seq.append((txt, got, c_m.elements[got[0]].kind if got else None))
        check("%s → inv 前缀且类型正确" % txt.split("[")[0],
              len(got) == 1 and got[0].startswith("inv") and got[0][0].islower()
              and c_m.elements[got[0]].kind == want_kind,
              str(seq[-1]))
    check("反演像序号递增（inv1→inv5）",
          [g[0] for _, g, _ in seq] == ["inv%d" % i for i in range(1, 6)],
          str([g[0] for _, g, _ in seq]))
    check("反演点命名与反演像互不干扰（点仍是 A）", new_pt[0] == "A", str(new_pt))

    # 显式标签优先
    before = set(c_m.order)
    c_m.process("q=Invert[c2,k]")
    check("显式标签不被自动命名覆盖", "q" in c_m.order and c_m.elements["q"].kind == "conic", "")
    # 与已有标签冲突时跳过
    c_m2 = Construction()
    for t in ["O=(0,0)", "k=Circle[O,2]", "c2=Circle[(5,0),1]", "inv1=(9,9)"]:
        c_m2.process(t)
    used = auto_create(c_m2, "Invert[c2,k]")
    check("自动命名跳过已占用的 inv1（用 inv2）", used == ["inv2"], str(used))
    # 反演像可参与后续命令（嵌套/引用）
    c_m3 = Construction()
    for t in ["O=(0,0)", "k=Circle[O,2]", "c2=Circle[(5,0),1]", "L=Line[(-9,0),(9,0)]"]:
        c_m3.process(t)
    inv_lbl3 = auto_create(c_m3, "Invert[c2,k]")        # 自动命名 → inv1
    c_m3.process("D=Intersect[%s,L]" % inv_lbl3[0])     # 作为参数被引用
    check("反演像可被标签引用（Intersect[inv, 线]）",
          inv_lbl3[0].startswith("inv") and c_m3.elements["D"].kind == "point",
          "%s | %s" % (inv_lbl3, c_m3.order))
    c_m6 = Construction()
    for t in ["O=(0,0)", "k=Circle[O,2]", "c2=Circle[(5,0),1]", "L=Line[(-9,0),(9,0)]"]:
        c_m6.process(t)
    c_m6.process("D2=Intersect[Invert[c2,k],L]")       # 嵌套：匿名辅助，不注册 inv
    check("嵌套反演不注册多余标签（匿名辅助）",
          not [l for l in c_m6.order if l.startswith("inv")] and c_m6.elements["D2"].kind == "point",
          str(c_m6.order))
    # .ggk 往返保留 inv 名
    c_m4 = Construction()
    for t in ["O=(0,0)", "k=Circle[O,2]", "c2=Circle[(5,0),1]"]:
        c_m4.process(t)
    auto_create(c_m4, "Invert[c2,k]")
    data = c_m4.save_ggk((-10, 10, -10, 10))
    c_m5 = Construction()
    c_m5.load_json(data)
    check(".ggk 往返保留 inv 命名", "inv1" in c_m5.order and c_m5.elements["inv1"].kind == "conic",
          str(c_m5.order))

# ---------------------------------------------------------------------------
section("N. 统计图（柱/箱/饼/折线/散点/点图 + 整体移动）")
c_ch, err_ch = build(["D={3,1,4,1,5,9,2,6}", "bc=BarChart[D]", "hc=Histogram[D,4]", "bp=BoxPlot[D]",
                      "pi=PieChart[{3,5,2,4}]", "lc=LineChart[D]", "lc2=LineChart[{1,2,3},{4,5,7}]",
                      "sc=ScatterPlot[{(1,2),(2,4),(3,3)}]", "scn=ScatterPlot[{1,4,9}]",
                      "dp=DotPlot[{1,2,2,3,1}]"])
check("统计图用例构造", err_ch is None, str(err_ch))
if err_ch is None:
    d_bc, d_bp, d_pi = drawn(c_ch, "bc"), drawn(c_ch, "bp"), drawn(c_ch, "pi")
    d_lc, d_lc2, d_sc, d_scn, d_dp = (drawn(c_ch, "lc"), drawn(c_ch, "lc2"), drawn(c_ch, "sc"),
                                      drawn(c_ch, "scn"), drawn(c_ch, "dp"))
    check("BarChart 频数表非空", len(d_bc["bins"]) > 0 and sum(d_bc["counts"]) == 8,
          "%s/%s" % (d_bc["bins"], d_bc["counts"]))
    check("BoxPlot 五数有序（min≤Q1≤中位≤Q3≤max）",
          d_bp["five"] == sorted(d_bp["five"]) and d_bp["n"] == 8, str(d_bp["five"]))
    check("PieChart 总和 = 14 且扇形数与数据一致",
          close(d_pi["total"], 14, 1e-12) and len(d_pi["items"]) == 4, str(d_pi["total"]))
    check("LineChart 单序列 → x=1..8、y=数据",
          d_lc["xs"] == [1.0 * i for i in range(1, 9)] and d_lc["ys"] == [3, 1, 4, 1, 5, 9, 2, 6],
          str(d_lc["xs"])[:40])
    check("LineChart 双序列 → 用给定 x/y", d_lc2["xs"] == [1, 2, 3] and d_lc2["ys"] == [4, 5, 7], "")
    check("ScatterPlot 点列表 → 保持坐标", d_sc["pts"] == [[1, 2], [2, 4], [3, 3]], str(d_sc["pts"]))
    check("ScatterPlot 数值列表 → x 用序号", d_scn["pts"] == [[1, 1], [2, 4], [3, 9]], str(d_scn["pts"]))
    check("DotPlot 相同值向上叠点",
          d_dp["stacks"] == [[1.0, 0], [1.0, 1], [2.0, 0], [2.0, 1], [3.0, 0]], str(d_dp["stacks"]))
    # 命名前缀（避免落到默认字母池）
    names = {}
    for txt in ("BarChart[{1,2}]", "BoxPlot[{1,2}]", "PieChart[{1,2}]",
                "LineChart[{1,2}]", "ScatterPlot[{1,2}]", "DotPlot[{1,2}]"):
        before = set(c_ch.order)
        c_ch.process(txt)
        names[txt] = [x for x in c_ch.order if x not in before][0]
    check("统计图自动命名有可辨识前缀（bc/bp/pie/lc/sc/dp）",
          all(names[k].startswith(v) for k, v in
              (("BarChart[{1,2}]", "bc"), ("BoxPlot[{1,2}]", "bp"), ("PieChart[{1,2}]", "pie"),
               ("LineChart[{1,2}]", "lc"), ("ScatterPlot[{1,2}]", "sc"), ("DotPlot[{1,2}]", "dp"))),
          str(names))
    # 整体移动：offset
    check("统计图默认 offset = [0, 0]",
          d_bc["offset"] == [0, 0] and d_lc["offset"] == [0, 0] and d_pi["offset"] == [0, 0], "")
    c_ch.move("bc", 3.0, -2.0)
    check("move(图, x, y) → 设置整体偏移", c_ch.elements["bc"].offset == [3.0, -2.0],
          str(c_ch.elements["bc"].offset))
    check("绘制状态带出 offset（前端据此整体平移）",
          drawn(c_ch, "bc")["offset"] == [3.0, -2.0], str(drawn(c_ch, "bc")["offset"]))
    c_ch.shift("bc", 1.0, 1.0)
    check("shift(图, dx, dy) → 偏移累加", c_ch.elements["bc"].offset == [4.0, -1.0],
          str(c_ch.elements["bc"].offset))
    try:
        c_ch.move("P_missing", 0, 0)
        check("未知标签 move 报错", False, "未报错")
    except Exception:
        check("未知标签 move 报错", True, "")
    try:
        c_ch.move("pi", float("nan"), 0)
        check("统计图 move 接受任意数值（不做几何校验）", True, "")
    except Exception as e:
        check("统计图 move 接受任意数值（不做几何校验）", False, str(e))
    c_ch.elements["bc"].locked = True
    try:
        c_ch.move("bc", 0, 0)
        check("锁定统计图不可移动", False, "未报错")
    except Exception:
        check("锁定统计图不可移动", True, "")
    c_ch.elements["bc"].locked = False
    # 派生对象（非统计图）仍不可直接移动
    c_ch.process("Q=(0,0)"); c_ch.process("R=(2,0)"); c_ch.process("sg=Segment[Q,R]")
    try:
        c_ch.move("sg", 0, 0)
        check("派生对象（线段）仍不可直接移动", False, "未报错")
    except Exception:
        check("派生对象（线段）仍不可直接移动", True, "")
    # .ggk 往返保留 offset
    ggk = c_ch.save_ggk((-10, 10, -10, 10))
    c_ch2 = Construction()
    c_ch2.load_json(ggk)
    check(".ggk 往返保留统计图 offset", c_ch2.elements["bc"].offset == [4.0, -1.0],
          str(c_ch2.elements.get("bc").offset))
    # LineChart 长度不一致 → 明确报错（process 把 GeoError 转成 "错误: …" 消息）
    msg_bad = c_ch.process("bad=LineChart[{1,2,3},{1,2}]")
    check("LineChart 长度不一致报错", msg_bad.startswith("错误") and "长度" in msg_bad, msg_bad[:40])

section("O. 三维统计图（柱/散点/高度场 → 网格对象）")
c_3d, err_3d = build(["b3=BarChart3D[{1,3,2}]", "PTS={(1,1,1),(2,2,3),(3,1,2)}",
                      "s3=ScatterPlot3D[PTS]", "f3=SurfaceChart3D[{1,2,3,2,3,4,3,4,5},3]"])
check("三维统计图用例构造", err_3d is None, str(err_3d))
if err_3d is None:
    def mesh_of(lab):
        d = drawn(c_3d, lab)
        data = d.get("data") or {}
        return d, data.get("verts", []), data.get("faces", []), data.get("edges", [])

    d, V, F, E = mesh_of("b3")
    check("BarChart3D：3 根柱 = 24 顶点/18 面（每柱 8/6）",
          d["objtype"] == "polyhedron" and len(V) == 24 and len(F) == 18, "%d/%d" % (len(V), len(F)))
    check("BarChart3D：欧拉特征 = 2×柱数", len(V) - len(E) + len(F) == 6, "%d" % (len(V) - len(E) + len(F)))
    d, V, F, E = mesh_of("s3")
    check("ScatterPlot3D：3 个标记 = 18 顶点/24 面（正八面体）",
          len(V) == 18 and len(F) == 24 and len(V) - len(E) + len(F) == 6, "%d/%d" % (len(V), len(F)))
    d, V, F, E = mesh_of("f3")
    check("SurfaceChart3D：3×3 高度场 = 9 顶点/4 面（欧拉 = 1）",
          len(V) == 9 and len(F) == 4 and len(V) - len(E) + len(F) == 1, "%d/%d/%d" % (len(V), len(F), len(V) - len(E) + len(F)))

    # 外向面序：每条柱（8 顶点一组）的面法向应背离该柱中心
    def component_outward(V, F, size):
        import math as _m
        for gi in range(0, len(V), size):
            grp = V[gi:gi + size]
            cx = sum(p[0] for p in grp) / len(grp)
            cy = sum(p[1] for p in grp) / len(grp)
            cz = sum(p[2] for p in grp) / len(grp)
            for f in F:
                if not (gi <= f[0] < gi + size):
                    continue
                pts = [V[i] for i in f]
                fx = sum(p[0] for p in pts) / len(pts)
                fy = sum(p[1] for p in pts) / len(pts)
                fz = sum(p[2] for p in pts) / len(pts)
                nx = ny = nz = 0.0
                for i in range(len(pts)):
                    ax, ay, az = pts[i]
                    bx, by, bz = pts[(i + 1) % len(pts)]
                    nx += (ay - by) * (az + bz)
                    ny += (az - bz) * (ax + bx)
                    nz += (ax - bx) * (ay + by)
                if nx * (fx - cx) + ny * (fy - cy) + nz * (fz - cz) < 0:
                    return False
        return True

    d, V, F, E = mesh_of("b3")
    check("BarChart3D 面序外向（非凸网格不用质心归一化）", component_outward(V, F, 8), "")
    d, V, F, E = mesh_of("s3")
    check("ScatterPlot3D 面序外向", component_outward(V, F, 6), "")
    # 命名前缀与 state3d 类型
    names3 = {}
    before = set(c_3d.order)
    for txt in ("BarChart3D[{1,2}]", "ScatterPlot3D[{(1,2,3)}]", "SurfaceChart3D[{1,2,3,4},2]"):
        before = set(c_3d.order)
        c_3d.process(txt)
        names3[txt] = [x for x in c_3d.order if x not in before][0]
    check("三维统计图命名前缀 bc3_/sc3_/sf3_",
          names3["BarChart3D[{1,2}]"].startswith("bc3_")
          and names3["ScatterPlot3D[{(1,2,3)}]"].startswith("sc3_")
          and names3["SurfaceChart3D[{1,2,3,4},2]"].startswith("sf3_"), str(names3))
    msg_bad3 = c_3d.process("bad3=SurfaceChart3D[{1,2,3,4},1]")
    check("SurfaceChart3D 列数不足报错", msg_bad3.startswith("错误") and "列" in msg_bad3, msg_bad3[:40])

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
section("Z. 计算记忆 LRU 与撤销成本模型（REVIEW P0-3）")

import kernel.memo as _memo  # noqa: E402
from kernel.construction import UNDO_LIMIT as _UNDO_LIMIT  # noqa: E402

_old_max = _memo._MAX_ENTRIES
try:
    _memo.clear()
    _memo._MAX_ENTRIES = 2
    _memo.put(("t", 1), {"v": 1})
    _memo.put(("t", 2), {"v": 2})
    _memo.get(("t", 1))                 # 触碰最久未用 → 应在淘汰中存活
    _memo.put(("t", 3), {"v": 3})       # 超上限 → 淘汰最久未用（应为 t2）
    _kept = (_memo.get(("t", 1)) is not None, _memo.get(("t", 2)) is not None)
    check("记忆按 LRU 淘汰（最近使用的条目不被淘汰）", _kept[0] and not _kept[1], str(_kept))
finally:
    _memo._MAX_ENTRIES = _old_max
    _memo.clear()
check("记忆统计含 hits/misses/entries/coords", set(_memo.stats()) >= {"entries", "coords", "hits", "misses"},
      str(sorted(_memo.stats())))
check("撤销栈上限常量存在且被引用", _UNDO_LIMIT == 200 and hasattr(Construction, "snapshot"), str(_UNDO_LIMIT))

# ---------------------------------------------------------------------------
section("Z2. CAS 算子接线命令（REVIEW §6 #1：Solve/NSolve/Limit/PartialFractions/Substitute/SolveODE/IsFinite）")

_c = Construction()
_c.process("S1=Solve[x^2-4=0, x]")
_e = _c.elements.get("S1")
check("Solve[x^2=4] → 数值解列表 {-2, 2}",
      _e is not None and _e.kind == "list" and len(_e.items) == 2
      and abs(_e.items[0] + 2) < 1e-9 and abs(_e.items[1] - 2) < 1e-9,
      str(getattr(_e, "items", None)))

_c.process("S2=求解方程[x^2=9, x]")           # 中文别名
_e = _c.elements.get("S2")
check("中文别名「求解方程」可用（Solve 别名注册生效）",
      _e is not None and _e.kind == "list" and abs(_e.items[0] + 3) < 1e-9, str(getattr(_e, "items", None)))

_c.process("S3=Solve[exp(x)=0, x]")           # 无解 → 空列表
_e = _c.elements.get("S3")
check("Solve 无解 → 空列表", _e is not None and _e.kind == "list" and _e.items == [], str(getattr(_e, "items", None)))

_c.process("S4=Solve[x^2+1=0, x]")            # 复数解 → 文本（不硬塞数值）
_e = _c.elements.get("S4")
check("Solve 复数解 → 文本（明确不返回假数值）",
      _e is not None and _e.kind == "result" and "I" in (_e.text or ""), str(getattr(_e, "text", None))[:30])

_c.process("N1=NSolve[cos(x)=x, x]")
_e = _c.elements.get("N1")
check("NSolve[cos(x)=x] → 实根 ≈ 0.739085（数值扫描兜底）",
      _e is not None and _e.kind == "list" and len(_e.items) == 1 and abs(_e.items[0] - 0.7390851332151607) < 1e-6,
      str(getattr(_e, "items", None)))

_msg = _c.process("N2=NSolve[exp(x)+1=0, x]")
check("NSolve 无实根 → 明确报错且不创建元素",
      _c.elements.get("N2") is None and _msg.startswith("错误"), (_msg or "")[:40])

_c.process("L1=Limit[sin(x)/x, 0]")
_e = _c.elements.get("L1")
check("Limit[sin(x)/x, 0] → 1", _e is not None and _e.kind == "number" and abs(_e.value - 1.0) < 1e-9,
      str(getattr(_e, "value", None)))

_msg = _c.process("L2=Limit[1/x, 0]")
check("Limit 为无穷 → 明确报错（不返回假数值）",
      _c.elements.get("L2") is None and "无穷" in (_msg or ""), (_msg or "")[:40])

_c.process("L3=极限[sin(x)/x, 0]")            # 中文别名
_e = _c.elements.get("L3")
check("中文别名「极限」可用", _e is not None and abs(_e.value - 1.0) < 1e-9, str(getattr(_e, "value", None)))

_c.process("P1=PartialFractions[(x^2+1)/(x-1), x]")
_e = _c.elements.get("P1")
check("PartialFractions → 函数且含 2/(x - 1) 项",
      _e is not None and _e.kind == "function" and "2" in str(_e.expr) and "/" in str(_e.expr),
      str(getattr(_e, "expr", None))[:40])

_c.process("B1=Substitute[x^2, x, 3]")
_e = _c.elements.get("B1")
check("Substitute[x^2, x, 3] → 9（无自由变量 → 数值）",
      _e is not None and _e.kind == "number" and abs(_e.value - 9.0) < 1e-9, str(getattr(_e, "value", None)))

_c.process("OD1=SolveODE[y'=y]")
_e = _c.elements.get("OD1")
check("SolveODE[y'=y] → 通解文本（含 exp）",
      _e is not None and _e.kind == "result" and "exp" in (_e.text or ""), str(getattr(_e, "text", None))[:40])

_c.process("F1=IsFinite[1/0]")
_c.process("F2=IsFinite[3]")
_c.process("F3=IsFinite[∞]")
_f1, _f2, _f3 = (_c.elements.get(k) for k in ("F1", "F2", "F3"))
check("IsFinite：1/0=False、3=True、∞=False",
      _f1 is not None and _f1.value is False and _f2 is not None and _f2.value is True
      and _f3 is not None and _f3.value is False,
      "%s/%s/%s" % (getattr(_f1, "value", None), getattr(_f2, "value", None), getattr(_f3, "value", None)))

# 依赖重算（DAG 正确性）：引用元素变化时，新命令必须刷新
_c.process("n=4")
_c.process("FD=IsFinite[1/n]")
_c.process("SD=Substitute[x^2, x, n]")
_c.process("KD=Limit[sin(n*x)/x, 0]")
_c.process("QD=Solve[x^2=n^2, x]")
_before = (_c.elements["FD"].value, _c.elements["SD"].value, _c.elements["KD"].value, list(_c.elements["QD"].items))
_c.process("SetValue[n, 0]")
_after = (_c.elements["FD"].value, _c.elements["SD"].value, _c.elements["KD"].value, list(_c.elements["QD"].items))
check("新命令随依赖重算（SetValue[n,0]：IsFinite→False / Substitute→0 / Limit→0 / Solve→[0]）",
      _before == (True, 16.0, 4.0, [-4.0, 4.0]) and _after == (False, 0.0, 0.0, [0.0]),
      "before=%s after=%s" % (_before, _after))

# ---------------------------------------------------------------------------
section("Z3. 二维剖分（Delaunay 三角剖分 / Voronoi 泰森多边形）")


def _poly_area(pp):
    acc = 0.0
    for k in range(len(pp)):
        k2 = (k + 1) % len(pp)
        acc += pp[k][0] * pp[k2][1] - pp[k2][0] * pp[k][1]
    return abs(acc) / 2.0


_t = Construction()
_t.process("Pts={(0,0),(4,0),(4,4),(0,4),(2,2)}")
_t.process("DT=Delaunay[Pts]")
_dt = _t.elements.get("DT")
check("Delaunay[内联点列表] → 4 个三角形，且总面积等于正方形面积",
      _dt is not None and _dt.kind == "list" and _dt.itemkind == "polygon" and len(_dt.items) == 4
      and all(len(pp) == 3 for pp in _dt.items) and abs(sum(_poly_area(pp) for pp in _dt.items) - 16.0) < 1e-6,
      "n=%s area=%.6f" % (len(_dt.items) if _dt else None,
                          sum(_poly_area(pp) for pp in _dt.items) if _dt else -1))

_t.process("VT=Voronoi[Pts]")
_vt = _t.elements.get("VT")
check("Voronoi[内联点列表] → 5 个元胞，且面积和等于外扩包围盒面积（元胞有界）",
      _vt is not None and len(_vt.items) == 5
      and abs(sum(_poly_area(pp) for pp in _vt.items) - 5.2 * 5.2) < 1e-6,
      "n=%s area=%.4f" % (len(_vt.items) if _vt else None,
                          sum(_poly_area(pp) for pp in _vt.items) if _vt else -1))

_t.process("DT2=三角剖分[Pts]")
check("中文别名「三角剖分」可用", _t.elements.get("DT2") is not None and len(_t.elements["DT2"].items) == 4, "")
_t.process("VT2=泰森多边形[Pts]")
check("中文别名「泰森多边形」可用", _t.elements.get("VT2") is not None and len(_t.elements["VT2"].items) == 5, "")

# 动态形态：变参点元素 + 拖动重算
_t2 = Construction()
for _i, (_x, _y) in enumerate(((0, 0), (4, 0), (4, 4), (0, 4))):
    _t2.process("Q%d=(%d,%d)" % (_i, _x, _y))
_t2.process("D2=Delaunay[Q0,Q1,Q2,Q3]")
_before = [list(map(list, pp)) for pp in _t2.elements["D2"].items]
_t2.process("SetCoords[Q2, 6, 4]")
_after = [list(map(list, pp)) for pp in _t2.elements["D2"].items]
check("Delaunay[变参点] 随 SetCoords 重算（三角形集合改变）", _before != _after,
      "before=%s after=%s" % (_before[:1], _after[:1]))

# 多边形入参（动态）
_t3 = Construction()
_t3.process("A3b=(0,0)")
_t3.process("B3b=(4,0)")
_t3.process("C3b=(4,4)")
_t3.process("D3b=(0,4)")
_t3.process("Poly=P1olygon[A3b,B3b,C3b,D3b]") if False else _t3.process("Poly=Polygon[A3b,B3b,C3b,D3b]")
_t3.process("DP=Delaunay[Poly]")
_t3.process("VP=Voronoi[Poly]")
check("接受多边形入参（Delaunay 2 三角形 / Voronoi 4 元胞）",
      _t3.elements.get("DP") is not None and len(_t3.elements["DP"].items) == 2
      and _t3.elements.get("VP") is not None and len(_t3.elements["VP"].items) == 4,
      "dt=%s vt=%s" % (len(_t3.elements["DP"].items) if _t3.elements.get("DP") else None,
                       len(_t3.elements["VP"].items) if _t3.elements.get("VP") else None))

# 退化与边界
_t4 = Construction()
_t4.process("Col={(0,0),(1,1),(2,2)}")
_t4.process("DC=Delaunay[Col]")
check("共线点 → 元素带明确 error（不给出错误图形）",
      (_t4.elements.get("DC") is not None) and "退化" in (getattr(_t4.elements["DC"], "error", "") or ""),
      str(getattr(_t4.elements.get("DC"), "error", None))[:36])

_t4.process("Dup={(0,0),(0,0),(1,1)}")
_t4.process("VD=Voronoi[Dup]")
check("Voronoi 重复点 → 元素带明确 error",
      (_t4.elements.get("VD") is not None) and "重合" in (getattr(_t4.elements["VD"], "error", "") or ""),
      str(getattr(_t4.elements.get("VD"), "error", None))[:30])

_msg_t = _t4.process("DT9=Delaunay[(0,0),(1,1)]")
check("Delaunay 点数不足 → 命令报错（不创建元素）",
      _t4.elements.get("DT9") is None and "至少" in (_msg_t or ""), (_msg_t or "")[:30])

# ---------------------------------------------------------------------------
section("Z4. 茎叶图 StemPlot")

_sp = Construction()
_sp.process("SP=StemPlot[{12,15,23,11,31,45,45}]")
_el = _sp.elements.get("SP")
check("StemPlot 十位为茎、个位为叶（12,15,23,11,31,45,45）",
      _el is not None and _el.kind == "stemplot" and _el.stems == [1, 2, 3, 4]
      and _el.leaves == [[1, 2, 5], [3], [1], [5, 5]],
      "%s / %s" % (getattr(_el, "stems", None), getattr(_el, "leaves", None)))

_sp.process("SP2=茎叶图[{1,2,21}]")
check("中文别名「茎叶图」可用",
      _sp.elements.get("SP2") is not None and _sp.elements["SP2"].stems == [0, 2], "")

_sp.process("L={5,7,25}")
_sp.process("SP3=StemPlot[L]")
check("接受列表元素入参（5,7,25 → 茎 0/2）",
      _sp.elements.get("SP3").stems == [0, 2] and _sp.elements["SP3"].leaves == [[5, 7], [5]], "")

_msg_neg = _sp.process("SP4=StemPlot[{-1,2}]")
check("负数数据 → 元素带明确 error（不画出错误图形）",
      _sp.elements.get("SP4") is not None and "非负" in (_sp.elements["SP4"].error or ""),
      str(getattr(_sp.elements.get("SP4"), "error", None))[:36])

_msg_empty = _sp.process("SP5=StemPlot[{}]")
check("空数据 → 命令报错（不创建元素）",
      _sp.elements.get("SP5") is None and "数值数据" in (_msg_empty or ""), (_msg_empty or "")[:36])

# 依赖重算：列表被 Redefine 后茎叶图同步刷新
_before = (_sp.elements["SP3"].stems, _sp.elements["SP3"].leaves)
_sp.process("Redefine[L, L={9,19,29}]")
_after = (_sp.elements["SP3"].stems, _sp.elements["SP3"].leaves)
check("列表被重定义后茎叶图自动重算（依赖接线正确）",
      _before == ([0, 2], [[5, 7], [5]]) and _after == ([0, 1, 2], [[9], [9], [9]]),
      "%s → %s" % (_before, _after))

# ---------------------------------------------------------------------------
section("Z5. 列表字面量依赖化（含变量的 L={…} 随依赖重算）")

_lc = Construction()
_lc.process("n=1")
_lc.process("L={n, n*10+2, n*10+5}")
_lle = _lc.elements.get("L")
check("含变量的列表字面量挂上依赖（free=False, deps=[n]）",
      _lle is not None and _lle.free is False and [d.label for d in _lle.deps] == ["n"],
      "free=%s deps=%s" % (getattr(_lle, "free", None), [d.label for d in getattr(_lle, "deps", [])]))

_lc.process("SL=Sum[L]")
_lc.process("SPL=StemPlot[L]")
_before_l = (list(_lc.elements["L"].items), _lc.elements["SL"].value,
             list(_lc.elements["SPL"].stems), [list(x) for x in _lc.elements["SPL"].leaves])
_lc.process("SetValue[n, 3]")
_after_l = (list(_lc.elements["L"].items), _lc.elements["SL"].value,
            list(_lc.elements["SPL"].stems), [list(x) for x in _lc.elements["SPL"].leaves])
check("列表随依赖重算（n=1→3：L=[3,32,35]，Sum=70）",
      _after_l[0] == [3.0, 32.0, 35.0] and abs(_after_l[1] - 70.0) < 1e-9,
      "L=%s Sum=%s" % (_after_l[0], _after_l[1]))
check("经列表的 DAG 链贯通（Sum 与 StemPlot 同步刷新）",
      _before_l != _after_l and _after_l[2] == [0, 3] and _after_l[3] == [[3], [2, 5]],
      "%s → %s" % (_before_l, _after_l))

_lc.process("D2={3,1,4}")
check("纯常量列表保持静态快照（free=True，无依赖）—— 行为不变",
      _lc.elements["D2"].free is True and not _lc.elements["D2"].deps,
      "free=%s deps=%s" % (_lc.elements["D2"].free, len(_lc.elements["D2"].deps)))

_lc.process("n2=2")
_lc.process("P2={n2, n2*n2}")
_lc.process("SetValue[n2, 4]")
check("表达式项也随依赖重算（n2=2→4：P2=[4,16]）",
      list(_lc.elements["P2"].items) == [4.0, 16.0], str(_lc.elements["P2"].items))

# ---------------------------------------------------------------------------
section("Z6. 列表字面量接受点标签（{A,B} / {A,B,M}）")

_pl = Construction()
_pl.process("A=(1,1)")
_pl.process("B=(3,1)")
_pl.process("M=Midpoint[A,B]")
_pl.process("LP={A,B,M}")
_ple = _pl.elements.get("LP")
check("点标签列表 {A,B,M} → itemkind=point、坐标正确、依赖为三点",
      _ple is not None and _ple.itemkind == "point"
      and [list(x) for x in _ple.items] == [[1.0, 1.0], [3.0, 1.0], [2.0, 1.0]]
      and sorted(d.label for d in _ple.deps) == ["A", "B", "M"],
      "%s / %s / %s" % (getattr(_ple, "itemkind", None),
                        [list(x) for x in getattr(_ple, "items", [])],
                        sorted(d.label for d in getattr(_ple, "deps", []))))

_pl.process("SetCoords[A, 5, 5]")
_after = [list(x) for x in _pl.elements["LP"].items]
check("移动点后点标签列表自动重算（含派生中点 M）",
      _after == [[5.0, 5.0], [3.0, 1.0], [4.0, 3.0]], str(_after))

_msg_mix = _pl.process("LM={A,(9,9)}")
check("点标签与坐标混用 → 明确报错（不创建元素）",
      _pl.elements.get("LM") is None and "要么全是点标签" in (_msg_mix or ""), (_msg_mix or "")[:40])

_msg_par = _pl.process("LQ={(A),(B)}")
check("给点加括号 → 报错并提示改用 {A,B} 形式",
      _pl.elements.get("LQ") is None and "不要加括号" in (_msg_par or ""), (_msg_par or "")[:60])

_pl.process("LC={(1,2),(3,4)}")
check("坐标元组列表不受影响（回归）",
      [list(x) for x in _pl.elements["LC"].items] == [[1.0, 2.0], [3.0, 4.0]]
      and _pl.elements["LC"].itemkind == "point", "")

# ---------------------------------------------------------------------------
section("Z7. 剖分信息（面积/质心/摘要）与内联列表动态性（含 memo 修复）")

_gi = Construction()
for _lab, _xy in (("A", (0, 0)), ("B", (4, 0)), ("C", (4, 4)), ("D", (0, 4)), ("M", (2, 2))):
    _gi.process("%s=(%d,%d)" % (_lab, _xy[0], _xy[1]))
_gi.process("VV=Voronoi[{A,B,C,D,M}]")
_gi.process("TT=Delaunay[{A,B,C,D,M}]")
_vd = _gi.elements["VV"].draw((0, 0, 1, 1))
_td = _gi.elements["TT"].draw((0, 0, 1, 1))
check("Voronoi 序列化含每个元胞的面积与质心（5 个）",
      len(_vd.get("areas", [])) == 5 and len(_vd.get("centroids", [])) == 5
      and abs(sum(_vd["areas"]) - 5.2 * 5.2) < 1e-6,
      "areas=%s" % [round(v, 3) for v in _vd.get("areas", [])])
check("Voronoi 摘要含数量/顶点范围/总面积",
      "5 个多边形" in _vd.get("value", "") and "总面积 27.04" in _vd.get("value", ""), _vd.get("value"))
check("Delaunay 摘要为 4 个三角形、总面积 16",
      "4 个多边形（3 顶点）" in _td.get("value", "") and "总面积 16" in _td.get("value", ""), _td.get("value"))

# 内联点标签列表 → 依赖变化时下游命令必须重算（曾因 memo 对不可见列表签名退化而失效）
_in = Construction()
_in.process("P=(0,0)")
_in.process("Q=(2,0)")
_in.process("R=(1,2)")
_in.process("VI=Voronoi[{P,Q,R}]")
_first = [list(map(float, poly)) for poly in _in.elements["VI"].items[0]]
_in.process("SetCoords[P, -2, -1]")
_second = [list(map(float, poly)) for poly in _in.elements["VI"].items[0]]
check("内联点标签列表驱动 Voronoi 重算（memo 修复后随点移动刷新）",
      _first != _second and abs(float(_second[0][0]) + 2.6) < 1e-6,
      "%s → %s" % ([round(v, 2) for v in _first[0]], [round(v, 2) for v in _second[0]]))

_in2 = Construction()
_in2.process("k=2")
_in2.process("SI=Sum[{k, k*10}]")
_before_sum = _in2.elements["SI"].value
_in2.process("SetValue[k, 5]")
check("内联数值列表驱动 Sum 重算（2+20=22 → 5+50=55）",
      abs(_before_sum - 22.0) < 1e-9 and abs(_in2.elements["SI"].value - 55.0) < 1e-9,
      "%s → %s" % (_before_sum, _in2.elements["SI"].value))

# ---------------------------------------------------------------------------
section("Z8. 角度为有向 0..360°（钝角/优角/平角都正确，弧的圆心角 0..2π）")


def _sweep_mod2pi(el):
    sw = el.ang2 - el.ang1
    while sw < 0:
        sw += 2 * math.pi
    while sw >= 2 * math.pi:
        sw -= 2 * math.pi
    return sw


_ag = Construction()
_ag.process("A8a=(2,0)")
_ag.process("B8a=(1,0)")
_ag.process("C8a=(0,1)")          # BA=(1,0) → BC=(-1,1)：逆时针 135°
_ag.process("C8b=(0,-1)")         # BD=(-1,-1)：逆时针 225°（优角，旧实现会折成 135°）
_ag.process("E8=(-2,0)")          # 平角
_ag.process("G1=Angle[A8a,B8a,C8a]")
_ag.process("G2=Angle[A8a,B8a,C8b]")
_ag.process("G3=Angle[A8a,B8a,E8]")
_ag.process("G4=Angle[A8a,B8a,A8a]")
_e1, _e2, _e3, _e4 = (_ag.elements[k] for k in ("G1", "G2", "G3", "G4"))
check("Angle 有向 0..360°：135°（逆时针侧）/ 225°（优角）/ 180°（平角）/ 0°（同向）",
      abs(_e1.value - 135) < 1e-9 and abs(_e2.value - 225) < 1e-9
      and abs(_e3.value - 180) < 1e-9 and abs(_e4.value - 0) < 1e-9,
      "%.1f / %.1f / %.1f / %.1f" % (_e1.value, _e2.value, _e3.value, _e4.value))
check("优角可超过 180°（不再限制在 0..180）", _e2.value > 180 and _e2.rad > math.pi,
      "%.1f° rad=%.4f" % (_e2.value, _e2.rad))
check("弧的圆心角契约：rad == (ang2-ang1) mod 2π（四条用例一致）",
      all(abs(_sweep_mod2pi(e) - e.rad) < 1e-9 for e in (_e1, _e2, _e3, _e4)),
      "%.4f/%.4f/%.4f/%.4f" % tuple(_sweep_mod2pi(e) for e in (_e1, _e2, _e3, _e4)))
_ag.process("V8=Angle[(1,0),(-1,-1)]")
check("二向量形式同为有向：Angle[(1,0),(-1,-1)] = 225°", abs(_ag.elements["V8"].value - 225) < 1e-9,
      "%.1f°" % _ag.elements["V8"].value)

# ---------------------------------------------------------------------------
section("Z9. 交互控件（Button / CheckBox / InputBox）")

_wg = Construction()
_wg.process("c9=Circle[(0,0),2]")
_wg.process("n9=3")
_wg.process('b9=Button["点我", "A9=(2,2)", (3,4)]')
_wg.process('cb9=CheckBox["显示圆", c9, (-3,1)]')
_wg.process("ib9=InputBox[n9, (2,-2)]")
_b, _cb, _ib = _wg.elements["b9"], _wg.elements["cb9"], _wg.elements["ib9"]
check("Button：caption/script/位置正确", _b.kind == "button" and _b.caption == "点我"
      and _b.script == "A9=(2,2)" and abs(_b.x - 3) < 1e-9 and abs(_b.y - 4) < 1e-9,
      "%s %r %r (%.1f,%.1f)" % (_b.kind, _b.caption, _b.script, _b.x, _b.y))
check("CheckBox：绑定目标对象", _cb.kind == "checkbox" and _cb.target == "c9" and _cb.caption == "显示圆",
      "%s → %s" % (_cb.kind, _cb.target))
check("InputBox：绑定目标对象", _ib.kind == "inputbox" and _ib.target == "n9", "%s → %s" % (_ib.kind, _ib.target))
check("控件序列化含 caption/target/坐标（供前端派生实时态）",
      all(k in _b.draw((0, 0, 1, 1)) for k in ("caption", "target", "x", "y"))
      and "script" in _b.draw((0, 0, 1, 1)), "")
_msg_b = _wg.process('bx=Button["只有说明"]')
_msg_c = _wg.process('cbx=CheckBox["说明", 不存在]')
check("控件参数缺失/目标不存在 → 明确报错",
      _wg.elements.get("bx") is None and "命令脚本" in (_msg_b or "")
      and _wg.elements.get("cbx") is None and "找不到对象" in (_msg_c or ""),
      "%s | %s" % ((_msg_b or "")[:22], (_msg_c or "")[:22]))

# ---------------------------------------------------------------------------
section("Z10. 画布滑块（Slider 位置 + 线段几何）")

_sl = Construction()
_sl.process("sA=Slider[0,10,1,(-2,2)]")
_sl.process("sB=Slider[0,5,(1,1)]")
_sl.process("sC=Slider[-1,1]")
_a, _b2, _c = _sl.elements["sA"], _sl.elements["sB"], _sl.elements["sC"]
check("Slider 支持 (x,y) 位置并序列化 slider_x/y/len",
      abs(_a.slider_x + 2) < 1e-9 and abs(_a.slider_y - 2) < 1e-9 and abs(_a.slider_len - 3) < 1e-9
      and all(k in _a.draw((0, 0, 1, 1)) for k in ("slider_x", "slider_y", "slider_len", "min", "max", "step")),
      "pos=(%s,%s) len=%s" % (_a.slider_x, _a.slider_y, _a.slider_len))
check("省略步长时仍可带位置（Slider[0,5,(1,1)]）",
      abs(_b2.slider_x - 1) < 1e-9 and abs(_b2.slider_y - 1) < 1e-9 and _b2.step and _b2.step > 0,
      "pos=(%s,%s) step=%s" % (_b2.slider_x, _b2.slider_y, _b2.step))
check("缺省位置自动排布（左上起逐行下移，互不重叠）",
      _c.slider_x is not None and _c.slider_y is not None and _c.slider_y < _b2.slider_y,
      "(%s,%s)" % (_c.slider_x, _c.slider_y))

# ---------------------------------------------------------------------------
import json as _json_mod  # noqa: E402  （Z11 段用）
section("Z11. 滑块定义保持与 .ggk v5 数值持久化")

_pv = Construction()
_pv.process("sP=Slider[0,10,1,(-5,3)]")
_pv.process("nP=3")
_pv.process("gP(x)=sP*x")
_pv.move("sP", 6.0, 0.0)
_pv.process("SetValue[nP, 5]")
check("拖动滑块不改写 defn（仍是 Slider[…]）且几何/范围保留",
      _pv.elements["sP"].defn.startswith("sP=Slider[") and _pv.elements["sP"].min == 0
      and _pv.elements["sP"].max == 10 and abs(_pv.elements["sP"].slider_x + 5) < 1e-9,
      "%r min=%s" % (_pv.elements["sP"].defn, _pv.elements["sP"].min))
check("普通自由数值仍按值写入 defn（旧行为不变）", _pv.elements["nP"].defn == "nP=5", _pv.elements["nP"].defn)
check("函数引用滑块会联动（g(x)=sP*x → 6x）", "6" in str(_pv.elements["gP"].expr), str(_pv.elements["gP"].expr)[:20])

_pv.process("SetValue[sP, 8]")
_data = _json_mod.loads(_pv.save_json())
check(".ggk v5：values 保存自由数值当前值",
      _data.get("version") == 5 and abs(_data.get("values", {}).get("sP", -1) - 8) < 1e-9
      and abs(_data.get("values", {}).get("nP", -1) - 5) < 1e-9, str(_data.get("values")))
_pv2 = Construction()
_pv2.load_json(_json_mod.dumps(_data))
check(".ggk 往返：滑块仍是滑块且当前值保留（不再回到最小值）",
      _pv2.elements["sP"].value == 8 and _pv2.elements["sP"].defn.startswith("sP=Slider[")
      and _pv2.elements["sP"].min == 0 and _pv2.elements["nP"].value == 5,
      "sP=%.1f defn=%r nP=%.1f" % (_pv2.elements["sP"].value, _pv2.elements["sP"].defn, _pv2.elements["nP"].value))
_old = dict(_data); _old.pop("values"); _old["version"] = 4
_pv3 = Construction()
_pv3.load_json(_json_mod.dumps(_old))
check("旧 v4 文件（无 values）仍可载入（用 defn 初值）",
      _pv3.elements["sP"].value == 0 and _pv3.elements["sP"].min == 0, "%.1f" % _pv3.elements["sP"].value)

# ---------------------------------------------------------------------------
section("Z12. 控件/滑块锚点移动（SetWidgetPos）")

_sw = Construction()
_sw.process('bW=Button["点我", "BW=(1,1)", (0,0)]')
_sw.process("cW=Circle[(0,0),1]")
_sw.process('cbW=CheckBox["显示c", cW, (0,0)]')
_sw.process("nW=3")
_sw.process("ibW=InputBox[nW, (0,0)]")
_sw.process("slW=Slider[0,10,1,(0,0)]")
_sw.process("SetValue[slW, 7]")
for _ln in ("SetWidgetPos[bW,(2,3)]", "SetWidgetPos[cbW,(-2,1)]", "SetWidgetPos[ibW,(1,-1)]", "SetWidgetPos[slW,(4,-2)]"):
    _sw.process(_ln)
check("SetWidgetPos 更新按钮/复选框/输入框锚点并重写 defn",
      abs(_sw.elements["bW"].x - 2) < 1e-9 and "Button[" in _sw.elements["bW"].defn and "(2,3)" in _sw.elements["bW"].defn
      and abs(_sw.elements["cbW"].x + 2) < 1e-9 and "( -2,1)".replace(" ", "") in _sw.elements["cbW"].defn
      and abs(_sw.elements["ibW"].y + 1) < 1e-9 and "InputBox[" in _sw.elements["ibW"].defn,
      "%r" % _sw.elements["bW"].defn)
check("SetWidgetPos 移动滑块并保留其数值（值不回到 min）",
      abs(_sw.elements["slW"].slider_x - 4) < 1e-9 and abs(_sw.elements["slW"].slider_y + 2) < 1e-9
      and abs(_sw.elements["slW"].value - 7) < 1e-9 and "Slider[" in _sw.elements["slW"].defn,
      "%r 值=%.1f" % (_sw.elements["slW"].defn, _sw.elements["slW"].value))
_msg_sw = _sw.process("SetWidgetPos[nW,(1,1)]")
check("对普通数值调用 SetWidgetPos → 明确报错", "滑动条" in (_msg_sw or "") or "控件" in (_msg_sw or ""), (_msg_sw or "")[:40])
_dsw = _json_mod.loads(_sw.save_json())
_sw2 = Construction()
_sw2.load_json(_json_mod.dumps(_dsw))
check(".ggk 往返保留控件新位置与滑块数值",
      "(4,-2)" in _sw2.elements["slW"].defn and abs(_sw2.elements["slW"].value - 7) < 1e-9
      and "(2,3)" in _sw2.elements["bW"].defn,
      "%r 值=%.1f" % (_sw2.elements["slW"].defn, _sw2.elements["slW"].value))

# ---------------------------------------------------------------------------
section("Z13. 表达式依赖：受控点/数值/字面量坐标随滑块重算")

_ex = Construction()
_ex.process("sX=Slider[0,10,1,(0,0)]")
_ex.process("SetValue[sX, 3]")
_ex.process("AX=(sX,0)")                       # 受控点
_ex.process("sgX=Segment[(0,0),(sX,2)]")       # 字面量坐标里引用滑块
_ex.process("nX=sX*2")                         # 受控数值
_ex.process("PX=(1,2)")                        # 纯常量 → 自由点
_ex.process("cxX=Circle[(0,0),sX]")            # 元素参数（原本就跟随，回归）
_B = (round(_ex.elements["AX"].x, 3), round(_ex.elements["sgX"].x2, 3),
      round(_ex.elements["nX"].value, 3), round(_ex.elements["cxX"].r, 3))
_ex.process("SetValue[sX, 7]")
_A = (round(_ex.elements["AX"].x, 3), round(_ex.elements["sgX"].x2, 3),
      round(_ex.elements["nX"].value, 3), round(_ex.elements["cxX"].r, 3))
check("受控点 A=(s,0) 随滑块重算（3 → 7）", _B[0] == 3.0 and _A[0] == 7.0, "%s → %s" % (_B[0], _A[0]))
check("字面量坐标 (s,2) 随滑块重算（Segment 端点 3 → 7）", _B[1] == 3.0 and _A[1] == 7.0, "%s → %s" % (_B[1], _A[1]))
check("受控数值 n=s*2 随滑块重算（6 → 14）", _B[2] == 6.0 and _A[2] == 14.0, "%s → %s" % (_B[2], _A[2]))
check("元素参数（圆半径）本就跟随（回归）", _B[3] == 3.0 and _A[3] == 7.0, "%s → %s" % (_B[3], _A[3]))
check("受控点不可直接拖动、纯常量点仍自由",
      _ex.elements["AX"].free is False and _ex.elements["PX"].free is True
      and _ex.elements["AX"].defn == "AX=(sX,0)", "%r free=%s" % (_ex.elements["AX"].defn, _ex.elements["AX"].free))
_dex = _json_mod.loads(_ex.save_json())
_ex2 = Construction()
_ex2.load_json(_json_mod.dumps(_dex))
_ex2.process("SetValue[sX, 5]")
check(".ggk 往返后受控点仍然跟随（AX.x → 5）", round(_ex2.elements["AX"].x, 3) == 5.0,
      str(round(_ex2.elements["AX"].x, 3)))

# ---------------------------------------------------------------------------
section("Z14. 就地编辑控件说明/脚本（SetCaption / SetScript）")

_ce = Construction()
_ce.process('bE=Button["旧说明", "AE=(1,1)", (2,3)]')
_ce.process("cE=Circle[(0,0),1]")
_ce.process('cbE=CheckBox["旧说明", cE, (0,0)]')
_ce.process('txE=Text["旧文本", (1,1)]')
_ce.process('SetCaption[bE, "开始"]')
_ce.process('SetScript[bE, "BE=(2,2);CE=(3,3)"]')
_ce.process('SetCaption[cbE, "显示圆"]')
_ce.process('SetCaption[txE, "新文本"]')
check("SetCaption 改按钮/复选框说明并重写 defn",
      _ce.elements["bE"].caption == "开始" and _ce.elements["bE"].defn == 'bE=Button["开始","BE=(2,2);CE=(3,3)",(2,3)]'
      and _ce.elements["cbE"].caption == "显示圆" and 'CheckBox["显示圆"' in _ce.elements["cbE"].defn,
      "%r | %r" % (_ce.elements["bE"].defn, _ce.elements["cbE"].defn))
check("SetScript 改按钮脚本（分号分隔多条）",
      _ce.elements["bE"].script == "BE=(2,2);CE=(3,3)" and "BE=(2,2)" in _ce.elements["bE"].defn,
      repr(_ce.elements["bE"].script))
check("SetCaption 对文本改内容与 defn",
      _ce.elements["txE"].content == "新文本" and 'Text["新文本"' in _ce.elements["txE"].defn,
      "%r %r" % (_ce.elements["txE"].content, _ce.elements["txE"].defn))
_msg_sc = _ce.process('SetScript[cE, "x"]')
check("SetScript 用非按钮 → 明确报错", "按钮" in (_msg_sc or ""), (_msg_sc or "")[:34])
_dce = _json_mod.loads(_ce.save_json())
_ce2 = Construction()
_ce2.load_json(_json_mod.dumps(_dce))
check(".ggk 往返保留新说明与脚本",
      _ce2.elements["bE"].caption == "开始" and _ce2.elements["bE"].script == "BE=(2,2);CE=(3,3)"
      and _ce2.elements["txE"].content == "新文本",
      "%r %r" % (_ce2.elements["bE"].caption, _ce2.elements["bE"].script))

# ---------------------------------------------------------------------------
section("Z15. 输入框提交 SetInput（数值 / 表达式 / 坐标）")

_si = Construction()
_si.process("sI=Slider[0,10,1,(0,0)]")
_si.process("SetValue[sI, 3]")
_si.process("nI=5")
_si.process("dI=sI*2")
_si.process("AI=(1,1)")
_si.process('SetInput[sI, "7"]')
check("SetInput 纯数值 → 改值且保留 Slider 定义（不退化成普通数值）",
      abs(_si.elements["sI"].value - 7) < 1e-9 and _si.elements["sI"].defn == "sI=Slider[0,10,1,(0,0)]"
      and _si.elements["sI"].min == 0, "%r 值=%.1f" % (_si.elements["sI"].defn, _si.elements["sI"].value))
_si.process('SetInput[sI, "2+3*2"]')
check("SetInput 数值表达式 → 求值改值（滑块仍保留）",
      abs(_si.elements["sI"].value - 8) < 1e-9 and "Slider[" in _si.elements["sI"].defn,
      "值=%.1f defn=%r" % (_si.elements["sI"].value, _si.elements["sI"].defn))
_si.process('SetInput[nI, "sI+1"]')
check("SetInput 引用元素的表达式 → 重定义为受控数值（free=False、保留表达式）",
      _si.elements["nI"].free is False and _si.elements["nI"].defn == "nI=sI+1"
      and abs(_si.elements["nI"].value - 9) < 1e-9,
      "free=%s defn=%r 值=%.1f" % (_si.elements["nI"].free, _si.elements["nI"].defn, _si.elements["nI"].value))
_si.process("SetValue[sI, 9]")
check("重定义后跟随滑块（sI=9 → nI=10）", abs(_si.elements["nI"].value - 10) < 1e-9,
      "%.1f" % _si.elements["nI"].value)
_si.process('SetInput[AI, "(4,5)"]')
check("SetInput 坐标 → 重定义点", abs(_si.elements["AI"].x - 4) < 1e-9 and abs(_si.elements["AI"].y - 5) < 1e-9,
      "(%.1f,%.1f)" % (_si.elements["AI"].x, _si.elements["AI"].y))
_si.process('SetInput[dI, "sI*3"]')
check("SetInput 改受控对象 → 按新表达式重定义", abs(_si.elements["dI"].value - 27) < 1e-9,
      "%.1f" % _si.elements["dI"].value)
_msg_si = _si.process('SetInput[nI, "((("]')
check("SetInput 非法表达式 → 明确报错", "不匹配" in (_msg_si or "") or "错误" in (_msg_si or ""), (_msg_si or "")[:30])

print("\n" + "=" * 60)
print("2D 内核检测矩阵：%d 项断言，%d 失败" % (PASS + FAIL, FAIL))
if FAILED:
    for nm in FAILED:
        print("  FAILED: " + nm)
    print("结果: FAILED")
    sys.exit(1)
print("结果: ALL PASS")
sys.exit(0)
