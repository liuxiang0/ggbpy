"""会话隔离（P2）：每个会话拥有独立的构造 / CAS / state3d rev 历史 / 变更锁 / 宏。

设计要点：
- 会话 id 来源：查询参数 `?sid=`（脚本/测试可显式指定）> cookie `ggbpy_sid` > `default`
- 每个请求由中间件解析出会话并写入 ContextVar；`server.main` 里的 `cons` / `cas` /
  `_SD` 是**代理对象**，属性访问时按当前请求解析到对应会话 —— 端点代码无需改动。
- 会话数上限 + TTL（超限淘汰最久未使用）；`default` 会话永不淘汰（兼容旧脚本）。
"""

from __future__ import annotations

import contextvars
import threading
import time
from collections import OrderedDict
from typing import Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware

from kernel.cas import CASEngine
from kernel.construction import Construction

MAX_SESSIONS = 24
TTL_SECONDS = 6 * 3600
COOKIE_NAME = "ggbpy_sid"
DEFAULT_SID = "default"

_current_sid: contextvars.ContextVar[str] = contextvars.ContextVar("ggbpy_sid", default=DEFAULT_SID)


class Session:
    """一个会话的全部可变状态。"""

    def __init__(self, sid: str) -> None:
        self.sid = sid
        self.cons = Construction()
        self.cons.macros = {}          # 宏随会话隔离（不跨用户泄漏）
        self.cas = CASEngine(self.cons)
        # state3d 增量协议：rev / 指纹表 / 历史 / 锁
        self.sd: Dict[str, object] = {"rev": 0, "fp": {}, "hist": {}, "lock": threading.Lock()}
        self.lock = threading.Lock()   # 该会话的构造变更串行化
        self.created = time.time()
        self.touched = self.created
        self.requests = 0

    def mut(self, fn, *args, **kwargs):
        """会话内串行执行一次变更。"""
        with self.lock:
            self.touched = time.time()
            self.requests += 1
            return fn(*args, **kwargs)

    def touch(self) -> None:
        self.touched = time.time()
        self.requests += 1

    def info(self) -> Dict[str, object]:
        return {"sid": self.sid, "elements": len(self.cons.order),
                "can_undo": len(self.cons._undo) > 0, "can_redo": len(self.cons._redo) > 0,
                "requests": self.requests, "age": round(time.time() - self.created, 1),
                "idle": round(time.time() - self.touched, 1)}


_SESSIONS: "OrderedDict[str, Session]" = OrderedDict()
_LOCK = threading.Lock()


def resolve_sid(query_sid: Optional[str], cookie_sid: Optional[str]) -> str:
    sid = (query_sid or "").strip() or (cookie_sid or "").strip() or DEFAULT_SID
    return sid[:64]


def get_session(sid: str) -> Session:
    """取（或创建）会话；超过上限时淘汰最久未使用的非 default 会话。"""
    with _LOCK:
        s = _SESSIONS.get(sid)
        if s is None:
            s = Session(sid)
            _SESSIONS[sid] = s
        _SESSIONS.move_to_end(sid)
        _evict_locked()
        return s


def _evict_locked() -> int:
    now = time.time()
    dropped = 0
    for sid in list(_SESSIONS.keys()):
        if sid == DEFAULT_SID:
            continue
        s = _SESSIONS[sid]
        if now - s.touched > TTL_SECONDS:
            _SESSIONS.pop(sid, None)
            dropped += 1
    while len(_SESSIONS) > MAX_SESSIONS:
        victim = next((sid for sid in _SESSIONS if sid != DEFAULT_SID), None)
        if victim is None:
            break
        _SESSIONS.pop(victim, None)
        dropped += 1
    return dropped


def sweep() -> int:
    """手动清理过期会话（供 /api/session 与测试调用）。"""
    with _LOCK:
        return _evict_locked()


def session_stats() -> Dict[str, object]:
    with _LOCK:
        return {"count": len(_SESSIONS), "max": MAX_SESSIONS, "ttl": TTL_SECONDS,
                "sids": [{"sid": s.sid, "elements": len(s.cons.order), "idle": round(time.time() - s.touched, 1)}
                         for s in _SESSIONS.values()]}


def current_session() -> Session:
    """当前请求所属会话（无请求上下文时落到 default）。"""
    return get_session(_current_sid.get())


def set_current(sid: str) -> None:
    _current_sid.set(sid)


def reset_for_tests() -> None:
    """仅测试用：清空会话表。"""
    with _LOCK:
        _SESSIONS.clear()


class SessionMiddleware(BaseHTTPMiddleware):
    """解析会话 id（?sid= > cookie > default），写入 ContextVar 并按需下发 cookie。"""

    async def dispatch(self, request, call_next):
        qsid = request.query_params.get("sid")
        csid = request.cookies.get(COOKIE_NAME)
        sid = resolve_sid(qsid, csid)
        set_current(sid)
        get_session(sid).touch()
        response = await call_next(request)
        # 只在「显式 ?sid=」时下发 cookie：无 cookie 的脚本请求保持 cookie-less（落到 default），
        # 浏览器端由前端生成自己的随机 sid，从而各浏览器/上下文天然隔离。
        if qsid and request.cookies.get(COOKIE_NAME) != sid:
            response.set_cookie(COOKIE_NAME, sid, max_age=86400, samesite="lax")
        return response
