"""导入导出命令（OBJ/STL/glTF 导入导出、图片与文本，P2 结构拆分：从 commands.py 抽出）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .cmd_util import _label_of, _point_arg, label_of
from .stats import _REF_DOT, _REF_X
from .elements import GeoError, GeoImage, GeoText
from .parser import eval_number
from . import image_store


__all__ = [
    "_tuple_parts",
    "_cmd_image",
    "_txt_num",
    "_dyn_text_segments",
    "_ref_text",
    "_dyn_text_compute",
    "_cmd_text",
]


def _tuple_parts(s: str) -> List[str]:
    s = s.strip()
    if not (s.startswith("(") and s.endswith(")")):
        raise GeoError("需要 (a,b) 形式: " + s)
    inner = s[1:-1]
    parts = inner.split(",")
    if len(parts) != 2:
        raise GeoError("元组需要恰好两个分量: " + s)
    return [p.strip() for p in parts]

def _cmd_image(cons, defn, args):
    """Image[基点A, 基点B, 图片ID] — 以两点定位/缩放的图片（保持原始长宽比）。"""
    if len(args) != 3:
        raise GeoError("Image 需要 基点A、基点B 和图片ID")
    a = _point_arg(cons, args[0])
    b = _point_arg(cons, args[1])
    from . import image_store
    iid = args[2].strip().strip('"').strip("'")
    rec = image_store.get(iid)
    if rec is None:
        raise GeoError("图片不存在或已失效: " + iid)
    el = GeoImage(_label_of(defn), defn)
    el.free = False
    el.imgid = iid
    el.iw = int(rec.get("w", 0) or 0)
    el.ih = int(rec.get("h", 0) or 0)
    el.set_deps([a, b], lambda d: {"ax": d[0].x, "ay": d[0].y, "bx": d[1].x, "by": d[1].y})
    return cons.add(el)

def _txt_num(v: float) -> str:
    s = ("%.6f" % float(v)).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"

def _dyn_text_segments(content: str):
    """文本模板 → [('lit', 文字) | ('ref', token)]：支持 "..." 字面与 + 拼接对象引用。"""
    segs = []
    i, n = 0, len(content)
    while i < n:
        if content[i] == '"':
            j = i + 1
            buf = []
            while j < n and content[j] != '"':
                if content[j] == "\\" and j + 1 < n:
                    buf.append(content[j + 1])
                    j += 2
                else:
                    buf.append(content[j])
                    j += 1
            segs.append(("lit", "".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and content[j] != '"':
                j += 1
            for part in re.split(r"\+", content[i:j]):
                p = part.strip()
                if p:
                    segs.append(("ref", p))
            i = j
    return segs

def _ref_text(m, tok: str) -> str:
    """按引用 token 生成当前文本：对象标签 / x(A) / A.x。m: label → 元素。"""
    md = _REF_DOT.match(tok)
    if md:
        o = m.get(md.group(1).strip())
        if o is not None and o.kind == "point":
            return _txt_num(o.x if md.group(2) in ("x", "X") else o.y)
        raise GeoError("文本引用需要点对象: " + tok)
    mx = _REF_X.match(tok)
    if mx:
        o = m.get(mx.group(2).strip())
        if o is not None and o.kind == "point":
            return _txt_num(o.x if mx.group(1) in ("x", "X") else o.y)
        raise GeoError("x(A)/y(A) 需要点: " + tok)
    o = m.get(tok)
    if o is None:
        raise GeoError("文本引用了不存在的对象: " + tok)
    if o.kind == "number":
        return _txt_num(o.value)
    if o.kind == "angle":
        return _txt_num(o.value) + "°"
    if o.kind == "point":
        return "(" + _txt_num(o.x) + ", " + _txt_num(o.y) + ")"
    raise GeoError("文本仅支持引用 数值/角度/点: " + tok)

def _dyn_text_compute(deps, segs, anchor_pt, anchor_xy):
    m = {d.label: d for d in deps}
    buf = []
    for kind, v in segs:
        buf.append(v if kind == "lit" else _ref_text(m, v))
    content = "".join(buf)
    st = {"content": content}
    if anchor_pt is not None:
        ap = m.get(anchor_pt.label, anchor_pt)
        st["x"], st["y"] = ap.x, ap.y
        st["anchor_is_point"] = True
    else:
        st["x"], st["y"] = anchor_xy
        st["anchor_is_point"] = False
    return st

def _cmd_text(cons, defn, args):
    """Text[模板, 点或坐标] → 文本标注。
    模板支持动态引用："AB = " + d / x(A) / A.x / A（+ 拼接对象），拖动时实时更新。"""
    if len(args) != 2:
        raise GeoError('Text 需要 文字 和 位置（点或 (x,y)）')
    content_s = args[0].strip()
    segs = _dyn_text_segments(content_s)
    ref_objs = []
    seen = set()
    for kind, v in segs:
        if kind == "lit":
            continue
        name = v
        mdot = _REF_DOT.match(v)
        mx = _REF_X.match(v)
        if mdot:
            name = mdot.group(1).strip()
        elif mx:
            name = mx.group(2).strip()
        o = cons.elements.get(name)
        if o is None:
            raise GeoError("文本引用了不存在的对象: " + v)
        if o.kind not in ("number", "angle", "point"):
            raise GeoError("文本仅支持引用 数值/角度/点: " + v)
        if o.label not in seen:
            seen.add(o.label)
            ref_objs.append(o)
    pos = args[1].strip()
    el = GeoText(label_of(defn), defn)
    el.free = False
    el.content = ""
    deps = list(ref_objs)
    anchor_pt = None
    anchor_xy = (0.0, 0.0)
    pt = cons.elements.get(pos)
    if pt is not None and pt.kind == "point":
        anchor_pt = pt
        if pt.label not in seen:
            seen.add(pt.label)
            deps.append(pt)
    elif pos.startswith("("):
        parts = _tuple_parts(pos)
        anchor_xy = (eval_number(cons, parts[0]), eval_number(cons, parts[1]))
    else:
        raise GeoError("Text 位置需要 点 或 (x,y)")
    el.set_deps(deps, lambda d: _dyn_text_compute(d, segs, anchor_pt, anchor_xy))
    el.compute()
    return cons.add(el)
