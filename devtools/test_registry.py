#!/usr/bin/env python3
"""命令注册表一致性检测（P1-F）：防止 COMMANDS / ALIASES / _result_kind / DISPLAY_NAMES 四张表漂移。

用法：python3 -B devtools/test_registry.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel import commands as C  # noqa: E402

PASS = 0
FAIL = 0
FAILED = []

KINDS = {"number", "point", "list", "matrix", "boolean", "function", "complex", "text",
         "geo3d", "polygon", "circle", "conic", "segment", "line", "ray", "vector", "arc",
         "polyline", "locus", "barchart", "boxplot", "result", "image", "angle", "slope",
         # 自动标签专用类型（未命名曲线/统计图）
         "implicit", "parametric", "polar", "piechart", "sumrect",
         # 统计图家族（本批新增：折线/散点/点图）
         "linechart", "scatterplot", "dotplot", "stemplot", "button", "checkbox", "inputbox"}

# 多词命令识别用的词根：出现在非首位即说明是拼接词，显示名在该处必须大写
WORD_ROOTS = ("coefficient", "polygon", "create", "delete", "bisector", "between",
              "chart", "plot", "value", "color", "coords", "visible", "locked",
              "cloud", "path", "ineq", "perimeter", "surface", "random")
# 本身就是单个词、拼写即"首字母大写"的命令（无需 CamelCase）
SINGLE_WORD_OK = {"incenter", "excenter", "incircle", "midpoint", "polyline",
                  "circumcircle", "semicircle", "histogram", "hyperbola", "parabola",
                  "ellipse", "conic", "locus", "translate", "transpose", "intersect",
                  "derivative", "conjugate", "covariance", "circumference", "iteration",
                  "parametric", "perimeter", "randomize", "surfacearea"}


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  OK   " + name)
    else:
        FAIL += 1
        FAILED.append(name)
        print("  FAIL " + name + "  " + detail)


print("=== 命令注册表一致性 ===")
cmds = set(C.COMMANDS.keys())
check("COMMANDS 非空（%d 条）" % len(cmds), len(cmds) > 100)

# 1) 每条命令都有结果类型提示
missing_kind = sorted(c for c in cmds if c not in C.RESULT_KINDS)
check("每条命令都在 RESULT_KINDS（结果类型单一来源）", not missing_kind, "缺 %d 条: %s" % (len(missing_kind), missing_kind[:12]))

# 2) 结果类型取值合法
bad_kinds = sorted({C.RESULT_KINDS[c] for c in cmds if c in C.RESULT_KINDS} - KINDS)
check("_result_kind 取值都在已知类型集合内", not bad_kinds, str(bad_kinds))

# 3) 别名解析到真实命令
bad_alias = sorted({v for v in C.ALIASES.values() if v not in cmds})
check("ALIASES 的值都指向真实命令", not bad_alias, str(bad_alias[:12]))

# 4) 别名不与命令名冲突、且无歧义（同一别名不能指向两个命令由 dict 保证）
clash = sorted(set(C.ALIASES.keys()) & cmds)
check("别名与英文命令名不冲突", not clash, str(clash[:12]))

# 5) 显示名：多词命令应有 CamelCase（首字母外还有大写），否则给出待补清单
def camel_ok(low):
    """含词根拼接的命令：显示名在词根处必须大写；已知单词命令只需首字母大写。"""
    disp = C.DISPLAY_NAMES.get(low, low[:1].upper() + low[1:])
    if low in SINGLE_WORD_OK:
        return disp[:1].isupper()
    hits = [w for w in WORD_ROOTS if low.find(w) > 0]
    if not hits:
        return disp[:1].isupper()
    for w in hits:
        i = low.find(w)
        if i < len(disp) and not disp[i].isupper():
            return False
    return True


not_camel = sorted(c for c in cmds if not camel_ok(c))
check("多词命令都有 CamelCase 显示名（或显式豁免）", not not_camel,
      "待补 %d 条: %s" % (len(not_camel), not_camel[:14]))

# 6) 显示名不与命令名/别名重复
disp = {}
dups = []
for c in cmds:
    d = C.DISPLAY_NAMES.get(c, c[:1].upper() + c[1:])
    if d in disp:
        dups.append((d, disp[d], c))
    disp[d] = c
check("显示名唯一", not dups, str(dups[:5]))

# 7) 中文别名不应与英文命令同名（避免歧义）
# REVIEW #6：显示名必须挂在真实命令上（重构单一来源时曾发现 5 个不可达孤儿）
orphan_disp = sorted(k for k in C.DISPLAY_NAMES if k not in cmds)
check("DISPLAY_NAMES 的键都是真实命令（无孤儿显示名）", not orphan_disp, str(orphan_disp[:6]))

zh_dup = sorted(k for k in C.ALIASES if k in C.DISPLAY_NAMES)
check("中文别名不与显示名冲突", not zh_dup, str(zh_dup[:8]))

# 8) 参数签名表（kernel/signatures.py）：**全覆盖 + 无失效 key + 前缀 == 显示名**
#    前缀必须等于显示名：前端 Tab 补全会把签名整串填入，前缀不对就会填出另一条命令 ✗
#    （本轮修掉的真实缺陷：9 条 key 失效 → 对应命令一直无参数提示，另有 1 条前缀写成了别的命令）
from kernel.signatures import SIGNATURES  # noqa: E402

def _disp(k):
    return C.DISPLAY_NAMES.get(k) or (k[:1].upper() + k[1:])

def _split_top(sig):
    """只按**顶层**「 或 」切分（括号内的「或」是参数名的一部分，如 Solve[方程 或 方程组, 变量?]）。"""
    out, depth, cur, i = [], 0, "", 0
    while i < len(sig):
        ch = sig[i]
        if ch in "[({":
            depth += 1
        elif ch in "])}":
            depth -= 1
        if depth == 0 and sig.startswith(" 或 ", i):
            out.append(cur); cur = ""; i += len(" 或 "); continue
        cur += ch; i += 1
    out.append(cur)
    return [x.strip() for x in out if x.strip()]

dead_sig = sorted(k for k in SIGNATURES if k not in cmds)
check("签名表没有失效 key（都挂在真实命令上）", not dead_sig, str(dead_sig[:8]))
missing_sig = sorted(k for k in cmds if k not in SIGNATURES)
check("190 条命令全部登记参数签名（不再回退 名字[…]）", not missing_sig, str(missing_sig[:8]))
fallback = sorted(k for k in cmds if SIGNATURES.get(k, "").endswith("[…]"))
check("签名表无 […] 回退项", not fallback, str(fallback[:8]))
bad_pre = [(k, SIGNATURES[k]) for k in SIGNATURES
           if k in cmds and not SIGNATURES[k].lower().startswith(_disp(k).lower())]
check("签名前缀 == 该命令的显示名", not bad_pre, str(bad_pre[:4]))
bad_alt = [(k, v, p) for k, v in SIGNATURES.items() for p in _split_top(v)
           if k in cmds and not p.lower().startswith(_disp(k).lower())]
check("签名的每个顶层备选形式都以显示名开头", not bad_alt, str(bad_alt[:3]))
bad_bracket = [(k, v) for k, v in SIGNATURES.items()
               if v.count("[") != v.count("]") or v.count("]") < 1]
check("签名括号配对且至少一组参数", not bad_bracket, str(bad_bracket[:4]))

# ---------------------------------------------------------------------------
# 签名的**语义**守卫：签名写的是真实可用的调用形式吗？
# 背景（2026-10-10）：签名表 190/190 只保证了"结构完整"，但 arc/prism/pyramid/cylinder/cone
# 五条的写法与内核实现不符（如 `Pyramid[多边形, 高度]` 实际是 `Pyramid[点,点,点]` 三棱锥）✗
# —— 这里用「按签名形式真跑一遍」把它们钉死（新写签名也应尽量进这张表）。
from kernel.construction import Construction  # noqa: E402

SEMANTIC_CASES = [
    # (说明, 前置, 用签名形式写的调用)
    ("Arc[起点, 终点, 圆心]", ["A=(-1,0)", "B=(1,0)", "C=(0,0)"], "Arc[A,B,C]"),
    ("Sector[起点, 终点, 圆心]", ["A=(-1,0)", "B=(1,0)", "C=(0,0)"], "Sector[A,B,C]"),
    ("Semicircle[点, 点]", ["A=(-1,0)", "B=(1,0)"], "Semicircle[A,B]"),
    ("Cube[点, 点]", ["A=(0,0,0)", "B=(2,0,0)"], "Cube[A,B]"),
    ("Prism[点, 点, 点]（三棱柱）", ["A=(0,0,0)", "B=(2,0,0)", "C=(0,2,0)"], "Prism[A,B,C]"),
    ("Pyramid[点, 点, 点]（三棱锥）", ["A=(0,0,0)", "B=(2,0,0)", "C=(0,2,0)"], "Pyramid[A,B,C]"),
    ("Cylinder[底心, 底半径点, 顶心]", ["A=(0,0,0)", "R=(1,0,0)", "T=(0,0,3)"], "Cylinder[A,R,T]"),
    ("Cone[底心, 底半径点, 顶点]", ["A=(0,0,0)", "R=(1,0,0)", "T=(0,0,3)"], "Cone[A,R,T]"),
    ("Sphere[球心, 半径]", ["O=(0,0,0)"], "Sphere[O,2]"),
    ("Plane[点, 点, 点]", ["A=(0,0,0)", "B=(1,0,0)", "C=(0,1,0)"], "Plane[A,B,C]"),
    ("RegularPolygon[点A, 点B, 边数]", ["A=(0,0)", "B=(1,0)"], "RegularPolygon[A,B,6]"),
    ("Delaunay[点列表]", ["L={(0,0),(1,0),(0,1)}"], "Delaunay[L]"),
]
sem_bad = []
for _desc, _pre, _call in SEMANTIC_CASES:
    _c = Construction()
    try:
        for _ln in _pre:
            _c.process(_ln)
        _msg = _c.process("X=" + _call)
        if not _msg.startswith("OK"):
            sem_bad.append((_desc, _msg[:50]))
    except Exception as _e:            # noqa: BLE001 —— 检测脚本：任何异常都算失败
        sem_bad.append((_desc, repr(_e)[:50]))
check("签名语义：按签名形式实跑均成功（%d 例）" % len(SEMANTIC_CASES), not sem_bad, str(sem_bad[:3]))

_bad_sig_text = [k for k, v in SIGNATURES.items()
                 if "多边形, 高度" in v or "圆心, 点, 点" in v or "底心, 顶点, 半径" in v]
check("签名表不含已确认错误的写法（多边形+高度 / 圆心在前 / 底心顶点半径）",
      not _bad_sig_text, str(_bad_sig_text))

print("\n" + "=" * 56)
print("注册表检查：%d 项断言，%d 失败" % (PASS + FAIL, FAIL))
if FAILED:
    for n in FAILED:
        print("  FAILED: " + n)
    sys.exit(1)
print("结果: ALL PASS")
sys.exit(0)
