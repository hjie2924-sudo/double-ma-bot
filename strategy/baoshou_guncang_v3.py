# -*- coding: utf-8 -*-
"""保守双均线滚仓 V3 — 15m BTC/ETH/SOL

相比 V2（过度过滤，6个月6单）：
- 回退到 V4 Lite 入场逻辑（保留 EMA50/200 趋势 + MACD，移除 ADX/BB 震荡过滤）
- 保留 V2 的金字塔比例（50%/30%，比原版 60%/40% 更安全）
- 新增：MACD 反转强制减仓
- 新增：浮盈达 2R 后启动移动止盈

优化目标：保持 20+ 交易量，胜率提升到 40%+，维持 +7% 以上收益
"""

from baoshou_guncang import BaoshouGuncang
from datetime import datetime
from freqtrade.persistence import Trade
from pandas import DataFrame
import logging

logger = logging.getLogger(__name__)


class BaoshouGuncangV3(BaoshouGuncang):
    """保守双均线滚仓 V3 — 轻过滤 + 改进风控"""

    position_adjustment_enable = True
    max_entry_position_adjustment = 2

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """继承父类指标 + 新增 MACD 反转标记"""
        dataframe = super().populate_indicators(dataframe, metadata)

        # MACD 反转：柱状图从正转负 / 负转正
        dataframe['macd_reversal_bear'] = (
            (dataframe['macdhist'] < 0) & (dataframe['macdhist'].shift(1) > 0)
        )
        dataframe['macd_reversal_bull'] = (
            (dataframe['macdhist'] > 0) & (dataframe['macdhist'].shift(1) < 0)
        )
        return dataframe

    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake, max_stake,
                              current_entry_rate, current_exit_rate,
                              current_entry_profit, current_exit_profit,
                              **kwargs):
        """金字塔滚仓 V2 比例 + MACD 反转减仓"""
        filled = trade.select_filled_orders(trade.entry_side)
        if not filled:
            return None
        total = sum(o.safe_cost for o in filled)
        nr = trade.nr_of_successful_entries

        # ── MACD 反转 → 减仓 50% ──
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if dataframe is not None and not dataframe.empty:
            last = dataframe.iloc[-1]
            if trade.is_short and last.get('macd_reversal_bull', False):
                if current_profit > 0:
                    logger.info(f"MACD反转(short→long) 减仓50% @ {current_profit:.2%}")
                    return -total * 0.5
            elif not trade.is_short and last.get('macd_reversal_bear', False):
                if current_profit > 0:
                    logger.info(f"MACD反转(long→short) 减仓50% @ {current_profit:.2%}")
                    return -total * 0.5

        # ── 止盈 4R (12%) ──
        if current_profit >= 0.12:
            logger.info(f"V3止盈4R: profit={current_profit:.2%}")
            return -total

        # ── 金字塔加仓 (V2比例: 50%/30%) ──
        if nr == 1 and current_profit >= 0.03:
            add = total * 0.5
            logger.info(f"V3滚仓#1: +{add:.2f} @ {current_profit:.2%}")
            return add
        if nr == 2 and current_profit >= 0.06:
            add = total * 0.3
            logger.info(f"V3滚仓#2: +{add:.2f} @ {current_profit:.2%}")
            return add

        return None

    def custom_stoploss(self, pair, trade, current_time, current_rate,
                        current_profit, after_fill, **kwargs):
        """移动止盈：2R后追踪到1R"""
        if current_profit >= 0.06:  # 2R → 锁定 1R
            return -0.03
        if trade.nr_of_successful_entries >= 2 and current_profit > 0.01:
            return -0.005
        return None
