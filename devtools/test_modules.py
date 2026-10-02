#!/usr/bin/env python3
"""模块边界检测（P2 内核/前端拆分）：3D 几何层独立性与前端文案表外置。

用法：python3 -B devtools/test_modules.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
FAILED = []


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  OK   " + name + (("  [" + detail + "]") if detail else ""))
    else:
        FAIL += 1
        FAILED.append(name)
        print("  FAIL " + name + "  " + detail)


print("=== A. 内核：3D 几何层独立 ===")
geo_src = (ROOT / "kernel" / "geometry3d.py").read_text(encoding="utf-8")
cmd_src = (ROOT / "kernel" / "commands.py").read_text(encoding="utf-8")

check("geometry3d 不 import 命令层",
      not re.search(r"^from \.commands|^import commands", geo_src, re.M)
      and "from .commands" not in geo_src, "")
check("geometry3d 只依赖 elements/math/numpy",
      set(re.findall(r"^from \.(\w+) import", geo_src, re.M)) <= {"elements"}, 
      str(sorted(set(re.findall(r"^from \.(\w+) import", geo_src, re.M)))))
check("commands.py 通过 re-export 保持兼容",
      "from .geometry3d import" in cmd_src, "")

import kernel.commands as C  # noqa: E402
import kernel.geometry3d as G  # noqa: E402

moved = list(G.__all__)
check("搬迁函数数量 ≥ 30", len(moved) >= 30, "n=%d" % len(moved))
same = all(getattr(C, n, None) is getattr(G, n, None) for n in moved)
check("commands 与 geometry3d 指向同一函数对象（re-export 一致）", same, "")
check("3D 求交/体积入口仍从 commands 可用",
      all(hasattr(C, n) for n in ("_ix_solid_solid", "_ix_sphere_solid", "_mesh_volume", "_clip_polyhedron")), "")

# 独立导入：新进程里只导入 geometry3d，不应把 commands 拉进来
code = ("import sys; sys.path.insert(0, %r); import kernel.geometry3d as g; "
        "print('COMMANDS_LOADED' if 'kernel.commands' in sys.modules else 'ISOLATED', len(g.__all__))" % str(ROOT))
out = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True)
check("新进程可独立导入 geometry3d（不拉起命令层）",
      out.returncode == 0 and out.stdout.startswith("ISOLATED"), out.stdout.strip()[:60] + out.stderr.strip()[:40])
check("commands.py 行数已下降（< 7200）", len(cmd_src.splitlines()) < 7200, str(len(cmd_src.splitlines())))
check("geometry3d 与 solids 无循环依赖",
      "from .solids" not in geo_src
      and "from .geometry3d" in (ROOT / "kernel" / "solids.py").read_text(encoding="utf-8"), "")
check("geometry3d.py 规模合理（600–1200 行）",
      600 <= len(geo_src.splitlines()) <= 1200, str(len(geo_src.splitlines())))

print("\n=== A2. solids 模块 ===")
solids_src = (ROOT / "kernel" / "solids.py").read_text(encoding="utf-8")
check("solids 不 import 命令层", "from .commands" not in solids_src, "")
check("solids 通过 geometry3d 复用共用件",
      "from .geometry3d import" in solids_src, "")
import kernel.solids as S  # noqa: E402

sol_moved = list(S.__all__)
check("solids 搬迁函数数量 ≥ 25", len(sol_moved) >= 25, "n=%d" % len(sol_moved))
check("solids 与 commands re-export 一致",
      all(getattr(C, n, None) is getattr(S, n, None) for n in sol_moved), "")
check("立体命令入口仍可用",
      all(hasattr(C, n) for n in ("_cube_state", "_cone_state", "_cylinder_state", "_regular_polyhedron")), "")
check("commands.py 行数已降至 < 6700", len(cmd_src.splitlines()) < 6700, str(len(cmd_src.splitlines())))


def undefined_refs(path):
    """静态检查：模块内调用的 `_name(...)` 与引用的 `_CONST` 必须在本模块定义/导入。

    覆盖两类跨模块拆分漏项：函数搬走了但依赖的函数没搬（第一版漏了 `_poly_state`）、
    函数搬走了但模块级常量没搬（第一版漏了 `_PHI`）。
    """
    txt = (ROOT / path).read_text(encoding="utf-8")
    defined = set(re.findall(r"def (\w+)\(", txt))
    assigned = set(re.findall(r"^(_?[A-Za-z]\w*)\s*=", txt, re.M))
    imported_names = set()
    for line in txt.splitlines():                       # 逐行解析，避免跨行贪婪匹配
        m_from = re.match(r"\s*from\s+[\w.]+\s+import\s+(.+?)\s*$", line)
        if m_from:
            for part in m_from.group(1).strip().strip("()").split(","):
                nm = part.strip().split(" as ")[-1].strip()
                if nm:
                    imported_names.add(nm)
            continue
        m_imp = re.match(r"\s*import\s+([\w.]+)\s*(?:as\s+(\w+))?\s*$", line)
        if m_imp:
            imported_names.add(m_imp.group(2) or m_imp.group(1).split(".")[0])
    called = set(re.findall(r"(?<![\w.])(_\w+)\(", txt))
    consts = set(re.findall(r"(?<![\w.'\"])(_[A-Z][A-Z0-9_]*)(?![\w(])", txt))
    miss = sorted((called | consts) - defined - assigned - imported_names)
    return miss


for mod in ("kernel/geometry3d.py", "kernel/solids.py"):
    miss = undefined_refs(mod)
    check(mod + " 无未定义引用（函数与常量跨模块防漏）", not miss, "缺: " + str(miss[:8]))

print("\n=== B. 前端：文案表外置 ===")
app = (ROOT / "server" / "static" / "app.js").read_text(encoding="utf-8")
i18n_path = ROOT / "server" / "static" / "i18n.js"
index = (ROOT / "server" / "static" / "index.html").read_text(encoding="utf-8")
check("i18n.js 存在", i18n_path.exists(), "")
check("app.js 引用 window.GGB_I18N", "window.GGB_I18N" in app, "")
i18n = i18n_path.read_text(encoding="utf-8") if i18n_path.exists() else ""
check("文案数据已外置（app.js 不再含词条）",
      "cmd_ph" not in app and "cmd_ph" in i18n, "")
check("index.html 在 app.js 之前加载 i18n.js",
      index.index("/static/i18n.js") < index.index("/static/app.js"), "")
check("app.js 行数下降（< 5600）", len(app.splitlines()) < 5600, str(len(app.splitlines())))

# 词条一致性：zh / en 键集合应一致
node_js = (
    "const fs=require('fs');global.window={};"
    "eval(fs.readFileSync(%r,'utf8'));"
    "const i=window.GGB_I18N||{};const z=Object.keys(i.zh||{});const e=Object.keys(i.en||{});"
    "const miss=e.filter(k=>!z.includes(k));const extra=z.filter(k=>!e.includes(k));"
    "console.log(JSON.stringify({zh:z.length,en:e.length,missingInZh:miss,missingInEn:extra}));"
) % str(i18n_path)
try:
    out2 = subprocess.run(["node", "-e", node_js], capture_output=True, text=True, timeout=30)
    data = json.loads(out2.stdout.strip().splitlines()[-1]) if out2.returncode == 0 else None
except Exception as e:
    data = None
if data is None:
    check("可解析 i18n.js 词条", False, "node 执行失败")
else:
    check("可解析 i18n.js 词条（zh/en 各 ≥100 条）",
          data["zh"] >= 100 and data["en"] >= 100, "zh=%d en=%d" % (data["zh"], data["en"]))
    check("中英文词条键集合一致（无漏翻）",
          not data["missingInZh"] and not data["missingInEn"],
          "缺 zh=%s 缺 en=%s" % (data["missingInZh"][:5], data["missingInEn"][:5]))

print("\n" + "=" * 56)
print("模块边界检测：%d 项断言，%d 失败" % (PASS + FAIL, FAIL))
if FAILED:
    for n in FAILED:
        print("  FAILED: " + n)
    sys.exit(1)
print("结果: ALL PASS")
sys.exit(0)
