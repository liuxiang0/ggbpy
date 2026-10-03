#!/usr/bin/env bash
# ggbpy P0 —— 启动开发服务器
# 用法: ./run.sh   （默认 http://127.0.0.1:8090）
cd "$(dirname "$0")"
PORT="${PORT:-8090}"
# 自动挑选可用的 python3（系统 3.12 有 numpy/sympy；若 PATH 指向无三方库的 venv 会失败）
. "$(dirname "$0")/devtools/_env.sh"
echo "ggbpy: 使用 $PY ($("$PY" -c 'import sys;print(sys.version.split()[0])'))"
exec "$PY" server/main.py --port "$PORT"
