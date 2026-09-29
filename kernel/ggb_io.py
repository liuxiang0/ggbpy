"""GGB XML 导出/导入（GeoGebra 兼容子集，P0）。

导出：自由元素写 <element>（点/向量 → coords，数值 → value，函数 → expression），
派生元素写 <element> + <command>（GeoGebra 5 的 construction 结构）。
导入：解析 <element>/<command> 后按创建顺序重放 process_internal。

限制：仅覆盖 P0 的命令与类型；GeoGebra 完整文件中的未知节点会跳过。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple

from .elements import GeoError


def _fmt(v: float) -> str:
    s = ("%.6f" % v).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _is_3d(el) -> bool:
    """3D 元素：geo3d 对象，或带显式 z 的三维点。"""
    return el.kind == "geo3d" or (el.kind == "point" and getattr(el, "z", None) is not None)


def _needs_external_data(el) -> bool:
    """导出需要额外数据块、无法只靠 defn 重放的元素（OBJ/STL/glTF 导入的网格）。"""
    return bool(getattr(el, "meshid", ""))


def _refs_label(defn: str, label: str) -> bool:
    """defn 中是否以独立标识符形式引用了 label。"""
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(label) + r"(?![A-Za-z0-9_])", defn) is not None


def _collect_3d_skips(cons) -> List[str]:
    """需要从 .ggb 导出中跳过的标签：依赖外部网格数据（mesh_store）的元素 + 级联引用者。

    3D 点/球/多面体/曲面等已能通过「3D 点坐标 + 命令重放」完整往返，
    只有 OBJ/STL/glTF 导入的网格必须把数据放在 .ggk 里，因此单独跳过并警告。
    """
    skipped = [lab for lab in cons.order if _needs_external_data(cons.elements[lab])]
    skip_set = set(skipped)
    changed = True
    while changed:
        changed = False
        for lab in cons.order:
            if lab in skip_set:
                continue
            el = cons.elements[lab]
            if any(_refs_label(el.defn, s) for s in skip_set):
                skip_set.add(lab)
                skipped.append(lab)
                changed = True
    return [lab for lab in cons.order if lab in skip_set]


def _parse_defn(defn: str) -> Tuple[str, str, List[str], Optional[int]]:
    """把 defn（如 "M=Midpoint[A,B]" 或 "P=Intersect[f,g]#0"）拆成
    (label, name, args, idx)。idx 为多结果命令的元素序号。"""
    idx = None
    m0 = re.match(r"^(.*)#(\d+)$", defn.strip())
    if m0:
        defn = m0.group(1)
        idx = int(m0.group(2))
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*([A-Za-z_][A-Za-z0-9_]*)\[(.*)\]$", defn.strip())
    if not m:
        return "", "", [], idx
    label, name, inner = m.group(1), m.group(2), m.group(3)
    args = [a.strip() for a in inner.split(",") if a.strip()]
    return label, name, args, idx


def export_ggb(cons, warnings: Optional[List[str]] = None) -> str:
    lines: List[str] = []
    skip = set(_collect_3d_skips(cons))
    if skip:
        note = ("ggbpy 提示：以下元素依赖外部网格数据（OBJ/STL/glTF 导入），.ggb 子集无法承载，已跳过 " +
                str(len(skip)) + " 个：" + ", ".join(lab for lab in cons.order if lab in skip) +
                "。请用 .ggk 保存以保留这些网格。")
        if warnings is not None:
            warnings.append(note)
        lines.append('<?xml version="1.0" encoding="utf-8"?>')
        lines.append("<!-- " + _xml_escape(note) + " -->")
    else:
        lines.append('<?xml version="1.0" encoding="utf-8"?>')
    lines.append('<geogebra format="5.0" version="5.0.826.0" app="ggbpy" platform="python">')
    lines.append('  <gui show="true" />')
    lines.append("  <construction title=\"ggbpy\" author=\"ggbpy\">")
    for lab in cons.order:
        if lab in skip:
            continue
        el = cons.elements[lab]
        lines.append('    <element type="' + el.kind + '" label="' + el.label + '">')
        lines.append('      <show object="true" label="true"/>')
        lines.append('      <objColor r="0" g="0" b="0" alpha="0"/>')
        if el.kind == "point" and el.free:
            if getattr(el, "z", None) is not None:
                # 三维点：写出真实 z 并加 w="1"（2D 点用 z="1" 的齐次约定）
                lines.append('      <coords x="' + _fmt(el.x) + '" y="' + _fmt(el.y)
                             + '" z="' + _fmt(el.z) + '" w="1"/>')
            else:
                lines.append('      <coords x="' + _fmt(el.x) + '" y="' + _fmt(el.y) + '" z="1"/>')
        elif el.kind == "vector" and el.free:
            lines.append('      <coords x="' + _fmt(el.dx) + '" y="' + _fmt(el.dy) + '" z="0"/>')
        elif el.kind == "number" and el.free:
            lines.append('      <value val="' + _fmt(el.value) + '"/>')
        elif el.kind == "function":
            # 自由函数与"引用其他对象"的函数都存表达式（依赖顺序即创建顺序）
            body = _function_body(el)
            if body:
                lines.append('      <expression exp="' + _xml_escape(body) + '"/>')
        elif el.kind in ("list", "inequality"):
            # 自有格式：列表/不等式直接存完整定义（GGB 原生格式不同，仅保证自身往返）
            lines.append('      <expression exp="' + _xml_escape(el.defn) + '"/>')
        lines.append("    </element>")
    # 派生元素 → command（多结果命令只导一次：取 #0 元素）
    for lab in cons.order:
        if lab in skip:
            continue
        el = cons.elements[lab]
        if el.free:
            continue
        _label, name, args, idx = _parse_defn(el.defn)
        if not name:
            continue
        ins = "".join(' a' + str(i) + '="' + a + '"' for i, a in enumerate(args))
        idxattr = (' idx="' + str(idx) + '"') if idx is not None else ''
        lines.append('    <command name="' + name + '"' + idxattr + '>')
        lines.append("      <input" + ins + "/>")
        lines.append('      <output a0="' + el.label + '"/>')
        lines.append("    </command>")
    lines.append("  </construction>")
    lines.append("</geogebra>")
    return "\n".join(lines)


def _function_body(el) -> str:
    """函数赋值形式（f(x)=body）返回 body；命令形式（Derivative 等）返回空。"""
    body = el.defn
    m = re.match(r"^[A-Za-z_][A-Za-z0-9_]*\(x\)=(.*)$", body.strip())
    return m.group(1) if m else ""


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def import_ggb(cons, text: str) -> None:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise GeoError("GGB XML 解析失败: " + str(e))
    cons.clear(silent=True)
    construction = root.find("construction")
    if construction is None:
        raise GeoError("缺少 <construction> 节点")
    # 第一遍：自由元素
    pending_commands: List[Tuple[str, List[str], str]] = []
    for elem in construction.findall("element"):
        label = elem.get("label", "")
        etype = elem.get("type", "")
        coords = elem.find("coords")
        value = elem.find("value")
        expression = elem.find("expression")
        if etype == "point" and coords is not None:
            cx, cy = coords.get("x", "0"), coords.get("y", "0")
            zattr = coords.get("z", "1")
            # 三维点：w="1" 标记（本程序导出约定），或 z 不是齐次 1
            if coords.get("w") == "1" or zattr not in ("", "1"):
                cons.process_internal(label + "=(" + cx + "," + cy + "," + zattr + ")")
            else:
                cons.process_internal(label + "=(" + cx + "," + cy + ")")
        elif etype == "vector" and coords is not None:
            cons.process_internal(label + "=(" + coords.get("x", "0") + "," + coords.get("y", "0") + ")")
        elif etype == "number" and value is not None:
            cons.process_internal(label + "=" + value.get("val", "0"))
        elif etype == "function" and expression is not None:
            exp = expression.get("exp", "")
            if exp:
                cons.process_internal(label + "(x)=" + exp)
        elif etype in ("list", "inequality") and expression is not None:
            exp = expression.get("exp", "")
            if exp:
                cons.process_internal(exp)
        # 其余类型：留待 command 重放
    # 第二遍：命令（按文件顺序）
    for cmd in construction.findall("command"):
        name = cmd.get("name", "")
        inputs = cmd.find("input")
        outputs = cmd.find("output")
        if inputs is None or outputs is None:
            continue
        args = [inputs.get("a" + str(i), "") for i in range(10) if inputs.get("a" + str(i)) is not None]
        out_label = outputs.get("a0", "")
        idx = cmd.get("idx")
        if name and args:
            line = out_label + "=" + name + "[" + ",".join(args) + "]"
            if idx is not None:
                line += "#" + idx
            cons.process_internal(line)
