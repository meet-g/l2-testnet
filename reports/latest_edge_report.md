# Hyperliquid L2 Alpha Edge & Performance Report (HYPE - Mainnet)

- **Network**: Hyperliquid Mainnet
- **Asset**: HYPE-PERP
- **Timestamp**: 2026-10-28 00:58:30
- **Mid Price**: $81.79
- **Book Spread**: $0.00 (0.12 bps)
- **Total Cumulative CVD**: +91446.9400 HYPE

## 1. Paper-Trading Performance Summary

| Strategy | Trades | Win Rate | Gross PnL ($) | Net Fees ($) | Net PnL ($) | Profit Factor | Sharpe Ratio | Max Drawdown ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | 0 | 0.0% | $+0.00 | +$0.00 | $+0.00 | 0.00 | 0.00 | $0.00 |
| Convexity_Cascade | 2 | 0.0% | $-7.63 | -$5.10 | $-12.73 | 0.00 | -24964.34 | $12.73 |
| Momentum_Expansion | 3 | 33.3% | $-1.17 | -$6.38 | $-7.55 | 0.13 | -643.08 | $10.12 |

## 2. Predictive Edge Matrix (Information Coefficient & Directional Hit Rate)

| Signal Factor | 1s IC | 1s Hit% | 3s IC | 3s Hit% | 5s IC | 5s Hit% | 10s IC | 10s Hit% | 30s IC | 30s Hit% | 60s IC | 60s Hit% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | +0.116 | 8.9% | +0.195 | 25.3% | +0.241 | 41.8% | +0.165 | 48.4% | +0.138 | 54.9% | +0.083 | 51.9% |
| Convexity_Cascade | +0.110 | 9.2% | +0.191 | 26.2% | +0.247 | 43.3% | +0.187 | 49.0% | +0.129 | 54.2% | +0.064 | 50.7% |
| Momentum_Expansion | +0.081 | 9.5% | +0.146 | 27.0% | +0.197 | 44.4% | +0.134 | 50.2% | +0.117 | 54.2% | +0.083 | 54.9% |

## 3. Position Trade Log (Executed Positions)

| Exit Time | Strategy | Side & Size | Exit Price | Exec Type | Exit Reason | Net PnL ($) | Return (bps) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| 23:43:43 | Momentum_Expansion | SHORT 104.59 BTC | $81.3 | MAKER | DEFENSIVE_MAKER_HEDGE | $-5.58 | -6.6 bps |
| 23:48:50 | Momentum_Expansion | SHORT 52.30 BTC | $81.3 | MAKER | DEFENSIVE_MAKER_HEDGE | $-3.11 | -7.3 bps |
| 23:48:55 | Convexity_Cascade | SHORT 104.60 BTC | $81.3 | MAKER | DEFENSIVE_MAKER_HEDGE | $-6.21 | -7.3 bps |
| 23:58:47 | Momentum_Expansion | SHORT 104.62 BTC | $81.2 | MAKER | TRAILING_STOP | $+1.14 | +1.3 bps |
| 00:39:43 | Convexity_Cascade | LONG 104.46 BTC | $81.3 | MAKER | DEFENSIVE_MAKER_HEDGE | $-6.52 | -7.7 bps |
