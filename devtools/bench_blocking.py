#!/usr/bin/env python3
"""阻塞压测（REVIEW P0-2）：重计算期间的请求排队延迟。

做法：
1. 会话 H 与 会话 P（不同 sid）；
2. 空闲基线：对 P 连打 N 次轻请求（GET /api/state），记录延迟；
3. 会话 H 上跑一条重命令（默认 ImplicitSurface n=32）；
4. 重命令运行期间，对 **P** 持续打同样的轻请求，记录延迟；
5. 输出：重命令耗时、空闲基线（p50/max）、阻塞期（p50/max/失败数）、放大倍数。

跨会话测量是刻意的：若阻塞只影响同会话，说明锁是会话级；若**跨会话也排队**，
说明 CPU 计算在持有全局解释器/单进程事件循环期间阻塞了所有请求（P0-2 的核心论点）。

用法：
    python3 devtools/bench_blocking.py [--base http://127.0.0.1:8090] [--n 32] [--probes 40]
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import urllib.error
import urllib.request

# 每次运行用**唯一**表达式（ε 级偏移，形状不变）：否则第二次会命中 kernel/memo.py 的计算记忆，
# 重命令耗时骤降、A/B 对比失真（本次实测踩到：1925 ms → 320 ms 就是缓存命中）。
HEAVY = ("ImplicitSurface[x^2+y^2+z^2-(4.0+{eps})=0,-2.2,2.2,-2.2,2.2,-2.2,2.2,{n}]")


def post(base: str, path: str, sid: str, payload: dict, timeout: float = 120.0):
    req = urllib.request.Request(
        base + path + ("?sid=" + sid if sid else ""),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def get_ms(base: str, path: str, sid: str, timeout: float = 120.0):
    t0 = time.perf_counter()
    req = urllib.request.Request(base + path + ("?sid=" + sid if sid else ""))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()
        st = r.status
    return (time.perf_counter() - t0) * 1000.0, st


def stats(xs):
    if not xs:
        return {"n": 0, "p50": None, "max": None}
    return {"n": len(xs), "p50": statistics.median(xs), "max": max(xs)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8090")
    ap.add_argument("--n", type=int, default=32, help="隐式曲面分辨率")
    ap.add_argument("--probes", type=int, default=40, help="空闲基线探测次数")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    sid_h, sid_p = "bench_heavy", "bench_probe"

    # 干净起点
    for sid in (sid_h, sid_p):
        post(base, "/api/clear", sid, {})

    # 空闲基线
    base_ms = []
    for _ in range(a.probes):
        ms, _st = get_ms(base, "/api/state", sid_p)
        base_ms.append(ms)
    b = stats(base_ms)

    # 重计算 + 并发探测
    probe_ms, fails = [], [0]
    done = threading.Event()

    def prober():
        while not done.is_set():
            try:
                ms, _st = get_ms(base, "/api/state", sid_p, timeout=180.0)
                probe_ms.append(ms)
            except Exception:
                fails[0] += 1
            time.sleep(0.02)

    th = threading.Thread(target=prober, daemon=True)
    cmd = HEAVY.format(n=a.n, eps="%d" % (time.time_ns() % 1000000 + 1))
    t0 = time.perf_counter()
    th.start()
    st, js = post(base, "/api/input", sid_h, {"text": "S=" + cmd}, timeout=300.0)
    heavy_ms = (time.perf_counter() - t0) * 1000.0
    done.set()
    th.join(timeout=5)
    p = stats(probe_ms)

    print("=== 阻塞压测（REVIEW P0-2）===")
    print("  重命令: %s" % cmd)
    print("  重命令耗时: %.0f ms（HTTP %s, ok=%s）" % (heavy_ms, st, js.get("ok")))
    print("  空闲基线(会话 P): n=%d p50=%.1f ms max=%.1f ms" % (b["n"], b["p50"], b["max"]))
    print("  阻塞期探测(会话 P): n=%d p50=%.1f ms max=%.1f ms 失败=%d"
          % (p["n"], p["p50"] or -1, p["max"] or -1, fails[0]))
    if b["p50"]:
        print("  放大: p50 ×%.1f / max ×%.1f" % (p["p50"] / b["p50"], (p["max"] or 0) / b["max"]))
    print("  结论: %s" % ("跨会话阻塞（全局排队）" if (p["p50"] or 0) > 5 * (b["p50"] or 1)
                        else "未观测到显著跨会话阻塞"))
    post(base, "/api/clear", sid_h, {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
