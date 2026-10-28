# Trading Session Audit Report: `session_20261027_225931_094_e70d`

- **Session ID**: `session_20261027_225931_094_e70d`
- **Target Asset**: `HYPE-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: PAPER TRADING SIMULATION
- **Session Start**: 2026-10-27T22:59:31
- **Session End**: 2026-10-28 00:58:29
- **Duration**: 118m 58s (7138.8s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Executive Strategy Performance Audit

| Strategy | Trades | Win Rate | Volume (HYPE) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Convexity_Cascade** | 2 | 0.0% | 209.0600 | -$5.10 | **$-12.73** | -7.5 bps | 0.00 | [`Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv) |
| **Hedged_Convexity** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv) |
| **Momentum_Expansion** | 3 | 33.3% | 261.5100 | -$6.38 | **$-7.55** | -4.2 bps | 0.13 | [`Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv) |

---

## 2. Individual Trade Logs per Strategy

### Strategy: `Convexity_Cascade`

- **Total Executed Trades**: 2 | **Wins**: 0 | **Losses**: 2 | **Win Rate**: 0.0% | **Net PnL**: $-12.73
- **Audit CSV**: [`strategies/Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `CC-0003` | SHORT | 104.6000 | 23:47:29 | $81.3 | 23:48:55 | $81.3 | 85.4s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.21** | -7.3 bps |
| 2 | `CC-0005` | LONG | 104.4600 | 00:39:06 | $81.4 | 00:39:43 | $81.3 | 36.2s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$6.52** | -7.7 bps |

### Strategy: `Hedged_Convexity`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv)

_No trades were opened/closed for Hedged_Convexity during this session._

### Strategy: `Momentum_Expansion`

- **Total Executed Trades**: 3 | **Wins**: 1 | **Losses**: 2 | **Win Rate**: 33.3% | **Net PnL**: $-7.55
- **Audit CSV**: [`strategies/Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv)

| # | Trade ID | Side | Size (HYPE) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `ME-0001` | SHORT | 104.5900 | 23:43:37 | $81.3 | 23:43:43 | $81.3 | 5.5s | `DEFENSIVE_MAKER_HEDGE` | -$2.55 | **-$5.58** | -6.6 bps |
| 2 | `ME-0002` | SHORT | 52.3000 | 23:47:29 | $81.3 | 23:48:50 | $81.3 | 80.4s | `DEFENSIVE_MAKER_HEDGE` | -$1.28 | **-$3.11** | -7.3 bps |
| 3 | `ME-0004` | SHORT | 104.6200 | 23:57:22 | $81.2 | 23:58:47 | $81.2 | 84.7s | `TRAILING_STOP` | -$2.55 | **+$1.14** | +1.3 bps |

