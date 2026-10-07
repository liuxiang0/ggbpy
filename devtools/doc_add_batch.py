#!/usr/bin/env python3
"""**安全追加 CHANGELOG 批次条目**（把「踩过的坑」变成工具，而不是靠记性）。

为什么需要它：连续两批用「替换锚点行」的方式写 CHANGELOG，把上一批**整条删掉**了 ✗。
本工具强制：**在最新批次行之前插入** + 编号自增校验 + 写后调用 `test_quality.py` 的结构守卫，
守卫不过就**自动回滚**（原子性：要么写成，要么原样不动）。

用法：
    python3 devtools/doc_add_batch.py --title "标题（日期）" --details "① … ② …"
    python3 devtools/doc_add_batch.py --title "…" --details "…" --dry-run
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
BACKUP = ROOT / "logs" / "doc_add_batch.bak.log"
_NUM = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
PAT = re.compile(r"^- \*\*第([一二三四五六七八九十百零]+)批")


def cn2int(t: str) -> int:
    section, cur = 0, 0
    for ch in t:
        if ch in _NUM:
            cur = _NUM[ch]
        elif ch == "十":
            section += (cur or 1) * 10
            cur = 0
        elif ch == "百":
            section += (cur or 1) * 100
            cur = 0
    return section + cur


def int2cn(n: int) -> str:
    d = "零一二三四五六七八九"
    assert 0 < n < 1000, n
    if n < 10:
        return d[n]
    if n < 20:
        return "十" + (d[n % 10] if n % 10 else "")
    if n < 100:
        return d[n // 10] + "十" + (d[n % 10] if n % 10 else "")
    head = d[n // 100] + "百"
    rest = n % 100
    if rest == 0:
        return head
    if rest < 10:
        return head + "零" + d[rest]
    return head + d[rest // 10] + "十" + (d[rest % 10] if rest % 10 else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True, help="批次标题（含日期），如：某某功能（2026-10-07）")
    ap.add_argument("--details", required=True, help="条目要点（①②③…）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    lines = CHANGELOG.read_text(encoding="utf-8").split("\n")
    found = [(cn2int(m.group(1)), i) for i, l in enumerate(lines) for m in [PAT.match(l)] if m]
    if not found:
        print("✗ 没找到任何批次条目，拒绝写入")
        return 1
    newest, newest_i = max(found)
    new_no = newest + 1
    entry = "- **第%s批：%s**：%s" % (int2cn(new_no), a.title.strip(), a.details.strip())
    assert "\n" not in entry
    print("最新批次 = 第%d批（行 %d）→ 本次将插入：第%d批" % (newest, newest_i + 1, new_no))
    print("待写入条目：" + entry[:70] + "…")
    if a.dry_run:
        print("（--dry-run：未写入）")
        return 0

    BACKUP.parent.mkdir(exist_ok=True)
    shutil.copy2(CHANGELOG, BACKUP)
    out = lines[:newest_i] + [entry] + lines[newest_i:]     # ← 只在锚点行**之前插入**，绝不替换锚点行
    CHANGELOG.write_text("\n".join(out), encoding="utf-8")

    chk = CHANGELOG.read_text(encoding="utf-8").split("\n")
    nums = [cn2int(m.group(1)) for l in chk for m in [PAT.match(l)] if m]
    ok = (len(chk) == len(lines) + 1 and nums.count(new_no) == 1 and new_no in nums)
    if not ok:                                              # 自身断言：行数 +1、新编号唯一
        shutil.copy2(BACKUP, CHANGELOG)
        print("✗ 自检失败（行数/编号不符），已回滚")
        return 1
    # 交给**结构守卫**复核（编号唯一/最新段连续/段长/总数/条目长度）
    r = subprocess.run([sys.executable, "-B", str(ROOT / "devtools" / "test_quality.py")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        shutil.copy2(BACKUP, CHANGELOG)
        tail = "\n".join([l for l in r.stdout.split("\n") if "FAIL" in l or "结果" in l][-6:])
        print("✗ 结构守卫未通过 → 已回滚\n" + tail)
        return 1
    print("✓ 已插入第%d批（行 %d），结构守卫通过" % (new_no, newest_i + 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
