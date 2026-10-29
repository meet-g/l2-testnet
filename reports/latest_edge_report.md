# Hyperliquid L2 Alpha Edge & Performance Report (HYPE - Mainnet)

- **Network**: Hyperliquid Mainnet
- **Asset**: HYPE-PERP
- **Timestamp**: 2026-10-29 11:28:45
- **Mid Price**: $86.41
- **Book Spread**: $0.00 (0.12 bps)
- **Total Cumulative CVD**: +443004.9400 HYPE

## 1. Paper-Trading Performance Summary

| Strategy | Trades | Win Rate | Gross PnL ($) | Net Fees ($) | Net PnL ($) | Profit Factor | Sharpe Ratio | Max Drawdown ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | 16 | 75.0% | $+145.81 | -$43.36 | $+102.45 | 3.12 | 284.78 | $41.71 |
| Convexity_Cascade | 16 | 56.2% | $+73.05 | -$40.80 | $+32.25 | 1.73 | 134.97 | $20.83 |
| Momentum_Expansion | 28 | 46.4% | $+7.92 | -$67.58 | $-59.65 | 0.52 | -124.55 | $86.65 |

## 2. Predictive Edge Matrix (Information Coefficient & Directional Hit Rate)

| Signal Factor | 1s IC | 1s Hit% | 3s IC | 3s Hit% | 5s IC | 5s Hit% | 10s IC | 10s Hit% | 30s IC | 30s Hit% | 60s IC | 60s Hit% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | +0.061 | 10.7% | +0.099 | 30.7% | +0.114 | 50.5% | +0.092 | 54.2% | +0.035 | 52.1% | -0.003 | 100.0% |
| Convexity_Cascade | +0.020 | 10.2% | +0.042 | 29.5% | +0.054 | 48.6% | +0.048 | 51.9% | +0.027 | 53.1% | +0.007 | 100.0% |
| Momentum_Expansion | -0.001 | 10.2% | -0.002 | 29.3% | +0.013 | 49.4% | +0.030 | 52.3% | -0.012 | 55.0% | -0.028 | 100.0% |

## 3. Position Trade Log (Executed Positions)

| Exit Time | Strategy | Side & Size | Exit Price | Exec Type | Exit Reason | Net PnL ($) | Return (bps) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| 10:34:36 | Hedged_Convexity | LONG 103.38 BTC | $82.4 | MAKER | TRAILING_STOP | $+11.30 | +13.3 bps |
| 10:36:07 | Momentum_Expansion | SHORT 104.13 BTC | $81.9 | MAKER | DEFENSIVE_MAKER_HEDGE | $-32.44 | -38.2 bps |
| 10:37:34 | Convexity_Cascade | LONG 103.72 BTC | $82.2 | MAKER | TAKE_PROFIT | $+20.27 | +23.8 bps |
| 10:37:34 | Momentum_Expansion | LONG 51.86 BTC | $82.2 | MAKER | TAKE_PROFIT | $+10.13 | +23.8 bps |
| 10:48:58 | Hedged_Convexity | LONG 99.75 BTC | $85.4 | MAKER | TAKE_PROFIT | $+17.10 | +20.1 bps |
| 10:52:32 | Hedged_Convexity | LONG 98.54 BTC | $86.0 | TAKER | STOP_LOSS | $-25.66 | -30.2 bps |
| 10:59:20 | Momentum_Expansion | LONG 99.96 BTC | $84.9 | TAKER | STOP_LOSS | $-18.36 | -21.6 bps |
| 11:02:45 | Hedged_Convexity | LONG 98.96 BTC | $86.1 | MAKER | TAKE_PROFIT | $+16.74 | +19.7 bps |
| 11:02:56 | Hedged_Convexity | LONG 98.72 BTC | $86.1 | MAKER | DEFENSIVE_MAKER_HEDGE | $-6.60 | -7.8 bps |
| 11:09:39 | Hedged_Convexity | LONG 98.39 BTC | $86.5 | MAKER | TRAILING_STOP | $+5.04 | +5.9 bps |
| 11:12:26 | Hedged_Convexity | LONG 98.38 BTC | $86.5 | MAKER | TRAILING_STOP | $+7.60 | +8.9 bps |
| 11:15:23 | Hedged_Convexity | LONG 97.78 BTC | $87.0 | MAKER | TRAILING_STOP | $+7.62 | +9.0 bps |
| 11:17:21 | Momentum_Expansion | SHORT 97.67 BTC | $86.9 | MAKER | TRAILING_STOP | $+9.18 | +10.8 bps |
| 11:21:17 | Momentum_Expansion | LONG 97.83 BTC | $86.9 | MAKER | TRAILING_STOP | $+3.62 | +4.3 bps |
| 11:28:28 | Hedged_Convexity | LONG 98.14 BTC | $86.6 | MAKER | DEFENSIVE_MAKER_HEDGE | $-7.55 | -8.9 bps |
