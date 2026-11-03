# Hyperliquid L2 Alpha Edge & Performance Report (HYPE - Mainnet)

- **Network**: Hyperliquid Mainnet
- **Asset**: HYPE-PERP
- **Timestamp**: 2026-11-03 16:35:52
- **Mid Price**: $84.05
- **Book Spread**: $0.00 (0.12 bps)
- **Total Cumulative CVD**: -6549.8200 HYPE

## 1. Paper-Trading Performance Summary

| Strategy | Trades | Win Rate | Gross PnL ($) | Net Fees ($) | Net PnL ($) | Profit Factor | Sharpe Ratio | Max Drawdown ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| MicroPrice_FastFill | 23 | 43.5% | $+25.03 | -$61.20 | $-36.17 | 0.65 | -111.52 | $35.69 |

## 2. Predictive Edge Matrix (Information Coefficient & Directional Hit Rate)

| Signal Factor | 1s IC | 1s Hit% | 3s IC | 3s Hit% | 5s IC | 5s Hit% | 10s IC | 10s Hit% | 30s IC | 30s Hit% | 60s IC | 60s Hit% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| MicroPrice_FastFill | +0.089 | 12.3% | +0.113 | 31.8% | +0.155 | 53.0% | +0.158 | 58.9% | +0.134 | 53.7% | +0.058 | 53.7% |

## 3. Position Trade Log (Executed Positions)

| Exit Time | Strategy | Side & Size | Exit Price | Exec Type | Exit Reason | Net PnL ($) | Return (bps) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| 17:25:17 | MicroPrice_FastFill | LONG 101.29 BTC | $83.9 | MAKER | PROFIT_DECAY_EXIT | $-2.35 | -2.8 bps |
| 17:26:33 | MicroPrice_FastFill | SHORT 101.34 BTC | $83.7 | MAKER | TAKE_PROFIT | $+15.19 | +17.9 bps |
| 17:27:48 | MicroPrice_FastFill | LONG 101.57 BTC | $83.6 | MAKER | DEFENSIVE_MAKER_HEDGE | $-8.54 | -10.0 bps |
| 17:28:53 | MicroPrice_FastFill | LONG 101.23 BTC | $83.9 | MAKER | DEFENSIVE_MAKER_HEDGE | $-11.05 | -13.0 bps |
| 17:31:23 | MicroPrice_FastFill | LONG 101.24 BTC | $84.0 | MAKER | TRAILING_STOP | $+1.82 | +2.1 bps |
| 17:31:56 | MicroPrice_FastFill | LONG 101.23 BTC | $84.0 | MAKER | PROFIT_DECAY_EXIT | $-1.94 | -2.3 bps |
| 17:34:31 | MicroPrice_FastFill | LONG 101.20 BTC | $84.1 | MAKER | TRAILING_STOP | $+7.03 | +8.3 bps |
| 17:36:40 | MicroPrice_FastFill | LONG 101.11 BTC | $84.0 | MAKER | PROFIT_DECAY_EXIT | $-5.58 | -6.6 bps |
| 17:38:22 | MicroPrice_FastFill | SHORT 101.35 BTC | $83.9 | MAKER | DEFENSIVE_MAKER_HEDGE | $-10.15 | -11.9 bps |
| 17:41:09 | MicroPrice_FastFill | LONG 101.19 BTC | $84.1 | MAKER | TRAILING_STOP | $+5.71 | +6.7 bps |
| 17:42:25 | MicroPrice_FastFill | LONG 101.06 BTC | $84.2 | MAKER | TRAILING_STOP | $+3.07 | +3.6 bps |
| 17:43:13 | MicroPrice_FastFill | LONG 101.24 BTC | $84.1 | MAKER | TAKE_PROFIT | $+13.75 | +16.2 bps |
| 17:45:11 | MicroPrice_FastFill | LONG 101.10 BTC | $84.0 | MAKER | DEFENSIVE_MAKER_HEDGE | $-8.82 | -10.4 bps |
| 17:47:20 | MicroPrice_FastFill | SHORT 101.34 BTC | $84.0 | MAKER | DEFENSIVE_MAKER_HEDGE | $-12.08 | -14.2 bps |
| 17:50:17 | MicroPrice_FastFill | LONG 101.15 BTC | $84.0 | TAKER | SESSION_SHUTDOWN | $-3.60 | -4.2 bps |
