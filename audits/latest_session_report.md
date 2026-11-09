# Trading Session Audit Report: `session_20261109_180038_591_1196`

- **Session ID**: `session_20261109_180038_591_1196`
- **Target Asset**: `xyz:SKHX-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: PAPER TRADING SIMULATION
- **Session Start**: 2026-11-09T18:00:38
- **Session End**: 2026-11-09 18:11:48
- **Duration**: 11m 9s (669.4s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Executive Strategy Performance Audit

| Strategy | Trades | Win Rate | Volume (XYZ:SKHX) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Convexity_Cascade** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv) |
| **Hedged_Convexity** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv) |
| **Momentum_Expansion** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv) |
| **Queue_Replenishment** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Queue_Replenishment.csv`](strategies/Queue_Replenishment.csv) |
| **Stock_Microstructure_Alpha** | 3 | 0.0% | 30.0000 | -$4.83 | **$-16.73** | -6.2 bps | 0.00 | [`Stock_Microstructure_Alpha.csv`](strategies/Stock_Microstructure_Alpha.csv) |

---

## 2. Individual Trade Logs per Strategy

### Strategy: `Convexity_Cascade`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv)

_No trades were opened/closed for Convexity_Cascade during this session._

### Strategy: `Hedged_Convexity`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv)

_No trades were opened/closed for Hedged_Convexity during this session._

### Strategy: `Momentum_Expansion`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv)

_No trades were opened/closed for Momentum_Expansion during this session._

### Strategy: `Queue_Replenishment`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/Queue_Replenishment.csv`](strategies/Queue_Replenishment.csv)

_No trades were opened/closed for Queue_Replenishment during this session._

### Strategy: `Stock_Microstructure_Alpha`

- **Total Executed Trades**: 3 | **Wins**: 0 | **Losses**: 3 | **Win Rate**: 0.0% | **Net PnL**: $-16.73
- **Audit CSV**: [`strategies/Stock_Microstructure_Alpha.csv`](strategies/Stock_Microstructure_Alpha.csv)

| # | Trade ID | Side | Size (XYZ:SKHX) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `SMA-0001` | LONG | 10.0000 | 18:00:49 | $895.0 | 18:01:14 | $894.4 | 24.1s | `STOP_LOSS` | -$1.61 | **-$7.41** | -8.3 bps |
| 2 | `SMA-0002` | LONG | 10.0000 | 18:05:26 | $894.7 | 18:05:42 | $893.9 | 16.1s | `STOP_LOSS` | -$1.61 | **-$9.11** | -10.2 bps |
| 3 | `SMA-0003` | LONG | 10.0000 | 18:10:23 | $893.4 | 18:10:50 | $893.5 | 26.9s | `TRAILING_STOP` | -$1.61 | **-$0.21** | -0.2 bps |

