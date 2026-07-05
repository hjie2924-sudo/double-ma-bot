-- SQLite 交易数据库表结构
-- 用于存储交易信号、回测结果和实盘记录

-- 交易信号日志
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    pair TEXT NOT NULL,              -- 交易对，如 'BTC/USDT'
    timeframe TEXT NOT NULL,         -- 时间级别，如 '15m'
    signal_type TEXT NOT NULL,       -- 'long' / 'short'
    entry_price REAL,                -- 入场价
    stoploss_price REAL,             -- 止损价
    tp1_price REAL,                  -- 第一止盈价
    tp2_price REAL,                  -- 第二止盈价
    ma_spread REAL,                  -- 均线价差 %
    macd_value REAL,                 -- MACD 值
    macd_signal REAL,                -- MACD 信号线
    ema50 REAL,                      -- EMA50
    ema200 REAL,                     -- EMA200
    trend TEXT,                      -- 'bull' / 'bear'
    risk_per_trade REAL,             -- 每笔风险 %
    position_size REAL,              -- 仓位大小
    status TEXT DEFAULT 'pending'    -- 'pending' / 'entered' / 'tp1' / 'tp2' / 'stopped' / 'closed'
);

-- 交易记录（含结果）
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER REFERENCES signals(id),
    pair TEXT NOT NULL,
    direction TEXT NOT NULL,         -- 'long' / 'short'
    entry_time DATETIME,
    exit_time DATETIME,
    entry_price REAL,
    exit_price REAL,
    amount REAL,                     -- 交易数量
    profit_loss REAL,                -- 盈亏（绝对值）
    profit_loss_pct REAL,            -- 盈亏 %
    exit_reason TEXT,                -- 'tp1' / 'tp2' / 'stop_loss' / 'manual'
    max_drawdown_pct REAL,           -- 最大回撤 %
    fees REAL DEFAULT 0,             -- 手续费
    notes TEXT
);

-- 回测结果
CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    strategy TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    pair TEXT NOT NULL,
    start_date DATE,
    end_date DATE,
    total_trades INTEGER,
    win_trades INTEGER,
    loss_trades INTEGER,
    win_rate REAL,                   -- 胜率 %
    avg_profit_pct REAL,             -- 平均盈利 %
    avg_loss_pct REAL,               -- 平均亏损 %
    profit_factor REAL,              -- 盈亏比
    total_profit_pct REAL,           -- 总收益率 %
    max_drawdown_pct REAL,           -- 最大回撤 %
    sharpe_ratio REAL,               -- 夏普比率
    raw_results TEXT                 -- JSON 格式完整结果
);

-- 均线状态快照（定期记录）
CREATE TABLE IF NOT EXISTS ma_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    pair TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    close_price REAL,
    ma20 REAL,
    ma60 REAL,
    ma120 REAL,
    ema20 REAL,
    ema60 REAL,
    ema120 REAL,
    ema50 REAL,
    ema200 REAL,
    ma_spread REAL,
    is_congested INTEGER DEFAULT 0,  -- 0/1 是否均线密集
    trend TEXT,                      -- 'bull' / 'bear' / 'congested'
    macd REAL,
    macdsignal REAL,
    notes TEXT
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_signals_pair_time ON signals(pair, timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_pair_time ON trades(pair, entry_time);
CREATE INDEX IF NOT EXISTS idx_backtest_strategy ON backtest_results(strategy, run_time);
CREATE INDEX IF NOT EXISTS idx_ma_snapshots_pair_time ON ma_snapshots(pair, timestamp);
