# Trading Session Audit Report: `session_20261030_141720_286_7d32`

- **Session ID**: `session_20261030_141720_286_7d32`
- **Target Asset**: `xyz:SKHX-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: REAL EXCHANGE ORDERS (LIVE)
- **Session Start**: 2026-10-30T14:17:20
- **Session End**: 2026-10-30 14:41:04
- **Duration**: 23m 44s (1424.2s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Real On-Chain Hyperliquid Execution (Exchange Reconciled)

> [!IMPORTANT]
> The figures below represent **actual on-chain fills and cash settlements** verified directly against the Hyperliquid clearinghouse API for this trading session.

| Metric | Real Value (Exchange Settled) |
| :--- | :---: |
| **Total Real Fills** | 54 (45 Maker / 9 Taker) |
| **Real Executed Volume** | 20.6680 xyz:SKHX |
| **Real Closed PnL** | $-3.2681 USDC |
| **Real Fees Paid to Hyperliquid** | $0.8357 USDC |
| **Real Net Realized PnL** | **-$4.1038 USDC** |
| **On-Chain Fills CSV** | [`live_exchange_fills.csv`](live_exchange_fills.csv) |

---

## 2. Theoretical Paper-Simulation Benchmark

| Strategy | Trades | Win Rate | Volume (XYZ:SKHX) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Convexity_Cascade** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv) |
| **Hedged_Convexity** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv) |
| **MicroPrice_Maker** | 35 | 77.1% | 14.3500 | -$1.03 | **+$3.00** | +2.0 bps | 1.66 | [`MicroPrice_Maker.csv`](strategies/MicroPrice_Maker.csv) |
| **Momentum_Expansion** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv) |

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

### Strategy: `MicroPrice_Maker`

- **Total Executed Trades**: 35 | **Wins**: 27 | **Losses**: 8 | **Win Rate**: 77.1% | **Net PnL**: $+3.00
- **Audit CSV**: [`strategies/MicroPrice_Maker.csv`](strategies/MicroPrice_Maker.csv)

| # | Trade ID | Side | Size (XYZ:SKHX) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `MPM-0001` | SHORT | 0.4100 | 14:17:45 | $1,044.7 | 14:17:50 | $1,044.1 | 5.3s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.22** | +5.1 bps |
| 2 | `MPM-0002` | LONG | 0.4100 | 14:17:52 | $1,044.1 | 14:17:56 | $1,044.6 | 3.8s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.18** | +4.2 bps |
| 3 | `MPM-0003` | SHORT | 0.4100 | 14:18:01 | $1,044.1 | 14:18:22 | $1,043.4 | 21.1s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.26** | +6.1 bps |
| 4 | `MPM-0004` | LONG | 0.4100 | 14:18:23 | $1,043.4 | 14:18:28 | $1,044.9 | 5.4s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.59** | +13.8 bps |
| 5 | `MPM-0005` | LONG | 0.4100 | 14:18:49 | $1,044.6 | 14:19:05 | $1,044.8 | 15.6s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.06** | +1.3 bps |
| 6 | `MPM-0006` | SHORT | 0.4100 | 14:19:05 | $1,044.8 | 14:19:32 | $1,045.6 | 26.9s | `SIGNAL_REVERSAL` | -$0.03 | **-$0.35** | -8.3 bps |
| 7 | `MPM-0007` | SHORT | 0.4100 | 14:20:37 | $1,046.6 | 14:20:58 | $1,045.7 | 21.1s | `TRAILING_STOP` | -$0.03 | **+$0.34** | +8.0 bps |
| 8 | `MPM-0008` | LONG | 0.4100 | 14:21:09 | $1,045.9 | 14:21:31 | $1,044.4 | 21.7s | `STOP_LOSS` | -$0.05 | **-$0.67** | -15.7 bps |
| 9 | `MPM-0009` | SHORT | 0.4100 | 14:22:31 | $1,042.1 | 14:22:45 | $1,041.1 | 14.8s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.38** | +9.0 bps |
| 10 | `MPM-0010` | LONG | 0.4100 | 14:23:02 | $1,041.2 | 14:23:07 | $1,041.7 | 5.4s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.18** | +4.2 bps |
| 11 | `MPM-0011` | SHORT | 0.4100 | 14:23:18 | $1,041.7 | 14:23:29 | $1,040.4 | 10.9s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.51** | +11.9 bps |
| 12 | `MPM-0012` | LONG | 0.4100 | 14:23:30 | $1,040.4 | 14:23:39 | $1,041.2 | 9.5s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.30** | +7.1 bps |
| 13 | `MPM-0013` | LONG | 0.4100 | 14:24:12 | $1,039.0 | 14:24:39 | $1,039.4 | 27.2s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.14** | +3.2 bps |
| 14 | `MPM-0014` | SHORT | 0.4100 | 14:24:50 | $1,038.8 | 14:25:17 | $1,038.1 | 27.0s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.26** | +6.1 bps |
| 15 | `MPM-0015` | SHORT | 0.4100 | 14:25:38 | $1,038.2 | 14:26:05 | $1,039.8 | 26.8s | `STOP_LOSS` | -$0.05 | **-$0.72** | -16.8 bps |
| 16 | `MPM-0016` | LONG | 0.4100 | 14:27:10 | $1,040.2 | 14:27:15 | $1,040.4 | 5.2s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.06** | +1.3 bps |
| 17 | `MPM-0017` | SHORT | 0.4100 | 14:27:25 | $1,040.1 | 14:27:31 | $1,039.6 | 5.3s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.18** | +4.2 bps |
| 18 | `MPM-0018` | LONG | 0.4100 | 14:27:36 | $1,040.2 | 14:28:14 | $1,041.3 | 37.4s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.43** | +10.0 bps |
| 19 | `MPM-0019` | SHORT | 0.4100 | 14:28:24 | $1,042.3 | 14:29:02 | $1,042.0 | 37.9s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.10** | +2.3 bps |
| 20 | `MPM-0020` | LONG | 0.4100 | 14:29:04 | $1,042.0 | 14:29:12 | $1,042.3 | 8.6s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.10** | +2.3 bps |
| 21 | `MPM-0021` | SHORT | 0.4100 | 14:29:18 | $1,042.3 | 14:29:45 | $1,043.8 | 26.8s | `STOP_LOSS` | -$0.05 | **-$0.67** | -15.8 bps |
| 22 | `MPM-0022` | SHORT | 0.4100 | 14:30:55 | $1,043.9 | 14:31:00 | $1,043.4 | 5.5s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.18** | +4.2 bps |
| 23 | `MPM-0023` | LONG | 0.4100 | 14:31:49 | $1,043.9 | 14:32:15 | $1,042.5 | 25.9s | `STOP_LOSS` | -$0.05 | **-$0.63** | -14.8 bps |
| 24 | `MPM-0024` | SHORT | 0.4100 | 14:33:15 | $1,041.9 | 14:33:26 | $1,043.1 | 10.4s | `SIGNAL_REVERSAL` | -$0.03 | **-$0.52** | -12.1 bps |
| 25 | `MPM-0025` | LONG | 0.4100 | 14:35:34 | $1,045.0 | 14:35:39 | $1,045.2 | 5.4s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.06** | +1.3 bps |
| 26 | `MPM-0026` | SHORT | 0.4100 | 14:35:41 | $1,045.2 | 14:36:06 | $1,045.0 | 25.1s | `TRAILING_STOP` | -$0.03 | **+$0.07** | +1.7 bps |
| 27 | `MPM-0027` | SHORT | 0.4100 | 14:36:44 | $1,044.1 | 14:37:11 | $1,043.2 | 26.8s | `TRAILING_STOP` | -$0.03 | **+$0.36** | +8.5 bps |
| 28 | `MPM-0028` | LONG | 0.4100 | 14:37:21 | $1,043.4 | 14:37:43 | $1,045.2 | 21.5s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.71** | +16.7 bps |
| 29 | `MPM-0029` | LONG | 0.4100 | 14:38:04 | $1,045.9 | 14:38:15 | $1,046.6 | 10.7s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.26** | +6.1 bps |
| 30 | `MPM-0030` | LONG | 0.4100 | 14:38:20 | $1,046.0 | 14:38:32 | $1,047.4 | 11.2s | `TRAILING_STOP` | -$0.03 | **+$0.57** | +13.2 bps |
| 31 | `MPM-0031` | LONG | 0.4100 | 14:38:32 | $1,047.2 | 14:38:37 | $1,047.8 | 4.7s | `SIGNAL_REVERSAL` | -$0.03 | **+$0.22** | +5.1 bps |
| 32 | `MPM-0032` | SHORT | 0.4100 | 14:38:38 | $1,047.8 | 14:38:58 | $1,048.6 | 20.0s | `SIGNAL_REVERSAL` | -$0.03 | **-$0.35** | -8.2 bps |
| 33 | `MPM-0033` | SHORT | 0.4100 | 14:39:58 | $1,049.0 | 14:40:08 | $1,048.8 | 9.3s | `TRAILING_STOP` | -$0.03 | **+$0.05** | +1.3 bps |
| 34 | `MPM-0034` | SHORT | 0.4100 | 14:40:13 | $1,048.9 | 14:40:18 | $1,046.9 | 5.4s | `TAKE_PROFIT` | -$0.03 | **+$0.79** | +18.5 bps |
| 35 | `MPM-0035` | SHORT | 0.4100 | 14:40:24 | $1,046.2 | 14:40:34 | $1,047.6 | 10.4s | `STOP_LOSS` | -$0.05 | **-$0.63** | -14.8 bps |

### Strategy: `Momentum_Expansion`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv)

_No trades were opened/closed for Momentum_Expansion during this session._


---

## 3. Real Exchange Order Audit Log (Hyperliquid API)

| Event ID | Time | Event | Side | Size (XYZ:SKHX) | Price | TIF | OID | Status | Signal Score | Error |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `EVT-0001` | 14:17:40 | **SUBMIT** | SELL | 0.4790 | $1,044.9 | `Alo` | - | `submitting` | -0.918 | - |
| `EVT-0002` | 14:17:41 | **RESTING** | SELL | 0.4790 | $1,044.9 | `Alo` | `590750200343` | `ok` | -0.918 | - |
| `EVT-0003` | 14:17:46 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590750200343` | `ok` | +0.000 | - |
| `EVT-0004` | 14:17:46 | **SUBMIT** | SELL | 0.1920 | $1,044.7 | `Alo` | - | `submitting` | -0.969 | - |
| `EVT-0005` | 14:17:47 | **RESTING** | SELL | 0.1920 | $1,044.7 | `Alo` | `590750300960` | `ok` | -0.969 | - |
| `EVT-0006` | 14:17:51 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590750300960` | `ok` | +0.000 | - |
| `EVT-0007` | 14:17:51 | **SUBMIT** | BUY | 0.4220 | $1,044.1 | `Alo` | - | `submitting` | +0.942 | - |
| `EVT-0008` | 14:17:52 | **RESTING** | BUY | 0.4220 | $1,044.1 | `Alo` | `590750362187` | `ok` | +0.942 | - |
| `EVT-0009` | 14:17:57 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590750362187` | `ok` | +0.000 | - |
| `EVT-0010` | 14:17:57 | **SUBMIT** | SELL | 0.2380 | $1,044.6 | `Alo` | - | `submitting` | -0.987 | - |
| `EVT-0011` | 14:17:57 | **RESTING** | SELL | 0.2380 | $1,044.6 | `Alo` | `590750441004` | `ok` | -0.987 | - |
| `EVT-0012` | 14:18:02 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590750441004` | `ok` | +0.000 | - |
| `EVT-0013` | 14:18:02 | **SUBMIT** | SELL | 0.3850 | $1,044.1 | `Alo` | - | `submitting` | -0.991 | - |
| `EVT-0014` | 14:18:03 | **RESTING** | SELL | 0.3850 | $1,044.1 | `Alo` | `590750582845` | `ok` | -0.991 | - |
| `EVT-0015` | 14:18:07 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590750582845` | `ok` | +0.000 | - |
| `EVT-0016` | 14:18:22 | **SUBMIT** | BUY | 0.3850 | $1,043.4 | `Alo` | - | `submitting` | +0.357 | - |
| `EVT-0017` | 14:18:23 | **RESTING** | BUY | 0.3850 | $1,043.4 | `Alo` | `590750845606` | `ok` | +0.357 | - |
| `EVT-0018` | 14:18:25 | **SUBMIT** | BUY | 0.4790 | $1,043.4 | `Alo` | - | `submitting` | +0.996 | - |
| `EVT-0019` | 14:18:27 | **RESTING** | BUY | 0.4790 | $1,043.4 | `Alo` | `590750933751` | `ok` | +0.996 | - |
| `EVT-0020` | 14:18:29 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590750933751` | `ok` | +0.000 | - |
| `EVT-0021` | 14:18:33 | **SUBMIT** | SELL | 0.4790 | $1,044.8 | `Alo` | - | `submitting` | -0.974 | - |
| `EVT-0022` | 14:18:34 | **RESTING** | SELL | 0.4790 | $1,044.8 | `Alo` | `590751171222` | `ok` | -0.974 | - |
| `EVT-0023` | 14:18:39 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590751171222` | `ok` | +0.000 | - |
| `EVT-0024` | 14:18:49 | **SUBMIT** | BUY | 0.4790 | $1,044.6 | `Alo` | - | `submitting` | +0.995 | - |
| `EVT-0025` | 14:18:50 | **RESTING** | BUY | 0.4790 | $1,044.6 | `Alo` | `590751464142` | `ok` | +0.995 | - |
| `EVT-0026` | 14:18:55 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590751464142` | `ok` | +0.000 | - |
| `EVT-0027` | 14:19:32 | **SUBMIT** | SELL | 0.4790 | $1,045.9 | `Alo` | - | `submitting` | +0.220 | - |
| `EVT-0028` | 14:19:32 | **RESTING** | SELL | 0.4790 | $1,045.9 | `Alo` | `590752265810` | `ok` | +0.220 | - |
| `EVT-0029` | 14:19:38 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590752265810` | `ok` | +0.000 | - |
| `EVT-0030` | 14:19:38 | **SUBMIT** | SELL | 0.4790 | $1,045.6 | `Alo` | - | `submitting` | -0.436 | - |
| `EVT-0031` | 14:19:39 | **RESTING** | SELL | 0.4790 | $1,045.6 | `Alo` | `590752379264` | `ok` | -0.436 | - |
| `EVT-0032` | 14:19:42 | **SUBMIT** | SELL | 0.4780 | $1,045.6 | `Alo` | - | `submitting` | -0.986 | - |
| `EVT-0033` | 14:19:42 | **REJECTED** | SELL | 0.4780 | $1,045.6 | `Alo` | - | `rejected` | -0.986 | Post only order would have immediately matched, bbo was 1045.6@1045.7. asset=110022 |
| `EVT-0034` | 14:19:44 | **SUBMIT** | SELL | 0.4780 | $1,045.7 | `Alo` | - | `submitting` | -0.913 | - |
| `EVT-0035` | 14:19:44 | **REJECTED** | SELL | 0.4780 | $1,045.7 | `Alo` | - | `rejected` | -0.913 | Post only order would have immediately matched, bbo was 1045.8@1046. asset=110022 |
| `EVT-0036` | 14:19:46 | **SUBMIT** | SELL | 0.4780 | $1,045.7 | `Alo` | - | `submitting` | -0.913 | - |
| `EVT-0037` | 14:19:46 | **REJECTED** | SELL | 0.4780 | $1,045.7 | `Alo` | - | `rejected` | -0.913 | Post only order would have immediately matched, bbo was 1045.7@1045.8. asset=110022 |
| `EVT-0038` | 14:19:48 | **SUBMIT** | SELL | 0.4780 | $1,045.7 | `Alo` | - | `submitting` | -0.913 | - |
| `EVT-0039` | 14:19:48 | **REJECTED** | SELL | 0.4780 | $1,045.7 | `Alo` | - | `rejected` | -0.913 | Post only order would have immediately matched, bbo was 1045.7@1046. asset=110022 |
| `EVT-0040` | 14:19:50 | **SUBMIT** | SELL | 0.4780 | $1,045.8 | `Alo` | - | `submitting` | -0.927 | - |
| `EVT-0041` | 14:19:50 | **REJECTED** | SELL | 0.4780 | $1,045.8 | `Alo` | - | `rejected` | -0.927 | Post only order would have immediately matched, bbo was 1045.9@1046.1. asset=110022 |
| `EVT-0042` | 14:19:52 | **SUBMIT** | SELL | 0.4780 | $1,045.8 | `Alo` | - | `submitting` | -0.927 | - |
| `EVT-0043` | 14:19:53 | **REJECTED** | SELL | 0.4780 | $1,045.8 | `Alo` | - | `rejected` | -0.927 | Post only order would have immediately matched, bbo was 1045.9@1046. asset=110022 |
| `EVT-0044` | 14:19:54 | **SUBMIT** | SELL | 0.4780 | $1,046.0 | `Alo` | - | `submitting` | -0.986 | - |
| `EVT-0045` | 14:19:55 | **RESTING** | SELL | 0.4780 | $1,046.0 | `Alo` | `590752635768` | `ok` | -0.986 | - |
| `EVT-0046` | 14:20:00 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590752635768` | `ok` | +0.000 | - |
| `EVT-0047` | 14:20:00 | **SUBMIT** | BUY | 0.1980 | $1,045.2 | `Alo` | - | `submitting` | +0.900 | - |
| `EVT-0048` | 14:20:00 | **REJECTED** | BUY | 0.1980 | $1,045.2 | `Alo` | - | `rejected` | +0.900 | Post only order would have immediately matched, bbo was 1045.1@1045.2. asset=110022 |
| `EVT-0049` | 14:20:02 | **SUBMIT** | BUY | 0.4780 | $1,045.2 | `Alo` | - | `submitting` | +0.900 | - |
| `EVT-0050` | 14:20:03 | **RESTING** | BUY | 0.4780 | $1,045.2 | `Alo` | `590752806324` | `ok` | +0.900 | - |
| `EVT-0051` | 14:20:05 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590752806324` | `ok` | +0.000 | - |
| `EVT-0052` | 14:20:05 | **SUBMIT** | SELL | 0.4780 | $1,045.5 | `Alo` | - | `submitting` | -0.924 | - |
| `EVT-0053` | 14:20:06 | **RESTING** | SELL | 0.4780 | $1,045.5 | `Alo` | `590752858701` | `ok` | -0.924 | - |
| `EVT-0054` | 14:20:08 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590752858701` | `ok` | +0.000 | - |
| `EVT-0055` | 14:20:08 | **SUBMIT** | SELL | 0.4780 | $1,045.5 | `Alo` | - | `submitting` | -0.924 | - |
| `EVT-0056` | 14:20:09 | **REJECTED** | SELL | 0.4780 | $1,045.5 | `Alo` | - | `rejected` | -0.924 | Post only order would have immediately matched, bbo was 1045.9@1046. asset=110022 |
| `EVT-0057` | 14:20:10 | **SUBMIT** | SELL | 0.4780 | $1,046.0 | `Alo` | - | `submitting` | -0.383 | - |
| `EVT-0058` | 14:20:11 | **REJECTED** | SELL | 0.4780 | $1,046.0 | `Alo` | - | `rejected` | -0.383 | Reduce only order would increase position. asset=110022 |
| `EVT-0059` | 14:20:15 | **SUBMIT** | BUY | 0.4780 | $1,046.1 | `Alo` | - | `submitting` | +0.928 | - |
| `EVT-0060` | 14:20:15 | **REJECTED** | BUY | 0.4780 | $1,046.1 | `Alo` | - | `rejected` | +0.928 | Post only order would have immediately matched, bbo was 1045.6@1045.7. asset=110022 |
| `EVT-0061` | 14:20:17 | **SUBMIT** | BUY | 0.4780 | $1,046.1 | `Alo` | - | `submitting` | +0.928 | - |
| `EVT-0062` | 14:20:18 | **REJECTED** | BUY | 0.4780 | $1,046.1 | `Alo` | - | `rejected` | +0.928 | Post only order would have immediately matched, bbo was 1045.6@1045.7. asset=110022 |
| `EVT-0063` | 14:20:19 | **SUBMIT** | BUY | 0.4780 | $1,046.1 | `Alo` | - | `submitting` | +0.928 | - |
| `EVT-0064` | 14:20:20 | **REJECTED** | BUY | 0.4780 | $1,046.1 | `Alo` | - | `rejected` | +0.928 | Post only order would have immediately matched, bbo was 1045.7@1045.8. asset=110022 |
| `EVT-0065` | 14:20:26 | **SUBMIT** | SELL | 0.4780 | $1,045.7 | `Alo` | - | `submitting` | -0.930 | - |
| `EVT-0066` | 14:20:26 | **REJECTED** | SELL | 0.4780 | $1,045.7 | `Alo` | - | `rejected` | -0.930 | Post only order would have immediately matched, bbo was 1046.1@1046.2. asset=110022 |
| `EVT-0067` | 14:20:28 | **SUBMIT** | SELL | 0.4780 | $1,045.7 | `Alo` | - | `submitting` | -0.930 | - |
| `EVT-0068` | 14:20:28 | **REJECTED** | SELL | 0.4780 | $1,045.7 | `Alo` | - | `rejected` | -0.930 | Post only order would have immediately matched, bbo was 1046.3@1046.5. asset=110022 |
| `EVT-0069` | 14:20:30 | **SUBMIT** | SELL | 0.4780 | $1,045.7 | `Alo` | - | `submitting` | -0.930 | - |
| `EVT-0070` | 14:20:30 | **REJECTED** | SELL | 0.4780 | $1,045.7 | `Alo` | - | `rejected` | -0.930 | Post only order would have immediately matched, bbo was 1047@1047.1. asset=110022 |
| `EVT-0071` | 14:20:32 | **SUBMIT** | SELL | 0.4780 | $1,047.1 | `Alo` | - | `submitting` | -0.828 | - |
| `EVT-0072` | 14:20:32 | **REJECTED** | SELL | 0.4780 | $1,047.1 | `Alo` | - | `rejected` | -0.828 | Post only order would have immediately matched, bbo was 1047.3@1047.4. asset=110022 |
| `EVT-0073` | 14:20:34 | **SUBMIT** | SELL | 0.4780 | $1,047.1 | `Alo` | - | `submitting` | -0.828 | - |
| `EVT-0074` | 14:20:34 | **RESTING** | SELL | 0.4780 | $1,047.1 | `Alo` | `590753423898` | `ok` | -0.828 | - |
| `EVT-0075` | 14:20:38 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590753423898` | `ok` | +0.000 | - |
| `EVT-0076` | 14:20:38 | **SUBMIT** | SELL | 0.4780 | $1,046.6 | `Alo` | - | `submitting` | -0.989 | - |
| `EVT-0077` | 14:20:39 | **REJECTED** | SELL | 0.4780 | $1,046.6 | `Alo` | - | `rejected` | -0.989 | Post only order would have immediately matched, bbo was 1046.7@1046.8. asset=110022 |
| `EVT-0078` | 14:20:40 | **SUBMIT** | SELL | 0.4780 | $1,046.6 | `Alo` | - | `submitting` | -0.989 | - |
| `EVT-0079` | 14:20:40 | **RESTING** | SELL | 0.4780 | $1,046.6 | `Alo` | `590753568808` | `ok` | -0.989 | - |
| `EVT-0080` | 14:20:53 | **SUBMIT** | BUY | 0.4780 | $1,045.5 | `Alo` | - | `submitting` | -0.841 | - |
| `EVT-0081` | 14:20:53 | **REJECTED** | BUY | 0.4780 | $1,045.5 | `Alo` | - | `rejected` | -0.841 | Post only order would have immediately matched, bbo was 1045.4@1045.5. asset=110022 |
| `EVT-0082` | 14:20:55 | **SUBMIT** | BUY | 0.4780 | $1,045.5 | `Alo` | - | `submitting` | -0.841 | - |
| `EVT-0083` | 14:20:55 | **RESTING** | BUY | 0.4780 | $1,045.5 | `Alo` | `590753848575` | `ok` | -0.841 | - |
| `EVT-0084` | 14:20:59 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590753848575` | `ok` | +0.000 | - |
| `EVT-0085` | 14:20:59 | **SUBMIT** | BUY | 0.4780 | $1,045.7 | `Alo` | - | `submitting` | +0.680 | - |
| `EVT-0086` | 14:20:59 | **RESTING** | BUY | 0.4780 | $1,045.7 | `Alo` | `590753921507` | `ok` | +0.680 | - |
| `EVT-0087` | 14:21:04 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590753921507` | `ok` | +0.000 | - |
| `EVT-0088` | 14:21:04 | **SUBMIT** | BUY | 0.4780 | $1,045.3 | `Alo` | - | `submitting` | +0.968 | - |
| `EVT-0089` | 14:21:05 | **REJECTED** | BUY | 0.4780 | $1,045.3 | `Alo` | - | `rejected` | +0.968 | Reduce only order would increase position. asset=110022 |
| `EVT-0090` | 14:21:07 | **SUBMIT** | BUY | 0.4780 | $1,045.3 | `Alo` | - | `submitting` | +0.968 | - |
| `EVT-0091` | 14:21:07 | **RESTING** | BUY | 0.4780 | $1,045.3 | `Alo` | `590754117073` | `ok` | +0.968 | - |
| `EVT-0092` | 14:21:10 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590754117073` | `ok` | +0.000 | - |
| `EVT-0093` | 14:21:10 | **SUBMIT** | BUY | 0.4780 | $1,045.9 | `Alo` | - | `submitting` | +0.994 | - |
| `EVT-0094` | 14:21:11 | **RESTING** | BUY | 0.4780 | $1,045.9 | `Alo` | `590754196280` | `ok` | +0.994 | - |
| `EVT-0095` | 14:21:15 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590754196280` | `ok` | +0.000 | - |
| `EVT-0096` | 14:21:15 | **SUBMIT** | SELL | 0.2020 | $1,045.7 | `Alo` | - | `submitting` | -0.939 | - |
| `EVT-0097` | 14:21:16 | **RESTING** | SELL | 0.2020 | $1,045.7 | `Alo` | `590754282535` | `ok` | -0.939 | - |
| `EVT-0098` | 14:21:17 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590754282535` | `ok` | +0.000 | - |
| `EVT-0099` | 14:21:17 | **SUBMIT** | SELL | 0.4780 | $1,045.7 | `Alo` | - | `submitting` | -0.939 | - |
| `EVT-0100` | 14:21:18 | **RESTING** | SELL | 0.4780 | $1,045.7 | `Alo` | `590754314772` | `ok` | -0.939 | - |
| `EVT-0101` | 14:21:21 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590754314772` | `ok` | +0.000 | - |
| `EVT-0102` | 14:21:25 | **SUBMIT** | SELL | 0.4780 | $1,045.5 | `Alo` | - | `submitting` | -0.779 | - |
| `EVT-0103` | 14:21:26 | **RESTING** | SELL | 0.4780 | $1,045.5 | `Alo` | `590754480294` | `ok` | -0.779 | - |
| `EVT-0104` | 14:21:32 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590754480294` | `ok` | +0.000 | - |
| `EVT-0105` | 14:21:32 | **SUBMIT** | SELL | 0.2010 | $1,044.6 | `Alo` | - | `submitting` | -0.976 | - |
| `EVT-0106` | 14:21:33 | **RESTING** | SELL | 0.2010 | $1,044.6 | `Alo` | `590754622184` | `ok` | -0.976 | - |
| `EVT-0107` | 14:21:37 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590754622184` | `ok` | +0.000 | - |
| `EVT-0108` | 14:21:47 | **SUBMIT** | SELL | 0.4790 | $1,044.3 | `Alo` | - | `submitting` | -0.908 | - |
| `EVT-0109` | 14:21:47 | **RESTING** | SELL | 0.4790 | $1,044.3 | `Alo` | `590754975123` | `ok` | -0.908 | - |
| `EVT-0110` | 14:21:53 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590754975123` | `ok` | +0.000 | - |
| `EVT-0111` | 14:21:53 | **SUBMIT** | SELL | 0.2010 | $1,044.1 | `Alo` | - | `submitting` | -0.966 | - |
| `EVT-0112` | 14:21:54 | **REJECTED** | SELL | 0.2010 | $1,044.1 | `Alo` | - | `rejected` | -0.966 | Post only order would have immediately matched, bbo was 1044.1@1044.2. asset=110022 |
| `EVT-0113` | 14:21:55 | **SUBMIT** | SELL | 0.4790 | $1,044.1 | `Alo` | - | `submitting` | -0.966 | - |
| `EVT-0114` | 14:21:56 | **REJECTED** | SELL | 0.4790 | $1,044.1 | `Alo` | - | `rejected` | -0.966 | Post only order would have immediately matched, bbo was 1044.1@1044.2. asset=110022 |
| `EVT-0115` | 14:21:57 | **SUBMIT** | SELL | 0.4790 | $1,044.1 | `Alo` | - | `submitting` | -0.966 | - |
| `EVT-0116` | 14:21:59 | **RESTING** | SELL | 0.4790 | $1,044.1 | `Alo` | `590755168723` | `ok` | -0.966 | - |
| `EVT-0117` | 14:22:00 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590755168723` | `ok` | +0.000 | - |
| `EVT-0118` | 14:22:00 | **SUBMIT** | SELL | 0.4790 | $1,044.3 | `Alo` | - | `submitting` | -0.971 | - |
| `EVT-0119` | 14:22:00 | **RESTING** | SELL | 0.4790 | $1,044.3 | `Alo` | `590755211629` | `ok` | -0.971 | - |
| `EVT-0120` | 14:22:04 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590755211629` | `ok` | +0.000 | - |
| `EVT-0121` | 14:22:04 | **SUBMIT** | SELL | 0.2010 | $1,043.7 | `Alo` | - | `submitting` | -0.843 | - |
| `EVT-0122` | 14:22:04 | **RESTING** | SELL | 0.2010 | $1,043.7 | `Alo` | `590755335554` | `ok` | -0.843 | - |
| `EVT-0123` | 14:22:09 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590755335554` | `ok` | +0.000 | - |
| `EVT-0124` | 14:22:09 | **SUBMIT** | SELL | 0.4240 | $1,043.3 | `Alo` | - | `submitting` | -0.955 | - |
| `EVT-0125` | 14:22:09 | **REJECTED** | SELL | 0.4240 | $1,043.3 | `Alo` | - | `rejected` | -0.955 | Post only order would have immediately matched, bbo was 1043.3@1043.4. asset=110022 |
| `EVT-0126` | 14:22:11 | **SUBMIT** | SELL | 0.4790 | $1,043.3 | `Alo` | - | `submitting` | -0.955 | - |
| `EVT-0127` | 14:22:12 | **RESTING** | SELL | 0.4790 | $1,043.3 | `Alo` | `590755458269` | `ok` | -0.955 | - |
| `EVT-0128` | 14:22:14 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590755458269` | `ok` | +0.000 | - |
| `EVT-0129` | 14:22:14 | **SUBMIT** | SELL | 0.4790 | $1,043.0 | `Alo` | - | `submitting` | -0.948 | - |
| `EVT-0130` | 14:22:15 | **RESTING** | SELL | 0.4790 | $1,043.0 | `Alo` | `590755524338` | `ok` | -0.948 | - |
| `EVT-0131` | 14:22:19 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590755524338` | `ok` | +0.000 | - |
| `EVT-0132` | 14:22:19 | **SUBMIT** | SELL | 0.2010 | $1,043.2 | `Alo` | - | `submitting` | -0.983 | - |
| `EVT-0133` | 14:22:20 | **RESTING** | SELL | 0.2010 | $1,043.2 | `Alo` | `590755623948` | `ok` | -0.983 | - |
| `EVT-0134` | 14:22:22 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590755623948` | `ok` | +0.000 | - |
| `EVT-0135` | 14:22:45 | **SUBMIT** | BUY | 0.4790 | $1,041.1 | `Alo` | - | `submitting` | +0.408 | - |
| `EVT-0136` | 14:22:46 | **RESTING** | BUY | 0.4790 | $1,041.1 | `Alo` | `590756093102` | `ok` | +0.408 | - |
| `EVT-0137` | 14:22:52 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590756093102` | `ok` | +0.000 | - |
| `EVT-0138` | 14:22:52 | **SUBMIT** | BUY | 0.4790 | $1,039.7 | `Alo` | - | `submitting` | -0.575 | - |
| `EVT-0139` | 14:22:53 | **REJECTED** | BUY | 0.4790 | $1,039.7 | `Alo` | - | `rejected` | -0.575 | Reduce only order would increase position. asset=110022 |
| `EVT-0140` | 14:22:56 | **SUBMIT** | BUY | 0.4800 | $1,040.9 | `Alo` | - | `submitting` | +0.770 | - |
| `EVT-0141` | 14:22:57 | **RESTING** | BUY | 0.4800 | $1,040.9 | `Alo` | `590756310274` | `ok` | +0.770 | - |
| `EVT-0142` | 14:23:03 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590756310274` | `ok` | +0.000 | - |
| `EVT-0143` | 14:23:03 | **SUBMIT** | BUY | 0.2090 | $1,041.2 | `Alo` | - | `submitting` | +0.846 | - |
| `EVT-0144` | 14:23:04 | **RESTING** | BUY | 0.2090 | $1,041.2 | `Alo` | `590756441958` | `ok` | +0.846 | - |
| `EVT-0145` | 14:23:08 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590756441958` | `ok` | +0.000 | - |
| `EVT-0146` | 14:23:18 | **SUBMIT** | SELL | 0.4800 | $1,041.7 | `Alo` | - | `submitting` | -0.977 | - |
| `EVT-0147` | 14:23:19 | **RESTING** | SELL | 0.4800 | $1,041.7 | `Alo` | `590756747856` | `ok` | -0.977 | - |
| `EVT-0148` | 14:23:24 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590756747856` | `ok` | +0.000 | - |
| `EVT-0149` | 14:23:29 | **SUBMIT** | BUY | 0.4810 | $1,040.4 | `Alo` | - | `submitting` | +0.997 | - |
| `EVT-0150` | 14:23:30 | **RESTING** | BUY | 0.4810 | $1,040.4 | `Alo` | `590756970167` | `ok` | +0.997 | - |
| `EVT-0151` | 14:23:31 | **SUBMIT** | BUY | 0.2080 | $1,040.4 | `Alo` | - | `submitting` | +0.997 | - |
| `EVT-0152` | 14:23:32 | **REJECTED** | BUY | 0.2080 | $1,040.4 | `Alo` | - | `rejected` | +0.997 | Post only order would have immediately matched, bbo was 1040.1@1040.3. asset=110022 |
| `EVT-0153` | 14:23:33 | **SUBMIT** | BUY | 0.2080 | $1,040.4 | `Alo` | - | `submitting` | +0.997 | - |
| `EVT-0154` | 14:23:34 | **RESTING** | BUY | 0.2080 | $1,040.4 | `Alo` | `590757032368` | `ok` | +0.997 | - |
| `EVT-0155` | 14:23:35 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590757032368` | `ok` | +0.000 | - |
| `EVT-0156` | 14:23:39 | **SUBMIT** | SELL | 0.4810 | $1,041.2 | `Alo` | - | `submitting` | -0.265 | - |
| `EVT-0157` | 14:23:40 | **RESTING** | SELL | 0.4810 | $1,041.2 | `Alo` | `590757164813` | `ok` | -0.265 | - |
| `EVT-0158` | 14:23:46 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590757164813` | `ok` | +0.000 | - |
| `EVT-0159` | 14:23:46 | **SUBMIT** | SELL | 0.4810 | $1,040.6 | `Alo` | - | `submitting` | -0.072 | - |
| `EVT-0160` | 14:23:46 | **RESTING** | SELL | 0.4810 | $1,040.6 | `Alo` | `590757273446` | `ok` | -0.072 | - |
| `EVT-0161` | 14:23:51 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590757273446` | `ok` | +0.000 | - |
| `EVT-0162` | 14:23:51 | **SUBMIT** | SELL | 0.4810 | $1,040.0 | `Alo` | - | `submitting` | -0.326 | - |
| `EVT-0163` | 14:23:52 | **RESTING** | SELL | 0.4810 | $1,040.0 | `Alo` | `590757362058` | `ok` | -0.326 | - |
| `EVT-0164` | 14:23:57 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590757362058` | `ok` | +0.000 | - |
| `EVT-0165` | 14:23:57 | **SUBMIT** | SELL | 0.4810 | $1,039.8 | `Alo` | - | `submitting` | -0.315 | - |
| `EVT-0166` | 14:23:57 | **RESTING** | SELL | 0.4810 | $1,039.8 | `Alo` | `590757469601` | `ok` | -0.315 | - |
| `EVT-0167` | 14:24:02 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590757469601` | `ok` | +0.000 | - |
| `EVT-0168` | 14:24:02 | **SUBMIT** | SELL | 0.4810 | $1,039.0 | `Gtc` | - | `submitting` | -0.753 | - |
| `EVT-0169` | 14:24:03 | **RESTING** | SELL | 0.4810 | $1,039.0 | `Gtc` | `590757608426` | `ok` | -0.753 | - |
| `EVT-0170` | 14:24:05 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590757608426` | `ok` | +0.000 | - |
| `EVT-0171` | 14:24:05 | **SUBMIT** | SELL | 0.4810 | $1,039.0 | `Gtc` | - | `submitting` | -0.754 | - |
| `EVT-0172` | 14:24:05 | **RESTING** | SELL | 0.4810 | $1,039.0 | `Gtc` | `590757667485` | `ok` | -0.754 | - |
| `EVT-0173` | 14:24:06 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590757667485` | `ok` | +0.000 | - |
| `EVT-0174` | 14:24:07 | **SUBMIT** | SELL | 0.4810 | $1,038.6 | `Gtc` | - | `submitting` | -0.550 | - |
| `EVT-0175` | 14:24:08 | **FILLED** | SELL | 0.4810 | $1,038.6 | `Gtc` | `590757693280` | `ok` | -0.550 | - |
| `EVT-0176` | 14:24:12 | **SUBMIT** | BUY | 0.4810 | $1,039.0 | `Alo` | - | `submitting` | +0.957 | - |
| `EVT-0177` | 14:24:12 | **REJECTED** | BUY | 0.4810 | $1,039.0 | `Alo` | - | `rejected` | +0.957 | Post only order would have immediately matched, bbo was 1038.8@1039. asset=110022 |
| `EVT-0178` | 14:24:14 | **SUBMIT** | BUY | 0.4810 | $1,039.0 | `Alo` | - | `submitting` | +0.957 | - |
| `EVT-0179` | 14:24:14 | **REJECTED** | BUY | 0.4810 | $1,039.0 | `Alo` | - | `rejected` | +0.957 | Post only order would have immediately matched, bbo was 1038.7@1038.9. asset=110022 |
| `EVT-0180` | 14:24:16 | **SUBMIT** | BUY | 0.4810 | $1,039.0 | `Alo` | - | `submitting` | +0.957 | - |
| `EVT-0181` | 14:24:16 | **REJECTED** | BUY | 0.4810 | $1,039.0 | `Alo` | - | `rejected` | +0.957 | Post only order would have immediately matched, bbo was 1038.6@1038.8. asset=110022 |
| `EVT-0182` | 14:24:39 | **SUBMIT** | SELL | 0.4810 | $1,039.4 | `Alo` | - | `submitting` | -0.988 | - |
| `EVT-0183` | 14:24:40 | **RESTING** | SELL | 0.4810 | $1,039.4 | `Alo` | `590758271916` | `ok` | -0.988 | - |
| `EVT-0184` | 14:24:45 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590758271916` | `ok` | +0.000 | - |
| `EVT-0185` | 14:24:50 | **SUBMIT** | SELL | 0.4810 | $1,038.8 | `Alo` | - | `submitting` | -0.862 | - |
| `EVT-0186` | 14:24:50 | **REJECTED** | SELL | 0.4810 | $1,038.8 | `Alo` | - | `rejected` | -0.862 | Post only order would have immediately matched, bbo was 1038.8@1038.9. asset=110022 |
| `EVT-0187` | 14:24:52 | **SUBMIT** | SELL | 0.4810 | $1,038.8 | `Alo` | - | `submitting` | -0.862 | - |
| `EVT-0188` | 14:24:52 | **REJECTED** | SELL | 0.4810 | $1,038.8 | `Alo` | - | `rejected` | -0.862 | Post only order would have immediately matched, bbo was 1039@1039.1. asset=110022 |
| `EVT-0189` | 14:24:54 | **SUBMIT** | SELL | 0.4810 | $1,038.8 | `Alo` | - | `submitting` | -0.862 | - |
| `EVT-0190` | 14:24:54 | **REJECTED** | SELL | 0.4810 | $1,038.8 | `Alo` | - | `rejected` | -0.862 | Post only order would have immediately matched, bbo was 1038.8@1039. asset=110022 |
| `EVT-0191` | 14:25:06 | **SUBMIT** | SELL | 0.4810 | $1,038.6 | `Alo` | - | `submitting` | -0.967 | - |
| `EVT-0192` | 14:25:06 | **RESTING** | SELL | 0.4810 | $1,038.6 | `Alo` | `590758712025` | `ok` | -0.967 | - |
| `EVT-0193` | 14:25:12 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590758712025` | `ok` | +0.000 | - |
| `EVT-0194` | 14:25:38 | **SUBMIT** | SELL | 0.4820 | $1,038.2 | `Alo` | - | `submitting` | -0.964 | - |
| `EVT-0195` | 14:25:39 | **REJECTED** | SELL | 0.4820 | $1,038.2 | `Alo` | - | `rejected` | -0.964 | Post only order would have immediately matched, bbo was 1038.2@1038.3. asset=110022 |
| `EVT-0196` | 14:25:40 | **SUBMIT** | SELL | 0.4820 | $1,038.2 | `Alo` | - | `submitting` | -0.964 | - |
| `EVT-0197` | 14:25:41 | **RESTING** | SELL | 0.4820 | $1,038.2 | `Alo` | `590759249700` | `ok` | -0.964 | - |
| `EVT-0198` | 14:25:44 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590759249700` | `ok` | +0.000 | - |
| `EVT-0199` | 14:25:44 | **SUBMIT** | SELL | 0.4820 | $1,038.4 | `Alo` | - | `submitting` | -0.960 | - |
| `EVT-0200` | 14:25:45 | **REJECTED** | SELL | 0.4820 | $1,038.4 | `Alo` | - | `rejected` | -0.960 | Post only order would have immediately matched, bbo was 1038.6@1038.7. asset=110022 |
| `EVT-0201` | 14:26:00 | **SUBMIT** | BUY | 0.4820 | $1,038.7 | `Alo` | - | `submitting` | +0.590 | - |
| `EVT-0202` | 14:26:01 | **RESTING** | BUY | 0.4820 | $1,038.7 | `Alo` | `590759584766` | `ok` | +0.590 | - |
| `EVT-0203` | 14:26:06 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590759584766` | `ok` | +0.000 | - |
| `EVT-0204` | 14:26:06 | **SUBMIT** | BUY | 0.4820 | $1,039.8 | `Gtc` | - | `submitting` | -0.314 | - |
| `EVT-0205` | 14:26:07 | **FILLED** | BUY | 0.4820 | $1,039.2 | `Gtc` | `590759755161` | `ok` | -0.314 | - |
| `EVT-0206` | 14:26:10 | **SUBMIT** | BUY | 0.4810 | $1,038.7 | `Alo` | - | `submitting` | +0.983 | - |
| `EVT-0207` | 14:26:11 | **RESTING** | BUY | 0.4810 | $1,038.7 | `Alo` | `590759822577` | `ok` | +0.983 | - |
| `EVT-0208` | 14:26:17 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590759822577` | `ok` | +0.000 | - |
| `EVT-0209` | 14:26:26 | **SUBMIT** | BUY | 0.4810 | $1,039.5 | `Alo` | - | `submitting` | +0.923 | - |
| `EVT-0210` | 14:26:27 | **RESTING** | BUY | 0.4810 | $1,039.5 | `Alo` | `590760111197` | `ok` | +0.923 | - |
| `EVT-0211` | 14:26:33 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590760111197` | `ok` | +0.000 | - |
| `EVT-0212` | 14:26:33 | **SUBMIT** | SELL | 0.1970 | $1,040.2 | `Alo` | - | `submitting` | -0.979 | - |
| `EVT-0213` | 14:26:34 | **RESTING** | SELL | 0.1970 | $1,040.2 | `Alo` | `590760216263` | `ok` | -0.979 | - |
| `EVT-0214` | 14:26:38 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590760216263` | `ok` | +0.000 | - |
| `EVT-0215` | 14:26:53 | **SUBMIT** | BUY | 0.1970 | $1,039.5 | `Alo` | - | `submitting` | -0.142 | - |
| `EVT-0216` | 14:26:54 | **RESTING** | BUY | 0.1970 | $1,039.5 | `Alo` | `590760560310` | `ok` | -0.142 | - |
| `EVT-0217` | 14:27:00 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590760560310` | `ok` | +0.000 | - |
| `EVT-0218` | 14:27:10 | **SUBMIT** | BUY | 0.4810 | $1,040.2 | `Alo` | - | `submitting` | +0.994 | - |
| `EVT-0219` | 14:27:10 | **RESTING** | BUY | 0.4810 | $1,040.2 | `Alo` | `590760906747` | `ok` | +0.994 | - |
| `EVT-0220` | 14:27:16 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590760906747` | `ok` | +0.000 | - |
| `EVT-0221` | 14:27:52 | **SUBMIT** | SELL | 0.4810 | $1,039.9 | `Alo` | - | `submitting` | -0.466 | - |
| `EVT-0222` | 14:27:53 | **REJECTED** | SELL | 0.4810 | $1,039.9 | `Alo` | - | `rejected` | -0.466 | Post only order would have immediately matched, bbo was 1040@1040.1. asset=110022 |
| `EVT-0223` | 14:27:54 | **SUBMIT** | SELL | 0.4810 | $1,039.9 | `Alo` | - | `submitting` | -0.466 | - |
| `EVT-0224` | 14:27:55 | **RESTING** | SELL | 0.4810 | $1,039.9 | `Alo` | `590761639951` | `ok` | -0.466 | - |
| `EVT-0225` | 14:27:57 | **SUBMIT** | SELL | 0.4810 | $1,039.9 | `Alo` | - | `submitting` | -0.994 | - |
| `EVT-0226` | 14:27:58 | **RESTING** | SELL | 0.4810 | $1,039.9 | `Alo` | `590761662005` | `ok` | -0.994 | - |
| `EVT-0227` | 14:27:59 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590761662005` | `ok` | +0.000 | - |
| `EVT-0228` | 14:28:03 | **SUBMIT** | BUY | 0.4810 | $1,040.2 | `Alo` | - | `submitting` | +0.367 | - |
| `EVT-0229` | 14:28:04 | **REJECTED** | BUY | 0.4810 | $1,040.2 | `Alo` | - | `rejected` | +0.367 | Post only order would have immediately matched, bbo was 1040@1040.2. asset=110022 |
| `EVT-0230` | 14:28:05 | **SUBMIT** | BUY | 0.4810 | $1,040.2 | `Alo` | - | `submitting` | +0.367 | - |
| `EVT-0231` | 14:28:06 | **RESTING** | BUY | 0.4810 | $1,040.2 | `Alo` | `590761798270` | `ok` | +0.367 | - |
| `EVT-0232` | 14:28:09 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590761798270` | `ok` | +0.000 | - |
| `EVT-0233` | 14:28:14 | **SUBMIT** | BUY | 0.4810 | $1,041.3 | `Gtc` | - | `submitting` | -0.223 | - |
| `EVT-0234` | 14:28:15 | **FILLED** | BUY | 0.4810 | $1,041.3 | `Gtc` | `590761954611` | `ok` | -0.223 | - |
| `EVT-0235` | 14:28:16 | **SUBMIT** | SELL | 0.1930 | $1,041.3 | `Alo` | - | `submitting` | -0.909 | - |
| `EVT-0236` | 14:28:16 | **RESTING** | SELL | 0.1930 | $1,041.3 | `Alo` | `590761977948` | `ok` | -0.909 | - |
| `EVT-0237` | 14:28:20 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590761977948` | `ok` | +0.000 | - |
| `EVT-0238` | 14:28:20 | **SUBMIT** | BUY | 0.4210 | $1,041.6 | `Alo` | - | `submitting` | +0.989 | - |
| `EVT-0239` | 14:28:21 | **RESTING** | BUY | 0.4210 | $1,041.6 | `Alo` | `590762049432` | `ok` | +0.989 | - |
| `EVT-0240` | 14:28:23 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590762049432` | `ok` | +0.000 | - |
| `EVT-0241` | 14:28:23 | **SUBMIT** | BUY | 0.1930 | $1,041.6 | `Alo` | - | `submitting` | +0.989 | - |
| `EVT-0242` | 14:28:24 | **RESTING** | BUY | 0.1930 | $1,041.6 | `Alo` | `590762101699` | `ok` | +0.989 | - |
| `EVT-0243` | 14:28:25 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590762101699` | `ok` | +0.000 | - |
| `EVT-0244` | 14:28:30 | **SUBMIT** | BUY | 0.1930 | $1,042.7 | `Gtc` | - | `submitting` | -0.976 | - |
| `EVT-0245` | 14:28:31 | **FILLED** | BUY | 0.1930 | $1,042.7 | `Gtc` | `590762234224` | `ok` | -0.976 | - |
| `EVT-0246` | 14:28:32 | **SUBMIT** | SELL | 0.4800 | $1,042.7 | `Alo` | - | `submitting` | -0.976 | - |
| `EVT-0247` | 14:28:33 | **RESTING** | SELL | 0.4800 | $1,042.7 | `Alo` | `590762297061` | `ok` | -0.976 | - |
| `EVT-0248` | 14:28:36 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590762297061` | `ok` | +0.000 | - |
| `EVT-0249` | 14:28:46 | **SUBMIT** | SELL | 0.4800 | $1,042.7 | `Alo` | - | `submitting` | -0.984 | - |
| `EVT-0250` | 14:28:47 | **RESTING** | SELL | 0.4800 | $1,042.7 | `Alo` | `590762542171` | `ok` | -0.984 | - |
| `EVT-0251` | 14:28:52 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590762542171` | `ok` | +0.000 | - |
| `EVT-0252` | 14:28:52 | **SUBMIT** | SELL | 0.1880 | $1,042.4 | `Alo` | - | `submitting` | -0.988 | - |
| `EVT-0253` | 14:28:53 | **RESTING** | SELL | 0.1880 | $1,042.4 | `Alo` | `590762650893` | `ok` | -0.988 | - |
| `EVT-0254` | 14:28:58 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590762650893` | `ok` | +0.000 | - |
| `EVT-0255` | 14:28:58 | **SUBMIT** | SELL | 0.4220 | $1,042.2 | `Alo` | - | `submitting` | -0.772 | - |
| `EVT-0256` | 14:28:58 | **RESTING** | SELL | 0.4220 | $1,042.2 | `Alo` | `590762743309` | `ok` | -0.772 | - |
| `EVT-0257` | 14:29:03 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590762743309` | `ok` | +0.000 | - |
| `EVT-0258` | 14:29:03 | **SUBMIT** | BUY | 0.2350 | $1,042.0 | `Alo` | - | `submitting` | +0.954 | - |
| `EVT-0259` | 14:29:04 | **RESTING** | BUY | 0.2350 | $1,042.0 | `Alo` | `590762891860` | `ok` | +0.954 | - |
| `EVT-0260` | 14:29:06 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590762891860` | `ok` | +0.000 | - |
| `EVT-0261` | 14:29:06 | **SUBMIT** | BUY | 0.4220 | $1,042.0 | `Alo` | - | `submitting` | +0.954 | - |
| `EVT-0262` | 14:29:06 | **RESTING** | BUY | 0.4220 | $1,042.0 | `Alo` | `590762945920` | `ok` | +0.954 | - |
| `EVT-0263` | 14:29:08 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590762945920` | `ok` | +0.000 | - |
| `EVT-0264` | 14:29:34 | **SUBMIT** | BUY | 0.4220 | $1,043.7 | `Gtc` | - | `submitting` | -0.617 | - |
| `EVT-0265` | 14:29:35 | **FILLED** | BUY | 0.4220 | $1,043.7 | `Gtc` | `590763455714` | `ok` | -0.617 | - |
| `EVT-0266` | 14:29:51 | **SUBMIT** | SELL | 0.4790 | $1,043.0 | `Alo` | - | `submitting` | -0.916 | - |
| `EVT-0267` | 14:29:51 | **RESTING** | SELL | 0.4790 | $1,043.0 | `Alo` | `590763719022` | `ok` | -0.916 | - |
| `EVT-0268` | 14:30:17 | **SUBMIT** | BUY | 0.4790 | $1,043.3 | `Alo` | - | `submitting` | +0.508 | - |
| `EVT-0269` | 14:30:18 | **RESTING** | BUY | 0.4790 | $1,043.3 | `Alo` | `590764184945` | `ok` | +0.508 | - |
| `EVT-0270` | 14:30:24 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590764184945` | `ok` | +0.000 | - |
| `EVT-0271` | 14:30:24 | **SUBMIT** | BUY | 0.4790 | $1,043.4 | `Alo` | - | `submitting` | +0.514 | - |
| `EVT-0272` | 14:30:24 | **RESTING** | BUY | 0.4790 | $1,043.4 | `Alo` | `590764326704` | `ok` | +0.514 | - |
| `EVT-0273` | 14:30:29 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590764326704` | `ok` | +0.000 | - |
| `EVT-0274` | 14:30:29 | **SUBMIT** | BUY | 0.4790 | $1,043.5 | `Alo` | - | `submitting` | -0.510 | - |
| `EVT-0275` | 14:30:30 | **RESTING** | BUY | 0.4790 | $1,043.5 | `Alo` | `590764429871` | `ok` | -0.510 | - |
| `EVT-0276` | 14:30:34 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590764429871` | `ok` | +0.000 | - |
| `EVT-0277` | 14:30:34 | **SUBMIT** | BUY | 0.4790 | $1,044.4 | `Gtc` | - | `submitting` | -0.333 | - |
| `EVT-0278` | 14:30:35 | **RESTING** | BUY | 0.4790 | $1,044.4 | `Gtc` | `590764532896` | `ok` | -0.333 | - |
| `EVT-0279` | 14:30:36 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590764532896` | `ok` | +0.000 | - |
| `EVT-0280` | 14:30:36 | **SUBMIT** | BUY | 0.4790 | $1,044.4 | `Gtc` | - | `submitting` | -0.333 | - |
| `EVT-0281` | 14:30:37 | **FILLED** | BUY | 0.4790 | $1,044.4 | `Gtc` | `590764573299` | `ok` | -0.333 | - |
| `EVT-0282` | 14:30:50 | **SUBMIT** | BUY | 0.4790 | $1,043.8 | `Alo` | - | `submitting` | +0.852 | - |
| `EVT-0283` | 14:30:50 | **RESTING** | BUY | 0.4790 | $1,043.8 | `Alo` | `590764748947` | `ok` | +0.852 | - |
| `EVT-0284` | 14:30:56 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590764748947` | `ok` | +0.000 | - |
| `EVT-0285` | 14:30:56 | **SUBMIT** | SELL | 0.1770 | $1,043.9 | `Alo` | - | `submitting` | -0.982 | - |
| `EVT-0286` | 14:30:56 | **RESTING** | SELL | 0.1770 | $1,043.9 | `Alo` | `590764832630` | `ok` | -0.982 | - |
| `EVT-0287` | 14:30:59 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590764832630` | `ok` | +0.000 | - |
| `EVT-0288` | 14:30:59 | **SUBMIT** | SELL | 0.4790 | $1,043.9 | `Alo` | - | `submitting` | -0.982 | - |
| `EVT-0289` | 14:31:00 | **RESTING** | SELL | 0.4790 | $1,043.9 | `Alo` | `590764901085` | `ok` | -0.982 | - |
| `EVT-0290` | 14:31:01 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590764901085` | `ok` | +0.000 | - |
| `EVT-0291` | 14:31:38 | **SUBMIT** | SELL | 0.4790 | $1,044.2 | `Alo` | - | `submitting` | -0.087 | - |
| `EVT-0292` | 14:31:39 | **RESTING** | SELL | 0.4790 | $1,044.2 | `Alo` | `590765544192` | `ok` | -0.087 | - |
| `EVT-0293` | 14:31:44 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590765544192` | `ok` | +0.000 | - |
| `EVT-0294` | 14:31:44 | **SUBMIT** | SELL | 0.4790 | $1,043.7 | `Alo` | - | `submitting` | -0.899 | - |
| `EVT-0295` | 14:31:45 | **RESTING** | SELL | 0.4790 | $1,043.7 | `Alo` | `590765615298` | `ok` | -0.899 | - |
| `EVT-0296` | 14:31:49 | **SUBMIT** | SELL | 0.4790 | $1,043.7 | `Alo` | - | `submitting` | -0.899 | - |
| `EVT-0297` | 14:31:49 | **RESTING** | SELL | 0.4790 | $1,043.7 | `Alo` | `590765720604` | `ok` | -0.899 | - |
| `EVT-0298` | 14:31:50 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590765720604` | `ok` | +0.000 | - |
| `EVT-0299` | 14:31:51 | **SUBMIT** | BUY | 0.4790 | $1,043.9 | `Alo` | - | `submitting` | +0.750 | - |
| `EVT-0300` | 14:31:51 | **RESTING** | BUY | 0.4790 | $1,043.9 | `Alo` | `590765745719` | `ok` | +0.750 | - |
| `EVT-0301` | 14:31:53 | **SUBMIT** | BUY | 0.4790 | $1,043.9 | `Alo` | - | `submitting` | +0.750 | - |
| `EVT-0302` | 14:31:54 | **REJECTED** | BUY | 0.4790 | $1,043.9 | `Alo` | - | `rejected` | +0.750 | Post only order would have immediately matched, bbo was 1043.6@1043.9. asset=110022 |
| `EVT-0303` | 14:31:56 | **SUBMIT** | SELL | 0.4790 | $1,043.8 | `Alo` | - | `submitting` | -0.894 | - |
| `EVT-0304` | 14:31:56 | **RESTING** | SELL | 0.4790 | $1,043.8 | `Alo` | `590765832807` | `ok` | -0.894 | - |
| `EVT-0305` | 14:32:00 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590765832807` | `ok` | +0.000 | - |
| `EVT-0306` | 14:32:00 | **SUBMIT** | SELL | 0.1760 | $1,043.5 | `Alo` | - | `submitting` | -0.961 | - |
| `EVT-0307` | 14:32:01 | **RESTING** | SELL | 0.1760 | $1,043.5 | `Alo` | `590765923796` | `ok` | -0.961 | - |
| `EVT-0308` | 14:32:32 | **SUBMIT** | BUY | 0.1760 | $1,042.1 | `Alo` | - | `submitting` | +0.855 | - |
| `EVT-0309` | 14:32:33 | **RESTING** | BUY | 0.1760 | $1,042.1 | `Alo` | `590766482110` | `ok` | +0.855 | - |
| `EVT-0310` | 14:32:38 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590766482110` | `ok` | +0.000 | - |
| `EVT-0311` | 14:32:38 | **SUBMIT** | BUY | 0.1760 | $1,042.2 | `Alo` | - | `submitting` | -0.393 | - |
| `EVT-0312` | 14:32:39 | **RESTING** | BUY | 0.1760 | $1,042.2 | `Alo` | `590766585653` | `ok` | -0.393 | - |
| `EVT-0313` | 14:32:44 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590766585653` | `ok` | +0.000 | - |
| `EVT-0314` | 14:32:44 | **SUBMIT** | BUY | 0.1760 | $1,042.6 | `Alo` | - | `submitting` | -0.630 | - |
| `EVT-0315` | 14:32:44 | **RESTING** | BUY | 0.1760 | $1,042.6 | `Alo` | `590766659844` | `ok` | -0.630 | - |
| `EVT-0316` | 14:32:49 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590766659844` | `ok` | +0.000 | - |
| `EVT-0317` | 14:32:49 | **SUBMIT** | BUY | 0.1760 | $1,043.1 | `Alo` | - | `submitting` | +0.613 | - |
| `EVT-0318` | 14:32:50 | **RESTING** | BUY | 0.1760 | $1,043.1 | `Alo` | `590766788788` | `ok` | +0.613 | - |
| `EVT-0319` | 14:32:54 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590766788788` | `ok` | +0.000 | - |
| `EVT-0320` | 14:32:54 | **SUBMIT** | BUY | 0.1760 | $1,043.3 | `Alo` | - | `submitting` | -0.994 | - |
| `EVT-0321` | 14:32:55 | **REJECTED** | BUY | 0.1760 | $1,043.3 | `Alo` | - | `rejected` | -0.994 | Post only order would have immediately matched, bbo was 1043@1043.1. asset=110022 |
| `EVT-0322` | 14:32:57 | **SUBMIT** | BUY | 0.1760 | $1,043.3 | `Alo` | - | `submitting` | -0.994 | - |
| `EVT-0323` | 14:32:57 | **REJECTED** | BUY | 0.1760 | $1,043.3 | `Alo` | - | `rejected` | -0.994 | Post only order would have immediately matched, bbo was 1042.8@1043. asset=110022 |
| `EVT-0324` | 14:32:59 | **SUBMIT** | BUY | 0.1760 | $1,043.3 | `Alo` | - | `submitting` | -0.994 | - |
| `EVT-0325` | 14:32:59 | **REJECTED** | BUY | 0.1760 | $1,043.3 | `Alo` | - | `rejected` | -0.994 | Post only order would have immediately matched, bbo was 1042.2@1042.3. asset=110022 |
| `EVT-0326` | 14:33:01 | **SUBMIT** | BUY | 0.1760 | $1,042.9 | `Alo` | - | `submitting` | +0.513 | - |
| `EVT-0327` | 14:33:02 | **REJECTED** | BUY | 0.1760 | $1,042.9 | `Alo` | - | `rejected` | +0.513 | Post only order would have immediately matched, bbo was 1041.8@1041.9. asset=110022 |
| `EVT-0328` | 14:33:03 | **SUBMIT** | BUY | 0.1760 | $1,042.9 | `Alo` | - | `submitting` | +0.513 | - |
| `EVT-0329` | 14:33:04 | **REJECTED** | BUY | 0.1760 | $1,042.9 | `Alo` | - | `rejected` | +0.513 | Post only order would have immediately matched, bbo was 1041.9@1042. asset=110022 |
| `EVT-0330` | 14:33:20 | **SUBMIT** | BUY | 0.1760 | $1,042.3 | `Alo` | - | `submitting` | -0.916 | - |
| `EVT-0331` | 14:33:21 | **RESTING** | BUY | 0.1760 | $1,042.3 | `Alo` | `590767304296` | `ok` | -0.916 | - |
| `EVT-0332` | 14:33:27 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590767304296` | `ok` | +0.000 | - |
| `EVT-0333` | 14:33:27 | **SUBMIT** | BUY | 0.1760 | $1,043.1 | `Alo` | - | `submitting` | +0.546 | - |
| `EVT-0334` | 14:33:27 | **REJECTED** | BUY | 0.1760 | $1,043.1 | `Alo` | - | `rejected` | +0.546 | Post only order would have immediately matched, bbo was 1042.9@1043.1. asset=110022 |
| `EVT-0335` | 14:33:29 | **SUBMIT** | BUY | 0.1760 | $1,043.1 | `Alo` | - | `submitting` | +0.546 | - |
| `EVT-0336` | 14:33:29 | **RESTING** | BUY | 0.1760 | $1,043.1 | `Alo` | `590767447982` | `ok` | +0.546 | - |
| `EVT-0337` | 14:33:32 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590767447982` | `ok` | +0.000 | - |
| `EVT-0338` | 14:33:32 | **SUBMIT** | BUY | 0.1760 | $1,043.6 | `Alo` | - | `submitting` | -0.926 | - |
| `EVT-0339` | 14:33:33 | **RESTING** | BUY | 0.1760 | $1,043.6 | `Alo` | `590767519059` | `ok` | -0.926 | - |
| `EVT-0340` | 14:33:38 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590767519059` | `ok` | +0.000 | - |
| `EVT-0341` | 14:33:38 | **SUBMIT** | BUY | 0.1760 | $1,043.5 | `Alo` | - | `submitting` | -0.077 | - |
| `EVT-0342` | 14:33:38 | **REJECTED** | BUY | 0.1760 | $1,043.5 | `Alo` | - | `rejected` | -0.077 | Reduce only order would increase position. asset=110022 |
| `EVT-0343` | 14:33:42 | **SUBMIT** | BUY | 0.4790 | $1,043.9 | `Alo` | - | `submitting` | +0.842 | - |
| `EVT-0344` | 14:33:43 | **REJECTED** | BUY | 0.4790 | $1,043.9 | `Alo` | - | `rejected` | +0.842 | Post only order would have immediately matched, bbo was 1043.6@1043.8. asset=110022 |
| `EVT-0345` | 14:33:44 | **SUBMIT** | BUY | 0.4790 | $1,043.9 | `Alo` | - | `submitting` | +0.842 | - |
| `EVT-0346` | 14:33:45 | **REJECTED** | BUY | 0.4790 | $1,043.9 | `Alo` | - | `rejected` | +0.842 | Post only order would have immediately matched, bbo was 1043.5@1043.8. asset=110022 |
| `EVT-0347` | 14:33:46 | **SUBMIT** | BUY | 0.4790 | $1,043.9 | `Alo` | - | `submitting` | +0.842 | - |
| `EVT-0348` | 14:33:47 | **RESTING** | BUY | 0.4790 | $1,043.9 | `Alo` | `590767768278` | `ok` | +0.842 | - |
| `EVT-0349` | 14:33:48 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590767768278` | `ok` | +0.000 | - |
| `EVT-0350` | 14:33:58 | **SUBMIT** | SELL | 0.4790 | $1,044.4 | `Alo` | - | `submitting` | -0.854 | - |
| `EVT-0351` | 14:33:58 | **RESTING** | SELL | 0.4790 | $1,044.4 | `Alo` | `590767922598` | `ok` | -0.854 | - |
| `EVT-0352` | 14:34:04 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590767922598` | `ok` | +0.000 | - |
| `EVT-0353` | 14:34:04 | **SUBMIT** | BUY | 0.1750 | $1,044.6 | `Alo` | - | `submitting` | +0.961 | - |
| `EVT-0354` | 14:34:05 | **RESTING** | BUY | 0.1750 | $1,044.6 | `Alo` | `590768100993` | `ok` | +0.961 | - |
| `EVT-0355` | 14:34:06 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590768100993` | `ok` | +0.000 | - |
| `EVT-0356` | 14:34:06 | **SUBMIT** | BUY | 0.4790 | $1,044.6 | `Alo` | - | `submitting` | +0.961 | - |
| `EVT-0357` | 14:34:07 | **RESTING** | BUY | 0.4790 | $1,044.6 | `Alo` | `590768133012` | `ok` | +0.961 | - |
| `EVT-0358` | 14:34:09 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590768133012` | `ok` | +0.000 | - |
| `EVT-0359` | 14:34:14 | **SUBMIT** | BUY | 0.4790 | $1,046.0 | `Gtc` | - | `submitting` | +0.753 | - |
| `EVT-0360` | 14:34:15 | **FILLED** | BUY | 0.4790 | $1,045.8 | `Gtc` | `590768240741` | `ok` | +0.753 | - |
| `EVT-0361` | 14:34:16 | **SUBMIT** | BUY | 0.4780 | $1,045.7 | `Alo` | - | `submitting` | +0.753 | - |
| `EVT-0362` | 14:34:17 | **REJECTED** | BUY | 0.4780 | $1,045.7 | `Alo` | - | `rejected` | +0.753 | Post only order would have immediately matched, bbo was 1045.5@1045.6. asset=110022 |
| `EVT-0363` | 14:34:18 | **SUBMIT** | BUY | 0.4780 | $1,045.7 | `Alo` | - | `submitting` | +0.753 | - |
| `EVT-0364` | 14:34:19 | **REJECTED** | BUY | 0.4780 | $1,045.7 | `Alo` | - | `rejected` | +0.753 | Post only order would have immediately matched, bbo was 1045.4@1045.6. asset=110022 |
| `EVT-0365` | 14:34:35 | **SUBMIT** | SELL | 0.4790 | $1,043.9 | `Alo` | - | `submitting` | -0.875 | - |
| `EVT-0366` | 14:34:35 | **RESTING** | SELL | 0.4790 | $1,043.9 | `Alo` | `590768549016` | `ok` | -0.875 | - |
| `EVT-0367` | 14:34:41 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590768549016` | `ok` | +0.000 | - |
| `EVT-0368` | 14:34:41 | **SUBMIT** | BUY | 0.1700 | $1,044.2 | `Alo` | - | `submitting` | +0.993 | - |
| `EVT-0369` | 14:34:42 | **RESTING** | BUY | 0.1700 | $1,044.2 | `Alo` | `590768644696` | `ok` | +0.993 | - |
| `EVT-0370` | 14:34:43 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590768644696` | `ok` | +0.000 | - |
| `EVT-0371` | 14:34:43 | **SUBMIT** | BUY | 0.4790 | $1,044.2 | `Alo` | - | `submitting` | +0.993 | - |
| `EVT-0372` | 14:34:44 | **RESTING** | BUY | 0.4790 | $1,044.2 | `Alo` | `590768688057` | `ok` | +0.993 | - |
| `EVT-0373` | 14:34:46 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590768688057` | `ok` | +0.000 | - |
| `EVT-0374` | 14:35:02 | **SUBMIT** | BUY | 0.4790 | $1,043.6 | `Alo` | - | `submitting` | +0.973 | - |
| `EVT-0375` | 14:35:03 | **RESTING** | BUY | 0.4790 | $1,043.6 | `Alo` | `590768974085` | `ok` | +0.973 | - |
| `EVT-0376` | 14:35:08 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590768974085` | `ok` | +0.000 | - |
| `EVT-0377` | 14:35:13 | **SUBMIT** | SELL | 0.4780 | $1,045.5 | `Alo` | - | `submitting` | -0.996 | - |
| `EVT-0378` | 14:35:13 | **RESTING** | SELL | 0.4780 | $1,045.5 | `Alo` | `590769184177` | `ok` | -0.996 | - |
| `EVT-0379` | 14:35:19 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590769184177` | `ok` | +0.000 | - |
| `EVT-0380` | 14:35:23 | **SUBMIT** | BUY | 0.4780 | $1,044.6 | `Alo` | - | `submitting` | -0.119 | - |
| `EVT-0381` | 14:35:24 | **REJECTED** | BUY | 0.4780 | $1,044.6 | `Alo` | - | `rejected` | -0.119 | Post only order would have immediately matched, bbo was 1044.5@1044.6. asset=110022 |
| `EVT-0382` | 14:35:25 | **SUBMIT** | BUY | 0.4780 | $1,044.6 | `Alo` | - | `submitting` | -0.239 | - |
| `EVT-0383` | 14:35:26 | **REJECTED** | BUY | 0.4780 | $1,044.6 | `Alo` | - | `rejected` | -0.239 | Post only order would have immediately matched, bbo was 1044.3@1044.4. asset=110022 |
| `EVT-0384` | 14:35:27 | **SUBMIT** | BUY | 0.4780 | $1,044.6 | `Alo` | - | `submitting` | -0.258 | - |
| `EVT-0385` | 14:35:28 | **REJECTED** | BUY | 0.4780 | $1,044.6 | `Alo` | - | `rejected` | -0.258 | Post only order would have immediately matched, bbo was 1044.1@1044.5. asset=110022 |
| `EVT-0386` | 14:35:30 | **SUBMIT** | BUY | 0.4780 | $1,044.3 | `Alo` | - | `submitting` | +0.170 | - |
| `EVT-0387` | 14:35:30 | **RESTING** | BUY | 0.4780 | $1,044.3 | `Alo` | `590769402695` | `ok` | +0.170 | - |
| `EVT-0388` | 14:35:35 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590769402695` | `ok` | +0.000 | - |
| `EVT-0389` | 14:35:35 | **SUBMIT** | BUY | 0.4780 | $1,045.0 | `Alo` | - | `submitting` | +0.386 | - |
| `EVT-0390` | 14:35:35 | **RESTING** | BUY | 0.4780 | $1,045.0 | `Alo` | `590769496582` | `ok` | +0.386 | - |
| `EVT-0391` | 14:35:40 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590769496582` | `ok` | +0.000 | - |
| `EVT-0392` | 14:35:40 | **SUBMIT** | BUY | 0.4780 | $1,045.1 | `Alo` | - | `submitting` | -0.456 | - |
| `EVT-0393` | 14:35:41 | **REJECTED** | BUY | 0.4780 | $1,045.1 | `Alo` | - | `rejected` | -0.456 | Post only order would have immediately matched, bbo was 1044.8@1045. asset=110022 |
| `EVT-0394` | 14:35:42 | **SUBMIT** | SELL | 0.4780 | $1,045.2 | `Alo` | - | `submitting` | -0.996 | - |
| `EVT-0395` | 14:35:43 | **RESTING** | SELL | 0.4780 | $1,045.2 | `Alo` | `590769602455` | `ok` | -0.996 | - |
| `EVT-0396` | 14:35:46 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590769602455` | `ok` | +0.000 | - |
| `EVT-0397` | 14:35:46 | **SUBMIT** | BUY | 0.4780 | $1,045.1 | `Alo` | - | `submitting` | +0.909 | - |
| `EVT-0398` | 14:35:46 | **RESTING** | BUY | 0.4780 | $1,045.1 | `Alo` | `590769655315` | `ok` | +0.909 | - |
| `EVT-0399` | 14:35:48 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590769655315` | `ok` | +0.000 | - |
| `EVT-0400` | 14:35:48 | **SUBMIT** | BUY | 0.4780 | $1,045.1 | `Alo` | - | `submitting` | +0.909 | - |
| `EVT-0401` | 14:35:49 | **RESTING** | BUY | 0.4780 | $1,045.1 | `Alo` | `590769684922` | `ok` | +0.909 | - |
| `EVT-0402` | 14:35:51 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590769684922` | `ok` | +0.000 | - |
| `EVT-0403` | 14:36:01 | **SUBMIT** | BUY | 0.4780 | $1,044.8 | `Alo` | - | `submitting` | -0.783 | - |
| `EVT-0404` | 14:36:02 | **REJECTED** | BUY | 0.4780 | $1,044.8 | `Alo` | - | `rejected` | -0.783 | Post only order would have immediately matched, bbo was 1044.7@1044.8. asset=110022 |
| `EVT-0405` | 14:36:03 | **SUBMIT** | BUY | 0.4780 | $1,044.8 | `Alo` | - | `submitting` | -0.783 | - |
| `EVT-0406` | 14:36:04 | **RESTING** | BUY | 0.4780 | $1,044.8 | `Alo` | `590769910358` | `ok` | -0.783 | - |
| `EVT-0407` | 14:36:07 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590769910358` | `ok` | +0.000 | - |
| `EVT-0408` | 14:36:07 | **SUBMIT** | BUY | 0.4780 | $1,045.2 | `Alo` | - | `submitting` | +0.175 | - |
| `EVT-0409` | 14:36:08 | **RESTING** | BUY | 0.4780 | $1,045.2 | `Alo` | `590769973317` | `ok` | +0.175 | - |
| `EVT-0410` | 14:36:28 | **SUBMIT** | BUY | 0.4790 | $1,044.5 | `Alo` | - | `submitting` | +0.995 | - |
| `EVT-0411` | 14:36:29 | **RESTING** | BUY | 0.4790 | $1,044.5 | `Alo` | `590770378045` | `ok` | +0.995 | - |
| `EVT-0412` | 14:36:34 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590770378045` | `ok` | +0.000 | - |
| `EVT-0413` | 14:36:34 | **SUBMIT** | BUY | 0.1700 | $1,045.3 | `Alo` | - | `submitting` | +0.970 | - |
| `EVT-0414` | 14:36:35 | **RESTING** | BUY | 0.1700 | $1,045.3 | `Alo` | `590770479486` | `ok` | +0.970 | - |
| `EVT-0415` | 14:36:40 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590770479486` | `ok` | +0.000 | - |
| `EVT-0416` | 14:36:44 | **SUBMIT** | SELL | 0.1700 | $1,044.1 | `Alo` | - | `submitting` | -0.478 | - |
| `EVT-0417` | 14:36:45 | **REJECTED** | SELL | 0.1700 | $1,044.1 | `Alo` | - | `rejected` | -0.478 | Post only order would have immediately matched, bbo was 1044.1@1044.2. asset=110022 |
| `EVT-0418` | 14:36:46 | **SUBMIT** | SELL | 0.1700 | $1,044.1 | `Alo` | - | `submitting` | -0.478 | - |
| `EVT-0419` | 14:36:47 | **RESTING** | SELL | 0.1700 | $1,044.1 | `Alo` | `590770630207` | `ok` | -0.478 | - |
| `EVT-0420` | 14:36:50 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590770630207` | `ok` | +0.000 | - |
| `EVT-0421` | 14:37:06 | **SUBMIT** | SELL | 0.4790 | $1,043.1 | `Alo` | - | `submitting` | -0.935 | - |
| `EVT-0422` | 14:37:06 | **RESTING** | SELL | 0.4790 | $1,043.1 | `Alo` | `590770956225` | `ok` | -0.935 | - |
| `EVT-0423` | 14:37:21 | **SUBMIT** | BUY | 0.4790 | $1,043.4 | `Alo` | - | `submitting` | +0.984 | - |
| `EVT-0424` | 14:37:22 | **RESTING** | BUY | 0.4790 | $1,043.4 | `Alo` | `590771169491` | `ok` | +0.984 | - |
| `EVT-0425` | 14:37:26 | **SUBMIT** | BUY | 0.4790 | $1,043.4 | `Alo` | - | `submitting` | +0.984 | - |
| `EVT-0426` | 14:37:27 | **RESTING** | BUY | 0.4790 | $1,043.4 | `Alo` | `590771257477` | `ok` | +0.984 | - |
| `EVT-0427` | 14:37:28 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590771257477` | `ok` | +0.000 | - |
| `EVT-0428` | 14:37:32 | **SUBMIT** | BUY | 0.4790 | $1,044.6 | `Alo` | - | `submitting` | +0.867 | - |
| `EVT-0429` | 14:37:33 | **REJECTED** | BUY | 0.4790 | $1,044.6 | `Alo` | - | `rejected` | +0.867 | Post only order would have immediately matched, bbo was 1044.4@1044.6. asset=110022 |
| `EVT-0430` | 14:37:34 | **SUBMIT** | BUY | 0.4790 | $1,044.6 | `Alo` | - | `submitting` | +0.867 | - |
| `EVT-0431` | 14:37:35 | **RESTING** | BUY | 0.4790 | $1,044.6 | `Alo` | `590771372201` | `ok` | +0.867 | - |
| `EVT-0432` | 14:37:39 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590771372201` | `ok` | +0.000 | - |
| `EVT-0433` | 14:37:39 | **SUBMIT** | BUY | 0.1670 | $1,044.8 | `Alo` | - | `submitting` | +0.966 | - |
| `EVT-0434` | 14:37:39 | **REJECTED** | BUY | 0.1670 | $1,044.8 | `Alo` | - | `rejected` | +0.966 | Post only order would have immediately matched, bbo was 1044.6@1044.8. asset=110022 |
| `EVT-0435` | 14:37:41 | **SUBMIT** | BUY | 0.4790 | $1,044.8 | `Alo` | - | `submitting` | +0.966 | - |
| `EVT-0436` | 14:37:42 | **RESTING** | BUY | 0.4790 | $1,044.8 | `Alo` | `590771478163` | `ok` | +0.966 | - |
| `EVT-0437` | 14:37:44 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590771478163` | `ok` | +0.000 | - |
| `EVT-0438` | 14:37:44 | **SUBMIT** | SELL | 0.4780 | $1,045.2 | `Alo` | - | `submitting` | -0.826 | - |
| `EVT-0439` | 14:37:45 | **RESTING** | SELL | 0.4780 | $1,045.2 | `Alo` | `590771510323` | `ok` | -0.826 | - |
| `EVT-0440` | 14:37:49 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590771510323` | `ok` | +0.000 | - |
| `EVT-0441` | 14:38:04 | **SUBMIT** | BUY | 0.4780 | $1,045.9 | `Alo` | - | `submitting` | +0.839 | - |
| `EVT-0442` | 14:38:05 | **REJECTED** | BUY | 0.4780 | $1,045.9 | `Alo` | - | `rejected` | +0.839 | Post only order would have immediately matched, bbo was 1045.8@1045.9. asset=110022 |
| `EVT-0443` | 14:38:06 | **SUBMIT** | BUY | 0.4780 | $1,045.9 | `Alo` | - | `submitting` | +0.839 | - |
| `EVT-0444` | 14:38:07 | **RESTING** | BUY | 0.4780 | $1,045.9 | `Alo` | `590771936601` | `ok` | +0.839 | - |
| `EVT-0445` | 14:38:11 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590771936601` | `ok` | +0.000 | - |
| `EVT-0446` | 14:38:15 | **SUBMIT** | SELL | 0.4780 | $1,046.6 | `Alo` | - | `submitting` | -0.824 | - |
| `EVT-0447` | 14:38:16 | **RESTING** | SELL | 0.4780 | $1,046.6 | `Alo` | `590772110097` | `ok` | -0.824 | - |
| `EVT-0448` | 14:38:21 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590772110097` | `ok` | +0.000 | - |
| `EVT-0449` | 14:38:22 | **SUBMIT** | BUY | 0.1670 | $1,046.0 | `Alo` | - | `submitting` | +0.983 | - |
| `EVT-0450` | 14:38:22 | **RESTING** | BUY | 0.1670 | $1,046.0 | `Alo` | `590772240349` | `ok` | +0.983 | - |
| `EVT-0451` | 14:38:27 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590772240349` | `ok` | +0.000 | - |
| `EVT-0452` | 14:38:27 | **SUBMIT** | BUY | 0.4150 | $1,047.5 | `Alo` | - | `submitting` | +0.841 | - |
| `EVT-0453` | 14:38:27 | **REJECTED** | BUY | 0.4150 | $1,047.5 | `Alo` | - | `rejected` | +0.841 | Post only order would have immediately matched, bbo was 1047@1047.1. asset=110022 |
| `EVT-0454` | 14:38:29 | **SUBMIT** | BUY | 0.4770 | $1,047.5 | `Alo` | - | `submitting` | +0.841 | - |
| `EVT-0455` | 14:38:29 | **REJECTED** | BUY | 0.4770 | $1,047.5 | `Alo` | - | `rejected` | +0.841 | Post only order would have immediately matched, bbo was 1047.2@1047.3. asset=110022 |
| `EVT-0456` | 14:38:31 | **SUBMIT** | BUY | 0.4770 | $1,047.5 | `Alo` | - | `submitting` | +0.841 | - |
| `EVT-0457` | 14:38:32 | **REJECTED** | BUY | 0.4770 | $1,047.5 | `Alo` | - | `rejected` | +0.841 | Post only order would have immediately matched, bbo was 1047.4@1047.5. asset=110022 |
| `EVT-0458` | 14:38:33 | **SUBMIT** | BUY | 0.4770 | $1,047.2 | `Alo` | - | `submitting` | +0.980 | - |
| `EVT-0459` | 14:38:34 | **RESTING** | BUY | 0.4770 | $1,047.2 | `Alo` | `590772486936` | `ok` | +0.980 | - |
| `EVT-0460` | 14:38:38 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590772486936` | `ok` | +0.000 | - |
| `EVT-0461` | 14:38:38 | **SUBMIT** | SELL | 0.4770 | $1,047.8 | `Alo` | - | `submitting` | -0.983 | - |
| `EVT-0462` | 14:38:38 | **REJECTED** | SELL | 0.4770 | $1,047.8 | `Alo` | - | `rejected` | -0.983 | Post only order would have immediately matched, bbo was 1048@1048.1. asset=110022 |
| `EVT-0463` | 14:38:40 | **SUBMIT** | SELL | 0.4770 | $1,047.8 | `Alo` | - | `submitting` | -0.983 | - |
| `EVT-0464` | 14:38:40 | **REJECTED** | SELL | 0.4770 | $1,047.8 | `Alo` | - | `rejected` | -0.983 | Post only order would have immediately matched, bbo was 1048.2@1048.3. asset=110022 |
| `EVT-0465` | 14:38:42 | **SUBMIT** | SELL | 0.4770 | $1,047.8 | `Alo` | - | `submitting` | -0.983 | - |
| `EVT-0466` | 14:38:42 | **REJECTED** | SELL | 0.4770 | $1,047.8 | `Alo` | - | `rejected` | -0.983 | Post only order would have immediately matched, bbo was 1048.6@1048.7. asset=110022 |
| `EVT-0467` | 14:38:58 | **SUBMIT** | BUY | 0.4770 | $1,048.6 | `Alo` | - | `submitting` | +0.991 | - |
| `EVT-0468` | 14:38:59 | **RESTING** | BUY | 0.4770 | $1,048.6 | `Alo` | `590773011792` | `ok` | +0.991 | - |
| `EVT-0469` | 14:39:05 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590773011792` | `ok` | +0.000 | - |
| `EVT-0470` | 14:39:05 | **SUBMIT** | BUY | 0.1660 | $1,049.1 | `Alo` | - | `submitting` | +0.966 | - |
| `EVT-0471` | 14:39:05 | **RESTING** | BUY | 0.1660 | $1,049.1 | `Alo` | `590773189275` | `ok` | +0.966 | - |
| `EVT-0472` | 14:39:10 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590773189275` | `ok` | +0.000 | - |
| `EVT-0473` | 14:39:10 | **SUBMIT** | SELL | 0.4150 | $1,049.3 | `Alo` | - | `submitting` | -0.978 | - |
| `EVT-0474` | 14:39:11 | **RESTING** | SELL | 0.4150 | $1,049.3 | `Alo` | `590773310419` | `ok` | -0.978 | - |
| `EVT-0475` | 14:39:13 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590773310419` | `ok` | +0.000 | - |
| `EVT-0476` | 14:39:13 | **SUBMIT** | SELL | 0.1660 | $1,049.3 | `Alo` | - | `submitting` | -0.978 | - |
| `EVT-0477` | 14:39:13 | **RESTING** | SELL | 0.1660 | $1,049.3 | `Alo` | `590773348608` | `ok` | -0.978 | - |
| `EVT-0478` | 14:39:15 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590773348608` | `ok` | +0.000 | - |
| `EVT-0479` | 14:39:36 | **SUBMIT** | SELL | 0.1660 | $1,049.3 | `Alo` | - | `submitting` | -0.904 | - |
| `EVT-0480` | 14:39:37 | **RESTING** | SELL | 0.1660 | $1,049.3 | `Alo` | `590773631533` | `ok` | -0.904 | - |
| `EVT-0481` | 14:39:42 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590773631533` | `ok` | +0.000 | - |
| `EVT-0482` | 14:39:46 | **SUBMIT** | SELL | 0.1660 | $1,048.8 | `Alo` | - | `submitting` | -0.839 | - |
| `EVT-0483` | 14:39:47 | **RESTING** | SELL | 0.1660 | $1,048.8 | `Alo` | `590773732361` | `ok` | -0.839 | - |
| `EVT-0484` | 14:39:48 | **SUBMIT** | SELL | 0.4770 | $1,048.8 | `Alo` | - | `submitting` | -0.839 | - |
| `EVT-0485` | 14:39:49 | **REJECTED** | SELL | 0.4770 | $1,048.8 | `Alo` | - | `rejected` | -0.839 | Post only order would have immediately matched, bbo was 1048.9@1049.1. asset=110022 |
| `EVT-0486` | 14:39:50 | **SUBMIT** | SELL | 0.4770 | $1,048.8 | `Alo` | - | `submitting` | -0.839 | - |
| `EVT-0487` | 14:39:51 | **REJECTED** | SELL | 0.4770 | $1,048.8 | `Alo` | - | `rejected` | -0.839 | Post only order would have immediately matched, bbo was 1049@1049.2. asset=110022 |
| `EVT-0488` | 14:39:57 | **SUBMIT** | SELL | 0.4770 | $1,049.0 | `Alo` | - | `submitting` | -0.949 | - |
| `EVT-0489` | 14:39:58 | **REJECTED** | SELL | 0.4770 | $1,049.0 | `Alo` | - | `rejected` | -0.949 | Post only order would have immediately matched, bbo was 1049@1049.3. asset=110022 |
| `EVT-0490` | 14:39:59 | **SUBMIT** | SELL | 0.4770 | $1,049.0 | `Alo` | - | `submitting` | -0.949 | - |
| `EVT-0491` | 14:40:00 | **REJECTED** | SELL | 0.4770 | $1,049.0 | `Alo` | - | `rejected` | -0.949 | Post only order would have immediately matched, bbo was 1049@1049.2. asset=110022 |
| `EVT-0492` | 14:40:01 | **SUBMIT** | SELL | 0.4770 | $1,049.0 | `Alo` | - | `submitting` | -0.949 | - |
| `EVT-0493` | 14:40:02 | **RESTING** | SELL | 0.4770 | $1,049.0 | `Alo` | `590773901611` | `ok` | -0.949 | - |
| `EVT-0494` | 14:40:03 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590773901611` | `ok` | +0.000 | - |
| `EVT-0495` | 14:40:08 | **SUBMIT** | SELL | 0.4770 | $1,049.1 | `Alo` | - | `submitting` | -0.768 | - |
| `EVT-0496` | 14:40:08 | **RESTING** | SELL | 0.4770 | $1,049.1 | `Alo` | `590773996430` | `ok` | -0.768 | - |
| `EVT-0497` | 14:40:14 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590773996430` | `ok` | +0.000 | - |
| `EVT-0498` | 14:40:14 | **SUBMIT** | SELL | 0.1660 | $1,048.9 | `Alo` | - | `submitting` | -0.839 | - |
| `EVT-0499` | 14:40:14 | **RESTING** | SELL | 0.1660 | $1,048.9 | `Alo` | `590774059577` | `ok` | -0.839 | - |
| `EVT-0500` | 14:40:19 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590774059577` | `ok` | +0.000 | - |
| `EVT-0501` | 14:40:24 | **SUBMIT** | SELL | 0.4780 | $1,046.2 | `Alo` | - | `submitting` | -0.834 | - |
| `EVT-0502` | 14:40:24 | **REJECTED** | SELL | 0.4780 | $1,046.2 | `Alo` | - | `rejected` | -0.834 | Post only order would have immediately matched, bbo was 1046.2@1046.4. asset=110022 |
| `EVT-0503` | 14:40:26 | **SUBMIT** | SELL | 0.4780 | $1,046.2 | `Alo` | - | `submitting` | -0.834 | - |
| `EVT-0504` | 14:40:27 | **RESTING** | SELL | 0.4780 | $1,046.2 | `Alo` | `590774187538` | `ok` | -0.834 | - |
| `EVT-0505` | 14:40:30 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590774187538` | `ok` | +0.000 | - |
| `EVT-0506` | 14:40:30 | **SUBMIT** | SELL | 0.4780 | $1,046.6 | `Alo` | - | `submitting` | -0.974 | - |
| `EVT-0507` | 14:40:31 | **REJECTED** | SELL | 0.4780 | $1,046.6 | `Alo` | - | `rejected` | -0.974 | Post only order would have immediately matched, bbo was 1047.6@1047.7. asset=110022 |
| `EVT-0508` | 14:40:34 | **SUBMIT** | BUY | 0.4780 | $1,047.6 | `Gtc` | - | `submitting` | -0.993 | - |
| `EVT-0509` | 14:40:36 | **RESTING** | BUY | 0.4780 | $1,047.6 | `Gtc` | `590774297193` | `ok` | -0.993 | - |
| `EVT-0510` | 14:40:36 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590774297193` | `ok` | +0.000 | - |
| `EVT-0511` | 14:40:36 | **SUBMIT** | BUY | 0.4780 | $1,047.6 | `Gtc` | - | `submitting` | -0.993 | - |
| `EVT-0512` | 14:40:37 | **REJECTED** | BUY | 0.4780 | $1,047.6 | `Gtc` | - | `rejected` | -0.993 | Reduce only order would increase position. asset=110022 |
| `EVT-0513` | 14:40:39 | **SUBMIT** | SELL | 0.4770 | $1,047.6 | `Alo` | - | `submitting` | -0.993 | - |
| `EVT-0514` | 14:40:39 | **RESTING** | SELL | 0.4770 | $1,047.6 | `Alo` | `590774343679` | `ok` | -0.993 | - |
| `EVT-0515` | 14:40:40 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590774343679` | `ok` | +0.000 | - |
| `EVT-0516` | 14:40:45 | **SUBMIT** | SELL | 0.4770 | $1,047.2 | `Alo` | - | `submitting` | -0.928 | - |
| `EVT-0517` | 14:40:46 | **REJECTED** | SELL | 0.4770 | $1,047.2 | `Alo` | - | `rejected` | -0.928 | Post only order would have immediately matched, bbo was 1047.7@1047.8. asset=110022 |
| `EVT-0518` | 14:40:47 | **SUBMIT** | SELL | 0.4770 | $1,047.2 | `Alo` | - | `submitting` | -0.928 | - |
| `EVT-0519` | 14:40:48 | **REJECTED** | SELL | 0.4770 | $1,047.2 | `Alo` | - | `rejected` | -0.928 | Post only order would have immediately matched, bbo was 1048.3@1048.5. asset=110022 |
| `EVT-0520` | 14:40:49 | **SUBMIT** | SELL | 0.4770 | $1,047.2 | `Alo` | - | `submitting` | -0.928 | - |
| `EVT-0521` | 14:40:50 | **REJECTED** | SELL | 0.4770 | $1,047.2 | `Alo` | - | `rejected` | -0.928 | Post only order would have immediately matched, bbo was 1048.3@1048.4. asset=110022 |
| `EVT-0522` | 14:40:51 | **SUBMIT** | BUY | 0.4770 | $1,048.3 | `Alo` | - | `submitting` | +0.947 | - |
| `EVT-0523` | 14:40:52 | **RESTING** | BUY | 0.4770 | $1,048.3 | `Alo` | `590774558422` | `ok` | +0.947 | - |
| `EVT-0524` | 14:40:57 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `590774558422` | `ok` | +0.000 | - |
| `EVT-0525` | 14:40:57 | **SUBMIT** | BUY | 0.1600 | $1,049.6 | `Alo` | - | `submitting` | +0.978 | - |
| `EVT-0526` | 14:40:57 | **REJECTED** | BUY | 0.1600 | $1,049.6 | `Alo` | - | `rejected` | +0.978 | Post only order would have immediately matched, bbo was 1049.3@1049.4. asset=110022 |
| `EVT-0527` | 14:40:59 | **SUBMIT** | BUY | 0.4760 | $1,049.6 | `Alo` | - | `submitting` | +0.978 | - |
| `EVT-0528` | 14:40:59 | **REJECTED** | BUY | 0.4760 | $1,049.6 | `Alo` | - | `rejected` | +0.978 | Post only order would have immediately matched, bbo was 1049.4@1049.5. asset=110022 |
| `EVT-0529` | 14:41:01 | **SUBMIT** | BUY | 0.4760 | $1,049.6 | `Alo` | - | `submitting` | +0.978 | - |
| `EVT-0530` | 14:41:02 | **REJECTED** | BUY | 0.4760 | $1,049.6 | `Alo` | - | `rejected` | +0.978 | Post only order would have immediately matched, bbo was 1049.2@1049.3. asset=110022 |

