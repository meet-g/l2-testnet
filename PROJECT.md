# Project: Orthogonal Microstructure Strategy Research & Production Integration

## Architecture
The system architecture integrates an orthogonal market microstructure strategy (`Queue_Replenishment`) into the existing Hyperliquid high-frequency trading and offline L2 replay platform. The architecture comprises five decoupled layers:

1. **Market Microstructure Feature Extraction Layer (`signals/queue_replenishment.py`)**:
   - Computes dynamic Level-1 queue replenishment deltas ($R_{b1}, R_{a1}$) accounting for aggressive trade depletion and resting quote updates.
   - Computes multi-tier (Levels 1-3) depth replenishment ($R_{b3}, R_{a3}$) and order cancellation asymmetry ($C_a, C_b$).
   - Tracks depletion latency persistence ($\tau_a, \tau_b$) across consecutive depleted order book snapshots.
   - Applies active taker flow gating ($|S_{cvd}| \ge 0.18$) and 2-minute macro trend alignment to eliminate dead spreads and toxic adverse selection.
   - Scales notional depth thresholds dynamically via `book.notional_scale` ($85,000 / P_{mid}$) for cross-coin portability.
   - Returns a strictly normalized `SignalResult` with `score` $\in [-1.0, 1.0]$ and `confidence` $\in [0.0, 1.0]$.

2. **Composite Alpha Aggregation Layer (`signals/composite_alpha.py`)**:
   - Instantiates `QueueReplenishmentSignal` alongside existing sub-signals.
   - Exposes `signal_queue_replenishment` for direct engine and backtest extraction.

3. **Configuration & Parameter Management Layer (`strategies.json`, `config.py`)**:
   - Registers strategy parameters (`entry_threshold: 0.82`, `order_size_btc: 0.1`, `take_profit_bps: 20.0`, `stop_loss_bps: 8.0`, `trailing_stop_activation_bps: 5.0`, `trailing_stop_distance_bps: 2.0`, `hedge_trigger_loss_bps: -3.5`, `hedge_reversal_threshold: 0.15`, `min_volatility_bps: 4.5`, `loss_cooldown_secs: 120`).
   - Registers dataclass definitions and programmatic fallback defaults in `config.py`.

4. **Execution & Risk Management Engine Layer (`engine/backtester.py`, `main.py`)**:
   - Implements `HEDGED_MAKER` lifecycle: passive maker entry at inside quotes (1.5 bps fee), maker take profit (+20 bps), trailing stop fee ratchet (+5 bps activation, 2 bps distance), defensive maker hedge exit (-3.5 bps loss on signal reversal saving 3.0 bps taker fee), and emergency taker stop loss (-8 bps, 4.5 bps taker fee + 0.2 bps slippage).
   - Enforces co-entry protection (+0.04 conviction hurdle boost, 50% size discount) when multiple strategies hold simultaneous positions in the same direction.
   - Routes live and paper trading in `main.py`.

5. **Multi-Core Parallel Replay & Verification Layer (`scripts/test_all_strategies_all_data.py`)**:
   - Saturates 12 CPU cores using multiprocessing with LPT bin packing.
   - Wires `QueueReplenishment` signal caller in `active_sig_callers` and `sub_sigs` for high-throughput parallel evaluation across all 505 HYPE recording datasets.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Level-1 Dynamic Queue Replenishment Delta | Real-time calculation of $R_{b1} = \Delta Q_{b1} + Vol_{sold}$ and $R_{a1} = \Delta Q_{a1} + Vol_{bought}$ | M1 | Survey R1/R2 |
| F2 | Multi-Tier Depth & Cancellation Asymmetry | 3-level replenishment $R_{b3}, R_{a3}$ and multi-tier cancellation asymmetry $S_{canc} = \frac{C_a - C_b}{C_a + C_b + \epsilon}$ | M1 | Survey R1/R2 |
| F3 | Depletion Latency Persistence Tracker | Tracks consecutive depleted snapshots $\tau_a, \tau_b$ to measure depth elasticity and replenishment delays | M1 | Survey R1/R2 |
| F4 | Trend & Flow Directional Gating | Active trade flow gate ($|S_{cvd}| \ge 0.18$), 2-min macro trend alignment, and sign consistency | M1 | Survey R1/R2 |
| F5 | Composite Alpha Model Integration | Instantiate and expose `signal_queue_replenishment` in `signals/composite_alpha.py` | M1 | Survey R1 |
| F6 | Strategy Parameter Registration in `strategies.json` | Configure `Queue_Replenishment` parameters and register in `execution_strategies` | M2 | Survey R1/R2 |
| F7 | Config Class Models & Defaults in `config.py` | Add `QueueReplenishmentConfig` dataclass and update `DEFAULT_STRATEGIES_JSON` | M2 | Survey R1 |
| F8 | Backtester Strategy Registry & Engine Integration | Register `Queue_Replenishment` in `engine/backtester.py:strategy_defs` and `unique_signals` as `HEDGED_MAKER` | M2 | Survey R1 |
| F9 | CLI & Runtime Routing in `main.py` | Register strategy in `main.py` for live/paper trading and strategy list validation | M2 | Survey R1 |
| F10 | Replay Script Caller Hook in `scripts/test_all_strategies_all_data.py` | Wire `QueueReplenishment` into `active_sig_callers` and `sub_sigs` for multi-core replay | M2 | Survey R3 |
| F11 | Standalone 505 HYPE Dataset Backtest Evaluation | Execute parallel replay of `Queue_Replenishment` across all 505 HYPE datasets, achieving positive Net PnL (> $0) under VIP 0 retail fees | M3 | Survey R3 |
| F12 | Combined Portfolio Synergy Evaluation | Execute 4-strategy parallel replay across all 505 HYPE datasets, expanding Net PnL beyond the +$1,694.20 Triad baseline | M3 | Survey R3 |
| F13 | Audit Artifact Generation & Performance Documentation | Generate `audits/queue_replenishment_505_eval.json` and comprehensive synergy audit report | M3 | Survey R3 |
| F14 | Adversarial Robustness & Extreme Condition Testing | Verify strategy behavior under zero volatility, spread spikes, order book collapse, and rapid reversals | M4 | Final Gate |
| F15 | Zero-Cheat Forensic Audit Verification | Verify 100% authentic logic, zero hardcoding, zero dummy facades, and strict fee/risk compliance | M4 | Final Gate |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Signal Module Implementation (`QueueReplenishmentSignal`) | Implement F1, F2, F3, F4, F5 in `signals/queue_replenishment.py` and `signals/composite_alpha.py` | Survey Complete | PLANNED |
| M2 | System Integration & Configuration Registration | Implement F6, F7, F8, F9, F10 in `strategies.json`, `config.py`, `engine/backtester.py`, `main.py`, and `scripts/test_all_strategies_all_data.py` | M1 | PLANNED |
| M3 | 505 HYPE Dataset Parallel Backtesting & Portfolio Synergy | Execute F11, F12, F13 across all 505 HYPE datasets via `scripts/test_all_strategies_all_data.py` | M1, M2 | PLANNED |
| M4 | Final Gate Review & Adversarial Hardening | Execute F14, F15 with Reviewers, Challengers, and Forensic Auditor | M1, M2, M3 | PLANNED |

## Interface Contracts
### `signals/queue_replenishment.py` ↔ `engine/backtester.py`
- Inherits: `signals.base.BaseSignal(ABC)`
- Method: `compute(self, book: OrderBook, trades: TradeManager, timestamp_ms: Optional[int] = None) -> SignalResult`
- Output Schema:
  - `name: str = "QueueReplenishment"`
  - `score: float` strictly in $[-1.0, 1.0]$
  - `raw_value: float` (unbounded core composite replenishment value)
  - `confidence: float` strictly in $[0.0, 1.0]$
  - `timestamp_ms: int`
  - `metadata: Dict[str, Any]` including `l1_rep_bid`, `l1_rep_ask`, `l3_rep_bid`, `l3_rep_ask`, `latency_bid`, `latency_ask`, `s_canc`, `cvd_fast`, `trend_bps`

### `strategies.json` & `config.py` ↔ `engine/backtester.py`
- Configuration Dictionary:
  ```json
  "Queue_Replenishment": {
      "enabled": true,
      "execution_type": "HEDGED_MAKER",
      "entry_threshold": 0.82,
      "order_size_btc": 0.1,
      "take_profit_bps": 20.0,
      "stop_loss_bps": 8.0,
      "trailing_stop_activation_bps": 5.0,
      "trailing_stop_distance_bps": 2.0,
      "hedge_trigger_loss_bps": -3.5,
      "hedge_reversal_threshold": 0.15,
      "min_volatility_bps": 4.5,
      "loss_cooldown_secs": 120
  }
  ```

### `scripts/test_all_strategies_all_data.py`
- Registration in `active_sig_callers`:
  ```python
  if hasattr(runner.alpha_model, "signal_queue_replenishment") and runner.alpha_model.signal_queue_replenishment:
      active_sig_callers["QueueReplenishment"] = runner.alpha_model.signal_queue_replenishment.compute
  ```
- Registration in `sub_sigs`:
  ```python
  sub_sigs["QueueReplenishment"] = 0.0
  ```

## Code Layout
- `signals/queue_replenishment.py`: Owned exclusively by M1 Worker
- `signals/composite_alpha.py`: Owned exclusively by M1 Worker
- `strategies.json`: Owned exclusively by M2 Worker
- `config.py`: Owned exclusively by M2 Worker
- `engine/backtester.py`: Owned exclusively by M2 Worker
- `main.py`: Owned exclusively by M2 Worker
- `scripts/test_all_strategies_all_data.py`: Owned exclusively by M2 Worker
- `audits/`: Owned exclusively by M3 Worker
