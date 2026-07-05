# -*- coding: utf-8 -*-
"""
双均线短线突破策略策略 v2 — Freqtrade 版

v2 改进（基于首次回测反馈）：
    1. 均线密集阈值 2% → 4%（缓解"太挑食"）
    2. 入场简化：K线>MA20 + 均线密集 + 趋势同向（不需要MACD金叉同步）
    3. 止损 5% → 2%（适配15分钟级别）
    4. 增加波动率过滤器
    5. MACD作为加分项而非必要条件

策略逻辑：
    做多：均线密集 + K线在MA20上方 + EMA50>EMA200 + MACD>0
    做空：均线密集 + K线在MA20下方 + EMA50<EMA200 + MACD<0
"""

from functools import reduce
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from pandas import DataFrame
import pandas as pd


class DoubleMAZhonghuadanV2(IStrategy):
    """
    双均线短线突破策略 v2 — 放宽条件 + 降低止损
    
    推荐配置：
        timeframe = '15m'
        startup_candle_count = 200
        stoploss = -0.02  # 2% 硬止损
    """

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = '15m'
    startup_candle_count = 200

    minimal_roi = {"0": 1.0}
    stoploss = -0.02
    use_custom_stoploss = False

    # ── 可调参数 ────────────────────────────────────
    # 均线密集阈值（放宽到 4%）
    congestion_threshold = DecimalParameter(
        0.02, 0.08, default=0.04, decimals=3,
        space='buy', optimize=True
    )

    # 最小 ATR 波动（避免死鱼行情）
    min_atr_pct = DecimalParameter(
        0.001, 0.01, default=0.003, decimals=4,
        space='buy', optimize=True
    )

    # ── 指标 ────────────────────────────────────────

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 均线
        dataframe['ma20'] = ta.SMA(dataframe, timeperiod=20)
        dataframe['ma60'] = ta.SMA(dataframe, timeperiod=60)
        dataframe['ma120'] = ta.SMA(dataframe, timeperiod=120)
        dataframe['ema20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema60'] = ta.EMA(dataframe, timeperiod=60)
        dataframe['ema120'] = ta.EMA(dataframe, timeperiod=120)
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)

        # MACD
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']

        # ATR
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']

        # 均线密集判断（MA20-MA120 价差 < 阈值）
        dataframe['ma_spread'] = (
            abs(dataframe['ma20'] - dataframe['ma120']) / dataframe['ma120'] * 100
        )
        dataframe['ma_congested'] = (
            dataframe['ma_spread'] < self.congestion_threshold.value
        )

        # MACD 金叉/死叉（加分项，非必需）
        dataframe['macd_cross_up'] = (
            (dataframe['macdhist'] > 0) & (dataframe['macdhist'].shift(1) <= 0)
        )
        dataframe['macd_cross_down'] = (
            (dataframe['macdhist'] < 0) & (dataframe['macdhist'].shift(1) >= 0)
        )

        # 趋势方向
        dataframe['trend_bull'] = dataframe['ema50'] > dataframe['ema200']
        dataframe['trend_bear'] = dataframe['ema50'] < dataframe['ema200']

        # 简化价格位置判断
        dataframe['above_ma20'] = dataframe['close'] > dataframe['ma20']
        dataframe['below_ma20'] = dataframe['close'] < dataframe['ma20']

        # 多头/空头排列
        dataframe['ma_bullish'] = (
            (dataframe['ma20'] > dataframe['ma60']) &
            (dataframe['ma60'] > dataframe['ma120'])
        )
        dataframe['ma_bearish'] = (
            (dataframe['ma120'] > dataframe['ma60']) &
            (dataframe['ma60'] > dataframe['ma20'])
        )

        # 波动率足够
        dataframe['enough_volatility'] = (
            dataframe['atr_pct'] > self.min_atr_pct.value
        )

        return dataframe

    # ── 入场 ────────────────────────────────────────

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0

        # 做多：均线密集 + K>MA20 + 多头趋势 + MACD>0 + 有波动
        long_conditions = (
            dataframe['ma_congested'] &
            dataframe['above_ma20'] &
            dataframe['trend_bull'] &
            (dataframe['macd'] > 0) &
            dataframe['enough_volatility']
        )
        dataframe.loc[long_conditions, 'enter_long'] = 1

        # 做空：均线密集 + K<MA20 + 空头趋势 + MACD<0 + 有波动
        short_conditions = (
            dataframe['ma_congested'] &
            dataframe['below_ma20'] &
            dataframe['trend_bear'] &
            (dataframe['macd'] < 0) &
            dataframe['enough_volatility']
        )
        dataframe.loc[short_conditions, 'enter_short'] = 1

        return dataframe

    # ── 出场 ────────────────────────────────────────

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'exit_long'] = 0
        dataframe.loc[:, 'exit_short'] = 0

        # 平多：转为空头排列
        exit_long = (
            dataframe['ma_bearish'] |
            dataframe['trend_bear'] |
            dataframe['below_ma20']
        )
        dataframe.loc[exit_long, 'exit_long'] = 1

        # 平空：转为多头排列
        exit_short = (
            dataframe['ma_bullish'] |
            dataframe['trend_bull'] |
            dataframe['above_ma20']
        )
        dataframe.loc[exit_short, 'exit_short'] = 1

        return dataframe
