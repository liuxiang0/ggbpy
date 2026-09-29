"""图片数据仓库：以短 id 索引图片（data URL），供 Image 元素与 .ggk 保存/加载使用。

- put(data_url, w, h) -> id：按内容哈希生成稳定 id
- get(id) / decode(id)：查询与解码为 (mime, bytes)
- serialize() / load(dict)：随 .ggk 一起保存与恢复
"""

from __future__ import annotations

import base64
import hashlib
import re
from typing import Dict, Optional, Tuple

IMAGES: Dict[str, dict] = {}

_DATA_RE = re.compile(r"^data:([^;,]+);base64,(.*)$", re.S)


def put(data_url: str, w: int = 0, h: int = 0) -> str:
    """存入图片，返回短 id。data_url 需为 data:image/...;base64,...。"""
    s = (data_url or "").strip()
    if not _DATA_RE.match(s):
        raise ValueError("图片数据格式不正确（需 data:image/...;base64,...）")
    iid = "img_" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]
    IMAGES[iid] = {"data": s, "w": int(w or 0), "h": int(h or 0)}
    return iid


def get(iid: str) -> Optional[dict]:
    return IMAGES.get(iid)


def decode(iid: str) -> Optional[Tuple[str, bytes]]:
    rec = IMAGES.get(iid)
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
    if ids is None:
        return {k: dict(v) for k, v in IMAGES.items()}
    out = {}
    for k in ids:
        if k and k in IMAGES:
            out[k] = dict(IMAGES[k])
    return out


def load(d) -> None:
    if not isinstance(d, dict):
        return
    for k, v in d.items():
        if isinstance(v, dict) and v.get("data"):
            IMAGES[k] = {"data": v.get("data", ""),
                         "w": int(v.get("w", 0) or 0),
                         "h": int(v.get("h", 0) or 0)}
