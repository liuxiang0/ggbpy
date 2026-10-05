from pathlib import Path
p = Path("README.md"); s = p.read_text(encoding="utf-8"); assert len(s) > 20000
a1 = "- **滑块参数就地在对象列表里改**："
assert s.count(a1) == 1
s = s.replace(a1, """- **画布滑块右侧有 ▶ / ⏸ 播放切换**：点 ▶ 让参数自动播放（每 90ms 按步长推进、到最大值回到最小值，与对象列表的 ▶ 同一实现），
  播放中图标变 **⏸**，再点即暂停；只有播放中的滑块会动画，且在播放框上点击不会被「画布交互自动停止播放」抢先
""" + a1, 1)
a4 = "- **第八十批（2026-10-05 ·"
assert s.count(a4) == 1
entry = "\n".join([
    "- **第八十一批（2026-10-05 · 画布滑块加 ▶/⏸ 播放切换）**：",
    "  - **需求**：在滑块右侧加播放三角 ▶，点击后变 ⏸，来回切换",
    "  - **实现**：`render2d` 在轨道右侧画播放圆钮（▶ 绿 / ⏸ 红），命中框写入 `widgetBoxes[label]`（新增 `playX0/X1/Y0/Y1` 与 `playing`，便于断言与诊断）；`app.js` 新增 `sliderPlayAt(sx,sy)`，在画布 `pointerdown` 中**优先**处理 → 调用已有的 `sliderPlay(label)`（本身就是开关）",
    "  - **顺带修一个真 UX bug**：`pointerdown` 开头的「画布交互自动停止播放」会**先停再启** → 点播放钮永远只能重播、无法暂停 ✗ → 改为「点在 ▶/⏸ 上时不先停」✓",
    "  - **实测**：初始 `playing=false` 且命中判定正确 ✓ → 点 ▶ → `playLabel=seS`、`playing=true`（图标 ⏸）✓ → 再点 → `playLabel=null`、`playing=false`（回到 ▶）✓",
    "  - **排障记录**：全量矩阵里对象列表面板会覆盖画布该位置 → 真实鼠标点击落到列表行（实测启动了**另一个**滑块的播放）；另发现 Y 段与 U 段滑块**位置相同导致命中框重叠** → 已错开位置并在段首清理残留播放",
    "  - 检测：2D 浏览器 120 → **123**（数字取自实际输出）",
    "",
])
s = s.replace(a4, entry + a4, 1)
a5 = "2D 前端 120 + 代码质量 19 = 1695 断言"
assert s.count(a5) == 1
s = s.replace(a5, "2D 前端 123 + 代码质量 19 = 1698 断言", 1)
assert len(s) > 20000
p.write_text(s, encoding="utf-8"); print("README：%d 行" % len(s.splitlines()))

p = Path("CHANGELOG.md"); s = p.read_text(encoding="utf-8")
a = "- **第八十批：滑块范围编辑入口做实（列表行 ⚙）（2026-10-05）**"
assert s.count(a) == 1
add = ("- **第八十一批：画布滑块 ▶/⏸ 播放切换（2026-10-05）**：① `render2d` 在轨道右侧绘制播放圆钮（▶/⏸，`widgetBoxes` 暴露 playX0/playing 便于断言）；"
       "② `app.js` 加 `sliderPlayAt` 并在画布 pointerdown 优先处理 → 复用既有 `sliderPlay`（开关）；③ **修 UX bug**：pointerdown 开头的「画布交互自动停止播放」使点播放钮变成先停再启、永远无法暂停 → 改为点在 ▶/⏸ 上不先停；"
       "④ 实测：▶ → playing=true（⏸）；再点 → playing=false（▶）；⑤ 检测：2D 浏览器 **123**，全量 **1698 断言**、11/11 全绿\n")
p.write_text(s.replace(a, add + a, 1), encoding="utf-8"); print("CHANGELOG：%d 行" % len(s.splitlines()))
