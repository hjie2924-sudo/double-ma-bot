# -*- coding: utf-8 -*-
"""激进双均线宽鬆版 — 回测用，去掉趋势过滤"""

from zhonghuadan import Zhonghuadan
from pandas import DataFrame


class JijinBacktest(Zhonghuadan):
    """激进双均线宽鬆版 — 回测用，仅 MACD + 均线密集"""

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0
        dataframe.loc[:, 'enter_tag'] = ''

        # 均线密集 + MACD 金叉 → 做多
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

        # 回踩 20MA + MACD
        method_b_long = (
            dataframe['pullback_buy'] &
            dataframe['macd_cross_up']
        )
        method_b_short = (
            dataframe['pullback_sell'] &
            dataframe['macd_cross_down']
        )

        long_cond = method_a_long | method_b_long
        short_cond = method_a_short | method_b_short

        dataframe.loc[long_cond, 'enter_long'] = 1
        dataframe.loc[long_cond, 'enter_tag'] = 'long_signal'
        dataframe.loc[short_cond, 'enter_short'] = 1
        dataframe.loc[short_cond, 'enter_tag'] = 'short_signal'

        return dataframe
