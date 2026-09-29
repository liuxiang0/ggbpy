import sys, math
sys.path.insert(0, ".")
from kernel.construction import Construction

def run(lines):
    c = Construction()
    for t in lines:
        msg = c.process(t)
        if not msg.startswith("OK"):
            print("  FAIL", t, "->", msg)
    return c

def mesh(c, lbl):
    return c.elements[lbl].data

# 1) Cylinder[圆, 高]
c = run(["O=(0,0)", "c=Circle[O,2]", "K=Cylinder[c,4]"])
if "K" in c.elements:
    d = mesh(c, "K"); vs = d["verts"]
    zs = sorted(set(round(v[2],3) for v in vs))
    rs = [round(math.hypot(v[0], v[1]),3) for v in vs]
    print("form1", c.elements["K"].defn, "| z:", zs, "| r:", min(rs), max(rs), "| nv:", len(vs), "| nf:", len(d["faces"]), "| ne:", len(d["edges"]))

# 1b) 滑块驱动高度
c2 = run(["O=(0,0)", "c=Circle[O,2]", "hh=Slider[1,5,0.5]", "K2=Cylinder[c,hh]"])
vs = mesh(c2, "K2")["verts"]
print("form1b", c2.elements["K2"].defn, "| zmax@1:", round(max(v[2] for v in vs),3))
c2.elements["hh"].value = 4.0
c2._recompute(c2.elements["hh"])
vs = mesh(c2, "K2")["verts"]
print("       after hh=4 zmax:", round(max(v[2] for v in vs),3))

# 2) Cylinder[底心, 顶心, 半径]
c3 = run(["P=(0,0,0)", "Q=(0,0,5)", "K3=Cylinder[P,Q,2]"])
vs = mesh(c3, "K3")["verts"]
zs = sorted(set(round(v[2],3) for v in vs))
rs = [round(math.hypot(v[0], v[1]),3) for v in vs]
print("form2", c3.elements["K3"].defn, "| z:", zs, "| r:", min(rs), max(rs))

# 2b) 斜轴
c4 = run(["P=(0,0,0)", "Q=(4,0,0)", "K4=Cylinder[P,Q,1.5]"])
vs = mesh(c4, "K4")["verts"]
xs = sorted(set(round(v[0],3) for v in vs))
print("form2b", c4.elements["K4"].defn, "| x:", xs, "| r(yz):", round(max(math.hypot(v[1],v[2]) for v in vs),3))

# 2c) 2D 点到 3D
c4b = run(["A=(0,0)", "B=(0,3)", "K=Cylinder[A,B,1]"])
vs = mesh(c4b, "K")["verts"]
print("form2c", c4b.elements["K"].defn, "| z:", sorted(set(round(v[2],3) for v in vs)))

# 3) 经典三点
c5 = run(["A=(0,0,0)", "B=(2,0,0)", "T=(0,0,4)", "K5=Cylinder[A,B,T]"])
vs = mesh(c5, "K5")["verts"]
zs = sorted(set(round(v[2],3) for v in vs))
rs = [round(math.hypot(v[0],v[1]),3) for v in vs]
print("classic", c5.elements["K5"].defn, "| z:", zs, "| r:", min(rs), max(rs))

# 4) 错误输入
c6 = run(["A=(0,0,0)","B=(2,0,0)"])
print("zero radius:", c6.process("Cylinder[A,B,0]"))
print("neg height:", c6.process("Cylinder[Circle[(0,0),1], -1]"))
print("DONE")