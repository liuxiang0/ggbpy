#!/usr/bin/env python3
"""统一数值容差检测（P2/P3）：常量分级、源码零魔数、前后端取值一致。

背景：`1e-12` / `1e-9` 这类「判定接近 0」的魔数曾散落在 13 个内核模块里（264 处），
本检测确保：
  1) 容差常量集中在 `kernel/tolerance.py`，取值与分级有文档、顺序正确；
  2) kernel/ 与 server/ 的**代码**（不含注释/文档串）里不再出现浮点科学计数字面量；
  3) 扫描器自带自检（植入字面量必须被抓到），避免守卫失效；
  4) 前端 `app.js` 只用同名常量，且与内核取值一致。

用法：python3 -B devtools/test_tolerance.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
FAILED = []

LIT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?e-\d+)(?![\w.])")


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  OK   " + name + (("  [" + detail + "]") if detail else ""))
    else:
        FAIL += 1
        FAILED.append(name)
        print("  FAIL " + name + "  " + detail)


def strip_py(line: str) -> str:
    """把字符串字面量与注释替换成空白，只留可执行的代码。"""
    out, i, in_str = [], 0, None
    while i < len(line):
        ch = line[i]
        if in_str:
            if ch == "\\" and i + 1 < len(line):
                out.append("  "); i += 2; continue
            if ch == in_str:
                in_str = None
            out.append(" "); i += 1; continue
        if ch in "\"'":
            in_str = ch; out.append(" "); i += 1; continue
        if ch == "#":
            out.append(" " * (len(line) - i)); break
        out.append(ch); i += 1
    return "".join(out)


def strip_js(line: str) -> str:
    out, i, in_str = [], 0, None
    while i < len(line):
        ch = line[i]
        if in_str:
            if ch == "\\" and i + 1 < len(line):
                out.append("  "); i += 2; continue
            if ch == in_str:
                in_str = None
            out.append(" "); i += 1; continue
        if ch in "\"'":
            in_str = ch; out.append(" "); i += 1; continue
        if line.startswith("//", i):
            out.append(" " * (len(line) - i)); break
        out.append(ch); i += 1
    return "".join(out)


def scan_code_literals(path: Path, stripper, skip_docstrings: bool):
    """返回 [(行号, 字面量, 行内容)]：只统计代码部分（跳过注释/字符串/文档串）。"""
    hits = []
    in_doc = False
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if skip_docstrings and ('"""' in line or "'''" in line):
            if line.count('"""') % 2 or line.count("'''") % 2:
                in_doc = not in_doc
            continue
        if skip_docstrings and in_doc:
            continue
        for m in LIT.finditer(stripper(line)):
            hits.append((i, m.group(1), line.strip()[:70]))
    return hits


print("=== A. 容差常量分级 ===")
from kernel import tolerance as T  # noqa: E402
import kernel.geom_util as GU  # noqa: E402

check("EPSILON = 1e-12（判定等于 0）", T.EPSILON == 1e-12, repr(T.EPSILON))
check("TIGHT = 1e-15（更严格的零判定）", T.TIGHT == 1e-15, repr(T.TIGHT))
check("COORD = 1e-9（坐标/长度尺度）", T.COORD == 1e-9, repr(T.COORD))
check("ZERO_SQ = 1e-18 且 ≈ COORD²", T.ZERO_SQ == 1e-18 and abs(T.ZERO_SQ - T.COORD ** 2) <= 1e-24,
      "%r vs %r" % (T.ZERO_SQ, T.COORD ** 2))
check("LOOSE = 1e-7 / COARSE = 1e-6 / NEGLIGIBLE = 1e-300",
      T.LOOSE == 1e-7 and T.COARSE == 1e-6 and T.NEGLIGIBLE == 1e-300, "")
check("ROOT_TOL / OPT_XATOL / OPT_FATOL 齐全",
      T.ROOT_TOL == 1e-10 and T.OPT_XATOL == 1e-10 and T.OPT_FATOL == 1e-14, "")
order = [T.NEGLIGIBLE, T.ZERO_SQ, T.TIGHT, T.EPSILON, T.ROOT_TOL, T.COORD, T.LOOSE, T.COARSE]
check("分级顺序正确（越靠前越严格）", order == sorted(order), str(order))
check("ALL 表覆盖全部常量", set(T.ALL) == {"EPSILON", "TIGHT", "COORD", "ZERO_SQ", "LOOSE", "COARSE",
                                       "NEGLIGIBLE", "ROOT_TOL", "OPT_XATOL", "OPT_FATOL"},
      str(sorted(T.ALL)))
check("geom_util 已并入统一容差表（不再有本地 EPS 别名）",
      not hasattr(GU, "EPS") and GU.COORD == T.COORD, "COORD=%r" % getattr(GU, "COORD", None))

print("\n=== B. 内核/服务端代码零魔数 ===")
offenders = []
for p in sorted(list((ROOT / "kernel").glob("*.py")) + list((ROOT / "server").glob("*.py"))):
    if p.name == "tolerance.py":
        continue
    hits = scan_code_literals(p, strip_py, True)
    if hits:
        offenders.append((p.name, hits))
check("kernel/ 与 server/ 代码中无浮点科学计数字面量", not offenders,
      "; ".join("%s:%d %s" % (n, h[0][0], h[0][1]) for n, h in offenders[:5]))

print("\n=== C. 扫描器自检 ===")
planted = "    if abs(det) < 1e-12:  # 注释里的 1e-9 不算"
found = [m.group(1) for m in LIT.finditer(strip_py(planted))]
check("植入的代码字面量会被抓到", found == ["1e-12"], str(found))
comment_only = "    x = 1.0  # 容差 1e-12"
check("注释里的字面量不误报", not list(LIT.finditer(strip_py(comment_only))), "")
js_line = "  if (denom < 1e-12) { /* ok */ }  // 1e-9 in comment"
check("JS 行同样只取代码部分", [m.group(1) for m in LIT.finditer(strip_js(js_line))] == ["1e-12"], "")

print("\n=== D. 迁移覆盖面 ===")
cmd_src = (ROOT / "kernel" / "commands.py").read_text(encoding="utf-8")
geo_src = (ROOT / "kernel" / "geometry3d.py").read_text(encoding="utf-8")
sol_src = (ROOT / "kernel" / "solids.py").read_text(encoding="utf-8")
geo2d_src = (ROOT / "kernel" / "geo2d.py").read_text(encoding="utf-8")
total_uses = sum(len(re.findall(r"(?<![\w.])" + n + r"(?![\w])", cmd_src + geo_src + sol_src + geo2d_src))
                 for n in ("EPSILON", "COORD", "LOOSE", "COARSE", "ZERO_SQ", "TIGHT", "NEGLIGIBLE"))
check("三大内核模块已改用具名常量（引用 ≥ 150 处）", total_uses >= 150, "n=%d" % total_uses)
check("geometry3d 不再出现裸 1e-12（用户指出的第 75 行）",
      not scan_code_literals(ROOT / "kernel" / "geometry3d.py", strip_py, True), "")

print("\n=== D2. 策略守卫 ===")
tol_names = ("EPSILON", "TIGHT", "COORD", "ZERO_SQ", "LOOSE", "COARSE",
             "NEGLIGIBLE", "ROOT_TOL", "OPT_XATOL", "OPT_FATOL")
alias_hits = []
mismatch = []
for pth in sorted(list((ROOT / "kernel").glob("*.py")) + list((ROOT / "server").glob("*.py"))):
    if pth.name == "tolerance.py":
        continue
    txt = pth.read_text(encoding="utf-8")
    code_only = "\n".join(strip_py(l) for l in txt.splitlines())
    if re.search(r"(?<![\w.])EPS(?![\w])", code_only):
        alias_hits.append(pth.name)
    used = {n for n in tol_names if re.search(r"(?<![\w.])" + n + r"(?![\w])", code_only)}
    m = re.search(r"^from \.tolerance import ([^\n#]+)", txt, re.M)
    imported = {x.strip() for x in m.group(1).split(",") if x.strip()} if m else set()
    if used != imported:
        mismatch.append((pth.name, sorted(used - imported), sorted(imported - used)))
check("不再使用旧别名 EPS（统一用具名常量）", not alias_hits, str(alias_hits))
check("每个模块的容差导入集合 == 实际使用集合（防漏导入/多余导入）", not mismatch,
      str(mismatch[:3]))

print("\n=== E. 前端容差一致性 ===")
app = (ROOT / "server" / "static" / "app.js").read_text(encoding="utf-8")
fe = dict(re.findall(r"var (EPSILON|COORD|COARSE) = ([0-9.e-]+);", app))
check("app.js 定义同名容差常量", set(fe) == {"EPSILON", "COORD", "COARSE"}, str(fe))
check("前端取值与内核一致",
      fe.get("EPSILON") == "1e-12" and fe.get("COORD") == "1e-9" and fe.get("COARSE") == "1e-6",
      str(fe))
app_hits = []
for i, line in enumerate(app.splitlines(), 1):
    code = strip_js(line)
    if re.search(r"var (EPSILON|COORD|COARSE) =", code):
        continue                      # 常量定义行本身允许字面量
    for m in LIT.finditer(code):
        app_hits.append((i, m.group(1)))
check("app.js 其余位置无容差字面量", not app_hits, str(app_hits[:5]))

print("\n" + "=" * 56)
print("容差检测：%d 项断言，%d 失败" % (PASS + FAIL, FAIL))
if FAILED:
    for n in FAILED:
        print("  FAILED: " + n)
    sys.exit(1)
print("结果: ALL PASS")
sys.exit(0)
