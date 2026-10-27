# Hyperliquid L2 Alpha Edge & Performance Report (HYPE - Mainnet)

- **Network**: Hyperliquid Mainnet
- **Asset**: HYPE-PERP
- **Timestamp**: 2026-10-26 13:58:56
- **Mid Price**: $76.84
- **Book Spread**: $0.00 (0.39 bps)
- **Total Cumulative CVD**: +1084.9000 HYPE

## 1. Paper-Trading Performance Summary

| Strategy | Trades | Win Rate | Gross PnL ($) | Net Fees ($) | Net PnL ($) | Profit Factor | Sharpe Ratio | Max Drawdown ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | 2 | 50.0% | $-1.60 | -$5.10 | $-6.70 | 0.31 | -317.27 | $10.94 |
| Momentum_Expansion | 15 | 60.0% | $+51.57 | -$38.25 | $+13.33 | 1.35 | 82.67 | $32.53 |

## 2. Predictive Edge Matrix (Information Coefficient & Directional Hit Rate)

| Signal Factor | 1s IC | 1s Hit% | 3s IC | 3s Hit% | 5s IC | 5s Hit% | 10s IC | 10s Hit% | 30s IC | 30s Hit% | 60s IC | 60s Hit% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | +0.084 | 10.7% | +0.133 | 30.7% | +0.157 | 50.7% | +0.120 | 54.4% | +0.046 | 54.2% | -0.018 | 53.0% |
| Momentum_Expansion | +0.051 | 11.3% | +0.085 | 32.2% | +0.113 | 53.6% | +0.056 | 55.9% | +0.029 | 57.0% | +0.075 | 54.5% |

## 3. Position Trade Log (Executed Positions)

| Exit Time | Strategy | Side & Size | Exit Price | Exec Type | Exit Reason | Net PnL ($) | Return (bps) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| 13:23:35 | Momentum_Expansion | SHORT 109.86 BTC | $77.4 | MAKER | DEFENSIVE_MAKER_HEDGE | $-7.27 | -8.6 bps |
| 13:27:06 | Momentum_Expansion | SHORT 109.98 BTC | $77.3 | MAKER | DEFENSIVE_MAKER_HEDGE | $-7.28 | -8.6 bps |
| 13:31:14 | Momentum_Expansion | SHORT 109.94 BTC | $77.3 | MAKER | DEFENSIVE_MAKER_HEDGE | $-6.07 | -7.1 bps |
| 13:36:42 | Momentum_Expansion | LONG 109.95 BTC | $77.3 | MAKER | DEFENSIVE_MAKER_HEDGE | $-5.74 | -6.8 bps |
| 13:41:48 | Momentum_Expansion | SHORT 109.71 BTC | $77.4 | MAKER | TRAILING_STOP | $+9.58 | +11.3 bps |
| 13:43:36 | Momentum_Expansion | SHORT 109.96 BTC | $77.2 | MAKER | TRAILING_STOP | $+8.95 | +10.5 bps |
| 13:45:56 | Momentum_Expansion | LONG 109.88 BTC | $77.4 | MAKER | TRAILING_STOP | $+3.99 | +4.7 bps |
| 13:48:22 | Hedged_Convexity | SHORT 110.25 BTC | $77.2 | MAKER | DEFENSIVE_MAKER_HEDGE | $-9.72 | -11.4 bps |
| 13:49:58 | Momentum_Expansion | SHORT 110.15 BTC | $77.1 | MAKER | TRAILING_STOP | $+0.60 | +0.7 bps |
| 13:50:46 | Momentum_Expansion | LONG 110.05 BTC | $77.2 | MAKER | DEFENSIVE_MAKER_HEDGE | $-5.63 | -6.6 bps |
| 13:53:49 | Momentum_Expansion | SHORT 110.20 BTC | $77.0 | MAKER | TRAILING_STOP | $+8.70 | +10.2 bps |
| 13:54:37 | Momentum_Expansion | SHORT 110.33 BTC | $77.0 | MAKER | TRAILING_STOP | $+5.96 | +7.0 bps |
| 13:56:41 | Momentum_Expansion | SHORT 110.53 BTC | $76.8 | MAKER | TRAILING_STOP | $+9.07 | +10.7 bps |
| 13:57:40 | Hedged_Convexity | SHORT 110.85 BTC | $76.6 | MAKER | TRAILING_STOP | $+3.01 | +3.5 bps |
| 13:58:05 | Momentum_Expansion | SHORT 110.84 BTC | $76.7 | MAKER | DEFENSIVE_MAKER_HEDGE | $-6.32 | -7.4 bps |
