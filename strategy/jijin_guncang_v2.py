# -*- coding: utf-8 -*-
"""激进双均线滚仓-15m-BTC/ETH/SOL

基于回测教训 + 文献优化：
- 止损 2%（原 1% 太紧被噪音扫，提到 2% 给滚仓留空间）
- 均线密集阈值 2%
- 加 EMA50/200 趋势过滤（砍掉逆势噪音单）
- 加 ADX 震荡过滤（避开横盘）
- 金字塔加仓：100% → 50% → 30%
- 止盈：4R（8%）全部离场
"""

from double_ma_zhonghuadan_v4 import DoubleMAZhonghuadanV4
from freqtrade.strategy import DecimalParameter, IntParameter
from pandas import DataFrame
from datetime import datetime
from freqtrade.persistence import Trade
import logging

logger = logging.getLogger(__name__)


class JijinGuncangV2(DoubleMAZhonghuadanV4):
    """激进双均线滚仓优化版"""

    stoploss = -0.02  # 2% 止损（原 1%）
    use_custom_stoploss = True
    position_adjustment_enable = True
    max_entry_position_adjustment = 2

    congestion_threshold = DecimalParameter(
        0.01, 0.04, default=0.02, decimals=4, space='buy', optimize=True
    )
    adx_threshold = IntParameter(15, 30, default=20, space='buy')

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0
        dataframe.loc[:, 'enter_tag'] = ''

        not_choppy = ~dataframe['is_choppy']

        # 方法 A: 均线密集突破
        long_a = (
            dataframe['ma_congested'] & dataframe['above_ma20'] &
            dataframe['prev_above_ma20'] & dataframe['macd_cross_up'] &
            not_choppy
        )
        short_a = (
            dataframe['ma_congested'] & dataframe['below_ma20'] &
            dataframe['prev_below_ma20'] & dataframe['macd_cross_down'] &
            not_choppy
        )
        # 方法 B: 回踩 20MA
        long_b = (
            dataframe['pullback_buy'] & dataframe['macd_cross_up'] &
            not_choppy
        )
        short_b = (
            dataframe['pullback_sell'] & dataframe['macd_cross_down'] &
            not_choppy
        )

        dataframe.loc[long_a | long_b, 'enter_long'] = 1
        dataframe.loc[long_a | long_b, 'enter_tag'] = 'long'
        dataframe.loc[short_a | short_b, 'enter_short'] = 1
        dataframe.loc[short_a | short_b, 'enter_tag'] = 'short'

        return dataframe

    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake, max_stake,
                              current_entry_rate, current_exit_rate,
                              current_entry_profit, current_exit_profit,
                              **kwargs):
        """金字塔滚仓 + 分段止盈"""
        filled = trade.select_filled_orders(trade.entry_side)
        if not filled:
            return None
        total = sum(o.safe_cost for o in filled)
        nr = trade.nr_of_successful_entries

        # 止盈 4R (8%) 全部离场
        if current_profit >= 0.08:
            return -total

        # 金字塔加仓（递減）
        # 1R = 1%  → 第一个目标 2%（给滚仓启动空间）
        if nr == 1 and current_profit >= 0.02:
            add = total * 0.5
            return add
        if nr == 2 and current_profit >= 0.04:
            add = total * 0.3
            return add

        return None

    def custom_stoploss(self, pair, trade, current_time, current_rate,
                        current_profit, after_fill, **kwargs):
        if trade.nr_of_successful_entries >= 2 and current_profit > 0.005:
            return -0.003
        return None

    def custom_stake_amount(self, pair, current_time, current_rate,
                            proposed_stake, min_stake, max_stake,
                            entry_tag, side, **kwargs):
        wallet = self.wallets.get_total_stake_amount()
        return min(wallet * 0.10 / abs(self.stoploss), max_stake)
