# -*- coding: utf-8 -*-
"""
中华单策略 — 1:1 复刻币哥视频 DeHKseWdE-M

核心特征（与 V4 的区别）：
    1. 止损 1%
    2. 只保留 MACD 过滤，去掉趋势、ADX、布林带
    3. 入场 = 均线密集 + K线突破 + 回踩不破 + MACD 确认
    4. 分段止盈：赚 1% 平一半，赚 2% 平全部
    5. 初始仓位：5% 本金做单笔最大亏损（止损 1% → 仓位 250U）

配置要求：
    timeframe = '15m', leverage = 100x
    stoploss = -0.01, position_adjustment_enable = True
"""

import logging
from datetime import datetime
import talib.abstract as ta
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from freqtrade.persistence import Trade
from pandas import DataFrame

logger = logging.getLogger(__name__)


class Zhonghuadan(IStrategy):
    """
    中华单 — 币哥 15 分钟短线（100+ 次实测，胜率 78%+）
    """

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = '15m'
    startup_candle_count = 200

    stoploss = -0.01
    use_custom_stoploss = True
    position_adjustment_enable = True
    max_entry_position_adjustment = 0
    minimal_roi = {"0": 1.0}

    # ── 参数 ──
    congestion_threshold = DecimalParameter(
        0.01, 0.04, default=0.02, decimals=4, space='buy', optimize=True
    )
    macd_fast = IntParameter(10, 14, default=12, space='buy')
    macd_slow = IntParameter(24, 30, default=26, space='buy')
    macd_signal = IntParameter(7, 11, default=9, space='buy')

    @property
    def protections(self):
        return [
            {"method": "StoplossGuard", "lookback_period_candles": 72, "trade_limit": 5,
             "stop_duration_candles": 48, "only_per_pair": False},
            {"method": "MaxDrawdown", "lookback_period_candles": 672,
             "max_allowed_drawdown": 0.15, "stop_duration_candles": 960,
             "only_per_pair": False},
        ]

    # ── 指标 ──

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        for period in [20, 60, 120]:
            dataframe[f'ma{period}'] = ta.SMA(dataframe, timeperiod=period)
            dataframe[f'ema{period}'] = ta.EMA(dataframe, timeperiod=period)

        macd = ta.MACD(dataframe, fastperiod=self.macd_fast.value,
                       slowperiod=self.macd_slow.value,
                       signalperiod=self.macd_signal.value)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']

        dataframe['macd_cross_up'] = (
            (dataframe['macdhist'] > 0) & (dataframe['macdhist'].shift(1) <= 0)
        )
        dataframe['macd_cross_down'] = (
            (dataframe['macdhist'] < 0) & (dataframe['macdhist'].shift(1) >= 0)
        )

        dataframe['ma_spread'] = (
            abs(dataframe['ma20'] - dataframe['ma120']) / dataframe['ma120'] * 100
        )
        dataframe['ma_congested'] = (
            dataframe['ma_spread'] < self.congestion_threshold.value
        )

        dataframe['above_ma20'] = dataframe['close'] > dataframe['ma20']
        dataframe['below_ma20'] = dataframe['close'] < dataframe['ma20']
        dataframe['prev_above_ma20'] = dataframe['close'].shift(1) > dataframe['ma20'].shift(1)
        dataframe['prev_below_ma20'] = dataframe['close'].shift(1) < dataframe['ma20'].shift(1)

        dataframe['ma_bullish'] = (
            (dataframe['ma20'] > dataframe['ma60']) & (dataframe['ma60'] > dataframe['ma120'])
        )
        dataframe['ma_bearish'] = (
            (dataframe['ma120'] > dataframe['ma60']) & (dataframe['ma60'] > dataframe['ma20'])
        )

        return dataframe

    # ── 入场 ──

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0
        dataframe.loc[:, 'enter_tag'] = ''

        long_cond = (
            dataframe['ma_congested'] &
            dataframe['above_ma20'] &
            dataframe['prev_above_ma20'] &
            dataframe['macd_cross_up']
        )
        dataframe.loc[long_cond, 'enter_long'] = 1
        dataframe.loc[long_cond, 'enter_tag'] = 'zhd_long'

        short_cond = (
            dataframe['ma_congested'] &
            dataframe['below_ma20'] &
            dataframe['prev_below_ma20'] &
            dataframe['macd_cross_down']
        )
        dataframe.loc[short_cond, 'enter_short'] = 1
        dataframe.loc[short_cond, 'enter_tag'] = 'zhd_short'

        return dataframe

    # ── 出场 ──

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'exit_long'] = 0
        dataframe.loc[:, 'exit_short'] = 0

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
    # 中华单核心：分段止盈
    # ═══════════════════════════════════════════════════

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        """浮盈 0.5% 上移止损到保本"""
        if current_profit >= 0.005:
            return -0.001
        return None

    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: float | None, max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float,
                              **kwargs) -> float | None:
        """
        中华单分段止盈：
        - 盈利 1%（1:1）→ 平仓 50%
        - 盈利 2%（1:2）→ 平仓剩余
        """
        if trade.nr_of_successful_entries > 1:
            return None

        filled = trade.select_filled_orders(trade.entry_side)
        if not filled:
            return None
        total = sum(o.safe_cost for o in filled)

        if current_profit >= 0.01:
            half = -total * 0.5
            logger.info(f"中华单 1:1 止盈: {pair} -50% ({half:.2f})")
            return half

        if current_profit >= 0.02:
            remaining = -total * 0.5
            logger.info(f"中华单 1:2 止盈: {pair} -50%")
            return remaining

        return None

    def custom_stake_amount(self, pair: str, current_time: datetime,
                            current_rate: float, proposed_stake: float,
                            min_stake: float, max_stake: float,
                            entry_tag: str | None, side: str,
                            **kwargs) -> float:
        """
        初始仓位计算：5% 本金作为单笔最大亏损
        止损 1% → 仓位 = 2.5 / 0.01 = 250U

        注意：这是开仓时的初始仓位计算，不是滚仓。
        当前策略只做分段止盈（减仓），不做浮盈加仓。
        """
        wallet = self.wallets.get_total_stake_amount()
        max_loss = wallet * 0.05
        position = max_loss / abs(self.stoploss)
        max_allowed = wallet * 90.0 * 0.8
        return min(position, max_allowed, max_stake)

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: str | None, side: str, **kwargs) -> bool:
        today = current_time.date()
        daily_loss = 0.0
        for t in Trade.get_trades_proxy():
            if t.is_open or not t.close_date:
                continue
            if t.close_date.date() != today:
                continue
            if t.close_profit_abs and t.close_profit_abs < 0:
                daily_loss += abs(t.close_profit_abs)

        if daily_loss > self.wallets.get_total_stake_amount() * 0.10:
            logger.warning(f"中华单熔断：日亏 {daily_loss:.2f} 超限")
            return False
        return True
