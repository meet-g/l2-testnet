# Trading Session Audit Report: `session_20261107_163615_948_84cf`

- **Session ID**: `session_20261107_163615_948_84cf`
- **Target Asset**: `HYPE-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: PAPER TRADING SIMULATION
- **Session Start**: 2026-11-07T16:36:15
- **Session End**: 2026-11-08 15:05:53
- **Duration**: 1349m 37s (80977.3s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Executive Strategy Performance Audit

| Strategy | Trades | Win Rate | Volume (HYPE) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Convexity_Cascade** | 22 | 54.5% | 2306.8200 | -$56.09 | **+$20.40** | +0.9 bps | 1.42 | [`Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv) |
| **Hedged_Convexity** | 5 | 60.0% | 495.2900 | -$14.03 | **$-13.41** | -1.9 bps | 0.32 | [`Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv) |
| **Momentum_Expansion** | 19 | 52.6% | 1812.0500 | -$49.73 | **$-67.26** | -3.6 bps | 0.19 | [`Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv) |
| **Queue_Replenishment** | 3 | 100.0% | 331.4100 | -$7.65 | **+$22.79** | +8.9 bps | 99.90 | [`Queue_Replenishment.csv`](strategies/Queue_Replenishment.csv) |

---

## 2. Individual Trade Logs per Strategy

### Strategy: `Convexity_Cascade`

- **Total Executed Trades**: 22 | **Wins**: 12 | **Losses**: 10 | **Win Rate**: 54.5% | **Net PnL**: $+20.40
- **Audit CSV**: [`strategies/Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `CC-0001` | SHORT | 109.7500 | 17:36:17 | $77.5 | 17:39:17 | $77.5 | 180.0s | `TIME_LIMIT` | -$2.55 | **-$5.73** | -6.7 bps |
| 2 | `CC-0002` | LONG | 109.3900 | 18:20:35 | $77.7 | 18:22:40 | $77.8 | 125.4s | `TRAILING_STOP` | -$2.55 | **+$7.52** | +8.8 bps |
| 3 | `CC-0003` | LONG | 109.3600 | 18:28:01 | $77.7 | 18:29:07 | $77.7 | 66.6s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$5.94** | -7.0 bps |
| 4 | `CC-0004` | LONG | 109.4700 | 18:34:29 | $77.6 | 18:35:37 | $77.7 | 67.1s | `TRAILING_STOP` | -$2.55 | **+$2.60** | +3.1 bps |
| 5 | `CC-0005` | SHORT | 109.8200 | 19:40:58 | $77.4 | 19:44:00 | $77.3 | 182.7s | `TRAILING_STOP` | -$2.55 | **+$3.73** | +4.4 bps |
| 6 | `CC-0008` | SHORT | 54.9900 | 19:46:42 | $77.3 | 19:49:43 | $77.3 | 180.2s | `TIME_LIMIT` | -$1.28 | **-$1.94** | -4.6 bps |
| 7 | `CC-0010` | SHORT | 110.5600 | 20:48:15 | $76.9 | 20:49:26 | $76.9 | 70.8s | `TRAILING_STOP` | -$2.55 | **+$0.77** | +0.9 bps |
| 8 | `CC-0011` | SHORT | 110.6800 | 20:51:24 | $76.8 | 20:52:39 | $76.8 | 75.1s | `PROFIT_DECAY_EXIT` | -$2.55 | **-$2.11** | -2.5 bps |
| 9 | `CC-0012` | SHORT | 110.3600 | 21:07:08 | $77.0 | 21:07:55 | $76.9 | 47.5s | `TRAILING_STOP` | -$2.55 | **+$7.69** | +9.0 bps |
| 10 | `CC-0013` | SHORT | 110.7600 | 21:32:36 | $76.7 | 21:34:48 | $76.8 | 132.6s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.09** | -7.2 bps |
| 11 | `CC-0015` | LONG | 55.1300 | 22:21:34 | $77.1 | 22:22:08 | $77.1 | 34.1s | `PROFIT_DECAY_EXIT` | -$1.28 | **-$1.11** | -2.6 bps |
| 12 | `CC-0018` | SHORT | 109.8200 | 23:25:28 | $77.4 | 23:28:20 | $77.4 | 171.6s | `PROFIT_DECAY_EXIT` | -$2.55 | **-$2.99** | -3.5 bps |
| 13 | `CC-0022` | SHORT | 109.5100 | 01:16:42 | $77.6 | 01:17:55 | $77.5 | 73.4s | `TRAILING_STOP` | -$2.55 | **+$7.32** | +8.6 bps |
| 14 | `CC-0025` | SHORT | 110.0600 | 02:45:41 | $77.2 | 02:47:08 | $77.2 | 87.0s | `TRAILING_STOP` | -$2.55 | **+$0.77** | +0.9 bps |
| 15 | `CC-0029` | LONG | 110.0200 | 06:16:24 | $77.3 | 06:22:24 | $77.4 | 360.1s | `TIME_LIMIT` | -$2.55 | **+$13.18** | +15.5 bps |
| 16 | `CC-0031` | SHORT | 110.3200 | 08:28:48 | $77.1 | 08:32:53 | $77.1 | 245.6s | `PROFIT_DECAY_EXIT` | -$2.55 | **-$2.11** | -2.5 bps |
| 17 | `CC-0032` | SHORT | 110.4400 | 09:15:21 | $77.0 | 09:18:03 | $76.8 | 161.5s | `TAKE_PROFIT` | -$2.55 | **+$18.66** | +21.9 bps |
| 18 | `CC-0038` | LONG | 109.7200 | 11:25:33 | $77.5 | 11:27:01 | $77.4 | 88.0s | `STOP_LOSS` | -$5.10 | **-$14.24** | -16.8 bps |
| 19 | `CC-0042` | LONG | 109.4300 | 13:11:12 | $77.7 | 13:12:14 | $77.7 | 61.7s | `TRAILING_STOP` | -$2.55 | **+$2.60** | +3.1 bps |
| 20 | `CC-0044` | LONG | 109.1900 | 13:15:47 | $77.8 | 13:17:07 | $77.9 | 80.5s | `TRAILING_STOP` | -$2.55 | **+$1.60** | +1.9 bps |
| 21 | `CC-0046` | LONG | 108.9600 | 13:20:30 | $78.0 | 13:21:23 | $78.0 | 52.2s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.58** | -7.7 bps |
| 22 | `CC-0047` | SHORT | 109.0800 | 13:23:06 | $77.9 | 13:23:17 | $77.9 | 10.7s | `TRAILING_STOP` | -$2.55 | **+$2.80** | +3.3 bps |

### Strategy: `Hedged_Convexity`

- **Total Executed Trades**: 5 | **Wins**: 3 | **Losses**: 2 | **Win Rate**: 60.0% | **Net PnL**: $-13.41
- **Audit CSV**: [`strategies/Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `HC-0007` | SHORT | 109.9800 | 19:46:42 | $77.3 | 19:49:43 | $77.3 | 180.2s | `TIME_LIMIT` | -$2.55 | **-$3.87** | -4.6 bps |
| 2 | `HC-0009` | SHORT | 110.4500 | 20:43:24 | $77.0 | 20:46:24 | $76.9 | 179.5s | `TRAILING_STOP` | -$2.55 | **+$0.43** | +0.5 bps |
| 3 | `HC-0020` | SHORT | 109.5100 | 00:03:50 | $77.6 | 00:04:33 | $77.6 | 42.4s | `TRAILING_STOP` | -$2.55 | **+$0.43** | +0.5 bps |
| 4 | `HC-0027` | SHORT | 110.0000 | 03:36:44 | $77.3 | 03:37:04 | $77.4 | 20.1s | `STOP_LOSS` | -$5.10 | **-$15.88** | -18.7 bps |
| 5 | `HC-0034` | SHORT | 55.3500 | 09:18:03 | $76.8 | 09:20:01 | $76.7 | 118.4s | `TRAILING_STOP` | -$1.27 | **+$5.49** | +12.9 bps |

### Strategy: `Momentum_Expansion`

- **Total Executed Trades**: 19 | **Wins**: 10 | **Losses**: 9 | **Win Rate**: 52.6% | **Net PnL**: $-67.26
- **Audit CSV**: [`strategies/Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `ME-0006` | SHORT | 54.9100 | 19:40:58 | $77.4 | 19:44:00 | $77.3 | 182.7s | `TRAILING_STOP` | -$1.27 | **+$2.42** | +5.7 bps |
| 2 | `ME-0014` | LONG | 110.2600 | 22:21:33 | $77.1 | 22:21:57 | $77.1 | 23.7s | `TRAILING_STOP` | -$2.55 | **+$0.42** | +0.5 bps |
| 3 | `ME-0016` | SHORT | 110.1300 | 22:36:40 | $77.2 | 22:39:40 | $77.2 | 180.0s | `TIME_LIMIT` | -$2.55 | **-$4.86** | -5.7 bps |
| 4 | `ME-0017` | LONG | 109.8500 | 23:08:56 | $77.4 | 23:09:10 | $77.3 | 13.4s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.39** | -7.5 bps |
| 5 | `ME-0019` | LONG | 109.4000 | 23:46:57 | $77.7 | 23:48:14 | $77.8 | 77.2s | `TRAILING_STOP` | -$2.55 | **+$3.54** | +4.2 bps |
| 6 | `ME-0021` | LONG | 109.4100 | 01:03:42 | $77.7 | 01:04:00 | $77.7 | 17.9s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.38** | -7.5 bps |
| 7 | `ME-0023` | LONG | 109.4500 | 01:33:26 | $77.7 | 01:36:03 | $77.7 | 157.0s | `TRAILING_STOP` | -$2.55 | **+$2.16** | +2.5 bps |
| 8 | `ME-0024` | SHORT | 55.0300 | 02:45:41 | $77.2 | 02:46:58 | $77.2 | 77.2s | `TRAILING_STOP` | -$1.27 | **+$0.32** | +0.8 bps |
| 9 | `ME-0026` | SHORT | 110.1100 | 02:47:40 | $77.2 | 02:50:36 | $77.2 | 175.8s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$8.06** | -9.5 bps |
| 10 | `ME-0028` | LONG | 55.0100 | 06:16:24 | $77.3 | 06:18:42 | $77.3 | 137.4s | `TRAILING_STOP` | -$1.28 | **+$0.21** | +0.5 bps |
| 11 | `ME-0030` | SHORT | 110.1000 | 06:38:16 | $77.2 | 06:39:37 | $77.2 | 80.1s | `TRAILING_STOP` | -$2.55 | **+$0.43** | +0.5 bps |
| 12 | `ME-0033` | SHORT | 55.2700 | 09:17:55 | $76.9 | 09:18:04 | $76.8 | 9.8s | `TRAILING_STOP` | -$1.27 | **+$5.18** | +12.2 bps |
| 13 | `ME-0037` | SHORT | 110.9900 | 09:22:49 | $76.6 | 09:23:18 | $76.7 | 28.9s | `STOP_LOSS` | -$5.10 | **-$13.69** | -16.1 bps |
| 14 | `ME-0039` | SHORT | 110.0000 | 12:01:58 | $77.3 | 12:03:34 | $77.4 | 96.3s | `STOP_LOSS` | -$5.10 | **-$13.70** | -16.1 bps |
| 15 | `ME-0041` | LONG | 54.7000 | 13:11:27 | $77.7 | 13:12:13 | $77.7 | 46.0s | `TRAILING_STOP` | -$1.28 | **+$0.21** | +0.5 bps |
| 16 | `ME-0043` | LONG | 109.2200 | 13:15:17 | $77.8 | 13:15:18 | $77.9 | 1.7s | `TRAILING_STOP` | -$2.55 | **+$0.73** | +0.9 bps |
| 17 | `ME-0045` | LONG | 109.0200 | 13:18:19 | $78.0 | 13:19:01 | $77.9 | 42.4s | `STOP_LOSS` | -$5.10 | **-$15.27** | -18.0 bps |
| 18 | `ME-0048` | LONG | 109.5700 | 14:38:03 | $77.6 | 14:38:10 | $77.5 | 6.6s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$8.03** | -9.4 bps |
| 19 | `ME-0049` | LONG | 109.6200 | 14:41:07 | $77.5 | 14:41:45 | $77.5 | 37.9s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.50** | -7.6 bps |

### Strategy: `Queue_Replenishment`

- **Total Executed Trades**: 3 | **Wins**: 3 | **Losses**: 0 | **Win Rate**: 100.0% | **Net PnL**: $+22.79
- **Audit CSV**: [`strategies/Queue_Replenishment.csv`](strategies/Queue_Replenishment.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `QR-0035` | SHORT | 110.6600 | 09:18:08 | $76.8 | 09:20:01 | $76.7 | 112.7s | `TRAILING_STOP` | -$2.55 | **+$15.41** | +18.1 bps |
| 2 | `QR-0036` | SHORT | 110.9300 | 09:20:38 | $76.6 | 09:22:53 | $76.6 | 135.6s | `TRAILING_STOP` | -$2.55 | **+$0.92** | +1.1 bps |
| 3 | `QR-0040` | LONG | 109.8200 | 12:50:24 | $77.4 | 12:50:50 | $77.5 | 26.3s | `TRAILING_STOP` | -$2.55 | **+$6.45** | +7.6 bps |

