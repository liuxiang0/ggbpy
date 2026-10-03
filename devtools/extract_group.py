#!/usr/bin/env python3
"""命令组抽取工具（P2 结构拆分配套）。

用途：把 kernel/commands.py 里的命令实现成组搬到独立模块，并自动
①AST 求闭包 ②合成导入 ③从 commands.py 删除 ④插入 re-export。

用法：
    python3 devtools/extract_group.py --analyze            # 列出剩余可搬组（含组外依赖）
    python3 devtools/extract_group.py --module transforms --seeds _cmd_rotate,_cmd_reflect ... --doc "…" [--apply]

不带 --apply 时只做「干跑」：报告闭包、行数与合成导入，不写文件。
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TOL = ("EPSILON", "TIGHT", "COORD", "ZERO_SQ", "LOOSE", "COARSE", "NEGLIGIBLE",
       "ROOT_TOL", "OPT_XATOL", "OPT_FATOL")
THIRD_PARTY = {"sympy", "numpy", "scipy"}


def provider_modules():
    """已抽出的模块（提供外部符号）：动态扫描 kernel/ 下所有模块（排除 commands 自身）。

    动态化避免每次新增模块都要改工具（曾因漏列 primitives 导致 _resolve_vector3 漏导入）。
    """
    import importlib
    mods = {}
    for f in sorted((ROOT / "kernel").glob("*.py")):
        name = f.stem
        if name in ("commands", "__init__"):
            continue
        try:
            mods[name] = importlib.import_module("kernel." + name)
        except Exception:
            continue
    return mods


def load_commands():
    path = ROOT / "kernel" / "commands.py"
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    tree = ast.parse(src)
    top = {}
    consts = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            top[n.name] = (n.lineno, n.end_lineno)
        elif isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            nm = n.targets[0].id
            consts[nm] = (n.lineno, n.end_lineno)
    return path, src, lines, top, consts


def src_of(lines, top, name):
    a, b = top[name]
    return "".join(lines[a - 1:b])


def calls_in(code):
    return {n.func.id for n in ast.walk(ast.parse(code))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def attr_bases(code):
    return {n.value.id for n in ast.walk(ast.parse(code))
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}


def closure(top, lines, seeds):
    got, q = set(), [s for s in seeds if s in top]
    missing = [s for s in seeds if s not in top]
    while q:
        n = q.pop()
        if n in got or n not in top:
            continue
        got.add(n)
        for c in calls_in(src_of(lines, top, n)):
            if c in top and c not in got:
                q.append(c)
    return got, missing


def external_deps(top, lines, got, provided):
    ext = set()
    for n in got:
        code = src_of(lines, top, n)
        for name in calls_in(code) | attr_bases(code):
            if name in top and name not in got and name not in provided:
                ext.add(name)
    return sorted(ext)


def synthesize_imports(lines, top, moved, provided_mods):
    """合成 import：按模块合并、同名符号只取一个提供者（按模块名排序，确定性）。"""
    code = "\n".join(src_of(lines, top, n) for n in moved)
    called = calls_in(code) | attr_bases(code)
    tree = ast.parse(code)
    local = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            local.add(node.name)
        elif isinstance(node, ast.arg):
            local.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            local.add(node.id)
    used_names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | called

    per_mod = {}
    assigned = set()
    # elements/tolerance/parser 由下面的专门步骤处理（避免重复 import）
    SPECIAL = {"elements", "tolerance", "parser"}
    for mod in sorted(set(provided_mods) - SPECIAL):
        m = provided_mods[mod]
        prov = set(getattr(m, "__all__", []))
        try:
            mtree = ast.parse((ROOT / "kernel" / (mod + ".py")).read_text(encoding="utf-8"))
            for node in mtree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    prov.add(node.name)
                elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                    prov.add(node.targets[0].id)
        except Exception:
            pass
        names = sorted((used_names & prov) - local - assigned)
        if names:
            per_mod[mod] = names
            assigned |= set(names)

    imports = ["from .%s import %s" % (m, ", ".join(ns)) for m, ns in sorted(per_mod.items())]
    # 元素类 / 容差常量 / 解析器 / 子模块
    import kernel.elements as _els
    import kernel.tolerance as _tol
    caps = sorted(n for n in used_names if n.startswith("Geo") and hasattr(_els, n))
    if caps:
        imports.append("from .elements import " + ", ".join(caps))
    tol = sorted(n for n in used_names if n in TOL and hasattr(_tol, n))
    if tol:
        imports.append("from .tolerance import " + ", ".join(tol))
    # parse 层：把用到的 parser 符号整体导入（_split_brace/tokenize/parse_line/eval_number…）
    import kernel.parser as _parser
    already = set(assigned) | set(caps) | set(tol)
    pnames = sorted(n for n in used_names if hasattr(_parser, n) and n not in local and n not in already)
    if pnames:
        imports.append("from .parser import " + ", ".join(pnames))
    known_modules = {"schemas", "mesh_store", "image_store", "memo", "macro", "blob_store"}
    for b in sorted(attr_bases(code) & known_modules):
        imports.append("from . import %s" % b)
    return imports


def analyze():
    _, _, lines, top, _consts = load_commands()
    provided = set()
    prov_mods = provider_modules()
    for m in prov_mods.values():
        provided |= set(getattr(m, "__all__", []))
    provided |= {"eval_number", "parse_line", "_split_commas"}
    groups = {}
    for name in top:
        if not name.startswith("_cmd_"):
            continue
        key = name[len("_cmd_"):]
        groups.setdefault(key[:1].upper(), []).append(name)
    # 按「功能族」粗分（用命令名关键词）
    FAMILIES = {
        "点/线/圆/多边形": ("point", "segment", "line", "ray", "vector", "circle", "semicircle",
                            "arc", "sector", "polygon", "rigidpolygon", "regpoly", "polyline",
                            "midpoint", "perp", "parallel", "tangent", "anglebis", "foot",
                            "incenter", "centroid", "circumcircle", "incircle", "intersect"),
        "变换": ("reflect", "rotate", "translate", "dilate", "invert", "matrix"),
        "编辑/样式": ("set", "rename", "redefine", "delete", "lock", "hide", "show", "caption"),
        "数值/统计": ("sum", "mean", "median", "mode", "variance", "stdev", "min", "max", "sort",
                      "q1", "q3", "iqr", "normal", "ncr", "npr", "gcd", "lcm", "abs", "round",
                      "floor", "ceil", "mod", "random", "slider"),
        "导入导出": ("import", "export", "obj", "stl", "gltf", "load", "save", "image", "text"),
    }
    rows = []
    for fam, keys in FAMILIES.items():
        seeds = [n for n in top if n.startswith("_cmd_") and any(k in n[len("_cmd_"):] for k in keys)]
        got, missing = closure(top, lines, seeds)
        ext = external_deps(top, lines, got, provided)
        size = sum(src_of(lines, top, n).count("\n") for n in got)
        rows.append((fam, len(seeds), len(got), size, ext))
    print("%-16s %6s %6s %8s  %s" % ("族", "种子", "闭包", "行数", "组外依赖"))
    for fam, ns, ng, size, ext in rows:
        print("%-16s %6d %6d %8d  %s" % (fam, ns, ng, size, ext[:6] or "无"))
    print("\n剩余 _cmd_* 总数:", len([n for n in top if n.startswith("_cmd_")]))


def apply_extraction(module, seeds, doc, dry):
    path, src, lines, top, consts = load_commands()
    prov_mods = provider_modules()
    provided = set()
    for m in prov_mods.values():
        provided |= set(getattr(m, "__all__", []))
    provided |= {"eval_number", "parse_line", "_split_commas"}
    got, missing = closure(top, lines, seeds)
    assert not missing, "未找到种子: %s" % missing
    ext = external_deps(top, lines, got, provided)
    assert not ext, "组外依赖非空，需先一并搬迁: %s" % ext
    moved = sorted(got, key=lambda n: top[n][0])
    # 被引用但仍在 commands.py 的模块级常量 → 一并搬迁（如 _PRED_VIEW）
    code_all = "\n".join(src_of(lines, top, n) for n in moved)
    used = {n.id for n in ast.walk(ast.parse(code_all)) if isinstance(n, ast.Name)}
    moved_consts = sorted(c for c in consts if c in used and c not in moved)
    imports = synthesize_imports(lines, top, moved, prov_mods)
    total = sum(src_of(lines, top, n).count("\n") for n in moved)
    print("[%s] %d 函数 / %d 行；随迁常量: %s" % (module, len(moved), total, moved_consts or "无"))
    print("  导入:", imports)
    if dry:
        print("  （干跑，未写文件）")
        return
    const_blocks = ["".join(lines[consts[c][0] - 1:consts[c][1]]).rstrip("\n") for c in moved_consts]
    header = '"""%s"""\n\nfrom __future__ import annotations\n\nimport math\nimport re\nfrom typing import Any, Dict, List, Optional, Tuple\n\n%s\n\n\n__all__ = [\n%s]\n\n\n' % (
        doc, "\n".join(imports),
        "".join('    "%s",\n' % n for n in list(moved_consts) + moved))
    (ROOT / "kernel" / (module + ".py")).write_text(
        header + ("\n\n".join(const_blocks) + "\n\n\n" if const_blocks else "")
        + "\n\n".join(src_of(lines, top, n).rstrip("\n") for n in moved) + "\n", encoding="utf-8")
    out_lines = list(lines)
    ranges = [(top[n][0], top[n][1]) for n in moved] + [(consts[c][0], consts[c][1]) for c in moved_consts]
    for a, b in sorted(ranges, key=lambda t: -t[0]):
        del out_lines[a - 1:b]
    out = "".join(out_lines)
    anchor = "from .calculus import (  # noqa: F401"
    assert out.count(anchor) == 1
    j = out.index(")\n", out.index(anchor)) + 2
    const_reexport = "".join("from .%s import %s  # noqa: F401\n" % (module, c) for c in moved_consts)
    out = out[:j] + "\n# %s（P2 结构拆分：命令组抽出）\n%sfrom .%s import (  # noqa: F401\n%s)\n" % (
        doc, const_reexport, module,
        "".join("    %s,\n" % n for n in list(moved_consts) + moved)) + out[j:]
    path.write_text(out, encoding="utf-8")
    print("  已写入 kernel/%s.py；commands.py 现在 %d 行" % (module, len(out.splitlines())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--module")
    ap.add_argument("--seeds", default="")
    ap.add_argument("--doc", default="")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.analyze:
        analyze()
        return
    assert a.module and a.seeds, "需要 --module 与 --seeds"
    apply_extraction(a.module, [s.strip() for s in a.seeds.split(",") if s.strip()],
                     a.doc or (a.module + " 命令（P2 结构拆分：从 commands.py 抽出）。"), not a.apply)


if __name__ == "__main__":
    main()
