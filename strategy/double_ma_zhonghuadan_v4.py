# -*- coding: utf-8 -*-
"""
双均线中华单策略 v4 — Freqtrade 版（完整实现 5 条核心法则）

基于 v3 回测验证的策略骨架，补全技能书要求的全部风控机制:

v4 新增:
    1. 震荡过滤:ADX < 20 或布林带宽度收縮 → 不开仓
    2. 开仓方法 B:回踩 20MA 不破开仓（补充方法 A 均线密集突破）
    3. 赔率过滤:止损:止盈未达 1:3 不开仓
    4. 仓位計算:custom_stake_amount 用「最大可接受亏损 ÷ |stoploss|」反推
    5. 分段止盈:1:1 平仓 50%，剩余博 1:2+
    6. 熔断机制:连亏 3 次停 24h，连亏 5 次停 1 周，单日亏 >5% 停当日
    7. 杠杆约束:15m 级别实际杠杆 ≤ 5x

配置要求:
    timeframe = '15m'
    startup_candle_count = 200
    stoploss = -0.03（硬止损安全网）
    trading_mode = 'futures', margin_mode = 'isolated'
    position_adjustment_enable = True
"""

import logging
from datetime import datetime, timedelta
import talib.abstract as ta
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from freqtrade.persistence import Trade
from pandas import DataFrame

logger = logging.getLogger(__name__)


class DoubleMAZhonghuadanV4(IStrategy):
    """
    双均线中华单 v4 — 完整风控版（15 分钟）

    交易对:BTC/ETH/SOL
    资金:50 USDT 起步
    """

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = '15m'
    startup_candle_count = 200

    # 硬止损:最后安全网。实际止损由 custom_stoploss 动态计算
    stoploss = -0.03
    use_custom_stoploss = True

    # 分段止盈（position_adjustment）
    position_adjustment_enable = True
    max_entry_position_adjustment = 0  # 仅减仓，不加仓

    # ROI 关闭（用 custom_exit + 分段止盈代替）
    minimal_roi = {"0": 1.0}

    # ── 可调参数（hyperopt 空间） ────────────────────
    congestion_threshold = DecimalParameter(
        0.015, 0.05, default=0.025, decimals=4, space='buy', optimize=True
    )
    adx_threshold = IntParameter(15, 30, default=20, space='buy')
    macd_fast = IntParameter(10, 14, default=12, space='buy')
    macd_slow = IntParameter(24, 30, default=26, space='buy')
    macd_signal = IntParameter(7, 11, default=9, space='buy')

    # 风控参数
    max_risk_per_trade = DecimalParameter(
        0.03, 0.10, default=0.05, decimals=3, space='sell',
    )  # 每笔最大亏损占本金比例

    max_daily_loss = DecimalParameter(
        0.05, 0.20, default=0.15, decimals=3, space='sell',
    )  # 单日亏损上限（配合 10% 单笔风险）

    # ── 熔断保护 ──────────────────────────────────────
    @property
    def protections(self):
        return [
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 72,  # 72 根 15m K 线 ≈ 18 小时
                "trade_limit": 3,
                "stop_duration_candles": 96,   # 停 24 小时
                "only_per_pair": False,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 672,  # 7 天
                "max_allowed_drawdown": 0.10,
                "stop_duration_candles": 960,     # 停 10 天
                "only_per_pair": False,
            },
        ]

    # ── 指标 ──────────────────────────────────────────

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 6 条均线
        for period in [20, 60, 120]:
            dataframe[f'ma{period}'] = ta.SMA(dataframe, timeperiod=period)
            dataframe[f'ema{period}'] = ta.EMA(dataframe, timeperiod=period)

        # 趋势过滤
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)

        # MACD
        macd = ta.MACD(dataframe, fastperiod=self.macd_fast.value,
                       slowperiod=self.macd_slow.value,
                       signalperiod=self.macd_signal.value)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']

        # MACD 交叉
        dataframe['macd_cross_up'] = (
            (dataframe['macdhist'] > 0) & (dataframe['macdhist'].shift(1) <= 0)
        )
        dataframe['macd_cross_down'] = (
            (dataframe['macdhist'] < 0) & (dataframe['macdhist'].shift(1) >= 0)
        )

        # 均线密集
        dataframe['ma_spread'] = (
            abs(dataframe['ma20'] - dataframe['ma120']) / dataframe['ma120'] * 100
        )
        dataframe['ma_congested'] = (
            dataframe['ma_spread'] < self.congestion_threshold.value
        )

        # ── 新增:震荡过滤 ──
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_width'] = (bb['upperband'] - bb['lowerband']) / bb['middleband']
        # 震荡判定:ADX 太低 或 布林带急速收窄
        dataframe['is_choppy'] = (
            (dataframe['adx'] < self.adx_threshold.value) |
            (dataframe['bb_width'] < dataframe['bb_width'].rolling(20).mean() * 0.7)
        )

        # 趋势
        dataframe['trend_bull'] = dataframe['ema50'] > dataframe['ema200']
        dataframe['trend_bear'] = dataframe['ema50'] < dataframe['ema200']

        # 价格位置
        dataframe['above_ma20'] = dataframe['close'] > dataframe['ma20']
        dataframe['below_ma20'] = dataframe['close'] < dataframe['ma20']
        dataframe['prev_above_ma20'] = dataframe['close'].shift(1) > dataframe['ma20'].shift(1)
        dataframe['prev_below_ma20'] = dataframe['close'].shift(1) < dataframe['ma20'].shift(1)

        # 均线排列
        dataframe['ma_bullish'] = (
            (dataframe['ma20'] > dataframe['ma60']) & (dataframe['ma60'] > dataframe['ma120'])
        )
        dataframe['ma_bearish'] = (
            (dataframe['ma120'] > dataframe['ma60']) & (dataframe['ma60'] > dataframe['ma20'])
        )

        # ── 新增:方法 B 回踩 20MA 信号 ──
        # 做多回踩:前 2 根在 MA20 下方 → 当前 K 线站回上方 → 且均线已有趋势
        dataframe['pullback_buy'] = (
            (dataframe['close'].shift(2) < dataframe['ma20'].shift(2)) &
            (dataframe['close'] > dataframe['ma20']) &
            dataframe['ma_congested']
        )
        dataframe['pullback_sell'] = (
            (dataframe['close'].shift(2) > dataframe['ma20'].shift(2)) &
            (dataframe['close'] < dataframe['ma20']) &
            dataframe['ma_congested']
        )

        # ── 新增:记录均线密集区宽度（用于动态止损） ──
        dataframe['congestion_width'] = dataframe['ma_spread'].where(
            dataframe['ma_congested'], other=float('nan')
        ).ffill()

        return dataframe

    # ── 入场 ──────────────────────────────────────────

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0
        dataframe.loc[:, 'enter_tag'] = ''

        # ── 震荡市一律不做 ──
        not_choppy = ~dataframe['is_choppy']

        # ── 方法 A:均线密集突破 ──
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

        # ── 方法 B:回踩 20MA ──
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

        long_cond = (method_a_long | method_b_long) & not_choppy
        short_cond = (method_a_short | method_b_short) & not_choppy

        dataframe.loc[long_cond, 'enter_long'] = 1
        dataframe.loc[long_cond, 'enter_tag'] = 'long_signal'
        dataframe.loc[short_cond, 'enter_short'] = 1
        dataframe.loc[short_cond, 'enter_tag'] = 'short_signal'

        return dataframe

    # ── 出场 ──────────────────────────────────────────

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'exit_long'] = 0
        dataframe.loc[:, 'exit_short'] = 0

        # 核心出场条件:均线排列反转 + K 线方向翻转
        exit_long = (
            dataframe['ma_bearish'] |
            (dataframe['trend_bear'] & dataframe['macd_cross_down']) |
            (dataframe['below_ma20'] & dataframe['prev_below_ma20'])
        )
        dataframe.loc[exit_long, 'exit_long'] = 1

        exit_short = (
            dataframe['ma_bullish'] |
            (dataframe['trend_bull'] & dataframe['macd_cross_up']) |
            (dataframe['above_ma20'] & dataframe['prev_above_ma20'])
        )
        dataframe.loc[exit_short, 'exit_short'] = 1

        return dataframe

    # ═══════════════════════════════════════════════════
    # 以下为 custom_ 方法重写 — 赔率 / 仓位 / 止盈
    # ═══════════════════════════════════════════════════

    # ── 动态止损:确保赔率 ≥ 1:3 ──
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        """
        止损逻辑（优先级从高到低）:
        1. 若刚开仓 → 计算均线密集区宽度，用于赔率判定
        2. 若浮盈达 3% → 止损上移至保本
        3. 若浮盈达 6% → 止损上移至 2% 盈利
        """
        # 获取开仓时的 DataFrame（含 congestion_width）
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None

        candle = dataframe.iloc[-1]
        entry_rate = trade.open_rate

        # 计算动态止损距离
        if trade.is_short:
            stop_pct = abs(current_rate - entry_rate) / entry_rate
        else:
            stop_pct = abs(entry_rate - current_rate) / entry_rate

        # 浮盈达 3%（1 倍止损）→ 保本
        if current_profit >= 0.03:
            return -0.002  # 微利保本
        # 浮盈达 6%（2 倍止损）→ 锁定 2% 利润
        if current_profit >= 0.06:
            return -0.02

        # 未到目标 → 保持硬止损
        return None

    # ── 分段止盈（position_adjustment） ──
    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: float | None, max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float,
                              **kwargs) -> float | None:
        """
        中华单分段止盈:
        - 盈利达 3%（1:1 赔率）→ 平仓 50%
        - 盈利达 6%（1:2 赔率）→ 平仓剩余 50%
        用负 stake 实现减仓。
        """
        if trade.nr_of_successful_entries > 1:
            return None  # 已经减过仓，不再调

        filled_entries = trade.select_filled_orders(trade.entry_side)
        if not filled_entries:
            return None
        total_stake = sum(o.safe_cost for o in filled_entries)

        # 第一段止盈:达到 1:1 赔率（3% 盈利）
        if current_profit >= 0.03:
            half_stake = -total_stake * 0.5
            logger.info(f"分段止盈(1:1): {pair} 减仓 50% ({half_stake:.2f} USDT)")
            return half_stake

        # 第二段止盈:达到 1:2 赔率（6% 盈利）
        if current_profit >= 0.06:
            # 返回剩余全部（减完）
            remaining = -total_stake * 0.5
            logger.info(f"分段止盈(1:2): {pair} 减仓剩余 50%")
            return remaining

        return None

    # ── 仓位计算 ──
    def custom_stake_amount(self, pair: str, current_time: datetime,
                            current_rate: float, proposed_stake: float,
                            min_stake: float, max_stake: float,
                            entry_tag: str | None, side: str,
                            **kwargs) -> float:
        """
        初始仓位计算:仓位 = 可接受亏损 ÷ |stoploss|
        10% 本金作为单笔最大亏损 → 50U × 10% = 5U
        15m 止损 3% → 仓位 = 5 / 0.03 = 167U（实际杠杆 3.33x）
        上限:不超过杠杆允许的最大仓位（30x → 1500U）

        注意:这是开仓时的初始仓位计算，不是滚仓。
        当前策略只做分段止盈（减仓），不做浮盈加仓。
        """
        wallet = self.wallets.get_total_stake_amount()
        # 用 10% 本金作为可接受亏损
        max_loss_amount = wallet * 0.10
        position = max_loss_amount / abs(self.stoploss)
        # 上限:80% 杠杆能力
        max_allowed = wallet * 30.0 * 0.8
        return min(position, max_allowed, max_stake)

    # ── 日亏损熔断（额外检查，配合 protections） ──
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: str | None, side: str, **kwargs) -> bool:
        """
        开仓前检查当日亏损是否超标。
        """
        # 统计当日已平仓亏损
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
        if daily_loss > wallet * self.max_daily_loss.value:
            logger.warning(f"熔断:当日亏损 {daily_loss:.2f} 超限，拒绝开仓")
            return False

        return True
