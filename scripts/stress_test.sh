#!/bin/bash

# 压测脚本封装 (Wrapper for stress_test_quota.py)
# Usage: ./stress_test.sh <api_key> [qpm] [concurrency] [duration] [model] [url]

# 默认值配置
DEFAULT_URL="https://www.ezmodel.cloud/v1"
DEFAULT_QPM=800
DEFAULT_CONCURRENCY=20
DEFAULT_DURATION=120
DEFAULT_MODEL="grok-3-mini"

# 参数处理
API_KEY=$1
QPM=${2:-$DEFAULT_QPM}
CONCURRENCY=${3:-$DEFAULT_CONCURRENCY}
DURATION=${4:-$DEFAULT_DURATION}
MODEL=${5:-$DEFAULT_MODEL}
URL=${6:-$DEFAULT_URL}

# 帮助/错误检查
if [ -z "$API_KEY" ]; then
    echo "Usage: $0 <api_key> [qpm] [concurrency] [duration] [model] [url]"
    echo ""
    echo "Examples:"
    echo "  $0 sk-123456"
    echo "  $0 sk-123456 120 20"
    echo "  $0 sk-123456 600 50 60 gpt-4"
    exit 1
fi

# 获取当前脚本所在目录，确保能找到 python 脚本
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PYTHON_SCRIPT="$SCRIPT_DIR/stress_test_quota.py"

# 检查 Python 环境
PYTHON_CMD="python"
if ! command -v python &> /dev/null; then
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    else
        echo "Error: Python is not installed or not in PATH."
        exit 1
    fi
fi

echo "----------------------------------------------------------------"
echo "Starting Stress Test via Shell Wrapper"
echo "Target:      $URL"
echo "API Key:     ${API_KEY:0:8}..."
echo "QPM:         $QPM"
echo "Concurrency: $CONCURRENCY"
echo "Duration:    $DURATION s"
echo "Model:       $MODEL"
echo "Script:      $PYTHON_SCRIPT"
echo "----------------------------------------------------------------"

# 执行 Python 脚本
"$PYTHON_CMD" "$PYTHON_SCRIPT" \
  --url "$URL" \
  --key "$API_KEY" \
  --qpm "$QPM" \
  --concurrency "$CONCURRENCY" \
  --duration "$DURATION" \
  --model "$MODEL"