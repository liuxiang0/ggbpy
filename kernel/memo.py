"""计算记忆（memo）：让撤销/重做、快照回放不再重算重对象。

背景：快照只存 (label, defn, 样式)，恢复时按 defn 重放。对隐式曲面/大网格这类
对象，一次重放要 1–2 秒。这里按「defn + 各依赖的几何状态签名」缓存计算结果：
- 依赖没变、defn 没变 → 直接复用缓存状态（毫秒级）
- 任一依赖值/坐标变化或 defn 变化 → 键不同 → 自然失效，不会用错结果

只在派生元素（有 _fn 的非自由元素）上生效；自由元素的坐标就是其状态。
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

_SIG_VIEW = (-10.0, 10.0, -10.0, 10.0)
_MAX_ENTRIES = 96          # 条目数上限
_MAX_COORDS = 600_000      # 顶点/元素规模上限（近似内存保护）

_STORE: "OrderedDict[Tuple, Dict[str, Any]]" = OrderedDict()
_COORDS = 0
HITS = 0
MISSES = 0


_SKIP_KEYS = {"label", "defn", "color", "free", "locked", "error", "value", "samples", "wire"}


def _sig_walk(obj, out, depth=0):
    """把 draw() 输出折成有界指纹：字典按键、列表记长度 + 数值校验和。

    关键点：多边形(xs/ys)、圆(cx/cy/r)、线段、函数(expr)、圆锥曲线等都不放在
    data 里，必须靠 draw() 输出区分；否则不同构造里同名同 defn 的对象会误命中缓存。
    """
    if depth > 4 or len(out) > 60:
        return
    if isinstance(obj, dict):
        for k in sorted(obj.keys()):
            if k in _SKIP_KEYS:
                continue
            out.append(str(k))
            _sig_walk(obj[k], out, depth + 1)
    elif isinstance(obj, (list, tuple)):
        out.append("n%d" % len(obj))
        acc = 0.0
        cnt = 0
        for item in obj[:200]:
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                acc += float(item)
                cnt += 1
            elif isinstance(item, (list, tuple)):
                for x in item[:4]:
                    if isinstance(x, (int, float)) and not isinstance(x, bool):
                        acc += float(x)
                        cnt += 1
            elif isinstance(item, str):
                out.append(item[:24])
        out.append("%.9g/%d" % (acc, cnt))
    elif isinstance(obj, str):
        out.append(obj[:24])
    elif obj is not None:
        out.append(repr(obj)[:24])


def _state_sig(el) -> Tuple:
    """元素的几何状态签名：能区分"依赖是否变化"的最小信息。"""
    kind = getattr(el, "kind", "")
    if kind == "point":
        return ("pt", round(float(getattr(el, "x", 0.0)), 12),
                round(float(getattr(el, "y", 0.0)), 12),
                None if getattr(el, "z", None) is None else round(float(el.z), 12))
    if kind == "number":
        v = getattr(el, "value", None)
        try:
            return ("num", round(float(v), 12))
        except (ValueError, TypeError):  # 值无法转为浮点（None/字符串/复数）：用 repr 作为键
            return ("num", repr(v))
    if kind == "list":
        # 列表可能**不可见**（如命令参数里的内联列表 `_hl`）→ draw() 返回 None，
        # 若沿用通用路径会得到常量指纹，使依赖者误命中过期缓存（实测 Voronoi/Sum 不刷新）。
        # 因此这里直接用 items/itemkind 构造有界指纹。
        items = getattr(el, "items", []) or []
        acc, cnt, shape = 0.0, 0, 0
        for it in items[:200]:
            if isinstance(it, bool):
                continue
            if isinstance(it, (int, float)):
                acc += float(it)
                cnt += 1
            elif isinstance(it, (list, tuple)):
                shape = max(shape, len(it))
                for x in it[:4]:
                    if isinstance(x, (int, float)) and not isinstance(x, bool):
                        acc += float(x)
                        cnt += 1
        return ("list", getattr(el, "itemkind", ""), len(items), shape, round(acc, 9), cnt)
    if kind == "boolean":
        return ("bool", bool(getattr(el, "value", None)))
    if kind == "complex":
        return ("cplx", round(float(getattr(el, "re", 0.0)), 12), round(float(getattr(el, "im", 0.0)), 12))
    # 通用路径：用 draw() 输出做有界几何指纹（覆盖多边形/圆/线段/函数/圆锥/圆弧/折线…）
    try:
        d = el.draw(_SIG_VIEW)
        parts: List[Any] = []
        _sig_walk(d, parts)
        if parts:
            return (kind, tuple(parts))
    except Exception:  # 防御性捕获：该分支失败不应中断用户操作
        pass
    return (kind, getattr(el, "defn", ""), getattr(el, "error", None))


def key_for(el) -> Optional[Tuple]:
    """派生元素的计算记忆键；自由元素/无 _fn 元素返回 None。"""
    if getattr(el, "free", False) or getattr(el, "_fn", None) is None:
        return None
    defn = getattr(el, "defn", "") or ""
    # 随机性命令的结果不依赖输入状态 → 绝不能命中记忆
    low = defn.lower()
    if "random" in low or "随机" in low:
        return None
    deps = getattr(el, "deps", None) or []
    try:
        return (getattr(el, "kind", ""), el.defn, tuple(_state_sig(d) for d in deps))
    except Exception:  # 防御性捕获：该分支失败不应中断用户操作
        return None


def _size_of(state: Dict[str, Any]) -> int:
    n = 1
    data = state.get("data")
    if isinstance(data, dict):
        for k in ("verts", "faces", "edges", "segs", "pts"):
            v = data.get(k)
            if isinstance(v, list):
                n += len(v)
    return n


def get(key: Optional[Tuple]) -> Optional[Dict[str, Any]]:
    global HITS, MISSES, _COORDS
    if key is None:
        return None
    hit = _STORE.get(key)
    if hit is None:
        MISSES += 1
        return None
    HITS += 1
    _STORE.move_to_end(key)
    return dict(hit)          # 浅拷贝顶层字典；内部网格数据只读复用


def put(key: Optional[Tuple], state: Dict[str, Any]) -> None:
    global _COORDS
    if key is None or not isinstance(state, dict):
        return
    if key in _STORE:
        _COORDS -= _size_of(_STORE[key])
    _STORE[key] = state
    _STORE.move_to_end(key)
    _COORDS += _size_of(state)
    while _STORE and (len(_STORE) > _MAX_ENTRIES or _COORDS > _MAX_COORDS):
        _old, old_state = _STORE.popitem(last=False)
        _COORDS -= _size_of(old_state)


def clear() -> None:
    global _COORDS
    _STORE.clear()
    _COORDS = 0


def stats() -> Dict[str, Any]:
    return {"entries": len(_STORE), "coords": _COORDS, "hits": HITS, "misses": MISSES}
