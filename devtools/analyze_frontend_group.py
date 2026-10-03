#!/usr/bin/env python3
"""前端函数组耦合分析（前端拆分配套，与 kernel 的 extract_group.py 对应）。

对 server/static/app.js 的任意函数组计算：
- 传递闭包（组内互相调用的顶层函数）
- 每个函数读/写的**应用级状态**（缩进 2 的 `var`，即 `^  var X =`）
- 组外依赖的顶层函数（需一并搬迁或注入）
- 代码行数合计

用法：
    python3 devtools/analyze_frontend_group.py drawGrid strokeSeg strokePoly ...
    python3 devtools/analyze_frontend_group.py --list      # 列出候选：状态耦合 ≤6 的函数组

约定：app.js 顶层函数以「缩进 2 的 `}`」行结束（本仓库格式统一；JS 正则字面量会让
括号配平失效，故不采用配平）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "server" / "static" / "app.js"


def split_declarators(rest: str):
    """把 `a = 1, b = 2, c` 按顶层逗号拆开（忽略 {} [] () 内的逗号，如 `var view = {a:1,b:2}`）。"""
    out, depth, cur = [], 0, ""
    for ch in rest:
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def load():
    """收集顶层函数名与**应用级状态**（缩进 2 的 var/let/const）。

    注意支持多声明语句（`var cssW = 0, cssH = 0, dpr = 1;`）与无初始化的 `var X;` ——
    曾因只取第一个声明符导致 `cssH` 未被识别，draw2d 模块运行时报 ReferenceError。
    """
    lines = APP.read_text(encoding="utf-8").splitlines(keepends=True)
    top_fns, top_vars = set(), set()
    for l in lines:
        m = re.match(r"^  function (\w+)\(", l)
        if m:
            top_fns.add(m.group(1))
            continue
        m = re.match(r"^  (?:var|let|const)\s+(.+?);?\s*$", l.rstrip("\n"))
        if m:
            for part in split_declarators(m.group(1)):
                nm = re.match(r"\s*([A-Za-z_$][\w$]*)", part)
                if nm:
                    top_vars.add(nm.group(1))
    return lines, top_fns, top_vars


def span(lines, name):
    """返回 (起行, 止行+1)。

    单行薄包装（`function f() { return _x.f.apply(...); }`）必须按行处理，否则
    span 会越过边界吞掉后续函数 —— 曾因此把整个 panels 组误判进 draw2d 闭包。
    """
    i = next(k for k, l in enumerate(lines) if re.match(r"^  function %s\(" % name, l))
    if lines[i].rstrip().endswith("}"):
        return i, i + 1
    j = i + 1
    while j < len(lines) and not re.match(r"^  \}\s*$", lines[j]):
        j += 1
    return i, j + 1


def strip_literals(body: str) -> str:
    body = re.sub(r"//[^\n]*", "", body)
    body = re.sub(r"'(?:[^'\\]|\\.)*'", "''", body)
    body = re.sub(r'"(?:[^"\\]|\\.)*"', '""', body)
    return body


def calls(body: str):
    return set(re.findall(r"(?<![\w.$])([A-Za-z_$][\w$]*)\s*\(", body))


def analyze(seeds):
    lines, top_fns, top_vars = load()
    got, q = set(), list(seeds)
    while q:
        n = q.pop()
        if n in got or n not in top_fns:
            continue
        got.add(n)
        i, j = span(lines, n)
        for c in calls("".join(lines[i:j])):
            if c in top_fns and c not in got:
                q.append(c)
    per = {}
    for n in sorted(got):
        i, j = span(lines, n)
        body = "".join(lines[i:j])
        clean = strip_literals(body)
        st = sorted(v for v in top_vars if re.search(r"(?<![\w.$])%s(?![\w$])" % re.escape(v), clean))
        writes = sorted(v for v in st if re.search(
            r"(?:(?<![\w.$])%s\s*(?:=[^=]|\+=|-=|\+\+|--)|(?:\+\+|--)\s*%s(?![\w$]))"
            % (re.escape(v), re.escape(v)), clean))
        ext = sorted(c for c in calls(body) if c in top_fns and c not in got)
        per[n] = {"lines": j - i, "state": st, "writes": writes, "ext_fn": ext}
    return per, lines, top_fns


def report(seeds):
    per, _, _ = analyze(seeds)
    if not per:
        print("未找到函数:", seeds)
        return per
    all_state = sorted({s for v in per.values() for s in v["state"]})
    all_writes = sorted({s for v in per.values() for s in v["writes"]})
    ext = sorted({c for v in per.values() for c in v["ext_fn"]})
    print("闭包 %d 函数 / %d 行" % (len(per), sum(v["lines"] for v in per.values())))
    for n in sorted(per, key=lambda x: per[x]["lines"], reverse=True):
        v = per[n]
        print("  %-22s %4d 行  状态[%s] 写[%s] 组外[%s]" % (
            n, v["lines"], ",".join(v["state"]) or "-", ",".join(v["writes"]) or "-",
            ",".join(v["ext_fn"]) or "-"))
    print("合并状态(%d): %s" % (len(all_state), ", ".join(all_state)))
    print("写入(%d): %s" % (len(all_writes), ", ".join(all_writes) or "无"))
    print("组外函数: %s" % (", ".join(ext) or "无"))
    return per


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--json":
        print(json.dumps(report(args[1:]), ensure_ascii=False, indent=1))
    else:
        report(args)
