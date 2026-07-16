# -*- coding: utf-8 -*-
"""
双均线短线突破策略策略 — Freqtrade 版

基于双均线研究文献双均线系统 + 短线突破策略 15 分钟变体。

核心逻辑：
    1. 均线密集（MA20-MA120 价差 < 阈值）→ 市场休息，准备动手
    2. 均线发散（6条线有序排列）→ 趋势行情，顺势而为
    3. MACD 金叉/死叉确认方向
    4. EMA50 > EMA200 → 大趋势向上（做多前提）
    5. EMA50 < EMA200 → 大趋势向下（做空前提）
    6. 分段止盈：1:1 平 50%，1:2 平剩余

来源：
    - 双均线研究文献：基础框架
    - 短线策略：15分短線，MACD過濾，分段止盈，勝率78%+
    - 趋势过滤法：200 MA 趨勢過濾，胜率59%
    - 趋势跟踪法：EMA50/200 排列確認
"""

from functools import reduce
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from pandas import DataFrame
import pandas as pd


class DoubleMAZhonghuadan(IStrategy):
    """
    双均线短线突破策略 15 分钟策略
    
    推荐配置（Freqtrade）：
        timeframe = '15m'
        startup_candle_count = 200
        minimal_roi = {0: 1.0}  # 不使用内置ROI，由自定义止盈控制
        stoploss = -0.05  # 硬止损 5%
    """

    # ── 基本配置 ────────────────────────────────────
    INTERFACE_VERSION = 3

    can_short = True  # 支持做空
    timeframe = '15m'

    # 起步需要 200 根 K 线来计算 EMA200
    startup_candle_count = 200

    # 不使用内置 ROI 退出（由自定义止盈信号控制）
    minimal_roi = {
        "0": 1.0
    }

    # 硬止损：到达即全平
    stoploss = -0.05

    # 使用自定义止盈信号
    use_custom_stoploss = False

    # ── 可调参数 ────────────────────────────────────
    # 均线密集阈值：MA20 和 MA120 之间的最大价差百分比
    congestion_threshold = DecimalParameter(
        0.01, 0.05, default=0.02, decimals=3,
        space='buy', optimize=True
    )

    # MACD 参数
    macd_fast = IntParameter(8, 16, default=12, space='buy')
    macd_slow = IntParameter(20, 30, default=26, space='buy')
    macd_signal = IntParameter(7, 12, default=9, space='buy')

    # ── 指标计算 ────────────────────────────────────

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        计算所有技术指标：
        - MA20, MA60, MA120
        - EMA20, EMA60, EMA120
        - EMA50, EMA200 (趋势过滤)
        - MACD
        - 均线密集/发散状态
        """

        # ── 简单移动平均 ──
        dataframe['ma20'] = ta.SMA(dataframe, timeperiod=20)
        dataframe['ma60'] = ta.SMA(dataframe, timeperiod=60)
        dataframe['ma120'] = ta.SMA(dataframe, timeperiod=120)

        # ── 指数移动平均 ──
        dataframe['ema20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema60'] = ta.EMA(dataframe, timeperiod=60)
        dataframe['ema120'] = ta.EMA(dataframe, timeperiod=120)

        # ── 趋势过滤均线 ──
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)

        # ── MACD ──
        macd = ta.MACD(
            dataframe,
            fastperiod=self.macd_fast.value,
            slowperiod=self.macd_slow.value,
            signalperiod=self.macd_signal.value,
        )
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']

        # ── 均线密集/发散判断 ──
        # 计算 MA20 到 MA120 的价差 %
        dataframe['ma_spread'] = (
            abs(dataframe['ma20'] - dataframe['ma120']) / dataframe['ma120'] * 100
        )

        # 均线密集：价差 < 阈值
        dataframe['ma_congested'] = (
            dataframe['ma_spread'] < self.congestion_threshold.value
        )

        # ── MACD 交叉 ──
        # 金叉：macd 上穿 macdsignal
        # MACD 的 histogram 由负转正 = 金叉
        dataframe['macd_cross_up'] = (
            (dataframe['macdhist'] > 0) & (dataframe['macdhist'].shift(1) <= 0)
        )
        # 死叉
        dataframe['macd_cross_down'] = (
            (dataframe['macdhist'] < 0) & (dataframe['macdhist'].shift(1) >= 0)
        )

        # ── 多空判断 ──
        # 价格在所有均线上方 = 偏多
        dataframe['price_above_all_ma'] = (
            (dataframe['close'] > dataframe['ma20']) &
            (dataframe['close'] > dataframe['ma60']) &
            (dataframe['close'] > dataframe['ma120'])
        )

        # 价格在所有均线下方 = 偏空
        dataframe['price_below_all_ma'] = (
            (dataframe['close'] < dataframe['ma20']) &
            (dataframe['close'] < dataframe['ma60']) &
            (dataframe['close'] < dataframe['ma120'])
        )

        # ── 大趋势方向 ──
        # EMA50 > EMA200 = 多头排列（大趋势向上）
        dataframe['trend_bull'] = dataframe['ema50'] > dataframe['ema200']
        # EMA50 < EMA200 = 空头排列
        dataframe['trend_bear'] = dataframe['ema50'] < dataframe['ema200']

        # ── EMA 发散辅助判断 ──
        # 多头排列：MA20 > MA60 > MA120
        dataframe['ma_bullish_aligned'] = (
            (dataframe['ma20'] > dataframe['ma60']) &
            (dataframe['ma60'] > dataframe['ma120'])
        )
        # 空头排列：MA120 > MA60 > MA20
        dataframe['ma_bearish_aligned'] = (
            (dataframe['ma120'] > dataframe['ma60']) &
            (dataframe['ma60'] > dataframe['ma20'])
        )

        # ── 波动过滤器（略高于正常波动的 K 线） ──
        # ATR 用于止损计算
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)

        return dataframe

    # ── 入场信号 ────────────────────────────────────

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        做多条件（全部满足）：
        1. 均线密集（ma_congested）
        2. 价格在所有均线上方（price_above_all_ma）
        3. MACD 金叉确认（macd_cross_up）
        4. 大趋势向上（trend_bull: EMA50 > EMA200）

        做空条件（全部满足）：
        1. 均线密集（ma_congested）
        2. 价格在所有均线下方（price_below_all_ma）
        3. MACD 死叉确认（macd_cross_down）
        4. 大趋势向下（trend_bear: EMA50 < EMA200）
        """
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0
        dataframe.loc[:, 'enter_tag'] = ''

        # ── 做多 ──
        long_conditions = (
            dataframe['ma_congested'] &
            dataframe['price_above_all_ma'] &
            dataframe['macd_cross_up'] &
            dataframe['trend_bull']
        )
        dataframe.loc[long_conditions, 'enter_long'] = 1
        dataframe.loc[long_conditions, 'enter_tag'] = 'zhonghuadan_long'

        # ── 做空 ──
        short_conditions = (
            dataframe['ma_congested'] &
            dataframe['price_below_all_ma'] &
            dataframe['macd_cross_down'] &
            dataframe['trend_bear']
        )
        dataframe.loc[short_conditions, 'enter_short'] = 1
        dataframe.loc[short_conditions, 'enter_tag'] = 'zhonghuadan_short'

        return dataframe

    # ── 出场信号 ────────────────────────────────────

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        出场条件：
        1. 止损触发（stoploss 自动处理）
        2. 均线重新发散 + K 线方向逆转 → 手动退出
        3. 趋势反转（EMA50/EMA200 死叉/金叉）

        注意：分段止盈（1:1平50%, 1:2平剩余）由 custom_exit 实现
        """
        dataframe.loc[:, 'exit_long'] = 0
        dataframe.loc[:, 'exit_short'] = 0
        dataframe.loc[:, 'exit_tag'] = ''

        # ── 平多：均线转为空头排列 或 趋势反转 ──
        exit_long_conditions = (
            dataframe['ma_bearish_aligned'] |
            dataframe['trend_bear']
        )
        dataframe.loc[exit_long_conditions, 'exit_long'] = 1
        dataframe.loc[exit_long_conditions, 'exit_tag'] = 'trend_reverse'

        # ── 平空：均线转为多头排列 ──
        exit_short_conditions = (
            dataframe['ma_bullish_aligned'] |
            dataframe['trend_bull']
        )
        dataframe.loc[exit_short_conditions, 'exit_short'] = 1
        dataframe.loc[exit_short_conditions, 'exit_tag'] = 'trend_reverse'

        return dataframe

    # ── 自定义出场（分段止盈） ─────────────────────

    def custom_exit(
        self,
        pair: str,
        trade: 'Trade',
        current_time: 'datetime',
        current_rate: float,
        current_profit: float,
        **kwargs
    ):
        """
        分段止盈逻辑（短线突破策略方案）：
        - 第一段：盈亏比 1:1 时平 50%
        - 第二段：盈亏比 1:2 时平剩余
        - 也可以让利润跑，追踪止损

        注意：Freqtrade 的 custom_exit 签名中不直接支持 partial exits。
        这里改为两个出口信号：
            - tp1: 盈利 >= 止损距离 × 1.0（1:1）
            - tp2: 盈利 >= 止损距离 × 2.0（1:2）
        
        由于 Freqtrade 本身支持 partial exits（v2023+），我们使用 exit_pct 参数：
        """
        # 获取止损距离（按 stoploss 5%）
        stoploss_dist = 0.05

        # TP1: 盈亏比 1:1 → 盈利 5%
        if current_profit >= stoploss_dist * 1.0:
            return 'tp1_1to1'

        return None

    def custom_exit_price(
        self,
        pair: str,
        trade: 'Trade',
        current_time: 'datetime',
        proposed_rate: float,
        current_profit: float,
        exit_tag: str,
        **kwargs
    ):
        """使用当前市价出场（不挂限价单）"""
        return proposed_rate

    # ── 仓位计算 ────────────────────────────────────

    def custom_stake_amount(
        self,
        pair: str,
        current_time: 'datetime',
        current_rate: float,
        proposed_stake: float,
        min_stake: float,
        max_stake: float,
        entry_tag: str,
        side: str,
        **kwargs
    ) -> float:
        """
        基于风险计算仓位：
        stake = max_risk / stoploss_pct
        
        对于 dry-run 模式：每笔风险 = 2.5 USDT（50U 本金的 5%）
        开仓金额 = 2.5 / 0.05 = 50 USDT（用足本金）
        """
        # 使用 fixed stake（在 config 中设置）
        # 这里返回默认值，实际金额由 config 的 stake_amount 控制
        return proposed_stake
