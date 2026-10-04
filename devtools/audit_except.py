#!/usr/bin/env python3
"""`except Exception` 审计工具（REVIEW P1 第 10 条）。

对 kernel/ 与 server/ 的每处宽泛捕获，打印：
  - 位置、缩进、是否带说明注释
  - 所属 try 体的前两条语句（判断「捕获的是什么操作」）
  - 分类建议：可收窄（解析/IO/数值）或需保留（防御性回滚、可选失败）

用法：
    python3 devtools/audit_except.py            # 全量清单
    python3 devtools/audit_except.py --stats    # 只输出统计
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NARROW_HINT = {
    "json": "json.JSONDecodeError",
    "float(": "ValueError/TypeError",
    "int(": "ValueError/TypeError",
    "open(": "OSError",
    "read_text": "OSError",
    "write_text": "OSError",
    "os.": "OSError",
    "localStorage": "-",
    "re.compile": "re.error",
    "re.match": "-",
    "Decimal": "InvalidOperation",
}


def sites():
    out = []
    for f in sorted(list((ROOT / "kernel").glob("*.py")) + list((ROOT / "server").glob("*.py"))):
        lines = f.read_text(encoding="utf-8").splitlines()
        for i, l in enumerate(lines):
            if "except Exception" not in l:
                continue
            # 找所属 try（向上找最近的 try:）
            j = i - 1
            while j >= 0 and not lines[j].strip().startswith("try:"):
                j -= 1
            body = []
            if j >= 0:
                k = j + 1
                while k < i and len(body) < 2:
                    if lines[k].strip() and not lines[k].strip().startswith("#"):
                        body.append(lines[k].strip())
                    k += 1
            prev = lines[i - 1].strip() if i else ""
            same = l.split("#", 1)[1].strip() if "#" in l else ""
            note = same or (prev if prev.startswith("#") else "")
            hint = ""
            joined = " ".join(body)
            for key, val in NARROW_HINT.items():
                if key in joined:
                    hint = val
                    break
            out.append({"file": f.relative_to(ROOT), "line": i + 1, "note": note,
                        "body": body, "hint": hint})
    return out


def main() -> int:
    s = sites()
    if "--stats" in sys.argv:
        noted = [x for x in s if x["note"]]
        hints = [x for x in s if x["hint"] and x["hint"] != "-"]
        print("总站点: %d | 带说明: %d | 无说明: %d | 疑似可收窄: %d"
              % (len(s), len(noted), len(s) - len(noted), len(hints)))
        for x in hints:
            print("  可收窄? %s:%d → %s   %s" % (x["file"], x["line"], x["hint"], x["body"][:1]))
        return 0
    for x in s:
        print("%s:%d%s  %s" % (x["file"], x["line"],
                               "  # " + x["note"] if x["note"] else "",
                               (x["body"][0][:70] if x["body"] else "")))
    noted = [x for x in s if x["note"]]
    print("\n合计 %d 处，其中带说明 %d 处" % (len(s), len(noted)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
