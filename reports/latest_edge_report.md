# Hyperliquid L2 Alpha Edge & Performance Report (xyz:SKHX - Mainnet)

- **Network**: Hyperliquid Mainnet
- **Asset**: xyz:SKHX-PERP
- **Timestamp**: 2026-10-30 14:41:04
- **Mid Price**: $1,049.45
- **Book Spread**: $0.10 (0.95 bps)
- **Total Cumulative CVD**: -1347.4180 XYZ:SKHX

## 1. Paper-Trading Performance Summary

| Strategy | Trades | Win Rate | Gross PnL ($) | Net Fees ($) | Net PnL ($) | Profit Factor | Sharpe Ratio | Max Drawdown ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| MicroPrice_Maker | 35 | 77.1% | $+4.03 | -$1.03 | $+3.00 | 1.66 | 127.91 | $9500.00 |

## 2. Predictive Edge Matrix (Information Coefficient & Directional Hit Rate)

| Signal Factor | 1s IC | 1s Hit% | 3s IC | 3s Hit% | 5s IC | 5s Hit% | 10s IC | 10s Hit% | 30s IC | 30s Hit% | 60s IC | 60s Hit% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| MicroPrice_Maker | +0.063 | 12.9% | +0.089 | 34.8% | +0.091 | 48.6% | +0.102 | 52.3% | +0.071 | 52.0% | +0.054 | 49.0% |

## 3. Position Trade Log (Executed Positions)

| Exit Time | Strategy | Side & Size | Exit Price | Exec Type | Exit Reason | Net PnL ($) | Return (bps) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| 14:29:45 | MicroPrice_Maker | SHORT 0.41 BTC | $1,043.8 | TAKER | STOP_LOSS | $-0.67 | -15.8 bps |
| 14:31:00 | MicroPrice_Maker | SHORT 0.41 BTC | $1,043.4 | MAKER | SIGNAL_REVERSAL | $+0.18 | +4.2 bps |
| 14:32:15 | MicroPrice_Maker | LONG 0.41 BTC | $1,042.5 | TAKER | STOP_LOSS | $-0.63 | -14.8 bps |
| 14:33:26 | MicroPrice_Maker | SHORT 0.41 BTC | $1,043.1 | MAKER | SIGNAL_REVERSAL | $-0.52 | -12.1 bps |
| 14:35:39 | MicroPrice_Maker | LONG 0.41 BTC | $1,045.2 | MAKER | SIGNAL_REVERSAL | $+0.06 | +1.3 bps |
| 14:36:06 | MicroPrice_Maker | SHORT 0.41 BTC | $1,045.0 | MAKER | TRAILING_STOP | $+0.07 | +1.7 bps |
| 14:37:11 | MicroPrice_Maker | SHORT 0.41 BTC | $1,043.2 | MAKER | TRAILING_STOP | $+0.36 | +8.5 bps |
| 14:37:43 | MicroPrice_Maker | LONG 0.41 BTC | $1,045.2 | MAKER | SIGNAL_REVERSAL | $+0.71 | +16.7 bps |
| 14:38:15 | MicroPrice_Maker | LONG 0.41 BTC | $1,046.6 | MAKER | SIGNAL_REVERSAL | $+0.26 | +6.1 bps |
| 14:38:32 | MicroPrice_Maker | LONG 0.41 BTC | $1,047.4 | MAKER | TRAILING_STOP | $+0.57 | +13.2 bps |
| 14:38:37 | MicroPrice_Maker | LONG 0.41 BTC | $1,047.8 | MAKER | SIGNAL_REVERSAL | $+0.22 | +5.1 bps |
| 14:38:58 | MicroPrice_Maker | SHORT 0.41 BTC | $1,048.6 | MAKER | SIGNAL_REVERSAL | $-0.35 | -8.2 bps |
| 14:40:08 | MicroPrice_Maker | SHORT 0.41 BTC | $1,048.8 | MAKER | TRAILING_STOP | $+0.05 | +1.3 bps |
| 14:40:18 | MicroPrice_Maker | SHORT 0.41 BTC | $1,046.9 | MAKER | TAKE_PROFIT | $+0.79 | +18.5 bps |
| 14:40:34 | MicroPrice_Maker | SHORT 0.41 BTC | $1,047.6 | TAKER | STOP_LOSS | $-0.63 | -14.8 bps |
