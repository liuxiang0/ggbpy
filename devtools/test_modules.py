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
check("geometry3d 只依赖 elements/tolerance/mesh_store/math/numpy",
      set(re.findall(r"^from \.(\w+) import", geo_src, re.M)) <= {"elements", "tolerance", "mesh_store"},
      str(sorted(set(re.findall(r"^from \.(\w+) import", geo_src, re.M)))))
check("geometry3d 不再内联边表去重循环（统一走 mesh_store.edges_of）",
      "min(a, b), max(a, b)" not in geo_src and "mesh_store.edges_of(" in geo_src, "")
tol_src = (ROOT / "kernel" / "tolerance.py").read_text(encoding="utf-8")
check("tolerance 是叶子模块（不做相对导入）",
      not re.search(r"^from \.", tol_src, re.M), "")
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
check("commands.py 行数已降至 < 6300", len(cmd_src.splitlines()) < 6300, str(len(cmd_src.splitlines())))


def undefined_refs(path):
    """静态检查：模块内调用的 `_name(...)` 与引用的 `_CONST` 必须在本模块定义/导入。

    覆盖两类跨模块拆分漏项：函数搬走了但依赖的函数没搬（第一版漏了 `_poly_state`）、
    函数搬走了但模块级常量没搬（第一版漏了 `_PHI`）。
    """
    txt = (ROOT / path).read_text(encoding="utf-8")
    # 任意缩进的 def/class 都算定义（如函数内 `class _L:`）
    defined = set(re.findall(r"^\s*(?:def|class)\s+(\w+)", txt, re.M))
    # 含类型注解的赋值也算定义（如 `_nested_evaluator: Optional[Callable] = None`）
    assigned = set(re.findall(r"^(_?[A-Za-z]\w*)\s*(?::[^=\n]+)?=", txt, re.M))
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


for mod in ("kernel/geometry3d.py", "kernel/solids.py", "kernel/geo2d.py", "kernel/stats.py",
            "kernel/cmd_util.py", "kernel/charts.py", "kernel/commands3d.py",
            "kernel/primitives.py", "kernel/transforms.py", "kernel/editing.py",
            "kernel/numeric.py", "kernel/io_cmds.py", "kernel/conics.py", "kernel/linalg.py",
            "kernel/measures.py", "kernel/proofs.py", "kernel/centers.py", "kernel/fits.py",
            "kernel/iteration.py", "kernel/macros.py", "kernel/misc.py", "kernel/registry.py",
            "kernel/nested.py"):
    miss = undefined_refs(mod)
    check(mod + " 无未定义引用（函数与常量跨模块防漏）", not miss, "缺: " + str(miss[:8]))

print("\n=== A3. geo2d 模块（二维几何基元与变换） ===")
geo2d_src = (ROOT / "kernel" / "geo2d.py").read_text(encoding="utf-8")
check("geo2d 不 import 命令层", "from .commands" not in geo2d_src, "")
check("geo2d 只依赖 elements/tolerance",
      set(re.findall(r"^from \.(\w+) import", geo2d_src, re.M)) <= {"elements", "tolerance"},
      str(sorted(set(re.findall(r"^from \.(\w+) import", geo2d_src, re.M)))))
import kernel.geo2d as G2  # noqa: E402

g2_moved = list(G2.__all__)
check("geo2d 搬迁函数数量 ≥ 15", len(g2_moved) >= 15, "n=%d" % len(g2_moved))
check("geo2d 与 commands re-export 一致",
      all(getattr(C, n, None) is getattr(G2, n, None) for n in g2_moved), "")
check("变换/基元入口仍可用",
      all(hasattr(C, n) for n in ("_transform_fn", "_line_state", "_line_through", "_conic_t")), "")
check("geo2d.py 规模合理（300–700 行）", 300 <= len(geo2d_src.splitlines()) <= 700,
      str(len(geo2d_src.splitlines())))

print("\n=== A4. stats 模块（统计/拟合） ===")
stats_src = (ROOT / "kernel" / "stats.py").read_text(encoding="utf-8")
check("stats 不 import 命令层", "from .commands" not in stats_src, "")
check("stats 依赖白名单（tolerance/geo2d/elements）",
      set(re.findall(r"^from \.(\w+) import", stats_src, re.M)) <= {"tolerance", "geo2d", "elements"},
      str(sorted(set(re.findall(r"^from \.(\w+) import", stats_src, re.M)))))
import kernel.stats as ST  # noqa: E402

st_moved = list(ST.__all__)
check("stats 搬迁函数数量 ≥ 8（统计/拟合）", len(st_moved) >= 8, "n=%d" % len(st_moved))
check("stats 与 commands re-export 一致",
      all(getattr(C, n, None) is getattr(ST, n, None) for n in st_moved), "")
check("统计入口仍可用（中位数/方差/拟合/球面拟合）",
      all(hasattr(C, n) for n in ("_median", "_variance", "_fitline_state", "_fitsphere_state")), "")
check("_REF_X/_REF_DOT 常量随 stats 迁移且 re-export 一致",
      getattr(C, "_REF_X", None) is ST._REF_X and getattr(C, "_REF_DOT", None) is ST._REF_DOT, "")
# 软预算：统计图状态 + 三维统计图网格构造加入后为 ~265 行；上限防止无序膨胀
check("stats.py 规模合理（80–340 行）", 80 <= len(stats_src.splitlines()) <= 340,
      str(len(stats_src.splitlines())))

print("\n=== B0. 前端：数据表外置（CAS/工具定义/工具分类） ===")
app_src = (ROOT / "server" / "static" / "app.js").read_text(encoding="utf-8")
index_src = (ROOT / "server" / "static" / "index.html").read_text(encoding="utf-8")
data_path = ROOT / "server" / "static" / "data.js"
data_src = data_path.read_text(encoding="utf-8") if data_path.exists() else ""
check("data.js 存在", data_path.exists(), "")
check("app.js 引用 window.GGB_DATA", "window.GGB_DATA" in app_src, "")
check("数据表已外置（app.js 不再含 CAS 命令表）",
      "'PartialFractions'" not in app_src and "'PartialFractions'" in data_src, "")
check("index.html 在 app.js 之前加载 data.js",
      index_src.index("/static/data.js") < index_src.index("/static/app.js"), "")
check("index.html 在 i18n.js 之后加载 data.js",
      index_src.index("/static/i18n.js") < index_src.index("/static/data.js"), "")
node_data = (
    "const fs=require('fs');global.window={};"
    "eval(fs.readFileSync(%r,'utf8'));"
    "const d=window.GGB_DATA||{};const t=d.TOOLS||{};const cats=d.TOOL_CATS||[];"
    "const listed=new Set();cats.forEach(c=>(c.tools||[]).forEach(k=>listed.add(k)));"
    "const missing=[...listed].filter(k=>!t[k]);const extra=Object.keys(t).filter(k=>!listed.has(k));"
    "const seen={},dup=[];cats.forEach(c=>(c.tools||[]).forEach(k=>{"
    "if(seen[k])dup.push(k+':'+seen[k]+'+'+c.id);else seen[k]=c.id;}));"
    "const calc=(cats.find(c=>c.id==='calculates')||{}).tools||[];"
    "const ch=(cats.find(c=>c.id==='charts')||{}).tools||[];"
    "const catIds=cats.map(c=>c.id);const catDefs=cats.map(c=>({id:c.id,tools:c.tools||[],def:c.def||null}));"
    "console.log(JSON.stringify({cas:(d.CAS_COMMANDS||[]).length,tools:Object.keys(t).length,"
    "cats:cats.length,missing,extra,dup,calc,ch,catIds,catDefs}));"
) % str(data_path)
try:
    out3 = subprocess.run(["node", "-e", node_data], capture_output=True, text=True, timeout=30)
    d3 = json.loads(out3.stdout.strip().splitlines()[-1]) if out3.returncode == 0 else None
except Exception:
    d3 = None
if d3 is None:
    check("可解析 data.js 数据表", False, "node 执行失败")
else:
    check("data.js 含 CAS 命令表（≥10 条）与工具定义（≥30 个）",
          d3["cas"] >= 10 and d3["tools"] >= 30, "cas=%d tools=%d" % (d3["cas"], d3["tools"]))
    check("TOOL_CATS 里列出的工具都在 TOOLS 中有定义（无悬空）", not d3["missing"], str(d3["missing"][:6]))
    # TOOLS 里未列入分类面板的工具，必须能在顶栏找到按钮（如 image 只在 #btn-image）
    orphan = [k for k in d3["extra"] if ('id="btn-%s"' % k) not in index_src]
    check("未列入分类的工具都有顶栏按钮（无孤儿工具）", not orphan,
          "无分类且无按钮=%s；仅顶栏=%s" % (orphan, d3["extra"][:6]))
    # 用户反馈：菜单「计算→直方图」与「统计图→直方图」是同一个按钮（同一 barchart 工具）
    check("工具分类无重复登记（同一工具只属一个分类）", not d3.get("dup"), str(d3.get("dup", [])[:4]))
    check("「计算」分类不含直方图（barchart 仅归统计图）", "barchart" not in d3.get("calc", []),
        str(d3.get("calc")))
    check("「统计图」分类仍含直方图（功能未丢）", "barchart" in d3.get("ch", []), str(d3.get("ch")[:4]))

    # 全分类结构校验：id 唯一 / 非空 / def ∈ tools（不只是「计算/统计图」两处）
    _ids = d3.get("catIds", [])
    check("分类 id 唯一", len(_ids) == len(set(_ids)), str([i for i in _ids if _ids.count(i) > 1]))
    _defs = d3.get("catDefs", [])
    check("每个分类都有工具（无空分类）", all(c["tools"] for c in _defs), str([c["id"] for c in _defs if not c["tools"]]))
    check("每个分类的默认工具 def 都在其 tools 内", all((not c["def"]) or c["def"] in c["tools"] for c in _defs), str([c["id"] for c in _defs if c["def"] and c["def"] not in c["tools"]]))
    check("分类总数与工具覆盖合理（≥ 10 个分类且无重复登记）", len(_defs) >= 10 and not d3.get("dup"), "cats=%d" % len(_defs))
# 软预算：data.js 外置后 5542 行，统计图绘制（六类 + 拖动命中盒）加入后 ~5697 行
check("app.js 行数受控（< 5800）", len(app_src.splitlines()) < 5800, str(len(app_src.splitlines())))

def ast_undefined_calls(path):
    """AST 静态检查：模块内所有 `name(...)` 调用必须已定义（顶层/嵌套/局部赋值）、导入或内建。

    比正则版守卫更严：可发现「搬迁后漏导入非下划线助手/标准库」这类错误
    （曾漏 `eval_number`、`label_of`、`re` 各一次）。
    """
    import ast as _ast
    import builtins as _bi
    tree = _ast.parse((ROOT / path).read_text(encoding="utf-8"))
    top = set()
    for n in tree.body:
        if isinstance(n, (_ast.FunctionDef, _ast.ClassDef)):
            top.add(n.name)
        if isinstance(n, _ast.Assign):
            for t in n.targets:
                for x in _ast.walk(t):
                    if isinstance(x, _ast.Name):
                        top.add(x.id)
        if isinstance(n, _ast.AnnAssign) and isinstance(n.target, _ast.Name):
            top.add(n.target.id)
    # 导入可能出现在函数体内（本仓库用惰性导入打破循环依赖）→ 全树收集
    for n in _ast.walk(tree):
        if isinstance(n, (_ast.Import, _ast.ImportFrom)):
            for a in n.names:
                top.add(a.asname or a.name.split(".")[0])
    local = set()
    for node in _ast.walk(tree):
        if isinstance(node, (_ast.FunctionDef, _ast.ClassDef)):
            local.add(node.name)
        elif isinstance(node, _ast.arg):
            local.add(node.arg)
        elif isinstance(node, _ast.Name) and isinstance(node.ctx, (_ast.Store, _ast.Del)):
            local.add(node.id)
    called = {n.func.id for n in _ast.walk(tree)
              if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)}
    # 属性访问的基名（schemas.x / mesh_store.y）也必须在模块内可解析
    bases = {n.value.id for n in _ast.walk(tree)
             if isinstance(n, _ast.Attribute) and isinstance(n.value, _ast.Name)}
    return sorted((called | bases) - top - local - set(dir(_bi)))


print("\n=== A8. calculus 模块（微积分/符号计算命令） ===")
calc_src = (ROOT / "kernel" / "calculus.py").read_text(encoding="utf-8")
check("calculus 不 import 命令层（无循环导入）", "from .commands" not in calc_src, "")
check("calculus 不引用命令注册表",
      not re.search(r"\b(COMMANDS|ALIASES|RESULT_KINDS|DISPLAY_NAMES)\b", calc_src), "")
import kernel.calculus as CALC  # noqa: E402

check("calculus 搬迁函数 ≥ 20（微积分/数论/拟合）", len(CALC.__all__) >= 20, "n=%d" % len(CALC.__all__))
check("calculus 与 commands re-export 同一对象",
      all(getattr(C, n, None) is getattr(CALC, n, None) for n in CALC.__all__), "")
check("calulus 依赖白名单（elements/tolerance/parser/cmd_util）",
      set(re.findall(r"^from \.(\w+) import", calc_src, re.M)) <= {"elements", "tolerance", "parser", "cmd_util"},
      str(sorted(set(re.findall(r"^from \.(\w+) import", calc_src, re.M)))))
check("calculus.py 规模合理（300–900 行）", 300 <= len(calc_src.splitlines()) <= 900,
      str(len(calc_src.splitlines())))
check("commands.py 因 calculus 拆分继续下降（< 5700）", len(cmd_src.splitlines()) < 5700,
      str(len(cmd_src.splitlines())))

print("\n=== A9. charts / commands3d 模块（命令组继续抽出） ===")
import kernel.charts as CH  # noqa: E402
import kernel.commands3d as C3  # noqa: E402

for name, mod, min_n, lo, hi in (("charts", CH, 10, 150, 420), ("commands3d", C3, 35, 500, 1100)):
    src_m = (ROOT / "kernel" / (name + ".py")).read_text(encoding="utf-8")
    check("%s 不 import 命令层" % name, "from .commands" not in src_m, "")
    check("%s 不引用命令注册表" % name,
          not re.search(r"\b(COMMANDS|ALIASES|RESULT_KINDS|DISPLAY_NAMES)\b", src_m), "")
    check("%s 搬迁函数 ≥ %d" % (name, min_n), len(mod.__all__) >= min_n, "n=%d" % len(mod.__all__))
    check("%s 与 commands re-export 同一对象" % name,
          all(getattr(C, n, None) is getattr(mod, n, None) for n in mod.__all__), "")
    check("%s.py 规模合理（%d–%d 行）" % (name, lo, hi), lo <= len(src_m.splitlines()) <= hi,
          str(len(src_m.splitlines())))
check("commands.py 因命令组抽出继续下降（< 4700）", len(cmd_src.splitlines()) < 4700,
      str(len(cmd_src.splitlines())))
check("统计图/三维命令入口仍可用",
      all(hasattr(C, n) for n in ("_cmd_barchart", "_cmd_piechart", "_cmd_linechart", "_cmd_cube",
                                  "_cmd_surface", "_cmd_volume")), "")

print("\n=== A10. 命令组模块（图元/变换/编辑/数值/导入导出） ===")
import importlib as _importlib  # noqa: E402

CMD_GROUP_MODULES = [
    ("primitives", 70, 900, 1600), ("transforms", 15, 300, 600), ("editing", 8, 60, 260),
    ("numeric", 15, 80, 300), ("io_cmds", 5, 80, 300),
    ("conics", 10, 150, 420), ("linalg", 12, 80, 260), ("measures", 12, 90, 300),
    ("proofs", 3, 15, 140), ("centers", 5, 30, 160), ("fits", 7, 90, 300),
    ("iteration", 3, 60, 240), ("macros", 2, 12, 120), ("misc", 2, 25, 140),
]
for _name, _min_n, _lo, _hi in CMD_GROUP_MODULES:
    _src = (ROOT / "kernel" / (_name + ".py")).read_text(encoding="utf-8")
    _mod = _importlib.import_module("kernel." + _name)
    check("%s 不 import 命令层" % _name, "from .commands" not in _src, "")
    check("%s 不引用命令注册表" % _name,
          not re.search(r"\b(COMMANDS|ALIASES|RESULT_KINDS|DISPLAY_NAMES)\b", _src), "")
    check("%s 搬迁函数 ≥ %d" % (_name, _min_n), len(_mod.__all__) >= _min_n, "n=%d" % len(_mod.__all__))
    check("%s 与 commands re-export 同一对象" % _name,
          all(getattr(C, n, None) is getattr(_mod, n, None) for n in _mod.__all__), "")
    check("%s.py 规模合理（%d–%d 行）" % (_name, _lo, _hi), _lo <= len(_src.splitlines()) <= _hi,
          str(len(_src.splitlines())))
check("commands.py 因命令组继续抽出（< 1950 行）", len(cmd_src.splitlines()) < 1950,
      str(len(cmd_src.splitlines())))
check("图元/变换/编辑/数值/导入导出入口仍可用",
      all(hasattr(C, n) for n in ("_cmd_midpoint", "_cmd_segment", "_cmd_circle", "_cmd_polygon",
                                  "_cmd_rotate", "_cmd_reflect", "_cmd_setvalue", "_cmd_setcolor",
                                  "_cmd_sum", "_cmd_mean", "_cmd_image", "_cmd_text")), "")

print("\n=== A11. registry 模块（四张注册表集中） ===")
reg_src = (ROOT / "kernel" / "registry.py").read_text(encoding="utf-8")
import kernel.registry as REG  # noqa: E402

check("registry 不 import 命令层（单向依赖，无环）",
      not re.search(r"^\s*(?:from \.commands import|import kernel\.commands)", reg_src, re.M), "")
check("registry 四张表由 SPECS 单一来源派生（新增命令只改一处）",
      "SPECS:" in reg_src and "_derive(SPECS)" in reg_src
      and "\nCOMMANDS = {" not in reg_src and "\nALIASES = {" not in reg_src
      and "\nRESULT_KINDS = {" not in reg_src, "")
check("registry 不再有孤儿显示名",
      not [k for k in REG.DISPLAY_NAMES if k not in REG.COMMANDS], "")
check("registry 四张表齐全且规模合理",
      len(REG.COMMANDS) >= 160 and len(REG.ALIASES) >= 180
      and len(REG.DISPLAY_NAMES) >= 60 and len(REG.RESULT_KINDS) >= 160,
      "COMMANDS=%d ALIASES=%d DISPLAY_NAMES=%d RESULT_KINDS=%d" % (
          len(REG.COMMANDS), len(REG.ALIASES), len(REG.DISPLAY_NAMES), len(REG.RESULT_KINDS)))
check("commands 与 registry 指向同一批表（re-export）",
      C.COMMANDS is REG.COMMANDS and C.ALIASES is REG.ALIASES
      and C.DISPLAY_NAMES is REG.DISPLAY_NAMES and C.RESULT_KINDS is REG.RESULT_KINDS, "")
check("registry 从命令组模块汇总实现（≥ 15 条 import）",
      len(re.findall(r"^from \.\w+ import", reg_src, re.M)) >= 15,
      str(len(re.findall(r"^from \.\w+ import", reg_src, re.M))))
check("registry.py 规模合理（200–600 行）", 200 <= len(reg_src.splitlines()) <= 600,
      str(len(reg_src.splitlines())))
check("commands.py 已退化为调度器规模（< 1650 行）", len(cmd_src.splitlines()) < 1650,
      str(len(cmd_src.splitlines())))
_sub = subprocess.run([sys.executable, "-B", "-c",
                       "import sys; sys.path.insert(0, %r); import kernel.registry; "
                       "print('COMMANDS_LOADED' if 'kernel.commands' in sys.modules else 'ISOLATED')" % str(ROOT)],
                      capture_output=True, text=True)
check("新进程只导入 registry 不会拉起 commands（依赖方向正确）",
      _sub.stdout.strip() == "ISOLATED", _sub.stdout.strip()[:40] + _sub.stderr.strip()[:40])

print("\n=== A12. nested 模块（嵌套命令求值器）+ commands 调度器化 ===")
nest_src = (ROOT / "kernel" / "nested.py").read_text(encoding="utf-8")
import kernel.nested as NEST  # noqa: E402
import kernel.cmd_util as _CU  # noqa: E402
import kernel.registry as _REG  # noqa: E402

check("nested 不 import 命令层（依赖 registry 命令表）",
      not re.search(r"^\s*(?:from \.commands import|import kernel\.commands)", nest_src, re.M), "")
check("nested 依赖 registry + cmd_util + parser + elements",
      set(re.findall(r"^from \.(\w+) import", nest_src, re.M)) == {"cmd_util", "registry", "parser", "elements"},
      str(sorted(set(re.findall(r"^from \.(\w+) import", nest_src, re.M)))))
check("nested 导入即注入嵌套求值钩子", "set_nested_evaluator(_eval_nested)" in nest_src, "")
check("cmd_util 的钩子指向 nested._eval_nested", _CU._nested_evaluator is NEST._eval_nested, "")
check("命名助手随注册表（registry 提供 _result_kind/_label_kind）",
      _REG._result_kind is C._result_kind and _REG._label_kind is C._label_kind, "")
check("commands 与 nested re-export 同一对象",
      C._eval_nested is NEST._eval_nested and C._DetachedConstruction is NEST._DetachedConstruction, "")
check("commands.py 已接近纯调度器（< 1200 行）", len(cmd_src.splitlines()) < 1200,
      str(len(cmd_src.splitlines())))
check("commands.py 仅剩调度与共享助手（顶层 def ≤ 14 个）",
      len(re.findall(r"^def ", cmd_src, re.M)) <= 14, str(len(re.findall(r"^def ", cmd_src, re.M))))

print("\n=== A14. 重计算协作让出（REVIEW P0-2：不长时间独占 GIL） ===")
_c3 = (ROOT / "kernel" / "commands3d.py").read_text(encoding="utf-8")
check("marching 循环含协作让出（GGBPY_YIELD_MS，0 可关闭）",
      "GGBPY_YIELD_MS" in _c3 and "_time.sleep(0)" in _c3 and "_yield_ms > 0 and _time.time() >= _next_yield" in _c3, "")
check("让出周期可配且默认 5ms", 'os.environ.get("GGBPY_YIELD_MS", "5")' in _c3, "")
check("阻塞压测工具在库（devtools/bench_blocking.py）",
      (ROOT / "devtools" / "bench_blocking.py").exists(), "")
_memo_src = (ROOT / "kernel" / "memo.py").read_text(encoding="utf-8")
check("计算记忆命中时刷新 LRU（get 内 move_to_end，防重元素被误淘汰）",
      "def get(" in _memo_src and "_STORE.move_to_end(key)" in _memo_src, "")
check("撤销/重做压测工具在库（devtools/bench_undo.py）",
      (ROOT / "devtools" / "bench_undo.py").exists(), "")

print("\n=== A13. 几何工具去重（REVIEW 第 10 条：网格边表派生单一实现） ===")
_dup_edge = []
for _p in sorted((ROOT / "kernel").glob("*.py")):
    if _p.name == "mesh_store.py":
        continue
    for _i, _l in enumerate(_p.read_text(encoding="utf-8").splitlines(), 1):
        if "min(a, b), max(a, b)" in _l or "min(i, j), max(i, j)" in _l:
            _dup_edge.append("%s:%d" % (_p.name, _i))
check("kernel 内边表派生只有 mesh_store.edges_of 一处实现", not _dup_edge, str(_dup_edge[:4]))
check("convexhull 与立体求交都复用 edges_of",
      "mesh_store.edges_of(faces)" in (ROOT / "kernel" / "commands3d.py").read_text(encoding="utf-8")
      and "mesh_store.edges_of(faces)" in (ROOT / "kernel" / "geometry3d.py").read_text(encoding="utf-8"), "")

print("\n=== A7. AST 级守卫：抽出模块不得漏导入 ===")
for mod in ("kernel/geometry3d.py", "kernel/solids.py", "kernel/geo2d.py", "kernel/stats.py",
            "kernel/cmd_util.py", "kernel/calculus.py", "kernel/schemas.py",
            "kernel/charts.py", "kernel/commands3d.py", "kernel/primitives.py",
            "kernel/transforms.py", "kernel/editing.py", "kernel/numeric.py", "kernel/io_cmds.py",
            "kernel/conics.py", "kernel/linalg.py", "kernel/measures.py",
            "kernel/proofs.py", "kernel/centers.py", "kernel/fits.py", "kernel/iteration.py",
            "kernel/macros.py", "kernel/misc.py", "kernel/registry.py", "kernel/nested.py"):
    miss = ast_undefined_calls(mod)
    check(mod + " 所有调用均已定义/导入（AST 检查）", not miss, str(miss[:6]))

print("\n=== A6. cmd_util 共享命令层（参数解析/元素构造） ===")
cu_src = (ROOT / "kernel" / "cmd_util.py").read_text(encoding="utf-8") if (ROOT / "kernel" / "cmd_util.py").exists() else ""
check("cmd_util.py 存在", bool(cu_src), "")
check("cmd_util 不 import 命令层（无循环导入）", "from .commands" not in cu_src, "")
check("cmd_util 不引用命令注册表（COMMANDS/ALIASES/RESULT_KINDS）",
      not re.search(r"\b(COMMANDS|ALIASES|RESULT_KINDS|DISPLAY_NAMES)\b", cu_src), "")
import kernel.cmd_util as CU  # noqa: E402

check("cmd_util 搬迁助手 ≥ 12 个", len(CU.__all__) >= 14, "n=%d" % len(CU.__all__))
check("commands 与 cmd_util re-export 同一对象",
      all(getattr(C, n, None) is getattr(CU, n, None) for n in CU.__all__), "")
check("嵌套常量随迁且 re-export 一致",
      C._NESTED_CALL_RE is CU._NESTED_CALL_RE and C._NESTED_MAX_DEPTH == CU._NESTED_MAX_DEPTH, "")
check("commands 经 nested 模块完成嵌套求值钩子注入",
      "from .nested import" in cmd_src and "set_nested_evaluator(_eval_nested)" not in cmd_src, "")
check("cmd_util.py 规模合理（120–340 行）", 120 <= len(cu_src.splitlines()) <= 340,
      str(len(cu_src.splitlines())))
check("commands.py 因拆分继续下降（< 6200）", len(cmd_src.splitlines()) < 6200, str(len(cmd_src.splitlines())))

print("\n=== A5. schemas 模块（元素 data 载荷集中定义） ===")
schemas_src = (ROOT / "kernel" / "schemas.py").read_text(encoding="utf-8")
check("schemas 是叶子模块（不做相对导入）", not re.search(r"^from \.", schemas_src, re.M), "")
import kernel.schemas as SCH  # noqa: E402

built = {
    "line3d": SCH.line3d(0, 0, 0, 1, 1, 1),
    "segment3d": SCH.segment3d(0, 0, 0, 1, 0, 0),
    "plane": SCH.plane(0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0),
    "sphere": SCH.sphere(0, 0, 0, 2),
    "circle3d": SCH.circle3d(0, 0, 0, 1, [0, 0, 1], [1, 0, 0], [0, 1, 0]),
    "section": SCH.section([[0, 0, 0]], [0, 0, 1]),
    "curve3d": SCH.curve3d([[0, 0, 0, 1, 1, 1]]),
    "polyhedron": SCH.polyhedron(mesh={"verts": [], "faces": [], "edges": []}, solid="mesh"),
    "surface": SCH.surface([], [], [], 8, expr="x"),
    "cube": SCH.cube([], [], []),
    "chart3d": SCH.chart3d("chart_bar3d", [], [], []),
}
check("schema builder 均可调用且带 objtype", len(built) == 11 and all(b.get("objtype") for b in built.values()), "")
check("键顺序保持 objtype → solid → data（不改动载荷结构）",
      list(built["plane"].keys()) == ["objtype", "solid", "data"]
      and list(built["polyhedron"].keys()) == ["objtype", "solid", "data"]
      and list(built["line3d"].keys()) == ["objtype", "data"], str(list(built["plane"].keys())))
check("curve3d 自动带 count", built["curve3d"]["data"].get("count") == 1, "")
check("plane 支持额外键（FitPlane 的 fit=True）",
      SCH.plane(0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, fit=True)["data"].get("fit") is True, "")
check("surface/chart3d 走 polyhedron 且 solid 正确",
      built["surface"]["solid"] == "surface" and built["chart3d"]["solid"] == "chart_bar3d", "")

inline_hits = []
for pth in sorted((ROOT / "kernel").glob("*.py")):
    if pth.name == "schemas.py":
        continue
    for i, line in enumerate(pth.read_text(encoding="utf-8").splitlines(), 1):
        code = line.split("#", 1)[0]
        if re.search(r'"objtype"\s*:', code):
            inline_hits.append("%s:%d" % (pth.name, i))
check("kernel 内联 objtype 载荷已收敛到 schemas.py（新增内联会被拦下）", not inline_hits,
      str(inline_hits[:4]))

print("\n=== B16. 前端：LaTeX 序列化（static/latex.js）+ 界面弹窗（static/ui.js） ===")
for _name, _probe, _fns, _injs in (
    ("latex", "function toLatex() { return _latex", ("toLatex",),
     ("var CMD_W = env.get('CMD_W')", "GREEK_T = env.get('GREEK_T')")),
    ("ui", "function showHelpModal() { return _ui", ("showHelpModal",),
     ("var esc = env.esc;", "var renderCas = env.renderCas;")),
):
    _path = ROOT / "server" / "static" / (_name + ".js")
    _src = _path.read_text(encoding="utf-8") if _path.exists() else ""
    check("%s.js 存在" % _name, _path.exists(), "")
    check("%s 已装配且原实现体移走（仅剩薄包装）" % _name, _probe in app_src, "")
    check("index.html 在 app.js 之前加载 %s.js" % _name,
          index_src.index("/static/%s.js" % _name) < index_src.index("/static/app.js"), "")
    check("%s 覆盖预期函数" % _name, all(("function %s(" % f) in _src for f in _fns), "")
    check("%s 依赖既有模块助手/常量" % _name, all(t in _src for t in _injs), "")

print("\n=== B15. 前端：命中测试/逆投影（static/hit.js）+ 工具预览（static/preview.js） ===")
for _name, _probe, _fns, _injs in (
    ("hit", "function hitObject() { return _hit", ("hitObject", "hitObject3d", "unproj3", "nearestPathParam"),
     ("var sxp = env.sxp;", "var proj3 = env.proj3;", "var camBasis3 = env.camBasis3;")),
    ("preview", "function computeToolPreview() { return _preview", ("computeToolPreview",),
     ("var findEl = env.findEl;", "var hitObject = env.hitObject;")),
):
    _path = ROOT / "server" / "static" / (_name + ".js")
    _src = _path.read_text(encoding="utf-8") if _path.exists() else ""
    check("%s.js 存在" % _name, _path.exists(), "")
    check("%s 已装配且原实现体移走（仅剩薄包装）" % _name, _probe in app_src, "")
    check("index.html 在 app.js 之前加载 %s.js" % _name,
          index_src.index("/static/%s.js" % _name) < index_src.index("/static/app.js"), "")
    check("%s 覆盖预期函数" % _name, all(("function %s(" % f) in _src for f in _fns), "")
    check("%s 注入既有模块助手" % _name, all(t in _src for t in _injs), "")

print("\n=== B14. 前端：三维对象位移/拖动（static/drag3d.js） ===")
d3_path = ROOT / "server" / "static" / "drag3d.js"
d3_src = d3_path.read_text(encoding="utf-8") if d3_path.exists() else ""
check("drag3d.js 存在", d3_path.exists(), "")
check("app.js 通过 window.GGB_DRAG3 装配（原实现体已移走，仅剩薄包装）",
      "window.GGB_DRAG3" in app_src and "function flushObjShift3d() { return _drag3d" in app_src, "")
check("index.html 在 app.js 之前加载 drag3d.js",
      index_src.index("/static/drag3d.js") < index_src.index("/static/app.js"), "")
check("drag3d 覆盖位移落地/局部平移/状态判空",
      all(("function %s(" % f) in d3_src for f in ("flushObjShift3d", "localShift3dEl", "shiftLocal")), "")
# 判定「是否整体替换 objShift3d」：捕获赋值右侧再判断（避免正则回溯造成假阴性/假阳性）
_d3_writes = [w.strip() for w in re.findall(r"(?<![\w.$])objShift3d\s*=(?!=)\s*([^\n;]*)", d3_src)]
check("drag3d 原地修改共享状态对象（objShift3d.dx/dy/dz 归零），不整体替换",
      "objShift3d.dx = 0" in d3_src and all(w.startswith("env.get") for w in _d3_writes),
      str(_d3_writes[:2]))

print("\n=== B13. 前端：二维工具交互层（static/tools2d.js） ===")
t2_path = ROOT / "server" / "static" / "tools2d.js"
t2_src = t2_path.read_text(encoding="utf-8") if t2_path.exists() else ""
check("tools2d.js 存在", t2_path.exists(), "")
check("app.js 通过 window.GGB_T2D 装配（原实现体已移走，仅剩薄包装）",
      "window.GGB_T2D" in app_src and "Click a point or segment" not in app_src
      and "function toolCanvasClick() { return _tools2d" in app_src, "")
check("index.html 在 app.js 之前加载 tools2d.js",
      index_src.index("/static/tools2d.js") < index_src.index("/static/app.js"), "")
check("tools2d 覆盖 2D 工具族（点/线段/位似/图片/距离/斜率/角度/图表工具）",
      all(k in t2_src for k in ("toolCanvasClick", "toolPointAt", "snapHitLabel", "resetTool",
                                "chartDataPrompt")), "")
# 晚读规则：app.js 会整体替换 elements（elements = d.elements），异步回调里必须重新读取，
# 否则用的是入口捕获的旧数组 —— 曾导致图片工具第二步失效（新点找不到）
check("tools2d 异步回调内晚读 replaceable 状态（postInput 回调不用入口捕获的 elements）",
      "var elsNow = env.get('elements');" in t2_src
      and "for (var j = 0; j < elements.length; j++) {" not in t2_src, "")
check("tools2d 图片流程仍按两步基点创建（Image[…] + 完成后清 pendingImage）",
      "postInput('Image['" in t2_src and "env.set('pendingImage', null)" in t2_src, "")

print("\n=== B12. 前端：二维元素绘制层（static/render2d.js） ===")
r2_path = ROOT / "server" / "static" / "render2d.js"
r2_src = r2_path.read_text(encoding="utf-8") if r2_path.exists() else ""
check("render2d.js 存在", r2_path.exists(), "")
check("app.js 通过 window.GGB_R2D 装配（原绘制体已移走，仅剩薄包装）",
      "window.GGB_R2D" in app_src and "ctx.lineTo(poly[i].x, poly[i].y)" not in app_src
      and "function drawElement() { return _render2d" in app_src, "")
check("index.html 在 app.js 之前加载 render2d.js",
      index_src.index("/static/render2d.js") < index_src.index("/static/app.js"), "")
check("render2d 覆盖元素/圆锥曲线/不等式/叠加层/图片",
      all(("function %s(" % f) in r2_src for f in ("drawElement", "drawConic", "drawInequality",
                                                   "drawOverlay", "drawSelectionOverlay",
                                                   "drawImageEl", "getImage", "conicPathPts")), "")
check("render2d 复用既有模块助手（sxp/syp/drawGrid/图表绘制等为注入）",
      "var sxp = env.sxp;" in r2_src and "var drawGrid = env.drawGrid;" in r2_src
      and "var drawBarChart = env.drawBarChart;" in r2_src, "")

print("\n=== B11. 前端：三维工具交互模块（static/tools3d.js，3D 工具族） ===")
t3_path = ROOT / "server" / "static" / "tools3d.js"
t3_src = t3_path.read_text(encoding="utf-8") if t3_path.exists() else ""
check("tools3d.js 存在", t3_path.exists(), "")
check("app.js 通过 window.GGB_T3D 装配（原实现体已移走，仅剩薄包装）",
      "window.GGB_T3D" in app_src and "SOLID3_CMD" not in app_src
      and "function tool3dClick() { return _tools3d" in app_src, "")
check("index.html 在 app.js 之前加载 tools3d.js",
      index_src.index("/static/tools3d.js") < index_src.index("/static/app.js"), "")
check("tools3d 覆盖三维工具族（点/线段/平面/球/立方体/圆锥/圆柱/多面体）",
      all(k in t3_src for k in ("pt3d", "seg3d", "plane3d", "sphere3d", "cube3d", "cone3d",
                                "cylinder3d", "SOLID3_CMD")), "")
check("外部仍被引用的助手保留在 app.js 并注入（如 hitPoint3d）",
      "function hitPoint3d(sx, sy) {" in app_src and "hitPoint3d: hitPoint3d" in app_src
      and "var hitPoint3d = env.hitPoint3d;" in t3_src, "")
check("tools3d 的状态写入选点经 env.set（toolSel3d），且无直接变量赋值",
      "env.set('toolSel3d', " in t3_src and "toolSel3d = [" not in t3_src, "")

print("\n=== B10. 前端：三维叠加层模块（static/overlay3d.js）+ 状态绑定工具 ===")
ov_path = ROOT / "server" / "static" / "overlay3d.js"
ov_src = ov_path.read_text(encoding="utf-8") if ov_path.exists() else ""
check("overlay3d.js 存在", ov_path.exists(), "")
check("render3d 经 _overlay 三段调用（原实现体已移走）",
      all(k in app_src for k in ("_overlay.drawBasePlane();", "_overlay.drawSelection3d();",
                                  "_overlay.drawZHandle();"))
      and "rgba(99,102,241,.35)" not in app_src, "")
check("index.html 在 app.js 之前加载 overlay3d.js",
      index_src.index("/static/overlay3d.js") < index_src.index("/static/app.js"), "")
check("overlay3d 含基准平面/选中高亮/z 控制柄",
      all(("function %s(" % f) in ov_src for f in ("drawBasePlane", "drawSelection3d", "drawZHandle")), "")
# 状态绑定交叉检查：用常驻工具（曾抓到 planeZ 缺 getter case）
_sub = subprocess.run([sys.executable, "-B", "devtools/check_state_bindings.py"], cwd=str(ROOT),
                      capture_output=True, text=True)
check("状态绑定交叉检查工具（模块 get/set ↔ app.js 分支）",
      _sub.returncode == 0 and "全部 get/set 均有对应分支" in _sub.stdout,
      _sub.stdout.strip()[:70])

print("\n=== B9. 前端：三维场景绘制模块（static/scene3d.js，render3d 主绘制段）+ get/set 交叉检查 ===")
sc_path = ROOT / "server" / "static" / "scene3d.js"
sc_src = sc_path.read_text(encoding="utf-8") if sc_path.exists() else ""
check("scene3d.js 存在", sc_path.exists(), "")
check("app.js 经 _scene.drawScene() 调用（原 245 行内联段已移走）",
      "_scene.drawScene();" in app_src and "画家算法" not in app_src.replace("// 三维场景绘制", ""), "")
check("index.html 在 app.js 之前加载 scene3d.js",
      index_src.index("/static/scene3d.js") < index_src.index("/static/app.js"), "")
check("scene3d 覆盖几何收集/遮挡分类/顶点绘制",
      all(k in sc_src for k in ("var faces = []", "GGB_OCC.buildFacePolys", "ctx3.font = '13px sans-serif'")), "")
check("scene3d 的调试计数经 env 读写（不再直接改应用变量）",
      "set('dbgProjReuse'" in sc_src and "set('dbgOccTests'" in sc_src
      and "dbgOccTests++" not in sc_src, "")
# get/set 交叉检查已固化为 devtools/check_state_bindings.py（见 B10）

print("\n=== B8. 前端：三维遮挡判定模块（static/occlusion3d.js，render3d 第三步） ===")
oc_path = ROOT / "server" / "static" / "occlusion3d.js"
oc_src = oc_path.read_text(encoding="utf-8") if oc_path.exists() else ""
check("occlusion3d.js 存在", oc_path.exists(), "")
check("遮挡适配已随场景段进入 scene3d（app.js 不再有 edgeOccluded 定义）",
      "window.GGB_OCC.buildFacePolys(faces)" in sc_src
      and "window.GGB_OCC.edgeOccluded(p1, p2, facePolys, proj3" in sc_src
      and app_src.count("function edgeOccluded(p1, p2) {") == 0, "")
check("遮挡逻辑改为显式参数（不依赖闭包局部量）",
      "function edgeOccluded(p1, p2, facePolys, proj3, onTest)" in oc_src
      and "function buildFacePolys(faces)" in oc_src, "")
check("index.html 在 app.js 之前加载 occlusion3d.js",
      index_src.index("/static/occlusion3d.js") < index_src.index("/static/app.js"), "")
_sub = subprocess.run(["node", "devtools/test_occlusion_module.js"], cwd=str(ROOT), capture_output=True, text=True)
check("occlusion3d 单元测试（射线法/面表排序/早停/计数回调）",
      _sub.returncode == 0 and _sub.stdout.count("OK") >= 10,
      (_sub.stdout.strip().splitlines() or [""])[0][:50] + _sub.stderr.strip()[-50:])

print("\n=== B7. 前端：三维坐标轴绘制模块（static/axes3d.js，render3d 第二步） ===")
ax_path = ROOT / "server" / "static" / "axes3d.js"
ax_src = ax_path.read_text(encoding="utf-8") if ax_path.exists() else ""
check("axes3d.js 存在", ax_path.exists(), "")
check("app.js 通过 window.GGB_AX3 装配（原绘制体已移走）",
      "window.GGB_AX3" in app_src and "axisTicks3d.tickLen" not in app_src
      and "function drawAxes3d() { return _axes3d" in app_src, "")
check("index.html 在 app.js 之前加载 axes3d.js",
      index_src.index("/static/axes3d.js") < index_src.index("/static/app.js"), "")
check("axes3d 含坐标轴/迷你轴/刻度/箭头/步长",
      all(("function %s(" % f) in ax_src for f in ("drawAxes3d", "drawMiniAxes3d", "arrowHead3",
                                                   "niceStep3d", "saveAxisTicks3d")), "")
check("axes3d 复用 proj3d 的转发助手（proj3/line3 为注入）",
      "var proj3 = env.proj3;" in ax_src and "var line3 = env.line3;" in ax_src, "")
check("axes3d 不直接依赖 localStorage 之外的全局状态（axisTicks3d 经 env 注入）",
      "var axisTicks3d = env.get('axisTicks3d');" in ax_src, "")

print("\n=== B6. 前端：三维投影/屏幕空间模块（static/proj3d.js，render3d 第一步） ===")
p3_path = ROOT / "server" / "static" / "proj3d.js"
p3_src = p3_path.read_text(encoding="utf-8") if p3_path.exists() else ""
check("proj3d.js 存在", p3_path.exists(), "")
check("app.js 通过 window.GGB_P3 装配（原实现体已移走，仅剩薄包装）",
      "window.GGB_P3" in app_src
      and "var pxScale = Math.min(cssW, cssH) * 0.42 / cam.r;" not in app_src
      and "function proj3() { return _proj3d" in app_src, "")
check("index.html 在 app.js 之前加载 proj3d.js",
      index_src.index("/static/proj3d.js") < index_src.index("/static/app.js"), "")
check("proj3d 含投影/逆投影/命中判定",
      all(("function %s(" % f) in p3_src for f in ("proj3", "camBasis3", "line3", "distToSeg",
                                                   "pointInScreenPoly", "snapAxis3d", "wsegHit")), "")
check("有写入的模块自动注入 set（dbgProjCalls 自增写回应用状态）",
      "set: _panelStateSet" in app_src and "env.set('dbgProjCalls', env.get('dbgProjCalls') + 1)" in p3_src, "")
check("proj3d 未夺走 draw2d 的转发助手（sxp/syp 为注入）",
      "var sxp = env.sxp;" in p3_src and "var syp = env.syp;" in p3_src, "")

print("\n=== B5. 前端：统计图渲染模块（static/charts.js） ===")
ch_path = ROOT / "server" / "static" / "charts.js"
ch_src = ch_path.read_text(encoding="utf-8") if ch_path.exists() else ""
check("charts.js 存在", ch_path.exists(), "")
check("app.js 通过 window.GGB_CHARTS 装配（原绘图体已移走）",
      "window.GGB_CHARTS" in app_src and "ctx.arc(pcx, pcy" not in app_src
      and "function drawPieChart() { return _charts" in app_src, "")
check("index.html 在 app.js 之前加载 charts.js",
      index_src.index("/static/charts.js") < index_src.index("/static/app.js"), "")
check("charts.js 含六类统计图绘制",
      all(("function %s(" % f) in ch_src for f in ("drawBarChart", "drawBoxPlot", "drawPieChart",
                                                    "drawLineChart", "drawScatterPlot", "drawDotPlot")), "")
check("charts.js 未夺走 draw2d 的转发助手（sxp/syp 为注入）",
      "var sxp = env.sxp;" in ch_src and "var syp = env.syp;" in ch_src
      and "function sxp() { return _draw2d" in app_src, "")

print("\n=== B4. 前端：绘制基元模块（static/draw2d.js）+ JS 作用域守卫 ===")
d2_path = ROOT / "server" / "static" / "draw2d.js"
d2_src = d2_path.read_text(encoding="utf-8") if d2_path.exists() else ""
check("draw2d.js 存在", d2_path.exists(), "")
check("app.js 通过 window.GGB_D2 装配（原绘制体已移走）",
      "window.GGB_D2" in app_src and "ctx.moveTo(sx, 0); ctx.lineTo(sx, h);" not in app_src
      and "function drawGrid() { return _draw2d" in app_src, "")
check("index.html 在 app.js 之前加载 draw2d.js",
      index_src.index("/static/draw2d.js") < index_src.index("/static/app.js"), "")
check("draw2d 未夺走 panels 的转发助手（fmtNum 仍是 panels 包装）",
      "function fmtNum() { return _panels.fmtNum" in app_src
      and "var fmtNum = env.fmtNum;" in d2_src, "")
# JS 作用域守卫：四个模块全部标识符可解析
_sub = subprocess.run(["node", "devtools/check_frontend_modules.js"], cwd=str(ROOT), capture_output=True, text=True)
check("前端模块 JS 作用域守卫（全部标识符可解析，动态扫描 static/*.js）",
      _sub.returncode == 0
      and _sub.stdout.count("OK") >= len([q for q in (ROOT / "server" / "static").glob("*.js")
                                          if q.name not in ("app.js", "data.js", "i18n.js")]),
      _sub.stdout.strip().replace("\n", " | ")[:80])
# 守卫自检：删掉 drawGrid 的 cssH 注入必须被抓到
_mut = re.sub(r"var C = env\.get\('C'\), cssH = env\.get\('cssH'\),", "var C = env.get('C'),", d2_src, count=1)
if _mut != d2_src:
    _tmpf = ROOT / "server" / "static" / "_mut_check.js"
    _tmpf.write_text(_mut, encoding="utf-8")
    _m = subprocess.run(["node", "devtools/check_frontend_modules.js", str(_tmpf)],
                        cwd=str(ROOT), capture_output=True, text=True)
    _tmpf.unlink()
    check("守卫自检：漏注入状态会被抓到（变异 cssH）",
          _m.returncode == 1 and "cssH" in _m.stdout, _m.stdout.strip()[:60])
else:
    check("守卫自检：漏注入状态会被抓到（变异 cssH）", False, "变异未生效（draw2d.js 结构变化）")

print("\n=== B3. 前端：面板渲染模块（static/panels.js） ===")
pan_path = ROOT / "server" / "static" / "panels.js"
pan_src = pan_path.read_text(encoding="utf-8") if pan_path.exists() else ""
check("panels.js 存在", pan_path.exists(), "")
check("app.js 通过 window.GGB_PANELS 装配（原渲染体已移走）",
      "window.GGB_PANELS" in app_src and 'class="obj-empty"' not in app_src
      and "function renderList() { return _panels" in app_src, "")
check("app.js 为 17 个面板函数保留薄包装",
      len(re.findall(r"return _panels\.\w+\.apply\(null, arguments\);", app_src)) == 17,
      str(len(re.findall(r"return _panels\.\w+\.apply\(null, arguments\);", app_src))))
check("index.html 在 app.js 之前加载 panels.js",
      index_src.index("/static/panels.js") < index_src.index("/static/app.js"), "")
check("panels.js 状态经 env 注入（不直接引用应用级变量）",
      "env.get(" in pan_src and "env.set(" in pan_src and "window.GGB_I18N" not in pan_src, "")
check("panels.js 无 DOM 事件装配（只做渲染）", "addEventListener" not in pan_src, "")
_sub = subprocess.run(["node", "devtools/test_panels_module.js"], cwd=str(ROOT), capture_output=True, text=True)
check("panels.js 桩环境冒烟（列表/工具面板/分类/写状态/翻译/转义）",
      _sub.returncode == 0 and all(k in _sub.stdout for k in (
          "空列表提示: true", "对象行渲染: true", "showCat 写 activeCat: true",
          "翻译可用: true", "esc 转义: true")),
      ((_sub.stdout.strip().splitlines() or [""])[-1][:50]) + _sub.stderr.strip()[-60:])

print("\n=== B2. 前端：试卷渲染/导出模块（static/exam.js） ===")
exam_path = ROOT / "server" / "static" / "exam.js"
exam_src = exam_path.read_text(encoding="utf-8") if exam_path.exists() else ""
check("exam.js 存在", exam_path.exists(), "")
check("app.js 通过 window.GGB_EXAM 装配（原实现体已移走，仅剩薄包装）",
      "window.GGB_EXAM" in app_src and 'class="eq"' not in app_src
      and "exam_score_l" not in app_src and "function renderExam() { return _examMod" in app_src, "")
check("app.js 保留同名薄包装（调用点不变）",
      "function renderExam() { return _examMod" in app_src
      and "function escHtml(s) { return _examMod" in app_src, "")
check("index.html 在 app.js 之前加载 exam.js",
      index_src.index("/static/exam.js") < index_src.index("/static/app.js"), "")
check("exam.js 不含试卷面板装配代码（只做渲染/导出/转义）",
      "addEventListener" not in exam_src and "examPanel" not in exam_src, "")
check("exam.js 状态只读（无对 app 状态赋值）", "exam =" not in exam_src.replace("var exam = env.getExam();", ""), "")
_sub = subprocess.run(["node", "devtools/test_exam_module.js"], cwd=str(ROOT), capture_output=True, text=True)
check("exam.js 桩环境冒烟（渲染非空/转义/导出提示）",
      _sub.returncode == 0 and "renderExam 非空: true" in _sub.stdout
      and "转义生效: true" in _sub.stdout and "exportExam 提示: true" in _sub.stdout,
      (_sub.stdout.strip().splitlines() or [""])[-1][:60] + _sub.stderr.strip()[-60:])

print("\n=== B1. 前端：数学键盘面板模块 ===")
kb_path = ROOT / "server" / "static" / "keyboard.js"
kb_src = kb_path.read_text(encoding="utf-8") if kb_path.exists() else ""
check("keyboard.js 存在", kb_path.exists(), "")
check("app.js 通过 window.GGB_KB 装配（不再自带 kb* 实现）",
      "window.GGB_KB" in app_src and "function kbInsert" not in app_src and "function kbTarget" not in app_src, "")
check("index.html 在 app.js 之前加载 keyboard.js",
      index_src.index("/static/keyboard.js") < index_src.index("/static/app.js"), "")
check("键盘面板按键仍由 index.html 提供（≥40 个 .kb-key）",
      index_src.count('class="kb-key"') >= 40, str(index_src.count('class="kb-key"')))
check("keyboard.js 覆盖 bs/clear/enter 三种功能键",
      all(k in kb_src for k in ("'bs'", "'clear'", "'enter'")), "")
check("app.js 行数继续受控（< 5800）", len(app_src.splitlines()) < 5800, str(len(app_src.splitlines())))

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
# 预算：i18n 抽取前基线 5680 行；文案外置已验证（上方断言），此处只做软预算防膨胀
# （统计图功能新增绘制代码，行数由 5542 增至 ~5697，故上限放宽到 5800）
check("app.js 行数受控（< 5800，软预算）", len(app.splitlines()) < 5800, str(len(app.splitlines())))

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
