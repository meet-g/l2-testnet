# Hyperliquid L2 Alpha Edge & Performance Report (HYPE - Mainnet)

- **Network**: Hyperliquid Mainnet
- **Asset**: HYPE-PERP
- **Timestamp**: 2026-10-27 22:22:21
- **Mid Price**: $81.18
- **Book Spread**: $0.00 (0.12 bps)
- **Total Cumulative CVD**: +778723.8900 HYPE

## 1. Paper-Trading Performance Summary

| Strategy | Trades | Win Rate | Gross PnL ($) | Net Fees ($) | Net PnL ($) | Profit Factor | Sharpe Ratio | Max Drawdown ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | 36 | 52.8% | $+82.08 | -$98.18 | $-16.10 | 0.90 | 16.79 | $63.40 |
| Convexity_Cascade | 48 | 37.5% | $+69.33 | -$122.41 | $-53.08 | 0.74 | -67.43 | $100.58 |
| Momentum_Expansion | 133 | 54.1% | $+322.94 | -$318.76 | $+4.18 | 1.01 | -1.33 | $106.01 |

## 2. Predictive Edge Matrix (Information Coefficient & Directional Hit Rate)

| Signal Factor | 1s IC | 1s Hit% | 3s IC | 3s Hit% | 5s IC | 5s Hit% | 10s IC | 10s Hit% | 30s IC | 30s Hit% | 60s IC | 60s Hit% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Hedged_Convexity | +0.122 | 8.3% | +0.207 | 23.3% | +0.262 | 38.8% | +0.242 | 48.8% | +0.100 | 54.9% | +0.035 | 53.3% |
| Convexity_Cascade | +0.114 | 8.2% | +0.186 | 23.3% | +0.231 | 38.7% | +0.206 | 49.8% | +0.139 | 54.9% | +0.040 | 52.8% |
| Momentum_Expansion | +0.100 | 9.0% | +0.174 | 25.3% | +0.229 | 42.0% | +0.221 | 51.4% | +0.192 | 58.3% | +0.104 | 54.7% |

## 3. Position Trade Log (Executed Positions)

| Exit Time | Strategy | Side & Size | Exit Price | Exec Type | Exit Reason | Net PnL ($) | Return (bps) |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| 19:56:08 | Convexity_Cascade | SHORT 104.45 BTC | $81.3 | MAKER | TRAILING_STOP | $+8.11 | +9.5 bps |
| 19:59:44 | Momentum_Expansion | LONG 104.55 BTC | $81.3 | MAKER | PROFIT_DECAY_EXIT | $-2.45 | -2.9 bps |
| 20:06:34 | Momentum_Expansion | SHORT 104.69 BTC | $81.2 | MAKER | TRAILING_STOP | $+0.72 | +0.9 bps |
| 20:10:51 | Momentum_Expansion | SHORT 104.74 BTC | $81.1 | MAKER | PROFIT_DECAY_EXIT | $-2.13 | -2.5 bps |
| 20:17:17 | Momentum_Expansion | LONG 104.76 BTC | $81.3 | MAKER | TRAILING_STOP | $+9.68 | +11.4 bps |
| 20:22:25 | Momentum_Expansion | SHORT 104.83 BTC | $81.1 | MAKER | DEFENSIVE_MAKER_HEDGE | $-6.32 | -7.4 bps |
| 20:31:34 | Momentum_Expansion | SHORT 104.93 BTC | $81.0 | MAKER | TRAILING_STOP | $+1.16 | +1.4 bps |
| 20:50:58 | Momentum_Expansion | LONG 104.81 BTC | $81.1 | MAKER | DEFENSIVE_MAKER_HEDGE | $-6.11 | -7.2 bps |
| 21:26:52 | Momentum_Expansion | LONG 105.25 BTC | $80.8 | MAKER | TRAILING_STOP | $+5.06 | +6.0 bps |
| 21:33:33 | Momentum_Expansion | LONG 104.53 BTC | $81.5 | MAKER | TAKE_PROFIT | $+14.69 | +17.3 bps |
| 21:35:36 | Hedged_Convexity | LONG 104.24 BTC | $81.5 | MAKER | DEFENSIVE_MAKER_HEDGE | $-7.97 | -9.4 bps |
| 21:43:07 | Momentum_Expansion | SHORT 104.39 BTC | $81.4 | MAKER | TRAILING_STOP | $+2.07 | +2.4 bps |
| 21:46:15 | Momentum_Expansion | SHORT 104.54 BTC | $81.3 | MAKER | DEFENSIVE_MAKER_HEDGE | $-6.63 | -7.8 bps |
| 22:01:35 | Momentum_Expansion | SHORT 104.93 BTC | $81.0 | MAKER | DEFENSIVE_MAKER_HEDGE | $-5.49 | -6.5 bps |
| 22:07:35 | Convexity_Cascade | SHORT 104.89 BTC | $81.0 | MAKER | PROFIT_DECAY_EXIT | $-3.28 | -3.9 bps |
