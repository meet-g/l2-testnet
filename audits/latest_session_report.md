# Trading Session Audit Report: `session_20261026_130115_267_34a8`

- **Session ID**: `session_20261026_130115_267_34a8`
- **Target Asset**: `HYPE-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: PAPER TRADING SIMULATION
- **Session Start**: 2026-10-26T13:01:15
- **Session End**: 2026-10-26 13:58:56
- **Duration**: 57m 41s (3461.2s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Executive Strategy Performance Audit

| Strategy | Trades | Win Rate | Volume (HYPE) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Hedged_Convexity** | 2 | 50.0% | 221.1000 | -$5.10 | **$-6.70** | -3.9 bps | 0.31 | [`Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv) |
| **Momentum_Expansion** | 15 | 60.0% | 1651.1500 | -$38.25 | **+$13.33** | +1.0 bps | 1.35 | [`Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv) |

---

## 2. Individual Trade Logs per Strategy

### Strategy: `Hedged_Convexity`

- **Total Executed Trades**: 2 | **Wins**: 1 | **Losses**: 1 | **Win Rate**: 50.0% | **Net PnL**: $-6.70
- **Audit CSV**: [`strategies/Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `HC-0010` | SHORT | 110.2500 | 13:48:11 | $77.1 | 13:48:22 | $77.2 | 11.0s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$9.72** | -11.4 bps |
| 2 | `HC-0016` | SHORT | 110.8500 | 13:57:27 | $76.7 | 13:57:40 | $76.6 | 13.0s | `TRAILING_STOP` | -$2.55 | **+$3.01** | +3.5 bps |

### Strategy: `Momentum_Expansion`

- **Total Executed Trades**: 15 | **Wins**: 9 | **Losses**: 6 | **Win Rate**: 60.0% | **Net PnL**: $+13.33
- **Audit CSV**: [`strategies/Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `ME-0001` | LONG | 109.9100 | 13:03:43 | $77.3 | 13:04:04 | $77.4 | 21.2s | `TRAILING_STOP` | -$2.55 | **+$2.07** | +2.4 bps |
| 2 | `ME-0002` | LONG | 109.8600 | 13:07:13 | $77.4 | 13:07:45 | $77.4 | 32.2s | `TRAILING_STOP` | -$2.55 | **+$2.72** | +3.2 bps |
| 3 | `ME-0003` | SHORT | 109.8600 | 13:23:11 | $77.4 | 13:23:35 | $77.4 | 23.5s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.27** | -8.6 bps |
| 4 | `ME-0004` | SHORT | 109.9800 | 13:26:59 | $77.3 | 13:27:06 | $77.3 | 7.5s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.28** | -8.6 bps |
| 5 | `ME-0005` | SHORT | 109.9400 | 13:31:03 | $77.3 | 13:31:14 | $77.3 | 10.7s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.07** | -7.1 bps |
| 6 | `ME-0006` | LONG | 109.9500 | 13:36:36 | $77.3 | 13:36:42 | $77.3 | 5.3s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$5.74** | -6.8 bps |
| 7 | `ME-0007` | SHORT | 109.7100 | 13:41:01 | $77.5 | 13:41:48 | $77.4 | 47.5s | `TRAILING_STOP` | -$2.55 | **+$9.58** | +11.3 bps |
| 8 | `ME-0008` | SHORT | 109.9600 | 13:43:14 | $77.3 | 13:43:36 | $77.2 | 22.0s | `TRAILING_STOP` | -$2.55 | **+$8.95** | +10.5 bps |
| 9 | `ME-0009` | LONG | 109.8800 | 13:45:41 | $77.4 | 13:45:56 | $77.4 | 15.1s | `TRAILING_STOP` | -$2.55 | **+$3.99** | +4.7 bps |
| 10 | `ME-0011` | SHORT | 110.1500 | 13:49:33 | $77.2 | 13:49:58 | $77.1 | 25.1s | `TRAILING_STOP` | -$2.55 | **+$0.60** | +0.7 bps |
| 11 | `ME-0012` | LONG | 110.0500 | 13:50:30 | $77.2 | 13:50:46 | $77.2 | 16.0s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$5.63** | -6.6 bps |
| 12 | `ME-0013` | SHORT | 110.2000 | 13:53:02 | $77.1 | 13:53:49 | $77.0 | 46.5s | `TRAILING_STOP` | -$2.55 | **+$8.70** | +10.2 bps |
| 13 | `ME-0014` | SHORT | 110.3300 | 13:53:54 | $77.0 | 13:54:37 | $77.0 | 42.6s | `TRAILING_STOP` | -$2.55 | **+$5.96** | +7.0 bps |
| 14 | `ME-0015` | SHORT | 110.5300 | 13:56:09 | $76.9 | 13:56:41 | $76.8 | 32.0s | `TRAILING_STOP` | -$2.55 | **+$9.07** | +10.7 bps |
| 15 | `ME-0017` | SHORT | 110.8400 | 13:57:52 | $76.7 | 13:58:05 | $76.7 | 13.3s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.32** | -7.4 bps |

