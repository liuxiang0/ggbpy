
import sys
sys.path.insert(0, ".")
from kernel.construction import Construction
c = Construction()
for t in ["A=(0,0)","B=(4,0)","C=(0,3)","s=Segment[A,B]","L=Line[A,B]","pl=Plane[A,B,C]","S=Sphere[A,B]","K=Cube[A,B]"]:
    m = c.process(t)
    assert m.startswith("OK"), (t, m)
print("2D/3D mixed smoke OK:", {l:(c.elements[l].kind, getattr(c.elements[l],"objtype",None), c.elements[l].error) for l in ["s","L","pl","S","K"]})
