# Hyperliquid L2 Alpha Edge & Performance Report (BTC)

- **Asset**: BTC-PERP
- **Timestamp**: 2026-09-28 02:53:05
- **Mid Price**: $83,721.50
- **Book Spread**: $1.00 (0.12 bps)
- **Total Cumulative CVD**: -526.7092 BTC

## 1. Paper-Trading Performance Summary

| Strategy | Trades | Win Rate | Net PnL ($) | Profit Factor | Sharpe Ratio | Max Drawdown ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| AdaptiveML_Maker | 1165 | 81.7% | $+77.25 | 3.10 | 217.88 | $9000.25 |
| Composite_Maker | 733 | 80.1% | $+82.75 | 4.65 | 326.48 | $9000.09 |
| WOBI_Maker | 850 | 81.4% | $+97.74 | 4.60 | 319.21 | $9000.09 |
| MicroPrice_Maker | 932 | 81.4% | $+105.96 | 4.95 | 332.04 | $9000.04 |
| AdaptiveML_Taker | 339 | 18.0% | $-75.93 | 0.18 | -377.57 | $9076.62 |
| Composite_Taker | 280 | 26.4% | $-44.15 | 0.35 | -258.47 | $9044.44 |
| Absorption_Fade | 660 | 67.3% | $+42.93 | 2.05 | 158.67 | $9000.16 |

## 2. Predictive Edge Matrix (Information Coefficient & Directional Hit Rate)

| Signal Factor | 1s IC | 1s Hit% | 3s IC | 3s Hit% | 5s IC | 5s Hit% | 10s IC | 10s Hit% | 30s IC | 30s Hit% | 60s IC | 60s Hit% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| AdaptiveML_Maker | +0.021 | 6.7% | +0.089 | 18.7% | +0.165 | 30.5% | +0.124 | 40.4% | +0.051 | 43.9% | +0.048 | 46.7% |
| Composite_Maker | +0.058 | 8.6% | +0.121 | 25.1% | +0.222 | 41.6% | +0.220 | 56.7% | +0.020 | 56.7% | +0.098 | 72.1% |
| WOBI_Maker | +0.096 | 8.2% | +0.171 | 23.2% | +0.218 | 38.1% | +0.212 | 54.0% | +0.171 | 59.5% | +0.221 | 68.7% |
| MicroPrice_Maker | +0.091 | 8.3% | +0.162 | 23.7% | +0.207 | 38.9% | +0.190 | 53.3% | +0.125 | 60.7% | +0.186 | 68.0% |
| AdaptiveML_Taker | +0.021 | 6.7% | +0.089 | 18.7% | +0.165 | 30.5% | +0.124 | 40.4% | +0.051 | 43.9% | +0.048 | 46.7% |
| Composite_Taker | +0.058 | 8.6% | +0.121 | 25.1% | +0.222 | 41.6% | +0.220 | 56.7% | +0.020 | 56.7% | +0.098 | 72.1% |
| Absorption_Fade | +0.002 | 6.1% | +0.046 | 19.9% | +0.097 | 30.9% | +0.180 | 42.3% | -0.040 | 33.8% | +0.127 | 38.4% |

## 3. Position Trade Log (Executed Positions)

| Exit Time | Strategy | Side & Size | Exit Price | Exec Type | Exit Reason | Net PnL ($) | Return (bps) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| 02:52:36 | Composite_Maker | LONG 0.01 BTC | $83,737.0 | MAKER | SIGNAL_REVERSAL | $-0.20 | -2.3 bps |
| 02:52:37 | WOBI_Maker | LONG 0.01 BTC | $83,737.0 | MAKER | TIME_LIMIT | $-0.20 | -2.3 bps |
| 02:52:38 | Absorption_Fade | LONG 0.01 BTC | $83,737.0 | MAKER | SIGNAL_REVERSAL | $-0.27 | -3.2 bps |
| 02:52:39 | AdaptiveML_Maker | SHORT 0.01 BTC | $83,708.0 | MAKER | TAKE_PROFIT | $+0.32 | +3.9 bps |
| 02:52:39 | Composite_Taker | LONG 0.01 BTC | $83,709.0 | MAKER (SIGN) | SIGNAL_REVERSAL | $-0.81 | -9.7 bps |
| 02:52:39 | Absorption_Fade | SHORT 0.01 BTC | $83,708.0 | MAKER | TAKE_PROFIT | $+0.32 | +3.9 bps |
| 02:52:54 | AdaptiveML_Maker | LONG 0.01 BTC | $83,697.0 | MAKER | SIGNAL_REVERSAL | $+0.06 | +0.8 bps |
| 02:52:54 | MicroPrice_Maker | LONG 0.01 BTC | $83,697.0 | MAKER | TIME_LIMIT | $-0.36 | -4.3 bps |
| 02:52:55 | Composite_Maker | SHORT 0.01 BTC | $83,704.0 | MAKER | TRAILING_STOP | $+0.08 | +1.0 bps |
| 02:52:55 | Absorption_Fade | SHORT 0.01 BTC | $83,704.0 | MAKER | TRAILING_STOP | $+0.08 | +1.0 bps |
| 02:53:01 | AdaptiveML_Maker | LONG 0.01 BTC | $83,722.0 | MAKER | TAKE_PROFIT | $+0.21 | +2.6 bps |
| 02:53:01 | Composite_Maker | SHORT 0.01 BTC | $83,721.0 | MAKER | SIGNAL_REVERSAL | $-0.13 | -1.5 bps |
| 02:53:01 | MicroPrice_Maker | SHORT 0.01 BTC | $83,721.0 | MAKER | SIGNAL_REVERSAL | $-0.13 | -1.5 bps |
| 02:53:01 | Absorption_Fade | SHORT 0.01 BTC | $83,721.0 | MAKER | SIGNAL_REVERSAL | $-0.13 | -1.5 bps |
