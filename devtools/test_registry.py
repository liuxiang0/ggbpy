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
         "implicit", "parametric", "polar", "piechart", "sumrect"}

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
zh_dup = sorted(k for k in C.ALIASES if k in C.DISPLAY_NAMES)
check("中文别名不与显示名冲突", not zh_dup, str(zh_dup[:8]))

print("\n" + "=" * 56)
print("注册表检查：%d 项断言，%d 失败" % (PASS + FAIL, FAIL))
if FAILED:
    for n in FAILED:
        print("  FAILED: " + n)
    sys.exit(1)
print("结果: ALL PASS")
sys.exit(0)
