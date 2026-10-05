"""编辑与样式命令（改值/改色/改名/重定义/删除/显隐，P2 结构拆分：从 commands.py 抽出）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .calculus import _fmt
from .cmd_util import _resolve, label_of
from .elements import GeoError, GeoNumber
from .parser import eval_number
from . import macro


__all__ = [
    "_COLOR_NAMES",
    "_cmd_slider",
    "_cmd_setcoords",
    "_cmd_setvalue",
    "_cmd_setlocked",
    "_parse_color",
    "_cmd_delete",
    "_cmd_rename",
    "_cmd_redefine",
    "_cmd_setcolor",
    "_cmd_setvisible",
    "_cmd_macrodelete",
]


_COLOR_NAMES = {
    "red": "#e11d48", "blue": "#2563eb", "green": "#059669", "purple": "#7c3aed",
    "orange": "#ea580c", "teal": "#0d9488", "yellow": "#ca8a04", "gray": "#6b7280",
    "black": "#1a1a1a", "pink": "#db2777", "brown": "#92400e",
}


def _cmd_slider(cons, defn, args):
    """Slider[最小值, 最大值, 步长?, (x,y)?] → 滑动条数值。

    画布上按 GeoGebra 样式绘制成**线段 + 可拖动滑钮**（见前端 render2d）；
    位置缺省时自动排布在左下方（每多一个滑块下移一行）。
    """
    args = list(args)
    pos = None
    if args and args[-1].strip().startswith("("):
        pos = args.pop()
    if len(args) not in (2, 3):
        raise GeoError("Slider 需要 最小值、最大值（可选步长、可选位置 (x,y)）")
    lo = eval_number(cons, args[0])
    hi = eval_number(cons, args[1])
    step = eval_number(cons, args[2]) if len(args) == 3 else (hi - lo) / 100.0
    if hi <= lo:
        raise GeoError("最大值必须大于最小值")
    if step <= 0:
        raise GeoError("步长必须为正")
    el = GeoNumber(label_of(defn), defn, lo)
    el.min, el.max, el.step = lo, hi, step
    if pos is not None:
        parts = [q.strip() for q in pos.strip()[1:-1].split(",")]
        if len(parts) != 2:
            raise GeoError("Slider 位置需要 (x,y)")
        el.slider_x, el.slider_y = eval_number(cons, parts[0]), eval_number(cons, parts[1])
    else:
        n = sum(1 for e in cons.elements.values() if getattr(e, "min", None) is not None)
        el.slider_x, el.slider_y = -6.0, -2.0 - 1.4 * n      # 自动排布（左下方逐行下移）
    el.slider_len = 3.0                                      # 轨道世界长度
    return cons.add(el)

def _cmd_setcoords(cons, defn, args):
    """SetCoords[A, x, y] / SetCoords[A, x, y, z]：程序化移动自由点（脚本）。"""
    if len(args) not in (3, 4):
        raise GeoError("SetCoords 需要 点、x、y（或 x、y、z）")
    pt = _resolve(cons, args[0], ("point",))
    if not pt.free:
        raise GeoError(pt.label + " 是派生对象，不能移动")
    x = eval_number(cons, args[1])
    y = eval_number(cons, args[2])
    pt.x, pt.y = x, y
    if len(args) == 4:
        z = eval_number(cons, args[3])
        pt.z = z
        pt.defn = pt.label + "=(" + _fmt(x) + "," + _fmt(y) + "," + _fmt(z) + ")"
    else:
        if pt.z is not None:
            pt.defn = pt.label + "=(" + _fmt(x) + "," + _fmt(y) + "," + _fmt(pt.z) + ")"
        else:
            pt.defn = pt.label + "=(" + _fmt(x) + "," + _fmt(y) + ")"
    cons._recompute(pt)
    return []

def _cmd_setvalue(cons, defn, args):
    """SetValue[n, v]：设置数值对象（脚本）。"""
    if len(args) != 2:
        raise GeoError("SetValue 需要 数值对象 和 值")
    num = _resolve(cons, args[0], ("number",))
    v = eval_number(cons, args[1])
    num.value = v
    if getattr(num, "min", None) is None:
        num.defn = num.label + "=" + _fmt(v)
    # 滑动条保留 `Slider[...]` defn（见 construction.move 的同类处理）
    cons._recompute(num)
    return []

def _cmd_setlocked(cons, defn, args):
    """SetLocked[对象, true/false]：锁定/解锁对象。"""
    if len(args) != 2:
        raise GeoError("SetLocked 需要 对象 和 true/false")
    el = _resolve(cons, args[0])
    v = args[1].strip().lower()
    if v in ("true", "1", "yes", "锁定"):
        el.locked = True
    elif v in ("false", "0", "no", "解锁"):
        el.locked = False
    else:
        raise GeoError("SetLocked 需要 true 或 false")
    return []

def _parse_color(s: str) -> str:
    s = s.strip().lower()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1].strip()          # 允许 SetColor[A, "#059669"] 这种写法
    if s in _COLOR_NAMES:
        return _COLOR_NAMES[s]
    if re.match(r"^#[0-9a-f]{6}$", s):
        return s
    raise GeoError("未知颜色: " + s + "（可用 red/blue/green/purple/orange/teal/yellow/gray/black 或 #rrggbb）")

def _cmd_delete(cons, defn, args):
    if not args:
        raise GeoError("Delete 需要至少一个对象")
    for a in args:
        el = _resolve(cons, a)
        cons.delete(el.label)
    return []

def _cmd_rename(cons, defn, args):
    if len(args) != 2:
        raise GeoError("Rename 需要 对象 和 新标签")
    old = _resolve(cons, args[0]).label
    new = args[1].strip()
    cons.rename(old, new)
    return []

def _cmd_redefine(cons, defn, args):
    if len(args) != 2:
        raise GeoError("Redefine 需要 对象 和 新定义（如 A=(3,4)）")
    label = _resolve(cons, args[0]).label
    newdefn = args[1].strip()
    cons.redefine(label, newdefn)
    return []

def _cmd_setcolor(cons, defn, args):
    if len(args) != 2:
        raise GeoError("SetColor 需要 对象 和 颜色")
    el = _resolve(cons, args[0])
    el.color = _parse_color(args[1])
    return []

def _cmd_setvisible(cons, defn, args):
    if len(args) != 2:
        raise GeoError("SetVisible 需要 对象 和 true/false")
    el = _resolve(cons, args[0])
    v = args[1].strip().lower()
    if v in ("true", "1", "yes", "显示"):
        el.visible = True
    elif v in ("false", "0", "no", "隐藏"):
        el.visible = False
    else:
        raise GeoError("SetVisible 需要 true 或 false")
    return []

def _cmd_macrodelete(cons, defn, args):
    if len(args) != 1:
        raise GeoError("MacroDelete 需要 宏名")
    from . import macro
    if macro.delete_macro(args[0].strip(), cons):
        return []
    raise GeoError("宏不存在: " + args[0])
