"""导入网格仓库：以短 id 索引 OBJ 导入的网格，供 Mesh 元素与 .ggk 保存/加载使用。

- put(verts, faces) -> id：按内容哈希生成稳定 id（面表已做顶点去重与索引重排）
- get(id)：查询网格记录
- serialize(ids) / load(dict)：随 .ggk 一起保存与恢复
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Dict, List, Optional

MESHES: Dict[str, dict] = {}


def _clean(verts, faces):
    """顶点去重（1e-9）+ 面索引重排 + 丢弃退化面。"""
    uniq: List[List[float]] = []
    remap: List[int] = []
    for v in verts:
        found = -1
        for i, q in enumerate(uniq):
            if abs(q[0] - v[0]) < 1e-9 and abs(q[1] - v[1]) < 1e-9 and abs(q[2] - v[2]) < 1e-9:
                found = i
                break
        if found < 0:
            uniq.append([float(v[0]), float(v[1]), float(v[2])])
            found = len(uniq) - 1
        remap.append(found)
    out_faces = []
    for f in faces:
        idx = []
        for i in f:
            j = remap[i]
            if not idx or idx[-1] != j:
                idx.append(j)
        if len(idx) >= 3 and idx[0] == idx[-1]:
            idx.pop()
        if len(idx) >= 3:
            out_faces.append(idx)
    return uniq, out_faces


def put(verts, faces) -> str:
    uv, uf = _clean(verts, faces)
    if len(uv) < 3 or not uf:
        raise ValueError("网格数据不足（需要至少 3 个顶点与 1 个面）")
    key = json.dumps([[[round(c, 9) for c in v] for v in uv], uf], separators=(",", ":"))
    mid = "mesh_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    MESHES[mid] = {"verts": uv, "faces": uf}
    return mid


def get(mid: str) -> Optional[dict]:
    return MESHES.get(mid)


def edges_of(faces) -> List[List[int]]:
    seen = set()
    edges = []
    for f in faces:
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            if a == b:
                continue
            key = (min(a, b), max(a, b))
            if key not in seen:
                seen.add(key)
                edges.append([key[0], key[1]])
    return edges


def serialize(ids) -> dict:
    return {mid: MESHES[mid] for mid in ids if mid in MESHES}


def load(data) -> None:
    if not data:
        return
    for mid, rec in data.items():
        try:
            MESHES[mid] = {"verts": [[float(c) for c in v] for v in rec["verts"]],
                           "faces": [[int(i) for i in f] for f in rec["faces"]]}
        except Exception:
            continue
