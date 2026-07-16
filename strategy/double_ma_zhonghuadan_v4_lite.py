# -*- coding: utf-8 -*-
"""
V4 Lite — V4 去掉震荡过滤（ADX + 布林带）

与 V4 的区别：
    - 移除 ADX + Bollinger 震荡过滤 → 信号更多
    - 保留：6均线、MACD、EMA50/200 趋势、分段止盈、滚仓、熔断

目的：和 V4 并行跑，对比「有震荡过滤 vs 无震荡过滤」的信号数量和胜率。
"""

from double_ma_zhonghuadan_v4 import DoubleMAZhonghuadanV4
from pandas import DataFrame


class ZengqiangShuangjunxian(DoubleMAZhonghuadanV4):
    """
    增强双均线 — MACD + EMA50/200 趋势过滤，3% 止损，分段止盈 333U
    """

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0
        dataframe.loc[:, 'enter_tag'] = ''

        # 不检查 is_choppy，其余与 V4 一致

        method_a_long = (
            dataframe['ma_congested'] &
            dataframe['above_ma20'] &
            dataframe['prev_above_ma20'] &
            dataframe['macd_cross_up'] &
            dataframe['trend_bull']
        )
        method_a_short = (
            dataframe['ma_congested'] &
            dataframe['below_ma20'] &
            dataframe['prev_below_ma20'] &
            dataframe['macd_cross_down'] &
            dataframe['trend_bear']
        )

        method_b_long = (
            dataframe['pullback_buy'] &
            dataframe['macd_cross_up'] &
            dataframe['trend_bull']
        )
        method_b_short = (
            dataframe['pullback_sell'] &
            dataframe['macd_cross_down'] &
            dataframe['trend_bear']
        )

        long_cond = method_a_long | method_b_long
        short_cond = method_a_short | method_b_short

        dataframe.loc[long_cond, 'enter_long'] = 1
        dataframe.loc[long_cond, 'enter_tag'] = '增强版做多'
        dataframe.loc[short_cond, 'enter_short'] = 1
        dataframe.loc[short_cond, 'enter_tag'] = '增强版做空'

        return dataframe
