#!/usr/bin/env python3
"""前端函数组抽取（与 kernel/extract_group.py 对应）。

把 server/static/app.js 里一组函数搬到独立模块：

    python3 devtools/extract_frontend_group.py --module draw2d --api GGB_D2 \
        --seeds drawGrid,strokeSeg,strokePoly --doc "…" [--apply]

生成模块形态：`window.<API>.create(env)`
- 应用级状态（缩进 2 的 var）：只读 → 函数体开头注入 `var X = env.get('X');`
  被写 → 该变量全程 `env.get(...)` / `env.set(...)`（不设别名，避免快照过期）
- 组内调用的「转发型薄包装」（`function f() { return _m.f.apply(null, arguments); }`）
  → 生成 `function f() { return env.f.apply(null, arguments); }`，由 app.js 注入

app.js 侧：删除原实现 → 扩展状态 switch（`_stateGet`）→ 建模块实例 → 生成同名薄包装
index.html 侧：在 app.js 之前加载新脚本
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_frontend_group import APP, ROOT, analyze, calls, load, span, strip_literals  # noqa: E402


def is_forwarder(body: str) -> bool:
    return bool(re.match(r"^  function \w+\([^)]*\) \{ return _\w+\.\w+\.apply\(null, arguments\); \}$",
                         body.rstrip("\n")))


def build(module, api, seeds, doc, apply_changes):
    lines, top_fns, top_vars = load()
    per, _, _ = analyze(seeds)
    ORDER = [n for n in sorted(per, key=lambda x: span(lines, x)[0])]
    bodies = {}
    for n in ORDER:
        i, j = span(lines, n)
        bodies[n] = "".join(lines[i:j]).rstrip("\n")

    # 转发型薄包装（`function f(){ return _mod.f.apply(...) }`）属于**别的模块**：
    # 不能搬走（否则 app.js 注入的 f 指向本模块 → 无限递归），应当作注入助手。
    forwarders = []
    for n in ORDER:
        if is_forwarder(bodies[n]):
            m = re.match(r"^  function \w+\([^)]*\) \{ return _(\w+)\.", bodies[n].rstrip("\n"))
            if m and m.group(1) != module:
                forwarders.append(n)
    injected = forwarders
    real = [n for n in ORDER if n not in injected]
    all_state = sorted({s for n in real for s in per[n]["state"] if s != api and not s.startswith("_")})
    writes = sorted({s for n in real for s in per[n]["writes"]})

    def emit(n):
        body = bodies[n]
        if n in injected:
            return "  var %s = env.%s;   // 由 app.js 注入（属于其他模块）" % (n, n)
        st, wr = per[n]["state"], per[n]["writes"]
        for w in wr:
            body = re.sub(r"(?<![\w.$])%s(?!\w|\s*\()" % re.escape(w), "env.get('%s')" % w, body)
            body = re.sub(r"env\.get\('%s'\)\s*=\s*([^;\n]+);" % re.escape(w),
                          lambda m, w=w: "env.set('%s', %s);" % (w, m.group(1).strip()), body)
        reads = [v for v in st if v not in wr]
        alias_names = ", ".join("%s = env.get('%s')" % (v, v) for v in reads)
        head = re.search(r"^(  function %s\([^)]*\) \{\n)" % re.escape(n), body)
        if head:                       # 多行函数：别名占一行
            alias = "    var " + alias_names + ";\n" if reads else ""
            return body[:head.end()] + alias + body[head.end():]
        one = re.search(r"^(  function %s\([^)]*\) \{ )" % re.escape(n), body)
        assert one, n                  # 单行函数：别名内联在 `{ ` 之后
        alias = ("var " + alias_names + "; ") if reads else ""
        return body[:one.end()] + alias + body[one.end():]

    header = '/* ggbpy %s（P2 前端拆分：从 app.js 抽出）。\n *\n * 用法（app.js）：\n *   var _%s = %s.create({ get: _stateGet%s });\n *   之后同名函数由 app.js 保留薄包装，调用点无需改动。\n *\n * 状态：%s\n */\nwindow.%s = (function () {\n  \'use strict\';\n\n  function create(env) {\n' % (
        doc, module, api, "".join(", %s: %s" % (f, f) for f in forwarders), ", ".join(all_state) or "（无）", api)
    footer = '\n\n    return {\n%s    };\n  }\n\n  return { create: create };\n})();\n' % "".join(
        "      %s: %s,\n" % (n, n) for n in ORDER)
    src = header + "\n\n".join("    " + emit(n).replace("\n", "\n    ") for n in ORDER) + footer
    print("[%s] 闭包 %d 函数 / %d 行；状态 %s；转发注入 %s" % (
        module, len(ORDER), sum(per[n]["lines"] for n in ORDER),
        ", ".join(all_state) or "无", ", ".join(forwarders) or "无"))
    if not apply_changes:
        print("（干跑，未写文件）")
        return per, ORDER, all_state, writes, forwarders

    (ROOT / "server" / "static" / (module + ".js")).write_text(src, encoding="utf-8")

    # ---- app.js ----
    out = list(lines)
    spans = {n: span(lines, n) for n in ORDER if n not in injected}
    for n in sorted(spans, key=lambda x: -spans[x][0]):
        a, b = spans[n]
        del out[a:b]
    app = "".join(out)
    # 扩展状态 switch
    m = re.search(r"  function _panelStateGet\(k\) \{\n    switch \(k\) \{\n", app)
    assert m, "未找到 _panelStateGet"
    existing = set(re.findall(r"case '(\w+)':", app))
    add_cases = "".join("      case '%s': return %s;\n" % (v, v) for v in all_state if v not in existing)
    app = app[:m.end()] + add_cases + app[m.end():]
    # 状态写入（若有）
    if writes:
        sm = re.search(r"  function _panelStateSet\(k, v\) \{ ([^\n]*)\}", app)
        assert sm
        conds = "".join("\n    if (k === '%s') { %s = v; return; }" % (w, w) for w in writes)
        app = app[:sm.start()] + "  function _panelStateSet(k, v) {%s\n  }" % conds + app[sm.end():]
    anchor = "  function setMsg(msg, isErr) {"
    assert app.count(anchor) == 1
    inject_helpers = "".join(", %s: %s" % (f, f) for f in forwarders)
    wrappers = "\n".join("  function %s() { return _%s.%s.apply(null, arguments); }" % (n, module, n)
                          for n in ORDER if n not in injected)
    insert = ("  // %s 已抽到 static/%s.js（P2 前端拆分）；同名薄包装保持调用点不变\n"
              "  var _%s = window.%s.create({ get: _panelStateGet%s });\n%s\n\n"
              % (doc, module, module, api, inject_helpers, wrappers))
    app = app.replace(anchor, insert + anchor, 1)
    APP.write_text(app, encoding="utf-8")
    print("  已写入 static/%s.js；app.js 现在 %d 行" % (module, len(app.splitlines())))

    # ---- index.html ----
    idx = ROOT / "server" / "static" / "index.html"
    h = idx.read_text(encoding="utf-8")
    if "/static/%s.js" % module not in h:
        tag = '<script src="/static/app.js"></script>'
        assert h.count(tag) == 1
        h = h.replace(tag, '<script src="/static/%s.js"></script>\n' % module + tag, 1)
        idx.write_text(h, encoding="utf-8")
        print("  index.html 已加载 %s.js" % module)
    return per, ORDER, all_state, writes, forwarders


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", required=True)
    ap.add_argument("--api", default="")
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--doc", default="")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    build(a.module, a.api or ("GGB_" + a.module.upper()), [s.strip() for s in a.seeds.split(",") if s.strip()],
          a.doc or (a.module + " 渲染/绘制函数（P2 前端拆分：从 app.js 抽出）。"), a.apply)


if __name__ == "__main__":
    main()
