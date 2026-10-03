#!/usr/bin/env python3
"""前端模块状态绑定交叉检查（前端拆分配套守卫）。

模块里每个 `get('X')` 必须能在 app.js 的 `_panelStateGet` 找到 `case 'X'`；
每个 `set('X', …)` 必须能在 `_panelStateSet` 找到 `k === 'X'` 分支。

动机（真实事故）：scene3d 抽取时只给 4 个调试计数补了 setter，忘了 getter →
`get('dbgX')` 返回 undefined → `undefined + 1 = NaN` → 遮挡/复用计数全失效，
只有行为测试才发现。本检查可静态拦住。

用法：python3 devtools/check_state_bindings.py    （退出码 0 干净 / 1 有缺失）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "server" / "static" / "app.js"
SKIP = {"app.js", "data.js", "i18n.js"}


def main() -> int:
    app = APP.read_text(encoding="utf-8")
    get_sec = app[app.index("function _panelStateGet(k)"):app.index("function _panelStateSet(k, v)")]
    set_sec = app[app.index("function _panelStateSet(k, v)"):app.index("var _panels = window.GGB_PANELS.create")]
    bad = []
    mods = [p for p in sorted((ROOT / "server" / "static").glob("*.js")) if p.name not in SKIP]
    for m in mods:
        src = m.read_text(encoding="utf-8")
        for n in sorted(set(re.findall(r"get\('([A-Za-z_$][\w$]*)'\)", src))):
            if ("case '%s':" % n) not in get_sec:
                bad.append("%s: get('%s') 缺 getter case" % (m.name, n))
        for n in sorted(set(re.findall(r"set\('([A-Za-z_$][\w$]*)'", src))):
            if ("k === '%s'" % n) not in set_sec:
                bad.append("%s: set('%s') 缺 setter 分支" % (m.name, n))
    for b in bad:
        print("FAIL " + b)
    if not bad:
        print("OK   状态绑定交叉检查：模块 %d 个，全部 get/set 均有对应分支" % len(mods))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
