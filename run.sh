#!/usr/bin/env bash
# ggbpy P0 —— 启动开发服务器
# 用法: ./run.sh   （默认 http://127.0.0.1:8090）
cd "$(dirname "$0")"
PORT="${PORT:-8090}"
exec python3 server/main.py --port "$PORT"
