# Hyperliquid L2 Alpha Edge & Performance Report (HYPE - Mainnet)

- **Network**: Hyperliquid Mainnet
- **Asset**: HYPE-PERP
- **Timestamp**: 2026-10-12 23:36:55
- **Mid Price**: $83.11
- **Book Spread**: $0.00 (0.12 bps)
- **Total Cumulative CVD**: -68393.9100 HYPE

## 1. Paper-Trading Performance Summary

| Strategy | Trades | Win Rate | Gross PnL ($) | Net Fees ($) | Net PnL ($) | Profit Factor | Sharpe Ratio | Max Drawdown ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | 7 | 71.4% | $+32.04 | -$20.41 | $+11.63 | 1.41 | 24.91 | $24.27 |
| Convexity_Cascade | 12 | 83.3% | $+54.03 | -$25.50 | $+28.53 | 5.50 | 328.90 | $12.27 |
| Momentum_Expansion | 18 | 66.7% | $+74.68 | -$42.06 | $+32.62 | 1.62 | 151.31 | $39.05 |

## 2. Predictive Edge Matrix (Information Coefficient & Directional Hit Rate)

| Signal Factor | 1s IC | 1s Hit% | 3s IC | 3s Hit% | 5s IC | 5s Hit% | 10s IC | 10s Hit% | 30s IC | 30s Hit% | 60s IC | 60s Hit% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | +0.092 | 13.2% | +0.130 | 33.2% | +0.155 | 53.3% | +0.089 | 53.1% | +0.044 | 51.3% | +0.011 | 49.8% |
| Convexity_Cascade | +0.086 | 13.9% | +0.127 | 35.2% | +0.151 | 56.2% | +0.097 | 54.9% | +0.061 | 52.9% | +0.005 | 51.4% |
| Momentum_Expansion | +0.097 | 14.0% | +0.152 | 35.4% | +0.184 | 56.8% | +0.115 | 55.1% | +0.070 | 51.6% | +0.002 | 49.9% |

## 3. Position Trade Log (Executed Positions)

| Exit Time | Strategy | Side & Size | Exit Price | Exec Type | Exit Reason | Net PnL ($) | Return (bps) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| 18:38:39 | Convexity_Cascade | SHORT 102.15 BTC | $83.1 | MAKER | TRAILING_STOP | $+4.38 | +5.2 bps |
| 18:38:39 | Momentum_Expansion | SHORT 51.07 BTC | $83.1 | MAKER | TRAILING_STOP | $+2.19 | +5.2 bps |
| 18:39:06 | Momentum_Expansion | SHORT 102.21 BTC | $83.2 | TAKER | STOP_LOSS | $-12.84 | -15.1 bps |
| 18:40:45 | Momentum_Expansion | LONG 101.90 BTC | $83.4 | MAKER | DEFENSIVE_MAKER_HEDGE | $-6.32 | -7.4 bps |
| 18:43:30 | Momentum_Expansion | SHORT 102.17 BTC | $83.1 | MAKER | TRAILING_STOP | $+5.52 | +6.5 bps |
| 18:43:46 | Convexity_Cascade | SHORT 51.13 BTC | $83.1 | MAKER | TRAILING_STOP | $+1.23 | +2.9 bps |
| 18:43:46 | Momentum_Expansion | SHORT 51.13 BTC | $83.1 | MAKER | TRAILING_STOP | $+1.23 | +2.9 bps |
| 18:47:59 | Momentum_Expansion | SHORT 102.30 BTC | $83.0 | MAKER | TRAILING_STOP | $+2.66 | +3.1 bps |
| 18:48:15 | Convexity_Cascade | SHORT 51.18 BTC | $83.0 | MAKER | TRAILING_STOP | $+0.61 | +1.4 bps |
| 18:48:15 | Momentum_Expansion | SHORT 51.18 BTC | $83.0 | MAKER | TRAILING_STOP | $+0.61 | +1.4 bps |
| 18:50:07 | Convexity_Cascade | SHORT 102.63 BTC | $82.8 | MAKER | TRAILING_STOP | $+0.43 | +0.5 bps |
| 18:50:07 | Momentum_Expansion | SHORT 51.32 BTC | $82.8 | MAKER | TRAILING_STOP | $+0.21 | +0.5 bps |
| 18:52:06 | Momentum_Expansion | LONG 102.53 BTC | $82.9 | MAKER | DEFENSIVE_MAKER_HEDGE | $-7.47 | -8.8 bps |
| 18:59:59 | Convexity_Cascade | LONG 102.29 BTC | $83.1 | TAKER | SESSION_SHUTDOWN | $-3.68 | -4.3 bps |
| 18:59:59 | Momentum_Expansion | LONG 51.15 BTC | $83.1 | TAKER | SESSION_SHUTDOWN | $-1.84 | -4.3 bps |
