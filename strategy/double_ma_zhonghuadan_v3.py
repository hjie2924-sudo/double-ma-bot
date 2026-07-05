# -*- coding: utf-8 -*-
"""
双均线短线突破策略策略 v3 — Freqtrade 版

v3 策略（v1+v2 折中）：
    基于 v1 回测盈利 (+2.63%, Sharpe 1.09) 的逻辑骨架，
    吸取 v2 的教训（条件过松导致胜率崩溃），
    微调参数找到信号数量与质量的平衡点。

关键变化：
    1. 均线密集阈值: 2.5%（v1=2% 太少, v2=4% 太多）
    2. 止损: 3%（v1=5% 太宽, v2=2% 太窄）
    3. 保留 MACD 交叉确认（v1 的正确设计）
    4. 入场需 K 线收盘确认（避免盘中假突破）
    5. 出场加均线重新发散判断
"""

import talib.abstract as ta
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from pandas import DataFrame


class DoubleMAZhonghuadanV3(IStrategy):
    """
    双均线短线突破策略 v3 — 平衡版

    推荐配置：
        timeframe = '15m'
        startup_candle_count = 200
        stoploss = -0.03
    """

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = '15m'
    startup_candle_count = 200

    minimal_roi = {"0": 1.0}
    stoploss = -0.03
    use_custom_stoploss = False

    # ── 可调参数 ────────────────────────────────────
    congestion_threshold = DecimalParameter(
        0.015, 0.05, default=0.025, decimals=4,
        space='buy', optimize=True
    )

    macd_fast = IntParameter(10, 14, default=12, space='buy')
    macd_slow = IntParameter(24, 30, default=26, space='buy')
    macd_signal = IntParameter(7, 11, default=9, space='buy')

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

        # 价格位置（用收盘价，不是实时价）
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

        # 前一根 K 线也在 MA20 上方（确认突破有效）
        dataframe['prev_above_ma20'] = dataframe['close'].shift(1) > dataframe['ma20'].shift(1)
        dataframe['prev_below_ma20'] = dataframe['close'].shift(1) < dataframe['ma20'].shift(1)

        return dataframe

    # ── 入场 ────────────────────────────────────────

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0

        # 做多：密集 + K>MA20(连续2根) + MACD金叉 + 多头趋势
        long_conditions = (
            dataframe['ma_congested'] &
            dataframe['above_ma20'] &
            dataframe['prev_above_ma20'] &
            dataframe['macd_cross_up'] &
            dataframe['trend_bull']
        )
        dataframe.loc[long_conditions, 'enter_long'] = 1

        # 做空：密集 + K<MA20(连续2根) + MACD死叉 + 空头趋势
        short_conditions = (
            dataframe['ma_congested'] &
            dataframe['below_ma20'] &
            dataframe['prev_below_ma20'] &
            dataframe['macd_cross_down'] &
            dataframe['trend_bear']
        )
        dataframe.loc[short_conditions, 'enter_short'] = 1

        return dataframe

    # ── 出场 ────────────────────────────────────────

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'exit_long'] = 0
        dataframe.loc[:, 'exit_short'] = 0

        # 平多条件
        exit_long = (
            dataframe['ma_bearish'] |
            # 趋势反转为空头
            (dataframe['trend_bear'] & dataframe['macd_cross_down']) |
            # K线跌破 MA20
            (dataframe['below_ma20'] & dataframe['prev_below_ma20'])
        )
        dataframe.loc[exit_long, 'exit_long'] = 1

        # 平空条件
        exit_short = (
            dataframe['ma_bullish'] |
            (dataframe['trend_bull'] & dataframe['macd_cross_up']) |
            (dataframe['above_ma20'] & dataframe['prev_above_ma20'])
        )
        dataframe.loc[exit_short, 'exit_short'] = 1

        return dataframe
