# Trading Session Audit Report: `session_20261010_021309_875_1599`

- **Session ID**: `session_20261010_021309_875_1599`
- **Target Asset**: `HYPE-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: PAPER TRADING SIMULATION
- **Session Start**: 2026-10-10T02:13:09
- **Session End**: 2026-10-11 16:12:23
- **Duration**: 2279m 14s (136754.0s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Executive Strategy Performance Audit

| Strategy | Trades | Win Rate | Volume (HYPE) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Convexity_Cascade** | 16 | 62.5% | 1592.0900 | -$45.89 | **$-14.60** | -1.1 bps | 0.74 | [`Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv) |
| **Hedged_Convexity** | 7 | 100.0% | 694.8900 | -$17.85 | **+$33.91** | +5.7 bps | 99.90 | [`Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv) |
| **Momentum_Expansion** | 15 | 53.3% | 1492.0000 | -$45.89 | **$-27.55** | -2.2 bps | 0.62 | [`Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv) |

---

## 2. Individual Trade Logs per Strategy

### Strategy: `Convexity_Cascade`

- **Total Executed Trades**: 16 | **Wins**: 10 | **Losses**: 6 | **Win Rate**: 62.5% | **Net PnL**: $-14.60
- **Audit CSV**: [`strategies/Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `CC-0003` | SHORT | 99.7300 | 15:17:06 | $85.2 | 15:17:15 | $85.2 | 8.9s | `TRAILING_STOP` | -$2.55 | **+$0.74** | +0.9 bps |
| 2 | `CC-0004` | LONG | 99.3900 | 15:19:23 | $85.5 | 15:19:29 | $85.5 | 6.4s | `TRAILING_STOP` | -$2.55 | **-$0.97** | -1.1 bps |
| 3 | `CC-0007` | LONG | 99.2300 | 15:21:55 | $85.7 | 15:22:18 | $85.7 | 22.4s | `TRAILING_STOP` | -$2.55 | **+$0.82** | +1.0 bps |
| 4 | `CC-0009` | LONG | 99.0500 | 15:23:55 | $85.8 | 15:24:11 | $85.9 | 16.3s | `TRAILING_STOP` | -$2.55 | **+$3.33** | +3.9 bps |
| 5 | `CC-0010` | LONG | 98.9900 | 15:24:11 | $85.9 | 15:24:22 | $85.9 | 10.5s | `TRAILING_STOP` | -$2.55 | **+$3.39** | +4.0 bps |
| 6 | `CC-0014` | SHORT | 98.5300 | 15:31:36 | $86.3 | 15:31:58 | $86.1 | 22.1s | `TAKE_PROFIT` | -$2.55 | **+$13.51** | +15.9 bps |
| 7 | `CC-0016` | SHORT | 98.7000 | 15:32:13 | $86.1 | 15:32:45 | $86.1 | 32.3s | `TRAILING_STOP` | -$2.55 | **+$0.43** | +0.5 bps |
| 8 | `CC-0019` | LONG | 98.8600 | 15:52:35 | $86.0 | 15:53:34 | $86.2 | 59.1s | `TAKE_PROFIT` | -$2.55 | **+$13.96** | +16.4 bps |
| 9 | `CC-0022` | SHORT | 99.7700 | 17:54:36 | $85.2 | 17:55:41 | $85.1 | 64.5s | `TRAILING_STOP` | -$2.55 | **+$2.89** | +3.4 bps |
| 10 | `CC-0024` | SHORT | 99.9200 | 02:02:43 | $85.1 | 02:02:50 | $85.0 | 7.5s | `TRAILING_STOP` | -$2.55 | **-$0.65** | -0.8 bps |
| 11 | `CC-0029` | SHORT | 100.1300 | 04:50:11 | $84.9 | 04:52:42 | $84.9 | 150.8s | `TRAILING_STOP` | -$2.55 | **+$0.96** | +1.1 bps |
| 12 | `CC-0030` | SHORT | 100.2500 | 05:01:09 | $84.8 | 05:02:14 | $84.7 | 64.9s | `TRAILING_STOP` | -$2.55 | **+$2.06** | +2.4 bps |
| 13 | `CC-0031` | LONG | 100.0000 | 05:10:40 | $85.0 | 05:11:33 | $84.9 | 53.6s | `STOP_LOSS` | -$5.09 | **-$19.06** | -22.4 bps |
| 14 | `CC-0033` | LONG | 100.2800 | 09:10:33 | $84.8 | 09:13:33 | $84.7 | 180.0s | `TIME_LIMIT` | -$2.55 | **-$6.16** | -7.2 bps |
| 15 | `CC-0035` | LONG | 99.7600 | 10:11:51 | $85.2 | 10:13:39 | $85.1 | 107.2s | `STOP_LOSS` | -$5.09 | **-$18.43** | -21.7 bps |
| 16 | `CC-0037` | LONG | 99.5000 | 12:54:41 | $85.4 | 12:57:50 | $85.3 | 188.8s | `TIME_LIMIT` | -$2.55 | **-$11.40** | -13.4 bps |

### Strategy: `Hedged_Convexity`

- **Total Executed Trades**: 7 | **Wins**: 7 | **Losses**: 0 | **Win Rate**: 100.0% | **Net PnL**: $+33.91
- **Audit CSV**: [`strategies/Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `HC-0002` | LONG | 99.8000 | 15:14:54 | $85.2 | 15:15:05 | $85.2 | 10.7s | `TRAILING_STOP` | -$2.55 | **+$3.02** | +3.5 bps |
| 2 | `HC-0006` | LONG | 99.2300 | 15:21:55 | $85.7 | 15:22:18 | $85.7 | 22.4s | `TRAILING_STOP` | -$2.55 | **+$0.65** | +0.8 bps |
| 3 | `HC-0013` | SHORT | 98.5300 | 15:31:36 | $86.3 | 15:31:58 | $86.1 | 22.1s | `TAKE_PROFIT` | -$2.55 | **+$13.51** | +15.9 bps |
| 4 | `HC-0020` | LONG | 98.6500 | 15:53:52 | $86.2 | 15:54:39 | $86.3 | 47.0s | `TRAILING_STOP` | -$2.55 | **+$11.37** | +13.4 bps |
| 5 | `HC-0021` | SHORT | 99.6600 | 17:24:35 | $85.3 | 17:24:57 | $85.2 | 21.6s | `TRAILING_STOP` | -$2.55 | **+$4.16** | +4.9 bps |
| 6 | `HC-0026` | LONG | 98.8900 | 03:41:55 | $86.0 | 03:42:55 | $86.0 | 59.7s | `TRAILING_STOP` | -$2.55 | **+$0.42** | +0.5 bps |
| 7 | `HC-0028` | SHORT | 100.1300 | 04:50:13 | $84.9 | 04:52:42 | $84.9 | 148.7s | `TRAILING_STOP` | -$2.55 | **+$0.79** | +0.9 bps |

### Strategy: `Momentum_Expansion`

- **Total Executed Trades**: 15 | **Wins**: 8 | **Losses**: 7 | **Win Rate**: 53.3% | **Net PnL**: $-27.55
- **Audit CSV**: [`strategies/Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `ME-0001` | LONG | 100.5400 | 15:12:35 | $84.5 | 15:12:56 | $84.6 | 21.0s | `TRAILING_STOP` | -$2.55 | **+$3.08** | +3.6 bps |
| 2 | `ME-0005` | LONG | 99.3900 | 15:19:19 | $85.5 | 15:19:29 | $85.5 | 10.6s | `TRAILING_STOP` | -$2.55 | **-$0.97** | -1.1 bps |
| 3 | `ME-0008` | LONG | 99.2300 | 15:21:55 | $85.7 | 15:22:18 | $85.7 | 22.4s | `TRAILING_STOP` | -$2.55 | **+$0.82** | +1.0 bps |
| 4 | `ME-0011` | LONG | 98.9900 | 15:24:11 | $85.9 | 15:24:22 | $85.9 | 10.6s | `TRAILING_STOP` | -$2.55 | **+$3.39** | +4.0 bps |
| 5 | `ME-0012` | LONG | 98.7200 | 15:25:00 | $86.1 | 15:25:42 | $86.3 | 42.4s | `TRAILING_STOP` | -$2.55 | **+$12.64** | +14.9 bps |
| 6 | `ME-0015` | SHORT | 98.5300 | 15:31:36 | $86.3 | 15:32:03 | $86.1 | 27.1s | `TRAILING_STOP` | -$2.55 | **+$12.47** | +14.7 bps |
| 7 | `ME-0017` | SHORT | 98.7000 | 15:32:13 | $86.1 | 15:32:45 | $86.1 | 32.4s | `TRAILING_STOP` | -$2.55 | **+$0.43** | +0.5 bps |
| 8 | `ME-0018` | SHORT | 98.6800 | 15:35:50 | $86.1 | 15:36:04 | $86.2 | 13.8s | `STOP_LOSS` | -$5.10 | **-$16.33** | -19.2 bps |
| 9 | `ME-0023` | SHORT | 99.7700 | 17:54:36 | $85.2 | 17:55:41 | $85.1 | 64.5s | `TRAILING_STOP` | -$2.55 | **+$2.89** | +3.4 bps |
| 10 | `ME-0025` | SHORT | 99.9200 | 02:02:40 | $85.1 | 02:02:50 | $85.0 | 10.5s | `TRAILING_STOP` | -$2.55 | **-$0.65** | -0.8 bps |
| 11 | `ME-0027` | SHORT | 99.9900 | 04:49:55 | $85.0 | 04:50:22 | $84.9 | 26.8s | `TRAILING_STOP` | -$2.55 | **+$8.45** | +9.9 bps |
| 12 | `ME-0032` | LONG | 100.0000 | 05:10:40 | $85.0 | 05:11:33 | $84.9 | 53.6s | `STOP_LOSS` | -$5.09 | **-$19.06** | -22.4 bps |
| 13 | `ME-0034` | LONG | 100.2800 | 09:10:33 | $84.8 | 09:13:33 | $84.7 | 180.0s | `TIME_LIMIT` | -$2.55 | **-$6.16** | -7.2 bps |
| 14 | `ME-0036` | LONG | 99.7600 | 10:11:51 | $85.2 | 10:13:39 | $85.1 | 107.2s | `STOP_LOSS` | -$5.09 | **-$18.43** | -21.7 bps |
| 15 | `ME-0038` | LONG | 99.5000 | 12:54:41 | $85.4 | 12:58:06 | $85.3 | 204.8s | `TIME_LIMIT` | -$2.55 | **-$10.11** | -11.9 bps |

