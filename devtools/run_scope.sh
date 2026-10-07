#!/usr/bin/env bash
# **分范围检测**（迭代时用；全量 11 步是「提交前门禁」，不是每次改一行都要跑）
#
# 用法：
#   bash devtools/run_scope.sh <scope>
#
# scope 一览（按"你改了什么"选）：
#   docs     仅文档/CHANGELOG/README                → 代码质量守卫（含 CHANGELOG 批次结构）
#   registry kernel/registry.py · kernel/signatures.py → 命令注册表 + 签名表
#   kernel2d 2D 内核（commands/conics/…）            → 2D 内核矩阵
#   api2d    server/*.py 的 2D 端点                  → 2D API 矩阵（需服务）
#   ui2d     server/static/*.js|css|html（2D 前端）  → 模块边界 + 2D 前端矩阵（需服务）
#   kernel3d 3D 内核（commands3d/solids/…）          → 3D 内核矩阵
#   api3d    3D 端点                                 → 3D API 矩阵（需服务）
#   ui3d     3D 前端（render3d/scene3d/tools3d…）    → 模块边界 + 3D 浏览器矩阵（需服务）
#   core     容差/模块/会话这类"全局约束"             → 容差 + 模块边界 + 会话隔离（会话需服务）
#   quick    「改了代码但没碰 3D」的常用组合          → registry + kernel2d + core + quality
#   all      全量 11 步（= run_all_detection.sh，提交前必跑）
#
# 纪律：**迭代用小范围，提交前必须 `all` 并看到「全部检测通过」**（SOUL.md 铁律）。
set -u
. "$(dirname "$0")/_env.sh"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BASE="${GGBPY_BASE:-http://127.0.0.1:8090}"
cd "$ROOT"

ok=0; fail=0
step() {                      # step <标题> <命令...>
  local title="$1"; shift
  local t0 t1
  t0=$(date +%s.%N)
  if "$@" >/tmp/_scope_step.log 2>&1; then
    t1=$(date +%s.%N)
    ok=$((ok + 1))
    printf '  ✅ %-46s %5.1fs\n' "$title" "$(echo "$t1 - $t0" | bc)"
  else
    t1=$(date +%s.%N)
    fail=$((fail + 1))
    printf '  ❌ %-46s %5.1fs\n' "$title" "$(echo "$t1 - $t0" | bc)"
    tail -n 12 /tmp/_scope_step.log | sed 's/^/       /'
  fi
}

run_scope() {
  case "$1" in
    docs)
      step "代码质量（文档/CHANGELOG 结构守卫）" "$PY" -B devtools/test_quality.py ;;
    registry)
      step "命令注册表 + 参数签名表" "$PY" -B devtools/test_registry.py ;;
    kernel2d)
      step "2D 内核矩阵" "$PY" -B devtools/test_2d_matrix.py ;;
    api2d)
      step "2D / 平台 API 矩阵" "$PY" -B devtools/test_2d_api.py --base "$BASE" ;;
    ui2d)
      step "模块边界（前端作用域/预算）" "$PY" -B devtools/test_modules.py
      step "2D 前端浏览器矩阵" node devtools/verify_2d_ui_matrix.js ;;
    kernel3d)
      step "3D 内核矩阵" "$PY" -B devtools/test_3d_matrix.py ;;
    api3d)
      step "3D API 矩阵" "$PY" -B devtools/test_3d_api.py --base "$BASE" ;;
    ui3d)
      step "模块边界（前端作用域/预算）" "$PY" -B devtools/test_modules.py
      step "3D 浏览器矩阵" env GGBPY_BASE="$BASE" node devtools/verify_3d_ui_matrix.js ;;
    core)
      step "统一容差（零魔数/前后端一致）" "$PY" -B devtools/test_tolerance.py
      step "模块边界" "$PY" -B devtools/test_modules.py
      step "多会话隔离" "$PY" -B devtools/test_sessions.py --base "$BASE" ;;
    content2d)
      step "内容寻址仓库" "$PY" -B devtools/test_stores.py
      step "微积分/求根 smoke" "$PY" -B devtools/test_mixed_smoke.py ;;
    quick)
      run_scope registry
      run_scope kernel2d
      run_scope core
      run_scope docs ;;
    all)
      step "全量 11 步（run_all_detection.sh）" bash devtools/run_all_detection.sh
      tail -n 4 /tmp/_scope_step.log | sed 's/^/       /' ;;
    *)
      echo "未知 scope：$1"; sed -n '5,25p' "$0" | sed 's/^# \?//'; exit 2 ;;
  esac
}

echo "范围检测 scope=$1（BASE=$BASE）"
run_scope "$1"
echo "范围内步骤：通过 $ok / 失败 $fail"
[ "$fail" -eq 0 ] || exit 1
