"""滑块长度按 px：内核（字段/命令/持久化）。"""
from pathlib import Path

# 1) editing._cmd_slider：解析可选 px（位置/vertical 之后的裸数字）
p = Path("kernel/editing.py"); s = p.read_text(encoding="utf-8")
old = '''    if args and args[-1].strip().startswith("("):
        pos = args.pop()
    if len(args) not in (2, 3):'''
new = '''    if args and args[-1].strip().startswith("("):
        pos = args.pop()
    px = None
    if len(args) >= 3 and args[-1].strip().replace(".", "", 1).isdigit():
        px = float(args.pop())          # 可选：轨道**屏幕长度**（px），仅非默认时写入 defn
    if len(args) not in (2, 3):'''
assert s.count(old) == 1, ("args", s.count(old))
s = s.replace(old, new, 1)
old2 = '''    el.slider_vert = vertical                                # 竖直放置（轨道沿 +y，播放按钮在底部）'''
assert s.count(old2) == 1, ("tail", s.count(old2))
s = s.replace(old2, old2 + '''
    el.slider_px = px if (px and px > 0) else SLIDER_PX_DEFAULT   # 轨道屏幕长度（px，恒定）''', 1)
p.write_text(s, encoding="utf-8")
print("  editing._cmd_slider：支持 px")

# 2) tolerance：默认 px 常量（避免魔数散落）
p = Path("kernel/tolerance.py"); s = p.read_text(encoding="utf-8")
if "SLIDER_PX_DEFAULT" not in s:
    s = s.rstrip("\n") + "\n\n# 滑块轨道默认屏幕长度（px）；屏幕常量不进前端容差一致性检查\nSLIDER_PX_DEFAULT = 140.0\nSLIDER_PX_MIN = 40.0\nSLIDER_PX_MAX = 1200.0\n"
    p.write_text(s, encoding="utf-8")
print("  tolerance：SLIDER_PX_* 常量")

# 3) editing 顶部引入常量
p = Path("kernel/editing.py"); s = p.read_text(encoding="utf-8")
if "SLIDER_PX_DEFAULT" not in s.split("\n\n")[0]:
    import re
    m = re.search(r"^from \.tolerance import ([^\n]+)$", s, re.M)
    assert m, "未找到 tolerance import"
    names = m.group(1)
    if "SLIDER_PX_DEFAULT" not in names:
        s = s[:m.start()] + "from .tolerance import %s, SLIDER_PX_DEFAULT" % names + s[m.end():]
        p.write_text(s, encoding="utf-8")
        print("  editing：引入 SLIDER_PX_DEFAULT")

# 4) elements.GeoNumber.draw：序列化 slider_px
p = Path("kernel/elements.py"); s = p.read_text(encoding="utf-8")
old3 = '''            d["slider_vert"] = bool(getattr(self, "slider_vert", False))'''
assert s.count(old3) == 1, ("draw", s.count(old3))
s = s.replace(old3, old3 + '''
            d["slider_px"] = float(getattr(self, "slider_px", 140.0))''', 1)
p.write_text(s, encoding="utf-8")
print("  GeoNumber.draw：序列化 slider_px")

# 5) widgets：_regen_defn 带 px（仅非默认）+ SetSliderLength
p = Path("kernel/widgets.py"); s = p.read_text(encoding="utf-8")
old4 = '''        _v = ",vertical" if getattr(el, "slider_vert", False) else ""
        return "%s=Slider[%s,%s,%s,(%s,%s)%s]" % (lab, _num_txt(el.min), _num_txt(el.max),
                                                 _num_txt(el.step), _num_txt(el.slider_x),
                                                 _num_txt(el.slider_y), _v)'''
assert s.count(old4) == 1, ("regen", s.count(old4))
s = s.replace(old4, '''        _v = ",vertical" if getattr(el, "slider_vert", False) else ""
        _px = getattr(el, "slider_px", SLIDER_PX_DEFAULT)
        _p = "" if abs(_px - SLIDER_PX_DEFAULT) < COORD else "," + _num_txt(_px)
        return "%s=Slider[%s,%s,%s,(%s,%s)%s%s]" % (lab, _num_txt(el.min), _num_txt(el.max),
                                                   _num_txt(el.step), _num_txt(el.slider_x),
                                                   _num_txt(el.slider_y), _v, _p)''', 1)
s = s.replace("from .tolerance import COORD", "from .tolerance import COORD, SLIDER_PX_DEFAULT, SLIDER_PX_MAX, SLIDER_PX_MIN", 1)
s += '''

def _cmd_setsliderlength(cons, defn, args):
    """``SetSliderLength[滑块, px]`` → 设轨道**屏幕长度**（px，缩放时不变）。"""
    if len(args) != 2:
        raise GeoError("SetSliderLength 需要 滑块 和 像素长度")
    el = _resolve(cons, args[0])
    if getattr(el, "kind", "") != "number" or getattr(el, "min", None) is None:
        raise GeoError("SetSliderLength 需要滑动条（当前是 %s）" % getattr(el, "kind", "?"))
    px = eval_number(cons, args[1])
    if px < SLIDER_PX_MIN or px > SLIDER_PX_MAX:
        raise GeoError("长度需在 %d–%d px 之间" % (SLIDER_PX_MIN, SLIDER_PX_MAX))
    el.slider_px = float(px)
    el.defn = _regen_defn(el)
    return []
'''
p.write_text(s, encoding="utf-8")
print("  widgets：_regen_defn 带 px + SetSliderLength")

# 6) registry
p = Path("kernel/registry.py"); s = p.read_text(encoding="utf-8")
s = s.replace("_cmd_setslidervert, _cmd_setwidgetpos)", "_cmd_setsliderlength, _cmd_setslidervert,\n                      _cmd_setwidgetpos)", 1)
a = '''    ("setslidervertical", _cmd_setslidervert, "SetSliderVertical", "point", ("滑块方向", "竖直滑块")),'''
assert s.count(a) == 1
s = s.replace(a, a + '''
    ("setsliderlength", _cmd_setsliderlength, "SetSliderLength", "point", ("滑块长度", "改滑块长度")),''', 1)
p.write_text(s, encoding="utf-8")
print("  registry：SetSliderLength 已注册")
