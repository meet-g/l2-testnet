# Project: Root Cause Diagnostic Investigation — Hyperliquid Paper vs. Live Discrepancies

## Architecture & Diagnostic Framework
The diagnostic investigation analyzes the root causes of the severe performance discrepancy between theoretical paper backtesting (`engine/backtester.py`, `EdgeEvaluator`) and live execution on Hyperliquid (`engine/live_executor.py`). The investigation spans four core vectors:

1. **Vector 1: Slippage & Execution Type**
   - Determination of Maker vs Taker execution frequency and causes (`force_market_orders: true`, automated IOC escalation on `Alo` rejections).
   - Fee impact quantification (maker rebate/fee vs taker fee).
   - Spread-crossing penalty drag (paying full bid-ask spread on entry and exit).

2. **Vector 2: Queue Priority & Adverse Selection**
   - Fill mechanism comparison: `EdgeEvaluator` instantaneous touch fill vs. Hyperliquid strict FIFO queue priority.
   - Queue depth and order cancellation dynamics (94.6% of resting quotes cancelled as market drifts away).
   - Quantitative measurement of post-fill price drift (-0.82 bps 1s, -1.36 bps 30s) proving toxic flow and adverse sweeps.

3. **Vector 3: Latency & Order Lifecycle**
   - Book data staleness: WebSocket `l2Book` subscription omits `"fast": true`, causing ~1,000 ms lag.
   - Wire latency: synchronous HTTP POST over Python `requests` with single-threaded queue averaging 608.5 ms.
   - Total latency ~1,608 ms causing 53.8% `Alo` order rejections ("Post only order would have immediately matched").
   - State synchronization lag: 5-second REST polling in `sync_state()` causing 1,998 order rejections (`Reduce only...` and `Insufficient margin`).

4. **Vector 4: Exit Logic Disparities & Historical Audits**
   - Trailing stop ratchet simulation defect: `backtester.py` assumes trailing stops fill passively as Maker at `max(best_ask, limit)` earning maker fees in declining markets.
   - Emergency IOC stop loss defect: `live_executor.py` places client-side IOC stops at exact `best_bid` with 0 bps slippage buffer, causing 11-second, 11-reject cascades (-23.81 bps loss).
   - Orphaned native on-chain TPSL brackets: `place_bracket_order` implemented but never called by `on_signal_update`.
   - Actionable 5-point prioritized remediation architecture for `engine/backtester.py` and `engine/live_executor.py`.

---

## Feature Inventory
| # | Feature / Vector | Detailed Finding / Deliverable | Milestone | Source |
|---|------------------|--------------------------------|-----------|--------|
| F1 | Vector 1: Forced Taker & Spread Crossing | Analysis of `strategies.json` (`force_market_orders: true`, `market_slippage_pct: 0.01` from commit `2cb446b`) and IOC auto-escalation in `live_executor.py:1386-1405`. | M1 | Explorer 1 Survey |
| F2 | Vector 1: Empirical Trade & Fill Metrics | Statistics across 991 live trades (Maker: 75.2% WR, +$145.95 Net; Taker: 22.7% WR, -$59.30 Net) and 1,058 clearinghouse fills (Maker: +$6.50; Taker: -$45.34). | M1 | Explorer 1 Survey |
| F3 | Vector 1: Fee Drag & Friction Quantification | Quantify 3.18 bps minimum round-trip taker friction (1.38 bps spread + 1.80 bps fee on SKHX) vs 0.60 bps maker, destroying 50-80% of micro-scalping edge. | M1 | Explorer 1 Survey |
| F4 | Vector 2: Instantaneous Touch Fill in Backtest | Analysis of `EdgeEvaluator` in `engine/backtester.py:747-809` assuming 0 queue depth, 0 volume exhaustion, and immediate +0.5 to +1.5 bps mid-price credit. | M1 | Explorer 2 Survey |
| F5 | Vector 2: Queue Tail Reality & Churn | Analysis of FIFO queue in `live_executor.py:2116-2166`: 12.03 units ($12k) queue ahead on SKHX, 94.63% cancellation rate without filling during favorable rallies. | M1 | Explorer 2 Survey |
| F6 | Vector 2: Adverse Selection Quantification | Quantitative measurement of post-fill price drift across real clearinghouse fills (-0.82 bps 1s, -1.36 bps 30s) and 1.82 bps net entry distortion vs backtest. | M1 | Explorer 2 Survey |
| F7 | Vector 2: Taker Escalation Trap & Reconciled Proof | Analysis of `DEFENSIVE_HEDGE_ESCALATE` (0% WR) and direct proof in session 4156: Paper +$14.02 vs Live -$15.87 (-$29.89 discrepancy from 23 taker stops). | M1 | Explorer 2 Survey |
| F8 | Vector 3: L2 Book Update Lag (~1,000 ms) | WebSocket `l2Book` subscription in `main.py:354,441` and `data_collector.py:173` omitting `"fast": true`, causing 1,000 ms stale quote inputs. | M1 | Explorer 1 Survey |
| F9 | Vector 3: Wire & Processing Latency | Measured latency stats across 14,529 events: 608.5 ms mean wire time for RESTING, single-threaded executor serialization, total 1,608 ms pipeline delay. | M1 | Explorer 1 Survey |
| F10 | Vector 3: Order Rejection & State Decoupling | 5-second polling in `sync_state()` causing 1,321 "Reduce only would increase position" and 677 "Insufficient margin" rejections. 53.8% ALO rejection rate. | M1 | Explorer 1 Survey |
| F11 | Vector 4: Trailing Stop Simulation Inversion | Analysis of `engine/backtester.py:391-400` filling trailing stops at `max(best_ask, target_limit)` as Maker in declining markets. | M1 | Explorer 3 Survey |
| F12 | Vector 4: Emergency IOC Rejection Cascades | Analysis of `live_executor.py:1683,1868` placing IOC stops at exact `best_bid` with 0 slippage buffer, causing 11-second rejection cascade and -23.81 bps loss. | M1 | Explorer 3 Survey |
| F13 | Vector 4: Orphaned Native On-Chain TPSL | Analysis of `place_bracket_order` (lines 1471-1558) configured in `strategies.json` but orphaned in `on_signal_update`, leaving live positions unhedged. | M1 | Explorer 3 Survey |
| F14 | Comprehensive Historical Session Synthesis | Systematic audit table and deep dive across 47 live sessions and key case studies (`session_20261104_171133`, `session_20261030_102317`, `session_20261104_164427`, etc.). | M1 | All Explorers |
| F15 | Actionable Prioritized Remediation Architecture | Concrete specifications for updating `engine/backtester.py` (queue modeling, volume exhaustion, dynamic slippage, taker SL) and `engine/live_executor.py` (native TPSL, slippage buffer, WebSocket fills). | M1 | All Explorers |
| F16 | Independent Review & Adversarial Stress Testing | Rigorous examination by 2 Reviewers and empirical stress testing by 2 Challengers. | M2 | Gate Review |
| F17 | Forensic Integrity Audit Verification | Binary veto forensic audit verifying 100% authentic evidence, zero fabricated claims, zero simulation shortcuts, and strict alignment with code and data. | M2 | Gate Audit |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Master Diagnostic Report Generation | Synthesize F1 through F15 into authoritative diagnostic report at `audits/root_cause_investigation_report.md` | Survey Complete | IN_PROGRESS |
| M2 | Review, Challenge & Forensic Integrity Audit | Multi-agent gate verification (F16, F17) with 2 Reviewers, 2 Challengers, and Forensic Auditor | M1 | PLANNED |

---

## Code Layout & Ownership
- `audits/root_cause_investigation_report.md`: Owned exclusively by M1 Worker
- `.agents/teamwork/orchestrator_3/`: Orchestrator state and metadata
- `engine/backtester.py`, `engine/live_executor.py`, `strategies.json`, `config.py`: Target codebases for diagnostic review (Read-Only)
- `audits/`, `logs/`, `data/`: Evidence sources (Read-Only)
