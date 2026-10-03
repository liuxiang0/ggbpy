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
check("geometry3d 只依赖 elements/tolerance/math/numpy",
      set(re.findall(r"^from \.(\w+) import", geo_src, re.M)) <= {"elements", "tolerance"},
      str(sorted(set(re.findall(r"^from \.(\w+) import", geo_src, re.M)))))
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
    defined = set(re.findall(r"def (\w+)\(", txt))
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
            "kernel/cmd_util.py"):
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
    "console.log(JSON.stringify({cas:(d.CAS_COMMANDS||[]).length,tools:Object.keys(t).length,"
    "cats:cats.length,missing,extra}));"
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
    return sorted(called - top - local - set(dir(_bi)))


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

print("\n=== A7. AST 级守卫：抽出模块不得漏导入 ===")
for mod in ("kernel/geometry3d.py", "kernel/solids.py", "kernel/geo2d.py", "kernel/stats.py",
            "kernel/cmd_util.py", "kernel/calculus.py", "kernel/schemas.py"):
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
check("commands 注入嵌套求值钩子（set_nested_evaluator(_eval_nested)）",
      "set_nested_evaluator(_eval_nested)" in cmd_src, "")
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
