"""杂项命令（随机数/线框显示，P2 结构拆分）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .cmd_util import _resolve, label_of
from .elements import GeoError, GeoNumber
from .parser import eval_number


__all__ = [
    "_cmd_randombetween",
    "_cmd_randomize",
    "_cmd_setwire",
]


def _cmd_randombetween(cons, defn, args):
    """RandomBetween[min, max]：闭区间随机整数（创建时落定；Randomize 重滚）。"""
    if len(args) != 2:
        raise GeoError("RandomBetween 需要 最小值, 最大值")
    lo = int(eval_number(cons, args[0]))
    hi = int(eval_number(cons, args[1]))
    if hi < lo:
        raise GeoError("最大值必须不小于最小值")
    import random
    el = GeoNumber(label_of(defn), defn, float(random.randint(lo, hi)))
    el._random_src = (lo, hi)
    return cons.add(el)

def _cmd_randomize(cons, defn, args):
    """Randomize[A]：把 RandomBetween 数值重新随机（抛硬币/掷骰模拟）。"""
    if len(args) != 1:
        raise GeoError("Randomize 需要一个对象")
    from . import memo as _memo
    _memo.clear()          # 随机结果不参与计算记忆，清空以确保依赖它的对象重新生成
    el = _resolve(cons, args[0], ("number",))
    src = getattr(el, "_random_src", None)
    if not src:
        raise GeoError(el.label + " 不是 RandomBetween 创建的数值（无随机源）")
    import random
    el.value = float(random.randint(src[0], src[1]))
    el.defn = el.label + "=RandomBetween[" + str(src[0]) + "," + str(src[1]) + "]"
    cons._recompute(el)
    return []

def _cmd_setwire(cons, defn, args):
    """SetWire[label, true/false]：3D 物体线框显示模式。"""
    if len(args) != 2:
        raise GeoError("SetWire 需要 对象 和 true/false")
    el = _resolve(cons, args[0])
    if el.kind != "geo3d":
        raise GeoError("线框模式仅适用于 3D 物体")
    v = args[1].strip().lower()
    if v in ("true", "1", "yes", "线框"):
        el.wire = True
    elif v in ("false", "0", "no", "实体"):
        el.wire = False
    else:
        raise GeoError("SetWire 需要 true 或 false")
    return []
