"""嵌套命令求值（P2 结构拆分：从 commands.py 抽出）。

形如 `k=Cone[Circle[O,2],3]` 的参数里可以内联命令调用；本模块负责就地把它们
求值成**匿名辅助元素**（不注册、不进撤销快照/序列化，只挂在父元素 deps 上，
父元素 defn 保留用户原始写法，故 .ggk/.ggb 往返与撤销重放都能复现）。

依赖方向：nested → registry（命令表）→ 各命令组模块；cmd_util 是共享工具层。
导入本模块即完成 `cmd_util.set_nested_evaluator` 钩子注入（`_lookup` 使用）。
"""

from __future__ import annotations

from typing import List

from .cmd_util import (_NESTED_CALL_RE, _NESTED_MAX_DEPTH, _nested_depth,
                       set_nested_evaluator)
from .elements import GeoError
from .parser import _split_commas
from .registry import ALIASES, COMMANDS, _label_kind


class _DetachedConstruction:
    """嵌套命令求值用的影子构造。

    依赖仍从父构造的 elements 查找，但新元素**不注册**（匿名辅助对象：
    不进对象列表 / 撤销快照 / 序列化），只作为依赖挂在父元素的 deps 上。
    父元素的 defn 保留用户原始写法（如 `k=Cone[Circle[O,2],3]`），
    因此撤销、.ggk/.ggb 往返重放时会重新求值出同样的匿名依赖。
    """

    def __init__(self, cons, depth: int) -> None:
        self._cons = cons
        self.elements = cons.elements       # 共享查找表（只读使用）
        self.created: List = []
        self._seq = 0
        self._nested_depth = depth

    def add(self, el):
        self.created.append(el)
        if not getattr(el, "free", False):
            el.compute()
        return el

    def auto_label(self, kind):
        self._seq += 1
        return "_n%d_%s" % (self._seq, kind)

    def _recompute(self, el):
        return self._cons._recompute(el)

    def get(self, label):
        return self._cons.get(label)

    def push_history(self):
        pass


def _eval_nested(cons, text: str):
    """就地求值一个嵌套命令调用，返回匿名辅助元素（不注册）。"""
    t = text.strip()
    m = _NESTED_CALL_RE.match(t)
    if m is None:
        raise GeoError("无法解析嵌套命令: " + t)
    depth = _nested_depth(cons)
    if depth >= _NESTED_MAX_DEPTH:
        raise GeoError("嵌套命令层数过深（最多 %d 层）: %s" % (_NESTED_MAX_DEPTH, t))
    name, inner = m.group(1), m.group(2)
    lname = name.lower()
    lname = ALIASES.get(lname, lname)          # 中文别名归一化
    handler = COMMANDS.get(lname)
    if handler is None:
        raise GeoError("嵌套命令中不支持命令 " + name + "：请先用一条独立语句创建该对象，再用其标签作为参数")
    args = [a for a in _split_commas(inner) if a != ""]
    shadow = _DetachedConstruction(cons, depth + 1)
    label = shadow.auto_label(_label_kind(cons, lname, args))
    defn = label + "=" + t
    if lname in ("intersect", "extremum", "focus", "tangent"):
        created = handler(shadow, defn, args, None)
    else:
        created = handler(shadow, defn, args)
    els = created if isinstance(created, list) else [created]
    els = [e for e in els if e is not None]
    if not els:
        raise GeoError("嵌套命令未产生结果: " + t)
    res = els[0]
    if getattr(res, "error", None):
        raise GeoError("嵌套命令失败 " + t + "：" + str(res.error))
    return res


# 注入钩子：cmd_util._lookup 遇到 `Cmd[...]` 时调用本函数就地求值
set_nested_evaluator(_eval_nested)
