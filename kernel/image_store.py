"""图片数据仓库：以短 id 索引图片（data URL），供 Image 元素与 .ggk 保存/加载使用。

- put(data_url, w, h) -> id：按内容哈希生成稳定 id
- get(id) / decode(id)：查询与解码为 (mime, bytes)
- serialize() / load(dict)：随 .ggk 一起保存与恢复
"""

from __future__ import annotations

import base64
import re
from typing import Dict, Optional, Tuple

from . import blob_store

IMAGES: Dict[str, dict] = {}

_DATA_RE = re.compile(r"^data:([^;,]+);base64,(.*)$", re.S)


def put(data_url: str, w: int = 0, h: int = 0) -> str:
    """存入图片，返回短 id。data_url 需为 data:image/...;base64,...。"""
    s = (data_url or "").strip()
    if not _DATA_RE.match(s):
        raise ValueError("图片数据格式不正确（需 data:image/...;base64,...）")
    iid = blob_store.content_id("img_", s)
    return blob_store.put_record(IMAGES, iid, {"data": s, "w": int(w or 0), "h": int(h or 0)})


def get(iid: str) -> Optional[dict]:
    return blob_store.get_record(IMAGES, iid)


def decode(iid: str) -> Optional[Tuple[str, bytes]]:
    rec = blob_store.get_record(IMAGES, iid)
    if not rec:
        return None
    m = _DATA_RE.match(rec.get("data", ""))
    if not m:
        return None
    try:
        return m.group(1), base64.b64decode(m.group(2))
    except Exception:
        return None


def serialize(ids=None) -> dict:
    """导出图片记录（随 .ggk/.ggb 保存）。"""
    return blob_store.serialize(IMAGES, ids)


def _normalize(rec: dict) -> Optional[dict]:
    if not rec.get("data"):
        return None
    return {"data": rec.get("data", ""),
            "w": int(rec.get("w", 0) or 0),
            "h": int(rec.get("h", 0) or 0)}


def load(d) -> int:
    """恢复图片记录（坏记录跳过），返回写入条数。"""
    return blob_store.load(IMAGES, d, _normalize)
