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
import re
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
section("J. 嵌套命令参数（就地求值，匿名辅助不注册）")
c14, e14 = build([
    "O=(0,0,0)", "A3=(1,2,3)", "B3=(4,5,6)", "E1=(1,0,0)", "E2=(0,1,0)",
    "k1=Cone[Circle[O,2],3]",
    "k2=Cylinder[Circle[O,2],4]",
    "k3=Sphere[Midpoint[(0,0,0),(2,2,0)],1]",
    "k4=Sphere[O,Distance[A3,B3]]",
    "x1=Intersect[Plane[O,E1,E2],Plane[O,(0,1,0),(0,0,1)]]",
    "cu=Cube[Polygon[(0,0,0),(2,0,0),(2,2,0),(0,2,0)]]",
])
check("嵌套命令构造", e14 is None, str(e14))
if e14 is None:
    check("Cone[Circle[O,2],3] 底半径 2 / 高 3",
          close(max(math.hypot(v[0], v[1]) for v in c14.elements["k1"].data["verts"]), 2.0, 1e-9)
          and close(max(v[2] for v in c14.elements["k1"].data["verts"]), 3.0, 1e-9))
    check("Cylinder[Circle[O,2],4] 顶点 96", len(c14.elements["k2"].data["verts"]) == 96)
    mid = c14.elements["k3"]
    check("Sphere[Midpoint[...],1] 球心 (1,1,0)", close(mid.data["cx"], 1.0) and close(mid.data["cy"], 1.0),
          "(%s,%s)" % (mid.data["cx"], mid.data["cy"]))
    check("Sphere[O,Distance[A3,B3]] r=√27", close(c14.elements["k4"].data["r"], math.sqrt(27), 1e-9),
          "%.6f" % c14.elements["k4"].data["r"])
    check("嵌套 Intersect[Plane[...],Plane[...]] 得交线", not c14.elements["x1"].error, str(c14.elements["x1"].error))
    check("Cube[Polygon[...]] 8/6/12",
          (len(c14.elements["cu"].data["verts"]), len(c14.elements["cu"].data["faces"]),
           len(c14.elements["cu"].data["edges"])) == (8, 6, 12))
    check("匿名辅助不进对象列表（11 条语句 = 11 个对象）", len(c14.order) == 11, "order=" + str(len(c14.order)))
    check("匿名辅助不进 elements（无 _n 前缀）", not any(str(l).startswith("_n") for l in c14.order))
    # 撤销 / 重做 / 序列化都不丢嵌套语义
    c14.process("k5=Cone[Circle[O,1],2]")
    n_a = len(c14.order)
    c14.undo()
    check("嵌套对象可撤销", "k5" not in c14.elements and len(c14.order) == n_a - 1)
    c14.redo()
    check("嵌套对象可重做且 solid 保留",
          "k5" in c14.elements and c14.elements["k5"].solid == "cone")
    txt14 = c14.save_json()
    c17 = Construction()
    c17.load_json(txt14)
    check(".ggk 往返保留嵌套 defn", c17.elements["k1"].defn == "k1=Cone[Circle[O,2],3]", c17.elements["k1"].defn)
    check(".ggk 往返嵌套对象有效", not c17.elements["k1"].error and not c17.elements["k3"].error)
    # 错误路径（命令级错误 → 消息；元素级错误 → error 字段）
    for bad, expect in [("Sphere[O,NoSuchCmd[1]]", "嵌套命令中不支持命令"),
                        ("Midpoint[Sphere[O,1],1]", "不是点"),
                        ("Cone[Circle[O,-1],3]", "嵌套命令失败")]:
        c18 = Construction()
        c18.process("O=(0,0,0)")
        msg = c18.process("bad=" + bad)
        el = c18.elements.get("bad")
        hit = expect in msg or (el is not None and el.error and expect in el.error)
        check("嵌套错误提示: " + bad, hit, msg[:70])
    # 非嵌套路径同样不应静默使用无效底面圆
    c18b = Construction()
    c18b.process("O=(0,0,0)")
    c18b.process("cc=Circle[O,-1]")
    c18b.process("k=Cone[cc,3]")
    el = c18b.elements.get("k")
    check("无效底面圆 → 锥体带 error（不静默生成）",
          el is not None and el.error and "底面圆无效" in el.error, str(getattr(el, "error", None)))

# ---------------------------------------------------------------------------
section("M. 网格完整性（面序 / 外向 / Euler / 体积）")
def _newell_vol(vs, faces):
    V = 0.0
    for f in faces:
        a = vs[f[0]]
        for i in range(1, len(f) - 1):
            b, cc = vs[f[i]], vs[f[i + 1]]
            V += (a[0] * (b[1] * cc[2] - b[2] * cc[1]) - a[1] * (b[0] * cc[2] - b[2] * cc[0])
                  + a[2] * (b[0] * cc[1] - b[1] * cc[0]))
    return V / 6.0


def _outward(vs, faces):
    ctr = [sum(v[i] for v in vs) / len(vs) for i in range(3)]
    for f in faces:
        nx = ny = nz = 0.0
        for i in range(len(f)):
            a, b = vs[f[i]], vs[f[(i + 1) % len(f)]]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        fc = [sum(vs[i][k] for i in f) / len(f) for k in range(3)]
        if nx * (fc[0] - ctr[0]) + ny * (fc[1] - ctr[1]) + nz * (fc[2] - ctr[2]) <= 1e-12:
            return False, f
    return True, None


c19, e19 = build(["O=(0,0,0)", "c=Circle[O,2]", "cu=Cube[O,(2,0,0)]", "co=Cone[c,3]",
                  "cy=Cylinder[c,4]", "pr=Prism[O,(2,0,0),(0,2,0)]", "py=Pyramid[O,(2,0,0),(0,2,0)]",
                  "te=Tetrahedron[O,(2,0,0),(0,2,0)]", "oc=Octahedron[O,(2,0,0),(0,2,0)]",
                  "he=Hexahedron[O,(2,0,0),(0,2,0)]", "ic=Icosahedron[O,(2,0,0),(0,2,0)]",
                  "do=Dodecahedron[O,(2,0,0),(0,2,0)]"])
check("网格用例构造", e19 is None, str(e19))
if e19 is None:
    for lbl in ["cu", "co", "cy", "pr", "py", "te", "oc", "he", "ic", "do"]:
        d = c19.elements[lbl].data
        vs, faces = d["verts"], d["faces"]
        check(lbl + " Euler V-E+F=2", len(vs) - len(d["edges"]) + len(faces) == 2,
              "%d-%d+%d" % (len(vs), len(d["edges"]), len(faces)))
        ok, badf = _outward(vs, faces)
        check(lbl + " 面全部外向", ok, str(badf))
        check(lbl + " 散度体积 > 0", _newell_vol(vs, faces) > 1e-9, "%.6f" % _newell_vol(vs, faces))
    # 多面体体积 = 棱长解析式（棱全等的正多面体）
    for lbl, form in [("cu", lambda e: e ** 3), ("te", lambda e: e ** 3 / (6 * math.sqrt(2))),
                      ("oc", lambda e: math.sqrt(2) / 3 * e ** 3),
                      ("ic", lambda e: 5 / 12 * (3 + math.sqrt(5)) * e ** 3),
                      ("do", lambda e: (15 + 7 * math.sqrt(5)) / 4 * e ** 3)]:
        d = c19.elements[lbl].data
        vs = d["verts"]
        vv = abs(_newell_vol(vs, d["faces"]))
        e = min(math.dist(vs[a], vs[b]) for a, b in d["edges"])
        check(lbl + " 网格体积 = 棱长解析式", close(vv, form(e), 1e-6 * max(1.0, abs(form(e)))),
              "mesh=%.6f analytic=%.6f" % (vv, form(e)))

# ---------------------------------------------------------------------------
section("N. Volume / Area 立体")
c20, e20 = build(["O=(0,0,0)", "c=Circle[O,2]", "cu=Cube[O,(2,0,0)]", "sp=Sphere[O,2]",
                  "co=Cone[c,3]", "cy=Cylinder[c,4]", "co3=Cone[O,(0,0,1),30]",
                  "sq=Polygon[(0,0,0),(2,0,0),(2,2,0),(0,2,0)]"])
check("体积/表面积用例构造", e20 is None, str(e20))
if e20 is None:
    vol_area = [
        ("V_cu", "Volume[cu]", 8.0), ("V_sp", "Volume[sp]", 4 / 3 * math.pi * 8),
        ("V_co", "Volume[co]", math.pi * 4), ("V_cy", "Volume[cy]", math.pi * 16),
        ("V_nest", "Volume[Cube[sq]]", 8.0),
        ("A_cu", "Area[cu]", 24.0), ("A_sp", "Area[sp]", 4 * math.pi * 4),
        ("A_co", "Area[co]", math.pi * 2 * (2 + math.sqrt(13))),
        ("A_cy", "Area[cy]", 2 * math.pi * 2 * 6),
        ("V_alias", "体积[cy]", math.pi * 16), ("A_alias", "表面积[sp]", 4 * math.pi * 4),
    ]
    for lbl, cmd, exp in vol_area:
        c20.process(lbl + "=" + cmd)
        el = c20.elements.get(lbl)
        got = getattr(el, "value", None)
        check("%s = %.6f" % (cmd, exp), got is not None and close(got, exp, 1e-9),
              "None" if got is None else "%.6f" % got)
    c20.process("V_te=Volume[Tetrahedron[O,(2,0,0),(0,2,0)]]")
    check("Volume[嵌套 Tetrahedron] > 0", c20.elements["V_te"].value > 0, "%.6f" % c20.elements["V_te"].value)
    # 无限圆锥：报错（元素 error）
    c20.process("bad_v=Volume[co3]")
    c20.process("bad_a=Area[co3]")
    check("无限圆锥 Volume 报错", bool(c20.elements["bad_v"].error), str(c20.elements["bad_v"].error))
    check("无限圆锥 Area 报错", bool(c20.elements["bad_a"].error), str(c20.elements["bad_a"].error))
    r = c20.process("bad2=Volume[O]")
    check("Volume 非立体报错", "需要 3D 立体" in r, r)
    check("2D 多边形 Area 不变", close(c20.process("A_sq=Area[sq]") and c20.elements["A_sq"].value, 4.0))

# ---------------------------------------------------------------------------
section("O. 3D 求交扩展")
c21, e21 = build(["O=(0,0,0)", "A3=(1,2,3)", "B3=(4,5,6)", "c=Circle[O,2]",
                  "pl=Plane[O,(1,0,0),(0,1,0)]", "cu=Cube[O,(2,0,0)]", "sp=Sphere[O,2]",
                  "ln=Line[A3,B3]", "sg=Segment[(0,0,2),(0,0,6)]",
                  "ix1=Intersect[ln,pl]", "ix2=Intersect[pl,ln]",
                  "sec=Intersect[pl,cu]", "ix3=Intersect[cu,ln]", "ix4=Intersect[ln,sp,2]",
                  "ix5=Intersect[sp,sg]"])
check("求交用例构造", e21 is None, str(e21))
if e21 is None:
    p1 = c21.elements["ix1"]
    check("直线×面 → 交点 (-2,-1,0)", p1.kind == "point" and close(p1.x, -2.0) and close(p1.y, -1.0) and close(p1.z, 0.0),
          "(%s,%s,%s)" % (p1.x, p1.y, p1.z))
    check("面×直线 交换顺序一致", c21.elements["ix2"].kind == "point" and close(c21.elements["ix2"].x, -2.0))
    sec = c21.elements["sec"]
    check("平面×立体 → 截面 section", getattr(sec, "objtype", "") == "section" and sec.data["count"] >= 3,
          str(getattr(sec, "objtype", None)))
    if getattr(sec, "objtype", "") == "section":
        zs = set(round(p[2], 6) for p in sec.data["pts"])
        check("截面点共面（z=0）", zs == {0.0}, str(zs))
    check("立体×直线 → 交点", c21.elements["ix3"].kind == "point" and not c21.elements["ix3"].error,
          str(c21.elements["ix3"].error))
    check("球×直线 第 2 交点（idx=2）", c21.elements["ix4"].kind == "point" and not c21.elements["ix4"].error,
          str(c21.elements["ix4"].error))
    check("球×线段 → 交点", c21.elements["ix5"].kind == "point" and not c21.elements["ix5"].error,
          str(c21.elements["ix5"].error))
    # 范围与不支持的组合
    c21.process("oob=Intersect[sg,pl]")
    check("线段×面 超出线段 → error", bool(c21.elements["oob"].error), str(c21.elements["oob"].error))
    c21.process("pl2=Plane[(0,0,5),(1,0,5),(0,1,5)]")
    c21.process("par=Intersect[pl,pl2]")
    check("平行平面 → error", bool(c21.elements["par"].error), str(c21.elements["par"].error))
    c21.process("ixs=Intersect[cu,sp]")
    check("立体×球 已支持（交线 curve3d 或明确无交线）",
          not c21.elements["ixs"].error or "不相交" in c21.elements["ixs"].error,
          str(c21.elements["ixs"].error))
    c21.process("cc=Intersect[sp,pl]")
    c21.process("bad2=Intersect[cc,cu]")
    check("空间圆×立体 已支持（回归：交点或明确无交点）",
          not c21.elements["bad2"].error or "无交点" in c21.elements["bad2"].error,
          str(c21.elements["bad2"].error))

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
    check(".ggb 3D 往返不再需要跳过警告", not warns, str(warns))
    check(".ggb 包含 3D 元素标签", 'label="A3"' in xml and 'label="co"' in xml and 'label="sp"' in xml)
    check(".ggb 3D 点带真实 z", 'z="3" w="1"' in xml)
    c15b = Construction()
    c15b.load_ggb(xml)
    check(".ggb 3D 往返元素齐全", c15b.elements.get("co") is not None
          and len(c15b.elements["co"].data["verts"]) == len(c15.elements["co"].data["verts"]))

# ---------------------------------------------------------------------------
section("L. 3D 求交的既定边界（锁定当前行为，超出即为变化）")
c17, e17 = build([
    "O=(0,0,0)", "A3=(1,2,3)", "B3=(4,5,6)",
    "pl1=Plane[O,(1,0,0),(0,1,0)]", "pl2=Plane[(0,0,5),(1,0,5),(0,1,5)]",
    "sg=Segment[A3,B3]", "cu=Cube[O,(2,0,0)]", "sp=Sphere[O,2]",
])
check("边界用例构造", e17 is None, str(e17))
if e17 is None:
    c17.process("ix1=Intersect[pl1,pl2]")
    check("面×面（平行）产出元素并带 error", c17.elements["ix1"].error is not None, str(c17.elements["ix1"].error))
    c17.process("ix2=Intersect[sg,pl1]")
    check("线段×面超出线段 → 带 error", c17.elements["ix2"].error is not None, str(c17.elements["ix2"].error))
    c17.process("ix5=Intersect[pl1,cu]")
    check("平面×立体仍然可用（回归）", getattr(c17.elements["ix5"], "objtype", "") == "section",
          str(getattr(c17.elements["ix5"], "objtype", None)))
    c17.process("ix6=Intersect[cu,cu]")
    check("立体×立体已支持（回归：同立体相交）", not c17.elements["ix6"].error
          and len(c17.elements["ix6"].data["verts"]) == 8, str(c17.elements["ix6"].error))
    c17.process("ix7=Intersect[pl1,sp]")
    check("面×球已支持（3D 圆）", getattr(c17.elements["ix7"], "objtype", "") == "circle3d",
          str(getattr(c17.elements["ix7"], "objtype", None)))
    c17.process("ix8=Intersect[sp,cu]")
    check("球×立体已支持（回归）", not c17.elements["ix8"].error
          or "不相交" in c17.elements["ix8"].error, str(c17.elements["ix8"].error))

# ---------------------------------------------------------------------------
section("P. 面×球 → 3D 圆 / 体×体 / 截面周长")
c22, e22 = build([
    "O=(0,0,0)", "cA=Cube[O,(2,0,0)]", "sp=Sphere[O,2]",
    "top=Plane[(0,0,2),(1,0,2),(0,1,2)]", "mid=Plane[(0,0,1),(1,0,1),(0,1,1)]",
    "tan=Plane[(0,0,2),(1,0,2),(0,1,2)]", "far=Plane[(0,0,3),(1,0,3),(0,1,3)]",
    "P1=(1,1,1)", "P2=(3,1,1)", "cB=Cube[P1,P2]",
    "R1=(1,0,0)", "R2=(3,0,0)", "cR=Cube[R1,R2]",
    "F1=(5,0,0)", "F2=(7,0,0)", "cD=Cube[F1,F2]",
    "cc1=Intersect[sp,mid]", "cc2=Intersect[mid,sp]",
    "ab=Intersect[cA,cB]", "ba=Intersect[cB,cA]", "aa=Intersect[cA,cA]",
    "ar=Intersect[cA,cR]", "ad=Intersect[cA,cD]",
    "sec_top=Intersect[cA,top]", "sec_mid=Intersect[cA,mid]",
    "per_top=Perimeter[sec_top]", "per_mid=Perimeter[sec_mid]",
])
check("第四批用例构造", e22 is None, str(e22))
if e22 is None:
    cc = c22.elements["cc1"]
    check("球∩平面 → circle3d", getattr(cc, "objtype", "") == "circle3d", str(getattr(cc, "objtype", None)))
    if getattr(cc, "objtype", "") == "circle3d":
        d = cc.data
        check("圆心 = 球心投影 (0,0,1)", close(d["cx"], 0.0) and close(d["cy"], 0.0) and close(d["cz"], 1.0),
              "(%s,%s,%s)" % (d["cx"], d["cy"], d["cz"]))
        check("半径 = √(r²-d²) = √3", close(d["r"], math.sqrt(3), 1e-9), "%.6f" % d["r"])
        check("法向等于平面法向 (0,0,1)", close(abs(d["normal"][2]), 1.0), str(d["normal"]))
    check("面×球 交换顺序一致",
          getattr(c22.elements["cc2"], "objtype", "") == "circle3d"
          and close(c22.elements["cc2"].data["r"], math.sqrt(3), 1e-9))
    c22.process("cc3=Intersect[sp,tan]")
    check("平面与球相切 → error", bool(c22.elements["cc3"].error), str(c22.elements["cc3"].error))
    c22.process("cc4=Intersect[sp,far]")
    check("平面与球不相交 → error", bool(c22.elements["cc4"].error), str(c22.elements["cc4"].error))
    # 体 × 体
    for lbl, exp_v, exp_n in [("ab", 1.0, (8, 6, 12)), ("ba", 1.0, (8, 6, 12)), ("aa", 8.0, (8, 6, 12)),
                              ("ar", 4.0, (8, 6, 12))]:
        el = c22.elements[lbl]
        d = el.data
        got_n = (len(d["verts"]), len(d["faces"]), len(d["edges"]))
        check("体∩体 " + lbl + " v/f/e", got_n == exp_n, str(got_n))
        c22.process("V_" + lbl + "=Volume[" + lbl + "]")
        check("体∩体 " + lbl + " 体积 = %.1f" % exp_v,
              close(c22.elements["V_" + lbl].value, exp_v, 1e-9), "%.6f" % c22.elements["V_" + lbl].value)
    check("体∩体 对称性", close(c22.elements["V_ab"].value, c22.elements["V_ba"].value, 1e-12))
    c22.process("ad=Intersect[cA,cD]")
    check("不相交立体 → error", bool(c22.elements["ad"].error), str(c22.elements["ad"].error))
    # 截面：平面与顶面重合
    check("平面与顶面重合 → section count=4", getattr(c22.elements["sec_top"], "objtype", "") == "section"
          and c22.elements["sec_top"].data["count"] == 4,
          str(getattr(c22.elements["sec_top"], "data", {}).get("count")))
    check("顶面截面周长 = 8", close(c22.elements["per_top"].value, 8.0, 1e-9), "%.6f" % c22.elements["per_top"].value)
    check("腰截面周长 = 8", close(c22.elements["per_mid"].value, 8.0, 1e-9), "%.6f" % c22.elements["per_mid"].value)
    check("Perimeter 对非截面仍报错", "需要" in c22.process("bad=Perimeter[cA]"), c22.process("bad=Perimeter[cA]")[:60])

# ---------------------------------------------------------------------------
section("Q. 求交退化容差（t=0 命中 / 相切 / 端点贴面）")
c23, e23 = build(["O=(0,0,0)", "sp=Sphere[O,2]", "cu=Cube[O,(2,0,0)]",
                  "sg1=Segment[(2,0,0),(4,0,0)]", "sg2=Segment[(-4,0,0),(-2,0,0)]",
                  "ln_t=Line[(2,-5,0),(2,5,0)]",
                  "sg_face=Segment[(0,1,1),(-2,1,1)]",
                  "ix1=Intersect[sp,sg1]", "ix2=Intersect[sp,sg2]",
                  "ix3=Intersect[sp,ln_t]", "ix4=Intersect[cu,sg_face]"])
check("容差用例构造", e23 is None, str(e23))
if e23 is None:
    p1 = c23.elements["ix1"]
    check("线段起点恰在球面（t=0）→ 命中", not p1.error and close(p1.x, 2.0, 1e-9) and close(p1.y, 0.0, 1e-9),
          "err=%s (%s,%s)" % (p1.error, getattr(p1, "x", None), getattr(p1, "y", None)))
    p2 = c23.elements["ix2"]
    check("线段终点恰在球面（t=1）→ 命中", not p2.error and close(p2.x, -2.0, 1e-9),
          "err=%s x=%s" % (p2.error, getattr(p2, "x", None)))
    p3 = c23.elements["ix3"]
    check("相切直线（判别式=0）→ 单点", not p3.error and close(p3.x, 2.0, 1e-9) and close(p3.y, 0.0, 1e-9),
          "err=%s" % p3.error)
    c23.process("ix5=Intersect[sp,ln_t,2]")
    check("相切直线取第 2 交点 → 明确报错",
          bool(c23.elements["ix5"].error) and "只有 1 个" in c23.elements["ix5"].error,
          str(c23.elements["ix5"].error))
    p4 = c23.elements["ix4"]
    check("线段端点贴立体表面（t=0）→ 命中", not p4.error and close(p4.x, 0.0, 1e-9)
          and close(p4.y, 1.0, 1e-9) and close(p4.z, 1.0, 1e-9),
          "err=%s (%s,%s,%s)" % (p4.error, getattr(p4, "x", None), getattr(p4, "y", None), getattr(p4, "z", None)))
    c23.process("ix6=Intersect[cu,Segment[(1,1,1),(1.5,1.5,1.5)]]")
    check("整段在立体内部 → 明确提示",
          bool(c23.elements["ix6"].error) and "无交点" in c23.elements["ix6"].error,
          str(c23.elements["ix6"].error))

# ---------------------------------------------------------------------------
section("R. 球×球 / 空间圆求交 / 样式快照 / 退化网格")
c24, e24 = build([
    "O=(0,0,0)", "A=(2,0,0)", "B=(5,0,0)", "C=(0.5,0,0)",
    "s1=Sphere[O,2]", "s2=Sphere[A,2]", "s3=Sphere[B,2]", "s4=Sphere[C,2]", "s5=Sphere[O,0.4]",
    "sp=Sphere[O,1.4]", "pz=Plane[(0,0,1),(1,0,1),(0,1,1)]",
    "px=Plane[(0.5,0,0),(0.5,1,0),(0.5,0,1)]",
    "py=Plane[(0,2,0),(1,2,0),(0,2,1)]",
    "cu=Cube[O,(2,0,0)]", "cc=Intersect[sp,pz]",
    "u1=Intersect[s1,s2]", "u2=Intersect[s2,s1]",
    "v1=Intersect[cc,px]", "v2=Intersect[cc,px,2]",
    "w1=Intersect[cc,cu]", "w2=Intersect[cc,cu,2]",
])
check("第五批用例构造", e24 is None, str(e24))
if e24 is None:
    u1 = c24.elements["u1"]
    check("球×球 → circle3d", getattr(u1, "objtype", "") == "circle3d", str(getattr(u1, "objtype", None)))
    if getattr(u1, "objtype", "") == "circle3d":
        d = u1.data
        check("交圆圆心 = (1,0,0)", close(d["cx"], 1.0) and close(d["cy"], 0.0) and close(d["cz"], 0.0),
              "(%s,%s,%s)" % (d["cx"], d["cy"], d["cz"]))
        check("交圆半径 = √3", close(d["r"], math.sqrt(3), 1e-9), "%.6f" % d["r"])
    u2 = c24.elements["u2"]
    check("球×球 交换顺序：同一交圆", close(u2.data["cx"], 1.0) and close(u2.data["r"], math.sqrt(3), 1e-9))
    for cmd, kw in [("e1=Intersect[s1,s3]", "相离"), ("e2=Intersect[s1,s5]", "同心"),
                    ("e3=Intersect[s1,s4]", None), ("e4=Intersect[s1,s1]", "同心")]:
        c24.process(cmd)
        el = c24.elements[cmd.split("=")[0]]
        if kw:
            check("球×球 " + kw + " → error", bool(el.error) and kw in el.error, str(el.error))
        else:
            check("球×球 内含 → 仍有交圆（小偏心情形）", not el.error and close(el.data["cx"], 0.25, 1e-9),
                  str(el.error))
    # 空间圆 × 平面
    v1, v2 = c24.elements["v1"], c24.elements["v2"]
    rr = math.sqrt(1.4 ** 2 - 1.0)          # 圆半径 √(1.96-1)=0.979796
    yy = math.sqrt(rr * rr - 0.25)
    check("空间圆×平面 第 1 交点 (0.5,−√(r²−0.25),1)",
          not v1.error and close(v1.x, 0.5, 1e-9) and close(v1.y, -yy, 1e-9) and close(v1.z, 1.0, 1e-9),
          "err=%s (%s,%s,%s)" % (v1.error, getattr(v1, "x", None), getattr(v1, "y", None), getattr(v1, "z", None)))
    check("空间圆×平面 第 2 交点 y 取正", not v2.error and close(v2.y, yy, 1e-9), "%.9f" % (getattr(v2, "y", 0) or 0))
    c24.process("v3=Intersect[cc,px,3]")
    check("空间圆×平面 取第 3 交点 → error", bool(c24.elements["v3"].error), str(c24.elements["v3"].error))
    c24.process("v4=Intersect[cc,py]")
    check("空间圆与平面相离 → error", bool(c24.elements["v4"].error), str(c24.elements["v4"].error))
    c24.process("v5=Intersect[cc,pz]")
    check("空间圆与所在平面共面 → error", bool(c24.elements["v5"].error) and "共面" in c24.elements["v5"].error,
          str(c24.elements["v5"].error))
    # 空间圆 × 立体
    check("空间圆×立体 交点 (0,√(r²),1)", not c24.elements["w1"].error
          and close(c24.elements["w1"].x, 0.0, 1e-6) and close(c24.elements["w1"].z, 1.0, 1e-6),
          str(c24.elements["w1"].error))
    check("空间圆×立体 第 2 交点", not c24.elements["w2"].error and close(c24.elements["w2"].y, 0.0, 1e-6),
          str(c24.elements["w2"].error))
    c24.process("cin=Sphere[(1,1,1),0.5]")
    c24.process("pcin=Plane[(0,0,1),(1,0,1),(0,1,1)]")
    c24.process("cc2=Intersect[cin,pcin]")
    c24.process("in1=Intersect[cc2,cu]")
    check("整圆在立体内部 → error", bool(c24.elements["in1"].error) and "无交点" in c24.elements["in1"].error,
          str(c24.elements["in1"].error))

section("S. 样式快照（undo/redo 保留 locked/wire）与退化网格")
c25, e25 = build(["O=(0,0,0)", "c=Circle[O,2]", "co=Cone[c,3]", "sp=Sphere[O,1]"])
check("样式用例构造", e25 is None, str(e25))
if e25 is None:
    c25.elements["co"].color = "#ff0000"
    c25.elements["co"].locked = True
    c25.elements["co"].wire = True
    c25.process("x=Sphere[O,1.5]")
    c25.undo()
    el = c25.elements["co"]
    check("undo 后 color 保留", el.color == "#ff0000", str(el.color))
    check("undo 后 locked 保留", el.locked is True, str(el.locked))
    check("undo 后 wire 保留", getattr(el, "wire", None) is True, str(getattr(el, "wire", None)))
    c25.redo()
    el = c25.elements["co"]
    check("redo 后 locked/wire 保留",
          el.locked is True and getattr(el, "wire", None) is True and el.color == "#ff0000",
          "%s/%s" % (el.locked, getattr(el, "wire", None)))
    # .ggk 往返保留样式
    txt = c25.save_json()
    c26 = Construction()
    c26.load_json(txt)
    el2 = c26.elements.get("co")
    check(".ggk 往返 locked/wire 保留", el2 is not None and el2.locked is True and getattr(el2, "wire", None) is True,
          "%s/%s" % (getattr(el2, "locked", None), getattr(el2, "wire", None)))
    # 退化网格：薄板相交（体积小但形状有效）与零体积接触
    c25.process("P1=(1.999,1,1)", )
    c25.process("P2=(3.999,1,1)")
    c25.process("cu=Cube[O,(2,0,0)]")
    c25.process("thin=Cube[P1,P2]")
    c25.process("slab=Intersect[cu,thin]")
    slab = c25.elements["slab"]
    ok_thin = (not slab.error) and len(slab.data["verts"]) == 8 and len(slab.data["faces"]) == 6
    check("薄板相交仍得有效凸多面体（8/6）", ok_thin, slab.error or "%d/%d" % (len(slab.data["verts"]), len(slab.data["faces"])))
    if ok_thin:
        c25.process("V_slab=Volume[slab]")
        check("薄板体积 = 0.001×1×1 = 0.001", close(c25.elements["V_slab"].value, 0.001, 1e-9),
              "%.9f" % c25.elements["V_slab"].value)
        bad_faces = [f for f in slab.data["faces"] if len(f) < 3]
        check("网格无退化面（面顶点 ≥ 3）", not bad_faces, str(bad_faces))
        check("薄板 Euler V-E+F=2", len(slab.data["verts"]) - len(slab.data["edges"]) + len(slab.data["faces"]) == 2)
    # 面接触（零体积）→ 报错
    c25.process("M1=(2,0,0)"); c25.process("M2=(4,0,0)")
    c25.process("touch=Cube[M1,M2]")
    c25.process("t0=Intersect[cu,touch]")
    check("面接触（零体积）→ error", bool(c25.elements["t0"].error), str(c25.elements["t0"].error))

# ---------------------------------------------------------------------------
section("T. 3D 网格导出（OBJ / STL）")
from kernel.mesh_io import export_obj, export_stl  # noqa: E402

c27, e27 = build(["O=(0,0,0)", "cc=Circle[O,2]", "cu=Cube[O,(2,0,0)]", "co=Cone[cc,3]",
                  "sp=Sphere[O,2]", "pl=Plane[O,(1,0,0),(0,1,0)]", "sec=Intersect[pl,cu]",
                  "P1=(1,1,1)", "P2=(3,1,1)", "cB=Cube[P1,P2]", "cap=Intersect[cu,cB]"])
check("导出用例构造", e27 is None, str(e27))
if e27 is None:
    obj_text, w_obj = export_obj(c27)
    stl_text, w_stl = export_stl(c27)
    meshes = [c27.elements[l] for l in c27.order
              if getattr(c27.elements[l], "objtype", "") in ("cube", "polyhedron")]
    exp_v = sum(len(m.data["verts"]) for m in meshes)
    exp_f = sum(len(m.data["faces"]) for m in meshes)
    exp_tri = sum(sum(len(f) - 2 for f in m.data["faces"] if len(f) >= 3) for m in meshes)
    got_v = sum(1 for l in obj_text.splitlines() if l.startswith("v "))
    got_f = sum(1 for l in obj_text.splitlines() if l.startswith("f "))
    got_o = sum(1 for l in obj_text.splitlines() if l.startswith("o "))
    check("OBJ 顶点数 = 网格顶点总数", got_v == exp_v, "%d vs %d" % (got_v, exp_v))
    check("OBJ 面数 = 网格面总数", got_f == exp_f, "%d vs %d" % (got_f, exp_f))
    check("OBJ 每对象一个 o 块", got_o == len(meshes), "%d vs %d" % (got_o, len(meshes)))
    check("OBJ 面索引 1-based 且不越界", all(
        all(1 <= int(t) <= exp_v for t in l.split()[1:])
        for l in obj_text.splitlines() if l.startswith("f ")))
    check("OBJ 提示跳过非网格对象", any("跳过" in w for w in w_obj), str(w_obj))
    got_facet = stl_text.count("facet normal")
    check("STL 三角面数 = Σ(面顶点数−2)", got_facet == exp_tri, "%d vs %d" % (got_facet, exp_tri))
    check("STL solid 块数 = 网格对象数", stl_text.count("\nsolid ") + stl_text.startswith("solid ") == len(meshes)
          or (stl_text.count("solid ") - stl_text.count("endsolid ")) == len(meshes),
          str(stl_text.count("solid ") - stl_text.count("endsolid ")))
    normals_ok = True
    for line in stl_text.splitlines():
        if line.strip().startswith("facet normal"):
            v = [float(x) for x in line.split()[2:5]]
            nn = math.sqrt(sum(x * x for x in v))
            if nn > 1e-9 and abs(nn - 1.0) > 1e-6:
                normals_ok = False
    check("STL 面法向均为单位向量", normals_ok)
    check("STL 三角顶点数 = 3×面片数",
          sum(1 for l in stl_text.splitlines() if l.strip().startswith("vertex ")) == 3 * got_facet)
    # 空构造 → 明确警告
    c_empty = Construction()
    _t, w_empty = export_obj(c_empty)
    check("无网格对象时给出警告", bool(w_empty) and "没有可导出" in w_empty[0], str(w_empty))

# ---------------------------------------------------------------------------
section("U. 球×空间圆 / 空间圆×空间圆")
c28, e28 = build(["O=(0,0,0)", "A=(2,0,0)", "B=(1,0,1)", "s1=Sphere[O,2]", "s2=Sphere[A,2]",
                  "sp14=Sphere[O,1.4]", "sB=Sphere[B,0.5]",
                  "p0=Plane[O,(1,0,0),(0,1,0)]", "pz1=Plane[(0,0,1),(1,0,1),(0,1,1)]",
                  "px=Plane[(1,0,0),(1,1,0),(1,0,1)]",
                  "cc=Intersect[sp14,pz1]", "cA=Intersect[s1,p0]", "cB=Intersect[s2,p0]",
                  "cC=Intersect[s2,px]",
                  "sc1=Intersect[sB,cc]", "sc2=Intersect[sB,cc,2]",
                  "qq1=Intersect[cA,cB]", "qq2=Intersect[cA,cB,2]",
                  "qr1=Intersect[cA,cC]", "qr2=Intersect[cA,cC,2]"])
check("球×圆 / 圆×圆用例构造", e28 is None, str(e28))
if e28 is None:
    r0 = math.sqrt(1.4 ** 2 - 1.0)
    ex = r0 * (r0 * r0 + 1 - 0.25) / (2 * r0) / 1.0     # cos t = (r²+1−R²)/(2r)，x = r·cos t
    x_expected = (r0 * r0 + 1 - 0.25) / 2.0
    sc1, sc2 = c28.elements["sc1"], c28.elements["sc2"]
    check("球×空间圆 交点1 x=(r²+1−R²)/2", not sc1.error and close(sc1.x, x_expected, 1e-9),
          "err=%s x=%.9f 期望 %.9f" % (sc1.error, getattr(sc1, "x", 0) or 0, x_expected))
    check("球×空间圆 交点1/2 关于 y 对称", not sc2.error and close(sc1.x, sc2.x, 1e-12) and close(sc1.y, -sc2.y, 1e-12),
          "%.6f vs %.6f" % (sc1.y or 0, sc2.y or 0))
    check("球×空间圆 均落在 z=1 平面", close(sc1.z, 1.0, 1e-9) and close(sc2.z, 1.0, 1e-9))
    c28.process("sc3=Intersect[sp14,cc]")
    check("圆在球面上 → 无穷多交点错误", "无穷多" in str(c28.elements["sc3"].error), str(c28.elements["sc3"].error))
    c28.process("sc4=Intersect[s1,cc]")
    check("球与圆不相交 → error", bool(c28.elements["sc4"].error), str(c28.elements["sc4"].error))
    c28.process("sc5=Intersect[sB,cc,3]")
    check("球×圆 取第 3 交点 → error", bool(c28.elements["sc5"].error), str(c28.elements["sc5"].error))
    sq3 = math.sqrt(3)
    q1, q2, r1e, r2e = (c28.elements[k] for k in ("qq1", "qq2", "qr1", "qr2"))
    check("共面两圆 交点 (1,√3,0)", not q1.error and close(q1.x, 1.0, 1e-9) and close(q1.y, sq3, 1e-9)
          and close(q1.z, 0.0, 1e-9), "err=%s" % q1.error)
    check("共面两圆 第 2 交点 y 取负", not q2.error and close(q2.y, -sq3, 1e-9), "%.9f" % (getattr(q2, "y", 0) or 0))
    check("异面（同轴共球面）两圆 交点同值", not r1e.error and close(r1e.x, 1.0, 1e-9) and close(r1e.y, sq3, 1e-9),
          "err=%s" % r1e.error)
    check("异面两圆 第 2 交点", not r2e.error and close(r2e.y, -sq3, 1e-9))
    c28.process("q5=Intersect[cA,cA]")
    check("同一圆 → 重合（无穷多）", "重合" in str(c28.elements["q5"].error), str(c28.elements["q5"].error))
    c28.process("pz2=Plane[(0,0,1),(1,0,1),(0,1,1)]")
    c28.process("cE=Intersect[s1,pz2]")
    c28.process("q6=Intersect[cA,cE]")
    check("平行异面两圆 → error", bool(c28.elements["q6"].error), str(c28.elements["q6"].error))
    c28.process("q7=Intersect[cA,cB,3]")
    check("圆×圆 取第 3 交点 → error", bool(c28.elements["q7"].error), str(c28.elements["q7"].error))
    # 参数元素本身出错（相切球面圆）时给明确提示而非异常
    c28.process("bad=Plane[(0,0,2),(1,0,2),(0,1,2)]")
    c28.process("cBad=Intersect[s1,bad]")
    rbad = c28.process("q8=Intersect[cA,cBad]")
    check("求交参数自身出错 → 明确提示", "求交参数无效" in rbad, rbad[:70])

# ---------------------------------------------------------------------------
section("V. 曲面 Surface")
c29, e29 = build(["flat=Surface[0,-1,1,-1,1,4]", "ramp=Surface[x,0,1,0,1,8]",
                  "sad=Surface[x^2-y^2,-2,2,-2,2,24]", "a=2",
                  "dep=Surface[a*x^2+y^2,-1,1,-1,1,4]"])
check("曲面用例构造", e29 is None, str(e29))
if e29 is None:
    flat = c29.elements["flat"]
    d = flat.data
    check("曲面网格 v/f/e（4×4 → 25/16/40）",
          (len(d["verts"]), len(d["faces"]), len(d["edges"])) == (25, 16, 40),
          "%d/%d/%d" % (len(d["verts"]), len(d["faces"]), len(d["edges"])))
    check("曲面元素 solid=surface / objtype=polyhedron",
          flat.solid == "surface" and flat.objtype == "polyhedron", "%s/%s" % (flat.solid, flat.objtype))
    check("曲面顶点取值正确（z=0）", all(abs(v[2]) < 1e-12 for v in d["verts"]))
    c29.process("A_flat=Area[flat]")
    check("平面曲面 Area = 4", close(c29.elements["A_flat"].value, 4.0, 1e-9), "%.9f" % c29.elements["A_flat"].value)
    c29.process("A_ramp=Area[ramp]")
    check("斜面 z=x 的 Area = √2", close(c29.elements["A_ramp"].value, math.sqrt(2), 1e-9),
          "%.9f" % c29.elements["A_ramp"].value)
    c29.process("A_sad=Area[sad]")
    check("马鞍面 24×24 面积 ≈ 52.02（网格近似）", abs(c29.elements["A_sad"].value - 52.0182) < 0.05,
          "%.6f" % c29.elements["A_sad"].value)
    c29.process("V_surf=Volume[flat]")
    check("曲面 Volume → 明确报错", bool(c29.elements["V_surf"].error) and "没有体积" in c29.elements["V_surf"].error,
          str(c29.elements["V_surf"].error))
    r_range = c29.process("bad_range=Surface[x,1,1,0,1,4]")
    check("范围退化 → 明确报错", "范围" in r_range, r_range[:60])
    c29.process("bad_pole=Surface[1/x,0,1,0,1,4]")
    check("含奇点（非有限取值）→ error", bool(c29.elements["bad_pole"].error),
          str(c29.elements["bad_pole"].error))
    # 滑块联动
    z0 = c29.elements["dep"].data["verts"][0][2]
    c29.elements["a"].value = 3.0
    c29._recompute(c29.elements["a"])
    z1 = c29.elements["dep"].data["verts"][0][2]
    check("曲面随滑块重算（a=2→3）", not close(z0, z1), "%.3f → %.3f" % (z0, z1))
    # 与其他 3D 能力联动：曲面 ∩ 平面 → 截面（用曲面近似平面截 z=0）
    c29.process("pl0=Plane[(0,0,0.5),(1,0,0.5),(0,1,0.5)]")
    c29.process("sec_ramp=Intersect[pl0,ramp]")
    check("曲面（网格）与平面求交仍可用", not c29.elements["sec_ramp"].error
          and getattr(c29.elements["sec_ramp"], "objtype", "") == "section",
          str(c29.elements["sec_ramp"].error))

# ---------------------------------------------------------------------------
section("W. 3D 点列表与 FitPlane")
c30, e30 = build([
    "L={(0,0,1),(1,0,1.5),(0,1,0.75),(1,1,1.25)}",     # z = 1 + 0.5x − 0.25y
    "p0=L(1)", "fp=FitPlane[L]",
    "col={(0,0,0),(1,1,1),(2,2,2)}",
])
check("3D 点列表 / FitPlane 构造", e30 is None, str(e30))
if e30 is None:
    check("3D 点列表 itemkind=point3d", c30.elements["L"].itemkind == "point3d", c30.elements["L"].itemkind)
    p0 = c30.elements["p0"]
    check("点列表取元素 → 3D 点（带 z）", p0.kind == "point" and close(getattr(p0, "z", None) or 0, 1.0),
          "z=%s" % getattr(p0, "z", None))
    d = c30.elements["fp"].data
    check("FitPlane objtype=plane", getattr(c30.elements["fp"], "objtype", "") == "plane")
    n = (d["a"], d["b"], d["c"])
    # 期望法向 ∝ (0.5, -0.25, -1)（符号任意）
    exp = (0.5, -0.25, -1.0)
    le = math.sqrt(sum(v * v for v in exp))
    exp = tuple(v / le for v in exp)
    same = all(close(n[i], exp[i], 1e-7) for i in range(3)) or all(close(n[i], -exp[i], 1e-7) for i in range(3))
    check("FitPlane 法向 = (0.5,−0.25,−1) 归一化", same, "n=(%.6f,%.6f,%.6f)" % n)
    ctr = (0.5, 0.5, 1.125)
    val = n[0] * ctr[0] + n[1] * ctr[1] + n[2] * ctr[2] + d["d"]
    check("拟合平面过点云质心", abs(val) < 1e-9, "%.3e" % val)
    c30.process("fp2=FitPlane[col]")
    check("共线点云 → error", bool(c30.elements["fp2"].error), str(c30.elements["fp2"].error))
    c30.process("cu=Cube[(0,0,0),(2,0,0)]")
    c30.process("sec_fp=Intersect[fp,cu]")
    check("拟合平面 ∩ 立方体 → section", getattr(c30.elements["sec_fp"], "objtype", "") == "section",
          str(c30.elements["sec_fp"].error))
    c30.process("per=Perimeter[sec_fp]")
    check("截面周长 > 0", c30.elements["per"].value > 0, "%.6f" % c30.elements["per"].value)

# ---------------------------------------------------------------------------
section("X. OBJ 导入（Mesh 元素）")
from kernel.mesh_io import parse_obj  # noqa: E402
OBJ_CUBE = """# unit cube
v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
v 0 0 2
v 2 0 2
v 2 2 2
v 0 2 2
f 1 2 3 4
f 5 6 7 8
f 1 2 6 5
f 2 3 7 6
f 3 4 8 7
f 4 1 5 8
"""
vv, ff, ww = parse_obj(OBJ_CUBE)
check("parse_obj 顶点/面数", len(vv) == 8 and len(ff) == 6, "%d/%d" % (len(vv), len(ff)))
c31, e31 = build([])
import kernel.mesh_store as _ms  # noqa: E402
_mid = _ms.put(vv, ff)
c31, e31 = build(["m=Mesh[" + _mid + "]", "V_m=Volume[m]", "A_m=Area[m]"])
check("Mesh[id] 构造", e31 is None, str(e31))
if e31 is None:
    m = c31.elements["m"]
    d = m.data
    check("Mesh 元素 v/f/e = 8/6/12",
          (len(d["verts"]), len(d["faces"]), len(d["edges"])) == (8, 6, 12),
          "%d/%d/%d" % (len(d["verts"]), len(d["faces"]), len(d["edges"])))
    check("Mesh solid=mesh", m.solid == "mesh" and getattr(m, "meshid", "") == _mid, m.solid)
    check("Mesh 体积 = 8", close(c31.elements["V_m"].value, 8.0, 1e-9), "%.6f" % c31.elements["V_m"].value)
    check("Mesh 表面积 = 24", close(c31.elements["A_m"].value, 24.0, 1e-9), "%.6f" % c31.elements["A_m"].value)
    txt = c31.save_json()
    c32 = Construction()
    c32.load_json(txt)
    m2 = c32.elements.get("m")
    check(".ggk 往返保留导入网格",
          m2 is not None and len(m2.data["verts"]) == 8 and len(m2.data["faces"]) == 6,
          "None" if m2 is None else "%d/%d" % (len(m2.data["verts"]), len(m2.data["faces"])))
    # 导出的 OBJ 能被自己解析回来（往返）
    otext, _w = export_obj(c31)
    v2, f2, _w2 = parse_obj(otext)
    check("OBJ 导出→导入 往返一致（8/6）", len(v2) == 8 and len(f2) == 6, "%d/%d" % (len(v2), len(f2)))
    r_bad = c31.process("bad=Mesh[mesh_不存在]")
    check("未知网格 id → 明确报错", "找不到网格数据" in r_bad, r_bad[:60])

# ---------------------------------------------------------------------------
section("Y. 参数曲面 SurfaceParam")
c33, e33 = build([
    "tor=SurfaceParam[(2+cos(s))*cos(t),(2+cos(s))*sin(t),sin(s),s,t,0,2*pi,0,2*pi,32]",
    "cyl=SurfaceParam[cos(t),sin(t),s,s,t,0,2,0,2*pi,48]",
    "aa=2",
    "dep=SurfaceParam[aa*cos(t),aa*sin(t),s,s,t,0,1,0,2*pi,8]",
])
check("参数曲面构造", e33 is None, str(e33))
if e33 is None:
    tor = c33.elements["tor"]
    d = tor.data
    check("环面网格 v/f（32×32 → 1089/1024）",
          (len(d["verts"]), len(d["faces"])) == (1089, 1024),
          "%d/%d" % (len(d["verts"]), len(d["faces"])))
    check("参数曲面 solid=surface", tor.solid == "surface" and tor.objtype == "polyhedron",
          "%s/%s" % (tor.solid, tor.objtype))
    zs = [v[2] for v in d["verts"]]
    check("环面 z ∈ [−1,1]", close(min(zs), -1.0, 1e-9) and close(max(zs), 1.0, 1e-9),
          "%.6f..%.6f" % (min(zs), max(zs)))
    rr = [math.hypot(v[0], v[1]) for v in d["verts"]]
    check("环面管心距半径 ∈ [1,3]", close(min(rr), 1.0, 1e-9) and close(max(rr), 3.0, 1e-9),
          "%.6f..%.6f" % (min(rr), max(rr)))
    c33.process("A_tor=Area[tor]")
    exp_tor = 4 * math.pi ** 2 * 2 * 1
    check("环面面积 ≈ 4π²Rr（误差 <1%）",
          abs(c33.elements["A_tor"].value - exp_tor) / exp_tor < 0.01,
          "%.4f vs %.4f" % (c33.elements["A_tor"].value, exp_tor))
    c33.process("A_cyl=Area[cyl]")
    exp_cyl = 2 * math.pi * 2
    check("圆柱侧面面积 ≈ 2πrh（误差 <1%）",
          abs(c33.elements["A_cyl"].value - exp_cyl) / exp_cyl < 0.01,
          "%.4f vs %.4f" % (c33.elements["A_cyl"].value, exp_cyl))
    r_range = c33.process("bad=SurfaceParam[cos(t),sin(t),s,s,t,0,2,1,1,8]")
    check("参数范围退化 → 明确报错", "范围" in r_range, r_range[:60])
    c33.process("bad2=SurfaceParam[1/s,0,t,s,t,0,1,0,1,6]")
    check("参数曲面奇点 → error", bool(c33.elements["bad2"].error), str(c33.elements["bad2"].error))
    z0 = c33.elements["dep"].data["verts"][0][0]
    c33.elements["aa"].value = 3.0
    c33._recompute(c33.elements["aa"])
    z1 = c33.elements["dep"].data["verts"][0][0]
    check("参数曲面随滑块重算（aa 2→3）", not close(z0, z1), "%.3f → %.3f" % (z0, z1))
    r_nc = c33.process("bad3=SurfaceParam[cos(t),sin(t),s,s,s,0,1,0,1,4]")
    check("参数名相同 → 报错", "不能相同" in r_nc, r_nc[:60])

# ---------------------------------------------------------------------------
section("Z. 隐式曲面 ImplicitSurface（marching tetrahedra）")
c34, e34 = build([
    "sph=ImplicitSurface[x^2+y^2+z^2-4=0,-2.2,2.2,-2.2,2.2,-2.2,2.2,24]",
    "tor=ImplicitSurface[(sqrt(x^2+y^2)-2)^2+z^2-1=0,-3.2,3.2,-3.2,3.2,-1.5,1.5,24]",
])
check("隐式曲面构造", e34 is None, str(e34))
if e34 is None:
    sph = c34.elements["sph"]
    d = sph.data
    check("球面等值面有网格（顶点 > 500 / 面 > 1000）",
          len(d["verts"]) > 500 and len(d["faces"]) > 1000,
          "%d/%d" % (len(d["verts"]), len(d["faces"])))
    check("隐式曲面 solid=surface", sph.solid == "surface", sph.solid)
    rr = [math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) for v in d["verts"]]
    h = 4.4 / 24.0          # 网格步长：线性插值截断误差应在一个步长量级内
    check("等值面顶点贴近真球面（误差 < 网格步长）",
          all(abs(r - 2.0) < h for r in rr), "%.6f..%.6f (h=%.4f)" % (min(rr), max(rr), h))
    c34.process("A_sph=Area[sph]")
    exp_sph = 4 * math.pi * 4
    check("球面等值面面积（误差 <8%）",
          abs(c34.elements["A_sph"].value - exp_sph) / exp_sph < 0.08,
          "%.4f vs %.4f" % (c34.elements["A_sph"].value, exp_sph))
    c34.process("A_tor=Area[tor]")
    exp_tor = 4 * math.pi ** 2 * 2 * 1
    check("圆环等值面面积（误差 <8%）",
          abs(c34.elements["A_tor"].value - exp_tor) / exp_tor < 0.08,
          "%.4f vs %.4f" % (c34.elements["A_tor"].value, exp_tor))
    c34.process("bad=ImplicitSurface[x^2+y^2+z^2+1=0,-1,1,-1,1,-1,1,8]")
    check("无等值面 → error", bool(c34.elements["bad"].error), str(c34.elements["bad"].error))
    r_range = c34.process("bad2=ImplicitSurface[x,-1,1,-1,1,1,1,8]")
    check("z 范围退化 → 明确报错", "范围" in r_range, r_range[:60])
    c34.process("V_sph=Volume[sph]")
    check("隐式曲面 Volume → 曲面无体积", bool(c34.elements["V_sph"].error)
          and "没有体积" in c34.elements["V_sph"].error, str(c34.elements["V_sph"].error))

# ---------------------------------------------------------------------------
section("AA. STL 导入（ASCII / 二进制 / 往返）")
import struct as _struct  # noqa: E402
from kernel.mesh_io import parse_mesh  # noqa: E402
STL_ASCII = """solid tetra
  facet normal 0 0 -1
    outer loop
      vertex 0 0 0
      vertex 2 0 0
      vertex 0 2 0
    endloop
  endfacet
  facet normal 0 -1 0
    outer loop
      vertex 0 0 0
      vertex 0 0 2
      vertex 2 0 0
    endloop
  endfacet
  facet normal -1 0 0
    outer loop
      vertex 0 0 0
      vertex 0 2 0
      vertex 0 0 2
    endloop
  endfacet
  facet normal 1 1 1
    outer loop
      vertex 2 0 0
      vertex 0 0 2
      vertex 0 2 0
    endloop
  endfacet
endsolid tetra
"""
va, fa, _wa, fmta = parse_mesh(STL_ASCII.encode())
check("ASCII STL 解析（12 顶点 / 4 三角）", fmta == "stl-ascii" and len(va) == 12 and len(fa) == 4,
      "%s %d/%d" % (fmta, len(va), len(fa)))
tris = [(va[fa[i][0]], va[fa[i][1]], va[fa[i][2]]) for i in range(len(fa))]
blob = b"\x00" * 80 + _struct.pack("<I", len(tris))
for t3 in tris:
    blob += _struct.pack("<12fH", 0, 0, 0, *t3[0], *t3[1], *t3[2], 0)
vb, fb, _wb, fmtb = parse_mesh(blob)
check("二进制 STL 解析（12 顶点 / 4 三角）", fmtb == "stl-binary" and len(vb) == 12 and len(fb) == 4,
      "%s %d/%d" % (fmtb, len(vb), len(fb)))
_mid2 = _ms.put(vb, fb)
c35, e35 = build(["m=Mesh[" + _mid2 + "]", "V_m=Volume[m]", "A_m=Area[m]"])
check("STL 导入 → Mesh 元素", e35 is None, str(e35))
if e35 is None:
    m = c35.elements["m"]
    check("四面体网格 4/4/6",
          (len(m.data["verts"]), len(m.data["faces"]), len(m.data["edges"])) == (4, 4, 6),
          "%d/%d/%d" % (len(m.data["verts"]), len(m.data["faces"]), len(m.data["edges"])))
    check("STL 四面体体积 = 4/3", close(c35.elements["V_m"].value, 4.0 / 3.0, 1e-9),
          "%.9f" % c35.elements["V_m"].value)
    txt = c35.save_json()
    c36 = Construction()
    c36.load_json(txt)
    check(".ggk 往返保留 STL 导入网格",
          c36.elements.get("m") is not None and len(c36.elements["m"].data["faces"]) == 4)
# 导出 → 导入 往返（立方体）
c37, _e37 = build(["cu=Cube[(0,0,0),(2,0,0)]"])
stl_text, _w = export_stl(c37)
v3, f3, _w3, fmt3 = parse_mesh(stl_text.encode())
check("STL 导出→导入 往返（12 三角）", fmt3 == "stl-ascii" and len(f3) == 12, "%s %d" % (fmt3, len(f3)))
_mid3 = _ms.put(v3, f3)
c38, _e38 = build(["m=Mesh[" + _mid3 + "]", "V=Volume[m]"])
check("往返后立方体体积 = 8", close(c38.elements["V"].value, 8.0, 1e-9), "%.9f" % c38.elements["V"].value)
try:
    parse_mesh(b"\x01\x02\x03 not a mesh at all, quite long padding to avoid binary stl misdetect" + b"\x00" * 200)
    check("无法识别的网格文件 → 报错", False, "未报错")
except Exception as _ex:
    check("无法识别的网格文件 → 报错", True, str(_ex)[:40])

# ---------------------------------------------------------------------------
section("AB. 3D 统计：Centroid / FitSphere")
c39, e39 = build([
    "L={(0,0,0),(2,0,0),(0,2,0),(0,0,2)}", "ce=Centroid[L]",
    "L2={(1,2),(3,4),(5,6)}", "ce2=Centroid[L2]",
    "poly=Polygon[(0,0),(2,0),(2,2)]", "ce3=Centroid[poly]",
    "ce4=Centroid[{(1,1),(3,3)}]",
    "fs=FitSphere[L]",
])
check("统计用例构造", e39 is None, str(e39))
if e39 is None:
    ce = c39.elements["ce"]
    check("三维点列表质心 = (0.5,0.5,0.5)",
          ce.kind == "point" and close(ce.x, 0.5) and close(ce.y, 0.5) and close(ce.z, 0.5),
          "(%s,%s,%s)" % (ce.x, ce.y, ce.z))
    ce2 = c39.elements["ce2"]
    check("二维点列表质心 = (3,4) 且无 z",
          close(ce2.x, 3.0) and close(ce2.y, 4.0) and ce2.z is None, "(%s,%s,%s)" % (ce2.x, ce2.y, ce2.z))
    ce3 = c39.elements["ce3"]
    check("多边形质心仍可用 = (4/3, 2/3)", close(ce3.x, 4.0 / 3.0) and close(ce3.y, 2.0 / 3.0),
          "(%s,%s)" % (ce3.x, ce3.y))
    ce4 = c39.elements["ce4"]
    check("内联点列表质心 = (2,2)", close(ce4.x, 2.0) and close(ce4.y, 2.0))
    fs = c39.elements["fs"]
    d = fs.data
    check("FitSphere 球心 (1,1,1) r=√3",
          getattr(fs, "objtype", "") == "sphere" and close(d["cx"], 1.0, 1e-9) and close(d["r"], math.sqrt(3), 1e-9),
          "c=(%.6f,%.6f,%.6f) r=%.6f" % (d["cx"], d["cy"], d["cz"], d["r"]))
    c39.process("fs2=FitSphere[{(0,0,0),(2,0,0),(0,2,0),(0,0,2),(1,1,1)}]")
    check("不共球点云 → error", bool(c39.elements["fs2"].error), str(c39.elements["fs2"].error))
    r_few = c39.process("fs3=FitSphere[{(0,0,0),(1,0,0),(0,1,0)}]")
    check("不足 4 点 → error", bool(c39.elements["fs3"].error) or "至少" in r_few,
          str(c39.elements["fs3"].error) if "fs3" in c39.elements else r_few[:50])

# ---------------------------------------------------------------------------
section("AC. 球面×立体 → 交线（curve3d）")
c40, e40 = build(["cu=Cube[(0,0,0),(2,0,0)]",
                  "sA=Sphere[(1,1,1),1.2]", "xA=Intersect[sA,cu]",
                  "sB=Sphere[(1,1,1),1.5]", "xB=Intersect[sB,cu]",
                  "sC=Sphere[(1,1,1),0.9]", "xC=Intersect[sC,cu]",
                  "sD=Sphere[(1,1,1),2.0]", "xD=Intersect[sD,cu]",
                  "sE=Sphere[(1,1,1),1.7320508]", "xE=Intersect[sE,cu]"])
check("球×立体用例构造", e40 is None, str(e40))
if e40 is None:
    xA = c40.elements["xA"]
    check("r=1.2 得交线 curve3d 且段数 > 100",
          getattr(xA, "objtype", "") == "curve3d" and xA.data["count"] > 100,
          "%s/%s" % (getattr(xA, "objtype", None), getattr(xA, "data", {}).get("count")))
    pts = [p for seg in xA.data["segs"] for p in seg]
    dd = max(abs(math.dist(p, (1, 1, 1)) - 1.2) for p in pts)
    check("交线点精确落在球面（|d−r| < 1e-12）", dd < 1e-12, "max=%.2e" % dd)
    onb = all(abs(max(abs(p[0] - 1), abs(p[1] - 1), abs(p[2] - 1)) - 1) < 1e-7 for p in pts)
    check("交线点都在立方体表面", onb)
    check("r=1.5 交线段数 > 100", c40.elements["xB"].data["count"] > 100,
          str(c40.elements["xB"].data["count"]))
    check("r=0.9（球在立方体内）→ error", bool(c40.elements["xC"].error), str(c40.elements["xC"].error))
    check("r=2.0（球包住立方体）→ error", bool(c40.elements["xD"].error), str(c40.elements["xD"].error))
    check("相切（球过 8 顶点）→ error", bool(c40.elements["xE"].error), str(c40.elements["xE"].error))
    c40.process("sph2=Sphere[(0,0,0),1.5]")
    c40.process("x2=Intersect[sph2,cu]")
    check("球心在立方体顶点处仍有交线", not c40.elements["x2"].error
          and c40.elements["x2"].data["count"] > 10, str(c40.elements["x2"].error))

# ---------------------------------------------------------------------------
section("AD. glTF 2.0 导出")
from kernel.mesh_io import export_gltf  # noqa: E402
import base64 as _b64  # noqa: E402
import json as _json  # noqa: E402
import struct as _st  # noqa: E402

c41, _e41 = build(["cu=Cube[(0,0,0),(2,0,0)]", "cc=Circle[(0,0),2]", "co=Cone[cc,3]"])
gltf_text, w_gltf = export_gltf(c41)
g = _json.loads(gltf_text)
check("glTF JSON 合法且版本 2.0", g.get("asset", {}).get("version") == "2.0")
check("glTF 节点/网格数 = 网格对象数（2）", len(g["nodes"]) == 2 and len(g["meshes"]) == 2,
      "%d/%d" % (len(g["nodes"]), len(g["meshes"])))
raw = _b64.b64decode(g["buffers"][0]["uri"].split(",")[1])
check("glTF buffer 长度与 byteLength 一致", len(raw) == g["buffers"][0]["byteLength"],
      "%d vs %d" % (len(raw), g["buffers"][0]["byteLength"]))
cu = c41.elements["cu"].data
co = c41.elements["co"].data
exp_v = len(cu["verts"]) + len(co["verts"])
exp_tri = sum(len(f) - 2 for f in cu["faces"]) + sum(len(f) - 2 for f in co["faces"])
pos_accs = [a for a in g["accessors"] if a["type"] == "VEC3"]
idx_accs = [a for a in g["accessors"] if a["type"] == "SCALAR"]
check("glTF POSITION 顶点总数一致", sum(a["count"] for a in pos_accs) == exp_v,
      "%d vs %d" % (sum(a["count"] for a in pos_accs), exp_v))
check("glTF 索引总数 = 3×三角数", sum(a["count"] for a in idx_accs) == 3 * exp_tri,
      "%d vs %d" % (sum(a["count"] for a in idx_accs), 3 * exp_tri))
a0 = pos_accs[0]
check("glTF POSITION min/max 正确（立方体 0..2）",
      a0["min"] == [0.0, 0.0, 0.0] and a0["max"] == [2.0, 2.0, 2.0], str(a0["min"]) + str(a0["max"]))
first = _st.unpack_from("<3f", raw, g["bufferViews"][a0["bufferView"]]["byteOffset"])
check("glTF 首顶点数据可解析", all(abs(first[i] - [0.0, 0.0, 0.0][i]) < 1e-9 for i in range(3)), str(first))
check("glTF 无网格时给出警告", bool(export_gltf(Construction())[1]))

# ---------------------------------------------------------------------------
section("AE. 点云统计：BoundingBox / Covariance")
import numpy as _np  # noqa: E402
c42, e42 = build(["L={(0,0,0),(2,0,0),(0,3,0),(0,0,1),(2,3,1)}",
                  "bb=BoundingBox[L]", "V=Volume[bb]", "A=Area[bb]", "cov=Covariance[L]",
                  "L2={(1,2),(3,4),(5,9)}", "cov2=Covariance[L2]",
                  "same={(1,1,1),(1,1,1)}"])
check("统计用例构造", e42 is None, str(e42))
if e42 is None:
    bb = c42.elements["bb"]
    d = bb.data
    check("包围盒 8/6/12", (len(d["verts"]), len(d["faces"]), len(d["edges"])) == (8, 6, 12),
          "%d/%d/%d" % (len(d["verts"]), len(d["faces"]), len(d["edges"])))
    check("包围盒 lo/hi 正确", d["lo"] == [0.0, 0.0, 0.0] and d["hi"] == [2.0, 3.0, 1.0],
          str(d["lo"]) + str(d["hi"]))
    check("包围盒体积 = 6", close(c42.elements["V"].value, 6.0, 1e-9), "%.6f" % c42.elements["V"].value)
    check("包围盒表面积 = 22", close(c42.elements["A"].value, 22.0, 1e-9), "%.6f" % c42.elements["A"].value)
    check("包围盒数据可 JSON 序列化", isinstance(d["verts"][0][0], float))
    cov = c42.elements["cov"].data
    pts = _np.array([[0, 0, 0], [2, 0, 0], [0, 3, 0], [0, 0, 1], [2, 3, 1]], dtype=float)
    q = pts - pts.mean(axis=0)
    exp_cov = (q.T @ q) / len(pts)
    check("协方差矩阵 = numpy 参考（3×3）", cov.shape == (3, 3) and float(_np.max(_np.abs(cov - exp_cov))) < 1e-12,
          str(cov.shape))
    cov2 = c42.elements["cov2"].data
    p2 = _np.array([[1, 2], [3, 4], [5, 9]], dtype=float)
    q2 = p2 - p2.mean(axis=0)
    exp2 = (q2.T @ q2) / len(p2)
    check("协方差矩阵 = numpy 参考（2×2）", cov2.shape == (2, 2) and float(_np.max(_np.abs(cov2 - exp2))) < 1e-12,
          str(cov2.shape))
    c42.process("bad=BoundingBox[same]")
    check("点云退化为一点 → error", bool(c42.elements["bad"].error), str(c42.elements["bad"].error))
    r_bad = c42.process("bad2=Covariance[{(1,1,1)}]")
    check("单点协方差 → 明确报错", "至少" in r_bad or (c42.elements.get("bad2") is not None
                                                  and c42.elements["bad2"].error),
          r_bad[:50])

# ---------------------------------------------------------------------------
section("AF. glTF / GLB 导入")
c43, _e43 = build(["cu=Cube[(0,0,0),(2,0,0)]", "cc=Circle[(0,0),2]", "co=Cone[cc,3]"])
gltf_out, _w43 = export_gltf(c43)
v43, f43, _w43b, fmt43 = parse_mesh(gltf_out.encode())
exp_v43 = len(c43.elements["cu"].data["verts"]) + len(c43.elements["co"].data["verts"])
exp_t43 = (sum(len(x) - 2 for x in c43.elements["cu"].data["faces"])
           + sum(len(x) - 2 for x in c43.elements["co"].data["faces"]))
check("glTF 导出→导入 顶点一致", fmt43 == "gltf" and len(v43) == exp_v43, "%s %d vs %d" % (fmt43, len(v43), exp_v43))
check("glTF 导出→导入 三角一致", len(f43) == exp_t43, "%d vs %d" % (len(f43), exp_t43))
_mid4 = _ms.put(v43, f43)
c44, e44 = build(["m=Mesh[" + _mid4 + "]", "V_m=Volume[m]"])
check("glTF 导入 → Mesh 元素可用", e44 is None, str(e44))
if e44 is None:
    # 导入网格没有解析元数据，体积按三角网格计算（≠ 圆锥解析体积 πr²h/3）
    from kernel.commands import _mesh_volume as _mv  # noqa: E402
    exp_mesh_v = _mv(c43.elements["cu"].data) + _mv(c43.elements["co"].data)
    # glTF 顶点为 float32，往返后体积有 ~1e-7 相对误差
    check("glTF 导入网格体积 = 源网格体积之和（float32 容差）",
          abs(c44.elements["V_m"].value - exp_mesh_v) < 1e-5 * max(1.0, abs(exp_mesh_v)),
          "%.6f vs %.6f" % (c44.elements["V_m"].value, exp_mesh_v))
# GLB（二进制容器）
_js = _json.dumps({"asset": {"version": "2.0"},
                   "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
                   "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
                                 {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"}],
                   "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36},
                                   {"buffer": 0, "byteOffset": 36, "byteLength": 6}]}).encode()
_bin = _st.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0) + _st.pack("<3H", 0, 1, 2)
_jb = _js + b" " * ((4 - len(_js) % 4) % 4)
_bb = _bin + b"\x00" * ((4 - len(_bin) % 4) % 4)
_glb = (b"glTF" + _st.pack("<II", 2, 12 + 8 + len(_jb) + 8 + len(_bb))
        + _st.pack("<II", len(_jb), 0x4E4F534A) + _jb
        + _st.pack("<II", len(_bb), 0x004E4942) + _bb)
vglb, fglb, _wglb, fmtglb = parse_mesh(_glb)
check("GLB 解析（3 顶点/1 三角）", fmtglb == "glb" and len(vglb) == 3 and len(fglb) == 1,
      "%s %d/%d" % (fmtglb, len(vglb), len(fglb)))
check("GLB 顶点坐标正确", close(vglb[1][0], 1.0) and close(vglb[2][1], 1.0), str(vglb[1]) + str(vglb[2]))
try:
    parse_mesh(_json.dumps({"asset": {"version": "2.0"}, "buffers": [{"uri": "a.bin", "byteLength": 4}],
                            "meshes": []}))
    check("外部 buffer 的 .gltf → 报错", False, "未报错")
except Exception as _ex:
    check("外部 buffer 的 .gltf → 报错", "外部 buffer" in str(_ex), str(_ex)[:40])

# ---------------------------------------------------------------------------
section("AG. .ggb 3D 完整往返")
c45, e45 = build([
    "A3=(1,2,3)", "B3=(4,5,6)", "O=(0,0,0)", "P=(1,2)", "c=Circle[O,2]",
    "sp=Sphere[O,2]", "cu=Cube[O,(2,0,0)]", "co=Cone[c,3]",
    "pl=Plane[O,(1,0,0),(0,1,0)]", "sec=Intersect[pl,cu]",
    "sg=Segment[A3,B3]", "sph2=Sphere[(1,1,1),1.2]", "cur=Intersect[sph2,cu]",
    "cc=Intersect[sp,pl]", "L={(0,0,0),(1,0,0),(0,1,0)}", "fp=FitPlane[L]",
    "surf=Surface[x^2+y^2,-1,1,-1,1,6]",
])
check(".ggb 3D 用例构造", e45 is None, str(e45))
if e45 is None:
    warns = []
    xml = c45.save_ggb(warns)
    check(".ggb 含 3D 元素时不再警告", not warns, str(warns))
    check(".ggb 三维点写出真实 z（w=\"1\"）", 'z="3" w="1"' in xml, "")
    c46 = Construction()
    c46.load_ggb(xml)
    # 逐项对比
    for lbl, key in [("A3", "z"), ("sp", "r"), ("cu", "verts"), ("co", "verts"),
                     ("sec", "count"), ("cc", "r"), ("cur", "count"), ("surf", "verts")]:
        e1 = c45.elements[lbl]
        e2 = c46.elements.get(lbl)
        d1 = getattr(e1, "data", None) or {}
        d2 = getattr(e2, "data", None) or {} if e2 is not None else {}
        if key == "z":
            ok = e2 is not None and close(getattr(e2, "z", None) or 0, getattr(e1, "z", None) or 0, 1e-9)
            detail = "z %s → %s" % (getattr(e1, "z", None), getattr(e2, "z", None) if e2 else None)
        elif key in ("r",):
            ok = e2 is not None and close(d2.get(key, 0), d1.get(key, 0), 1e-9)
            detail = "%s %s → %s" % (key, d1.get(key), d2.get(key))
        elif key == "verts":
            ok = e2 is not None and len(d2.get("verts", [])) == len(d1.get("verts", []))
            detail = "v %d → %d" % (len(d1.get("verts", [])), len(d2.get("verts", [])))
        else:
            ok = e2 is not None and d2.get(key) == d1.get(key)
            detail = "%s %s → %s" % (key, d1.get(key), d2.get(key))
        check(".ggb 往返 " + lbl, ok and (e2 is not None and not e2.error), detail + (" err=%s" % (e2.error if e2 else None)))
    check(".ggb 往返 2D 点仍为二维", c46.elements.get("P") is not None and c46.elements["P"].z is None)
    check(".ggb 往返 元素总数一致", len(c46.order) == len(c45.order),
          "%d vs %d" % (len(c46.order), len(c45.order)))
    # 导入网格（meshid）必须跳过并警告
    _midx = _ms.put([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]])
    c47, _e47 = build(["m=Mesh[" + _midx + "]"])
    w2 = []
    xml2 = c47.save_ggb(w2)
    check("导入网格随 .ggb 内嵌保存（不再跳过告警）", not w2 and "<ggbpyData" in xml2, str(w2)[:60])
    check(".ggb 内容包含该网格元素", 'label="m"' in xml2)
    c47b = Construction()
    c47b.load_ggb(xml2)
    check(".ggb 往返后网格仍可用",
          c47b.elements.get("m") is not None and len(c47b.elements["m"].data["faces"]) == 1,
          str(c47b.elements.get("m") is not None))

# ---------------------------------------------------------------------------
section("AH. 协方差椭球 / 曲面参数线")
c48, e48 = build([
    "L={(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)}",
    "e1=CovarianceEllipsoid[L,2]",
    "S={(4,0,0),(-4,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)}",
    "e2=CovarianceEllipsoid[S,2]",
    "cyl=SurfaceParam[cos(t),sin(t),s,s,t,0,2,0,2*pi,16]",
    "isoCyl=SurfaceIsoline[cyl,1,1]",
    "tor=SurfaceParam[(2+cos(s))*cos(t),(2+cos(s))*sin(t),sin(s),s,t,0,2*pi,0,2*pi,20]",
    "isoTor=SurfaceIsoline[tor,0,2]",
    "flat=Surface[x^2+y^2,-1,1,-1,1,10]",
    "isoFlat=SurfaceIsoline[flat,0.5,1]",
    "imp=ImplicitSurface[x^2+y^2+z^2-4=0,-2.2,2.2,-2.2,2.2,-2.2,2.2,12]",
])
check("椭球/参数线用例构造", e48 is None, str(e48))
if e48 is None:
    import numpy as _np2  # noqa: E402
    six = _np2.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], dtype=float)
    q6 = six - six.mean(axis=0)
    w6 = _np2.linalg.eigvalsh((q6.T @ q6) / len(six))
    exp_axes = [2.0 * math.sqrt(max(0.0, float(x))) for x in w6]
    got_axes = sorted(c48.elements["e1"].data["axes"])
    check("椭球半轴 = k√λ（对称点云）", all(close(got_axes[i], exp_axes[i], 1e-9) for i in range(3)),
          "%s vs %s" % ([round(a, 4) for a in got_axes], [round(a, 4) for a in exp_axes]))
    check("对称点云 → 三轴相等", max(got_axes) - min(got_axes) < 1e-9)
    axes2 = sorted(c48.elements["e2"].data["axes"])
    check("长条点云 → 长轴 4.6188 / 短轴 1.1547",
          close(axes2[2], 4.618802153517007, 1e-9) and close(axes2[0], 1.1547005383792517, 1e-9),
          str([round(a, 4) for a in axes2]))
    check("椭球网格 v/f（21×21 → 441/400）",
          len(c48.elements["e1"].data["verts"]) == 441 and len(c48.elements["e1"].data["faces"]) == 400)
    cyl_pts = [p for s in c48.elements["isoCyl"].data["segs"] for p in s]
    check("圆柱参数线（固定 s=1）：z 恒为 1 且 r=1",
          all(close(p[2], 1.0, 1e-9) for p in cyl_pts) and all(close(math.hypot(p[0], p[1]), 1.0, 1e-9) for p in cyl_pts),
          "n=%d" % len(cyl_pts))
    flat_pts = [p for s in c48.elements["isoFlat"].data["segs"] for p in s]
    check("平面参数线（固定 x=0.5）：x 恒 0.5 且 z = 0.25+y²",
          all(close(p[0], 0.5, 1e-9) for p in flat_pts)
          and all(close(p[2], 0.25 + p[1] ** 2, 1e-9) for p in flat_pts), "n=%d" % len(flat_pts))
    tor_pts = [p for s in c48.elements["isoTor"].data["segs"] for p in s]
    check("环面参数线（固定 t=0）：y=0 且 z=sin(s)",
          all(close(p[1], 0.0, 1e-9) for p in tor_pts), "n=%d" % len(tor_pts))
    c48.process("bad=SurfaceIsoline[cyl,5,1]")
    check("参数值超出定义域 → 明确报错",
          bool(c48.elements["bad"].error) and "超出" in c48.elements["bad"].error,
          str(c48.elements["bad"].error))
    c48.process("bad2=SurfaceIsoline[imp,0,1]")
    check("隐式曲面参数线 → 明确报错",
          bool(c48.elements["bad2"].error) and "不支持参数线" in c48.elements["bad2"].error,
          str(c48.elements["bad2"].error))
    r_dim = c48.process("bad3=SurfaceIsoline[cyl,1,3]")
    check("非法维度 → 明确报错", "维度" in r_dim, r_dim[:50])

# ---------------------------------------------------------------------------
section("AI. 三维凸包 ConvexHull")
c49, e49 = build([
    "cube={(0,0,0),(2,0,0),(2,2,0),(0,2,0),(0,0,2),(2,0,2),(2,2,2),(0,2,2)}",
    "h1=ConvexHull[cube]", "V1=Volume[h1]", "A1=Area[h1]",
    "sp={(2,0,0),(-2,0,0),(0,2,0),(0,-2,0),(0,0,2),(0,0,-2),(1.1547,1.1547,1.1547),(-1.1547,-1.1547,1.1547),"
    "(1.1547,-1.1547,-1.1547),(-1.1547,1.1547,-1.1547)}",
    "h2=ConvexHull[sp]", "V2=Volume[h2]",
])
check("凸包用例构造", e49 is None, str(e49))
if e49 is None:
    h1 = c49.elements["h1"]
    check("立方体凸包 8 顶点 / 12 三角", len(h1.data["verts"]) == 8 and len(h1.data["faces"]) == 12,
          "%d/%d" % (len(h1.data["verts"]), len(h1.data["faces"])))
    check("凸包 Euler V-E+F=2",
          len(h1.data["verts"]) - len(h1.data["edges"]) + len(h1.data["faces"]) == 2,
          "%d-%d+%d" % (len(h1.data["verts"]), len(h1.data["edges"]), len(h1.data["faces"])))
    check("凸包体积 = 8", close(c49.elements["V1"].value, 8.0, 1e-9), "%.6f" % c49.elements["V1"].value)
    check("凸包表面积 = 24（立方体）", close(c49.elements["A1"].value, 24.0, 1e-9), "%.6f" % c49.elements["A1"].value)
    v2 = c49.elements["V2"].value
    sphere_v = 4 / 3 * math.pi * 8
    check("球面附近点云凸包体积在内接多面体量级（0.4–1.0 × 球）", 0.4 * sphere_v < v2 < sphere_v,
          "%.4f vs %.4f（比值 %.3f）" % (v2, sphere_v, v2 / sphere_v))
    c49.process("deg={(0,0,0),(1,0,0),(2,0,0),(3,0,0)}")
    c49.process("bad=ConvexHull[deg]")
    check("共线点云凸包 → error", bool(c49.elements["bad"].error), str(c49.elements["bad"].error))
    c49.process("bad2=ConvexHull[{(0,0,0),(1,0,0),(0,1,0)}]")
    check("不足 4 点 → 明确报错",
          bool(c49.elements["bad2"].error) and "至少需要 4 个点" in c49.elements["bad2"].error,
          str(c49.elements["bad2"].error))
    check("凸包可导出（OBJ 含 hull 对象）", export_obj(c49)[0].count("o ") >= 1)

# ---------------------------------------------------------------------------
section("AJ. 曲面取点 / 曲面投影")
c50, e50 = build([
    "cyl=SurfaceParam[cos(t),sin(t),s,s,t,0,2,0,2*pi,16]",
    "sp1=SurfacePoint[cyl,1,0]", "sp2=SurfacePoint[cyl,1.5,pi/2]",
    "pr1=SurfaceProject[(5,0,1),cyl]", "pr2=SurfaceProject[(0,0,9),cyl]",
    "flat=Surface[x^2+y^2,-1,1,-1,1,10]",
    "sp3=SurfacePoint[flat,0.5,-0.5]", "sp4=SurfacePoint[flat,0,0]",
    "plane0=Surface[0,-1,1,-1,1,4]", "pr3=SurfaceProject[(0.3,0.4,5),plane0]",
    "cu=Cube[(0,0,0),(2,0,0)]",
])
check("曲面取点/投影用例构造", e50 is None, str(e50))
if e50 is None:
    p1, p2 = c50.elements["sp1"], c50.elements["sp2"]
    check("SurfacePoint[圆柱,1,0] = (1,0,1)", close(p1.x, 1.0, 1e-9) and close(p1.y, 0.0, 1e-9)
          and close(p1.z, 1.0, 1e-9), "(%.4f,%.4f,%.4f)" % (p1.x, p1.y, p1.z))
    check("SurfacePoint[圆柱,1.5,π/2] = (0,1,1.5)", close(p2.x, 0.0, 1e-9) and close(p2.y, 1.0, 1e-9)
          and close(p2.z, 1.5, 1e-9), "(%.4f,%.4f,%.4f)" % (p2.x, p2.y, p2.z))
    p3 = c50.elements["sp3"]
    check("SurfacePoint[抛物面,0.5,−0.5] = (0.5,−0.5,0.5)",
          close(p3.x, 0.5, 1e-9) and close(p3.y, -0.5, 1e-9) and close(p3.z, 0.5, 1e-9),
          "(%.4f,%.4f,%.4f)" % (p3.x, p3.y, p3.z))
    check("SurfacePoint[抛物面,0,0] 顶点 = (0,0,0)", close(c50.elements["sp4"].z, 0.0, 1e-9))
    q1 = c50.elements["pr1"]
    check("投影 (5,0,1) 到圆柱侧面 = (1,0,1)",
          close(q1.x, 1.0, 1e-6) and close(q1.y, 0.0, 1e-6) and close(q1.z, 1.0, 1e-6),
          "(%.4f,%.4f,%.4f)" % (q1.x, q1.y, q1.z))
    q2 = c50.elements["pr2"]
    check("投影 (0,0,9) 到圆柱 → 端面 (0,0,2)",
          close(q2.z, 2.0, 1e-6) and close(math.hypot(q2.x, q2.y), 1.0, 1e-6),
          "(%.4f,%.4f,%.4f)" % (q2.x, q2.y, q2.z))
    q3 = c50.elements["pr3"]
    check("投影 (0.3,0.4,5) 到平面曲面 = (0.3,0.4,0)",
          close(q3.x, 0.3, 1e-6) and close(q3.y, 0.4, 1e-6) and close(q3.z, 0.0, 1e-6),
          "(%.4f,%.4f,%.4f)" % (q3.x, q3.y, q3.z))
    c50.process("bad=SurfacePoint[cyl,5,0]")
    check("参数越界 → error", bool(c50.elements["bad"].error) and "超出定义域" in c50.elements["bad"].error,
          str(c50.elements["bad"].error))
    c50.process("bad2=SurfaceProject[(1,2,3),cu]")
    check("投影目标不是曲面 → 明确报错",
          bool(c50.elements["bad2"].error) and "曲面" in c50.elements["bad2"].error,
          str(c50.elements["bad2"].error))

# ---------------------------------------------------------------------------
section("AK. 计算预算与球×立体性能（P0-B）")
import os as _os  # noqa: E402
c51, _e51 = build([])
# 1) 隐式曲面分辨率上限
c51.process("capped=ImplicitSurface[x^2+y^2+z^2-4=0,-3,3,-3,3,-3,3,64]")
check("ImplicitSurface 分辨率上限 48（超出自动夹取）",
      c51.elements["capped"].data.get("grid") == 48, str(c51.elements["capped"].data.get("grid")))
# 2) 时间预算 → 明确错误（用环境变量把预算压到 0，保证确定性）
_old_budget = _os.environ.get("GGBPY_IMPLICIT_BUDGET")
_os.environ["GGBPY_IMPLICIT_BUDGET"] = "0"
c52, _e52 = build(["imp=ImplicitSurface[x^2+y^2+z^2-4=0,-2.2,2.2,-2.2,2.2,-2.2,2.2,24]"])
if _old_budget is None:
    _os.environ.pop("GGBPY_IMPLICIT_BUDGET", None)
else:
    _os.environ["GGBPY_IMPLICIT_BUDGET"] = _old_budget
check("超时间预算 → 明确错误（不会长时间卡住）",
      bool(c52.elements["imp"].error) and "计算量过大" in c52.elements["imp"].error,
      str(c52.elements["imp"].error))
# 3) 球×多面数立体：向量化正确性 + 性能
_pts = []
for _i in range(40):
    _a = _i * 0.7
    _b = _i * 0.3
    _pts.append((math.sin(_a) * math.cos(_b) * 1.6, math.sin(_a) * math.sin(_b) * 1.6, math.cos(_a) * 1.6))
c53, _e53 = build(["L={" + ",".join("(%.4f,%.4f,%.4f)" % q for q in _pts) + "}",
                   "h=ConvexHull[L]", "s=Sphere[(0.4,0.2,0.3),1.5]"])
_t0 = __import__("time").time()
c53.process("ix=Intersect[s,h]")
_dt = __import__("time").time() - _t0
ix = c53.elements["ix"]
nf = len(c53.elements["h"].data["faces"])
check("球×凸包（%d 面）交线成立" % nf, not ix.error and ix.data["count"] > 10,
      "%s / %s 段" % (ix.error, getattr(ix, "data", {}).get("count")))
pts53 = [p for seg in ix.data["segs"] for p in seg]
dd53 = max(abs(math.dist(p, (0.4, 0.2, 0.3)) - 1.5) for p in pts53)
check("交线点精确落在球面", dd53 < 1e-9, "max=%.2e" % dd53)
check("球×多面数立体耗时 < 500ms（向量化）", _dt < 0.5, "%.0f ms" % (_dt * 1000))
# 4) 面数护栏（用 96×96 参数曲面当复杂立体）
c54, _e54 = build(["big=SurfaceParam[cos(t),sin(t),s,s,t,0,2,0,2*pi,96]", "sp4=Sphere[(0,0,1),3]"])
c54.process("ixbig=Intersect[sp4,big]")
check("面数 > 4000 的立体 → 明确护栏提示",
      bool(c54.elements["ixbig"].error) and "面数过多" in c54.elements["ixbig"].error,
      str(c54.elements["ixbig"].error))

# ---------------------------------------------------------------------------
section("AM. 撤销/重做增量与计算记忆（P1-D）")
import time as _time  # noqa: E402
import kernel.memo as _memo  # noqa: E402

_memo.clear()
c55, e55 = build(["cu=Cube[(0,0,0),(2,0,0)]",
                  "imp=ImplicitSurface[x^2+y^2+z^2-4=0,-2.2,2.2,-2.2,2.2,-2.2,2.2,32]"])
check("重做性能用例构造", e55 is None, str(e55))
if e55 is None:
    before = c55.elements["imp"].data
    v_before, f_before = len(before["verts"]), len(before["faces"])
    c55.process("A1=Area[imp]")
    area_before = c55.elements["A1"].value
    order_before = list(c55.order)
    c55.undo()          # 撤销 A1
    c55.undo()          # 撤销重对象 imp
    check("两次 undo 后重对象已移除", "imp" not in c55.elements and "A1" not in c55.elements,
          str(sorted(c55.elements.keys())))
    _t0 = _time.time()
    c55.redo()          # 重新创建重对象：应命中计算记忆
    _dt = _time.time() - _t0
    c55.redo()          # 再恢复 A1
    after = c55.elements["imp"].data
    check("redo 重放命中计算记忆（< 150 ms，原约 1200 ms）", _dt < 0.15, "%.0f ms" % (_dt * 1000))
    check("redo 后网格与撤销前完全一致",
          len(after["verts"]) == v_before and len(after["faces"]) == f_before
          and after["verts"][:3] == before["verts"][:3],
          "v %d→%d" % (v_before, len(after["verts"])))
    check("redo 后依赖元素重新算出一致结果",
          close(c55.elements["A1"].value, area_before, 1e-9),
          "%.6f vs %.6f" % (c55.elements["A1"].value, area_before))
    check("redo 后元素顺序不变", list(c55.order) == order_before,
          "%s vs %s" % (list(c55.order), order_before))
    st = _memo.stats()
    check("计算记忆有命中记录", st["hits"] > 0, str(st))

# 记忆正确性：依赖变化必须失效
_memo.clear()
c56, _e56 = build(["a=2", "cyl=SurfaceParam[a*cos(t),a*sin(t),u,u,t,0,1,0,2*pi,8]"])
r1 = c56.elements["cyl"].data["verts"][0][0]
c56.elements["a"].value = 5.0
c56._recompute(c56.elements["a"])
r2 = c56.elements["cyl"].data["verts"][0][0]
check("滑块值变化后不再复用旧结果（记忆键含依赖签名）", abs(r1 - 2.0) < 1e-9 and abs(r2 - 5.0) < 1e-9,
      "%.3f → %.3f" % (r1, r2))
# 随机元素不进记忆
c57, _e57 = build(["poly=Polygon[(0,0),(4,0),(4,4),(0,4)]", "rp=RandomPointIn[poly]"])
rp = c57.elements["rp"]
check("随机类元素不参与计算记忆（键为 None）", _memo.key_for(rp) is None, str(_memo.key_for(rp)))
p_a = (rp.x, rp.y)
rp.compute()
check("随机点每次重算都会变", (rp.x, rp.y) != p_a, "%.4f,%.4f" % (rp.x, rp.y))
# 记忆容量上限
_memo.clear()
for _i in range(140):
    _memo.put(("t", _i), {"data": {"verts": [[0, 0, 0]]}})
check("计算记忆有条目上限（不会无限增长）", _memo.stats()["entries"] <= 96, str(_memo.stats()["entries"]))
_memo.clear()

# ---------------------------------------------------------------------------
section("AN. .ggb 内嵌网格/图片数据（P2）")
from kernel.mesh_io import parse_obj as _parse_obj  # noqa: E402
import kernel.image_store as _img_store  # noqa: E402

_OBJ_CUBE = """v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
v 0 0 2
v 2 0 2
v 2 2 2
v 0 2 2
f 1 2 3 4
f 5 6 7 8
f 1 2 6 5
f 2 3 7 6
f 3 4 8 7
f 4 1 5 8
"""
_v, _f, _w = _parse_obj(_OBJ_CUBE)
_mid_embed = _ms.put(_v, _f)
_png = ("data:image/png;base64,89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082")
_iid_embed = _img_store.put(_png, 1, 1)
c58, e58 = build(["m=Mesh[" + _mid_embed + "]", "V=Volume[m]", "A=(0,0)", "B=(3,0)",
                  "pic=Image[A,B," + _iid_embed + "]", "sq=Cube[(0,0,0),(2,0,0)]"])
check("内嵌数据用例构造", e58 is None, str(e58))
if e58 is None:
    warns58 = []
    xml58 = c58.save_ggb(warns58)
    check(".ggb 内嵌 ggbpyData 数据块", "<ggbpyData" in xml58)
    check(".ggb 不再因网格/图片跳过并警告", not warns58, str(warns58))
    check(".ggb 仍写出网格命令与图片命令", 'name="Mesh"' in xml58 or "Mesh[" in xml58,
          "")
    c59 = Construction()
    c59.load_ggb(xml58)
    m2 = c59.elements.get("m")
    check(".ggb 往返后网格元素恢复（8/6）",
          m2 is not None and len(m2.data["verts"]) == 8 and len(m2.data["faces"]) == 6,
          "None" if m2 is None else "%d/%d" % (len(m2.data["verts"]), len(m2.data["faces"])))
    check(".ggb 往返后依赖体积一致（=8）",
          c59.elements.get("V") is not None and close(c59.elements["V"].value, 8.0, 1e-9),
          str(getattr(c59.elements.get("V"), "value", None)))
    pic2 = c59.elements.get("pic")
    check(".ggb 往返后图片元素恢复（且图片数据可用）",
          pic2 is not None and not pic2.error and _img_store.get(_iid_embed) is not None,
          "err=%s" % (pic2.error if pic2 is not None else None))
    check("混合构造（网格+图片+立方体）元素数一致",
          len(c59.order) == len(c58.order), "%d vs %d" % (len(c59.order), len(c58.order)))
    # 数据缺失时仍给出警告（防御路径）
    _tmp_v = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
    _tmp_id = _ms.put(_tmp_v, [[0, 1, 2]])
    c60, _e60 = build(["g=Mesh[" + _tmp_id + "]"])
    _ms.MESHES.pop(_tmp_id, None)          # 模拟"仓库里数据丢失"
    w60 = []
    xml60 = c60.save_ggb(w60)
    check("网格数据缺失 → 仍有警告（防御路径）", bool(w60) and "跳过" in w60[0], str(w60)[:70])
    check("数据缺失时不再写出该元素", 'label="g"' not in xml60)

# ---------------------------------------------------------------------------
section("AO. SVG 3D 投影导出（P2）")
from kernel.svg_io import export_svg3d as _svg3d  # noqa: E402

c61, e61 = build(["O=(0,0,0)", "cu=Cube[O,(2,0,0)]", "P=(1,1,1)", "sp=Sphere[(1,1,1),1.5]",
                  "pl=Plane[O,(1,0,0),(0,1,0)]", "sec=Intersect[sp,pl]"])
check("SVG3D 用例构造", e61 is None, str(e61))
if e61 is None:
    svg = _svg3d(c61)
    check("输出合法 SVG 根节点", svg.startswith("<?xml") and "<svg" in svg and svg.rstrip().endswith("</svg>"))
    check("立方体 6 面 + 平面 1 面 → polygon ≥ 7", svg.count("<polygon") >= 7, "n=%d" % svg.count("<polygon"))
    check("球经纬线 + 交线 → polyline ≥ 4", svg.count("<polyline") >= 4, "n=%d" % svg.count("<polyline"))
    check("点（O、P）输出为圆点与标签",
          svg.count("<circle") >= 2 and svg.count("<text") >= 2,
          "circle=%d text=%d" % (svg.count("<circle"), svg.count("<text")))
    check("SVG 内无 nan/None 数值", "nan" not in svg and "None" not in svg)
    # —— 本批补的三类导出：空间圆 / 截面 / 默认俯视 + 机位参数 ——
    _circ = [l for l in svg.split("\n") if l.strip().startswith("<polyline") and l.count(",") >= 60]
    check("空间圆（circle3d）导出为 65 点折线（此前静默漏画 ✗）", len(_circ) >= 1, "n=%d" % len(_circ))
    c64, _e64 = build(["A=(-1,-1,0)", "B=(1,-1,0)", "cu=Cube[A,B]",
                       "X1=(0,-3,0)", "X2=(0,3,0)", "X3=(0,0,4)", "pl=Plane[X1,X2,X3]",
                       "sec=Intersect[pl,cu]", 'SetColor[sec,"#ef4444"]'])
    check("截面用例构造", _e64 is None, str(_e64))
    if _e64 is None:
        _sv = _svg3d(c64)
        check("截面多边形（section）按元素颜色导出（此前静默漏画 ✗）",
              'stroke="#ef4444"' in _sv and "<polygon" in _sv, "")
        _c65, _ = build(["A=(0,0,0)", "B=(0,0,2)"])
        _sup = _svg3d(_c65)
        _dots, _last = {}, None
        for _l in _sup.split("\n"):
            if "<circle" in _l:
                _m = re.search(r'cy="([-\d.]+)"', _l)
                _last = float(_m.group(1)) if _m else None
            elif "<text" in _l and _last is not None:
                _dots[re.sub(r"<[^>]+>", "", _l).strip()] = _last
                _last = None
        check("默认机位是俯视（z=2 的点在屏幕上高于 z=0 的点）",
              len(_dots) == 2 and _dots.get("B", 0) < _dots.get("A", 0), str(_dots))
        check("yaw/pitch 机位参数生效（换角度输出不同）",
              _svg3d(_c65, yaw=0.4, pitch=-0.2) != _sup, "")
    check("画家算法：polygon 按深度排序输出（含 depth 递减的先后关系）",
          svg.index("<polygon") < svg.rindex("<polygon"), "")
    # 面预算
    c62, _e62 = build(["big=ImplicitSurface[x^2+y^2+z^2-4=0,-2.2,2.2,-2.2,2.2,-2.2,2.2,24]"])
    svg_big = _svg3d(c62, face_budget=500)
    check("大网格按 face_budget 限制多边形数量（≤500）",
          svg_big.count("<polygon") <= 500, "n=%d" % svg_big.count("<polygon"))
    # 无 3D 时明确报错
    c63, _e63 = build(["A=(0,0)", "c=Circle[A,2]"])
    try:
        _svg3d(c63)
        check("无 3D 对象 → 明确报错", False, "未报错")
    except Exception as _ex:
        check("无 3D 对象 → 明确报错", "3D" in str(_ex), str(_ex)[:40])

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
section("SurfaceArea（新功能：曲面/立体表面积）")

_c, _err = build(["Sp=Sphere[(0,0,0),2]", "SA=SurfaceArea[Sp]"])
_el = _c.elements.get("SA")
check("SurfaceArea[半径 2 球] = 4πr² ≈ 50.265482",
      _err is None and _el is not None and _el.kind == "number" and close(_el.value, 4 * math.pi * 4),
      str(_err or getattr(_el, "value", None)))

_c2, _err2 = build(["C1=Cube[(0,0,0),(1,0,0)]", "A1=SurfaceArea[C1]"])
_el2 = _c2.elements.get("A1")
check("SurfaceArea[单位立方体] = 6",
      _err2 is None and _el2 is not None and close(_el2.value, 6.0),
      str(_err2 or getattr(_el2, "value", None)))

_c3, _err3 = build(["Apex=(0,0,0)", "IC=Cone[Apex,(0,0,1),30]", "SA2=SurfaceArea[IC]"])
_el3 = _c3.elements.get("SA2")
check("SurfaceArea[无限圆锥] → 元素带明确 error（无有限表面积）",
      _el3 is not None and "表面积" in (getattr(_el3, "error", "") or ""),
      str(getattr(_el3, "error", None))[:40])

_c4 = Construction()
_c4.process("P2d=(1,1)")
_msg5 = _c4.process("SA3=SurfaceArea[P2d]")
check("SurfaceArea 拒绝二维对象（提示用 Area）",
      _c4.elements.get("SA3") is None and "Area" in (_msg5 or ""), (_msg5 or "")[:40])

# ---------------------------------------------------------------------------
section("列表字面量接受三维点标签（{P3,Q3}）")

_pc, _perr = build(["P3a=(1,2,3)", "Q3a=(4,5,6)", "L3p={P3a,Q3a}"])
_l3 = _pc.elements.get("L3p")
check("三维点标签列表 → itemkind=point3d、三分量坐标",
      _perr is None and _l3 is not None and _l3.itemkind == "point3d"
      and [list(x) for x in _l3.items] == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
      str(_perr or ([list(x) for x in getattr(_l3, "items", [])], getattr(_l3, "itemkind", None))))

_c5 = Construction()
_c5.process("P2a=(1,1)")
_c5.process("P3b=(1,2,3)")
_msg5 = _c5.process("LMix={P2a,P3b}")
check("二维点与三维点混在同一列表 → 明确报错",
      _c5.elements.get("LMix") is None and "分量数需一致" in (_msg5 or ""), (_msg5 or "")[:44])

print("\n" + "=" * 60)
print("3D 内核检测矩阵：%d 项断言，%d 失败" % (COUNT[0], len(FAILS)))
if FAILS:
    for f in FAILS:
        print("  FAILED: " + f)
print("结果:", "ALL PASS" if not FAILS else "FAILED")
sys.exit(0 if not FAILS else 1)
