#!/usr/bin/env python3
"""代码质量策略检测（REVIEW P1 第 10 条：`except Exception` 审计）。

策略（可执行、可回归）：
1. **宽泛捕获必须带说明**：每处 `except Exception` 的同行或上一行要有注释，写明「捕获的是什么、
   为什么可以吞」——避免把编程错误静默吞成 `error` 状态而不留痕迹。
   （类型明确的场景应直接收窄，如 `float()` → ValueError/TypeError、json/base64 → ValueError）
2. **禁止裸 `except:`**：连异常类型都不写的捕获一律拒绝。
3. **数量预算**：宽泛捕获总数不得超过 `BUDGET`，防止在审计后继续无节制增加；
   超预算时要么收窄类型，要么补说明并调高预算（需在提交信息里说明理由）。
4. **自检**：向临时文件注入一处无说明的捕获，扫描器必须报出（防止守卫本身失效）。

用法：python3 devtools/test_quality.py
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUDGET = 70          # 审计后基线 63，留少量余量；新增宽泛捕获需在此说明理由
BROAD = re.compile(r"except\s+Exception\b")
BARE = re.compile(r"except\s*:")

ok = 0
fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok, fail
    if cond:
        ok += 1
        print("  OK   %s%s" % (name, ("  [%s]" % detail) if detail else ""))
    else:
        fail += 1
        print("  FAIL %s%s" % (name, ("  [%s]" % detail) if detail else ""))


def scan(paths) -> tuple[list, list]:
    """返回 (无说明的宽泛捕获列表, 裸 except 列表)，元素为 "file:line[:片段]"。"""
    undocumented, bare = [], []
    for f in paths:
        lines = f.read_text(encoding="utf-8").splitlines()
        for i, l in enumerate(lines):
            try:
                rel = f.relative_to(ROOT)
            except ValueError:      # 自检用的临时目录不在仓库内
                rel = f
            if BARE.search(l):
                bare.append("%s:%d" % (rel, i + 1))
            if BROAD.search(l):
                has_inline = "#" in l
                prev_is_comment = i > 0 and lines[i - 1].strip().startswith("#")
                if not (has_inline or prev_is_comment):
                    undocumented.append("%s:%d" % (rel, i + 1))
    return undocumented, bare


def main() -> int:
    print("=== A. 宽泛捕获（except Exception）策略 ===")
    paths = sorted(list((ROOT / "kernel").glob("*.py")) + list((ROOT / "server").glob("*.py")))
    undocumented, bare = scan(paths)
    total = sum(1 for f in paths for l in f.read_text(encoding="utf-8").splitlines() if BROAD.search(l))
    check("kernel/ 与 server/ 的宽泛捕获都有说明注释", not undocumented, str(undocumented[:4]))
    check("无裸 except:（必须写明异常类型）", not bare, str(bare[:4]))
    check("宽泛捕获数量在预算内（≤ %d）" % BUDGET, total <= BUDGET, "n=%d" % total)

    print("\n=== B. 类型收窄抽查（明确场景不应再用宽泛捕获） ===")
    src_all = "".join(f.read_text(encoding="utf-8") for f in paths)
    check("环境变量数值解析已收窄（commands3d GGBPY_IMPLICIT_BUDGET）",
          "except (ValueError, TypeError):  # 环境变量非法" in src_all, "")
    check("ggbpyData 解码失败按 ValueError 家族收窄",
          "except ValueError as e:  # 坏数据" in src_all, "")
    check("记忆键数值化失败按 ValueError/TypeError 收窄",
          "except (ValueError, TypeError):  # 值无法转为浮点" in src_all, "")

    print("\n=== C. 扫描器自检（变异必须被抓到） ===")
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "kernel"
        bad.mkdir()
        (bad / "mut.py").write_text(
            "try:\n    pass\nexcept Exception:\n    pass\n", encoding="utf-8")
        mut_undoc, _ = scan(list(bad.glob("*.py")))
        check("注入的无说明宽泛捕获会被抓到", len(mut_undoc) == 1, str(mut_undoc))
        (bad / "mut2.py").write_text(
            "try:\n    pass\nexcept Exception:  # 已说明\nexcept:\n    pass\n", encoding="utf-8")
        _, mut_bare = scan(list(bad.glob("*.py")))
        check("注入的裸 except 会被抓到", len(mut_bare) >= 1, str(mut_bare))

    print("\n=== D. 文档章节完整性（README 限制/边界章节，防漂移） ===")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # 防误截断：曾有文档脚本把 README 写成空文件并提交（0 行），CI 未拦住
    check("README 非空且规模正常（≥ 400 行，防误截断）", len(readme.splitlines()) >= 400,
          "lines=%d bytes=%d" % (len(readme.splitlines()), len(readme.encode("utf-8"))))
    check("README 含变更历史与快速开始（结构完整）",
          "## 🚀 快速开始" in readme and "第五十六批" in readme, "")
    check("README 含「2D 限制」章节（与 3D 章节对称）", "#### 2D 限制" in readme, "")
    check("README 含「2D 检测矩阵」章节", "#### 2D 检测矩阵" in readme, "")
    if "#### 2D 限制" in readme:
        sec = readme[readme.index("#### 2D 限制"):readme.index("### 3D 视图")]
        bullets = [l for l in sec.splitlines() if l.startswith("- **")]
        check("2D 限制章节条目 ≥ 8（覆盖撤销/记忆/嵌套/统计图/工具等）", len(bullets) >= 8,
              "n=%d" % len(bullets))
        check("2D 限制章节锚定关键上限（撤销 200 / 嵌套 4 层 / 203 词条 / 11 分类）",
              all(k in sec for k in ("UNDO_LIMIT = 200", "4 层", "203", "11 个分类")), "")

    print("\n=== E. 回顾文档闭环状态（REVIEW_12_BATCHES.md §0） ===")
    rev = (ROOT / "REVIEW_12_BATCHES.md").read_text(encoding="utf-8")
    check("REVIEW 文档非空且含原始回顾文本",
          len(rev.splitlines()) >= 100 and "## 1. 一页数字" in rev, "lines=%d" % len(rev.splitlines()))
    check("REVIEW 含 §0 闭环状态章节", "## 0. 闭环状态" in rev, "")
    check("§0 覆盖架构债逐条状态（✅/⚠️/⛔ 标记 ≥10 条）",
          sum(rev.count(m) for m in ("✅", "⚠️", "⛔")) >= 10,
          str(sum(rev.count(m) for m in ("✅", "⚠️", "⛔"))))
    check("§0 含「判定不需要」并给出依据", "判定「不需要做」" in rev and "差量撤销快照" in rev, "")
    check("§0 给出可复现复核入口（三个工具）",
          all(k in rev for k in ("run_all_detection.sh", "bench_blocking.py", "bench_undo.py")), "")

    print("\n" + "=" * 56)
    print("代码质量策略检测：%d 项断言，%d 失败" % (ok + fail, fail))
    print("结果: " + ("ALL PASS" if fail == 0 else "FAILED"))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
