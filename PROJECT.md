# Project: Hyperliquid L2 Replay & Backtest Execution Acceleration

## Architecture
The execution acceleration architecture optimizes the high-frequency L2 replay and backtesting pipeline across four decoupled layers:
1. **Fast Ingestion & Deserialization Layer (`engine/data_collector.py`, `scripts/`)**:
   - High-throughput binary file streaming using `open("rb", buffering=1024*1024)`.
   - SIMD-accelerated JSON deserialization via `orjson.loads` with seamless, robust fallback to Python's standard `json`.
2. **Microstructure Alpha & Signal Calculation Layer (`signals/`, `engine/backtester.py`)**:
   - Monotonic sliding window queue for O(1) rolling price extrema (`min`/`max`) in `EdgeEvaluator.record_step`.
   - State-cached volume bucket imbalance in `VPINSignal` eliminating 99.9% of generator evaluations.
   - Zero-allocation rolling float deque for `VOISignal` variance and standardization.
   - C-accelerated O(log N) `bisect_left` lookup for chronological trend windows in `MomentumExpansionSignal`.
   - Redundant sub-signal evaluation deduplication in `CompositeAlpha`.
3. **OrderBook & Memory Allocation Layer (`core/orderbook.py`)**:
   - Elimination of redundant Timsort calls on pre-sorted Hyperliquid L2 order books.
   - `slots=True` memory optimization on `L2Level`, `Trade`, and `VolumeBucket` dataclasses, reducing per-instance memory by 68.4%.
   - Replay-mode bypass of unconsumed `self.history = deque(maxlen=500)` snapshot retaining queue.
4. **Multi-Core Batch Replay Layer (`scripts/test_all_strategies_all_data.py`)**:
   - Host CPU core saturation (`os.cpu_count() == 12`).
   - One-time worker process initialization of `StrategiesConfig`.
   - In-worker aggregation of exit reasons to minimize IPC serialization overhead.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | `orjson` Fast Deserialization & Fallback | SIMD JSON deserialization in `engine/data_collector.py` with automatic fallback to standard `json`. | M1 | Survey R1 |
| F2 | 1 MB Buffered Binary Streaming | Chunked binary buffer reads (`open("rb", buffering=1024*1024)`) in `L2ReplayEngine.stream_events`. | M1 | Survey R1 |
| F3 | Replay Script Ingest Acceleration | Update `scripts/replay_continuous_multiday_session.py` to use binary streaming and `orjson`. | M1 | Survey R1 |
| F4 | Monotonic Price Extrema Queue | O(1) sliding window queue in `EdgeEvaluator.record_step` replacing pure Python generator `min()`/`max()`. | M2 | Survey R2 |
| F5 | State-Cached VPIN Bucket Evaluation | Cache VPIN bucket sums on bucket count transitions, eliminating 99.9% of generator calls. | M2 | Survey R2 |
| F6 | Zero-Allocation VOI Variance Deque | Replace list allocations and generator variance with zero-allocation rolling float deque. | M2 | Survey R2 |
| F7 | O(log N) Trend Window Lookup | Replace linear scan in `MomentumExpansionSignal` with `bisect_left` on sorted timestamps. | M2 | Survey R2 |
| F8 | `CompositeAlpha` Caching & Cleanup | Cache enabled sub-signal lookup and eliminate dead signal initializations. | M2 | Survey R2 |
| F9 | Pre-Sorted OrderBook Sort Elimination | Remove redundant `.sort()` calls in `OrderBook.update_from_raw` for pre-sorted Hyperliquid feeds. | M3 | Survey R3 |
| F10 | Dataclass `slots=True` Memory Optimization | Add `slots=True` to `L2Level`, `Trade`, and `VolumeBucket` to reduce heap memory by 68.4%. | M3 | Survey R3 |
| F11 | Replay Mode History Bypass | Add `enable_history=False` option to bypass unused `self.history` deque in `OrderBook` during replay. | M3 | Survey R3 |
| F12 | Multi-Core Worker Saturation | Default worker pool to `os.cpu_count()` (12 cores) in `scripts/test_all_strategies_all_data.py`. | M4 | Survey R4 |
| F13 | Worker-Level Config Initialization | Load `StrategiesConfig` once per worker process instead of per dataset. | M4 | Survey R4 |
| F14 | Compact IPC Trade Metric Aggregation | Aggregate exit reason counts in worker processes to eliminate bulky trade dictionary IPC serialization. | M4 | Survey R4 |
| F15 | Continuous Multi-Day Benchmark Acceleration | Verify continuous 142-file replay runtime < 45.0s with 100% deterministic trade parity. | M5 | Survey R5 |
| F16 | Batch 76-Session Benchmark Acceleration | Verify 76-session batch replay runtime < 25.0s with 100% deterministic trade parity. | M5 | Survey R5 |
| F17 | Zero-Cheat Forensic Audit Verification | Verify zero hardcoded values, zero synthetic mocks, and strict fee/risk enforcement. | M5 | Survey R5 |
| F18 | Comprehensive Performance Optimization Report | Generate `replay_performance_optimization_report.md` with cProfile benchmarks and parity proofs. | M5 | Survey R5 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Fast I/O & Deserialization Pipeline (R1) | Implement F1, F2, F3 in `engine/data_collector.py` and `scripts/replay_continuous_multiday_session.py` | Survey Complete | DONE (2.65x speedup, verified parity) |
| M2 | Algorithmic Hot-Path & Signal Acceleration (R2) | Implement F4, F5, F6, F7, F8 in `engine/backtester.py` and `signals/` | Survey Complete | DONE (371s -> 265.7s, verified parity) |
| M3 | OrderBook & Allocation Streamlining (R3) | Implement F9, F10, F11 in `core/orderbook.py` | M1, M2 | DONE (slots=True, linear Timsort, history bypass, 100% parity) |
| M4 | Batch Replay Parallelism & Multi-Core Scaling (R4) | Implement F12, F13, F14 in `scripts/test_all_strategies_all_data.py` | M1, M2, M3 | DONE (12-core scaling, LPT bin-packing, IPC compression, 22.6s runtime, 100% parity) |
| M5 | Full Benchmark Verification, Parity Audit & Report (R5) | Execute F15, F16, F17, F18 across both harnesses, audit parity, and author report | M1, M2, M3, M4 | PLANNED |

## Interface Contracts
### `engine/data_collector.py`
- `L2ReplayEngine.stream_events()`: Must yield identical `dict` payloads whether parsed via `orjson` or standard `json`.
- Event schema: `{"type": str, "coin": str, "timestamp": int, "data": dict}`.

### `engine/backtester.py` ↔ `signals/`
- `EdgeEvaluator.record_step`: Must compute `current_volatility_bps` with bit-for-bit mathematical equality.
- Sub-signals (`VPINSignal`, `VOISignal`, `MomentumExpansionSignal`, `ConvexityCascadeSignal`, `HedgedConvexitySignal`):
  - Must return `tuple[float, dict]` or `float` with identical return types, metadata schemas, and float values.

### `core/orderbook.py`
- `L2Level`: Attributes `.px: float`, `.sz: float`, `.n: int`. Retains 100% attribute access compatibility.
- `OrderBook.get_bids()`, `OrderBook.get_asks()`: Return lists of `L2Level` objects preserving price-sorted order (descending for bids, ascending for asks).

## Code Layout
- `engine/data_collector.py`: Owned exclusively by M1 Worker.
- `scripts/replay_continuous_multiday_session.py`: Owned exclusively by M1 Worker.
- `engine/backtester.py`: Owned exclusively by M2 Worker.
- `signals/vpin.py`: Owned exclusively by M2 Worker.
- `signals/voi.py`: Owned exclusively by M2 Worker.
- `signals/momentum_expansion.py`: Owned exclusively by M2 Worker.
- `signals/composite_alpha.py`: Owned exclusively by M2 Worker.
- `core/orderbook.py`: Owned exclusively by M3 Worker.
- `scripts/test_all_strategies_all_data.py`: Owned exclusively by M4 Worker.
- `replay_performance_optimization_report.md`: Produced in M5.
