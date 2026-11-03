# Trading Session Audit Report: `session_20261103_163545_219_b92d`

- **Session ID**: `session_20261103_163545_219_b92d`
- **Target Asset**: `HYPE-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: PAPER TRADING SIMULATION
- **Session Start**: 2026-11-03T16:35:45
- **Session End**: 2026-11-03 16:35:52
- **Duration**: 0m 7s (7.2s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Executive Strategy Performance Audit

| Strategy | Trades | Win Rate | Volume (HYPE) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **MicroPrice_FastFill** | 23 | 43.5% | 2326.1900 | -$61.20 | **$-36.17** | -1.9 bps | 0.65 | [`MicroPrice_FastFill.csv`](strategies/MicroPrice_FastFill.csv) |

---

## 2. Individual Trade Logs per Strategy

### Strategy: `MicroPrice_FastFill`

- **Total Executed Trades**: 23 | **Wins**: 10 | **Losses**: 13 | **Win Rate**: 43.5% | **Net PnL**: $-36.17
- **Audit CSV**: [`strategies/MicroPrice_FastFill.csv`](strategies/MicroPrice_FastFill.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `MPFF-0001` | SHORT | 100.9700 | 17:13:00 | $84.2 | 17:13:38 | $84.3 | 37.6s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$9.32** | -11.0 bps |
| 2 | `MPFF-0002` | LONG | 100.7000 | 17:14:48 | $84.4 | 17:15:15 | $84.5 | 26.6s | `SIGNAL_REVERSAL` | -$2.55 | **+$2.89** | +3.4 bps |
| 3 | `MPFF-0003` | SHORT | 100.5900 | 17:15:20 | $84.5 | 17:15:47 | $84.6 | 26.9s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.88** | -9.3 bps |
| 4 | `MPFF-0004` | SHORT | 100.8000 | 17:17:29 | $84.3 | 17:18:06 | $84.2 | 37.3s | `TAKE_PROFIT` | -$2.55 | **+$12.47** | +14.7 bps |
| 5 | `MPFF-0005` | LONG | 100.7700 | 17:18:49 | $84.4 | 17:19:32 | $84.2 | 43.2s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$15.55** | -18.3 bps |
| 6 | `MPFF-0006` | LONG | 101.1700 | 17:20:58 | $84.0 | 17:21:20 | $84.0 | 21.7s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$7.30** | -8.6 bps |
| 7 | `MPFF-0007` | LONG | 101.3000 | 17:24:01 | $83.9 | 17:24:06 | $84.0 | 5.4s | `SIGNAL_REVERSAL` | -$2.55 | **+$2.62** | +3.1 bps |
| 8 | `MPFF-0008` | SHORT | 101.2500 | 17:24:17 | $83.9 | 17:24:49 | $83.9 | 32.4s | `TRAILING_STOP` | -$2.55 | **+$3.45** | +4.1 bps |
| 9 | `MPFF-0009` | LONG | 101.2900 | 17:24:50 | $83.9 | 17:25:17 | $83.9 | 27.4s | `PROFIT_DECAY_EXIT` | -$2.55 | **-$2.35** | -2.8 bps |
| 10 | `MPFF-0010` | SHORT | 101.3400 | 17:26:17 | $83.9 | 17:26:33 | $83.7 | 16.1s | `TAKE_PROFIT` | -$2.55 | **+$15.19** | +17.9 bps |
| 11 | `MPFF-0011` | LONG | 101.5700 | 17:27:22 | $83.7 | 17:27:48 | $83.6 | 26.6s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$8.54** | -10.0 bps |
| 12 | `MPFF-0012` | LONG | 101.2300 | 17:28:49 | $84.0 | 17:28:53 | $83.9 | 4.8s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$11.05** | -13.0 bps |
| 13 | `MPFF-0013` | LONG | 101.2400 | 17:30:53 | $84.0 | 17:31:23 | $84.0 | 30.1s | `TRAILING_STOP` | -$2.55 | **+$1.82** | +2.1 bps |
| 14 | `MPFF-0014` | LONG | 101.2300 | 17:31:39 | $84.0 | 17:31:56 | $84.0 | 16.1s | `PROFIT_DECAY_EXIT` | -$2.55 | **-$1.94** | -2.3 bps |
| 15 | `MPFF-0015` | LONG | 101.2000 | 17:33:00 | $84.0 | 17:34:31 | $84.1 | 90.6s | `TRAILING_STOP` | -$2.55 | **+$7.03** | +8.3 bps |
| 16 | `MPFF-0016` | LONG | 101.1100 | 17:35:03 | $84.1 | 17:36:40 | $84.0 | 96.9s | `PROFIT_DECAY_EXIT` | -$2.55 | **-$5.58** | -6.6 bps |
| 17 | `MPFF-0017` | SHORT | 101.3500 | 17:38:01 | $83.9 | 17:38:22 | $83.9 | 21.5s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$10.15** | -11.9 bps |
| 18 | `MPFF-0018` | LONG | 101.1900 | 17:40:42 | $84.0 | 17:41:09 | $84.1 | 27.0s | `TRAILING_STOP` | -$2.55 | **+$5.71** | +6.7 bps |
| 19 | `MPFF-0019` | LONG | 101.0600 | 17:42:03 | $84.1 | 17:42:25 | $84.2 | 21.5s | `TRAILING_STOP` | -$2.55 | **+$3.07** | +3.6 bps |
| 20 | `MPFF-0020` | LONG | 101.2400 | 17:42:57 | $84.0 | 17:43:13 | $84.1 | 16.1s | `TAKE_PROFIT` | -$2.55 | **+$13.75** | +16.2 bps |
| 21 | `MPFF-0021` | LONG | 101.1000 | 17:44:55 | $84.1 | 17:45:11 | $84.0 | 16.3s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$8.82** | -10.4 bps |
| 22 | `MPFF-0022` | SHORT | 101.3400 | 17:46:43 | $83.9 | 17:47:20 | $84.0 | 37.2s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$12.08** | -14.2 bps |
| 23 | `MPFF-0023` | LONG | 101.1500 | 17:50:06 | $84.0 | 17:50:17 | $84.0 | 10.5s | `SESSION_SHUTDOWN` | -$5.10 | **-$3.60** | -4.2 bps |

