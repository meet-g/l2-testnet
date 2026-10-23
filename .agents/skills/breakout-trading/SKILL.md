---
name: breakout-trading
description: >-
  Use this skill when automating order placement, stop loss, take profit, position tracking,
  and risk guardrails on the Breakout Prop Firm web terminal (breakoutprop.com).
---

# Breakout Prop Trading Automation Skill

This skill provides the operational runbook and toolchain for executing automated orders on the **Breakout Prop Firm** platform using browser automation (Playwright / CDP) and browser MCP tools.

## Architecture & Primitives

- **Execution Engine**: [`engine/breakout_executor.py`](file:///D:/L2%20-%20Testnet/engine/breakout_executor.py) (`BreakoutExecutor`)
- **CLI Test & Harness**: [`scripts/breakout_cli.py`](file:///D:/L2%20-%20Testnet/scripts/breakout_cli.py)
- **Session Cache**: `data/breakout_profile/` (stores persistent browser cookies/tokens)

---

## Operating Modes

### Mode 1: Chrome DevTools Protocol (CDP) - Recommended for Live Supervision
Start your regular Chrome browser with remote debugging enabled:
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 "https://portal.breakoutprop.com"
```
Once logged in, any script or agent call will instantly attach without 2FA or Cloudflare interruptions.

### Mode 2: Persistent Profile Mode
Launches Chromium with persistent storage in `data/breakout_profile`. 
Run the setup once:
```powershell
python scripts/breakout_cli.py --login
```
Complete login and 2FA in the opened window. All cookies and credentials persist for future headless runs.

### Mode 3: Interactive Visual Teaching Mode (One-by-One Action Recorder)
Launch the interactive teaching wizard to click and map every order action on the screen:
```powershell
python scripts/teach_breakout.py
```
Or attach to an already open Chrome instance:
```powershell
python scripts/teach_breakout.py --cdp
```
All mapped elements are saved to [`data/breakout_selectors.json`](file:///D:/L2%20-%20Testnet/data/breakout_selectors.json) and automatically used by the execution engine.

---

## Quick Reference CLI Commands

### 1. Check Account Status & Open Positions
```powershell
python scripts/breakout_cli.py --status
```
Displays:
- Account Balance & Equity
- Current Daily Drawdown vs. Defensive Threshold (3.5% vs. 4.0% limit)
- Active Open Positions (Entry Px, Mark Px, Unrealized PnL)

### 2. Place Buy / Long Order with TP & SL
```powershell
python scripts/breakout_cli.py --buy --symbol BTC-USD --size 100 --tp 70000 --sl 67000
```

### 3. Place Sell / Short Order with TP & SL
```powershell
python scripts/breakout_cli.py --sell --symbol BTC-USD --size 100 --tp 66000 --sl 68500
```

### 4. Close Active Position
```powershell
python scripts/breakout_cli.py --close --symbol BTC-USD
```

### 5. Emergency Flatten (Panic Button)
```powershell
python scripts/breakout_cli.py --panic
```
Cancels all pending resting orders and market-closes all active positions.

### 6. Inspect Terminal Selectors & Elements
```powershell
python scripts/breakout_cli.py --inspect
```
Dumps visible input fields, button test-IDs, and tables to calibrate selectors when Breakout updates their UI.

---

## Prop Firm Risk Rules & Circuit Breaker

| Prop Rule | Limit | Defensive Action |
| :--- | :--- | :--- |
| **Daily Drawdown** | **4.0%** | Hard circuit breaker halts order placement at **3.5%** |
| **Max Trailing Drawdown** | **8.0%** | Blocks new positions and alerts for manual review |
| **Stop Loss Requirement** | Mandatory | All orders should pass explicit `stop_loss_price` |

---

## Future Integration with `main.py`
In `main.py`, substitute or bridge `LiveOrderExecutor` with `BreakoutExecutor`:
```python
from engine.breakout_executor import BreakoutExecutor, OrderIntent, OrderSide

# In runner initialization:
self.breakout = BreakoutExecutor(headless=True)
await self.breakout.connect()

# On signal trigger:
if signal_score >= entry_threshold:
    await self.breakout.place_order(
        OrderIntent(side=OrderSide.BUY, symbol="BTC-USD", size=100.0, stop_loss_price=sl_px, take_profit_price=tp_px)
    )
```
