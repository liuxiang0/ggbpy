"""Construction —— 构造对象（几何场景容器）。

职责：
- 元素注册表（label -> GeoElement）+ 创建顺序
- 命令处理入口 process(line)：先压撤销快照，失败回滚
- 增量重算：move() 修改自由元素后沿 dependents 拓扑序重算
- 撤销/重做（命令粒度快照 = 全部 defn 序列，重放实现）
- JSON 存取、GGB-XML 导出/导入（委托 ggb_io）
- 序列化 to_serializable(view) 供前端渲染
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Tuple

from .elements import GeoElement, GeoError

DEFAULT_VIEW = (-10.0, 10.0, -10.0, 10.0)
UNDO_LIMIT = 200


class Construction:
    def __init__(self) -> None:
        self.elements: Dict[str, GeoElement] = {}
        self.order: List[str] = []
        self._undo: List[List[Tuple[str, str]]] = []
        self._redo: List[List[Tuple[str, str]]] = []
        self._counters: Dict[str, int] = {}
        self.message = ""

    # ------------------------------------------------------------------
    # 注册与移除
    # ------------------------------------------------------------------
    def add(self, el: GeoElement) -> GeoElement:
        if getattr(self, "_dry_run", False):
            # 重定义时的试创建：计算但不注册
            if not el.free:
                el.compute()
            return el
        if el.label in self.elements:
            raise GeoError("对象 " + el.label + " 已存在，请换一个名字")
        self.elements[el.label] = el
        self.order.append(el.label)
        if not el.free:
            el.compute()
        return el

    def get(self, label: str) -> GeoElement:
        el = self.elements.get(label)
        if el is None:
            raise GeoError("找不到对象 " + label)
        return el

    def clear(self, silent: bool = False) -> None:
        if not silent:
            # 清空作为一步可撤销操作
            self._push_undo()
            self._redo.clear()
        self.elements.clear()
        self.order.clear()
        self._counters.clear()
        if silent:
            return
        # 非静默清空：保留撤销栈（含刚压入的快照）
        self._redo.clear()

    def reorder(self, labels) -> None:
        """按给定顺序重排对象（Z 序：后列出的绘制在上层/列表后显示）。必须是全部标签的排列。"""
        seq = list(labels)
        if seq == self.order:
            return
        if len(seq) != len(self.order) or set(seq) != set(self.order):
            raise GeoError("顺序必须包含当前全部对象（不增不减）")
        self.order = seq
        # 依赖深度与绘制顺序无关，无需重算；撤销快照基于 order 重建故不入历史（视为显示态）

    # ------------------------------------------------------------------
    # 自动标签
    # ------------------------------------------------------------------
    def auto_label(self, kind: str) -> str:
        """按 GGB 习惯：点 A,B,C..；线/线段/射线 a,b,c..；圆 c,d,e..；
        函数 f,g,h..；向量 u,v,w..；数值 n1,n2..；多边形 poly1.."""
        pools = {
            "point": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "line": "abcdefghijklmnopqrstuvwxyz",
            "segment": "abcdefghijklmnopqrstuvwxyz",
            "ray": "abcdefghijklmnopqrstuvwxyz",
            "circle": "cdefghijklmnopqrstuvwxyz",
            "function": "fghijklmnopqrstuvwxyz",
            "vector": "uvwxyz",
            "conic": "cdefghijklmnopqrstuvwxyz",
            "number": "",
            "polygon": "",
            "list": "",
            "inequality": "",
            "geo3d": "abcdefghijklmnopqrstuvwxyz",
            "boolean": "abcdefghijklmnopqrstuvwxyz",
            "angle": "abcdefghijklmnopqrstuvwxyz",
            "polyline": "",
            "barchart": "",
            "text": "",
            "locus": "",
            "arc": "abcdefghijklmnopqrstuvwxyz",
            "result": "",
            "matrix": "",
            "parametric": "cdefghijklmnopqrstuvwxyz",
            "polar": "cdefghijklmnopqrstuvwxyz",
            "implicit": "cdefghijklmnopqrstuvwxyz",
            "complex": "z",
            "image": "pqrstuvwxyz",
        }
        pool = pools.get(kind, "abcdefghijklmnopqrstuvwxyz")
        idx = self._counters.get(kind, 0)
        while True:
            if pool:
                base = pool[idx % len(pool)]
                n = idx // len(pool)
                cand = base if n == 0 else base + "_" + str(n)   # A_1, B_1, ...（GeoGebra 风格）
            elif kind == "number":
                cand = "n" + str(idx + 1)
            elif kind == "list":
                cand = "l" + str(idx + 1)
            elif kind == "inequality":
                cand = "i" + str(idx + 1)
            elif kind == "polyline":
                cand = "pl" + str(idx + 1)
            elif kind == "barchart":
                cand = "bc" + str(idx + 1)
            elif kind == "text":
                cand = "tx" + str(idx + 1)
            elif kind == "locus":
                cand = "lo" + str(idx + 1)
            elif kind == "result":
                cand = "res" + str(idx + 1)
            elif kind == "matrix":
                cand = "mat" + str(idx + 1)
            else:
                cand = "poly" + str(idx + 1)
            idx += 1
            if cand not in self.elements:
                self._counters[kind] = idx
                return cand
            if idx > 10000:
                raise GeoError("自动标签用尽")

    # ------------------------------------------------------------------
    # 命令处理（含撤销）
    # ------------------------------------------------------------------
    def process(self, text: str) -> str:
        from . import commands
        line = text.strip()
        if not line:
            return ""
        self._push_undo()
        try:
            created = commands.process_line(self, line)
            self._redo.clear()
            if created:
                self.message = "已创建 " + ", ".join(e.label for e in created)
                fm = getattr(created[0], "fit_msg", None)
                if fm:
                    self.message += "；" + fm
            else:
                self.message = "OK"
            return "OK:" + self.message
        except GeoError as e:
            self._rollback_undo()
            self.message = "错误: " + str(e)
            return self.message
        except Exception as e:  # 防御：任何异常都回滚
            self._rollback_undo()
            self.message = "错误: " + repr(e)
            return self.message

    def process_internal(self, line: str) -> None:
        """重放用：不压撤销栈，失败抛错。"""
        from . import commands
        commands.process_line(self, line)

    # ------------------------------------------------------------------
    # 快照 / 撤销 / 重做
    # ------------------------------------------------------------------
    def snapshot(self) -> List[tuple]:
        """快照 = (label, defn, color, visible)，供撤销/重做。"""
        return [(lab, self.elements[lab].defn,
                 self.elements[lab].color, self.elements[lab].visible) for lab in self.order]

    def restore(self, snap: List[tuple]) -> None:
        self.elements.clear()
        self.order.clear()
        self._counters.clear()
        for lab, defn, color, visible in snap:
            self.process_internal(defn)
            el = self.elements.get(lab)
            if el is not None:
                el.color = color
                el.visible = visible

    def _push_undo(self) -> None:
        self._undo.append(self.snapshot())
        if len(self._undo) > UNDO_LIMIT:
            self._undo.pop(0)

    def _rollback_undo(self) -> None:
        if self._undo:
            self._undo.pop()

    def undo(self) -> bool:
        if not self._undo:
            return False
        snap = self._undo.pop()
        self._redo.append(self.snapshot())
        self.restore(snap)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        snap = self._redo.pop()
        self._undo.append(self.snapshot())
        self.restore(snap)
        return True

    def push_history(self) -> None:
        """手动压入撤销快照（拖拽开始、CAS 创建对象等外部变更前调用）。"""
        self._push_undo()
        self._redo.clear()

    def validate(self) -> List[str]:
        """依赖图一致性诊断：返回问题列表（空 = 一致）。"""
        bad: List[str] = []
        if set(self.order) != set(self.elements.keys()):
            bad.append("order 与 elements 键不一致")
        for lab in self.order:
            el = self.elements.get(lab)
            if el is None:
                bad.append("order 中有缺失对象 " + lab)
                continue
            for d in el.deps:
                dlab = getattr(d, "label", "")
                if dlab and not dlab.startswith("_") and dlab not in self.elements:
                    bad.append(lab + " 的依赖不在构造中: " + dlab)
                if el not in d.dependents:
                    bad.append(lab + " 不在依赖 " + dlab + " 的 dependents 中")
            if el.depth < 0:
                bad.append(lab + " 深度为负")
        return bad

    # ------------------------------------------------------------------
    # 拖拽 → 增量重算
    # ------------------------------------------------------------------
    def move(self, label: str, x: float, y: float, z: float = None) -> bool:
        el = self.get(label)
        if el.locked:
            raise GeoError(label + " 已锁定，不能移动")
        if not el.free:
            raise GeoError(label + " 是派生对象，不能直接移动")
        if el.kind == "point":
            ox, oy = el.x, el.y
            # 找到包含该点的刚性多边形组（可能有多个，取第一个）
            rigid_group = None
            for rp0 in list(el.dependents):
                if rp0.kind == "polygon" and getattr(rp0, "rigid", False):
                    rigid_group = rp0
                    break
            if rigid_group is not None:
                deps = [d for d in rigid_group.deps if d.kind == "point"]
                pivot = deps[0]
                if pivot is not el and abs(math.hypot(el.x - pivot.x, el.y - pivot.y)) > 1e-12:
                    # 拖动非首个顶点 → 绕第一个顶点（pivot）旋转（保距/保形，无平移）
                    import math as _m
                    oa = _m.atan2(oy - pivot.y, ox - pivot.x)
                    na = _m.atan2(float(y) - pivot.y, float(x) - pivot.x)
                    th = na - oa
                    moved = []
                    for v in deps[1:]:
                        if v.locked:
                            raise GeoError(v.label + " 已锁定，刚性多边形无法旋转")
                        vx0 = v.x - pivot.x
                        vy0 = v.y - pivot.y
                        v.x = pivot.x + vx0 * _m.cos(th) - vy0 * _m.sin(th)
                        v.y = pivot.y + vx0 * _m.sin(th) + vy0 * _m.cos(th)
                        v.defn = v.label + "=(" + _fmt(v.x) + "," + _fmt(v.y) + ")"
                        moved.append(v)
                    for m in moved:
                        self._recompute(m)
                    return True
                # 拖动首顶点（或退化）：整体平移
                el.x, el.y = float(x), float(y)
                if z is not None or el.z is not None:
                    el.z = float(z) if z is not None else (el.z or 0)
                    el.defn = label + "=(" + _fmt(el.x) + "," + _fmt(el.y) + "," + _fmt(el.z) + ")"
                else:
                    el.defn = label + "=(" + _fmt(el.x) + "," + _fmt(el.y) + ")"
                moved = [el]
                dx, dy = el.x - ox, el.y - oy
                if dx or dy:
                    for v in deps[1:]:
                        if not (v.free and v.kind == "point"):
                            continue
                        if v.locked:
                            raise GeoError(v.label + " 已锁定，刚性多边形无法整体移动")
                        v.x += dx
                        v.y += dy
                        v.defn = v.label + "=(" + _fmt(v.x) + "," + _fmt(v.y) + ")"
                        moved.append(v)
                for m in moved:
                    self._recompute(m)
                return True
            # 普通自由点（非刚性组）：直接移动
            el.x, el.y = float(x), float(y)
            if z is not None or el.z is not None:
                el.z = float(z) if z is not None else (el.z or 0)
                el.defn = label + "=(" + _fmt(el.x) + "," + _fmt(el.y) + "," + _fmt(el.z) + ")"
            else:
                el.defn = label + "=(" + _fmt(el.x) + "," + _fmt(el.y) + ")"
            self._recompute(el)
            return True
        elif el.kind == "number":
            el.value = float(x)
            el.defn = label + "=" + _fmt(el.value)
        else:
            raise GeoError(label + " 暂不支持拖拽")
        self._recompute(el)
        return True

    def _movable_point_roots(self, el):
        """沿依赖链收集"可整体平移的自由基点"（命名自由点）。

        返回 (roots, complete)：
        - roots：应平移的自由命名点（保持构造关系，如 Polygon[A,B,C] 移动 A/B/C）；
        - complete：False 表示存在匿名自由点/无法平移的源 → 调用方应退回"物化平移"。
        命中锁定点直接抛错。
        """
        roots = []
        complete = True
        seen = set()

        def walk(cur):
            nonlocal complete
            if id(cur) in seen or not complete:
                return
            seen.add(id(cur))
            if cur.kind == "point":
                if cur.free:
                    if cur.label.startswith("_"):
                        complete = False      # 匿名自由点无法作为持久移动根
                        return
                    if cur.locked:
                        raise GeoError(cur.label + " 已锁定，不能整体移动")
                    roots.append(cur)
                    return
                for d in cur.deps:
                    walk(d)
            else:
                for d in cur.deps:
                    walk(d)

        walk(el)
        # 去掉重复引用（同一自由点可能经多条路径到达）
        uniq = []
        us = set()
        for p in roots:
            if id(p) not in us:
                us.add(id(p))
                uniq.append(p)
        return uniq, complete

    def shift(self, label: str, dx: float, dy: float, dz: float = 0.0) -> bool:
        """整体平移对象（选中对象拖动）。

        优先 OOP 语义：若对象由命名自由基点构造（如 Polygon[A,B,C]、
        Segment[A,B]、Circle[O,P]、Text[..,A]），则平移这些基点——构造关系
        保持（defn 不变），多边形与顶点等关联对象同步移动；
        基点缺失/匿名（字面量自由对象）时退回"物化为自由字面量"。
        """
        el = self.get(label)
        if el.locked:
            raise GeoError(label + " 已锁定，不能移动")
        # 刚性多边形：拖动"非首顶点" → 绕第一个顶点旋转（保距/保形）
        if el.kind == "point":
            grp = None
            for rp0 in list(el.dependents):
                if rp0.kind == "polygon" and getattr(rp0, "rigid", False):
                    grp = rp0
                    break
            if grp is not None:
                deps = [d for d in grp.deps if d.kind == "point"]
                pivot = deps[0]
                if pivot is not el and abs(math.hypot(el.x - pivot.x, el.y - pivot.y)) > 1e-12:
                    oa = math.atan2(el.y - pivot.y, el.x - pivot.x)
                    na = math.atan2(el.y + dy - pivot.y, el.x + dx - pivot.x)
                    th = na - oa
                    moved = []
                    for v in deps[1:]:
                        if v.locked:
                            raise GeoError(v.label + " 已锁定，刚性多边形无法旋转")
                        vx0 = v.x - pivot.x
                        vy0 = v.y - pivot.y
                        v.x = pivot.x + vx0 * math.cos(th) - vy0 * math.sin(th)
                        v.y = pivot.y + vx0 * math.sin(th) + vy0 * math.cos(th)
                        v.defn = v.label + "=(" + _fmt(v.x) + "," + _fmt(v.y) + ")"
                        moved.append(v)
                    for m in moved:
                        self._recompute(m)
                    return True
        roots, complete = self._movable_point_roots(el)
        if complete and roots:
            # 刚性组扩展：基点若属于某个刚性多边形 → 该组全部自由顶点一起平移（整块刚体移动）
            ext = []
            es = set()
            for p in roots:
                if id(p) in es:
                    continue
                es.add(id(p))
                ext.append(p)
                for rp in list(p.dependents):
                    if rp.kind == "polygon" and getattr(rp, "rigid", False):
                        for v in rp.deps:
                            if v.kind == "point" and v.free and id(v) not in es:
                                if v.locked:
                                    raise GeoError(v.label + " 已锁定，不能整体移动")
                                es.add(id(v))
                                ext.append(v)
            roots = ext
            for p in roots:
                p.x += dx
                p.y += dy
                pz = getattr(p, "z", None)
                if pz is not None or dz:
                    p.z = (pz or 0.0) + dz
                    p.defn = p.label + "=(" + _fmt(p.x) + "," + _fmt(p.y) + "," + _fmt(p.z) + ")"
                else:
                    p.defn = p.label + "=(" + _fmt(p.x) + "," + _fmt(p.y) + ")"
            for p in roots:
                self._recompute(p)
            return True
        if el.kind == "point":
            el.x += dx
            el.y += dy
            ez = getattr(el, "z", None)
            if ez is not None or dz:
                el.z = (ez or 0.0) + dz
                el.defn = label + "=(" + _fmt(el.x) + "," + _fmt(el.y) + "," + _fmt(el.z) + ")"
            else:
                el.defn = label + "=(" + _fmt(el.x) + "," + _fmt(el.y) + ")"
        elif el.kind == "segment":
            el.x1 += dx; el.y1 += dy; el.x2 += dx; el.y2 += dy
            el.defn = (label + "=Segment[(" + _fmt(el.x1) + "," + _fmt(el.y1)
                       + "),(" + _fmt(el.x2) + "," + _fmt(el.y2) + ")]")
        elif el.kind == "circle":
            el.cx += dx; el.cy += dy
            el.defn = label + "=Circle[(" + _fmt(el.cx) + "," + _fmt(el.cy) + ")," + _fmt(el.r) + "]"
        elif el.kind == "line":
            el.c = el.c - el.a * dx - el.b * dy
            denom = el.a * el.a + el.b * el.b
            if denom < 1e-12:
                raise GeoError(label + " 退化直线，不能移动")
            px = -el.a * el.c / denom
            py = -el.b * el.c / denom
            qx = px - el.b
            qy = py + el.a
            el.defn = label + "=Line[(" + _fmt(px) + "," + _fmt(py) + "),(" + _fmt(qx) + "," + _fmt(qy) + ")]"
        elif el.kind == "polygon":
            for i in range(len(el.xs)):
                el.xs[i] += dx
                el.ys[i] += dy
            pts_s = ",".join("(" + _fmt(x) + "," + _fmt(y) + ")"
                             for x, y in zip(el.xs, el.ys))
            el.defn = label + "=Polygon[" + pts_s + "]"
        elif el.kind == "arc":
            # 起点/终点/圆心同步平移
            a1 = el.ang1
            s = (el.cx + el.r * math.cos(a1), el.cy + el.r * math.sin(a1))
            e = (el.cx + el.r * math.cos(el.ang2), el.cy + el.r * math.sin(el.ang2))
            el.cx += dx; el.cy += dy
            el.defn = (label + "=Arc[(" + _fmt(s[0] + dx) + "," + _fmt(s[1] + dy)
                       + "),(" + _fmt(e[0] + dx) + "," + _fmt(e[1] + dy)
                       + "),(" + _fmt(el.cx) + "," + _fmt(el.cy) + ")]")
        elif el.kind == "text":
            el.x += dx
            el.y += dy
            el.defn = label + "=Text[" + el.content + ",(" + _fmt(el.x) + "," + _fmt(el.y) + ")]"
        elif el.kind == "vector":
            el.sx += dx; el.sy += dy
            el.defn = (label + "=Vector[(" + _fmt(el.sx) + "," + _fmt(el.sy)
                       + "),(" + _fmt(el.sx + el.dx) + "," + _fmt(el.sy + el.dy) + ")]")
        elif el.kind == "geo3d":
            raise GeoError(label + " 无自由基点，无法整体平移（请用命名的点/线段/多边形创建）")
        else:
            raise GeoError(label + " 暂不支持整体拖动")
        # 物化为自由对象（不再被依赖重算覆盖）
        el.free = True
        el.deps = []
        el._fn = None
        self._recompute(el)
        return True

    def _recompute(self, root: GeoElement) -> None:
        dirty: set = set()
        stack = [root]
        while stack:
            el = stack.pop()
            for dep in el.dependents:
                if dep not in dirty:
                    dirty.add(dep)
                    stack.append(dep)
        for el in sorted(dirty, key=lambda e: e.depth):
            if not el.free:
                el.compute()

    # ------------------------------------------------------------------
    # 编辑：删除 / 重命名 / 重定义
    # ------------------------------------------------------------------
    def delete(self, label: str) -> None:
        """级联删除：连同所有依赖它的对象一起移除。"""
        el = self.elements.get(label)
        if el is None:
            raise GeoError("找不到对象 " + label)
        if el.locked:
            raise GeoError(label + " 已锁定，不能删除")
        if any(d.locked for d in el.dependents):
            locked_deps = [d.label for d in el.dependents if d.locked]
            raise GeoError("存在锁定的依赖对象 " + ", ".join(locked_deps) + "，不能删除")
        doomed: set = set()
        stack = [el]
        while stack:
            e = stack.pop()
            if e in doomed:
                continue
            doomed.add(e)
            for dep in e.dependents:
                stack.append(dep)
        for e in doomed:
            for d in e.deps:
                if d in self.elements or d is not None:
                    d.dependents.discard(e)
        doomed_labels = {e.label for e in doomed}
        for lab in doomed_labels:
            self.elements.pop(lab, None)
        self.order = [l for l in self.order if l not in doomed_labels]

    def rename(self, old: str, new: str) -> None:
        """重命名对象，并重写所有 defn 中的旧标签。"""
        import re
        if old not in self.elements:
            raise GeoError("找不到对象 " + old)
        if self.elements[old].locked:
            raise GeoError(old + " 已锁定，不能重命名")
        if not re.match(r"^[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*$", new):
            raise GeoError("非法标签: " + new)
        if new in self.elements:
            raise GeoError("对象 " + new + " 已存在")
        for lab in self.order:
            e = self.elements[lab]
            e.defn = re.sub(r"\b" + re.escape(old) + r"\b", new, e.defn)
        el = self.elements[old]
        el.label = new
        self.elements[new] = el
        del self.elements[old]
        self.order = [new if l == old else l for l in self.order]

    def redefine(self, label: str, defn_text: str) -> None:
        """用新定义替换对象（依赖它的对象自动改指向并重算）。"""
        from . import commands as C
        from .parser import parse_line
        old = self.elements.get(label)
        if old is None:
            raise GeoError("找不到对象 " + label)
        if old.locked:
            raise GeoError(label + " 已锁定，不能重定义")
        plabel, _kind, _payload = parse_line(self, defn_text)
        if plabel is not None and plabel != label:
            raise GeoError("重定义中的标签 " + plabel + " 与对象 " + label + " 不一致（改标签请用 Rename）")
        # 试创建（dry-run）
        self._dry_run = True
        try:
            created = C.process_line(self, defn_text)
        finally:
            self._dry_run = False
        if len(created) != 1:
            raise GeoError("重定义必须生成恰好一个对象")
        new_el = created[0]
        if new_el.label != label:
            new_el.label = label
        # 保留原样式
        new_el.color = old.color
        new_el.visible = old.visible
        # 1) 从旧元素上游集合摘除
        for d in old.deps:
            d.dependents.discard(old)
        # 2) 下游依赖改指向新元素
        affected = list(old.dependents)
        for dep_el in affected:
            for i, d in enumerate(dep_el.deps):
                if d is old:
                    dep_el.deps[i] = new_el
            dep_el.depth = max((d.depth for d in dep_el.deps), default=-1) + 1
            new_el.dependents.add(dep_el)
        # 3) 替换注册
        self.elements[label] = new_el
        # 4) 重算（沿依赖链传播到全部下游）
        new_el.compute()
        for dep_el in sorted(affected, key=lambda e: e.depth):
            if not dep_el.free:
                dep_el.compute()
        for dep_el in affected:
            self._recompute(dep_el)

    # ------------------------------------------------------------------
    # 序列化（前端）
    # ------------------------------------------------------------------
    def to_serializable(self, view: Tuple[float, float, float, float] = DEFAULT_VIEW) -> List[Dict[str, Any]]:
        out = []
        for lab in self.order:
            el = self.elements[lab]
            d = el.draw(view)
            if d is not None:
                out.append(d)
            elif not el.visible:
                # 隐藏对象：保留最小信息（列表灰显，可重新勾选显示恢复）
                out.append({"label": lab, "kind": el.kind, "defn": el.defn,
                            "free": el.free, "locked": el.locked, "color": el.color,
                            "visible": False, "error": el.error})
        return out

    # ------------------------------------------------------------------
    # 存取：JSON（自有格式）
    # ------------------------------------------------------------------
    def save_json(self) -> str:
        from . import macro, image_store
        img_ids = [getattr(self.elements[lab], "imgid", "") for lab in self.order
                   if getattr(self.elements[lab], "kind", "") == "image"]
        return json.dumps({
            "format": "ggk",
            "version": 3,
            "order": self.order,
            "defns": {lab: self.elements[lab].defn for lab in self.order},
            "styles": {lab: [self.elements[lab].color, self.elements[lab].visible,
                             self.elements[lab].locked,
                             bool(getattr(self.elements[lab], "wire", False))] for lab in self.order},
            "images": image_store.serialize(img_ids),
            "macros": macro.serialize(),
        }, ensure_ascii=False, indent=1)

    def save_ggk(self, view=None) -> str:
        """自有 .ggk 格式（JSON）：完整保留定义/样式/视口。"""
        data = json.loads(self.save_json())
        if view is not None:
            data["view"] = list(view)
        return json.dumps(data, ensure_ascii=False, indent=1)

    def load_json(self, text: str) -> Optional[tuple]:
        """加载 .ggk/.json；返回视口（若有）供前端恢复。"""
        data = json.loads(text)
        order = data["order"]
        defns = data["defns"]
        styles = data.get("styles", {})
        self.clear(silent=True)
        from . import image_store
        if data.get("images"):
            image_store.load(data["images"])   # 必须在重放 Image[...] 之前恢复图片数据
        for lab in order:
            self.process_internal(defns[lab])
            st = styles.get(lab)
            if st and lab in self.elements:
                self.elements[lab].color = st[0]
                self.elements[lab].visible = st[1]
                if len(st) > 2:
                    self.elements[lab].locked = bool(st[2])
                    if len(st) > 3 and st[3]:
                        try:
                            self.elements[lab].wire = True
                        except Exception:
                            pass
        from . import macro
        if data.get("macros"):
            macro.load(data["macros"])
        return tuple(data["view"]) if data.get("view") else None

    # ------------------------------------------------------------------
    # 存取：GGB XML
    # ------------------------------------------------------------------
    def save_ggb(self) -> str:
        from . import ggb_io
        return ggb_io.export_ggb(self)

    def load_ggb(self, text: str) -> None:
        from . import ggb_io
        ggb_io.import_ggb(self, text)

    def load_text(self, text: str) -> None:
        """加载 .ggk / .json（内容以 { 开头）或 .ggb XML（以 < 开头）。"""
        t = text.strip()
        if t.startswith("{"):
            self.load_json(t)
        elif t.startswith("<"):
            self.load_ggb(t)
        else:
            raise GeoError("无法识别的文件格式（需 .ggk/.json 或 .ggb XML）")

    def load_demo(self) -> None:
        demo = [
            "A=(1,1)",
            "B=(5,2)",
            "C=(2.5,4.5)",
            "M=Midpoint[A,B]",
            "N=Midpoint[B,C]",
            "g=Line[A,B]",
            "h=Line[C,M]",
            "P=Intersect[g,h]",
            "c=Circle[A,B,C]",
            "f(x)=0.15*(x-3)^2-0.5",
            "df=Derivative[f]",
            "tg=Tangent[f,1]",
            "X=Intersect[f,g]",
            "area=Integral[f,0,4]",
            "s=Segment[A,B]",
            "t=Translate[s,(2,1)]",
            "d=Circle[M,A]",
            "k=Reflect[s,P]",
            # ---- P3：圆锥曲线 / 不等式 / 统计 / 3D ----
            "F1=(-2,0)",
            "F2=(2,0)",
            "ell=Ellipse[F1,F2,(0,3)]",
            "region: x^2+y^2<9",
            "N3={3,1,4,1,5,9,2,6}",
            "N3sd=StDev[N3]",
            "A3=(0,0,0)",
            "B3=(3,0,0)",
            "C3=(0,3,0)",
            "cb=Cube[A3,B3,C3]",
            "sph=Sphere[A3,2.5]",
            # ---- P4：定理证明 ----
            "lmn=Line[M,N]",
            "lac=Line[A,C]",
            "th1=AreParallel[lmn,lac]",
            # ---- 初中几何：垂线/垂足/角平分线/内心/内切圆/滑动条 ----
            "per=PerpendicularLine[C,g]",
            "ft=Foot[C,g]",
            "ab=AngleBisector[A,B,C]",
            "tri=Polygon[A,B,C]",
            "ic=Incenter[tri]",
            "inc=Incircle[tri]",
            "ang=Angle[A,B,C]",
            "sl=Slider[0,5,0.1]",
            "g2(x)=sl*sin(x)",
            "ar=Area[tri]",
            # ---- 第二优先级：轨迹 / 文本 / 分布 ----
            "cir2=Circle[(0,0),(3,0)]",
            "PP=PointOnCircle[cir2]",
            "MM=Midpoint[PP,(3,0)]",
            "tr=Locus[MM,PP]",
            'lb=Text["轨迹: 中点MM",(0,-5)]',
            "nd2=NormalDist[0,1]",
            # ---- 第三优先级：圆弧/扇形/矩阵/解不等式/中文命令/锁定 ----
            "arc3=Arc[(1,0),(0,1),(0,0)]",
            "sec3=Sector[(1,0),(0,1),(0,0)]",
            "M3=Matrix[{{1,2},{3,4}}]",
            "d3=Det[M3]",
            "ineq3=SolveIneq[x^2<4, x]",
            "中=中点[A,B]",
            "SetLocked[中,true]",
        ]
        self.clear(silent=True)
        for line in demo:
            self.process_internal(line)


def _fmt(v: float) -> str:
    s = ("%.6f" % v).rstrip("0").rstrip(".")
    if s in ("", "-0"):
        s = "0"
    return s
