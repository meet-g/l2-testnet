# Project: Convexity Cascade Strategy Optimization & Calibration

## Architecture
The system consists of three architectural layers:
1. **Signal Generation (`signals/convexity_cascade.py`)**: Computes real-time L2 order book microstructural alpha factors from depth curves, order counts, trade flows (CVD), and liquidity gaps.
2. **Strategy Configuration (`strategies.json`)**: Configures execution thresholds, position sizing, profit targets, trailing stops, defensive hedging triggers, and risk cooldowns.
3. **Execution & Replay Engine (`engine/backtester.py`, `scripts/`)**: Replays L2 market data, evaluates FIFO queue fills, models VIP 0 fees (1.5 bps maker, 4.5 bps taker, 0.2 bps slippage), manages defensive maker hedging at top-of-book, and enforces portfolio co-entry discounting (+0.04 conviction hurdle, 50% size discount).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | True Depth Curvature Calculation | Compute discrete 2nd-derivative curvature $\Delta^2 Q / \Delta l^2$ across levels 1-5 instead of degenerate depth imbalance. | M1 | Survey (R2) |
| F2 | Dynamic Liquidity Hole Calibration | Rescale liquidity hole vacuum threshold to coin-specific level depth instead of fixed 396 HYPE to eliminate false vacuum triggers. | M1 | Survey (R1, R2) |
| F3 | Size-Weighted Order Concentration | Implement average order size ratio $\bar{S}_{bid} / \bar{S}_{ask}$ ($Q/N$) to detect true whale walls vs retail order splitting. | M1 | Survey (R1, R2) |
| F4 | Limit Wall Absorption Shielding | Check for opposing resting absorption blocks to prevent entries into heavy counter-flow walls. | M1 | Survey (R2) |
| F5 | Trade Flow / CVD Impulse Confirmation | Require aggressive taker trade flow impulse to confirm book convexity before entry. | M1 | Survey (R2) |
| F6 | Volatility & Volume Fee Hurdle Gating | Gate signals during low volatility or low volume regimes where fee hurdle cannot be cleared. | M1 | Survey (R2) |
| F7 | Conviction & Sizing Threshold Tuning | Calibrate `entry_threshold` in `strategies.json` to filter low-conviction noise trades. | M1 | Survey (R3) |
| F8 | Payoff Geometry & Trailing Stop Calibration | Widen `trailing_stop_distance_bps` and `take_profit_bps` to capture full cascade expansion beyond the 3.0 bps maker fee drag. | M1 | Survey (R1, R3) |
| F9 | Defensive Maker Hedge Recalibration | Adjust `hedge_trigger_loss_bps` and `hedge_reversal_threshold` to prevent premature hedge execution on normal spread bounce. | M1 | Survey (R1, R3) |
| F10 | Risk Guardrails & Loss Cooldown | Calibrate `stop_loss_bps` and `loss_cooldown_secs` to mitigate consecutive chop drawdowns. | M1 | Survey (R3) |
| F11 | Continuous Multi-Day Replay Benchmark | Achieve Net PnL >= +$250.00, WR >= 58.0%, PF >= 2.50, and stop rate <= 3.0% on 142 files (782 MB). | M2 | ORIGINAL_REQUEST (R4) |
| F12 | 76 Large Historical Sessions Benchmark | Achieve positive Net PnL, PF >= 2.00, WR >= 58.0% on 76 large HYPE sessions (702 MB). | M3 | ORIGINAL_REQUEST (R4) |
| F13 | Triad Portfolio Synergy & Co-Entry Integrity | Verify concurrent execution with Hedged_Convexity and Momentum_Expansion achieves synergy and valid co-entry discounting. | M3 | ORIGINAL_REQUEST (R4) |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Alpha Signal Enhancement & Strategy Calibration | Implement F1-F10 in `signals/convexity_cascade.py` and `strategies.json` | Survey Complete | DONE |
| M2 | Continuous Multi-Day Replay Benchmark Verification | Verify F11 across 142 continuous files (782 MB) to achieve Net PnL >= +$250, WR >= 58%, PF >= 2.50 | M1 | DONE |
| M3 | 76 Historical Sessions & Portfolio Synergy Verification | Verify F12, F13 across 76 large sessions (702 MB) and triad portfolio synergy | M2 | DONE |

## Interface Contracts
### `signals/convexity_cascade.py` ↔ `engine/backtester.py`
- Function: `ConvexityCascadeSignal.calculate_signal(order_book: dict, trades: list = None, ...) -> tuple[float, dict]`
  - Output: `(conviction_score, metadata)` where `conviction_score` is a float in `[-1.0, 1.0]`.
  - Sign convention: positive = bullish long signal, negative = bearish short signal.
  - Metadata dict: includes individual factor components (`curvature`, `hole_detected`, `concentration_ratio`, `cvd_impulse`, `vol_gate`).
  - Backward compatibility: must match expected return format for `L2EngineRunner` and `backtester.py`.

### `strategies.json` ↔ `engine/backtester.py`
- Configuration schema under `"Convexity_Cascade"`:
  ```json
  {
    "enabled": true,
    "entry_threshold": float,
    "take_profit_bps": float,
    "stop_loss_bps": float,
    "trailing_stop_activation_bps": float,
    "trailing_stop_distance_bps": float,
    "hedge_trigger_loss_bps": float,
    "hedge_reversal_threshold": float,
    "min_volatility_bps": float,
    "loss_cooldown_secs": int
  }
  ```

## Code Layout
- `signals/convexity_cascade.py`: Primary signal logic and factor formulations (Owned exclusively by Worker in M1).
- `strategies.json`: Strategy parameter configuration (Owned exclusively by Worker in M2).
- `engine/backtester.py`: Core backtesting engine, queue modeling, fee deduction, hedging, and co-entry discounting.
- `scripts/replay_continuous_multiday_session.py`: Continuous 5.87-day 142-file replay harness.
- `scripts/test_all_strategies_all_data.py`: 76 large HYPE sessions benchmark harness.
- `scripts/test_multi_strategy_synergy.py`: Triad portfolio synergy & co-entry discount test harness.
