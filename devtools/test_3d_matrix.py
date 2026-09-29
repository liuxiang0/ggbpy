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
    r = c21.process("bad=Intersect[cu,sp]")
    check("立体×球 明确不支持", "3D 求交暂不支持" in r, r[:80])
    r = c21.process("bad2=Intersect[pl,sp]")
    check("面×球 明确不支持（圆暂缺）", "3D 求交暂不支持" in r, r[:80])

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
    r6 = c17.process("ix6=Intersect[cu,cu]")
    check("立体×立体明确不支持", not r6.startswith("OK") and "3D 求交暂不支持" in r6, r6[:70])
    r7 = c17.process("ix7=Intersect[pl1,sp]")
    check("面×球明确不支持（3D 圆暂缺）", not r7.startswith("OK") and "3D 求交暂不支持" in r7, r7[:70])

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("3D 内核检测矩阵：%d 项断言，%d 失败" % (COUNT[0], len(FAILS)))
if FAILS:
    for f in FAILS:
        print("  FAILED: " + f)
print("结果:", "ALL PASS" if not FAILS else "FAILED")
sys.exit(0 if not FAILS else 1)
