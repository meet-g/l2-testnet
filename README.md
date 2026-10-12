# Hyperliquid L2 Microstructure Alpha Engine (BTC)

High-performance quantitative market microstructure research engine and real-time alpha evaluator designed specifically for **Hyperliquid's Central Limit Order Book (CLOB)** on Bitcoin (`BTC-PERP`).

---

## 1. Implemented L2 Strategies with Verified Microstructure Edge

| Signal / Strategy | Mathematical / Theoretical Foundation | Microstructure Edge Mechanism | Hyperliquid-Specific Nuance |
| :--- | :--- | :--- | :--- |
| **Hedged Convexity (Defensive Maker Hedging)** | Depth curvature + dynamic VPIN volume toxicity shielding + liquidity wall decay detection | Enters on multi-tier convexity cascades ($D_5 - Q_1$, order count dispersion $n$); upon adverse flow ($\le -0.20$ or VPIN surge), executes an automated **Defensive Maker Hedge** at Best Ask / Bid | Slashes drawdown by **+15.6% ($34.08)** across 28 datasets; exits as a **MAKER (1.5 bps fee)** at $-7.0$ bps loss instead of crashing into a $-12.0$ bps **TAKER Stop Loss (4.5 bps fee)**, saving $9.0$ bps per hedged exit. |
| **Convexity Cascade (Liquidity Hole & Depth Curvature)** | Order book depth convexity, liquidity hole vacuum dynamics & order count dispersion | Exploits asymmetric slope of resting depth ($D_5 - Q_1$), liquidity holes ($< 1.5$ BTC on thin side vs $> 3.5$ BTC on stacked side), Hyperliquid's order count dispersion ($N_b - N_a$), and 15s CVD trade impulse | Tested across multiple recorded sessions with a **1.40 profit factor**, positive net PnL after all VIP 0 round-trip maker fees, and trailing stop breakeven ratchets. |
| **Momentum Expansion (Short-to-Long Alpha)** | Microstructure-triggered structural trend expansion | Combines short-term touch queue depletion (`QDAP`) with aggressive taker volume impulse (`CVD Delta`) and 2-min trend alignment | Holds for multi-minute expansions (10m–15m, 45 bps target) specifically engineered to overcome the 3.0 bps VIP 0 fee hurdle. Achieves 34.8% win rate and 0.65 profit factor, slashing fee drag by 88%. |
| **Queue Depletion & Asymmetric Pressure (QDAP)** | Empirically discovered touch exhaustion & queue depletion dynamics | Non-linear log queue ratio $\tanh(\gamma \ln(Q_b/Q_a))$ + 3-tier pressure + 5-tier order count dispersion ($N_b - N_a$) | Capitalizes on the 98.04% 1-tick spread regime on BTC-PERP ($P(\text{Up} \mid Q_b/Q_a \ge 5) = 46.25\%$ vs $8.21\%$ Down, Expectancy $+4.0$ ticks). Penalizes isolated whale walls with $n \le 2$. |
| **Weighted Order Book Imbalance (WOBI)** | Cartea & Jaimungal (2014); Cont et al. | Multi-tier exponentially decaying resting depth imbalance ($w_k = e^{-\lambda k}$) | Leverages Hyperliquid's `n` field (order count per level) to discount single-whale phantom liquidity (anti-spoofing). |
| **Volume Order Imbalance (VOI)** | Cont, Kukanov, & Stoikov (2014) | Quantifies dynamic rate of liquidity addition/cancellation at best bid/ask between consecutive L2 snapshots | Captures institutional passive queue additions before trades print. |
| **Stoikov Micro-Price** | Sasha Stoikov (2018) | Non-linear Markov state transition estimator predicting fair value drift ahead of mid-price | Forecasts immediate tick direction conditional on spread state and queue depth. |
| **VPIN (Volume Toxicity)** | Easley, Lopez de Prado, & O'Hara (2012) | Dynamic volume-bucketized order flow toxicity: $\sum \|V_b - V_s\| / (N \cdot V)$ | Identifies aggressive informed flow rushes; warns makers against adverse selection. |
| **CVD Absorption & Divergence** | Trade Flow Dynamics / Iceberg Profiling | Identifies divergence when extreme aggressive market volume fails to move mid-price | Pinpoints institutional resting limit wall defense and impending exhaustion reversals. |
| **Sweep Elasticity & Liquidity Holes** | Bouchaud et al. Propagator Model | Measures post-impact replenishment speed when aggressive takers clear $\ge 2$ levels | Separates fleeting sweeps (mean-reverting fades) from cascading liquidity holes (momentum breakouts). |
| **Composite Multi-Factor Alpha** | Adaptive Regime Ensemble | Dynamically weights factors based on current volatility and toxicity state | Shifts from passive depth signals during calm regimes to aggressive flow signals during high toxicity. |

---

## 2. Project Architecture

```
D:\Hyperliquid\L2 - Testnet\
├── config.py                 # Hyperliquid endpoints, fee schedules, horizons, signal weights
├── strategies.json           # Interactive strategy selector & alpha signal weights config
├── main.py                   # CLI runner: live dashboard, benchmark, replay, test-connection
├── core/
│   ├── orderbook.py          # L2 book manager (20 depth levels, weighted mid, spread, order counts)
│   └── trade_stream.py       # High-speed trade stream, rolling CVD, VPIN volume bucketizer
├── signals/
│   ├── base.py               # Abstract BaseSignal and SignalResult dataclass
│   ├── hedged_convexity.py   # Hedged Convexity (Defensive Maker Hedging & VPIN Toxicity Shield)
│   ├── convexity_cascade.py  # Convexity Cascade (Liquidity Hole & Depth Curvature)
│   ├── momentum_expansion.py # Momentum Expansion (QDAP + CVD Impulse + Trend Alignment)
│   ├── qdap.py               # Queue Depletion & Asymmetric Pressure (Touch Exhaustion & Anti-Spoofing)
│   ├── wobi.py               # Multi-level WOBI with order concentration anti-spoofing
│   ├── voi.py                # Volume Order Imbalance (Cont-Kukanov-Stoikov)
│   ├── microprice.py         # Stoikov Micro-Price estimator
│   ├── vpin.py               # Volume-Synchronized Probability of Toxicity
│   ├── absorption.py         # CVD-Price Divergence & Passive Absorption detector
│   ├── sweep.py              # Book sweep & replenishment elasticity detector
│   └── composite_alpha.py    # Multi-factor alpha ensemble with regime switching
├── engine/
│   ├── backtester.py         # Multi-horizon forward IC evaluator & live paper execution simulator
│   └── data_collector.py     # Real-time L2 recorder (JSONL) and high-speed offline replay engine
├── ui/
│   └── dashboard.py          # Rich interactive terminal dashboard
├── data/                     # Stored L2 book and trade tick recordings (partitioned by coin)
│   ├── btc/                  # BTC L2 recordings & snippets
│   ├── eth/                  # ETH L2 recordings
│   └── sol/                  # SOL L2 recordings & snippets
└── reports/                  # Generated edge evaluation markdown reports
```

---

## 3. How to Run the Engine

### A. Testnet & Network Connection Verification
Verify end-to-end REST API metadata, 20-level L2 order book depth, and WebSocket real-time streaming against Hyperliquid Testnet:
```powershell
# Default testnet verification (BTC)
python main.py testnet

# Mainnet (Live) verification
python main.py test-connection --mainnet

# Or test with specific coin on Mainnet (e.g. ETH, SOL)
python main.py test-connection --mainnet --coin ETH

# Programmatic Python connection test (Mainnet or Testnet)
python -c "from main import connect_mainnet; print('Mainnet Connected:', connect_mainnet('BTC'))"
python -c "from main import connect_testnet; print('Testnet Connected:', connect_testnet('BTC'))"
```

### B. Connecting Your Account (Testnet or Mainnet)
Inspect and verify your account balance, margin, positions, and API Agent authorization:
```powershell
# Verify account status on Testnet (default)
python main.py check-account

# Verify account status on Mainnet (Live)
python main.py check-account --mainnet

# Or inspect any wallet address directly on Mainnet
python main.py check-account --mainnet --account 0xYourMasterWalletAddress
```

To switch permanently to Mainnet without typing `--mainnet` on each command, set in `.env`:
```ini
HYPERLIQUID_TESTNET=false
```

### C. Live Interactive Dashboard (Paper Trading)
Connect to Hyperliquid's live WebSocket, stream L2 book depth, compute alpha signals, and monitor paper trading in real time:
```powershell
# Live paper trading dashboard on Hyperliquid Testnet (default)
python main.py live

# Live paper trading dashboard on Hyperliquid Mainnet (Live market data)
python main.py live --mainnet
```

### D. Live Order Execution (Real Orders on Exchange Book)
Broadcast real limit orders to the Hyperliquid order book when high-conviction signals trigger:
```powershell
# Run live engine with REAL Testnet order execution
python main.py live --live-orders --order-size 0.0005

# Run live engine with REAL Mainnet (Live) order execution
python main.py live --mainnet --live-orders --order-size 0.0005

# Manually place a test limit order on Mainnet (e.g. 5% below market)
python main.py place-order --mainnet --side BUY --price 80000 --order-size 0.0005

# Cancel all open orders for the asset on Mainnet
python main.py cancel-orders --mainnet
```

### E. Live Timed Benchmark & Statistical Edge Evaluation
Run a timed benchmark (e.g. 60 seconds) without terminal clutter, evaluate forward return predictability across horizons (1s, 3s, 5s, 10s, 30s, 60s), and generate a markdown report:
```powershell
python main.py benchmark --duration 60 --no-ui
```

### F. Selecting & Deselecting Strategies (Config File)
The engine provides a centralized [strategies.json](file:///E:/Hyperliquid/L2%20-%20Testnet/strategies.json) configuration file allowing you to enable or disable any execution strategy or alpha signal factor:

```powershell
# Inspect currently active and deselected strategies
python main.py strategies

# Run with a custom strategy configuration file
python main.py live --strategies-config my_custom_strategies.json

# Override active live execution strategy from CLI
python main.py live --live-orders --strategy WOBI_Maker
```

In `strategies.json`, simply toggle `"enabled": true` or `"enabled": false`:
```json
{
  "live_execution": {
    "active_strategy": "Composite_Maker",
    "order_size_btc": 0.0005
  },
  "execution_strategies": {
    "Composite_Maker": { "enabled": true, "execution_type": "MAKER", "entry_threshold": 0.35 },
    "AdaptiveML_Maker": { "enabled": true, "execution_type": "MAKER", "entry_threshold": 0.35 },
    "WOBI_Maker": { "enabled": true, "execution_type": "MAKER", "entry_threshold": 0.35 },
    "AdaptiveML_Taker": { "enabled": false },
    "Composite_Taker": { "enabled": false }
  },
  "alpha_signals": {
    "WOBI": { "enabled": true, "weight": 0.25 },
    "VOI": { "enabled": true, "weight": 0.25 },
    "MicroPrice": { "enabled": true, "weight": 0.20 },
    "Absorption": { "enabled": true, "weight": 0.15 },
    "VPIN": { "enabled": false }
  }
}
```

### G. Offline Replay on Recorded L2 Data
Replay any previously recorded L2 session at accelerated speed (e.g. 10x) to backtest and optimize parameters:
```powershell
python main.py replay --replay-file data/btc/hl_btc_l2_YYYYMMDD_HHMMSS.jsonl --speed 10
```

---

## 4. Trade Auditing & Session Tracking (Per-Strategy Auditability)

Every trade placed by any strategy (simulated paper trading or real Hyperliquid exchange execution) is strictly isolated and **individually auditable per trading session**.

### A. Audit Architecture & Directory Structure
Whenever a session runs (`live`, `benchmark`, or `replay`), the engine generates an immutable, timestamped session audit directory:

```
audits/
├── latest_session_id.txt                    # Pointer to most recent trading session
├── latest_session_all_trades.csv            # Symlink/copy of latest master trade log
├── latest_session_report.md                 # Symlink/copy of latest markdown audit report
└── session_YYYYMMDD_HHMMSS/                 # Dedicated directory for this trading session
    ├── session_manifest.json                # Complete session metadata, settings, & strategy stats
    ├── all_trades.csv                       # Master ledger containing all trades across all strategies
    ├── trades_audit.jsonl                   # High-frequency newline-delimited JSON audit event log
    ├── session_audit_report.md              # Formatted Markdown report with executive & strategy breakdown
    ├── live_orders.csv                      # (Live mode) Real Hyperliquid order submissions, fills & cancels
    └── strategies/                          # INDIVIDUAL STRATEGY AUDIT CSVs:
        ├── Composite_Maker.csv              # Every trade executed by Composite_Maker
        ├── AdaptiveML_Maker.csv             # Every trade executed by AdaptiveML_Maker
        ├── WOBI_Maker.csv                   # Every trade executed by WOBI_Maker
        ├── MicroPrice_Maker.csv             # Every trade executed by MicroPrice_Maker
        ├── Absorption_Fade.csv              # Every trade executed by Absorption_Fade
        ├── AdaptiveML_Taker.csv             # Every trade executed by AdaptiveML_Taker
        └── Composite_Taker.csv              # Every trade executed by Composite_Taker
```

### B. Recorded Trade Attributes
Every row in `all_trades.csv` and `strategies/{strategy_name}.csv` records 29 audit attributes:
- **Identification**: `trade_id` (e.g. `CM-0001`), `session_id`, `strategy_name`, `coin`, `network`, `is_live`
- **Execution**: `side` (`LONG`/`SHORT`), `execution_type` (`MAKER`/`SMART_TAKER`), `order_id`
- **Pricing & Sizing**: `entry_price`, `exit_price`, `size_btc`, `notional_usd`
- **Timing**: `entry_time` (ISO), `exit_time` (ISO), `holding_secs`
- **Microstructure Signals**: `entry_signal`, `exit_signal`
- **PnL & Fee Accounting**: `gross_pnl_usd`, `entry_fee_usd`, `exit_fee_usd`, `total_fees_usd` (negative = maker rebate, positive = taker fee paid), `net_pnl_usd`, `return_bps`
- **Execution Quality & Risk**: `exit_reason` (`TAKE_PROFIT`, `TRAILING_STOP`, `TIME_LIMIT`, `SIGNAL_REVERSAL`, `SESSION_SHUTDOWN`), `peak_mfe_bps` (Maximum Favorable Excursion), `trough_mae_bps` (Maximum Adverse Excursion), `strategy_equity_after`

### C. Interactive CLI Audit Commands
Inspect trading sessions and strategy audit logs directly from your terminal:

```powershell
# 1. List all historical trading sessions
python main.py audit

# 2. Inspect the latest session (executive breakdown + recent trades)
python main.py audit --session latest

# 3. Inspect a specific historical session
python main.py audit --session session_20260929_193713

# 4. Filter audit view to an individual strategy
python main.py audit --session latest --strategy Composite_Maker

# 5. Customize trade table display limit
python main.py audit --session latest --strategy WOBI_Maker --limit 100
```

---

## 5. Key Quantitative Insights on Hyperliquid BTC

1. **Information Coefficient (IC) Hierarchy**:
   - Short-horizon forward return predictability ($1s \le \Delta t \le 10s$) is strongly driven by **WOBI** ($IC \approx +0.34$ to $+0.89$) and **Stoikov Micro-Price** ($IC \approx +0.33$ to $+0.86$).
   - Persistent depth on Hyperliquid acts as a physical barrier: heavy bid depth prevents downward movement and creates asymmetric upward drift.
2. **The High-Frequency Fee Reality**:
   - Hyperliquid taker fees are 4.5 bps (VIP 0) and maker fees are 1.5 bps (3.0 bps round-trip). Over sub-15-second horizons, expected price movement is frequently smaller than round-trip fees.
   - For high-frequency capture, **maker strategies** that earn spread while using L2 signals to skew quote reservation prices represent the primary institutional edge.
   - For swing capture, **Momentum Expansion** captures 15–30 bps multi-minute expansions to comfortably clear round-trip fees with asymmetric reward-to-risk.

---

## 6. Full-Day Empirical Research (`hyperliquid-2026-08-12`) & Strategy Enhancements

A comprehensive 24-hour institutional dataset for BTC perpetuals (`hyperliquid-2026-08-12`) was investigated:
- **824,716 L2 book state changes** across 25 price/size/order-count levels (93.6 MB)
- **215,511 tick fills** ($1.697 Billion volume, 26,601 BTC)
- 99.7% exact price match against Hyperliquid's official historical L2 snapshots

### A. Empirical Information Coefficient (IC) Hierarchy Across 24 Hours
| Microstructure Feature | 5s IC | 15s IC | 30s IC | 60s IC | 120s IC | 300s IC |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`WOBI-25` (Decayed Depth Imbalance - 25 Levels)** | **+0.3083** | **+0.2910** | **+0.2652** | **+0.2106** | **+0.1535** | **+0.0848** |
| **`n_imb_25` (Order Count Imbalance - 25 Levels)** | **+0.3087** | **+0.2852** | **+0.2481** | **+0.2053** | **+0.1576** | **+0.0905** |
| **`MicroPrice Drift` (Stoikov Microprice)** | **+0.3009** | **+0.2753** | **+0.2458** | **+0.1953** | **+0.1421** | **+0.0771** |
| **`imb_l1` (Touch Queue Exhaustion)** | **+0.2961** | **+0.2817** | **+0.2552** | **+0.2031** | **+0.1483** | **+0.0790** |
| **`imb_6_15` (Intermediate Depth)** | **+0.2112** | **+0.1929** | **+0.1759** | **+0.1382** | **+0.1078** | **+0.0612** |
| **`imb_16_25` (Deep Resting Book)** | **+0.1624** | **+0.1400** | **+0.1201** | **+0.0936** | **+0.0555** | **+0.0200** |
| **`Raw CVD 15s` (Taker Volume Alone)** | -0.0292 | -0.0412 | -0.0087 | -0.0044 | -0.0311 | -0.0265 |

### B. Discovery: The Institutional "Absorption Trap"
Raw taker order flow (CVD) alone exhibits negative correlation because retail market orders frequently buy directly into resting institutional limit ask walls, leading to buyer exhaustion and sharp downward reversals:
- **Ask Wall Absorption** (Ask Wall + Aggressive Buyer Flow): Price reverses **DOWN by -0.98 bps** within 30s (56.2% downward win rate).
- **Bid Wall Absorption** (Bid Wall + Aggressive Seller Flow): Price bounces **UP by +0.54 bps** within 30s (54.4% upward win rate).
- **Bear Confluence** (Ask Wall + Aggressive Seller Flow): Price expands **DOWN by -1.41 bps** within 60s (61.8% win rate).
- **Bull Confluence** (Bid Wall + Aggressive Buyer Flow): Price expands **UP by +0.89 bps** within 60s (60.9% win rate).

### C. Upgrades to `Momentum_Expansion`
1. **25-Level Decayed Depth & Order Count Imbalance**: Incorporates the full 25-level book with exponential decay (`\lambda = 0.12`) and 25-level order count density (`n_imb_25`) to prevent phantom whale spoofing.
2. **Dual-Horizon CVD Acceleration**: Blends a 15-second acute sweep impulse (65%) with a 60-second volume trend baseline (35%).
3. **Active Absorption Trap Shield**: If aggressive taker buying encounters an opposing ask wall (`WOBI < -0.15`), the engine actively vetoes long entries (avoiding top-of-book exhaustion traps).
4. **Calibrated Holding & Asymmetric Exits**: Calibrated to 25.0 bps Take Profit, 12.0 bps Stop Loss, 10.0 bps Trailing Stop Activation, 4.0 bps Trailing Distance, and 300s holding limit.

### D. Runtime Dual-Granularity Order Book Pulling (`nSigFigs=4`)
By default, Hyperliquid provides 20 levels at 1-tick ($1) granularity, spanning only ~$19 (0.02% of BTC price). The engine now supports runtime multi-depth pulling:
- **Granular 1-Tick Book** (`nSigFigs: None`): 20 levels, 1-tick resolution ($19 span) for touch queue, microprice, and immediate execution pricing.
- **Deep Macro Book** (`nSigFigs: 4`): 20 levels, $10 interval resolution ($190-$250+ span, ~25-30 bps) for macro wall detection and structural liquidity tracking.
- **Parquet Archive Replay**: `L2ReplayEngine` now natively streams directly from parquet directories (e.g. `hyperliquid-2026-08-12`) at adjustable playback speed (`--replay-file hyperliquid-2026-08-12 --speed 1000`).
