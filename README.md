# 双均线自动交易系统 (Double MA Bot)

基于 Freqtrade 的双均线 15 分钟期货自动交易系统。

## 运行架构

```
┌──────────────────┐     ┌─────────────────────┐
│  保守 (8082)      │     │  激进 (8083)         │
│  BaoshouGuncang  │     │  JijinGuncangV3     │
│  30x / 3% SL     │     │  90x / 2.5% SL      │
│  金字塔滚仓×2    │     │  金字塔滚仓×2       │
│  干运行(50U)     │     │  干运行(50U)        │
└──────────────────┘     └─────────────────────┘
         │                         │
         └─────────┬───────────────┘
                   ▼
           OKX Futures (BTC/ETH/SOL)
```

## 策略核心逻辑

双均线突破策略，基于三条 SMA 和三条 EMA 的密集/发散判断，配合 MACD 确认入场。

### 入场条件（做多示例）
1. 均线密集：MA20 与 MA120 价差 < 阈值（默认 2.5%）
2. K 线连续 2 根站上 MA20（确认突破有效）
3. MACD 金叉（柱状图由负转正）
4. EMA50 > EMA200（大趋势向上）

### 出场条件
1. 均线排列反转（多头→空头）
2. MACD 死叉 + 趋势转向
3. K 线跌破 MA20 连续 2 根

### 风控机制
- 硬止损：3%（保守）/ 2.5%（激进）
- 分段止盈：1:1 平 50%，1:2 平剩余
- 金字塔滚仓（浮盈加仓，不超过 2 次）
- MACD 反转减仓（激进版）
- 熔断：连亏 3 次停 24h

## 项目结构

```
double-ma-bot/
├── strategy/                  # 策略代码
│   ├── baoshou_guncang.py     # 保守系列（父类，正在运行）
│   ├── baoshou_guncang_v2.py  # 保守 V2（优化版）
│   ├── baoshou_guncang_v3.py  # 保守 V3（V4 Lite 入场逻辑）
│   ├── baoshou_backtest.py    # 保守回测场景
│   ├── baoshou_opt.py         # 保守优化参数
│   ├── jijin_guncang.py       # 激进系列（父类）
│   ├── jijin_guncang_v2.py    # 激进 V2
│   ├── jijin_guncang_v3.py    # 激进 V3（正在运行）
│   ├── jijin_backtest.py      # 激进回测场景
│   └── archive/               # 历史版本归档
├── config/
│   ├── config.json            # 默认配置（V4入口信号）
│   ├── config_lite.json       # 保守实例配置（运行中）
│   └── config_zhonghuadan.json# 激进实例配置（运行中）
├── scripts/
│   ├── download_data.sh       # 下载历史数据
│   ├── run_backtest.sh        # 运行回测
│   └── health_check.py        # 双实例健康监测
└── docs/                      # 详细文档（见 AI_CONTEXT.md）
```

## 当前运行状态

| 实例 | 策略 | 端口 | 杠杆 | 涨跌 | 钱包 | PID |
|------|------|------|------|------|------|-----|
| 保守 | BaoshouGuncang | 8082 | 30x | 3% | 50U | 137033 |
| 激进 | JijinGuncangV3 | 8083 | 90x | 2.5% | 50U | 137158 |

## 快速开始

```bash
# 环境
uv venv && source .venv/bin/activate && pip install -r requirements.txt

# 下载数据
bash scripts/download_data.sh

# 回测
freqtrade backtesting --config config/config_lite.json --strategy-path strategy

# 干运行
freqtrade trade --config config/config_lite.json --dry-run --strategy-path strategy -v
```

## 优化历史

| 版本 | 关键变化 | 回测结果 |
|------|---------|---------|
| 中华单 V1 | 均线密集 + MACD + 分段止盈 | +7.17%, Sharpe 1.89 |
| V2 | 放宽条件 + 降低止损 | +1.19%, Win% 50% |
| V3 | 折中平衡 | 实盘运行中 |
| V4 | ADX/BB 震荡过滤 + 完整风控 | 待验证 |
