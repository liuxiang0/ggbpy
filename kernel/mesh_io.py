"""3D 网格导出：OBJ（Wavefront）与 STL（ASCII）。

只导出可打印/可交换的 3D 网格对象（cube / polyhedron 系列），
坐标用世界坐标（右手系，z 向上，与 3D 视图一致）。

- OBJ：按对象分组（`o 标签`），保留多边形面（`f v1 v2 v3 ...`，1-based 索引）
- STL：三角形面片 + 面法向（ASCII，按对象分 `solid 标签` 块）

用法：
    text, warnings = export_obj(cons)
    text, warnings = export_stl(cons)
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

MESH_TYPES = ("cube", "polyhedron")


def _fmt(v: float) -> str:
    s = ("%.6f" % v).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _mesh_elements(cons) -> Tuple[List, List[str]]:
    """收集可导出的网格对象；返回 (元素列表, 警告)。"""
    meshes, warnings = [], []
    skipped = []
    for lab in cons.order:
        el = cons.elements[lab]
        if getattr(el, "kind", "") != "geo3d":
            continue
        objtype = getattr(el, "objtype", "")
        data = getattr(el, "data", None) or {}
        if objtype in MESH_TYPES and data.get("verts") and data.get("faces"):
            meshes.append(el)
        elif objtype == "section":
            skipped.append(lab + "(截面非闭合体)")
        else:
            skipped.append(lab + "(" + (objtype or "?") + ")")
    if not meshes:
        warnings.append("没有可导出的 3D 网格对象（需要 立方体/多面体/圆锥/圆柱/棱柱/棱锥/正多面体）")
    elif skipped:
        warnings.append("已跳过非网格 3D 对象：" + ", ".join(skipped))
    return meshes, warnings


def export_obj(cons) -> Tuple[str, List[str]]:
    meshes, warnings = _mesh_elements(cons)
    lines = ["# ggbpy 3D 导出（Wavefront OBJ）", "# 单位：世界坐标（z 向上）"]
    base = 1
    for el in meshes:
        vs = el.data["verts"]
        lines.append("o " + el.label)
        for v in vs:
            lines.append("v " + _fmt(v[0]) + " " + _fmt(v[1]) + " " + _fmt(v[2]))
        for f in el.data["faces"]:
            lines.append("f " + " ".join(str(base + i) for i in f))
        base += len(vs)
    return "\n".join(lines) + "\n", warnings


def _face_normal(vs, face) -> Tuple[float, float, float]:
    """面法向（Newell，单位化）；退化面返回 (0,0,0)。"""
    nx = ny = nz = 0.0
    n = len(face)
    for i in range(n):
        a = vs[face[i]]
        b = vs[face[(i + 1) % n]]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    ln = math.sqrt(nx * nx + ny * ny + nz * nz)
    if ln < 1e-15:
        return 0.0, 0.0, 0.0
    return nx / ln, ny / ln, nz / ln


def export_stl(cons) -> Tuple[str, List[str]]:
    meshes, warnings = _mesh_elements(cons)
    out = []
    for el in meshes:
        vs = el.data["verts"]
        out.append("solid " + el.label)
        for face in el.data["faces"]:
            if len(face) < 3:
                continue
            nx, ny, nz = _face_normal(vs, face)
            for i in range(1, len(face) - 1):
                tri = [face[0], face[i], face[i + 1]]
                out.append("  facet normal " + _fmt(nx) + " " + _fmt(ny) + " " + _fmt(nz))
                out.append("    outer loop")
                for idx in tri:
                    p = vs[idx]
                    out.append("      vertex " + _fmt(p[0]) + " " + _fmt(p[1]) + " " + _fmt(p[2]))
                out.append("    endloop")
                out.append("  endfacet")
        out.append("endsolid " + el.label)
    return "\n".join(out) + "\n", warnings


def parse_obj(text: str) -> Tuple[List[List[float]], List[List[int]], List[str]]:
    """解析 OBJ 文本 → (verts, faces, warnings)。

    支持 `v x y z` 与 `f a b c [d ...]`（含 `f v/vt/vn` 形式与负索引）；
    其它行（vt/vn/o/g/s/usemtl/#）忽略并汇总为提示。
    """
    from .elements import GeoError

    verts: List[List[float]] = []
    faces: List[List[int]] = []
    skipped = {"vt": 0, "vn": 0, "other": 0}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        tag = parts[0]
        if tag == "v":
            if len(parts) < 4:
                raise GeoError("OBJ 顶点行缺少分量: " + line[:40])
            verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif tag == "f":
            idxs: List[int] = []
            for tok in parts[1:]:
                head = tok.split("/")[0]
                if head == "":
                    continue
                i = int(head)
                if i < 0:
                    i = len(verts) + i + 1
                if i < 1 or i > len(verts):
                    raise GeoError("OBJ 面索引越界: " + tok)
                idxs.append(i - 1)
            if len(idxs) >= 3:
                faces.append(idxs)
        elif tag in ("vt", "vn"):
            skipped[tag] += 1
        else:
            skipped["other"] += 1
    if not verts or not faces:
        raise GeoError("OBJ 中没有可用的顶点或面（需要 v / f 行）")
    warnings = []
    if skipped["vt"] or skipped["vn"] or skipped["other"]:
        warnings.append("已忽略 vt=%d vn=%d 其它=%d 行" % (skipped["vt"], skipped["vn"], skipped["other"]))
    return verts, faces, warnings
