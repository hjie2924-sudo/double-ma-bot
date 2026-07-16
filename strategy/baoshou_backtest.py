# -*- coding: utf-8 -*-
"""回测用宽鬆版 — 去掉趋势过滤，放宽密集阈值"""

from double_ma_zhonghuadan_v4_lite import ZengqiangShuangjunxian
from freqtrade.strategy import DecimalParameter
from pandas import DataFrame


class BaoshouBacktest(ZengqiangShuangjunxian):
    """保守双均线宽鬆版 — 回测用"""

    # 放宽密集阈值到 5%
    congestion_threshold = DecimalParameter(
        0.02, 0.08, default=0.05, decimals=4, space='buy', optimize=True
    )

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0
        dataframe.loc[:, 'enter_tag'] = ''

        # 方法 A：均线密集突破（去掉趋势过滤）
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

        # 方法 B：回踩 20MA
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
