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

    print("\n=== D. 文档职责与结构（README 只写当前状态；历史归 CHANGELOG） ===")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    rl = len(readme.splitlines())
    # 防误截断（曾有脚本把 README 写成 0 行并提交）；上限防再次膨胀成"变更日志"
    check("README 规模正常（150–500 行）", 150 <= rl <= 500,
          "lines=%d bytes=%d" % (rl, len(readme.encode("utf-8"))))
    check("README 含标准章节（简介 / 快速开始 / 功能总览 / 检测 / 许可）",
          all(k in readme for k in ("## ✨ 项目简介", "## 🚀 快速开始", "## 🎯 功能总览",
                                    "## 🧪 检测与质量", "## 📄 许可与致谢")), "")
    # **职责分离**：README 不得再出现批次流水账（历史一律在 CHANGELOG）
    check("README 不重复变更历史（无「第N批」流水账，且明确指向 CHANGELOG.md）",
          re.search(r"第[一二三四五六七八九十百零]+批", readme) is None and "CHANGELOG.md" in readme,
          "命中=%s" % (re.findall(r"第[一二三四五六七八九十百零]+批", readme)[:3]))
    check("README 含「2D 限制」「3D 限制」两节（对称）",
          "#### 2D 限制" in readme and "#### 3D 限制" in readme, "")
    check("README 给出可复现检测入口（全量 + 分范围）",
          "run_all_detection.sh" in readme and "run_scope.sh" in readme, "")
    if "#### 2D 限制" in readme and "#### 3D 限制" in readme:
        sec = readme[readme.index("#### 2D 限制"):readme.index("#### 3D 限制")]
        bullets = [l for l in sec.splitlines() if l.startswith("- **")]
        check("2D 限制章节条目 ≥ 8（覆盖撤销/记忆/嵌套/统计图/工具等）", len(bullets) >= 8,
              "n=%d" % len(bullets))
        check("2D 限制章节锚定关键上限（撤销 200 / 嵌套 4 层 / 228 词条 / 11 分类）",
              all(k in sec for k in ("UNDO_LIMIT = 200", "4 层", "228", "11 个分类")), "")

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

    # F. **防重蹈覆辙守卫**：CHANGELOG 批次条目结构完整性
    #    背景：连续两批用「替换锚点行」写 CHANGELOG，把上一批整条**删掉了** ✗ —— 靠记性没拦住。
    #    真实结构：文件里有多段批次列表（含早期「工具批」），且历史上 59/58 批未入 CHANGELOG（60→57 有缺口）。
    #    因此守卫按「**含最大编号（最新）的连续段**」判定：段内编号必须差恰为 1、段长不减少、最新号不倒退、总数不减少。
    #    中间被删一条 → 最新段被切成两半 → 段长骤降，直接抓红 ✓
    print("\n=== F. 变更日志批次条目完整性（防「整条被替换/删除」） ===")
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    _NUM = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
            "八": 8, "九": 9}

    def _cn2int(t: str) -> int:
        """中文数字 → int（支持 一…九百九十九）。"""
        section, cur = 0, 0
        for ch in t:
            if ch in _NUM:
                cur = _NUM[ch]
            elif ch == "十":
                section += (cur or 1) * 10
                cur = 0
            elif ch == "百":
                section += (cur or 1) * 100
                cur = 0
        return section + cur

    entries = []
    for line in cl.splitlines():
        m = re.match(r"^- \*\*第([一二三四五六七八九十百零]+)批", line)
        if m:
            entries.append((_cn2int(m.group(1)), line))
    nums = [n for n, _ in entries]
    dup = sorted({n for n in nums if nums.count(n) > 1})
    check("CHANGELOG 批次条目总数不减少（≥ 80，防整条被删）", len(entries) >= 80,
          "n=%d" % len(entries))
    check("批次编号唯一（重复即说明「替换锚点行」写坏过）", not dup, str(dup[:6]))
    check("每条批次条目内容非空且够长（≥ 40 字，防写入被截断）",
          all(len(l) >= 40 for _, l in entries), str([n for n, l in entries if len(l) < 40][:5]))

    runs, cur = [], [entries[0]]
    for prev, nxt in zip(entries, entries[1:]):
        (cur.append(nxt) if prev[0] - nxt[0] == 1 else (runs.append(cur), cur := [nxt]))
    runs.append(cur)
    main = max(runs, key=lambda r: r[0][0])            # 含最大编号 = 最新批次所在段
    check("最新批次所在段编号连续（相邻差恰为 1；中间被删一条会在此断段）",
          all(a[0] - b[0] == 1 for a, b in zip(main, main[1:])),
          "段长=%d 首=%d 末=%d" % (len(main), main[0][0], main[-1][0]))
    check("最新批次连续段长度不减少（≥ 33）", len(main) >= 33,
          "段长=%d（首=%d 末=%d）" % (len(main), main[0][0], main[-1][0]))
    check("最新批次数不倒退（≥ 92）", main[0][0] >= 92, "最新=%d" % main[0][0])

    # -----------------------------------------------------------------------
    print("\n=== G. 检测脚本自身的端口透传（防非默认端口下悄悄测错服务） ===")
    _run_all = (ROOT / "devtools" / "run_all_detection.sh").read_text(encoding="utf-8")
    _wired = [
        ("多会话隔离", 'test_sessions.py --base "$BASE"'),
        ("2D/平台 API", 'test_2d_api.py --base "$BASE"'),
        ("3D 三层", 'GGBPY_BASE="$BASE" bash devtools/run_3d_detection.sh'),
        ("2D 前端", 'GGBPY_BASE="$BASE" node devtools/verify_2d_ui_matrix.js'),
    ]
    _miss = [n for n, pat in _wired if pat not in _run_all]
    check("run_all_detection.sh 的 4 个依赖服务的步骤都透传 BASE", not _miss, str(_miss))
    _sub_ok = ("GGBPY_BASE" in (ROOT / "devtools" / "run_3d_detection.sh").read_text(encoding="utf-8")
               and "GGBPY_BASE" in (ROOT / "devtools" / "test_3d_api.py").read_text(encoding="utf-8")
               and "GGBPY_BASE" in (ROOT / "devtools" / "verify_2d_ui_matrix.js").read_text(encoding="utf-8"))
    check("子脚本确实读取 GGBPY_BASE（不是只写了文档）", _sub_ok, "")

    print("\n" + "=" * 56)
    print("代码质量策略检测：%d 项断言，%d 失败" % (ok + fail, fail))
    print("结果: " + ("ALL PASS" if fail == 0 else "FAILED"))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
