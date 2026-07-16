# 双均线策略回测对比 — 2026-01-03 ~ 2026-07-15

> Data: OKX futures 15m candles (BTC/USDT, ETH/USDT, SOL/USDT)
> Time range: 2026-01-03 02:00 → 2026-07-15 13:45 (UTC)

---

## 保守滚仓 (Baoshou Guncang) — config_lite.json (30x leverage, 3% SL)

| Metric | BaoshouGuncang (原版) | BaoshouGuncangV2 (优化版) | V2 Change |
|--------|----------------------|---------------------------|-----------|
| **Trades** | 25 | 6 | ⬇️ -76% (fewer, selective) |
| **Avg Profit %** | 0.29% | 0.21% | ⬇️ |
| **Tot Profit USDT** | 3.586 | 0.596 | ⬇️ (-2.99) |
| **Tot Profit %** | 7.17% | 1.19% | ⬇️ |
| **Win / Draw / Loss** | 9 / 0 / 16 | 3 / 0 / 3 | — |
| **Win %** | 36.0% | 50.0% | ✅ **+14.0pp** |
| **Max Drawdown** | 1.58% (0.788 USDT) | 0.85% (0.426 USDT) | ✅ **-46% (halved)** |
| **Sharpe** | 1.89 | 0.76 | ⬇️ |
| **Sortino** | 4.02 | 6.65 | ✅ **+65%** |
| **Calmar** | 45.06 | 13.84 | ⬇️ |
| **Avg Duration** | 3:56 | 4:38 | ⬆️ +18% |

### Conservative V2 Assessment
- **Improved**: Win rate (+14pp), Max Drawdown (-46%), Sortino (+65%) — better risk management
- **Regressed**: Total profit (lower because fewer trades), Sharpe/Calmar (lower return drags ratios)
- **Bottom line**: V2 reduces trade count by 76%, halving drawdown while nearly doubling Sortino. The trade-off is lower total PnL, consistent with a more conservative filter.

---

## 激进滚仓 (Jijin Guncang) — config_zhonghuadan.json (90x leverage, 2% SL)

| Metric | JijinGuncang (原版) | JijinGuncangV2 (优化版) | V2 Change |
|--------|---------------------|-------------------------|-----------|
| **Trades** | 38 | 13 | ⬇️ -66% (fewer, selective) |
| **Avg Profit %** | -0.09% | -0.01% | ✅ **+0.08pp** |
| **Tot Profit USDT** | -1.598 | -0.095 | ✅ **+1.503 (94% less loss)** |
| **Tot Profit %** | -3.20% | -0.19% | ✅ **+3.01pp** |
| **Win / Draw / Loss** | 12 / 0 / 26 | 5 / 0 / 8 | — |
| **Win %** | 31.6% | 38.5% | ✅ **+6.9pp** |
| **Max Drawdown** | 3.87% (1.948 USDT) | 1.82% (0.91 USDT) | ✅ **-53% (halved)** |
| **Sharpe** | -1.72 | -0.06 | ✅ **+1.66** |
| **Sortino** | -1.12 | -0.03 | ✅ **+1.09** |
| **Calmar** | -8.18 | -1.03 | ✅ **+7.15** |
| **Avg Duration** | 2:12 | 4:13 | ⬆️ +91% |

### Aggressive V2 Assessment — 🏆 V2 dominates across ALL metrics
- **Improved**: Every single metric — Win rate (+6.9pp), Max Drawdown (-53%), Sharpe (+1.66), Sortino (+1.09), Calmar (+7.15), near-breakeven vs -3.2% loss
- **Nothing regressed**: V2 strictly Pareto-better than original
- **Bottom line**: V2 turns a -3.2% losing strategy into near-breakeven (-0.19%), cuts drawdown in half, and improves every risk-adjusted metric. Clear winner.

---

## 总览对比 (Combined Overview)

| Metric | 保守原版 | 保守V2 | 激进原版 | 激进V2 |
|--------|---------|--------|---------|--------|
| Trades | 25 | 6 | 38 | 13 |
| Tot Profit % | **+7.17%** | +1.19% | -3.20% | -0.19% |
| Win % | 36.0% | **50.0%** | 31.6% | 38.5% |
| Max Drawdown | 1.58% | **0.85%** | 3.87% | 1.82% |
| Sharpe | **1.89** | 0.76 | -1.72 | -0.06 |
| Sortino | 4.02 | **6.65** | -1.12 | -0.03 |
| Calmar | **45.06** | 13.84 | -8.18 | -1.03 |

**Bold** = best value in each row.

---

## Key Takeaways

1. **JijinGuncangV2 (激进优化版)** is the biggest winner — strictly better than original on every dimension. Massive reduction in losses and risk.
2. **BaoshouGuncangV2 (保守优化版)** improves risk metrics (Win%, Drawdown, Sortino) at the cost of lower total returns — intentional conservative filtering.
3. Both V2 strategies drastically reduce trade frequency (66-76% fewer trades), filtering out noise and low-conviction signals.
4. The V2 trend filter + pyramiding logic successfully reduces drawdown by 46-53% in both variants.
5. **Conservative original (BaoshouGuncang)** remains the highest absolute return (+7.17%) but with worse risk profile.
