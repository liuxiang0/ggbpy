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
from .parser import eval_number
from .elements import GeoButton, GeoCheckBox, GeoError, GeoInputBox
from .tolerance import COORD

# 滑块轨道长度的像素范围（屏幕量）
SLIDER_PX_DEFAULT = 140.0
SLIDER_PX_MIN = 40.0
SLIDER_PX_MAX = 1200.0
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


def _num_txt(v) -> str:
    """坐标/数值的紧凑文本（避免 1.0 变 1.000000）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f - round(f)) < COORD:
        return str(int(round(f)))
    return ("%.6f" % f).rstrip("0").rstrip(".")


def _esc(t: str) -> str:
    """defn 里的字符串转义（与前端一致：双引号换单引号）。"""
    return str(t).replace('"', "'")


def _regen_defn(el) -> str:
    """按控件当前字段重写 defn（位置/说明/脚本/绑定目标变化后调用，保证 .ggk 往返一致）。"""
    lab = el.label
    if isinstance(el, GeoButton):
        return '%s=Button["%s","%s",(%s,%s)]' % (lab, _esc(el.caption), _esc(el.script),
                                                _num_txt(el.x), _num_txt(el.y))
    if isinstance(el, GeoCheckBox):
        return '%s=CheckBox["%s",%s,(%s,%s)]' % (lab, _esc(el.caption), el.target,
                                                _num_txt(el.x), _num_txt(el.y))
    if isinstance(el, GeoInputBox):
        return "%s=InputBox[%s,(%s,%s)]" % (lab, el.target, _num_txt(el.x), _num_txt(el.y))
    if getattr(el, "kind", "") == "number" and getattr(el, "min", None) is not None:
        _v = ",vertical" if getattr(el, "slider_vert", False) else ""
        _px = getattr(el, "slider_px", SLIDER_PX_DEFAULT)
        _p = "" if abs(_px - SLIDER_PX_DEFAULT) < COORD else "," + _num_txt(_px)
        return "%s=Slider[%s,%s,%s,(%s,%s)%s%s]" % (lab, _num_txt(el.min), _num_txt(el.max),
                                                   _num_txt(el.step), _num_txt(el.slider_x),
                                                   _num_txt(el.slider_y), _v, _p)
    return el.defn


def _cmd_setcaption(cons, defn, args):
    """``SetCaption[控件|文本, "新说明"]`` → 改说明文字（控件重写 defn，文本改内容）。"""
    if len(args) != 2:
        raise GeoError('SetCaption 需要 对象 和 文字，如 SetCaption[btn, "开始"]')
    el = _resolve(cons, args[0])
    txt = _caption_of(cons, args[1])
    if isinstance(el, (GeoButton, GeoCheckBox)):
        el.caption = txt
        el.defn = _regen_defn(el)
        return []
    if getattr(el, "kind", "") == "text":
        el.content = txt
        el.defn = '%s=Text["%s",(%s,%s)]' % (el.label, _esc(txt), _num_txt(el.x), _num_txt(el.y))
        return []
    raise GeoError("SetCaption 需要 按钮/复选框 或 文本（当前是 %s）" % getattr(el, "kind", "?"))


def _cmd_setscript(cons, defn, args):
    """``SetScript[按钮, "命令1;命令2"]`` → 改按钮脚本（多条用 ; 或换行分隔）。"""
    if len(args) != 2:
        raise GeoError('SetScript 需要 按钮 和 脚本，如 SetScript[btn, "A=(1,1)"]')
    el = _resolve(cons, args[0])
    if not isinstance(el, GeoButton):
        raise GeoError("SetScript 需要 按钮（当前是 %s）" % getattr(el, "kind", "?"))
    el.script = _caption_of(cons, args[1])
    el.defn = _regen_defn(el)
    return []


def _cmd_setwidgetpos(cons, defn, args):
    """``SetWidgetPos[控件|滑动条, (x,y)]`` → 移动锚点，并同步重写 defn（.ggk 往返一致）。

    拖动控件/滑块位置时由前端调用；滑块的**当前值不受影响**（.ggk 的 values 另存）。
    """
    if len(args) != 2:
        raise GeoError("SetWidgetPos 需要 控件/滑动条 和 (x,y)")
    el = _resolve(cons, args[0])
    x, y = _pos_of(cons, args[1])
    if isinstance(el, GeoButton):
        el.x, el.y = x, y
        el.defn = _regen_defn(el)
        return []
    if isinstance(el, GeoCheckBox):
        el.x, el.y = x, y
        el.defn = _regen_defn(el)
        return []
    if isinstance(el, GeoInputBox):
        el.x, el.y = x, y
        el.defn = _regen_defn(el)
        return []
    if getattr(el, "kind", "") == "number" and getattr(el, "min", None) is not None:
        el.slider_x, el.slider_y = x, y
        el.defn = _regen_defn(el)
        return []
    raise GeoError("SetWidgetPos 需要 交互控件 或 滑动条（当前是 %s）" % getattr(el, "kind", "?"))


def _cmd_setinput(cons, defn, args):
    """``SetInput[目标, "文本"]`` → 输入框提交：按内容自动选择语义。

    - **自由数值/滑块 + 纯数值** → 只改值（保留 `Slider[…]` 定义，见 construction.move 的同类规则）
    - **其它情况**（表达式、坐标、受控对象）→ 重定义为 ``目标=文本``（自动重新挂依赖，见 exprdeps）
    这样输入框既能改值，也能直接写 ``s*2``、``(2,3)``、``x^2`` 这类定义（与 GeoGebra 输入框一致）。
    """
    if len(args) != 2:
        raise GeoError('SetInput 需要 目标 和 文本，如 SetInput[n, "s*2"]')
    tgt = _resolve(cons, args[0])
    text = _caption_of(cons, args[1]).strip()
    if not text:
        raise GeoError("SetInput 文本不能为空")
    free_num = getattr(tgt, "kind", "") == "number" and getattr(tgt, "free", False)
    if free_num:
        # 文本引用已有数值元素（如 s+1）→ 重定义成受控对象（之后跟随滑块）；
        # 纯数值 → 只改值（滑块保留 Slider[…] 定义，见 construction.move 的同类规则）
        from .exprdeps import _ref_deps
        _refs = [d for d in _ref_deps(cons, [text]) if getattr(d, "kind", "") in ("number", "angle")]
        if not _refs:
            try:
                v = eval_number(cons, text)
                from .editing import _cmd_setvalue
                return _cmd_setvalue(cons, defn, [tgt.label, _num_txt(v)])
            except GeoError:
                pass
    # 其它（含受控对象、点、表达式）→ 重定义
    from .editing import _cmd_redefine
    return _cmd_redefine(cons, defn, [tgt.label, tgt.label + "=" + text])


def _cmd_setslider(cons, defn, args):
    """``SetSlider[滑块, 最小值, 最大值, 步长?]`` → 改范围/步长。

    - **当前值保留**（若落到新范围外则夹紧到边界；按新步长吸附）
    - 位置（slider_x/slider_y）与 defn 一并同步 → `.ggk` 往返一致
    - 用途：滑块给函数/几何对象当**动态参数**，范围与步长需要随手调整
    """
    if len(args) not in (3, 4):
        raise GeoError("SetSlider 需要 滑块、最小值、最大值（可选步长）")
    el = _resolve(cons, args[0])
    if getattr(el, "kind", "") != "number" or getattr(el, "min", None) is None:
        raise GeoError("SetSlider 需要滑动条（当前是 %s）" % getattr(el, "kind", "?"))
    lo = eval_number(cons, args[1])
    hi = eval_number(cons, args[2])
    if hi <= lo:
        raise GeoError("最大值必须大于最小值")
    if len(args) == 4:
        step = eval_number(cons, args[3])
        if step <= 0:
            raise GeoError("步长必须为正")
    else:
        step = (hi - lo) / 100.0
    el.min, el.max, el.step = lo, hi, step
    # 保留当前值：夹紧到新范围并按新步长吸附
    v = float(el.value)
    v = max(lo, min(hi, v))
    import math as _m
    if step > 0:
        v = lo + round((v - lo) / step) * step
        v = max(lo, min(hi, v))
        if abs(v - round(v)) < COORD:
            v = float(round(v))
    el.value = v
    el.defn = _regen_defn(el)
    cons._recompute(el)
    return []


def _cmd_setslidervert(cons, defn, args):
    """``SetSliderVertical[滑块, true/false]`` → 竖直 / 水平放置（功能不变，仅方向与按钮位置）。"""
    if len(args) != 2:
        raise GeoError("SetSliderVertical 需要 滑块 和 true/false")
    el = _resolve(cons, args[0])
    if getattr(el, "kind", "") != "number" or getattr(el, "min", None) is None:
        raise GeoError("SetSliderVertical 需要滑动条（当前是 %s）" % getattr(el, "kind", "?"))
    v = args[1].strip().lower()
    if v in ("true", "1", "yes", "竖直", "vertical"):
        el.slider_vert = True
    elif v in ("false", "0", "no", "水平", "horizontal"):
        el.slider_vert = False
    else:
        raise GeoError("SetSliderVertical 需要 true 或 false")
    el.defn = _regen_defn(el)
    return []


def _cmd_setsliderlength(cons, defn, args):
    """``SetSliderLength[滑块, px]`` → 设轨道**屏幕长度**（px，缩放时不变）。"""
    if len(args) != 2:
        raise GeoError("SetSliderLength 需要 滑块 和 像素长度")
    el = _resolve(cons, args[0])
    if getattr(el, "kind", "") != "number" or getattr(el, "min", None) is None:
        raise GeoError("SetSliderLength 需要滑动条（当前是 %s）" % getattr(el, "kind", "?"))
    px = eval_number(cons, args[1])
    if px < SLIDER_PX_MIN or px > SLIDER_PX_MAX:
        raise GeoError("长度需在 %d–%d px 之间" % (SLIDER_PX_MIN, SLIDER_PX_MAX))
    el.slider_px = float(px)
    el.defn = _regen_defn(el)
    return []
