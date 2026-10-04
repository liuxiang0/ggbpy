"""通用内容寻址仓库（P2 结构收敛）。

图片仓库（`image_store`）与网格仓库（`mesh_store`）此前各写了一份
「内容哈希 → 短 id / serialize / load」逻辑；这里抽出共用部分，
各仓库只保留自己的领域规则（图片校验 data URL；网格顶点去重与面索引重排）。

约定：
- id = 前缀 + sha1(内容键)[:16]，内容相同 → id 相同（稳定、可去重）
- serialize(ids) 只导出仓库中真实存在的记录，随 .ggk / .ggb 一起保存
- load(data, normalize) 逐条规范化写入，坏记录跳过而不是整体失败
"""

from __future__ import annotations

import hashlib
from typing import Callable, Dict, Iterable, List, Optional

Record = Dict[str, object]
Normalizer = Callable[[Record], Optional[Record]]


def content_id(prefix: str, key: str) -> str:
    """按内容键生成稳定短 id。"""
    return prefix + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def put_record(store: Dict[str, Record], ident: str, record: Record) -> str:
    """写入记录并返回 id（同 id 覆盖等价内容，幂等）。"""
    store[ident] = record
    return ident


def get_record(store: Dict[str, Record], ident: str) -> Optional[Record]:
    return store.get(ident)


def all_ids(store: Dict[str, Record]) -> List[str]:
    return list(store.keys())


def serialize(store: Dict[str, Record], ids: Optional[Iterable[str]] = None) -> Dict[str, Record]:
    """导出记录（ids=None 表示全部）；只导出真实存在的 id。"""
    if ids is None:
        return {k: dict(v) for k, v in store.items()}
    out: Dict[str, Record] = {}
    for i in ids:
        if i and i in store:
            out[i] = dict(store[i])
    return out


def load(store: Dict[str, Record], data, normalize: Optional[Normalizer] = None) -> int:
    """从 {id: record} 恢复仓库；返回成功写入条数。

    normalize：可选规范化钩子（类型转换/字段校验），返回 None 表示丢弃该记录。
    """
    if not isinstance(data, dict):
        return 0
    n = 0
    for ident, rec in data.items():
        if not isinstance(ident, str) or not isinstance(rec, dict):
            continue
        out = rec
        if normalize is not None:
            try:
                out = normalize(rec)
            except Exception:  # 防御性捕获：该分支失败不应中断用户操作
                out = None
            if out is None:
                continue
        store[ident] = out
        n += 1
    return n


def clear(store: Dict[str, Record]) -> None:
    store.clear()


def stats(store: Dict[str, Record]) -> Dict[str, int]:
    return {"count": len(store), "ids": len({k for k in store})}
