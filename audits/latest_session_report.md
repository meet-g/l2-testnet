# Trading Session Audit Report: `session_20261023_224412_718_e676`

- **Session ID**: `session_20261023_224412_718_e676`
- **Target Asset**: `HYPE-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: PAPER TRADING SIMULATION
- **Session Start**: 2026-10-23T22:44:12
- **Session End**: 2026-10-24 10:22:18
- **Duration**: 698m 5s (41885.7s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Executive Strategy Performance Audit

| Strategy | Trades | Win Rate | Volume (HYPE) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Convexity_Cascade** | 16 | 50.0% | 1550.5100 | -$38.25 | **$-23.36** | -0.5 bps | 0.59 | [`Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv) |
| **Hedged_Convexity** | 14 | 42.9% | 1559.5200 | -$38.25 | **$-35.97** | -3.0 bps | 0.48 | [`Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv) |
| **Momentum_Expansion** | 27 | 70.4% | 2873.9800 | -$66.30 | **+$14.42** | +0.5 bps | 1.30 | [`Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv) |

---

## 2. Individual Trade Logs per Strategy

### Strategy: `Convexity_Cascade`

- **Total Executed Trades**: 16 | **Wins**: 8 | **Losses**: 8 | **Win Rate**: 50.0% | **Net PnL**: $-23.36
- **Audit CSV**: [`strategies/Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `CC-0003` | LONG | 109.4100 | 23:23:29 | $77.7 | 23:23:50 | $77.7 | 21.6s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.05** | -7.1 bps |
| 2 | `CC-0006` | SHORT | 110.0800 | 23:33:03 | $77.2 | 23:33:45 | $77.1 | 42.0s | `TRAILING_STOP` | -$2.55 | **+$6.72** | +7.9 bps |
| 3 | `CC-0013` | SHORT | 55.7500 | 23:56:52 | $76.2 | 23:57:08 | $76.3 | 16.5s | `DEFENSIVE_MAKER_HEDGE` | -$1.28 | **-$3.90** | -9.2 bps |
| 4 | `CC-0017` | SHORT | 111.5000 | 00:13:18 | $76.2 | 00:13:39 | $76.3 | 21.3s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.12** | -8.4 bps |
| 5 | `CC-0025` | SHORT | 110.5800 | 01:09:10 | $76.9 | 01:12:07 | $76.8 | 176.9s | `TRAILING_STOP` | -$2.55 | **+$0.80** | +0.9 bps |
| 6 | `CC-0026` | SHORT | 55.3700 | 01:17:20 | $76.8 | 01:17:51 | $76.7 | 30.5s | `TRAILING_STOP` | -$1.27 | **+$2.29** | +5.4 bps |
| 7 | `CC-0029` | SHORT | 111.6500 | 01:34:15 | $76.1 | 01:34:48 | $76.2 | 32.7s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.46** | -8.8 bps |
| 8 | `CC-0031` | SHORT | 111.3100 | 01:55:57 | $76.4 | 01:58:22 | $76.4 | 145.6s | `STOP_LOSS` | -$5.10 | **-$13.84** | -16.3 bps |
| 9 | `CC-0036` | LONG | 110.3200 | 03:10:02 | $77.0 | 03:11:07 | $77.1 | 65.0s | `TRAILING_STOP` | -$2.55 | **+$2.22** | +2.6 bps |
| 10 | `CC-0037` | LONG | 110.2600 | 03:12:49 | $77.1 | 03:13:16 | $77.0 | 26.0s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.74** | -7.9 bps |
| 11 | `CC-0040` | SHORT | 110.3700 | 04:49:47 | $77.0 | 04:50:04 | $77.0 | 16.5s | `TRAILING_STOP` | -$2.55 | **+$1.64** | +1.9 bps |
| 12 | `CC-0042` | SHORT | 110.4800 | 04:50:52 | $76.9 | 04:52:39 | $77.0 | 106.9s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.20** | -7.3 bps |
| 13 | `CC-0043` | LONG | 110.2000 | 05:13:11 | $77.1 | 05:15:59 | $77.1 | 167.2s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.08** | -7.1 bps |
| 14 | `CC-0049` | SHORT | 55.5600 | 08:09:28 | $76.5 | 08:09:42 | $76.4 | 13.8s | `TRAILING_STOP` | -$1.27 | **+$3.64** | +8.6 bps |
| 15 | `CC-0051` | SHORT | 111.6600 | 08:58:47 | $76.1 | 08:59:09 | $76.1 | 21.6s | `TRAILING_STOP` | -$2.55 | **+$1.86** | +2.2 bps |
| 16 | `CC-0055` | SHORT | 56.0100 | 09:38:14 | $75.9 | 09:38:40 | $75.6 | 26.8s | `TAKE_PROFIT` | -$1.27 | **+$14.86** | +35.0 bps |

### Strategy: `Hedged_Convexity`

- **Total Executed Trades**: 14 | **Wins**: 6 | **Losses**: 8 | **Win Rate**: 42.9% | **Net PnL**: $-35.97
- **Audit CSV**: [`strategies/Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `HC-0007` | SHORT | 110.2300 | 23:36:28 | $77.1 | 23:36:37 | $77.1 | 8.6s | `TRAILING_STOP` | -$2.55 | **+$3.80** | +4.5 bps |
| 2 | `HC-0011` | SHORT | 110.8200 | 23:48:37 | $76.7 | 23:48:59 | $76.5 | 22.1s | `TAKE_PROFIT` | -$2.55 | **+$14.96** | +17.6 bps |
| 3 | `HC-0012` | SHORT | 111.5100 | 23:56:52 | $76.2 | 23:57:08 | $76.3 | 16.5s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.79** | -9.2 bps |
| 4 | `HC-0016` | SHORT | 111.2000 | 00:08:48 | $76.4 | 00:09:10 | $76.4 | 21.5s | `TRAILING_STOP` | -$2.55 | **+$2.87** | +3.4 bps |
| 5 | `HC-0028` | SHORT | 111.4900 | 01:19:17 | $76.2 | 01:19:44 | $76.3 | 26.8s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.79** | -9.2 bps |
| 6 | `HC-0034` | LONG | 110.6000 | 02:46:04 | $76.9 | 02:46:42 | $76.8 | 37.8s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.19** | -8.5 bps |
| 7 | `HC-0046` | SHORT | 110.9200 | 08:02:21 | $76.6 | 08:02:37 | $76.7 | 16.5s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.76** | -9.1 bps |
| 8 | `HC-0047` | SHORT | 110.9800 | 08:06:37 | $76.6 | 08:09:15 | $76.5 | 157.7s | `TRAILING_STOP` | -$2.55 | **+$3.02** | +3.6 bps |
| 9 | `HC-0048` | SHORT | 111.1200 | 08:09:28 | $76.5 | 08:09:42 | $76.4 | 13.8s | `TRAILING_STOP` | -$2.55 | **+$7.70** | +9.1 bps |
| 10 | `HC-0052` | SHORT | 112.1000 | 09:07:17 | $75.8 | 09:07:38 | $75.9 | 21.2s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$8.38** | -9.9 bps |
| 11 | `HC-0053` | LONG | 111.6400 | 09:15:03 | $76.1 | 09:18:16 | $76.1 | 192.9s | `TIME_LIMIT` | -$2.55 | **-$4.00** | -4.7 bps |
| 12 | `HC-0054` | SHORT | 112.0200 | 09:38:14 | $75.9 | 09:38:24 | $75.9 | 10.8s | `TRAILING_STOP` | -$2.55 | **+$0.43** | +0.5 bps |
| 13 | `HC-0056` | SHORT | 112.2300 | 09:39:24 | $75.7 | 09:40:11 | $75.8 | 47.7s | `STOP_LOSS` | -$5.10 | **-$13.35** | -15.7 bps |
| 14 | `HC-0057` | SHORT | 112.6600 | 09:46:01 | $75.5 | 09:46:33 | $75.5 | 32.1s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$12.47** | -14.7 bps |

### Strategy: `Momentum_Expansion`

- **Total Executed Trades**: 27 | **Wins**: 19 | **Losses**: 8 | **Win Rate**: 70.4% | **Net PnL**: $+14.42
- **Audit CSV**: [`strategies/Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `ME-0001` | LONG | 109.1000 | 23:01:04 | $77.9 | 23:01:42 | $77.9 | 37.9s | `TRAILING_STOP` | -$2.55 | **+$0.82** | +1.0 bps |
| 2 | `ME-0002` | LONG | 109.3300 | 23:15:15 | $77.7 | 23:15:37 | $77.8 | 21.4s | `TRAILING_STOP` | -$2.55 | **+$0.50** | +0.6 bps |
| 3 | `ME-0004` | LONG | 54.7000 | 23:23:29 | $77.7 | 23:23:50 | $77.7 | 21.6s | `DEFENSIVE_MAKER_HEDGE` | -$1.27 | **-$3.02** | -7.1 bps |
| 4 | `ME-0005` | SHORT | 110.0000 | 23:32:02 | $77.3 | 23:32:20 | $77.2 | 17.9s | `TRAILING_STOP` | -$2.55 | **+$1.09** | +1.3 bps |
| 5 | `ME-0008` | SHORT | 110.2500 | 23:36:56 | $77.1 | 23:37:04 | $77.1 | 8.3s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.73** | -9.1 bps |
| 6 | `ME-0009` | LONG | 110.3300 | 23:39:40 | $77.0 | 23:40:17 | $77.1 | 37.7s | `TRAILING_STOP` | -$2.55 | **+$1.54** | +1.8 bps |
| 7 | `ME-0010` | SHORT | 110.3500 | 23:45:46 | $77.0 | 23:46:28 | $77.0 | 42.7s | `TRAILING_STOP` | -$2.55 | **+$1.09** | +1.3 bps |
| 8 | `ME-0014` | SHORT | 111.4600 | 23:57:21 | $76.3 | 23:57:35 | $76.3 | 13.9s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$5.89** | -6.9 bps |
| 9 | `ME-0015` | SHORT | 111.0300 | 00:06:29 | $76.6 | 00:07:05 | $76.4 | 36.5s | `TRAILING_STOP` | -$2.55 | **+$10.24** | +12.1 bps |
| 10 | `ME-0018` | SHORT | 111.4300 | 00:13:39 | $76.3 | 00:13:55 | $76.3 | 16.0s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.23** | -7.3 bps |
| 11 | `ME-0019` | LONG | 110.8300 | 00:22:14 | $76.7 | 00:23:02 | $76.8 | 48.5s | `TRAILING_STOP` | -$2.55 | **+$6.83** | +8.0 bps |
| 12 | `ME-0020` | LONG | 110.7400 | 00:29:02 | $76.8 | 00:30:02 | $76.7 | 60.0s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.09** | -7.2 bps |
| 13 | `ME-0021` | SHORT | 111.0100 | 00:31:18 | $76.6 | 00:31:44 | $76.5 | 26.9s | `TRAILING_STOP` | -$2.55 | **+$0.91** | +1.1 bps |
| 14 | `ME-0022` | LONG | 110.4000 | 01:01:05 | $77.0 | 01:01:21 | $77.0 | 16.4s | `TRAILING_STOP` | -$2.55 | **+$2.76** | +3.2 bps |
| 15 | `ME-0023` | LONG | 110.3800 | 01:01:27 | $77.0 | 01:02:31 | $77.1 | 64.2s | `TRAILING_STOP` | -$2.55 | **+$5.52** | +6.5 bps |
| 16 | `ME-0024` | LONG | 110.3500 | 01:03:03 | $77.0 | 01:04:13 | $77.0 | 70.5s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.96** | -8.2 bps |
| 17 | `ME-0027` | SHORT | 110.7500 | 01:17:14 | $76.8 | 01:17:51 | $76.7 | 36.6s | `TRAILING_STOP` | -$2.55 | **+$5.00** | +5.9 bps |
| 18 | `ME-0030` | LONG | 111.5100 | 01:42:36 | $76.2 | 01:44:40 | $76.3 | 124.0s | `TRAILING_STOP` | -$2.55 | **+$6.90** | +8.1 bps |
| 19 | `ME-0032` | SHORT | 111.0100 | 02:25:37 | $76.6 | 02:26:52 | $76.5 | 75.0s | `TRAILING_STOP` | -$2.55 | **+$0.43** | +0.5 bps |
| 20 | `ME-0033` | LONG | 110.8900 | 02:42:56 | $76.7 | 02:44:49 | $76.7 | 113.0s | `TRAILING_STOP` | -$2.55 | **+$1.90** | +2.2 bps |
| 21 | `ME-0035` | LONG | 110.6000 | 02:49:58 | $76.9 | 02:52:19 | $76.9 | 140.7s | `TRAILING_STOP` | -$2.55 | **+$2.11** | +2.5 bps |
| 22 | `ME-0038` | SHORT | 110.2000 | 03:49:33 | $77.1 | 03:50:58 | $77.1 | 85.3s | `TRAILING_STOP` | -$2.55 | **+$1.21** | +1.4 bps |
| 23 | `ME-0039` | SHORT | 109.9400 | 04:04:57 | $77.3 | 04:05:18 | $77.2 | 20.8s | `TRAILING_STOP` | -$2.55 | **+$5.37** | +6.3 bps |
| 24 | `ME-0041` | SHORT | 55.1900 | 04:49:47 | $77.0 | 04:50:04 | $77.0 | 16.5s | `TRAILING_STOP` | -$1.27 | **+$1.02** | +2.4 bps |
| 25 | `ME-0044` | SHORT | 110.5300 | 06:19:00 | $76.9 | 06:22:37 | $76.8 | 217.4s | `TRAILING_STOP` | -$2.55 | **+$6.75** | +7.9 bps |
| 26 | `ME-0045` | LONG | 110.4500 | 07:23:57 | $77.0 | 07:24:05 | $76.9 | 8.4s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$5.75** | -6.8 bps |
| 27 | `ME-0050` | LONG | 111.2200 | 08:36:24 | $76.4 | 08:38:53 | $76.4 | 148.6s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$5.89** | -6.9 bps |

