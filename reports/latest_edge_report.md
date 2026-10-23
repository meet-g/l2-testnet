# Hyperliquid L2 Alpha Edge & Performance Report (HYPE - Mainnet)

- **Network**: Hyperliquid Mainnet
- **Asset**: HYPE-PERP
- **Timestamp**: 2026-10-23 16:31:21
- **Mid Price**: $78.39
- **Book Spread**: $0.00 (0.13 bps)
- **Total Cumulative CVD**: -485.0300 HYPE

## 1. Paper-Trading Performance Summary

| Strategy | Trades | Win Rate | Gross PnL ($) | Net Fees ($) | Net PnL ($) | Profit Factor | Sharpe Ratio | Max Drawdown ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | 14 | 71.4% | $+67.90 | -$40.80 | $+27.10 | 1.62 | 126.53 | $24.12 |
| Convexity_Cascade | 27 | 63.0% | $+84.00 | -$66.30 | $+17.69 | 1.29 | 52.83 | $27.80 |
| Momentum_Expansion | 36 | 52.8% | $+58.98 | -$90.53 | $-31.55 | 0.70 | -99.24 | $51.58 |

## 2. Predictive Edge Matrix (Information Coefficient & Directional Hit Rate)

| Signal Factor | 1s IC | 1s Hit% | 3s IC | 3s Hit% | 5s IC | 5s Hit% | 10s IC | 10s Hit% | 30s IC | 30s Hit% | 60s IC | 60s Hit% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | +0.042 | 10.4% | +0.073 | 29.6% | +0.096 | 48.6% | +0.091 | 49.3% | +0.070 | 51.3% | -0.028 | 47.8% |
| Convexity_Cascade | +0.054 | 10.6% | +0.101 | 30.4% | +0.139 | 50.2% | +0.147 | 52.3% | +0.108 | 52.6% | +0.044 | 48.3% |
| Momentum_Expansion | +0.038 | 10.7% | +0.065 | 30.6% | +0.090 | 50.9% | +0.071 | 53.0% | +0.060 | 53.5% | +0.026 | 50.0% |

## 3. Position Trade Log (Executed Positions)

| Exit Time | Strategy | Side & Size | Exit Price | Exec Type | Exit Reason | Net PnL ($) | Return (bps) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| 15:02:24 | Hedged_Convexity | LONG 108.43 BTC | $78.4 | MAKER | TRAILING_STOP | $+1.44 | +1.7 bps |
| 15:02:24 | Convexity_Cascade | LONG 54.22 BTC | $78.4 | MAKER | TRAILING_STOP | $+0.51 | +1.2 bps |
| 15:18:22 | Convexity_Cascade | SHORT 54.93 BTC | $77.4 | MAKER | DEFENSIVE_MAKER_HEDGE | $-3.25 | -7.7 bps |
| 15:18:26 | Hedged_Convexity | SHORT 109.87 BTC | $77.5 | TAKER | STOP_LOSS | $-14.72 | -17.3 bps |
| 15:19:42 | Hedged_Convexity | SHORT 110.08 BTC | $77.2 | MAKER | TRAILING_STOP | $+0.65 | +0.8 bps |
| 15:24:47 | Hedged_Convexity | LONG 109.46 BTC | $77.8 | MAKER | TRAILING_STOP | $+9.59 | +11.3 bps |
| 15:30:06 | Hedged_Convexity | LONG 109.36 BTC | $77.8 | MAKER | TRAILING_STOP | $+7.78 | +9.1 bps |
| 15:31:54 | Convexity_Cascade | LONG 109.12 BTC | $78.1 | MAKER | TAKE_PROFIT | $+14.69 | +17.3 bps |
| 15:37:12 | Hedged_Convexity | LONG 108.72 BTC | $78.1 | MAKER | DEFENSIVE_MAKER_HEDGE | $-8.96 | -10.5 bps |
| 15:48:36 | Hedged_Convexity | LONG 108.55 BTC | $78.5 | MAKER | TAKE_PROFIT | $+14.27 | +16.8 bps |
| 15:49:24 | Hedged_Convexity | LONG 108.35 BTC | $78.4 | TAKER | STOP_LOSS | $-13.39 | -15.8 bps |
| 15:53:48 | Convexity_Cascade | LONG 108.34 BTC | $78.5 | MAKER | TRAILING_STOP | $+0.52 | +0.6 bps |
| 16:11:59 | Convexity_Cascade | LONG 108.99 BTC | $78.1 | MAKER | TRAILING_STOP | $+6.60 | +7.8 bps |
| 16:13:46 | Momentum_Expansion | LONG 108.97 BTC | $78.0 | MAKER | PROFIT_DECAY_EXIT | $-2.33 | -2.7 bps |
| 16:16:31 | Momentum_Expansion | LONG 108.77 BTC | $78.1 | MAKER | DEFENSIVE_MAKER_HEDGE | $-11.79 | -13.9 bps |
| 16:27:13 | Momentum_Expansion | LONG 108.49 BTC | $78.4 | MAKER | PROFIT_DECAY_EXIT | $-2.01 | -2.4 bps |
