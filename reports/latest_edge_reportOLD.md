# Hyperliquid L2 Alpha Edge & Performance Report (BTC)

- **Asset**: BTC-PERP
- **Timestamp**: 2026-09-27 20:55:37
- **Mid Price**: $84,714.50
- **Book Spread**: $1.00 (0.12 bps)
- **Total Cumulative CVD**: -73.1164 BTC

## 1. Paper-Trading Performance Summary

| Strategy | Trades | Win Rate | Net PnL ($) | Profit Factor | Sharpe Ratio | Max Drawdown ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| AdaptiveML_Maker | 209 | 89.0% | $+59.07 | 3.69 | 204.45 | $8.46 |
| Composite_Maker | 104 | 87.5% | $+54.98 | 8.23 | 381.98 | $2.60 |
| WOBI_Maker | 126 | 92.1% | $+75.00 | 15.66 | 472.93 | $2.60 |
| MicroPrice_Maker | 135 | 91.9% | $+82.03 | 14.34 | 464.87 | $2.60 |
| AdaptiveML_Taker | 68 | 58.8% | $+14.08 | 1.72 | 87.05 | $190.55 |
| Composite_Taker | 37 | 59.5% | $+23.78 | 3.09 | 212.62 | $88.92 |
| Absorption_Fade | 110 | 73.6% | $+19.99 | 1.86 | 124.50 | $2.60 |

## 2. Predictive Edge Matrix (Information Coefficient & Directional Hit Rate)

| Signal Factor | 1s IC | 1s Hit% | 3s IC | 3s Hit% | 5s IC | 5s Hit% | 10s IC | 10s Hit% | 30s IC | 30s Hit% | 60s IC | 60s Hit% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| AdaptiveML_Maker | +0.053 | 5.2% | +0.117 | 13.9% | +0.100 | 21.0% | +0.050 | 26.7% | +0.045 | 44.9% | +0.111 | 54.1% |
| Composite_Maker | -0.099 | 4.8% | -0.158 | 13.7% | -0.165 | 22.0% | -0.153 | 33.4% | -0.006 | 58.6% | +0.151 | 67.4% |
| WOBI_Maker | +0.040 | 5.1% | +0.084 | 14.4% | +0.106 | 23.2% | +0.085 | 34.4% | -0.049 | 50.8% | +0.112 | 51.0% |
| MicroPrice_Maker | +0.037 | 5.9% | +0.079 | 17.0% | +0.101 | 27.5% | +0.109 | 38.9% | -0.090 | 50.8% | +0.150 | 64.8% |
| AdaptiveML_Taker | +0.053 | 5.2% | +0.117 | 13.9% | +0.100 | 21.0% | +0.050 | 26.7% | +0.045 | 44.9% | +0.111 | 54.1% |
| Composite_Taker | -0.099 | 4.8% | -0.158 | 13.7% | -0.165 | 22.0% | -0.153 | 33.4% | -0.006 | 58.6% | +0.151 | 67.4% |
| Absorption_Fade | -0.172 | 0.0% | -0.293 | 0.0% | -0.372 | 0.0% | -0.350 | 3.7% | +0.074 | 20.7% | +0.262 | 36.1% |

## 3. Position Trade Log (Executed Positions)

| Exit Time | Strategy | Side & Size | Exit Price | Exec Type | Exit Reason | Net PnL ($) | Return (bps) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| 20:54:44 | Absorption_Fade | LONG 0.10 BTC | $84,716.0 | MAKER | TIME_LIMIT | $+0.27 | +0.3 bps |
| 20:54:48 | AdaptiveML_Maker | LONG 0.10 BTC | $84,716.0 | MAKER | SIGNAL_REVERSAL | $+0.27 | +0.3 bps |
| 20:55:01 | WOBI_Maker | SHORT 0.10 BTC | $84,715.0 | MAKER | TIME_LIMIT | $+0.27 | +0.3 bps |
| 20:55:01 | MicroPrice_Maker | SHORT 0.10 BTC | $84,715.0 | MAKER | TIME_LIMIT | $+0.27 | +0.3 bps |
| 20:55:15 | AdaptiveML_Maker | LONG 0.10 BTC | $84,716.0 | MAKER | TIME_LIMIT | $+0.27 | +0.3 bps |
| 20:55:16 | Absorption_Fade | LONG 0.10 BTC | $84,716.0 | MAKER | TIME_LIMIT | $+0.27 | +0.3 bps |
| 20:55:18 | AdaptiveML_Taker | LONG 0.10 BTC | $84,716.0 | MAKER (TIME) | TIME_LIMIT | $+0.00 | +0.0 bps |
| 20:55:20 | AdaptiveML_Maker | LONG 0.10 BTC | $84,716.0 | MAKER | SIGNAL_REVERSAL | $+0.27 | +0.3 bps |
| 20:55:21 | WOBI_Maker | SHORT 0.10 BTC | $84,715.0 | MAKER | TIME_LIMIT | $+0.27 | +0.3 bps |
| 20:55:21 | MicroPrice_Maker | SHORT 0.10 BTC | $84,715.0 | MAKER | TIME_LIMIT | $+0.27 | +0.3 bps |
| 20:55:26 | Composite_Maker | LONG 0.10 BTC | $84,716.0 | MAKER | SIGNAL_REVERSAL | $+0.27 | +0.3 bps |
| 20:55:26 | Absorption_Fade | LONG 0.10 BTC | $84,716.0 | MAKER | SIGNAL_REVERSAL | $+0.27 | +0.3 bps |
| 20:55:31 | AdaptiveML_Maker | LONG 0.10 BTC | $84,715.0 | MAKER | SIGNAL_REVERSAL | $+0.17 | +0.2 bps |
| 20:55:31 | AdaptiveML_Taker | LONG 0.10 BTC | $84,715.0 | MAKER (SIGN) | SIGNAL_REVERSAL | $-0.10 | -0.1 bps |
