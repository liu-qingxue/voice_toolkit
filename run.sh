#!/bin/bash
# 获取脚本所在目录（即项目根目录）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 虚拟环境中的 Python 解释器（优先使用 python3.12，否则回退到 python）
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3.12"
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
fi

# 检查虚拟环境是否存在
if [ ! -f "$VENV_PYTHON" ]; then
    echo "错误: 未找到虚拟环境 Python，请确认 venv/ 目录存在" >&2
    exit 1
fi

# 执行你的脚本（传递所有参数）
exec "$VENV_PYTHON" "$SCRIPT_DIR/live/toggle.py" "$@"