"""交互控件命令：Button / CheckBox / InputBox（新「控件」工具组的内核侧）。

设计要点（见 elements.GeoWidget）：
- 控件只保存 caption / target / 锚点坐标，**没有运行时状态**；
- checkbox 的勾选态 = 目标对象当前是否可见（前端读 state 派生）；
- inputbox 的当前文本 = 目标对象当前值（前端读 state 派生）；
- 位置可选传入 ``(x, y)``，缺省放在世界原点附近。
"""
from __future__ import annotations

from typing import List, Tuple

from .cmd_util import label_of, _lookup, _resolve
from .elements import GeoButton, GeoCheckBox, GeoError, GeoInputBox
from .parser import eval_number


def _caption_of(cons, body: str) -> str:
    """控件说明文字：支持 "带引号的文字" 或 已有标签（取该对象的显示值）。"""
    t = body.strip()
    if (t.startswith('"') and t.endswith('"') and len(t) >= 2) or (t.startswith("'") and t.endswith("'") and len(t) >= 2):
        return t[1:-1]
    el = _lookup(cons, t)
    if el is not None:
        return str(getattr(el, "content", None) or getattr(el, "value", None) or t)
    return t


def _pos_of(cons, body: str) -> Tuple[float, float]:
    """可选位置 (x,y)。"""
    t = body.strip()
    try:
        if t.startswith("(") and t.endswith(")"):
            parts = [q.strip() for q in t[1:-1].split(",")]
            if len(parts) != 2:
                raise GeoError("控件位置需要 (x,y)")
            return float(eval_number(cons, parts[0])), float(eval_number(cons, parts[1]))
        v = float(eval_number(cons, t))
        return v, 0.0
    except GeoError:
        raise
    except (ValueError, TypeError, IndexError) as ex:  # 位置参数无法解析为坐标
        raise GeoError("控件位置需要 (x,y): " + str(ex)[:40])


def _target_of(cons, body: str):
    """绑定目标：必须是已存在的对象（checkbox 切显示、inputbox 改数值）。"""
    return _resolve(cons, body.strip())


def _cmd_button(cons, defn, args):
    """``Button[说明, 命令脚本, (x,y)?]`` → 可点击按钮（点击逐行执行脚本）。"""
    if len(args) not in (2, 3):
        raise GeoError('Button 需要 说明 和 命令脚本，如 Button["点我", "A=(1,1)"]')
    el = GeoButton(label_of(defn), defn)
    el.free = False
    el.caption = _caption_of(cons, args[0])
    el.script = _caption_of(cons, args[1])      # 脚本同样支持带引号字符串
    if len(args) == 3:
        el.x, el.y = _pos_of(cons, args[2])
    return cons.add(el)


def _cmd_checkbox(cons, defn, args):
    """``CheckBox[说明, 目标对象, (x,y)?]`` → 复选框：勾选切换目标的显示。"""
    if len(args) not in (2, 3):
        raise GeoError('CheckBox 需要 说明 和 目标对象，如 CheckBox["显示圆", c]')
    tgt = _target_of(cons, args[1])
    el = GeoCheckBox(label_of(defn), defn)
    el.free = False
    el.caption = _caption_of(cons, args[0])
    el.target = tgt.label
    if len(args) == 3:
        el.x, el.y = _pos_of(cons, args[2])
    return cons.add(el)


def _cmd_inputbox(cons, defn, args):
    """``InputBox[目标对象, (x,y)?]`` → 输入框：编辑目标对象的数值。"""
    if len(args) not in (1, 2):
        raise GeoError('InputBox 需要 目标对象，如 InputBox[n]')
    tgt = _target_of(cons, args[0])
    el = GeoInputBox(label_of(defn), defn)
    el.free = False
    el.caption = tgt.label
    el.target = tgt.label
    if len(args) == 2:
        el.x, el.y = _pos_of(cons, args[1])
    return cons.add(el)
