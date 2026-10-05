import sys
from pathlib import Path
cnt, total = int(sys.argv[1]), int(sys.argv[2])
p = Path('README.md'); s = p.read_text(encoding='utf-8'); assert len(s) > 20000
a1 = '- **滑块是「动态参数」的主力**：'
assert s.count(a1) == 1
s = s.replace(a1, '- **滑块可竖直放置**：`Slider[min,max,step,(x,y),vertical]`（或用命令 `SetSliderVertical[滑块, true/false]`）—— 轨道沿 +y、'
                 'min 在底 max 在顶、数值标注在左侧、**播放按钮在轨道底部**；竖直/水平的拖动与播放功能完全一致（取值按轴换算）\n' + a1, 1)
a4 = '- **第八十二批（2026-10-05 ·'
assert s.count(a4) == 1
entry = '\n'.join([
    '- **第八十三批（2026-10-05 · 滑块可竖直放置，播放按钮置底）**：',
    '  - **需求**：滑块还可以竖直放置；播放按钮置于底部；功能不变',
    '  - **内核**：`Slider[最小值, 最大值, 步长?, (x,y)?, vertical?]` 新增可选 `vertical` 关键字（也接受 `v` / `竖直`）；`GeoNumber.draw()` 序列化 `slider_vert`；新增命令 `SetSliderVertical[滑块, true/false]`（别名 滑块方向/竖直滑块）；`_regen_defn` 带上该标志 → `.ggk` 往返一致',
    '  - **前端**：`render2d` 按 `slider_vert` 分支绘制（轨道沿 +y、min 在底、max 在顶、数值标注在左侧、**播放按钮在轨道底部**）；命中框新增 `axis`（`x`/`y`）与 `knobY`；`sliderValueAt(label, wx, wy)` 按轴取值（拖动/播放语义不变）',
    '  - **实测**：`vtS=Slider[0,10,1,(-2,2),vertical]` → 命中框 `axis=y`、轨道世界长 3、**播放按钮位于轨道底部之下**（`playY0 > y1`）✓；值 5（区间 0..10）→ 滑钮**纵向居中**（`knobY == 中点`）✓；零新增 JS 错误 ✓',
    '  - **遗留（已写明）**：竖直滑块的**值拖动**未纳入用例覆盖（合成 pointerdown 驱动不稳，且播放按钮紧贴轨道底部容易互相干扰）—— 轴感知取值由代码复用同一路径实现，待补 UI 级用例',
    '  - **命名坑（已修）**：命令表按「display name 小写 == key」分发，故 key 定为 `setslidervertical`，`SetSliderVertical[…]` 在命令栏可直接输入 ✓',
    '  - 检测：2D 浏览器 129 → **%d**' % cnt,
    '',
])
s = s.replace(a4, entry + a4, 1)
import re
s = re.sub(r'2D 前端 12\d \+ 代码质量 19 = 17\d\d 断言', '2D 前端 %d + 代码质量 19 = %d 断言' % (cnt, total), s, count=1)
p.write_text(s, encoding='utf-8'); print('README：%d 行' % len(s.splitlines()))
p = Path('CHANGELOG.md'); s = p.read_text(encoding='utf-8')
a = '- **第八十二批：动画速度/方向可调 + 多滑块同步（2026-10-05）**'
assert s.count(a) == 1
s = s.replace(a, '- **第八十三批：滑块可竖直放置（2026-10-05）**：① `Slider[…,(x,y),vertical]` 支持竖直（也接受 v/竖直），序列化 `slider_vert`；'
                 '② 新命令 `SetSliderVertical[滑块,true/false]`（别名 滑块方向/竖直滑块），`_regen_defn` 带该标志 → `.ggk` 往返；'
                 '③ 前端按方向分支绘制（轨道沿 +y、min 底 max 顶、**播放按钮在轨道底部**），命中框加 `axis`/`knobY`，按轴取值；'
                 '④ 实测轴=y、按钮在底部、值 5 → 滑钮纵向居中；⑤ 竖直播动路径未纳入用例（已写明）；⑥ 检测：2D 浏览器 **%d**，全量 **%d 断言**、11/11 全绿\n' % (cnt, total) + a, 1)
p.write_text(s, encoding='utf-8'); print('CHANGELOG：%d 行' % len(s.splitlines()))
