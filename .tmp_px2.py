"""前端：轨道长度按 px（屏幕恒定）；取值改用屏幕坐标换算。"""
from pathlib import Path

p = Path("server/static/render2d.js"); s = p.read_text(encoding="utf-8")
old = """          var _vert = !!e.slider_vert;
          var tk0, tk1, tky, tkx;
          if (_vert) {
            // 竖直：轨道沿 +y，min 在底、max 在顶；播放按钮在**底部**
            tkx = sxp(e.slider_x);
            tk0 = syp(e.slider_y);                      // 底（min）
            tk1 = syp(e.slider_y + (e.slider_len || 3)); // 顶（max）
          } else {
            tk0 = sxp(e.slider_x);
            tk1 = sxp(e.slider_x + (e.slider_len || 3));
            tky = syp(e.slider_y);
          }"""
assert s.count(old) == 1, ("len", s.count(old))
new = """          var _vert = !!e.slider_vert;
          var _px = e.slider_px > 0 ? e.slider_px : 140;   // 轨道**屏幕长度（px）**，缩放时不变
          var tk0, tk1, tky, tkx;
          if (_vert) {
            // 竖直：轨道沿 +y（屏幕向上），min 在底、max 在顶；播放按钮在**底部**
            tkx = sxp(e.slider_x);
            tk0 = syp(e.slider_y);          // 底（min）
            tk1 = tk0 - _px;                // 顶（max）
          } else {
            tk0 = sxp(e.slider_x);
            tk1 = tk0 + _px;
            tky = syp(e.slider_y);
          }"""
s = s.replace(old, new, 1)

# 命中框：加屏幕端点 s0/s1 与 trackPx
s = s.replace("""                  x0: tkx - 14, x1: tkx + 14, y0: Math.min(tk0, tk1) - 12, y1: Math.max(tk0, tk1) + 12,
                  knobX: kx, knobY: ky,""",
"""                  x0: tkx - 14, x1: tkx + 14, y0: Math.min(tk0, tk1) - 12, y1: Math.max(tk0, tk1) + 12,
                  knobX: kx, knobY: ky, s0: tk0, s1: tk1, trackPx: _px,""", 1)
s = s.replace("""                  x0: Math.min(tk0, tk1) - 10, x1: Math.max(tk0, tk1) + 10,
                  y0: tky - 14, y1: tky + 16, knobX: kx,""",
"""                  x0: Math.min(tk0, tk1) - 10, x1: Math.max(tk0, tk1) + 10,
                  y0: tky - 14, y1: tky + 16, knobX: kx, s0: tk0, s1: tk1, trackPx: _px,""", 1)
p.write_text(s, encoding="utf-8")
print("  render2d：轨道按 px + 命中框 s0/s1/trackPx")

p = Path("server/static/app.js"); s = p.read_text(encoding="utf-8")
old2 = """  function sliderValueAt(label, wx, wy) {
    var b = widgetBoxes[label];
    var el = findEl(label);
    if (!b || !el || el.min === null || el.min === undefined) return 0;
    var f = (b.axis === 'y') ? (wy - b.wy0) / ((b.wy1 - b.wy0) || 1)
                             : (wx - b.wx0) / ((b.wx1 - b.wx0) || 1);"""
assert s.count(old2) == 1, ("val", s.count(old2))
s = s.replace(old2, """  // 取值用**屏幕坐标**换算（轨道长度按 px → 世界换算不再适用）；sx/sy 为画布局部坐标
  function sliderValueAt(label, sx, sy) {
    var b = widgetBoxes[label];
    var el = findEl(label);
    if (!b || !el || el.min === null || el.min === undefined) return 0;
    var _p = (b.axis === 'y') ? sy : sx;
    var f = (_p - b.s0) / ((b.s1 - b.s0) || 1);""", 1)
s = s.replace("x: sliderValueAt(sldHit, wxp(sx), wyp(sy)), y: 0, push: true", "x: sliderValueAt(sldHit, sx, sy), y: 0, push: true", 1)
s = s.replace("var _sv = sliderValueAt(drag.label, wxp(ev.offsetX), wyp(ev.offsetY));",
              "var _sv = sliderValueAt(drag.label, ev.offsetX, ev.offsetY);", 1)
p.write_text(s, encoding="utf-8")
print("  app.js：sliderValueAt 用屏幕坐标 + 调用点改传屏幕坐标")
