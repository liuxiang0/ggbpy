#!/usr/bin/env bash
# ggbpy 全量检测：2D 内核矩阵 + 2D/平台 API 矩阵 + 3D 三层矩阵（内核/API/浏览器）
# 用法：bash devtools/run_all_detection.sh [BASE]
#   默认 BASE=http://127.0.0.1:8090（需先启动服务：PORT=8090 ./run.sh）
. "$(dirname "$0")/_env.sh"
set -u
BASE="${1:-http://127.0.0.1:8090}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
ok_steps=0
fail_steps=0

step() {
  local title="$1"; shift
  echo ""
  echo "==================================================================="
  echo "▶ $title"
  echo "==================================================================="
  if "$@"; then
    echo "✅ $title"
    ok_steps=$((ok_steps + 1))
  else
    echo "❌ $title"
    fail_steps=$((fail_steps + 1))
  fi
}

cd "$ROOT"
step "1/11 命令注册表一致性" "$PY" -B devtools/test_registry.py
step "2/11 内容寻址仓库检测" "$PY" -B devtools/test_stores.py
step "3/11 统一容差检测（零魔数/前后端一致）" "$PY" -B devtools/test_tolerance.py
step "4/11 模块边界检测（内核拆分/前端文案外置）" "$PY" -B devtools/test_modules.py
step "5/11 多会话隔离检测" "$PY" -B devtools/test_sessions.py --base "$BASE"
step "6/11 2D 内核检测矩阵" "$PY" -B devtools/test_2d_matrix.py
step "7/11 2D/平台 API 检测矩阵" "$PY" -B devtools/test_2d_api.py --base "$BASE"
step "8/11 3D 三层检测矩阵（内核/API/浏览器）" bash devtools/run_3d_detection.sh
step "9/11 2D 前端回归矩阵（编辑栏/CAS/分享/图片/导出/工具）" node devtools/verify_2d_ui_matrix.js
step "10/11 微积分/求根回归" "$PY" -B devtools/test_mixed_smoke.py 2>/dev/null || true
step "11/11 代码质量策略检测（宽泛捕获说明/预算/收窄抽查/文档批次完整性）" "$PY" -B devtools/test_quality.py

echo ""
echo "==================================================================="
echo "通过步骤: $ok_steps   失败步骤: $fail_steps"
if [ "$fail_steps" -eq 0 ]; then
  echo "全部检测通过 ✅"
  exit 0
fi
echo "存在失败 ❌"
exit 1
