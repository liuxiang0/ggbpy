"""前端：竖直滑块渲染（轨道沿 +y，min 在底、max 在顶，播放按钮在底部）+ 取值按轴。"""
from pathlib import Path

# 1) render2d：竖直分支
p = Path("server/static/render2d.js"); s = p.read_text(encoding="utf-8")
a = "        if (e.kind === 'number' && e.min !== null && e.min !== undefined\n            && e.slider_x !== null && e.slider_x !== undefined) {"
assert s.count(a) == 1, ("blk", s.count(a))
b = "          var tk0 = sxp(e.slider_x), tk1 = sxp(e.slider_x + (e.slider_len || 3)), tky = syp(e.slider_y);"
assert s.count(b) == 1, ("h", s.count(b))
new_h = '''          var _vert = !!e.slider_vert;
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
          }'''
s = s.replace(b, new_h, 1)

# 轨道/滑钮/标注：按方向分支
old_draw = """          var span = (e.max - e.min) || 1;
          var frac = Math.max(0, Math.min(1, (e.val - e.min) / span));
          var kx = tk0 + (tk1 - tk0) * frac;
          ctx.save();
          ctx.strokeStyle = '#94a3b8';
          ctx.lineWidth = 4;
          ctx.beginPath();
          ctx.moveTo(tk0, tky);
          ctx.lineTo(tk1, tky);
          ctx.stroke();
          ctx.fillStyle = '#2563eb';
          ctx.beginPath();
          ctx.arc(kx, tky, 7, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 2;
          ctx.stroke();
          ctx.fillStyle = '#334155';
          ctx.font = '12px sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText(fmtNum(e.min), tk0, tky + 9);
          ctx.fillText(fmtNum(e.max), tk1, tky + 9);
          ctx.textBaseline = 'bottom';
          ctx.fillStyle = '#1d4ed8';
          ctx.fillText(e.label + ' = ' + fmtNum(e.val), (tk0 + tk1) / 2, tky - 9);
          ctx.restore();"""
assert s.count(old_draw) == 1, ("draw", s.count(old_draw))
new_draw = """          var span = (e.max - e.min) || 1;
          var frac = Math.max(0, Math.min(1, (e.val - e.min) / span));
          var kx, ky;
          if (_vert) { kx = tkx; ky = tk0 - (tk0 - tk1) * frac; }   // 由底向上按 frac
          else { kx = tk0 + (tk1 - tk0) * frac; ky = tky; }
          ctx.save();
          ctx.strokeStyle = '#94a3b8';
          ctx.lineWidth = 4;
          ctx.beginPath();
          if (_vert) { ctx.moveTo(kx, tk0); ctx.lineTo(tkx, tk1); }
          else { ctx.moveTo(tk0, tky); ctx.lineTo(tk1, tky); }
          ctx.stroke();
          ctx.fillStyle = '#2563eb';
          ctx.beginPath();
          ctx.arc(kx, ky, 7, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 2;
          ctx.stroke();
          ctx.font = '12px sans-serif';
          ctx.fillStyle = '#334155';
          if (_vert) {
            ctx.textAlign = 'right';
            ctx.textBaseline = 'middle';
            ctx.fillText(fmtNum(e.min), tkx - 10, tk0);
            ctx.fillText(fmtNum(e.max), tkx - 10, tk1);
            ctx.textAlign = 'center';
            ctx.textBaseline = 'bottom';
            ctx.fillStyle = '#1d4ed8';
            ctx.fillText(e.label + ' = ' + fmtNum(e.val), tkx, tk1 - 12);
          } else {
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            ctx.fillText(fmtNum(e.min), tk0, tky + 9);
            ctx.fillText(fmtNum(e.max), tk1, tky + 9);
            ctx.textBaseline = 'bottom';
            ctx.fillStyle = '#1d4ed8';
            ctx.fillText(e.label + ' = ' + fmtNum(e.val), (tk0 + tk1) / 2, tky - 9);
          }
          ctx.restore();"""
s = s.replace(old_draw, new_draw, 1)

# 播放按钮位置：竖直播放按钮在底部
old_pb = "          var pbx = Math.max(tk0, tk1) + 18, pby = tky;"
assert s.count(old_pb) == 1, ("pb", s.count(old_pb))
s = s.replace(old_pb, "          var pbx = _vert ? tkx : Math.max(tk0, tk1) + 18;\n"
                      "          var pby = _vert ? tk0 + 26 : tky;   // 竖直时播放按钮在底部", 1)

# 命中框：方向与轴信息
old_box = """            wsmap[e.label] = { kind: 'slider', label: e.label,
                               playing: playing,
                               playX0: pbx - 12, playX1: pbx + 12, playY0: pby - 12, playY1: pby + 12,
                               x0: Math.min(tk0, tk1) - 10, x1: Math.max(tk0, tk1) + 10,
                               y0: tky - 14, y1: tky + 16, knobX: kx,
                               wx0: e.slider_x, wx1: e.slider_x + (e.slider_len || 3),
                               wy0: e.slider_y };"""
assert s.count(old_box) == 1, ("box", s.count(old_box))
new_box = """            var _ln = e.slider_len || 3;
            wsmap[e.label] = _vert
              ? { kind: 'slider', label: e.label, playing: playing, axis: 'y', vert: true,
                  playX0: pbx - 12, playX1: pbx + 12, playY0: pby - 12, playY1: pby + 12,
                  x0: tkx - 14, x1: tkx + 14, y0: Math.min(tk0, tk1) - 12, y1: Math.max(tk0, tk1) + 12,
                  knobX: kx,
                  wx0: e.slider_x, wx1: e.slider_x + _ln, wy0: e.slider_y, wy1: e.slider_y + _ln }
              : { kind: 'slider', label: e.label, playing: playing, axis: 'x',
                  playX0: pbx - 12, playX1: pbx + 12, playY0: pby - 12, playY1: pby + 12,
                  x0: Math.min(tk0, tk1) - 10, x1: Math.max(tk0, tk1) + 10,
                  y0: tky - 14, y1: tky + 16, knobX: kx,
                  wx0: e.slider_x, wx1: e.slider_x + _ln, wy0: e.slider_y, wy1: e.slider_y };"""
s = s.replace(old_box, new_box, 1)
p.write_text(s, encoding="utf-8")
print("  render2d：竖直渲染 + 按钮置底 + 命中框带轴")

# 2) app.js：sliderValueAt 按轴取值
p = Path("server/static/app.js"); s = p.read_text(encoding="utf-8")
old_v = """  function sliderValueAt(label, wx) {
    var b = widgetBoxes[label];
    var el = findEl(label);
    if (!b || !el || el.min === null || el.min === undefined) return 0;
    var f = (wx - b.wx0) / ((b.wx1 - b.wx0) || 1);"""
assert s.count(old_v) == 1, ("val", s.count(old_v))
s = s.replace(old_v, """  function sliderValueAt(label, wx, wy) {
    var b = widgetBoxes[label];
    var el = findEl(label);
    if (!b || !el || el.min === null || el.min === undefined) return 0;
    var f = (b.axis === 'y') ? (wy - b.wy0) / ((b.wy1 - b.wy0) || 1)
                             : (wx - b.wx0) / ((b.wx1 - b.wx0) || 1);""", 1)
# 调用点补上 wy
s = s.replace("x: sliderValueAt(sldHit, wxp(sx)), y: 0, push: true", "x: sliderValueAt(sldHit, wxp(sx), wyp(sy)), y: 0, push: true", 1)
s = s.replace("var _sv = sliderValueAt(drag.label, wxp(ev.offsetX));", "var _sv = sliderValueAt(drag.label, wxp(ev.offsetX), wyp(ev.offsetY));", 1)
p.write_text(s, encoding="utf-8")
print("  app.js：sliderValueAt 按轴 + 调用点补 wyp")
