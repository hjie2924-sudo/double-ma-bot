# -*- coding: utf-8 -*-
"""激进双均线 — 回测用（含滚仓模拟）

基于 Zhonghuadan，加入滚仓逻辑：
- 浮盈达 1R（1%）→ 加仓 1 份
- 浮盈达 2R（2%）→ 再加仓 1 份
- 最多加仓 2 次
"""

from zhonghuadan import Zhonghuadan
from datetime import datetime
from freqtrade.persistence import Trade
import logging

logger = logging.getLogger(__name__)


class JijinGuncang(Zhonghuadan):
    """激进双均线 + 滚仓"""

    position_adjustment_enable = True
    max_entry_position_adjustment = 2

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

        # ── 全部止盈 ──
        if current_profit >= 0.04:  # 4% = 4R
            return -total_stake

        nr_entries = trade.nr_of_successful_entries

        # 第一次加仓：浮盈达 1%（1R）
        if nr_entries == 1 and current_profit >= 0.01:
            add_stake = total_stake * 0.6
            return add_stake

        # 第二次加仓：浮盈达 2%（2R）
        if nr_entries == 2 and current_profit >= 0.02:
            add_stake = total_stake * 0.4
            return add_stake

        return None
