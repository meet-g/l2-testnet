# Trading Session Audit Report: `session_20261003_211704`

- **Session ID**: `session_20261003_211704`
- **Target Asset**: `BTC-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: PAPER TRADING SIMULATION
- **Session Start**: 2026-10-03T21:17:04
- **Session End**: 2026-10-04 15:06:38
- **Duration**: 1069m 33s (64173.6s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Executive Strategy Performance Audit

| Strategy | Trades | Win Rate | Volume (BTC) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Convexity_Cascade** | 4 | 0.0% | 0.4000 | -$10.18 | **$-12.18** | -3.6 bps | 0.00 | [`Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv) |
| **Hedged_Convexity** | 1 | 0.0% | 0.1000 | -$2.54 | **$-3.04** | -3.6 bps | 0.00 | [`Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv) |
| **Momentum_Expansion** | 1 | 0.0% | 0.1000 | -$2.54 | **$-2.64** | -3.1 bps | 0.00 | [`Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv) |

---

## 2. Individual Trade Logs per Strategy

### Strategy: `Convexity_Cascade`

- **Total Executed Trades**: 4 | **Wins**: 0 | **Losses**: 4 | **Win Rate**: 0.0% | **Net PnL**: $-12.18
- **Audit CSV**: [`strategies/Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv)

| # | Trade ID | Side | Size (BTC) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `CC-0002` | LONG | 0.1000 | 22:47:56 | $84,699.0 | 22:52:19 | $84,694.0 | 262.9s | `TIME_LIMIT` | -$2.54 | **-$3.04** | -3.6 bps |
| 2 | `CC-0003` | SHORT | 0.1000 | 23:05:01 | $84,720.0 | 23:08:58 | $84,721.0 | 236.9s | `TIME_LIMIT` | -$2.54 | **-$2.64** | -3.1 bps |
| 3 | `CC-0004` | LONG | 0.1000 | 01:02:39 | $84,798.0 | 01:05:39 | $84,797.0 | 180.0s | `TIME_LIMIT` | -$2.54 | **-$2.64** | -3.1 bps |
| 4 | `CC-0006` | LONG | 0.1000 | 09:12:40 | $85,139.0 | 09:15:40 | $85,126.0 | 180.1s | `TIME_LIMIT` | -$2.55 | **-$3.85** | -4.5 bps |

### Strategy: `Hedged_Convexity`

- **Total Executed Trades**: 1 | **Wins**: 0 | **Losses**: 1 | **Win Rate**: 0.0% | **Net PnL**: $-3.04
- **Audit CSV**: [`strategies/Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv)

| # | Trade ID | Side | Size (BTC) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `HC-0001` | LONG | 0.1000 | 22:47:56 | $84,699.0 | 22:52:19 | $84,694.0 | 262.9s | `TIME_LIMIT` | -$2.54 | **-$3.04** | -3.6 bps |

### Strategy: `Momentum_Expansion`

- **Total Executed Trades**: 1 | **Wins**: 0 | **Losses**: 1 | **Win Rate**: 0.0% | **Net PnL**: $-2.64
- **Audit CSV**: [`strategies/Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv)

| # | Trade ID | Side | Size (BTC) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `ME-0005` | LONG | 0.1000 | 01:02:39 | $84,798.0 | 01:05:39 | $84,797.0 | 180.0s | `TIME_LIMIT` | -$2.54 | **-$2.64** | -3.1 bps |

