# Hyperliquid L2 Alpha Edge & Performance Report (BTC - Mainnet)

- **Network**: Hyperliquid Mainnet
- **Asset**: BTC-PERP
- **Timestamp**: 2026-10-13 19:06:11
- **Mid Price**: $81,012.50
- **Book Spread**: $1.00 (0.12 bps)
- **Total Cumulative CVD**: -1437.8137 BTC

## 1. Paper-Trading Performance Summary

| Strategy | Trades | Win Rate | Gross PnL ($) | Net Fees ($) | Net PnL ($) | Profit Factor | Sharpe Ratio | Max Drawdown ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | 24 | 62.5% | $+85.15 | -$72.11 | $+13.04 | 1.14 | 42.29 | $35.52 |
| Convexity_Cascade | 4 | 75.0% | $+7.58 | -$8.61 | $-1.03 | 0.83 | -131.30 | $7.59 |
| Momentum_Expansion | 5 | 100.0% | $+20.76 | -$8.58 | $+12.18 | 99.00 | 901.34 | $7.05 |

## 2. Predictive Edge Matrix (Information Coefficient & Directional Hit Rate)

| Signal Factor | 1s IC | 1s Hit% | 3s IC | 3s Hit% | 5s IC | 5s Hit% | 10s IC | 10s Hit% | 30s IC | 30s Hit% | 60s IC | 60s Hit% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | +0.056 | 11.8% | +0.083 | 30.8% | +0.087 | 48.7% | +0.025 | 52.5% | -0.080 | 50.9% | -0.079 | 56.1% |
| Convexity_Cascade | +0.046 | 12.6% | +0.078 | 32.8% | +0.100 | 52.0% | +0.066 | 55.9% | -0.014 | 53.6% | +0.022 | 57.6% |
| Momentum_Expansion | +0.048 | 12.6% | +0.077 | 32.7% | +0.102 | 52.2% | +0.074 | 56.2% | -0.011 | 55.1% | +0.019 | 59.2% |

## 3. Position Trade Log (Executed Positions)

| Exit Time | Strategy | Side & Size | Exit Price | Exec Type | Exit Reason | Net PnL ($) | Return (bps) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| 16:31:51 | Convexity_Cascade | LONG 0.05 BTC | $81,326.4 | TAKER | STOP_LOSS | $-6.17 | -15.2 bps |
| 16:31:51 | Momentum_Expansion | LONG 0.10 BTC | $81,385.2 | MAKER | TRAILING_STOP | $+1.78 | +2.2 bps |
| 16:32:35 | Hedged_Convexity | SHORT 0.10 BTC | $81,373.6 | TAKER | STOP_LOSS | $-14.74 | -18.1 bps |
| 16:35:06 | Hedged_Convexity | SHORT 0.10 BTC | $81,179.7 | MAKER | TRAILING_STOP | $+7.69 | +9.5 bps |
| 16:35:50 | Hedged_Convexity | SHORT 0.10 BTC | $81,061.0 | MAKER | TAKE_PROFIT | $+12.57 | +15.5 bps |
| 16:36:30 | Hedged_Convexity | SHORT 0.10 BTC | $81,167.6 | TAKER | STOP_LOSS | $-17.13 | -21.1 bps |
| 16:40:13 | Hedged_Convexity | LONG 0.10 BTC | $81,261.2 | MAKER | TRAILING_STOP | $+3.49 | +4.3 bps |
| 16:40:50 | Hedged_Convexity | LONG 0.10 BTC | $81,152.4 | TAKER | STOP_LOSS | $-13.43 | -16.5 bps |
| 16:45:30 | Hedged_Convexity | LONG 0.10 BTC | $81,309.2 | MAKER | TRAILING_STOP | $+7.79 | +9.6 bps |
| 16:48:24 | Momentum_Expansion | LONG 0.10 BTC | $81,315.2 | MAKER | TRAILING_STOP | $+6.99 | +8.6 bps |
| 16:50:21 | Hedged_Convexity | LONG 0.10 BTC | $81,417.7 | MAKER | TRAILING_STOP | $+3.03 | +3.7 bps |
| 16:54:24 | Hedged_Convexity | SHORT 0.10 BTC | $81,171.7 | MAKER | TRAILING_STOP | $+7.49 | +9.2 bps |
| 16:56:17 | Hedged_Convexity | SHORT 0.10 BTC | $81,059.7 | MAKER | TRAILING_STOP | $+7.90 | +9.7 bps |
| 16:56:38 | Hedged_Convexity | SHORT 0.10 BTC | $81,062.7 | MAKER | TRAILING_STOP | $+2.40 | +3.0 bps |
| 16:58:14 | Hedged_Convexity | SHORT 0.10 BTC | $81,041.0 | MAKER | DEFENSIVE_MAKER_HEDGE | $-6.63 | -8.2 bps |
| 16:59:57 | Hedged_Convexity | LONG 0.10 BTC | $81,010.9 | TAKER | SESSION_SHUTDOWN | $-6.57 | -8.1 bps |
