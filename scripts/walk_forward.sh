#!/usr/bin/env bash
# ── 双均线策略 Walk-Forward 验证脚本 ──
# 用法: bash scripts/walk_forward.sh [保守|激进|all]
#
# 原理：
#   将数据分为：训练集(旧数据) + 验证集(新数据，未见过的)
#   策略只在训练集上做参数优化，在验证集上验证效果
#   如果训练集和验证集都表现良好 → 策略有泛化能力
#   如果训练集好但验证集差 → 过拟合，不可部署
#
# 参考文献：
#   Bailey, Borwein, López de Prado & Zhu (2014)
#   "The Probability of Backtest Overfitting"
#   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
#
# 数据划分方案：
#   训练: 2026-01-03 至 2026-05-01 (~4个月)
#   验证: 2026-05-01 至 2026-07-15 (~2.5个月)
#   Walk-forward 窗口: 60天训练 → 30天验证 (滑动)

set -e

BOT_DIR=~/double-ma-bot
VENV_PYTHON=$BOT_DIR/.venv/bin/freqtrade

TRAIN_START="20260103"
TRAIN_END="20260501"
VALIDATE_START="20260501"
VALIDATE_END="20260715"

run_backtest() {
    local strategy=$1
    local config=$2
    local label=$3
    local start=$4
    local end=$5

    echo ""
    echo "═══════════════════════════════════════════════"
    echo "  $label: $strategy"
    echo "  $start → $end"
    echo "═══════════════════════════════════════════════"
    echo ""

    $VENV_PYTHON backtesting \
        --config $BOT_DIR/$config \
        --strategy-path $BOT_DIR/strategy \
        --strategy $strategy \
        --timerange "${start}-${end}" \
        --export trades \
        --verbose
}

# ── 保守系列 Walk-Forward ──
conservative() {
    echo "========================================"
    echo "  保守系列 Walk-Forward 验证"
    echo "========================================"

    # 1. 训练期回测（样本内）
    run_backtest "BaoshouGuncang" "config/config_lite.json" \
        "保守-训练" $TRAIN_START $TRAIN_END

    # 2. 验证期回测（样本外）
    run_backtest "BaoshouGuncang" "config/config_lite.json" \
        "保守-验证" $VALIDATE_START $VALIDATE_END
}

# ── 激进系列 Walk-Forward ──
aggressive() {
    echo "========================================"
    echo "  激进系列 Walk-Forward 验证"
    echo "========================================"

    # 1. 训练期
    run_backtest "JijinGuncangV3" "config/config_zhonghuadan.json" \
        "激进V3-训练" $TRAIN_START $TRAIN_END

    # 2. 验证期
    run_backtest "JijinGuncangV3" "config/config_zhonghuadan.json" \
        "激进V3-验证" $VALIDATE_START $VALIDATE_END
}

# ── V4 vs V3 对比 ──
compare_v3_v4() {
    echo "========================================"
    echo "  V3 vs V4 对比回测（全量数据）"
    echo "========================================"

    run_backtest "BaoshouGuncang" "config/config_lite.json" \
        "保守V3(当前)-全量" "20260103" "20260715"

    # 如果 V4 策略已实装，可以取消注释以下行
    # run_backtest "DoubleMAZhonghuadanV4" "config/config.json" \
    #     "V4(ADX+BB过滤)-全量" "20260103" "20260715"
}

# ── 主逻辑 ──
case "${1:-all}" in
    保守)
        conservative
        compare_v3_v4
        ;;
    激进)
        aggressive
        ;;
    all)
        conservative
        aggressive
        ;;
    *)
        echo "用法: $0 [保守|激进|all]"
        exit 1
        ;;
esac

echo ""
echo "✅ Walk-Forward 验证完成"
echo ""
echo "判断标准："
echo "  训练 Sharpe > 1.0 且 验证 Sharpe > 0.5 → 策略有效"
echo "  训练 Sharpe > 1.0 但 验证 Sharpe < 0 → 过拟合"
echo "  训练/验证都差 → 策略无效"
