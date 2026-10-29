# Trading Session Audit Report: `session_20261028_222422_067_14b4`

- **Session ID**: `session_20261028_222422_067_14b4`
- **Target Asset**: `HYPE-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: PAPER TRADING SIMULATION
- **Session Start**: 2026-10-28T22:24:22
- **Session End**: 2026-10-29 11:28:45
- **Duration**: 784m 23s (47063.2s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Executive Strategy Performance Audit

| Strategy | Trades | Win Rate | Volume (HYPE) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Convexity_Cascade** | 16 | 56.2% | 1717.1500 | -$40.80 | **+$32.25** | +2.4 bps | 1.73 | [`Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv) |
| **Hedged_Convexity** | 16 | 75.0% | 1635.2200 | -$43.36 | **+$102.45** | +7.5 bps | 3.12 | [`Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv) |
| **Momentum_Expansion** | 28 | 46.4% | 2716.2300 | -$67.58 | **$-59.65** | -2.4 bps | 0.52 | [`Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv) |

---

## 2. Individual Trade Logs per Strategy

### Strategy: `Convexity_Cascade`

- **Total Executed Trades**: 16 | **Wins**: 9 | **Losses**: 7 | **Win Rate**: 56.2% | **Net PnL**: $+32.25
- **Audit CSV**: [`strategies/Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `CC-0002` | LONG | 105.4300 | 00:01:39 | $80.6 | 00:02:38 | $80.6 | 59.1s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.08** | -8.3 bps |
| 2 | `CC-0005` | SHORT | 106.2800 | 01:04:04 | $80.0 | 01:05:19 | $80.0 | 75.2s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.44** | -8.8 bps |
| 3 | `CC-0008` | SHORT | 106.9800 | 01:47:37 | $79.5 | 01:48:17 | $79.2 | 39.9s | `TAKE_PROFIT` | -$2.55 | **+$20.67** | +24.3 bps |
| 4 | `CC-0010` | SHORT | 107.5700 | 01:56:12 | $79.0 | 01:56:21 | $79.1 | 8.7s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.64** | -7.8 bps |
| 5 | `CC-0012` | SHORT | 107.9300 | 02:00:06 | $78.8 | 02:00:15 | $78.7 | 9.3s | `TRAILING_STOP` | -$2.55 | **+$8.82** | +10.4 bps |
| 6 | `CC-0014` | SHORT | 107.9600 | 02:04:46 | $78.7 | 02:05:08 | $78.6 | 21.7s | `TRAILING_STOP` | -$2.55 | **+$7.26** | +8.5 bps |
| 7 | `CC-0015` | SHORT | 108.3300 | 02:07:59 | $78.5 | 02:08:31 | $78.5 | 32.5s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$9.70** | -11.4 bps |
| 8 | `CC-0016` | SHORT | 108.3700 | 02:10:30 | $78.4 | 02:11:13 | $78.4 | 42.8s | `TRAILING_STOP` | -$2.55 | **+$2.70** | +3.2 bps |
| 9 | `CC-0031` | LONG | 107.2800 | 05:07:41 | $79.2 | 05:08:08 | $79.2 | 27.5s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.09** | -7.2 bps |
| 10 | `CC-0035` | LONG | 107.5600 | 06:24:59 | $79.0 | 06:28:28 | $79.1 | 208.6s | `TRAILING_STOP` | -$2.55 | **+$5.70** | +6.7 bps |
| 11 | `CC-0036` | SHORT | 107.7000 | 06:42:50 | $78.9 | 06:44:44 | $78.9 | 113.2s | `TRAILING_STOP` | -$2.55 | **+$2.60** | +3.1 bps |
| 12 | `CC-0038` | LONG | 108.0000 | 07:15:29 | $78.7 | 07:16:27 | $78.8 | 58.2s | `TRAILING_STOP` | -$2.55 | **+$4.02** | +4.7 bps |
| 13 | `CC-0039` | SHORT | 108.2500 | 07:33:29 | $78.5 | 07:35:10 | $78.5 | 101.5s | `PROFIT_DECAY_EXIT` | -$2.55 | **-$3.85** | -4.5 bps |
| 14 | `CC-0041` | LONG | 107.8600 | 08:00:56 | $78.8 | 08:01:16 | $78.9 | 20.0s | `TRAILING_STOP` | -$2.55 | **+$4.54** | +5.3 bps |
| 15 | `CC-0042` | LONG | 107.9300 | 08:05:51 | $78.8 | 08:06:07 | $78.7 | 16.2s | `PROFIT_DECAY_EXIT` | -$2.55 | **-$3.52** | -4.1 bps |
| 16 | `CC-0048` | LONG | 103.7200 | 10:37:30 | $81.9 | 10:37:34 | $82.2 | 3.8s | `TAKE_PROFIT` | -$2.55 | **+$20.27** | +23.8 bps |

### Strategy: `Hedged_Convexity`

- **Total Executed Trades**: 16 | **Wins**: 12 | **Losses**: 4 | **Win Rate**: 75.0% | **Net PnL**: $+102.45
- **Audit CSV**: [`strategies/Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `HC-0004` | SHORT | 105.8000 | 00:21:51 | $80.3 | 00:22:12 | $80.3 | 21.8s | `TRAILING_STOP` | -$2.55 | **+$4.80** | +5.6 bps |
| 2 | `HC-0007` | SHORT | 106.5600 | 01:24:56 | $79.8 | 01:25:02 | $79.8 | 5.4s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$8.62** | -10.1 bps |
| 3 | `HC-0009` | SHORT | 107.5000 | 01:49:11 | $79.1 | 01:49:32 | $79.0 | 20.9s | `TRAILING_STOP` | -$2.55 | **+$0.86** | +1.0 bps |
| 4 | `HC-0029` | LONG | 107.6400 | 04:46:58 | $79.0 | 04:48:29 | $79.1 | 91.6s | `TRAILING_STOP` | -$2.55 | **+$6.99** | +8.2 bps |
| 5 | `HC-0043` | LONG | 105.9500 | 10:32:21 | $80.2 | 10:32:26 | $80.4 | 5.1s | `TAKE_PROFIT` | -$2.55 | **+$19.70** | +23.2 bps |
| 6 | `HC-0044` | LONG | 105.6300 | 10:32:45 | $80.5 | 10:32:48 | $80.7 | 2.5s | `TAKE_PROFIT` | -$2.55 | **+$21.85** | +25.7 bps |
| 7 | `HC-0045` | LONG | 104.1000 | 10:33:53 | $81.6 | 10:34:03 | $82.0 | 10.4s | `TAKE_PROFIT` | -$2.55 | **+$31.28** | +36.8 bps |
| 8 | `HC-0046` | LONG | 103.3800 | 10:34:19 | $82.2 | 10:34:36 | $82.4 | 16.3s | `TRAILING_STOP` | -$2.55 | **+$11.30** | +13.3 bps |
| 9 | `HC-0050` | LONG | 99.7500 | 10:48:42 | $85.2 | 10:48:58 | $85.4 | 16.1s | `TAKE_PROFIT` | -$2.55 | **+$17.10** | +20.1 bps |
| 10 | `HC-0051` | LONG | 98.5400 | 10:52:27 | $86.3 | 10:52:32 | $86.0 | 5.4s | `STOP_LOSS` | -$5.09 | **-$25.66** | -30.2 bps |
| 11 | `HC-0053` | LONG | 98.9600 | 11:02:34 | $85.9 | 11:02:45 | $86.1 | 11.0s | `TAKE_PROFIT` | -$2.55 | **+$16.74** | +19.7 bps |
| 12 | `HC-0054` | LONG | 98.7200 | 11:02:51 | $86.1 | 11:02:56 | $86.1 | 5.3s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.60** | -7.8 bps |
| 13 | `HC-0055` | LONG | 98.3900 | 11:09:14 | $86.4 | 11:09:39 | $86.5 | 25.1s | `TRAILING_STOP` | -$2.55 | **+$5.04** | +5.9 bps |
| 14 | `HC-0056` | LONG | 98.3800 | 11:12:03 | $86.4 | 11:12:26 | $86.5 | 22.6s | `TRAILING_STOP` | -$2.55 | **+$7.60** | +8.9 bps |
| 15 | `HC-0057` | LONG | 97.7800 | 11:14:24 | $86.9 | 11:15:23 | $87.0 | 59.1s | `TRAILING_STOP` | -$2.55 | **+$7.62** | +9.0 bps |
| 16 | `HC-0060` | LONG | 98.1400 | 11:28:12 | $86.6 | 11:28:28 | $86.6 | 16.2s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.55** | -8.9 bps |

### Strategy: `Momentum_Expansion`

- **Total Executed Trades**: 28 | **Wins**: 13 | **Losses**: 15 | **Win Rate**: 46.4% | **Net PnL**: $-59.65
- **Audit CSV**: [`strategies/Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `ME-0001` | SHORT | 105.4500 | 23:47:44 | $80.6 | 23:48:54 | $80.6 | 70.8s | `PROFIT_DECAY_EXIT` | -$2.55 | **-$3.71** | -4.4 bps |
| 2 | `ME-0003` | SHORT | 105.5600 | 00:20:06 | $80.5 | 00:21:45 | $80.4 | 99.5s | `TAKE_PROFIT` | -$2.55 | **+$14.87** | +17.5 bps |
| 3 | `ME-0006` | SHORT | 53.1400 | 01:04:04 | $80.0 | 01:05:19 | $80.0 | 75.2s | `DEFENSIVE_MAKER_HEDGE` | -$1.28 | **-$3.72** | -8.8 bps |
| 4 | `ME-0011` | SHORT | 108.0000 | 02:00:01 | $78.7 | 02:00:03 | $78.8 | 1.4s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.95** | -9.4 bps |
| 5 | `ME-0013` | SHORT | 108.0000 | 02:04:03 | $78.7 | 02:04:14 | $78.8 | 10.4s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.84** | -9.2 bps |
| 6 | `ME-0017` | SHORT | 54.1900 | 02:10:30 | $78.4 | 02:11:13 | $78.4 | 42.8s | `TRAILING_STOP` | -$1.27 | **+$1.56** | +3.7 bps |
| 7 | `ME-0018` | SHORT | 108.2600 | 02:23:41 | $78.5 | 02:23:52 | $78.6 | 11.1s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$8.72** | -10.3 bps |
| 8 | `ME-0019` | SHORT | 108.3700 | 02:27:11 | $78.4 | 02:27:48 | $78.4 | 36.9s | `TRAILING_STOP` | -$2.55 | **+$4.04** | +4.8 bps |
| 9 | `ME-0020` | SHORT | 108.4900 | 02:30:51 | $78.4 | 02:31:08 | $78.3 | 16.8s | `TRAILING_STOP` | -$2.55 | **+$4.27** | +5.0 bps |
| 10 | `ME-0021` | SHORT | 108.5000 | 02:31:28 | $78.3 | 02:31:45 | $78.4 | 16.2s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.98** | -9.4 bps |
| 11 | `ME-0022` | LONG | 108.4600 | 03:14:49 | $78.4 | 03:15:19 | $78.4 | 30.0s | `TRAILING_STOP` | -$2.55 | **+$0.42** | +0.5 bps |
| 12 | `ME-0023` | LONG | 108.3800 | 03:15:30 | $78.4 | 03:15:46 | $78.4 | 15.8s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$5.69** | -6.7 bps |
| 13 | `ME-0024` | LONG | 108.5800 | 03:24:16 | $78.3 | 03:24:57 | $78.3 | 40.8s | `TRAILING_STOP` | -$2.55 | **+$0.58** | +0.7 bps |
| 14 | `ME-0025` | LONG | 108.6600 | 03:33:09 | $78.2 | 03:33:41 | $78.2 | 32.1s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.57** | -7.7 bps |
| 15 | `ME-0026` | LONG | 108.6100 | 04:05:07 | $78.3 | 04:07:44 | $78.3 | 156.8s | `TRAILING_STOP` | -$2.55 | **+$1.67** | +2.0 bps |
| 16 | `ME-0027` | LONG | 108.4000 | 04:12:55 | $78.4 | 04:15:42 | $78.5 | 166.0s | `TRAILING_STOP` | -$2.55 | **+$12.17** | +14.3 bps |
| 17 | `ME-0028` | SHORT | 108.1100 | 04:27:10 | $78.6 | 04:30:10 | $78.6 | 180.1s | `TIME_LIMIT` | -$2.55 | **-$3.31** | -3.9 bps |
| 18 | `ME-0030` | LONG | 53.7600 | 04:47:43 | $79.1 | 04:48:56 | $79.0 | 73.3s | `DEFENSIVE_MAKER_HEDGE` | -$1.27 | **-$2.83** | -6.7 bps |
| 19 | `ME-0032` | LONG | 53.6400 | 05:07:41 | $79.2 | 05:08:09 | $79.2 | 28.4s | `DEFENSIVE_MAKER_HEDGE` | -$1.27 | **-$3.04** | -7.2 bps |
| 20 | `ME-0033` | LONG | 106.9600 | 05:19:43 | $79.5 | 05:19:54 | $79.4 | 10.9s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.19** | -7.3 bps |
| 21 | `ME-0034` | SHORT | 107.6400 | 06:23:21 | $79.0 | 06:23:54 | $79.0 | 32.8s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.32** | -7.4 bps |
| 22 | `ME-0037` | LONG | 107.5800 | 06:58:02 | $79.0 | 06:59:07 | $79.0 | 64.7s | `TRAILING_STOP` | -$2.55 | **+$0.54** | +0.6 bps |
| 23 | `ME-0040` | LONG | 108.0400 | 07:50:00 | $78.7 | 07:50:49 | $78.7 | 48.3s | `TRAILING_STOP` | -$2.55 | **+$1.96** | +2.3 bps |
| 24 | `ME-0047` | SHORT | 104.1300 | 10:35:56 | $81.6 | 10:36:07 | $81.9 | 10.5s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$32.44** | -38.2 bps |
| 25 | `ME-0049` | LONG | 51.8600 | 10:37:30 | $81.9 | 10:37:34 | $82.2 | 3.8s | `TAKE_PROFIT` | -$1.28 | **+$10.13** | +23.8 bps |
| 26 | `ME-0052` | LONG | 99.9600 | 10:59:10 | $85.0 | 10:59:20 | $84.9 | 10.8s | `STOP_LOSS` | -$5.09 | **-$18.36** | -21.6 bps |
| 27 | `ME-0058` | SHORT | 97.6700 | 11:16:59 | $87.0 | 11:17:21 | $86.9 | 21.2s | `TRAILING_STOP` | -$2.55 | **+$9.18** | +10.8 bps |
| 28 | `ME-0059` | LONG | 97.8300 | 11:20:56 | $86.9 | 11:21:17 | $86.9 | 21.4s | `TRAILING_STOP` | -$2.55 | **+$3.62** | +4.3 bps |

