import json
import sys
sys.path.insert(0, ".")
from kernel.construction import Construction

c = Construction()
c.process("s=Slider[0,10,1,(-5,3),vertical]")
el = c.elements["s"]
print("  竖直创建: defn=%r vert=%s" % (el.defn, el.slider_vert))
d = el.draw((0, 0, 1, 1))
print("  draw 含 slider_vert:", d.get("slider_vert"))
c.process("SetSliderVertical[s, false]")
print("  改水平: defn=%r vert=%s" % (c.elements["s"].defn, c.elements["s"].slider_vert))
c.process("SetSliderVertical[s, true]")
print("  再改竖直: defn=%r" % c.elements["s"].defn)
c.process("SetValue[s, 7]")
print("  竖直后改值: 值=%.1f defn=%r（Slider 定义保留）" % (c.elements["s"].value, c.elements["s"].defn))
c2 = Construction(); c2.load_json(json.dumps(json.loads(c.save_json())))
print("  .ggk 往返: vert=%s 值=%.1f" % (c2.elements["s"].slider_vert, c2.elements["s"].value))
print("  报错:", (c.process("SetSliderVertical[c, true]") or "")[:40])
