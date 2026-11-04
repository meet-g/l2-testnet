# Hyperliquid L2 Alpha Edge & Performance Report (BTC - Mainnet)

- **Network**: Hyperliquid Mainnet
- **Asset**: BTC-PERP
- **Timestamp**: 2026-11-04 11:18:45
- **Mid Price**: $78,630.50
- **Book Spread**: $1.00 (0.13 bps)
- **Total Cumulative CVD**: +3.9184 BTC

## 1. Paper-Trading Performance Summary

| Strategy | Trades | Win Rate | Gross PnL ($) | Net Fees ($) | Net PnL ($) | Profit Factor | Sharpe Ratio | Max Drawdown ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| QDAP_Maker | 0 | 0.0% | $+0.00 | +$0.00 | $+0.00 | 0.00 | 0.00 | $0.00 |
| Composite_Maker | 0 | 0.0% | $+0.00 | +$0.00 | $+0.00 | 0.00 | 0.00 | $0.00 |
| AdaptiveML_Maker | 0 | 0.0% | $+0.00 | +$0.00 | $+0.00 | 0.00 | 0.00 | $0.00 |
| WOBI_Maker | 0 | 0.0% | $+0.00 | +$0.00 | $+0.00 | 0.00 | 0.00 | $0.00 |
| MicroPrice_Maker | 1 | 0.0% | $-0.11 | -$4.72 | $-4.83 | 0.00 | -3696.51 | $1.13 |
| MicroPrice_FastFill | 0 | 0.0% | $+0.00 | +$0.00 | $+0.00 | 0.00 | 0.00 | $0.00 |
| Absorption_Fade | 1 | 0.0% | $-0.11 | -$4.72 | $-4.83 | 0.00 | -3696.58 | $1.13 |
| AdaptiveML_Taker | 0 | 0.0% | $+0.00 | +$0.00 | $+0.00 | 0.00 | 0.00 | $0.00 |
| Composite_Taker | 0 | 0.0% | $+0.00 | +$0.00 | $+0.00 | 0.00 | 0.00 | $0.00 |
| Instant_FastFill | 1 | 0.0% | $-0.36 | -$7.08 | $-7.44 | 0.00 | -5700.69 | $3.75 |

## 2. Predictive Edge Matrix (Information Coefficient & Directional Hit Rate)

| Signal Factor | 1s IC | 1s Hit% | 3s IC | 3s Hit% | 5s IC | 5s Hit% | 10s IC | 10s Hit% | 30s IC | 30s Hit% | 60s IC | 60s Hit% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| QDAP_Maker | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% |
| Composite_Maker | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% |
| AdaptiveML_Maker | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% |
| WOBI_Maker | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% |
| MicroPrice_Maker | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% |
| MicroPrice_FastFill | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% |
| Absorption_Fade | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% |
| AdaptiveML_Taker | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% |
| Composite_Taker | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% |
| Instant_FastFill | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% | +0.000 | 50.0% |

## 3. Position Trade Log (Executed Positions)

| Exit Time | Strategy | Side & Size | Exit Price | Exec Type | Exit Reason | Net PnL ($) | Return (bps) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| 11:18:45 | MicroPrice_Maker | LONG 0.10 BTC | $78,628.9 | TAKER | SESSION_SHUTDOWN | $-4.83 | -6.1 bps |
| 11:18:45 | Absorption_Fade | SHORT 0.10 BTC | $78,632.1 | TAKER | SESSION_SHUTDOWN | $-4.83 | -6.1 bps |
| 11:18:45 | Instant_FastFill | LONG 0.10 BTC | $78,628.9 | TAKER | SESSION_SHUTDOWN | $-7.44 | -9.5 bps |
