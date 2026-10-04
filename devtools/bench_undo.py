#!/usr/bin/env python3
"""撤销/重做压测（REVIEW P0-3）：快照规模与回放耗时。

关注三件事：
1. **快照规模**：`Construction.snapshot()` 是「全量 (label, defn, 样式) 列表」，
   200 个快照（`UNDO_LIMIT`）在 N 个对象下占多少字节？
2. **快照成本**：每次 `_push_undo()` 的耗时（是否与 N 线性、是否值得做差量）。
3. **回放成本**：`restore()` 清空 + 逐条 `process_internal` 重放；
   计算记忆（kernel/memo.py）命中时应远快于冷启动重建。

用法：python3 devtools/bench_undo.py [--n 120] [--heavy 16]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import tracemalloc

sys.path.insert(0, ".")
from kernel.construction import UNDO_LIMIT, Construction  # noqa: E402


def build(n: int, heavy: int = 0) -> Construction:
    c = Construction()
    c.process("O=(0,0)")
    c.process("P1=(3,0)")
    c.process("k=Circle[O,P1]")
    i = 0
    while len(c.order) < n:
        i += 1
        c.process("A%d=(%d,%d)" % (i, i % 17 - 8, (i * 3) % 11 - 5))
        c.process("s%d=Segment[O,A%d]" % (i, i))
        if i % 5 == 0:
            c.process("c%d=Circle[A%d,1.5]" % (i, i))
        if i % 7 == 0:
            c.process("L%d=Line[O,A%d]" % (i, i))
        if heavy and i == 1:
            c.process("S=ImplicitSurface[x^2+y^2+z^2-4=0,-2.2,2.2,-2.2,2.2,-2.2,2.2,%d]" % heavy)
    return c


def ms(f, reps=1):
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        f()
        ts.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(ts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120, help="目标对象数")
    ap.add_argument("--heavy", type=int, default=0, help="加入一个 n=? 的隐式曲面（0=不加）")
    ap.add_argument("--memo-cold", action="store_true", help="每次 restore 前清空计算记忆（模拟条目被淘汰/首次回放）")
    a = ap.parse_args()

    c = build(a.n, a.heavy)
    snap = c.snapshot()
    n_el = len(snap)
    size_json = len(json.dumps(snap, ensure_ascii=False).encode("utf-8"))
    per_el = size_json / max(1, n_el)

    print("=== 撤销/重做压测（REVIEW P0-3）===")
    print("  对象数: %d（含隐式曲面: %s）" % (n_el, ("n=%d" % a.heavy) if a.heavy else "无"))
    print("  单快照: %d 字节（%.0f 字节/对象）" % (size_json, per_el))
    print("  %d 个快照（UNDO_LIMIT）合计: %.2f MB（仅快照文本；不含元素对象本身）"
          % (UNDO_LIMIT, size_json * UNDO_LIMIT / 1048576.0))

    # 快照成本
    t_snap = ms(c.snapshot, reps=200)
    print("  snapshot() 耗时: %.3f ms/次（N=%d）" % (t_snap, n_el))

    # 回放成本：直接 restore 同一快照（记忆热）；--memo-cold 时每次先清空记忆
    from kernel import memo as _memo
    if a.memo_cold:
        def _restore_cold():
            _memo.clear()
            c.restore(snap)
        t_restore_warm = ms(_restore_cold, reps=3)
    else:
        t_restore_warm = ms(lambda: c.restore(snap), reps=5)
    # 冷路径：重建同规模构造（模拟首次回放 / 记忆未命中）
    t_cold = ms(lambda: build(a.n, a.heavy), reps=3)
    print("  restore() %s: %.0f ms" % ("记忆清空(冷)" if a.memo_cold else "记忆热", t_restore_warm))
    print("  重建同规模构造（冷）: %.0f ms" % t_cold)
    print("  加速比: ×%.0f（计算记忆 kernel/memo.py 的作用）"
          % (t_cold / max(0.001, t_restore_warm)))

    # 撤销栈真实内存（tracemalloc，含 Python 对象开销）
    tracemalloc.start()
    c2 = build(a.n, a.heavy)
    for _ in range(UNDO_LIMIT):
        c2._push_undo()
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print("  %d 个快照的 Python 对象开销: 当前 %.2f MB / 峰值 %.2f MB"
          % (len(c2._undo), cur / 1048576.0, peak / 1048576.0))
    print("  单步 undo 端到端（内核级）: %.3f ms" % ms(lambda: (c2.undo(), c2.redo()), reps=20))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
