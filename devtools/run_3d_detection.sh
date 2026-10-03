#!/usr/bin/env bash
# ggbpy 3D 检测总入口：内核层 → API 层 → 浏览器层，任一层失败即非零退出。
#
# 用法:
#   bash devtools/run_3d_detection.sh              # 默认测 127.0.0.1:8090
#   PORT=8091 bash devtools/run_3d_detection.sh
#   GGBPY_BASE=http://127.0.0.1:8091 bash devtools/run_3d_detection.sh
#
# 注意: API/浏览器层测的是**运行中的服务**。服务若启动于本轮代码改动之前，
#       不会反映新行为（脚本会探测 solid 字段并明确报错）。
#       启动带新代码的实例:  PORT=8091 ./run.sh
. "$(dirname "$0")/_env.sh"
set -u

PORT="${PORT:-8090}"
BASE="${GGBPY_BASE:-http://127.0.0.1:$PORT}"
cd "$(dirname "$0")/.."

PASS_N=0
FAIL_N=0
declare -a FAILED_STEPS=()

banner() { printf '\n\033[1m==== %s ====\033[0m\n' "$1"; }

step() {                                  # step <名称> <命令...>
  local name="$1"; shift
  banner "$name"
  if "$@"; then
    PASS_N=$((PASS_N + 1))
    printf '\033[32m[OK]\033[0m %s\n' "$name"
  else
    FAIL_N=$((FAIL_N + 1))
    FAILED_STEPS+=("$name")
    printf '\033[31m[FAIL]\033[0m %s\n' "$name"
  fi
}

# ---- 0. 服务可用性（仅 API/浏览器层需要）----
banner "0. 服务探测 $BASE"
HTTP=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$BASE/" 2>/dev/null || echo 000)
if [ "$HTTP" != "200" ]; then
  printf '\033[31m服务不可达 (HTTP %s)\033[0m\n' "$HTTP"
  echo "请先启动：PORT=$PORT ./run.sh   （注意：改动内核后必须重启服务）"
  exit 2
fi
echo "服务可达 (HTTP 200)"

# ---- 1. 内核层 ----
step "1/5 内核 3D 检测矩阵" "$PY" -B devtools/test_3d_matrix.py
step "2/5 内核 3D 生成回归" "$PY" -B devtools/test_3d_generation_kernel.py
step "3/5 内核 圆柱/退化回归" "$PY" -B devtools/test_cylinder_kernel.py
"$PY" -B devtools/test_3d_degenerate.py >/dev/null && echo "  (degenerate 探针 OK)" || true

# ---- 2. API 层 ----
step "4/5 API 3D 检测矩阵" "$PY" -B devtools/test_3d_api.py --base "$BASE"

# ---- 3. 浏览器层 ----
step "5/5 浏览器 3D 检测矩阵" env GGBPY_BASE="$BASE" node devtools/verify_3d_ui_matrix.js

# ---- 汇总 ----
banner "汇总"
printf '通过步骤: %d   失败步骤: %d\n' "$PASS_N" "$FAIL_N"
if [ "$FAIL_N" -ne 0 ]; then
  for s in "${FAILED_STEPS[@]}"; do printf '  FAILED: %s\n' "$s"; done
  exit 1
fi
echo "全部 3D 检测通过 ✅"
