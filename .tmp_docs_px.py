import sys
from pathlib import Path
cnt = int(sys.argv[1])
total = 9 + 18 + 20 + 336 + 23 + 266 + 72 + 496 + 181 + 142 + cnt + 19
p = Path('README.md'); s = p.read_text(encoding='utf-8'); assert len(s) > 20000
a1 = '- **滑块可竖直放置**：'
assert s.count(a1) == 1
s = s.replace(a1, '''- **轨道长度按 px（屏幕恒定）**：`SetSliderLength[滑块, px]`（别名 滑块长度 / 改滑块长度）—— 40–1200 px，**缩放时长度不变**；默认 140px（≈旧观感）；也可在创建时写 `Slider[min,max,step,(x,y),vertical?,px?]`（px 需同时给出步长才无歧义）；长度写入 defn → `.ggk` 往返一致；取值映射改为**屏幕坐标**换算（水平/竖直共用）
''' + a1, 1)
a4 = '- **第八十三批（2026-10-05 ·'
assert s.count(a4) == 1
entry = '''
- **第八十四批（2026-10-05 · 滑块轨道长度按 px（方案 A））**：
  - **需求**：滑块显示长度可自由设置，并以 **px** 表达（屏幕长度恒定）
  - **内核**：`slider_px`（默认 **140**）+ 新命令 `SetSliderLength[滑块, px]`（40–1200，越界报错）；`Slider[…,(x,y),vertical?,px?]` 可在创建时给 px；**defn 仅在非默认时写入 px**（避免既有文本 churn）；`draw()` 序列化 `slider_px`
  - **顺带修 arg 解析两处 bug**：① 曾把 `step` 误当 px（`默认 px=1.0` ✗）→ px 仅在「已有步长」时识别；② 重放 defn 时 pop 顺序错（defn 为 `…,(x,y),vertical,240`）→ 改为**从后往前**剥离：px → vertical → (x,y)
  - **前端**：轨道按 **px** 绘制（`tk1 = tk0 ± px`，竖直向上），命中框新增 `s0/s1/trackPx`；`sliderValueAt(label, sx, sy)` 改用**屏幕坐标**换算
  - **实测**：默认 140px ✓ → `SetSliderLength 240` → 240px ✓；`Slider[…,vertical,200]` → 200px、**朝上**、播放按钮在底部 ✓；`.ggk` 往返 px/方向/步长全保留 ✓；越界报错 ✓；**U 段真实拖动回归通过**（0→7）✓
  - 检测：2D 内核 260 → **266**、2D API 71 → **72**、2D 浏览器 132 → **%d**
''' % cnt
s = s.replace(a4, entry + a4, 1)
import re
s = re.sub(r'2D 前端 1\d\d \+ 代码质量 19 = 1\d\d\d 断言', '2D 前端 %d + 代码质量 19 = %d 断言' % (cnt, total), s, count=1)
p.write_text(s, encoding='utf-8'); print('README：%d 行' % len(s.splitlines()))
p = Path('CHANGELOG.md'); s = p.read_text(encoding='utf-8')
a = '- **第八十三批：滑块可竖直放置（2026-10-05）**'
assert s.count(a) == 1
add = ('- **第八十四批：滑块轨道长度按 px（2026-10-05）**：① `slider_px`（默认 140）+ `SetSliderLength[滑块, px]`（40–1200）；'
       '`Slider[…,(x,y),vertical?,px?]` 创建时可用；defn 仅非默认时写 px，`draw()` 序列化；'
       '② 修 arg 解析两 bug（step 误判为 px；重放时 pop 顺序错 → 改为从后往前 px→vertical→(x,y)）；'
       '③ 前端轨道按 px 绘制（竖直向上）+ 命中框 s0/s1/trackPx + 取值改屏幕坐标换算；'
       '④ 实测 140→240/竖直 200 朝上/`.ggk` 往返/越界报错/U 段拖动回归通过；⑤ 检测：2D 内核 **266**、2D API **72**、2D 浏览器 **%d**，全量 **%d 断言**、11/11 全绿\n' % (cnt, total))
p.write_text(s.replace(a, add + a, 1), encoding='utf-8'); print('CHANGELOG：%d 行' % len(s.splitlines()))
