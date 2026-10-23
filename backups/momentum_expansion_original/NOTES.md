# Original Momentum Expansion Strategy Runbook & Full Specification

This directory preserves the exact, pristine version of the **Original Momentum Expansion Strategy** before the volume gating calibrations of October 23, 2026.

---

## 1. Directory Inventory

- [`momentum_expansion.py`](momentum_expansion.py): Pristine signal class implementation (`git show HEAD~1:signals/momentum_expansion.py`).
- [`strategies_original_momentum.json`](strategies_original_momentum.json): Pristine parameter configuration extracted from `strategies.json` at commit `3644e65`.
- [`NOTES.md`](NOTES.md): Complete mathematical runbook, empirical performance metrics, and restoration guide (this document).

---

## 2. Mathematical Architecture

The Original Momentum Expansion strategy was engineered as a high-frequency market microstructure alpha designed to enter early on multi-minute directional expansions:

### A. Order Book Structure Score ($S_{\text{book}}$)
1. **Touch Queue Depletion Ratio**:
   $$Q_r = \ln\left(\frac{\max(Q_{b1}, 0.005 \cdot \text{scale})}{\max(Q_{a1}, 0.005 \cdot \text{scale})}\right)$$
   $$S_{\text{touch}} = \tanh(0.40 \cdot Q_r)$$
2. **25-Level Decayed Weighted Order Book Imbalance (WOBI)**:
   $$WOBI = \frac{\sum_{i=0}^{24} e^{-0.12 i} (Q_{b,i} - Q_{a,i})}{\sum_{i=0}^{24} e^{-0.12 i} (Q_{b,i} + Q_{a,i})}$$
3. **Order Count Imbalance ($N_{\text{imb}}$)** (Anti-Whale Dispersion):
   $$N_{\text{imb}} = \frac{\sum_{i=0}^{24} n_{b,i} - \sum_{i=0}^{24} n_{a,i}}{\sum_{i=0}^{24} (n_{b,i} + n_{a,i})}$$
4. **Composite Book Score**:
   $$S_{\text{book}} = 0.45 \cdot WOBI + 0.30 \cdot S_{\text{touch}} + 0.25 \cdot N_{\text{imb}} + S_{\text{hole}}$$

### B. Dual-Horizon Taker Order Flow Impulse ($S_{\text{flow}}$)
Calculates Cumulative Volume Delta (CVD) across fast (15s) and slow (60s) windows:
$$\text{Flow}_{\text{fast}} = \tanh\left(\frac{\text{CVD}_{15\text{s}}}{\max(1.5 \cdot \text{scale}, 0.1 \cdot \text{scale})}\right)$$
$$\text{Flow}_{\text{slow}} = \tanh\left(\frac{\text{CVD}_{60\text{s}}}{\max(4.0 \cdot \text{scale}, 0.5 \cdot \text{scale})}\right)$$
$$S_{\text{flow}} = 0.65 \cdot \text{Flow}_{\text{fast}} + 0.35 \cdot \text{Flow}_{\text{slow}}$$

### C. Medium-Term Trend Alignment ($S_{\text{trend}}$)
Tracks 2-minute rolling mid-price return in basis points:
$$\text{Trend}_{\text{bps}} = \frac{P_{\text{mid}} - P_{\text{mid},-120\text{s}}}{P_{\text{mid},-120\text{s}}} \times 10,000$$
$$S_{\text{trend}} = \tanh\left(\frac{\text{Trend}_{\text{bps}}}{6.0}\right)$$

### D. Confluence Synthesis
When order book and flow agree in direction ($S_{\text{book}} \cdot S_{\text{flow}} > 0$), flow is active ($|S_{\text{flow}}| \ge 0.18$), and macro trend is aligned ($S_{\text{flow}} \cdot S_{\text{trend}} \ge -0.02$):
$$\text{RawAlpha} = 0.50 \cdot S_{\text{book}} + 0.35 \cdot S_{\text{flow}} + 0.15 \cdot S_{\text{trend}}$$

---

## 3. Original Execution Parameters (`strategies.json`)

```json
{
  "Momentum_Expansion": {
    "enabled": true,
    "description": "Multi-minute structural trend expansion entering on order book queue exhaustion, 25-level depth support, and CVD acceleration with absorption trap shielding",
    "signal_key": "MomentumExpansion",
    "execution_type": "HEDGED_MAKER",
    "entry_threshold": 0.70,
    "order_size_btc": 0.1,
    "take_profit_bps": 20.0,
    "stop_loss_bps": 8.0,
    "trailing_stop_activation_bps": 5.0,
    "trailing_stop_distance_bps": 2.0,
    "hedge_trigger_loss_bps": -4.0,
    "hedge_reversal_threshold": -0.35,
    "max_holding_time_secs": 180,
    "exit_reversal_threshold": 0.65,
    "min_volatility_bps": 4.5,
    "loss_cooldown_secs": 120
  }
}
```

---

## 4. Complete Empirical Benchmark (All 76 Large HYPE Sessions)

Benchmarked across all 76 HYPE recording files $\ge 7.0$ MB in `data/hype/` (701.9 MB raw tick data spanning Oct 5 to Oct 23, 2026):

| Microstructure Metric | Original Strategy Result |
| :--- | :---: |
| **Total Executed Trades** | 539 trades |
| **Winning Trades** | 350 wins |
| **Losing Trades** | 189 losses |
| **Win Rate** | **64.9%** |
| **Gross PnL ($)** | **+$2,078.84** |
| **Exchange Fees ($)** | **-$1,540.28** |
| **Net PnL ($)** | **+$538.57** |
| **Profit Factor** | **2.80** |
| **Average Trade Return** | **+1.18 bps** |
| **Maximum Drawdown ($)** | **$74.30** |
| **Fee Drag Ratio** | **74.1%** (Fees / Gross PnL) |

### Exit Reason Distribution:
- **Trailing Stop Exits**: 288 (53.4%) — Primary profit capture engine.
- **Take Profit Exits**: 59 (10.9%) — 20.0 bps target limit fills.
- **Defensive Maker Hedges**: 103 (19.1%) — Maker hedge exits.
- **Taker Stop Loss Hits**: 53 (9.8%) — Unhedged adverse sweeps hitting -8.0 bps taker stop loss.
- **Profit Decay Exits**: 21 (3.9%) — Positions that peaked $>4.0$ bps and decayed to $+0.5$ bps.
- **Time Limit Exits**: 3 (0.6%) — Exceeded 180s holding time.

---

## 5. Strengths vs. Vulnerabilities

### Key Strengths:
1. **Exceptional Runaway Trend Capture**: On powerful trending days (such as October 15 where HYPE surged $+2.5\%$ in 1 hour), the lower `0.70` threshold entered aggressively, capturing **+$131.57** on October 15 alone.
2. **High Opportunity Velocity**: Generated 539 trades across 76 sessions (~7.1 trades/hour), maintaining active market engagement.
3. **High Win Rate in Clean Trends**: Maintained a 64.9% win rate over 3 weeks of live mainnet data.

### Key Vulnerabilities:
1. **Severe Taker Stop Loss Penalty**: Suffered **53 catastrophic stop loss hits**. Because `hedge_reversal_threshold = -0.35` required the score to stay above $-0.35$ while losing $-4.0$ bps, fast toxic flow wiped through the passive book, forcing market orders at -8.0 to -12.0 bps with a 4.5 bps taker fee penalty.
2. **Extreme Fee Drag (74.1%)**: Paid $1,540.28 in fees on $2,078.84 gross profit.
3. **Low-Volume Churn**: Suffered repeated whipsaws during low-volume sideways chop (e.g., Oct 13, 14, 16, 21), where retail flow blips ($3,500 volume) triggered false breakouts.

---

## 6. How to Restore the Original Strategy

To switch back to the original strategy configuration at any time:

1. **Restore Signal Implementation**:
   ```powershell
   Copy-Item backups/momentum_expansion_original/momentum_expansion.py signals/momentum_expansion.py -Force
   ```
2. **Restore Strategy Config in `strategies.json`**:
   Update `strategies.json` under `"Momentum_Expansion"`:
   ```json
   "entry_threshold": 0.70,
   "hedge_trigger_loss_bps": -4.0,
   "hedge_reversal_threshold": -0.35
   ```
