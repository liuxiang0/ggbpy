#!/usr/bin/env bash
# ggbpy 全量检测：2D 内核矩阵 + 2D/平台 API 矩阵 + 3D 三层矩阵（内核/API/浏览器）
# 用法：bash devtools/run_all_detection.sh [BASE]
#   默认 BASE=http://127.0.0.1:8090（需先启动服务：PORT=8090 ./run.sh）
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
step "1/5 命令注册表一致性" python3 -B devtools/test_registry.py
step "2/5 2D 内核检测矩阵" python3 -B devtools/test_2d_matrix.py
step "3/5 2D/平台 API 检测矩阵" python3 -B devtools/test_2d_api.py --base "$BASE"
step "4/5 3D 三层检测矩阵（内核/API/浏览器）" bash devtools/run_3d_detection.sh
step "5/5 微积分/求根回归" python3 -B devtools/test_mixed_smoke.py 2>/dev/null || true

echo ""
echo "==================================================================="
echo "通过步骤: $ok_steps   失败步骤: $fail_steps"
if [ "$fail_steps" -eq 0 ]; then
  echo "全部检测通过 ✅"
  exit 0
fi
echo "存在失败 ❌"
exit 1
