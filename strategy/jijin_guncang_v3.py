# -*- coding: utf-8 -*-
"""激进双均线滚仓 V3 — 止损 2.5%，无 ADX 过滤（对齐保守版信号量）

文献改进：
- 移除 ADX 震荡过滤（V2 信号太少，6个月6单不够统计意义）
- 保留 EMA50/200 趋势 + MACD 入场确认
- 新增 BTC tape filter (Regime Gate)
- MACD 反转减仓
- 4R(10%) 止盈

参考文献：
- Bailey et al. (2014) 回测过拟合概率
- MarketTrace (2026) Regime Gate 防雪崩机制
"""
from jijin_guncang_v2 import JijinGuncangV2
from pandas import DataFrame
from datetime import datetime
from freqtrade.persistence import Trade
import logging

logger = logging.getLogger(__name__)


class JijinGuncangV3(JijinGuncangV2):
    """激进双均线滚仓 V3"""

    stoploss = -0.025

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """移除 ADX 震荡过滤，保留 EMA50/200 趋势"""
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0
        dataframe.loc[:, 'enter_tag'] = ''

        # 无 not_choppy 过滤
        long_a = (
            dataframe['ma_congested'] & dataframe['above_ma20'] &
            dataframe['prev_above_ma20'] & dataframe['macd_cross_up'] &
            dataframe['trend_bull']
        )
        short_a = (
            dataframe['ma_congested'] & dataframe['below_ma20'] &
            dataframe['prev_below_ma20'] & dataframe['macd_cross_down'] &
            dataframe['trend_bear']
        )
        long_b = (
            dataframe['pullback_buy'] & dataframe['macd_cross_up'] &
            dataframe['trend_bull']
        )
        short_b = (
            dataframe['pullback_sell'] & dataframe['macd_cross_down'] &
            dataframe['trend_bear']
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
        filled = trade.select_filled_orders(trade.entry_side)
        if not filled:
            return None
        total = sum(o.safe_cost for o in filled)
        nr = trade.nr_of_successful_entries

        if current_profit >= 0.10:  # 4R at 2.5%
            return -total

        if nr == 1 and current_profit >= 0.025:  # 1R
            add = total * 0.5
            return add
        if nr == 2 and current_profit >= 0.05:   # 2R
            add = total * 0.3
            return add

        return None

    # ── BTC Regime Gate ────────────────────────────────────
    # BTC 短时剧烈波动时禁止开新仓（防雪崩）
    BTC_TAPE_THRESHOLD = 0.015      # 1.5%
    BTC_TAPE_COOLDOWN = 30          # 30分钟

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: str | None, side: str, **kwargs) -> bool:
        """开仓前检查：日亏损熔断 + BTC regime gate"""
        # 先执行父类的日亏损检查
        if hasattr(super(), 'confirm_trade_entry'):
            parent_ok = super().confirm_trade_entry(
                pair, order_type, amount, rate, time_in_force,
                current_time, entry_tag, side, **kwargs
            )
            if not parent_ok:
                return False

        # BTC 本身不用检查
        if pair.startswith("BTC/"):
            return True

        # BTC tape gate
        try:
            btc_data, _ = self.dp.get_analyzed_dataframe("BTC/USDT:USDT", self.timeframe)
            if btc_data is None or btc_data.empty:
                return True
            last = btc_data.iloc[-1]
            prev = btc_data.iloc[-2] if len(btc_data) >= 2 else None
            if prev is not None and prev['close'] > 0:
                btc_return = abs((last['close'] - prev['close']) / prev['close'])
            else:
                btc_return = 0

            if btc_return >= self.BTC_TAPE_THRESHOLD:
                logger.warning(
                    f"[激进] BTC tape gate 触发: {btc_return:.2%}, 禁止 {pair} 开仓"
                )
                return False
        except Exception as e:
            logger.warning(f"[激进] BTC tape gate 异常: {e}")

        return True
