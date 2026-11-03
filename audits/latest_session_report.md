# Trading Session Audit Report: `session_20261103_213243_999_3dd9`

- **Session ID**: `session_20261103_213243_999_3dd9`
- **Target Asset**: `BTC-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: PAPER TRADING SIMULATION
- **Session Start**: 2026-11-03T21:32:43
- **Session End**: 2026-11-03 21:32:45
- **Duration**: 0m 1s (1.6s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Executive Strategy Performance Audit

| Strategy | Trades | Win Rate | Volume (BTC) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Instant_FastFill** | 1 | 0.0% | 0.1000 | -$7.01 | **$-7.37** | -9.5 bps | 0.00 | [`Instant_FastFill.csv`](strategies/Instant_FastFill.csv) |
| **MicroPrice_FastFill** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`MicroPrice_FastFill.csv`](strategies/MicroPrice_FastFill.csv) |

---

## 2. Individual Trade Logs per Strategy

### Strategy: `Instant_FastFill`

- **Total Executed Trades**: 1 | **Wins**: 0 | **Losses**: 1 | **Win Rate**: 0.0% | **Net PnL**: $-7.37
- **Audit CSV**: [`strategies/Instant_FastFill.csv`](strategies/Instant_FastFill.csv)

| # | Trade ID | Side | Size (BTC) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `IFF-0001` | LONG | 0.1000 | 21:32:45 | $77,926.6 | 21:32:45 | $77,922.9 | 0.2s | `SESSION_SHUTDOWN` | -$7.01 | **-$7.37** | -9.5 bps |

### Strategy: `MicroPrice_FastFill`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/MicroPrice_FastFill.csv`](strategies/MicroPrice_FastFill.csv)

_No trades were opened/closed for MicroPrice_FastFill during this session._

