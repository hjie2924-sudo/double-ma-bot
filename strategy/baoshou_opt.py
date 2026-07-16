# -*- coding: utf-8 -*-
"""保守双均线 — 回测优化版
基于 BaoshouBacktest，优化：
- 止损 2%（原 3%）
- 止盈 4%/8%（调整分段）
- 去掉趋势过滤（12天回测已证明趋势过滤是信号杀手）
- 密集阈值 5%
"""

from double_ma_zhonghuadan_v4 import DoubleMAZhonghuadanV4
from freqtrade.strategy import DecimalParameter
from pandas import DataFrame
from datetime import datetime
from freqtrade.persistence import Trade
import logging

logger = logging.getLogger(__name__)


class BaoshouOpt(DoubleMAZhonghuadanV4):
    """保守双均线优化版"""

    stoploss = -0.02  # 2% 止损
    position_adjustment_enable = True
    max_entry_position_adjustment = 0  # 先不加仓

    congestion_threshold = DecimalParameter(
        0.03, 0.08, default=0.05, decimals=4, space='buy', optimize=True
    )

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0
        dataframe.loc[:, 'enter_tag'] = ''

        # 方法 A + B，仅 MACD 确认
        method_a_long = (
            dataframe['ma_congested'] &
            dataframe['above_ma20'] &
            dataframe['prev_above_ma20'] &
            dataframe['macd_cross_up']
        )
        method_a_short = (
            dataframe['ma_congested'] &
            dataframe['below_ma20'] &
            dataframe['prev_below_ma20'] &
            dataframe['macd_cross_down']
        )
        method_b_long = dataframe['pullback_buy'] & dataframe['macd_cross_up']
        method_b_short = dataframe['pullback_sell'] & dataframe['macd_cross_down']

        dataframe.loc[method_a_long | method_b_long, 'enter_long'] = 1
        dataframe.loc[method_a_long | method_b_long, 'enter_tag'] = 'long'
        dataframe.loc[method_a_short | method_b_short, 'enter_short'] = 1
        dataframe.loc[method_a_short | method_b_short, 'enter_tag'] = 'short'

        return dataframe

    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake, max_stake,
                              current_entry_rate, current_exit_rate,
                              current_entry_profit, current_exit_profit,
                              **kwargs):
        """分段止盈: 盈利 4% 平一半，8% 平全部"""
        if trade.nr_of_successful_entries > 1:
            return None
        filled = trade.select_filled_orders(trade.entry_side)
        if not filled:
            return None
        total = sum(o.safe_cost for o in filled)
        if current_profit >= 0.04:
            return -total * 0.5
        if current_profit >= 0.08:
            return -total * 0.5
        return None

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, entry_tag, side, **kwargs):
        wallet = self.wallets.get_total_stake_amount()
        position = wallet * 0.10 / abs(self.stoploss)  # 10% 本金冒险
        return min(position, max_stake)
