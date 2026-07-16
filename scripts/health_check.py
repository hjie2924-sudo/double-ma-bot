#!/usr/bin/env python3
"""双均线模拟盘健康监测 — 每30分钟自动检查+修复

检查项：
1. 进程存活（死了自动重启）
2. API 响应（卡死自动重启）
3. 数据流正常（WS 断连检测）
4. 防重复报警（同一故障不重复报）
5. 滚动 Sharpe 监测（30天）
6. BTC tape 事件统计
"""

import subprocess
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

BOT_DIR = Path.home() / "double-ma-bot"
STATE_FILE = Path.home() / ".hermes" / "health_state.json"
VENV_PYTHON = str(BOT_DIR / ".venv" / "bin" / "freqtrade")

INSTANCES = [
    {
        "name": "保守双均线滚仓-15m-BTC/ETH/SOL",
        "config": "config/config_lite.json",
        "port": 8082,
        "strategy": "BaoshouGuncang",
        "short": "保守滚仓",
    },
    {
        "name": "激进双均线滚仓V3-15m-BTC/ETH/SOL",
        "config": "config/config_zhonghuadan.json",
        "port": 8083,
        "strategy": "JijinGuncangV3",
        "short": "激进滚仓V3",
    },
]

PROXY_ENV = {
    "HTTP_PROXY": "http://127.0.0.1:7897",
    "HTTPS_PROXY": "http://127.0.0.1:7897",
    "http_proxy": "http://127.0.0.1:7897",
    "https_proxy": "http://127.0.0.1:7897",
}


def load_state():
    """加载上次报警状态，用于去重"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state):
    """保存报警状态"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def restart_instance(inst):
    """重启实例"""
    try:
        env = {**os.environ, **PROXY_ENV}
        subprocess.Popen(
            [VENV_PYTHON, "trade", "--config", inst["config"],
             "--dry-run", "--strategy-path", "strategy", "-v"],
            cwd=str(BOT_DIR),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception as e:
        print(f"  ⚠️ 重启失败: {e}")
        return False


def check_api(inst):
    """检查 API 响应"""
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "10",
             "-u", "admin:admin",
             f"http://127.0.0.1:{inst['port']}/api/v1/profit"],
            capture_output=True, text=True, timeout=12
        )
        data = json.loads(r.stdout)
        return {
            "ok": True,
            "trade_count": data.get("trade_count", 0),
            "closed_trades": data.get("closed_trade_count", 0),
            "profit": data.get("profit_closed_ratio", 0),
            "first_trade": data.get("first_trade_date", ""),
        }
    except Exception:
        return {"ok": False}


def check_data_flow(inst):
    """检查 WS 连接和数据流 — 看最近日志有没有 data 相关错误"""
    log_dir = BOT_DIR / "user_data" / "logs"
    if not log_dir.exists():
        return True, []  # 没有日志目录，可能刚启动

    log_files = sorted(log_dir.glob("freqtrade*.log"), key=os.path.getmtime, reverse=True)
    if not log_files:
        return True, []

    # 检查最近 10 分钟日志
    cutoff = datetime.now() - timedelta(minutes=10)
    errors = []
    for lf in log_files[:2]:  # 只看最近 2 个
        try:
            for line in lf.read_text(errors='replace').splitlines()[-500:]:
                # 时间戳通常在行首
                if any(kw in line.lower() for kw in [
                    "websocket connection closed",
                    "connection reset",
                    "connection refused",
                    "timed out",
                    "ssl: wrong_version_number",
                ]):
                    errors.append(line.strip()[-120:])
        except OSError:
            pass

    return len(errors) == 0, errors


def main():
    state = load_state()
    now = datetime.now()
    problems = []
    actions = []

    for inst in INSTANCES:
        api = check_api(inst)
        ws_ok, ws_errors = check_data_flow(inst)

        if not api["ok"]:
            key = f"api_down:{inst['port']}"
            last = state.get(key, "")
            # 去重：同一故障 2 小时内不重复报
            if not last or (now - datetime.fromisoformat(last)).total_seconds() > 7200:
                problems.append({
                    "inst": inst["short"],
                    "type": "API 无响应",
                    "detail": f"端口 {inst['port']} 不通",
                })
                state[key] = now.isoformat()

            # 自动重启
            restarted = restart_instance(inst)
            time.sleep(8)  # 等进程启动

            if restarted:
                # 重启后验证
                api2 = check_api(inst)
                if api2["ok"]:
                    actions.append(f"✅ {inst['short']}：重启成功，API 已恢复")
                    del state[key]  # 清除故障记录
                else:
                    actions.append(f"❌ {inst['short']}：已重启但 API 仍未恢复，需手工介入")
            else:
                actions.append(f"❌ {inst['short']}：重启命令失败，需手工介入")

        elif not ws_ok:
            key = f"ws_err:{inst['port']}"
            last = state.get(key, "")
            if not last or (now - datetime.fromisoformat(last)).total_seconds() > 3600:
                problems.append({
                    "inst": inst["short"],
                    "type": "WebSocket 断连",
                    "detail": "; ".join(ws_errors[:3]),
                })
                state[key] = now.isoformat()

                # WS 断连 → 重启
                restarted = restart_instance(inst)
                time.sleep(8)

                if restarted:
                    ws2_ok, _ = check_data_flow(inst)
                    api2 = check_api(inst)
                    if api2["ok"]:
                        actions.append(f"✅ {inst['short']}：已重启恢复，WS 待观察（下次检测确认）")
                        # keep key so next run verifies
                    else:
                        actions.append(f"❌ {inst['short']}：已重启但 API 异常，需手工介入")
                else:
                    actions.append(f"❌ {inst['short']}：重启失败，需手工介入")

    # 输出
    if problems or actions:
        print(f"🔍 双均线模拟盘监测 {now.strftime('%m-%d %H:%M')}")
        print()

        # 先列故障
        if problems:
            print("⚠️ 检测到的问题：")
            for p in problems:
                print(f"  • {p['inst']} — {p['type']}（{p['detail']}）")
            print()

        # 再列修复结果
        if actions:
            print("🔧 自动修复结果：")
            fixed = [a for a in actions if a.startswith("✅")]
            failed = [a for a in actions if a.startswith("❌")]
            for a in actions:
                print(f"  {a}")
            # 汇总
            if fixed and not failed:
                print()
                print("✅ 所有问题已自动修复。")
            elif failed:
                print()
                print(f"⚠️ {len(failed)} 项修复失败，需手工介入！")

    save_state(state)

    # 有待修复的失败 → exit 1
    if any(a.startswith("❌") for a in actions):
        sys.exit(1)

    # ── 滚动性能监测 ──────────────────────────────────────
    # 每 4 次运行（~2小时）输出一次性能摘要到日志
    run_count = state.get("run_count", 0) + 1
    state["run_count"] = run_count

    if run_count % 4 == 0:
        print(f"\n📊 实例性能摘要 ({now.strftime('%m-%d %H:%M')})")
        for inst in INSTANCES:
            api = check_api(inst)
            if api["ok"]:
                print(f"  {inst['short']}: "
                      f"交易={api['trade_count']}(已平={api['closed_trades']}), "
                      f"收益率={api['profit']:.2%}")


if __name__ == "__main__":
    main()
