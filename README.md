# 🤖 Double MA Trading Bot

基于 Freqtrade 的双均线自动交易系统，采用**短线突破策略 15 分钟**策略变体。

## 策略来源

策略设计结合网络文献及实证研究：
- **双均线研究文献**：6 条均线（MA/EMA 20/60/120）密集/发散理论
- **短线突破策略**：15 分钟短線，MACD 過濾，分段止盈，勝率 78%+
- 趋势过滤法：200 MA 趨勢過濾，胜率59%
- 趋势跟踪法：EMA 50/200 排列確認趋势

## 核心参数

| 参数 | 值 |
|------|-----|
| 时间级别 | 15 分钟 |
| 均线 | MA/EMA 20/60/120 (6条) |
| 过滤器 | MACD + EMA50/200排列 |
| 每笔风险 | 5%（50U → $2.5止损） |
| 止盈 | 分两段：1:1平50%，1:2平50% |
| 最小赔率 | ≥ 1:2 |

## 项目结构

```
double-ma-bot/
├── README.md
├── requirements.txt
├── strategy/
│   ├── __init__.py
│   └── double_ma_zhonghuadan.py   # 短线突破策略策略
├── config/
│   ├── config.json                 # Freqtrade 配置（dry-run）
│   └── config.live.json            # 实盘配置（待部署）
├── scripts/
│   ├── download_data.sh            # 下载历史数据
│   └── run_backtest.sh             # 运行回测
├── database/
│   └── schema.sql                  # SQLite 表结构
└── .gitignore
```

## 快速开始

```bash
# 1. 安装依赖
uv venv && source .venv/bin/activate && pip install -r requirements.txt

# 2. 下载历史数据
bash scripts/download_data.sh

# 3. 回测
freqtrade backtesting --config config/config.json --strategy DoubleMAZhonghuadan

# 4. 模拟盘
freqtrade trade --config config/config.json --dry-run
```
