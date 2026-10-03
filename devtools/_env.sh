# 通用环境助手：挑选「能 import numpy/sympy」的 python3
# 背景：机器上可能存在多个解释器（系统 3.12 有三方库、某些 venv 没有），
# 若 PATH 里的 python3 恰好是无三方库的那个，服务与检测会直接失败。
# 用法：. "$(dirname "$0")/devtools/_env.sh"  → 之后用 "$PY"
pick_python() {
  if [ -n "${GGBPY_PY:-}" ]; then echo "$GGBPY_PY"; return; fi
  for c in python3 /usr/bin/python3 python3.12 /usr/bin/python3.12; do
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c "import numpy, sympy" >/dev/null 2>&1; then echo "$c"; return; fi
  done
  echo python3
}
PY="$(pick_python)"
export PY
