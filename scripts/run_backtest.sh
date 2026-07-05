#!/bin/bash
# 运行回测
# 用法: bash scripts/run_backtest.sh [时间级别] [开始日期] [结束日期]

TIMEFRAME=${1:-"15m"}
START=${2:-"$(date -d '90 days ago' +%Y%m%d)"}
END=${3:-"$(date +%Y%m%d)"}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

source "$PROJECT_DIR/.venv/bin/activate"

echo "🔬 回测配置:"
echo "   策略: DoubleMAZhonghuadan"
echo "   时间级别: $TIMEFRAME"
echo "   时间范围: $START → $END"
echo ""

freqtrade backtesting \
    --config "$PROJECT_DIR/config/config.json" \
    --strategy DoubleMAZhonghuadan \
    --timeframe "$TIMEFRAME" \
    --timerange "${START}-${END}" \
    --data-dir "$PROJECT_DIR/data" \
    2>&1

echo ""
echo "回测完成。"
