# -*- coding: utf-8 -*-
"""
纯双均线策略（币哥原版）— 无任何过滤器 + 滚仓

这是最原始的双均线系统：
    - 6 条均线（MA/EMA 20/60/120）
    - 均线密集 = 入场信号
    - K 线位置判断方向
    - 均线排列反转 = 出场
    - 不做 MACD、ADX、布林带、趋势过滤
    - 但有滚仓仓位 + 熔断保护

与 V4（中华单）对比：V4 加了多层过滤 → 信号少但质量高。
纯版信号多但假信号也多，胜率更低。两者并行对比才有意义。
"""

import logging
from datetime import datetime
import talib.abstract as ta
from freqtrade.strategy import IStrategy, DecimalParameter
from freqtrade.persistence import Trade
from pandas import DataFrame

logger = logging.getLogger(__name__)


class DoubleMAPure(IStrategy):
    """
    纯双均线（币哥原版）— 15 分钟

    逻辑极简：密集了看方向，方向定了就开。别的都不管。
    """

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = '15m'
    startup_candle_count = 200

    stoploss = -0.03
    use_custom_stoploss = True
    position_adjustment_enable = False  # 纯版不做分段止盈
    minimal_roi = {"0": 1.0}

    # ── 唯一可调参数 ──
    congestion_threshold = DecimalParameter(
        0.015, 0.05, default=0.025, decimals=4, space='buy', optimize=True
    )

    # ── 熔断 ──
    @property
    def protections(self):
        return [
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 72,
                "trade_limit": 3,
                "stop_duration_candles": 96,
                "only_per_pair": False,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 672,
                "max_allowed_drawdown": 0.15,
                "stop_duration_candles": 960,
                "only_per_pair": False,
            },
        ]

    # ── 指标（极简版） ──────────────────────────────

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 6 条均线
        for period in [20, 60, 120]:
            dataframe[f'ma{period}'] = ta.SMA(dataframe, timeperiod=period)
            dataframe[f'ema{period}'] = ta.EMA(dataframe, timeperiod=period)

        # 均线密集
        dataframe['ma_spread'] = (
            abs(dataframe['ma20'] - dataframe['ma120']) / dataframe['ma120'] * 100
        )
        dataframe['ma_congested'] = (
            dataframe['ma_spread'] < self.congestion_threshold.value
        )

        # 价格位置
        dataframe['above_ma20'] = dataframe['close'] > dataframe['ma20']
        dataframe['below_ma20'] = dataframe['close'] < dataframe['ma20']
        dataframe['prev_above_ma20'] = dataframe['close'].shift(1) > dataframe['ma20'].shift(1)
        dataframe['prev_below_ma20'] = dataframe['close'].shift(1) < dataframe['ma20'].shift(1)

        # 均线排列（出场用）
        dataframe['ma_bullish'] = (
            (dataframe['ma20'] > dataframe['ma60']) & (dataframe['ma60'] > dataframe['ma120'])
        )
        dataframe['ma_bearish'] = (
            (dataframe['ma120'] > dataframe['ma60']) & (dataframe['ma60'] > dataframe['ma20'])
        )

        return dataframe

    # ── 入场 ──────────────────────────────────────────

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0
        dataframe.loc[:, 'enter_tag'] = ''

        # 做多：密集 + K线在上方 + 前一根也在上方（确认突破有效）
        long_cond = (
            dataframe['ma_congested'] &
            dataframe['above_ma20'] &
            dataframe['prev_above_ma20']
        )
        dataframe.loc[long_cond, 'enter_long'] = 1
        dataframe.loc[long_cond, 'enter_tag'] = 'pure_long'

        # 做空：密集 + K线在下方 + 前一根也在下方
        short_cond = (
            dataframe['ma_congested'] &
            dataframe['below_ma20'] &
            dataframe['prev_below_ma20']
        )
        dataframe.loc[short_cond, 'enter_short'] = 1
        dataframe.loc[short_cond, 'enter_tag'] = 'pure_short'

        return dataframe

    # ── 出场 ──────────────────────────────────────────

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'exit_long'] = 0
        dataframe.loc[:, 'exit_short'] = 0

        # 均线排列反转 或 K 线跌破/突破 MA20
        exit_long = (
            dataframe['ma_bearish'] |
            (dataframe['below_ma20'] & dataframe['prev_below_ma20'])
        )
        dataframe.loc[exit_long, 'exit_long'] = 1

        exit_short = (
            dataframe['ma_bullish'] |
            (dataframe['above_ma20'] & dataframe['prev_above_ma20'])
        )
        dataframe.loc[exit_short, 'exit_short'] = 1

        return dataframe

    # ═══════════════════════════════════════════════════
    # 滚仓 + 保护
    # ═══════════════════════════════════════════════════

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        """纯版：浮盈 5% 上移止损到保本"""
        if current_profit >= 0.05:
            return -0.002
        return None

    def custom_stake_amount(self, pair: str, current_time: datetime,
                            current_rate: float, proposed_stake: float,
                            min_stake: float, max_stake: float,
                            entry_tag: str | None, side: str,
                            **kwargs) -> float:
        """滚仓：20% 本金做单笔最大亏损"""
        wallet = self.wallets.get_total_stake_amount()
        max_loss_amount = wallet * 0.20
        position = max_loss_amount / abs(self.stoploss)
        max_allowed = wallet * 30.0 * 0.8
        return min(position, max_allowed, max_stake)

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: str | None, side: str, **kwargs) -> bool:
        """当日亏损熔断"""
        today = current_time.date()
        daily_loss = 0.0
        for t in Trade.get_trades_proxy():
            if t.is_open or not t.close_date:
                continue
            if t.close_date.date() != today:
                continue
            if t.close_profit_abs and t.close_profit_abs < 0:
                daily_loss += abs(t.close_profit_abs)

        wallet = self.wallets.get_total_stake_amount()
        if daily_loss > wallet * 0.25:
            logger.warning(f"纯版熔断：当日亏损 {daily_loss:.2f} 超限")
            return False
        return True
