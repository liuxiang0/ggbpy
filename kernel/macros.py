"""自定义宏命令（MacroCreate/MacroList，P2 结构拆分）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .elements import GeoError
from . import macro


__all__ = [
    "_cmd_macrocreate",
    "_cmd_macrolist",
]


def _cmd_macrocreate(cons, defn, args):
    """MacroCreate[名称, {输入}, {输出}]：从当前构造创建宏。"""
    if len(args) != 3:
        raise GeoError("MacroCreate 需要 名称、输入对象集合、输出对象集合")
    from . import macro
    name = args[0].strip()
    inputs = [s.strip() for s in args[1].strip("{}").split(",") if s.strip()]
    outputs = [s.strip() for s in args[2].strip("{}").split(",") if s.strip()]
    try:
        m = macro.create_macro(cons, name, inputs, outputs)
    except ValueError as e:
        raise GeoError(str(e))
    return [cons.get(outputs[0])] if outputs and outputs[0] in cons.elements else []

def _cmd_macrolist(cons, defn, args):
    from . import macro
    ms = macro.list_macros(cons)
    if not ms:
        raise GeoError("暂无宏")
    return []
