# Trading Session Audit Report: `session_20260929_194956`

- **Session ID**: `session_20260929_194956`
- **Target Asset**: `BTC-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: REAL EXCHANGE ORDERS (LIVE)
- **Session Start**: 2026-09-29T19:49:56
- **Session End**: 2026-09-29 20:09:12
- **Duration**: 19m 16s (1156.3s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Real On-Chain Hyperliquid Execution (Exchange Reconciled)

> [!IMPORTANT]
> The figures below represent **actual on-chain fills and cash settlements** verified directly against the Hyperliquid clearinghouse API for this trading session.

| Metric | Real Value (Exchange Settled) |
| :--- | :---: |
| **Total Real Fills** | 32 (31 Maker / 1 Taker) |
| **Real Executed Volume** | 0.0220 BTC |
| **Real Closed PnL** | $-0.0995 USDC |
| **Real Fees Paid to Hyperliquid** | $0.4766 USDC |
| **Real Net Realized PnL** | **-$0.5761 USDC** |
| **On-Chain Fills CSV** | [`live_exchange_fills.csv`](live_exchange_fills.csv) |

---

## 2. Theoretical Paper-Simulation Benchmark

| Strategy | Trades | Win Rate | Volume (BTC) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Absorption_Fade** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Absorption_Fade.csv`](strategies/Absorption_Fade.csv) |
| **AdaptiveML_Maker** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`AdaptiveML_Maker.csv`](strategies/AdaptiveML_Maker.csv) |
| **AdaptiveML_Taker** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`AdaptiveML_Taker.csv`](strategies/AdaptiveML_Taker.csv) |
| **Composite_Maker** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Composite_Maker.csv`](strategies/Composite_Maker.csv) |
| **Composite_Taker** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Composite_Taker.csv`](strategies/Composite_Taker.csv) |
| **MicroPrice_Maker** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`MicroPrice_Maker.csv`](strategies/MicroPrice_Maker.csv) |
| **WOBI_Maker** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`WOBI_Maker.csv`](strategies/WOBI_Maker.csv) |

---

## 2. Individual Trade Logs per Strategy

### Strategy: `Absorption_Fade`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/Absorption_Fade.csv`](strategies/Absorption_Fade.csv)

_No trades were opened/closed for Absorption_Fade during this session._

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

### Strategy: `MicroPrice_Maker`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/MicroPrice_Maker.csv`](strategies/MicroPrice_Maker.csv)

_No trades were opened/closed for MicroPrice_Maker during this session._

### Strategy: `WOBI_Maker`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/WOBI_Maker.csv`](strategies/WOBI_Maker.csv)

_No trades were opened/closed for WOBI_Maker during this session._

