# AI Context — 双均线自动交易系统

> 本文档为未来 AI 代理（或人类维护者）提供完整的项目上下文。
> 阅读本文档后应能独立理解、维护和优化本系统。

---

## 一、项目定位

**双均线自动交易系统** 是一个运行在 Freqtrade 框架上的加密货币期货自动交易机器人。核心策略基于双均线密集/发散 + MACD 确认短线交易逻辑，采用双实例并行架构（保守 + 激进）。

**目标**：在 BTC/ETH/SOL 15分钟级别上持续产生正期望收益，同时通过严格风控防止爆仓。

---

## 二、当前运行状态（2026-07-17）

### 进程信息

| 实例 | 策略类 | 杠杆 | 止损 | 端口 | PID | 启动时间 |
|------|--------|------|------|------|-----|---------|
| 保守 | BaoshouGuncang | 30x | 3% | 8082 | 137033 | 7月16日 |
| 激进 | JijinGuncangV3 | 90x | 2.5% | 8083 | 137158 | 7月16日 |

两个实例均运行在 **dry-run（模拟盘）** 模式，启动资金 50 USDT，交易对 BTC/ETH/SOL。

### 关键配置

- 保守：`config/config_lite.json` → strategy: `BaoshouGuncang`
- 激进：`config/config_zhonghuadan.json` → strategy: `JijinGuncangV3`
- 均通过 Clash 代理（127.0.0.1:7897）连接 OKX
- 保守使用 `tradesv3.lite.dryrun.sqlite` 数据库
- 激进使用 `tradesv3.zhonghuadan.dryrun.sqlite` 数据库

### 健康监测

`scripts/health_check.py` 定时（每30分钟）检查：
1. 进程存活 → 死了自动重启
2. API 响应（8082/8083 端口）→ 不通自动重启
3. 数据流状态（WS 断连检测）→ 断连自动重启
4. 防重复报警（同一故障 2h 内不重复报）

---

## 三、策略版本树

```
                    ┌─ BaoshouGuncang (V1, 原版, 正在跑)
                    │  3% SL, 金字塔50%/30%
                    │  回测: 25笔, +7.17%, Win% 36%
                    │
Baoshou(保守) ──────┼─ BaoshouGuncangV2
 30x杠杆            │  入场收紧, 保留ADX过滤
                    │  回测: 6笔, +1.19%, Win% 50%
                    │
                    └─ BaoshouGuncangV3 (最新)
                       移除ADX, 回退到V4 Lite入场
                       MACD反转减仓, 移动止盈

                    ┌─ JijinGuncang (V1, 原版)
                    │  2% SL, 金字塔50%/30%
                    │  回测: 38笔, -3.20%, Win% 31.6%
                    │
Jijin(激进) ────────┼─ JijinGuncangV2 (优化版)
 90x杠杆            │  入场收紧, 保留ADX
                    │  回测: 13笔, -0.19%, Win% 38.5%
                    │
                    └─ JijinGuncangV3 (正在跑, 最新)
                       移除ADX震荡过滤
                       2.5% SL, MACD反转减仓

[archive/] ───────── DoubleMAZhonghuadan V1~V4 (原始策略, 已归档)
                    Zhonghuadan (纯币哥逻辑复刻)
                    DoubleMAPure (极简版)
```

### 版本演进说明

- **V1 → V2**：入场条件收紧 → 交易量大幅下降（-76%），但胜率提升（36%→50%），回撤减半
- **V2 → V3**：回退 V2 的部分收紧（移除 ADX 震荡过滤），因为 V2 把信号砍太狠（6笔/6月不够统计意义），折中找平衡
- **V4 存在但未部署**：ADX/BB 震荡过滤 + 完整风控套件。需 walk-forward 验证后再决定是否部署

---

## 四、核心代码文件

### `strategy/baoshou_guncang.py` [⚠️正在运行]
双均线突破策略基类（保守版）。核心指标：6条均线(MA/EMA 20/60/120)、MACD、EMA50/200趋势过滤。
入场：均线密集 + K线突破MA20(连续2根) + MACD交叉 + 趋势确认
出场：均线排列反转 / MACD反转 / K线跌破MA20
风控：Pyramid加仓(50%/30%比例, max 2次) + 硬止损3%

### `strategy/jijin_guncang_v3.py` [⚠️正在运行]
继承 JijinGuncangV2，移除 ADX 震荡过滤。入场条件保留：均线密集 + 突破 + MACD + 趋势 + 回踩。
杠杆 90x，止损 2.5%，止盈 4R(10%)。

### `strategy/baoshou_guncang_v3.py` [最新，未运行]
在 BaoshouGuncang(原版) 基础上增加了：
- V4 Lite 入场逻辑（保留 EMA50/200 + MACD，移除 ADX/BB）
- MACD 反转减仓
- 2R(6%) 移动止盈到 1R(3%)

### `strategy/jijin_guncang.py` / `baoshou_guncang_v2.py` [父类/历史]
提供基础的 populate_indicators 指标计算。V2 版本包含 ADX 震荡过滤（已被 V3 移除）。

### `scripts/health_check.py` [⚠️正在运行]
双实例健康监测守护脚本。每30分钟由 cron 调用一次。API不通/WS断连 → 自动重启进程。

---

## 五、关键参数一览

### 均线参数
| 参数 | 值 | 说明 |
|------|-----|------|
| 均线密集阈值 | 2.5% | MA20与MA120价差 |
| MA 20/60/120 | SMA | 短/中/长均线 |
| EMA 20/60/120 | EMA | 确认用 |
| EMA 50/200 | EMA | 趋势过滤 |

### MACD 参数
| 参数 | 值 |
|------|-----|
| Fast | 12 |
| Slow | 26 |
| Signal | 9 |

### 风控参数
| 参数 | 保守 | 激进 |
|------|------|------|
| 杠杆 | 30x | 90x |
| 硬止损 | 3%(1R) | 2.5%(1R) |
| 加仓1 | 盈利3% +50% | 盈利2.5% +50% |
| 加仓2 | 盈利6% +30% | 盈利5% +30% |
| 止盈 | 12%(4R)清仓 | 10%(4R)清仓 |
| 熔断 | 机制已定义 | 机制已定义 |

---

## 六、文献依据

策略设计参考以下量化金融研究结论：

1. **双均线交叉有效性**：移动平均线在趋势市场中有正期望（Brock et al. 1992, JOF），但在震荡市中表现退化
2. **MACD 过滤**：MACD 作为辅助确认信号可减少约 30% 假信号（投资百科, ADX 过滤研究）
3. **金字塔加仓**：等比例加仓在正期望策略中优于固定仓位（Kelly 准则衍生的 Fractional Kelly）
4. **ADX 过滤的取舍**：ADX<20 过滤可回避震荡市，但在 15m 时间框架上误杀比率高（V2→V3 回退原因）
5. **过拟合防控**：Bailey, Borwein, López de Prado & Zhu (2014) 证明参数遍历越多样本外表现越差。本系统的参数空间经过严格限制（仅 5 个浮点参数）
6. **幸存者偏差**：AQR 研究显示回测数据忽略已退市资产会高估收益 1-3%/年（美股）/ 10-20%/年（加密）。本系统仅交易 BTC/ETH/SOL 三大资产，幸存者偏差影响极小

---

## 七、已知限制与风险

1. **回测样本量不足**：25笔交易在量化领域被认为太少。需实盘积累 100-300 笔后才具备统计意义
2. **15m 级别信噪比低**：短时间框架的信号中约 60-70% 是市场噪音
3. **ADX 过滤的牺牲**：当前的 V3 策略选择了信号量而不是信号质量。是否会降低 Sharpe 需等待实盘数据验证
4. **滚仓双刃剑**：浮盈加仓在盈利单上放大收益，在亏损单上放大亏损。3% 止损 + 2次加仓 = 实际风险可能远超 3%
5. **策略 Decay**：任何策略都有有效期。当前逻辑在特定市场状态下有效（Trending + 波动>ADX20），如果市场状态切换，策略可能失效。需持续监测 Sharpe 和 Win% 的滚动变化

---

## 八、待办优化方向

基于文献调研，以下优化方向按优先级排列：

### P0: 累积样本量（正在做）
- 实盘干运行至少跑满 300 笔交易再做统计判断
- 目前每日约 1-5 笔，预计需要 2-4 个月

### P1: 建立 Walk-Forward 验证流程
- 当前回测全部是样本内。需建立 split:train/validate/test 三阶段
- 使用 Freqtrade `--timerange` 划分数据
- 每次优化后必须在 validate 集验证通过才能部署

### P2: BTC 市场状态过滤（Regime Gate）
- 当前无 BTC tape filter。按 MarketTrace 建议，在 BTC 短时剧烈波动（5分钟>1.5%）时应禁止 ALT 开新仓
- 实施方式：增加 `confirm_trade_entry` 检查 BTC 5分钟收益率
- 预期效果：减少在流动性事件中开仓的概率

### P3: 基于滚动 Sharpe 的策略健康监测
- 增加 30 天滚动 Sharpe 计算
- 当滚动 Sharpe < 0 持续 60 天以上 → 告警需人工介入
- 当滚动 Sharpe < -0.5 持续 30 天 → 自动暂停

### P4: Fractional Kelly 仓位管理
- 当前仓位通过固定比例反推（可接受亏损 ÷ 止损率）。可改为基于历史 Win% 和 AvgRR 的 Kelly 公式
- Fractional Kelly（25% 或 50%）防止过激
- 需积累足够交易后才有效（>100笔）

---

## 九、运维命令速查

```bash
# 查看进程
ps aux | grep freqtrade

# 查看 API 状态
curl -s -u admin:admin http://127.0.0.1:8082/api/v1/profit

# 查看日志（保守）
tail -f user_data/logs/freqtrade*.log

# 重启实例
cd ~/double-ma-bot && .venv/bin/freqtrade trade --config config/config_lite.json --dry-run --strategy-path strategy -v

# 停止实例
kill <PID>

# 重新下载数据
bash scripts/download_data.sh

# 运行回测
freqtrade backtesting --config config/config_lite.json --strategy-path strategy --timerange 20260103-20260715
```
