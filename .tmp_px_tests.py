from pathlib import Path
import json

# 1) 内核
p = Path("devtools/test_2d_matrix.py"); s = p.read_text(encoding="utf-8")
anchor = 'print("\\n" + "=" * 60)'
i = s.rindex(anchor)
sec = '''# ---------------------------------------------------------------------------
section("Z17. 滑块轨道长度按 px（SetSliderLength）")

_ll = Construction()
_ll.process("sL2=Slider[0,10,1,(0,0)]")
check("默认轨道长度 140px 且 defn 文本不变（非默认才写 px）",
      abs(_ll.elements["sL2"].slider_px - 140) < 1e-9 and _ll.elements["sL2"].defn == "sL2=Slider[0,10,1,(0,0)]",
      "px=%.0f defn=%r" % (_ll.elements["sL2"].slider_px, _ll.elements["sL2"].defn))
_ll.process("SetSliderLength[sL2, 240]")
check("SetSliderLength 改 px 并写入 defn",
      abs(_ll.elements["sL2"].slider_px - 240) < 1e-9 and _ll.elements["sL2"].defn == "sL2=Slider[0,10,1,(0,0),240]",
      "%r" % _ll.elements["sL2"].defn)
_ll.process("SetSliderVertical[sL2, true]")
check("与竖直共存：defn 顺序 (x,y),vertical,px 且可重放",
      _ll.elements["sL2"].defn == "sL2=Slider[0,10,1,(0,0),vertical,240]"
      and abs(_ll.elements["sL2"].slider_px - 240) < 1e-9 and _ll.elements["sL2"].slider_vert is True,
      "%r" % _ll.elements["sL2"].defn)
_dll = _json_mod.loads(_ll.save_json())
_ll2 = Construction(); _ll2.load_json(_json_mod.dumps(_dll))
check(".ggk 往返保留 px 与方向", abs(_ll2.elements["sL2"].slider_px - 240) < 1e-9
      and _ll2.elements["sL2"].slider_vert is True and _ll2.elements["sL2"].step == 1,
      "px=%.0f vert=%s" % (_ll2.elements["sL2"].slider_px, _ll2.elements["sL2"].slider_vert))
_msg_ll = _ll.process("SetSliderLength[sL2, 20]")
check("长度越界 → 明确报错", "px" in (_msg_ll or ""), (_msg_ll or "")[:32])
check("draw() 暴露 slider_px（供前端按 px 绘制）",
      abs(float(_ll.elements["sL2"].draw((0, 0, 1, 1)).get("slider_px", 0)) - 240) < 1e-9, "")

'''
s = s[:i] + sec + s[i:]
p.write_text(s, encoding="utf-8")
print("内核：Z17 段（6 断言）")

# 2) API
p = Path("devtools/test_2d_api.py"); s = p.read_text(encoding="utf-8")
i2 = s.rindex(anchor)
api = '''# ---------------------------------------------------------------------------
section("S2. 滑块长度按 px 经 HTTP")

clear()
put("sPx=Slider[0,10,1,(0,0)]")
put("SetSliderLength[sPx, 300]")
_sPx = {e.get("label"): e for e in state()}.get("sPx") or {}
check("API：slider_px=300 且 defn 同步", abs(float(_sPx.get("slider_px", 0)) - 300) < 1e-9
      and "(0,0),300]" in str(_sPx.get("defn")), "%s | %s" % (_sPx.get("slider_px"), _sPx.get("defn")))

'''
s = s[:i2] + api + s[i2:]
p.write_text(s, encoding="utf-8")
print("API：S2 段（1 断言）")

# 3) 浏览器：轨道像素长度（确定性，无需指针）
p = Path("devtools/verify_2d_ui_matrix.js"); s = p.read_text(encoding="utf-8")
anchor3 = "  check('竖直滑块无新增 JS 错误', JS_ERRORS.length === vtErrBefore,"
assert s.count(anchor3) == 1
block = """  // 轨道长度按 px（屏幕长度恒定）：默认 140，SetSliderLength 后随之变化
  const pxTrack0 = await page.evaluate(() => {
    const b = window.__ggbpyDebug.widgetBoxes()['vtS']; return b ? Math.round(Math.abs(b.s1 - b.s0)) : -1;
  });
  await typeCmd('SetSliderLength[vtS, 260]');
  await page.waitForTimeout(350);
  const pxTrack1 = await page.evaluate(() => {
    const b = window.__ggbpyDebug.widgetBoxes()['vtS']; return b ? Math.round(Math.abs(b.s1 - b.s0)) : -1;
  });
  check('轨道长度按 px（默认 140 → SetSliderLength 260 后 260，竖直同样生效）',
        pxTrack0 === 140 && pxTrack1 === 260, 'px ' + pxTrack0 + '→' + pxTrack1);
""" + anchor3
s = s.replace(anchor3, block, 1)
p.write_text(s, encoding="utf-8")
print("浏览器：+1 断言（px 轨道长度）")
