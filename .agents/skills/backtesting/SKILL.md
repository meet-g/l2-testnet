---
name: backtesting
description: Execute, evaluate, benchmark, and optimize quantitative microstructure backtesting strategies and offline L2 replay across Hyperliquid order book datasets.
---

# Microstructure Strategy Backtesting Runbook

This guide details how to execute, analyze, and optimize trading strategies using the offline L2 order book and trade replay engine in `D:\L2 - Testnet`.

---

## 1. Available Execution Modes & Scripts

### A. High-Throughput Parallel Backtesting (All 101 BTC Datasets)
Runs multiprocessing evaluation across all recordings in `data/btc/` for core alpha strategies (`Hedged_Convexity`, `Convexity_Cascade`, `Momentum_Expansion`):
```powershell
python scripts/test_all_btc_parallel.py
```

### B. Batch Replay Across Datasets
Sequential replay across historical datasets evaluating win rates, fee drag, net PnL, and profit factors:
```powershell
python scripts/test_profitable_strategies_all_data.py
```

### C. Top Large Sessions Replay
Runs evaluations focusing on the largest and most volatile sessions in `data/btc/`:
```powershell
python scripts/replay_large_sessions.py
```

### D. Single Dataset Replay (via Main CLI)
Accelerated replay of a specific recorded session (e.g. 10x, 100x):
```powershell
python main.py replay --replay-file data/btc/hl_btc_l2_20261003_120000.jsonl --speed 10
```

### E. Volatility Gating & Filter Backtests
Test the impact of spread, book depth volatility, and entry gating:
```powershell
python scripts/test_volatility_gating.py
python scripts/test_vol_fast.py
```

---

## 2. Strategy Configuration (`strategies.json`)

Adjust parameters before running tests:
- `entry_threshold`: Score threshold required to trigger an entry order (e.g., `0.70` to `0.86`).
- `take_profit_bps`: Profit target in basis points.
- `stop_loss_bps`: Emergency stop loss in basis points.
- `trailing_stop_activation_bps` & `trailing_stop_distance_bps`: Dynamic trailing stop ratchet.
- `hedge_trigger_loss_bps`: Trigger point for defensive maker hedge on adverse flow.
- `min_volatility_bps`: Minimum volatility filter to avoid choppy dead spreads.

---

## 3. Key Microstructure Performance Metrics

When analyzing results, always inspect:
1. **Net PnL vs. Gross PnL**: Account for VIP 0 maker rebates/fees (1.5 bps) vs taker fee penalties (4.5 bps).
2. **Win Rate & Profit Factor**: Ratio of gross profits to gross losses ($\ge 1.30$ preferred).
3. **MFE / MAE**: Maximum Favorable Excursion vs. Maximum Adverse Excursion.
4. **Holding Duration**: Ensure high-frequency alpha is not stuck in adverse inventory.
5. **Auditing**: Review generated CSV ledgers in `audits/` and strategy breakdowns under `audits/session_*/strategies/`.
