
import sys, math
sys.path.insert(0, ".")
from kernel.construction import Construction

def build(lines):
    c = Construction()
    for t in lines:
        msg = c.process(t)
        if not msg.startswith("OK"):
            return c, (t, msg)
    return c, None

def mesh(c, lbl):
    el = c.elements[lbl]
    return el.data, el

def elens(data):
    vs = data["verts"]
    return [math.dist(vs[a], vs[b]) for a, b in data["edges"]]

def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("  " + detail if detail else ""))

print("=== A. 3D 点 / 线段 / 直线 ===")
c, err = build(["A3=(1,2,3)", "B3=(4,6,3)", "s=Segment[A3,B3]", "L=Line[A3,B3]"])
if err: print("  build err", err)
else:
    d, el = mesh(c, "s")
    check("3D 线段 objtype", el.objtype == "segment", el.objtype)
    check("3D 线段长度=5", abs(math.dist([d["x1"],d["y1"],d["z1"]],[d["x2"],d["y2"],d["z2"]]) - 5) < 1e-9)
    d, el = mesh(c, "L")
    check("3D 直线 objtype", el.objtype == "line3d", el.objtype)
    check("3D 直线延伸 50", abs(math.dist([d["x1"],d["y1"],d["z1"]],[d["x2"],d["y2"],d["z2"]]) - 50) < 1e-9)
    mid = [(d["x1"]+d["x2"])/2, (d["y1"]+d["y2"])/2, (d["z1"]+d["z2"])/2]
    check("3D 直线过 A3", math.dist(mid, [1,2,3]) < 1e-9, str([round(x,3) for x in mid]))

print("=== B. 平面 ===")
c, err = build(["A3=(1,2,3)", "B3=(4,6,3)", "C3=(1,0,0)", "pl=Plane[A3,B3,C3]"])
if err: print("  build err", err)
else:
    d, el = mesh(c, "pl")
    check("平面 objtype", el.objtype == "plane", el.objtype)
    n = (d["a"], d["b"], d["c"])
    check("平面法向单位", abs(math.sqrt(sum(x*x for x in n)) - 1) < 1e-9)
    check("平面过 A3", abs(n[0]*1 + n[1]*2 + n[2]*3 + d["d"]) < 1e-9)
    check("平面过 B3", abs(n[0]*4 + n[1]*6 + n[2]*3 + d["d"]) < 1e-9)
    check("平面过 C3", abs(n[0]*1 + n[1]*0 + n[2]*0 + d["d"]) < 1e-9)

print("=== C. 球 ===")
c, err = build(["O=(0,0,0)", "P=(3,0,0)", "S1=Sphere[O,P]", "S2=Sphere[O,4]", "rr=2.5", "S3=Sphere[O,rr]"])
if err: print("  build err", err)
else:
    d, el = mesh(c, "S1"); check("球(点) r=3", el.objtype=="sphere" and abs(d["r"]-3)<1e-9, str(d))
    d, el = mesh(c, "S2"); check("球(数) r=4", abs(d["r"]-4)<1e-9, str(d))
    d, el = mesh(c, "S3"); check("球(数值元素) r=2.5", abs(d["r"]-2.5)<1e-9, str(d))
    c.elements["rr"].value = 5.0; c._recompute(c.elements["rr"])
    d, el = mesh(c, "S3"); check("球随数值元素更新 r=5", abs(d["r"]-5)<1e-9, str(d.get("r")))

print("=== C2. 球异常 ===")
c, err = build(["O=(0,0,0)"])
if not err:
    m = c.process("Sneg=Sphere[O,-1]"); el = c.elements.get("Sneg")
    print("  Sphere[O,-1] ->", m, "| error:", None if el is None else el.error, "| r:", None if el is None else getattr(el,"r",None))
    m = c.process("Szero=Sphere[O,0]"); el = c.elements.get("Szero")
    print("  Sphere[O,0]  ->", m, "| error:", None if el is None else el.error, "| r:", None if el is None else getattr(el,"r",None))

print("=== D. 多面体 ===")
P3 = ["A=(0,0,0)", "B=(4,0,0)", "C=(0,4,0)"]
specs = [
    ("Prism",      "Prism[A,B,C]",        6, 5, 9, None),
    ("Pyramid",    "Pyramid[A,B,C]",      4, 4, 6, None),
    ("Tetrahedron","Tetrahedron[A,B,C]",  4, 4, 6, "equal"),
    ("Octahedron", "Octahedron[A,B,C]",   6, 8, 12, "equal"),
    ("Hexahedron", "Hexahedron[A,B,C]",   8, 6, 12, "equal"),
    ("Icosahedron","Icosahedron[A,B,C]", 12, 20, 30, "equal"),
    ("Dodecahedron","Dodecahedron[A,B,C]",20,12,30, "equal"),
    ("Cube",       "Cube[A,B]",           8, 6, 12, "equal"),
]
for name, cmd, nv, nf, ne, equ in specs:
    c, err = build(P3 + [ "X=" + cmd ])
    if err:
        print("FAIL", name, cmd, "->", err); continue
    d, el = mesh(c, "X")
    okv = len(d["verts"]) == nv; okf = len(d["faces"]) == nf; oke = len(d["edges"]) == ne
    L = elens(d)
    okEq = (max(L)-min(L)) < 1e-6 * max(L) if equ else True
    check(name + " " + cmd + " v/f/e", okv and okf and oke,
          "v=%d/%d f=%d/%d e=%d/%d" % (len(d["verts"]),nv,len(d["faces"]),nf,len(d["edges"]),ne))
    if equ:
        check(name + " 棱全等", okEq, "min=%.4f max=%.4f" % (min(L),max(L)))
    # 面索引合法
    bad = [fi for fi in d["faces"] if any(i < 0 or i >= len(d["verts"]) for i in fi)]
    check(name + " 面索引合法", not bad, str(bad))

print("=== E. 退化输入（应进入 error 状态） ===")
E_cases = [(["A3=(1,1,1)"], "Segment[A3,A3]"), (["A3=(1,1,1)"], "Line[A3,A3]"),
           (["A=(0,0,0)"], "Sphere[A,0]"), (["A=(0,0,0)"], "Sphere[A,-1]"),
           (["A=(0,0,0)", "B=(1,0,0)"], "Tetrahedron[A,A,B]"),
           (["A=(1,1,1)", "B=(2,2,2)"], "Prism[A,A,B]")]
for lines, cmd in E_cases:
    cc = Construction()
    for t in lines: cc.process(t)
    before = set(cc.elements.keys())
    cc.process(cmd)
    newl = [l for l in cc.elements.keys() if l not in before]
    el = cc.elements[newl[0]] if newl else None
    check(cmd + " 报错", el is not None and el.error, str(el.error if el else "no element"))


print("=== F. 序列化往返 ===")
c, err = build(P3 + ["X=Cube[A,B]", "sph=Sphere[A,B]", "pl=Plane[A,B,C]", "L=Line[A,B]"])
if err: print("  build err", err)
else:
    txt = c.save_json()
    c2 = Construction(); c2.load_json(txt)
    ok = True
    for lbl in ["X","sph","pl","L"]:
        e1 = c.elements[lbl]; e2 = c2.elements.get(lbl)
        if e2 is None: ok = False; print("   缺失", lbl); continue
        if getattr(e2, "data", None) is None: ok = False; print("   data 缺失", lbl)
    check(".ggk 往返 3D 对象", ok)

print("DONE")
