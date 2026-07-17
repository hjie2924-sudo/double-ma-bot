"""
保守双均线 — 回测用（含滚仓模拟 + 方法B回踩信号）

核心逻辑：
- 方法A：均线密集(MA20/MA120价差<2.5%) + K线突破MA20(连续2根) + MACD交叉 + 趋势确认
- 方法B：回踩20MA + MACD交叉 + 趋势确认（增加信号多样性）
- 金字塔加仓：1R(3%)时 +60%，2R(6%)时 +40%，最多2次
- 加仓后止损上移至保本
- BTC tape filter（Regime Gate）避开放量暴跌

参考文献：
- Brock et al. (1992) 双均线策略有效性
- Fractional Kelly 仓位管理
- MarketTrace (2026) Regime Gate 防雪崩机制
"""

from double_ma_zhonghuadan_v4_lite import ZengqiangShuangjunxian
from datetime import datetime, timedelta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy
import logging

logger = logging.getLogger(__name__)


class BaoshouGuncang(ZengqiangShuangjunxian):
    """保守双均线 + 滚仓"""

    position_adjustment_enable = True
    max_entry_position_adjustment = 2  # 最多加仓 2 次

    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: float | None, max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit, current_exit_profit,
                              **kwargs) -> float | None:
        """滚仓 + 分段止盈"""

        filled_entries = trade.select_filled_orders(trade.entry_side)
        if not filled_entries:
            return None
        total_stake = sum(o.safe_cost for o in filled_entries)

        # ── 分段止盈（盈利够高时减仓）──
        if current_profit >= 0.12:  # 12% = 4R
            remaining = -total_stake
            logger.info(f"滚仓全部止盈: profit={current_profit:.2%}")
            return remaining

        # ── 滚仓加仓（金字塔递减）──
        nr_entries = trade.nr_of_successful_entries

        # 第一次加仓：浮盈达 3%（1R）
        if nr_entries == 1 and current_profit >= 0.03:
            add_stake = total_stake * 0.6  # 第二份 = 60%
            logger.info(f"滚仓加仓#1: +{add_stake:.2f} USDT, profit={current_profit:.2%}")
            return add_stake

        # 第二次加仓：浮盈达 6%（2R）
        if nr_entries == 2 and current_profit >= 0.06:
            add_stake = total_stake * 0.4  # 第三份 = 40%
            logger.info(f"滚仓加仓#2: +{add_stake:.2f} USDT, profit={current_profit:.2%}")
            return add_stake

        return None

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        """加仓后止损上移"""
        nr_entries = trade.nr_of_successful_entries

        # 加仓后 → 保本止损
        if nr_entries >= 2 and current_profit >= 0.005:
            return -0.002
        # 原始止损（3%）
        return None

    # ── BTC Regime Gate ────────────────────────────────────
    # 文献依据：MarketTrace (2026), "7 Failure Modes of Crypto Bots"
    # BTC 短时剧烈波动（5分钟 > 1.5%）时，禁止开新仓
    # 因为在 BTC 闪崩瞬间，所有 alt 相关性坍缩为 ~1
    # 此时开单 = 高概率吃满波动

    BTC_TAPE_THRESHOLD = 0.015      # 1.5% — 触发阈值
    BTC_TAPE_COOLDOWN = 30          # 30分钟 — 触发后封锁时间

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: str | None, side: str, **kwargs) -> bool:
        """开仓前检查 BTC 市场状态。如果 BTC 正在闪电崩盘，不开新仓。"""
        # 仅对 ALT 交易对做检查（BTC 本身不用检查）
        if pair.startswith("BTC/"):
            return True

        try:
            # 获取 BTC 15m K 线数据
            btc_data, _ = self.dp.get_analyzed_dataframe("BTC/USDT:USDT", self.timeframe)
            if btc_data is None or btc_data.empty:
                return True  # 数据未就绪，放行

            # 取最近 2 根 K 线的收盘价，计算 15m 收益率
            last = btc_data.iloc[-1]
            prev = btc_data.iloc[-2] if len(btc_data) >= 2 else None

            if prev is not None and prev['close'] > 0:
                btc_return = abs((last['close'] - prev['close']) / prev['close'])
            else:
                btc_return = 0

            # 如果 BTC 波动超阈值 → 封锁开仓
            if btc_return >= self.BTC_TAPE_THRESHOLD:
                logger.warning(
                    f"BTC tape gate 触发: BTC 15m波动={btc_return:.2%} "
                    f"(阈值={self.BTC_TAPE_THRESHOLD:.2%})，禁止 {pair} 开仓"
                )
                return False

        except Exception as e:
            # 获取数据失败不应阻塞交易
            logger.warning(f"BTC tape gate 检查异常: {e}")
            return True

        return True
