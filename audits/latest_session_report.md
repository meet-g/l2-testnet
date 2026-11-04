# Trading Session Audit Report: `session_20261104_111844_058_7155`

- **Session ID**: `session_20261104_111844_058_7155`
- **Target Asset**: `BTC-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: PAPER TRADING SIMULATION
- **Session Start**: 2026-11-04T11:18:44
- **Session End**: 2026-11-04 11:18:45
- **Duration**: 0m 1s (1.6s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Executive Strategy Performance Audit

| Strategy | Trades | Win Rate | Volume (BTC) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Absorption_Fade** | 1 | 0.0% | 0.1000 | -$4.72 | **$-4.83** | -6.1 bps | 0.00 | [`Absorption_Fade.csv`](strategies/Absorption_Fade.csv) |
| **AdaptiveML_Maker** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`AdaptiveML_Maker.csv`](strategies/AdaptiveML_Maker.csv) |
| **AdaptiveML_Taker** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`AdaptiveML_Taker.csv`](strategies/AdaptiveML_Taker.csv) |
| **Composite_Maker** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Composite_Maker.csv`](strategies/Composite_Maker.csv) |
| **Composite_Taker** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Composite_Taker.csv`](strategies/Composite_Taker.csv) |
| **Instant_FastFill** | 1 | 0.0% | 0.1000 | -$7.08 | **$-7.44** | -9.5 bps | 0.00 | [`Instant_FastFill.csv`](strategies/Instant_FastFill.csv) |
| **MicroPrice_FastFill** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`MicroPrice_FastFill.csv`](strategies/MicroPrice_FastFill.csv) |
| **MicroPrice_Maker** | 1 | 0.0% | 0.1000 | -$4.72 | **$-4.83** | -6.1 bps | 0.00 | [`MicroPrice_Maker.csv`](strategies/MicroPrice_Maker.csv) |
| **QDAP_Maker** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`QDAP_Maker.csv`](strategies/QDAP_Maker.csv) |
| **WOBI_Maker** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`WOBI_Maker.csv`](strategies/WOBI_Maker.csv) |

---

## 2. Individual Trade Logs per Strategy

### Strategy: `Absorption_Fade`

- **Total Executed Trades**: 1 | **Wins**: 0 | **Losses**: 1 | **Win Rate**: 0.0% | **Net PnL**: $-4.83
- **Audit CSV**: [`strategies/Absorption_Fade.csv`](strategies/Absorption_Fade.csv)

| # | Trade ID | Side | Size (BTC) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `AF-0002` | SHORT | 0.1000 | 11:18:44 | $78,631.0 | 11:18:45 | $78,632.1 | 0.8s | `SESSION_SHUTDOWN` | -$4.72 | **-$4.83** | -6.1 bps |

### Strategy: `AdaptiveML_Maker`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/AdaptiveML_Maker.csv`](strategies/AdaptiveML_Maker.csv)

_No trades were opened/closed for AdaptiveML_Maker during this session._

### Strategy: `AdaptiveML_Taker`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/AdaptiveML_Taker.csv`](strategies/AdaptiveML_Taker.csv)

_No trades were opened/closed for AdaptiveML_Taker during this session._

### Strategy: `Composite_Maker`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/Composite_Maker.csv`](strategies/Composite_Maker.csv)

_No trades were opened/closed for Composite_Maker during this session._

### Strategy: `Composite_Taker`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/Composite_Taker.csv`](strategies/Composite_Taker.csv)

_No trades were opened/closed for Composite_Taker during this session._

### Strategy: `Instant_FastFill`

- **Total Executed Trades**: 1 | **Wins**: 0 | **Losses**: 1 | **Win Rate**: 0.0% | **Net PnL**: $-7.44
- **Audit CSV**: [`strategies/Instant_FastFill.csv`](strategies/Instant_FastFill.csv)

| # | Trade ID | Side | Size (BTC) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `IFF-0003` | LONG | 0.1000 | 11:18:44 | $78,632.6 | 11:18:45 | $78,628.9 | 0.8s | `SESSION_SHUTDOWN` | -$7.08 | **-$7.44** | -9.5 bps |

### Strategy: `MicroPrice_FastFill`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/MicroPrice_FastFill.csv`](strategies/MicroPrice_FastFill.csv)

_No trades were opened/closed for MicroPrice_FastFill during this session._

### Strategy: `MicroPrice_Maker`

- **Total Executed Trades**: 1 | **Wins**: 0 | **Losses**: 1 | **Win Rate**: 0.0% | **Net PnL**: $-4.83
- **Audit CSV**: [`strategies/MicroPrice_Maker.csv`](strategies/MicroPrice_Maker.csv)

| # | Trade ID | Side | Size (BTC) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `MPM-0001` | LONG | 0.1000 | 11:18:44 | $78,630.0 | 11:18:45 | $78,628.9 | 0.8s | `SESSION_SHUTDOWN` | -$4.72 | **-$4.83** | -6.1 bps |

### Strategy: `QDAP_Maker`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/QDAP_Maker.csv`](strategies/QDAP_Maker.csv)

_No trades were opened/closed for QDAP_Maker during this session._

### Strategy: `WOBI_Maker`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/WOBI_Maker.csv`](strategies/WOBI_Maker.csv)

_No trades were opened/closed for WOBI_Maker during this session._

