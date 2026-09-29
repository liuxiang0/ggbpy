
import sys, math
sys.path.insert(0, ".")
from kernel.construction import Construction

def probe(lines, cmd):
    c = Construction()
    for t in lines:
        m = c.process(t)
        if not m.startswith("OK"): return "setup-fail:"+m
    before = set(c.elements.keys())
    m = c.process(cmd)
    new = [l for l in c.elements.keys() if l not in before]
    if not new: return m + " | (no new element)"
    el = c.elements[new[0]]
    return "%s | %s objtype=%s error=%s data=%s" % (m, new[0], getattr(el,"objtype",None), getattr(el,"error",None), getattr(el,"data",None))

cases = [
    (["A3=(1,1,1)"], "Segment[A3,A3]"),
    (["A3=(1,1,1)"], "Line[A3,A3]"),
    (["A3=(1,1,1)", "B3=(1,1,1)"], "Segment[A3,B3]"),
    (["A3=(1,1,1)", "B3=(2,2,2)", "C3=(3,3,3)"], "Plane[A3,B3,C3]"),
    (["A=(0,0,0)"], "Sphere[A,-1]"),
    (["A=(0,0,0)"], "Sphere[A,0]"),
    (["A=(0,0,0)", "B=(0,0,0)"], "Sphere[A,B]"),
    (["A=(0,0,0)", "B=(1,0,0)"], "Tetrahedron[A,A,B]"),
    (["A=(1,1,1)", "B=(2,2,2)"], "Prism[A,A,B]"),
]
for lines, cmd in cases:
    print("%-26s -> %s" % (cmd, probe(lines, cmd)))
print("DONE")
