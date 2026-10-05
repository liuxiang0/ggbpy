"""内核：滑块可竖直（slider_vert）——命令参数、序列化、SetSliderVertical。"""
from pathlib import Path

# 1) editing._cmd_slider：接受末尾 vertical 关键字
p = Path("kernel/editing.py"); s = p.read_text(encoding="utf-8")
old = """    args = list(args)
    pos = None
    if args and args[-1].strip().startswith("("):
        pos = args.pop()"""
new = """    args = list(args)
    pos = None
    vertical = False
    if args and args[-1].strip().lower() in ("vertical", "v", "竖直"):
        vertical = True
        args.pop()
    if args and args[-1].strip().startswith("("):
        pos = args.pop()"""
assert s.count(old) == 1, ("args", s.count(old))
s = s.replace(old, new, 1)
old2 = """    el.slider_len = 3.0                                      # 轨道世界长度
    return cons.add(el)"""
new2 = """    el.slider_len = 3.0                                      # 轨道世界长度
    el.slider_vert = vertical                                # 竖直放置（轨道沿 +y，播放按钮在底部）
    return cons.add(el)"""
assert s.count(old2) == 1, ("tail", s.count(old2))
s = s.replace(old2, new2, 1)
p.write_text(s, encoding="utf-8")
print("  editing._cmd_slider：支持 vertical")

# 2) elements.GeoNumber.draw：序列化方向
p = Path("kernel/elements.py"); s = p.read_text(encoding="utf-8")
old3 = """            d["slider_len"] = getattr(self, "slider_len", 3.0)"""
assert s.count(old3) == 1, ("draw", s.count(old3))
s = s.replace(old3, old3 + """
            d["slider_vert"] = bool(getattr(self, "slider_vert", False))""", 1)
p.write_text(s, encoding="utf-8")
print("  GeoNumber.draw：序列化 slider_vert")

# 3) widgets：_regen_defn 带上 vertical + 新命令 SetSliderVertical
p = Path("kernel/widgets.py"); s = p.read_text(encoding="utf-8")
old4 = """    if getattr(el, "kind", "") == "number" and getattr(el, "min", None) is not None:
        return "%s=Slider[%s,%s,%s,(%s,%s)]" % (lab, _num_txt(el.min), _num_txt(el.max),
                                               _num_txt(el.step), _num_txt(el.slider_x),
                                               _num_txt(el.slider_y))"""
assert s.count(old4) == 1, ("regen", s.count(old4))
s = s.replace(old4, """    if getattr(el, "kind", "") == "number" and getattr(el, "min", None) is not None:
        _v = ",vertical" if getattr(el, "slider_vert", False) else ""
        return "%s=Slider[%s,%s,%s,(%s,%s)%s]" % (lab, _num_txt(el.min), _num_txt(el.max),
                                                 _num_txt(el.step), _num_txt(el.slider_x),
                                                 _num_txt(el.slider_y), _v)""", 1)
s += '''

def _cmd_setslidervert(cons, defn, args):
    """``SetSliderVertical[滑块, true/false]`` → 竖直 / 水平放置（功能不变，仅方向与按钮位置）。"""
    if len(args) != 2:
        raise GeoError("SetSliderVertical 需要 滑块 和 true/false")
    el = _resolve(cons, args[0])
    if getattr(el, "kind", "") != "number" or getattr(el, "min", None) is None:
        raise GeoError("SetSliderVertical 需要滑动条（当前是 %s）" % getattr(el, "kind", "?"))
    v = args[1].strip().lower()
    if v in ("true", "1", "yes", "竖直", "vertical"):
        el.slider_vert = True
    elif v in ("false", "0", "no", "水平", "horizontal"):
        el.slider_vert = False
    else:
        raise GeoError("SetSliderVertical 需要 true 或 false")
    el.defn = _regen_defn(el)
    return []
'''
p.write_text(s, encoding="utf-8")
print("  widgets：_regen_defn 带 vertical + SetSliderVertical")

# 4) registry
p = Path("kernel/registry.py"); s = p.read_text(encoding="utf-8")
s = s.replace("_cmd_setinput, _cmd_setscript, _cmd_setslider,\n                      _cmd_setwidgetpos)",
              "_cmd_setinput, _cmd_setscript, _cmd_setslider,\n                      _cmd_setslidervert, _cmd_setwidgetpos)", 1)
a = '''    ("setslider", _cmd_setslider, "SetSlider", "point", ("滑块范围", "改滑块")),'''
assert s.count(a) == 1
s = s.replace(a, a + '''
    ("setslidervert", _cmd_setslidervert, "SetSliderVertical", "point", ("滑块方向", "竖直滑块")),''', 1)
p.write_text(s, encoding="utf-8")
print("  registry：SetSliderVertical 已注册")
