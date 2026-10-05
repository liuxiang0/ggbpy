"""动画：速度/方向可调 + 多滑块共用定时器同步播放。"""
from pathlib import Path

# 1) app.js：重写播放内核（多滑块同步 + 设置）
p = Path("server/static/app.js"); s = p.read_text(encoding="utf-8")
_a = s.index("  function sliderPlay(label) {")
_b = s.index("\n  }\n", _a) + len("\n  }\n")     # 函数结束（含换行）
_old = s[_a:_b]
assert "clearInterval(playState.timer)" in _old and len(_old) < 1400, ("old fn", len(_old))
new = '''  var anim = { ms: 90, dir: 'up' };     // 动画设置：步间隔(ms)、方向 up / down / bounce
  // 播放状态：多个滑块**共用一个定时器** → 真正同步；labels[label] 记录各自当前方向
  function isPlaying(label) { return !!(playState && playState.labels[label]); }
  function playingLabels() { return playState ? Object.keys(playState.labels) : []; }
  function sliderLabels() {
    var out = [];
    for (var i = 0; i < elements.length; i++) {
      var e = elements[i];
      if (e.kind === 'number' && e.min !== null && e.min !== undefined) out.push(e.label);
    }
    return out;
  }
  function stopPlay() {
    if (playState) { clearInterval(playState.timer); playState = null; }
  }
  function startPlay(labels) {
    var map = {};
    for (var i = 0; i < labels.length; i++) map[labels[i]] = (anim.dir === 'bounce') ? 'up' : anim.dir;
    if (!Object.keys(map).length) return;
    stopPlay();
    playState = { labels: map, timer: setInterval(animTick, anim.ms) };
  }
  function animTick() {
    if (!playState) return;
    var labs = Object.keys(playState.labels), alive = 0;
    for (var i = 0; i < labs.length; i++) {
      var L = labs[i], el = null;
      for (var j = 0; j < elements.length; j++) {
        if (elements[j].label === L && elements[j].min !== undefined) el = elements[j];
      }
      if (!el) { delete playState.labels[L]; continue; }     // 对象已删除 → 退出该滑块
      alive++;
      var step = el.step > 0 ? el.step : 0;
      var v = el.val + (playState.labels[L] === 'down' ? -step : step);
      if (v > el.max + 1e-9) {
        if (anim.dir === 'bounce') { playState.labels[L] = 'down'; v = el.max - step; }
        else v = el.min;
      } else if (v < el.min - 1e-9) {
        if (anim.dir === 'bounce') { playState.labels[L] = 'up'; v = el.min + step; }
        else v = el.max;
      }
      api('POST', '/api/drag', { label: L, x: v, y: 0, push: false }, function (d) {
        if (d && d.elements) { elements = d.elements; render(); }
      });
    }
    if (!alive) { stopPlay(); render(); }
  }
  function playToggle(label) {                    // 在播则退出，未播则加入（与在播的同步）
    if (!playState) { startPlay([label]); return; }
    if (playState.labels[label]) {
      delete playState.labels[label];
      if (!Object.keys(playState.labels).length) stopPlay();
    } else {
      playState.labels[label] = (anim.dir === 'bounce') ? 'up' : anim.dir;
      clearInterval(playState.timer);
      playState.timer = setInterval(animTick, anim.ms);
    }
  }
  function sliderPlay(label) { playToggle(label); render(); }
'''
s = s[:_a] + new + s[_b:]
p.write_text(s, encoding="utf-8")
print("  app.js：多滑块同步播放内核 + anim 设置 + 钩子")

# 2) app.js：顶栏三个按钮（全部播放/全部暂停/动画设置）
a = "  btn('btn-zoomin', function () {"
assert s.count(a) == 1, ("btn", s.count(a))
s = p.read_text(encoding="utf-8")
s = s.replace(a, '''  btn('btn-anim-play', function () {
    var ls = sliderLabels();
    if (!ls.length) { setMsg(t('animNone'), true); return; }
    startPlay(ls);
    setMsg(t('animPlay') + ': ' + ls.length + ' · ' + anim.ms + 'ms / ' + anim.dir, false);
  });
  btn('btn-anim-stop', function () { stopPlay(); render(); setMsg(t('animStop'), false); });
  btn('btn-anim-set', function () {
    var v = prompt(t('animSettings'), anim.ms + ',' + anim.dir);
    if (v === null) return;
    var sp = String(v).split(',');
    var ms = parseFloat(sp[0]);
    if (ms >= 10 && ms <= 2000) anim.ms = ms;
    var d = (sp[1] || '').trim();
    if (d === 'up' || d === 'down' || d === 'bounce') anim.dir = d;
    if (playState) { var ls = playingLabels(); stopPlay(); startPlay(ls); }   // 立即生效
    setMsg(t('animSet') + ': ' + anim.ms + 'ms / ' + anim.dir, false);
  });

''' + a, 1)
p.write_text(s, encoding="utf-8")
print("  app.js：顶栏动画按钮")

# 3) 状态：暴露 playingLabels
old_case = "      case 'playState': return playState;"
assert s.count(old_case) == 1
s = p.read_text(encoding="utf-8")
s = s.replace(old_case, old_case + "\n      case 'playingLabels': return playState ? Object.keys(playState.labels) : [];", 1)
p.write_text(s, encoding="utf-8")
print("  app.js：playingLabels 状态")

# 4) panels.js / render2d.js：改为按 playingLabels 判断
p = Path("server/static/panels.js"); s = p.read_text(encoding="utf-8")
old = "var pbSym = (playState && playState.label === e.label) ? '⏸' : '▶';"
assert s.count(old) == 1, ("panels", s.count(old))
s = s.replace(old, "var pbSym = (env.get('playingLabels') || []).indexOf(e.label) >= 0 ? '⏸' : '▶';", 1)
p.write_text(s, encoding="utf-8")
p = Path("server/static/render2d.js"); s = p.read_text(encoding="utf-8")
old2 = """          var _ps = env.get('playState');
          var playing = !!(_ps && _ps.label === e.label);"""
assert s.count(old2) == 1, ("r2d", s.count(old2))
s = s.replace(old2, "          var playing = (env.get('playingLabels') || []).indexOf(e.label) >= 0;", 1)
p.write_text(s, encoding="utf-8")
print("  panels/render2d：按 playingLabels 判断")

# 5) index.html：三个按钮
p = Path("server/static/index.html"); s = p.read_text(encoding="utf-8")
a2 = '    <button id="btn-home" data-i18n="tool_home" title="复位视图">⌂ 复位</button>'
assert s.count(a2) == 1, ("html", s.count(a2))
s = s.replace(a2, a2 + '''
    <button id="btn-anim-play" data-i18n="animPlay">▶ 全部播放</button>
    <button id="btn-anim-stop" data-i18n="animStop">⏸ 全部暂停</button>
    <button id="btn-anim-set" data-i18n="animSettings">⚙ 动画设置</button>''', 1)
p.write_text(s, encoding="utf-8")
print("  index.html：三个动画按钮")

# 6) i18n
p = Path("server/static/i18n.js"); s = p.read_text(encoding="utf-8")
zh = "widgetEditSlider: '滑块参数：最小值,最大值,步长', widgetEditSliderBad: '格式：最小值,最大值,步长',"
assert s.count(zh) == 1
s = s.replace(zh, zh + " animPlay: '全部播放', animStop: '全部暂停', animSettings: '动画设置：步间隔ms,方向(up/down/bounce)', animSet: '动画已设为', animNone: '没有可播放的滑块',", 1)
en = "widgetEditSlider: 'Slider: min,max,step', widgetEditSliderBad: 'Format: min,max,step',"
assert s.count(en) == 1
s = s.replace(en, en + " animPlay: 'Play all', animStop: 'Stop all', animSettings: 'Animation: interval ms,direction(up/down/bounce)', animSet: 'Animation set to', animNone: 'No sliders to play',", 1)
p.write_text(s, encoding="utf-8")
print("  i18n：5 个动画词条（中英）")
