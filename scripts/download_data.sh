#!/bin/bash
# 下载历史 K 线数据用于回测
# 用法: bash scripts/download_data.sh [时间级别] [天数]

TIMEFRAME=${1:-"15m"}
DAYS=${2:-90}
PAIRS=("BTC/USDT:USDT" "ETH/USDT:USDT" "SOL/USDT:USDT")

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_DIR/data"

source "$PROJECT_DIR/.venv/bin/activate"

mkdir -p "$DATA_DIR"

echo "📥 下载 $TIMEFRAME K 线数据，回溯 ${DAYS} 天..."
echo ""

for PAIR in "${PAIRS[@]}"; do
    PAIR_SAFE=$(echo "$PAIR" | tr '/' '_' | tr ':' '_')
    echo "  下载 $PAIR ..."
    
    freqtrade download-data \
        --config "$PROJECT_DIR/config/config.json" \
        --timeframe "$TIMEFRAME" \
        --timerange "${DAYS}d" \
        --pairs "$PAIR" \
        --data-dir "$DATA_DIR" \
        --exchange okx \
        2>&1 | tail -3
    
    echo "  ✅ $PAIR 完成"
    echo ""
done

echo "🎉 全部数据下载完成！"
echo "数据目录: $DATA_DIR"
ls -lh "$DATA_DIR"/okx/
