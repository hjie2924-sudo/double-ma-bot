# -*- coding: utf-8 -*-
"""
双均线中华单策略 v3-4H — 4 小时级别版

与 15 分钟版逻辑一致，但针对 4H 级别调整默认参数：
    - 均线密集阈值: 4%（4H 级别波动大，放宽）
    - 止损: 5%（4H 级别正常波动范围）
    - MACD: 标准 12/26/9
    - 趋势过滤: EMA 50/200

v3 核心设计：
    1. 均线密集 = 入场前提
    2. K 线连续 2 根确认（避免假突破）
    3. MACD 金叉/死叉 必要条件
    4. 顺 EMA50/200 大趋势
    5. 出场：均线排列反转 / 趋势反转 / K 线破位
"""

import talib.abstract as ta
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from pandas import DataFrame


class DoubleMAZhonghuadanV3_4H(IStrategy):
    """
    双均线中华单 v3 — 4 小时级别

    推荐配置：
        timeframe = '4h'
        startup_candle_count = 200
        stoploss = -0.05
    """

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = '4h'
    startup_candle_count = 200

    minimal_roi = {"0": 1.0}
    stoploss = -0.05
    use_custom_stoploss = False

    # ── 可调参数（4H 级别大幅放宽） ──────
    congestion_threshold = DecimalParameter(
        0.04, 0.15, default=0.08, decimals=4,
        space='buy', optimize=True
    )

    macd_fast = IntParameter(10, 16, default=12, space='buy')
    macd_slow = IntParameter(24, 32, default=26, space='buy')
    macd_signal = IntParameter(7, 13, default=9, space='buy')

    # ── 指标 ────────────────────────────────────────

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 6 条均线
        for period in [20, 60, 120]:
            dataframe[f'ma{period}'] = ta.SMA(dataframe, timeperiod=period)
            dataframe[f'ema{period}'] = ta.EMA(dataframe, timeperiod=period)

        # 趋势过滤
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)

        # MACD
        macd = ta.MACD(
            dataframe,
            fastperiod=self.macd_fast.value,
            slowperiod=self.macd_slow.value,
            signalperiod=self.macd_signal.value,
        )
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']

        # 均线密集
        dataframe['ma_spread'] = (
            abs(dataframe['ma20'] - dataframe['ma120']) / dataframe['ma120'] * 100
        )
        dataframe['ma_congested'] = (
            dataframe['ma_spread'] < self.congestion_threshold.value
        )

        # MACD 交叉（金叉/死叉）
        dataframe['macd_cross_up'] = (
            (dataframe['macdhist'] > 0) & (dataframe['macdhist'].shift(1) <= 0)
        )
        dataframe['macd_cross_down'] = (
            (dataframe['macdhist'] < 0) & (dataframe['macdhist'].shift(1) >= 0)
        )

        # 趋势
        dataframe['trend_bull'] = dataframe['ema50'] > dataframe['ema200']
        dataframe['trend_bear'] = dataframe['ema50'] < dataframe['ema200']

        # 价格位置
        dataframe['above_ma20'] = dataframe['close'] > dataframe['ma20']
        dataframe['below_ma20'] = dataframe['close'] < dataframe['ma20']

        # 均线排列
        dataframe['ma_bullish'] = (
            (dataframe['ma20'] > dataframe['ma60']) &
            (dataframe['ma60'] > dataframe['ma120'])
        )
        dataframe['ma_bearish'] = (
            (dataframe['ma120'] > dataframe['ma60']) &
            (dataframe['ma60'] > dataframe['ma20'])
        )

        # 前一根 K 线确认
        dataframe['prev_above_ma20'] = dataframe['close'].shift(1) > dataframe['ma20'].shift(1)
        dataframe['prev_below_ma20'] = dataframe['close'].shift(1) < dataframe['ma20'].shift(1)

        return dataframe

    # ── 入场 ────────────────────────────────────────

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0

        # 做多：密集 + K>MA20 + MACD方向确认（4H 级别不用趋势过滤，熊市会杀光信号）
        long_conditions = (
            dataframe['ma_congested'] &
            dataframe['above_ma20'] &
            (dataframe['macd'] > dataframe['macdsignal'])
        )
        dataframe.loc[long_conditions, 'enter_long'] = 1

        # 做空：密集 + K<MA20 + MACD方向确认
        short_conditions = (
            dataframe['ma_congested'] &
            dataframe['below_ma20'] &
            (dataframe['macd'] < dataframe['macdsignal'])
        )
        dataframe.loc[short_conditions, 'enter_short'] = 1

        return dataframe

    # ── 出场 ────────────────────────────────────────

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'exit_long'] = 0
        dataframe.loc[:, 'exit_short'] = 0

        exit_long = (
            dataframe['ma_bearish'] |
            (dataframe['macd'] < dataframe['macdsignal']) |
            (dataframe['below_ma20'] & dataframe['prev_below_ma20'])
        )
        dataframe.loc[exit_long, 'exit_long'] = 1

        exit_short = (
            dataframe['ma_bullish'] |
            (dataframe['macd'] > dataframe['macdsignal']) |
            (dataframe['above_ma20'] & dataframe['prev_above_ma20'])
        )
        dataframe.loc[exit_short, 'exit_short'] = 1

        return dataframe
