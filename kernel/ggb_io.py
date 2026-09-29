"""GGB XML 导出/导入（GeoGebra 兼容子集，P0）。

导出：自由元素写 <element>（点/向量 → coords，数值 → value，函数 → expression），
派生元素写 <element> + <command>（GeoGebra 5 的 construction 结构）。
导入：解析 <element>/<command> 后按创建顺序重放 process_internal。

限制：仅覆盖 P0 的命令与类型；GeoGebra 完整文件中的未知节点会跳过。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import List, Tuple

from .elements import GeoError


def _fmt(v: float) -> str:
    s = ("%.6f" % v).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


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


def export_ggb(cons) -> str:
    lines: List[str] = []
    lines.append('<?xml version="1.0" encoding="utf-8"?>')
    lines.append('<geogebra format="5.0" version="5.0.826.0" app="ggbpy" platform="python">')
    lines.append('  <gui show="true" />')
    lines.append("  <construction title=\"ggbpy\" author=\"ggbpy\">")
    for lab in cons.order:
        el = cons.elements[lab]
        lines.append('    <element type="' + el.kind + '" label="' + el.label + '">')
        lines.append('      <show object="true" label="true"/>')
        lines.append('      <objColor r="0" g="0" b="0" alpha="0"/>')
        if el.kind == "point" and el.free:
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
        if etype == "point" and coords is not None and coords.get("z", "1") == "1":
            cons.process_internal(label + "=(" + coords.get("x", "0") + "," + coords.get("y", "0") + ")")
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
