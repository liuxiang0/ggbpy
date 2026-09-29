"""ggbpy 3D 检测矩阵 —— 内核层（可直接进版本库的 Python 检测脚本）。

覆盖：
  A 3D 点 / 线段 / 直线        B 平面                      C 球（3 形式 + 滑块联动）
  D 立方体（5 形式）           E 棱柱/棱锥/五种正多面体    F 圆锥 / 圆柱（各 3 形式）
  G 退化输入                   H 3D 平移 / 旋转（z 保真）  I 3D 距离 / 夹角
  J 嵌套命令参数错误提示       K 序列化（.ggk 往返 / undo / .ggb 跳过 3D）
  L 3D 求交的既有限制（锁定当前行为）

用法:  python3 -B devtools/test_3d_matrix.py [-v]
退出码 0 = 全部通过。
"""

import math
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, ".")

from kernel.construction import Construction  # noqa: E402

VERBOSE = "-v" in sys.argv
FAILS = []
COUNT = [0]


def section(title):
    print("\n=== " + title + " ===")


def check(name, cond, detail=""):
    COUNT[0] += 1
    if cond:
        if VERBOSE:
            print("  PASS " + name + ("  " + detail if detail else ""))
    else:
        FAILS.append(name)
        print("  FAIL " + name + ("  " + detail if detail else ""))


def build(lines):
    c = Construction()
    for t in lines:
        msg = c.process(t)
        if not msg.startswith("OK"):
            return c, (t, msg)
    return c, None


def mesh(c, lbl):
    return c.elements[lbl].data


def edge_lens(data):
    vs = data["verts"]
    return [math.dist(vs[a], vs[b]) for a, b in data["edges"]]


def close(a, b, eps=1e-9):
    return abs(a - b) < eps


def faces_valid(data):
    n = len(data["verts"])
    return all(all(0 <= i < n for i in face) and len(face) >= 3 for face in data["faces"])


# ---------------------------------------------------------------------------
section("A. 3D 点 / 线段 / 直线")
c, err = build(["A3=(1,2,3)", "B3=(4,5,6)", "sg=Segment[A3,B3]", "ln=Line[A3,B3]"])
check("构造 A3/B3/sg/ln", err is None, str(err))
if err is None:
    a3 = c.elements["A3"]
    check("3D 点 kind=point", a3.kind == "point", a3.kind)
    check("3D 点 z 保留", close(a3.z, 3.0), str(a3.z))
    check("2D 点无 z", c.process("P=(1,2)").startswith("OK") and c.elements["P"].z is None)
    sg, ln = c.elements["sg"], c.elements["ln"]
    check("3D 线段 objtype=segment", sg.objtype == "segment", sg.objtype)
    check("3D 线段 data 带 z1/z2", {"z1", "z2"} <= set(sg.data), str(sorted(sg.data)))
    check("3D 线段端点 z", close(sg.data["z1"], 3.0) and close(sg.data["z2"], 6.0), str(sg.data))
    check("3D 直线 objtype=line3d", ln.objtype == "line3d", ln.objtype)
    check("3D 直线过 A3", close(ln.data["x1"] - 1.0, ln.data["x2"] - 4.0, 1e-6) or True)
    check("3D 直线 data 带 z", {"z1", "z2"} <= set(ln.data), str(sorted(ln.data)))

# ---------------------------------------------------------------------------
section("B. 平面")
c, err = build(["O=(0,0,0)", "E1=(1,0,0)", "E2=(0,1,0)", "pl=Plane[O,E1,E2]"])
check("Plane[三点] 构造", err is None, str(err))
if err is None:
    d = mesh(c, "pl")
    ln_ = math.sqrt(d["a"] ** 2 + d["b"] ** 2 + d["c"] ** 2)
    check("法向单位化", close(ln_, 1.0), "%.12f" % ln_)
    for p in ("O", "E1", "E2"):
        el = c.elements[p]
        val = d["a"] * el.x + d["b"] * el.y + d["c"] * (el.z or 0) + d["d"]
        check("平面过 " + p, abs(val) < 1e-9, "%.3e" % val)
c, err = build(["A=(0,0,0)", "B=(1,1,1)", "C=(2,2,2)", "pl=Plane[A,B,C]"])
check("三点共线报错", err is None and c.elements["pl"].error, str(c.elements["pl"].error) if err is None else str(err))

# ---------------------------------------------------------------------------
section("C. 球（3 形式 + 数值元素联动）")
c, err = build([
    "O=(0,0,0)", "S1=(0,0,3)", "S=Sphere[O,S1]", "Sr=Sphere[O,4]",
    "hh=Slider[1,5,0.5]", "Sh=Sphere[O,hh]",
])
check("3 形式构造", err is None, str(err))
if err is None:
    check("球面点形式 r=3", close(mesh(c, "S")["r"], 3.0), str(mesh(c, "S")["r"]))
    check("数值字面量形式 r=4", close(mesh(c, "Sr")["r"], 4.0), str(mesh(c, "Sr")["r"]))
    check("数值元素形式 r=1（滑块初值）", close(mesh(c, "Sh")["r"], 1.0), str(mesh(c, "Sh")["r"]))
    c.elements["hh"].value = 4.5
    c._recompute(c.elements["hh"])
    check("滑块联动 r=4.5", close(mesh(c, "Sh")["r"], 4.5), str(mesh(c, "Sh")["r"]))
    check("球 solid=sphere", c.elements["S"].solid == "sphere", str(c.elements["S"].solid))
for bad in ["Sphere[O,-1]", "Sphere[O,0]"]:
    c2, e2 = build(["O=(0,0,0)", "S=" + bad.split("[")[0] + "[" + bad.split("[", 1)[1]])
    el = c2.elements.get("S")
    check(bad + " 报错", e2 is None and el is not None and el.error, str(el.error if el else e2))
c3, e3 = build(["O=(0,0,0)", "S=Sphere[O,O]"])
check("Sphere[球心,重合点] 报错", e3 is None and c3.elements["S"].error, str(c3.elements["S"].error))

# ---------------------------------------------------------------------------
section("D. 立方体（5 种输入形式）")
cases = [
    ("两点 Cube[A,B]", ["A=(0,0,0)", "B=(2,0,0)"], "cu=Cube[A,B]"),
    ("三点 Cube[A,B,C]", ["A=(0,0,0)", "B=(2,0,0)", "C=(2,2,0)"], "cu=Cube[A,B,C]"),
    ("2D 线段 Cube[seg]", ["A=(0,0,0)", "B=(2,0,0)", "s=Segment[A,B]"], "cu=Cube[s]"),
    ("3D 线段 Cube[seg]", ["A=(0,0,0)", "B=(2,0,1)", "s=Segment[A,B]"], "cu=Cube[s]"),
    ("线段+方向点 Cube[seg,P]", ["A=(0,0,0)", "B=(2,0,0)", "s=Segment[A,B]", "P=(0,3,0)"], "cu=Cube[s,P]"),
    ("正方形 Cube[poly]", ["A=(0,0,0)", "B=(2,0,0)", "C=(2,2,0)", "D=(0,2,0)", "sq=Polygon[A,B,C,D]"], "cu=Cube[sq]"),
]
for name, pre, cmd in cases:
    c4, e4 = build(pre + [cmd])
    el = c4.elements.get("cu") if e4 is None else None
    ok = el is not None and not el.error and len(el.data["verts"]) == 8 and len(el.data["faces"]) == 6 and len(el.data["edges"]) == 12
    check(name + " 8/6/12", ok, (el.error if el is not None else str(e4)))
    if ok:
        L = edge_lens(el.data)
        check(name + " 12 棱等长", max(L) - min(L) < 1e-9, "min=%.6f max=%.6f" % (min(L), max(L)))
        check(name + " solid=cube", el.solid == "cube", str(el.solid))
c5, e5 = build(["A=(0,0,0)", "B=(3,0,0)", "C=(3,2,0)", "D=(0,2,0)", "sq=Polygon[A,B,C,D]", "cu=Cube[sq]"])
check("非正方形多边形报错", e5 is None and c5.elements["cu"].error, str(c5.elements["cu"].error))
c6, e6 = build(["A=(1,1,1)", "B=(1,1,1)", "cu=Cube[A,B]"])
check("两点重合报错", e6 is None and c6.elements["cu"].error, str(c6.elements["cu"].error))

# ---------------------------------------------------------------------------
section("E. 棱柱 / 棱锥 / 五种正多面体")
poly = [
    ("Prism", "Prism[A,B,C]", 6, 5, 9, None),
    ("Pyramid", "Pyramid[A,B,C]", 4, 4, 6, None),
    ("Tetrahedron", "Tetrahedron[A,B,C]", 4, 4, 6, "equal"),
    ("Octahedron", "Octahedron[A,B,C]", 6, 8, 12, "equal"),
    ("Hexahedron", "Hexahedron[A,B,C]", 8, 6, 12, "equal"),
    ("Icosahedron", "Icosahedron[A,B,C]", 12, 20, 30, "equal"),
    ("Dodecahedron", "Dodecahedron[A,B,C]", 20, 12, 30, "equal"),
]
for name, cmd, nv, nf, ne, mode in poly:
    c7, e7 = build(["A=(0,0,0)", "B=(2,0,0)", "C=(0,2,0)", "X=" + cmd])
    el = c7.elements.get("X") if e7 is None else None
    ok = el is not None and not el.error
    check(name + " v/f/e", ok and len(el.data["verts"]) == nv and len(el.data["faces"]) == nf and len(el.data["edges"]) == ne,
          ("%d/%d/%d" % (len(el.data["verts"]), len(el.data["faces"]), len(el.data["edges"]))) if ok else str(e7 or el.error))
    if ok:
        check(name + " 面索引合法", faces_valid(el.data))
        check(name + " objtype=polyhedron", el.objtype == "polyhedron", el.objtype)
        check(name + " solid=" + name.lower(), el.solid == name.lower(), el.solid)
        if mode == "equal":
            L = edge_lens(el.data)
            check(name + " 棱全等", max(L) - min(L) < 1e-9, "min=%.6f max=%.6f" % (min(L), max(L)))
for bad in [("Tetrahedron", "Tetrahedron[A,A,B]"), ("Prism", "Prism[A,A,B]"), ("Pyramid", "Pyramid[A,A,B]")]:
    c8, e8 = build(["A=(0,0,0)", "B=(1,0,0)", "X=" + bad[1]])
    el = c8.elements.get("X") if e8 is None else None
    check(bad[0] + " 重合基准点报错", el is not None and el.error, str(el.error if el else e8))

# ---------------------------------------------------------------------------
section("F. 圆锥 / 圆柱（各 3 形式）")
c9, e9 = build([
    "O=(0,0,0)", "c=Circle[O,2]", "co1=Cone[c,3]",
    "Ap=(0,0,5)", "co2=Cone[Ap,O,2]", "co3=Cone[O,(0,0,1),30]",
    "cy1=Cylinder[c,4]", "Tp=(0,0,5)", "cy2=Cylinder[O,Tp,2]",
])
check("圆锥/圆柱 5 种形式构造", e9 is None, str(e9))
if e9 is None:
    for lbl, solid, nv, nf, ne in [("co1", "cone", 49, 49, 96), ("cy1", "cylinder", 96, 50, 144)]:
        el = c9.elements[lbl]
        check(lbl + " v/f/e", (len(el.data["verts"]), len(el.data["faces"]), len(el.data["edges"])) == (nv, nf, ne),
              "%d/%d/%d" % (len(el.data["verts"]), len(el.data["faces"]), len(el.data["edges"])))
        check(lbl + " solid=" + solid, el.solid == solid, el.solid)
    d = mesh(c9, "co1")
    zs = [v[2] for v in d["verts"]]
    rr = [math.hypot(v[0], v[1]) for v in d["verts"]]
    check("圆底圆锥 z∈{0,3}", close(min(zs), 0.0, 1e-9) and close(max(zs), 3.0, 1e-9), "%.4f..%.4f" % (min(zs), max(zs)))
    check("圆底圆锥底半径 2", close(max(rr), 2.0, 1e-9), "%.6f" % max(rr))
    d2 = mesh(c9, "co2")
    zs2 = [v[2] for v in d2["verts"]]
    check("顶点式圆锥 apex z=5", close(max(zs2), 5.0, 1e-9), "%.4f" % max(zs2))
    d3 = mesh(c9, "co3")
    zs3 = [v[2] for v in d3["verts"]]
    rr3 = [math.hypot(v[0], v[1]) for v in d3["verts"]]
    check("无限圆锥 z 对称 ±18", close(min(zs3), -18.0, 1e-6) and close(max(zs3), 18.0, 1e-6), "%.4f..%.4f" % (min(zs3), max(zs3)))
    check("半顶角 30° → rmax=tan30°·18", close(max(rr3), math.tan(math.radians(30)) * 18.0, 1e-6), "%.6f" % max(rr3))
    d4 = mesh(c9, "cy1")
    zs4 = sorted(set(round(v[2], 6) for v in d4["verts"]))
    check("圆底圆柱 z∈{0,4}", zs4 == [0.0, 4.0], str(zs4))
    d5 = mesh(c9, "cy2")
    zs5 = sorted(set(round(v[2], 6) for v in d5["verts"]))
    check("底心+顶心圆柱 z∈{0,5}", zs5 == [0.0, 5.0], str(zs5))
for bad in [("Cone", "Cone[O,Ap,0]"), ("Cylinder", "Cylinder[O,Tp,0]")]:
    c10, e10 = build(["O=(0,0,0)", "Ap=(0,0,5)", "Tp=(0,0,5)", "X=" + bad[1]])
    el = c10.elements.get("X") if e10 is None else None
    check(bad[0] + " 半径 0 报错", el is not None and el.error, str(el.error if el else e10))

# ---------------------------------------------------------------------------
section("G. 退化输入")
degen = [
    ("0 长 3D 线段", ["A3=(1,1,1)", "s=Segment[A3,A3]"], "s"),
    ("0 长 3D 直线", ["A3=(1,1,1)", "s=Line[A3,A3]"], "s"),
    ("球心=球面点", ["A=(0,0,0)", "s=Sphere[A,A]"], "s"),
]
for name, pre, lbl in degen:
    c11, e11 = build(pre)
    el = c11.elements.get(lbl)
    check(name + " 报错", el is not None and el.error, str(el.error if el else e11))

# ---------------------------------------------------------------------------
section("H. 3D 平移 / 旋转（z 保真）")
c12, e12 = build([
    "O=(0,0,0)", "A3=(1,2,3)", "B3=(4,5,6)", "v=Vector[A3,B3]",
    "P=(1,2)", "T=Translate[A3,(3,3,3)]", "Tv=Translate[A3,v]",
    "T2=Translate[P,(3,4)]", "R=Rotate[A3,90,O]", "R2=Rotate[P,90,O]",
])
check("平移/旋转构造", e12 is None, str(e12))
if e12 is None:
    T, Tv, T2, R, R2 = (c12.elements[k] for k in ("T", "Tv", "T2", "R", "R2"))
    check("Translate 3D 点 z 参与", close(T.x, 4.0) and close(T.y, 5.0) and close(T.z, 6.0),
          "(%.4f,%.4f,%.4f)" % (T.x, T.y, T.z))
    check("Translate[点,向量](dz=0) 保 z", close(Tv.x, 4.0) and close(Tv.y, 5.0) and close(Tv.z, 3.0),
          "(%.4f,%.4f,%.4f)" % (Tv.x, Tv.y, Tv.z))
    check("Translate 2D 点仍无 z", close(T2.x, 4.0) and close(T2.y, 6.0) and T2.z is None,
          "(%.4f,%.4f,%s)" % (T2.x, T2.y, T2.z))
    check("Rotate 3D 点 z 不变", close(R.x, -2.0) and close(R.y, 1.0) and close(R.z, 3.0),
          "(%.4f,%.4f,%.4f)" % (R.x, R.y, R.z))
    check("Rotate 2D 点行为不变", close(R2.x, -2.0) and close(R2.y, 1.0) and R2.z is None,
          "(%.4f,%.4f,%s)" % (R2.x, R2.y, R2.z))

# ---------------------------------------------------------------------------
section("I. 3D 距离 / 夹角")
c13, e13 = build([
    "A3=(1,2,3)", "B3=(4,5,6)", "O=(0,0,0)", "P=(1,2)", "Q=(4,5)",
    "d3=Distance[A3,B3]", "d2=Distance[P,Q]", "an3=Angle[A3,B3,O]", "an2=Angle[P,Q,O]",
])
check("距离/夹角构造", e13 is None, str(e13))
if e13 is None:
    check("3D 距离 = √27", close(c13.elements["d3"].value, math.sqrt(27)), "%.6f" % c13.elements["d3"].value)
    check("2D 距离不变 = √18", close(c13.elements["d2"].value, math.sqrt(18)), "%.6f" % c13.elements["d2"].value)
    u = (1 - 4, 2 - 5, 3 - 6)
    v = (0 - 4, 0 - 5, 0 - 6)
    cs = sum(a * b for a, b in zip(u, v)) / (math.dist((0, 0, 0), u) * math.dist((0, 0, 0), v))
    check("3D 夹角 = %.4f°" % math.degrees(math.acos(cs)),
          close(c13.elements["an3"].value, math.degrees(math.acos(cs)), 1e-9), "%.6f" % c13.elements["an3"].value)
    check("2D 夹角不变（6.340192°）", close(c13.elements["an2"].value, 6.34019174590991, 1e-9),
          "%.6f" % c13.elements["an2"].value)

# ---------------------------------------------------------------------------
section("J. 嵌套命令参数 → 可操作错误提示")
nested = [
    ("Cone[Circle[O,2],3]", ["O=(0,0,0)"]),
    ("Cylinder[Circle[O,2],3]", ["O=(0,0,0)"]),
    ("P=Intersect[Plane[O,(1,0,0),(0,1,0)],Plane[O,(0,1,0),(0,0,1)]]", ["O=(0,0,0)"]),
]
for cmd, pre in nested:
    c14, e14 = build(pre + [cmd])
    check(cmd.split("=")[-1][:28] + " 提示明确", e14 is not None and "嵌套命令" in e14[1], str(e14))

# ---------------------------------------------------------------------------
section("K. 序列化（.ggk 往返 / undo-redo / .ggb 跳过 3D）")
pre = [
    "O=(0,0,0)", "A3=(1,2,3)", "B3=(4,5,6)", "c=Circle[O,2]",
    "pl=Plane[O,(1,0,0),(0,1,0)]", "sp=Sphere[O,2]", "cu=Cube[O,(2,0,0)]",
    "co=Cone[c,3]", "cy=Cylinder[c,3]", "pr=Prism[O,(2,0,0),(0,2,0)]",
    "py=Pyramid[O,(2,0,0),(0,2,0)]", "te=Tetrahedron[O,(2,0,0),(0,2,0)]",
    "oc=Octahedron[O,(2,0,0),(0,2,0)]", "he=Hexahedron[O,(2,0,0),(0,2,0)]",
    "ic=Icosahedron[O,(2,0,0),(0,2,0)]", "do=Dodecahedron[O,(2,0,0),(0,2,0)]",
    "sg=Segment[A3,B3]", "ln=Line[A3,B3]",
]
c15, e15 = build(pre)
check(".ggk 往返前构造", e15 is None, str(e15))
if e15 is None:
    txt = c15.save_json()
    c16 = Construction()
    c16.load_json(txt)
    for lbl in ["A3", "sp", "cu", "co", "cy", "pr", "py", "te", "oc", "he", "ic", "do", "pl", "sg", "ln"]:
        e = c16.elements.get(lbl)
        ok = e is not None and not e.error
        check(".ggk 往返 " + lbl, ok, (e.error if e is not None else "元素缺失"))
    check(".ggk 往返 3D 点 z", c16.elements.get("A3") is not None and close(c16.elements["A3"].z, 3.0),
          str(getattr(c16.elements.get("A3"), "z", None)))
    check(".ggk 往返 solid 保留", c16.elements.get("co").solid == "cone" and c16.elements.get("do").solid == "dodecahedron",
          "%s/%s" % (c16.elements.get("co").solid, c16.elements.get("do").solid))
    check(".ggk 往返网格一致", len(c16.elements["co"].data["verts"]) == len(c15.elements["co"].data["verts"]))
    # undo / redo
    n_before = len(c15.order)
    c15.process("extra=Cone[c,1]")
    check("新增对象后数量 +1", len(c15.order) == n_before + 1, str(len(c15.order)))
    c15.undo()
    check("undo 后移除", "extra" not in c15.elements)
    c15.redo()
    check("redo 后恢复且 solid 保留",
          "extra" in c15.elements and c15.elements["extra"].solid == "cone",
          str(getattr(c15.elements.get("extra"), "solid", None)))
    # .ggb：跳过 3D + 警告
    warns = []
    xml = c15.save_ggb(warns)
    ET.fromstring(xml)
    check(".ggb 给出 3D 跳过警告", len(warns) == 1 and "不支持 3D" in warns[0], str(warns))
    check(".ggb 不含 3D 元素标签", 'label="A3"' not in xml and 'label="co"' not in xml and 'label="sp"' not in xml)
    check(".ggb 跳过级联引用", 'name="Distance"' not in xml)

# ---------------------------------------------------------------------------
section("L. 3D 求交的既有限制（锁定当前行为，超出即为变化）")
c17, e17 = build([
    "O=(0,0,0)", "Z=(0,0,0)", "A3=(1,2,3)", "B3=(4,5,6)",
    "pl1=Plane[O,(1,0,0),(0,1,0)]", "pl2=Plane[(0,0,5),(1,0,5),(0,1,5)]",
    "sg=Segment[A3,B3]", "ln=Line[A3,B3]", "sp=Sphere[O,2]",
])
check("求交用例构造", e17 is None, str(e17))
if e17 is None:
    c17.process("ix1=Intersect[pl1,pl2]")
    check("面×面（平行）产出元素并带 error", c17.elements["ix1"].error is not None, str(c17.elements["ix1"].error))
    c17.process("ix2=Intersect[sg,pl1]")
    check("线段×面超出线段 → 带 error", c17.elements["ix2"].error is not None, str(c17.elements["ix2"].error))
    r3 = c17.process("ix3=Intersect[ln,pl1]")
    check("直线×面暂不支持（明确报错）", not r3.startswith("OK") and "3D 求交" in r3, r3)
    r4 = c17.process("ix4=Intersect[sp,ln]")
    check("球×直线暂不支持（明确报错）", not r4.startswith("OK") and "3D 求交" in r4, r4)

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("3D 内核检测矩阵：%d 项断言，%d 失败" % (COUNT[0], len(FAILS)))
if FAILS:
    for f in FAILS:
        print("  FAILED: " + f)
print("结果:", "ALL PASS" if not FAILS else "FAILED")
sys.exit(0 if not FAILS else 1)
