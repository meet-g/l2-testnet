"""Configuration module for Hyperliquid L2 Microstructure Alpha Engine."""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class AccountConfig:
    """Hyperliquid wallet and API Agent credentials."""
    account_address: str = field(
        default_factory=lambda: os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS", os.getenv("HL_ACCOUNT_ADDRESS", "")).strip()
    )
    secret_key: str = field(
        default_factory=lambda: os.getenv("HYPERLIQUID_SECRET_KEY", os.getenv("HL_SECRET_KEY", "")).strip()
    )
    is_agent: bool = True  # True if secret_key belongs to an authorized API agent

    @property
    def has_account(self) -> bool:
        return bool(self.account_address and self.account_address.startswith("0x") and len(self.account_address) == 42)

    @property
    def has_secret(self) -> bool:
        return bool(self.secret_key and len(self.secret_key.strip()) >= 64)


@dataclass
class HyperliquidConfig:
    # API endpoints
    MAINNET_WS_URL: str = "wss://api.hyperliquid.xyz/ws"
    MAINNET_REST_URL: str = "https://api.hyperliquid.xyz/info"
    MAINNET_EXCHANGE_URL: str = "https://api.hyperliquid.xyz/exchange"
    TESTNET_WS_URL: str = "wss://api.hyperliquid-testnet.xyz/ws"
    TESTNET_REST_URL: str = "https://api.hyperliquid-testnet.xyz/info"
    TESTNET_EXCHANGE_URL: str = "https://api.hyperliquid-testnet.xyz/exchange"
    
    use_testnet: bool = field(
        default_factory=lambda: os.getenv("HYPERLIQUID_TESTNET", "true").strip().lower() not in ("false", "0", "no", "mainnet")
    )
    
    @property
    def ws_url(self) -> str:
        return self.TESTNET_WS_URL if self.use_testnet else self.MAINNET_WS_URL

    @property
    def rest_url(self) -> str:
        return self.TESTNET_REST_URL if self.use_testnet else self.MAINNET_REST_URL

    @property
    def exchange_url(self) -> str:
        return self.TESTNET_EXCHANGE_URL if self.use_testnet else self.MAINNET_EXCHANGE_URL

    @property
    def network_name(self) -> str:
        return "Testnet" if self.use_testnet else "Mainnet"


@dataclass
class MarketConfig:
    coin: str = "BTC"
    depth_levels: int = 25  # Extended order book depth (up to 25 levels)
    subscribe_macro_book: bool = False  # Disabled by default in live trading to prevent WebSocket channel collisions
    macro_sig_figs: int = 4  # nSigFigs for macro order book subscription (4 = $10 buckets on BTC)
    tick_size: float = 1.0  # Hyperliquid BTC tick size is $1.00
    lot_size: float = 0.0001  # Minimum BTC order size fraction
    
    # Real On-Chain Fee Schedule (Hyperliquid VIP 0 Tier from account 0x76cf...2ff)
    # Verified directly against live fills: 1.5000 bps Maker fee, 4.5000 bps Taker fee
    taker_fee_bps: float = 4.5  # 0.0450% real live taker fee
    maker_fee_bps: float = 1.5  # 0.0150% real live maker fee (positive = fee paid)
    maker_rebate_bps: float = 1.5  # Positive fee paid on standard VIP 0 tier


@dataclass
class SignalConfig:
    # 1. Multi-Level Weighted Order Book Imbalance (WOBI)
    wobi_decay_lambda: float = 0.35  # Exponential weight decay factor: exp(-lambda * level)
    wobi_depth_tiers: List[int] = field(default_factory=lambda: [1, 5, 10, 20])
    whale_min_sz_btc: float = 5.0  # Level with >= 5.0 BTC considered a potential wall
    whale_concentration_threshold: float = 2.0  # sz / n >= 2.0 BTC per order = whale concentration
    
    # 2. Volume Order Imbalance (VOI)
    voi_rolling_window_secs: float = 10.0
    voi_zscore_window: int = 60
    
    # 3. Stoikov Micro-Price
    microprice_adj_factor: float = 0.5  # Weight factor on imbalance drift
    
    # 4. Volume-Synchronized Probability of Toxicity (VPIN)
    vpin_bucket_size_btc: float = 5.0  # Volume per bucket (BTC)
    vpin_window_buckets: int = 30  # Number of buckets for rolling VPIN
    vpin_toxic_threshold: float = 0.60  # Above 0.60 is high toxic flow (adverse selection danger)
    
    # 5. Cumulative Volume Delta (CVD) & Absorption
    cvd_window_secs: float = 30.0
    cvd_zscore_threshold: float = 2.0
    absorption_ratio_threshold: float = 2.5  # Delta volume / Price movement divergence ratio
    
    # 6. Book Sweep & Elasticity
    sweep_min_levels: int = 2  # Consuming >= 2 price levels in single trade burst
    sweep_min_sz_btc: float = 1.5
    replenishment_eval_ms: int = 500  # Evaluate book recovery within 500ms
    
    # 7. Composite Alpha Ensemble Weights
    weight_wobi: float = 0.25
    weight_voi: float = 0.25
    weight_microprice: float = 0.20
    weight_cvd_absorption: float = 0.15
    weight_vpin_toxic: float = 0.15
    weight_vpin: float = 0.15
    weight_qdap: float = 0.25

    # 8. Queue Replenishment Latency & Dynamic Asymmetry (QRLA)
    qr_kappa_touch_btc: float = 0.05
    qr_kappa_multi_btc: float = 0.10
    qr_kappa_lat: float = 2.0
    qr_depletion_threshold: float = 0.30
    qr_baseline_window: int = 30
    qr_cvd_window_secs: float = 15.0
    qr_cvd_scale_btc: float = 2.0
    qr_min_flow_hurdle: float = 0.18
    qr_trend_window_secs: float = 120.0
    qr_trend_scale_bps: float = 6.0
    qr_w_rep1: float = 0.40
    qr_w_rep3: float = 0.30
    qr_w_lat: float = 0.15
    qr_w_canc: float = 0.15


@dataclass
class BacktestConfig:
    # Evaluation horizons in seconds for forward return information coefficient (IC)
    horizons_seconds: List[int] = field(default_factory=lambda: [1, 3, 5, 10, 30, 60])
    
    # Simulation trade sizing
    initial_cash_usd: float = 10_000.0
    order_size_btc: float = 0.1
    max_position_btc: float = 0.5
    
    # Execution modes: 'MAKER' (spread capture + rebate) or 'SMART_TAKER' (dislocation with trailing stop)
    default_execution_mode: str = "MAKER"
    slippage_bps: float = 0.2  # Realistic top-of-book slippage for 0.1 BTC on liquid BTC-PERP
    max_spread_bps: float = 1.5  # Reject entries when spread exceeds 1.5 bps
    
    # -------------------------------------------------------------------------
    # 1. Passive Maker Execution (Avellaneda-Stoikov Micro-Scalp)
    # Pays 1.5 bps maker fee per fill (3.0 bps round-trip on standard VIP 0 tier)
    # -------------------------------------------------------------------------
    entry_threshold: float = 0.35  # Conviction score threshold for maker quoting
    take_profit_bps: float = 5.0   # Take profit calibrated to clear 3.0 bps round-trip maker fee (+2.0 bps net edge)
    stop_loss_bps: float = 5.0     # Stop loss at -5 bps
    trailing_stop_activation_bps: float = 3.5  # Only activate trailing stop once in the green net of 3 bps fee
    trailing_stop_distance_bps: float = 1.5    # Trail 1.5 bps behind peak
    exit_reversal_threshold: float = 0.35      # Require meaningful reversal conviction to avoid fee churn
    max_holding_time_secs: int = 45            # Fast turnover allowing sufficient time for queue expansion

    # -------------------------------------------------------------------------
    # 2. Smart Taker Execution (High-Conviction Momentum & Breakout)
    # Pays 4.5 bps taker fee; requires high expected drift and asymmetric targets
    # -------------------------------------------------------------------------
    entry_threshold_taker: float = 0.50         # Strict hurdle: only enter on major dislocation/sweep
    take_profit_bps_taker: float = 12.0         # +12.0 bps move to clear fee hurdle
    stop_loss_bps_taker: float = 8.0            # -8.0 bps stop loss
    trailing_stop_activation_bps_taker: float = 7.0  # Only activate AFTER beating round-trip fee hurdle
    trailing_stop_distance_bps_taker: float = 3.0    # Trail 3 bps from peak
    exit_reversal_threshold_taker: float = 0.40      # Higher threshold for reversal
    max_holding_time_secs_taker: int = 60            # Allow 60s for momentum expansion
    taker_exit_as_maker_on_tp: bool = True           # Post passive limit order on Take Profit (pays 1.5 bps maker fee instead of 4.5 bps)


DEFAULT_STRATEGIES_JSON = {
    "_comment": "Hyperliquid L2 Microstructure Alpha Engine - Strategy & Signal Configuration",
    "_instructions": "Set 'enabled': true or false to select/deselect any execution strategy or alpha signal.",
    "version": "1.0",
    "live_execution": {
        "_comment": "Configuration for live exchange execution when running with --live-orders",
        "active_strategy": "Composite_Maker",
        "order_size_btc": 0.0005,
        "max_position_btc": 0.05,
    },
    "execution_strategies": {
        "Hedged_Convexity": {
            "enabled": True,
            "description": "Multi-tier order book convexity with automated defensive maker hedging on adverse toxic flow and liquidity wall decay",
            "signal_key": "HedgedConvexity",
            "execution_type": "HEDGED_MAKER",
            "entry_threshold": 0.86,
            "order_size_btc": 0.1,
            "take_profit_bps": 18.0,
            "stop_loss_bps": 12.0,
            "trailing_stop_activation_bps": 3.5,
            "trailing_stop_distance_bps": 1.2,
            "hedge_trigger_loss_bps": -5.5,
            "hedge_reversal_threshold": -0.40,
            "max_holding_time_secs": 180,
            "exit_reversal_threshold": 0.85,
            "min_volatility_bps": 4.5,
            "loss_cooldown_secs": 60,
            "coentry_group": "triad",
        },
        "Convexity_Cascade": {
            "enabled": True,
            "description": "Multi-tier order book convexity and liquidity hole cascade with order count dispersion and trade flow impulse",
            "signal_key": "ConvexityCascade",
            "execution_type": "HEDGED_MAKER",
            "entry_threshold": 0.75,
            "order_size_btc": 0.1,
            "take_profit_bps": 18.0,
            "stop_loss_bps": 12.0,
            "trailing_stop_activation_bps": 4.5,
            "trailing_stop_distance_bps": 1.5,
            "hedge_trigger_loss_bps": -5.5,
            "hedge_reversal_threshold": -0.45,
            "max_holding_time_secs": 120,
            "exit_reversal_threshold": 0.85,
            "loss_cooldown_secs": 60,
            "coentry_group": "triad",
        },
        "Momentum_Expansion": {
            "enabled": True,
            "description": "Multi-minute structural trend expansion entering on order book queue exhaustion, 25-level depth support, and CVD acceleration with absorption trap shielding",
            "signal_key": "MomentumExpansion",
            "execution_type": "HEDGED_MAKER",
            "entry_threshold": 0.75,
            "order_size_btc": 0.1,
            "take_profit_bps": 20.0,
            "stop_loss_bps": 12.0,
            "trailing_stop_activation_bps": 4.5,
            "trailing_stop_distance_bps": 1.5,
            "hedge_trigger_loss_bps": -5.5,
            "hedge_reversal_threshold": -0.45,
            "max_holding_time_secs": 120,
            "exit_reversal_threshold": 0.70,
            "loss_cooldown_secs": 60,
            "coentry_group": "triad",
        },
        "Queue_Replenishment": {
            "enabled": True,
            "description": "Orthogonal queue replenishment dynamics with multi-tier cancellation asymmetry, depletion persistence, and defensive maker hedging",
            "signal_key": "QueueReplenishment",
            "execution_type": "HEDGED_MAKER",
            "entry_threshold": 0.985,
            "order_size_btc": 0.1,
            "take_profit_bps": 30.0,
            "stop_loss_bps": 8.0,
            "trailing_stop_activation_bps": 4.0,
            "trailing_stop_distance_bps": 1.5,
            "hedge_trigger_loss_bps": -3.5,
            "hedge_reversal_threshold": -0.15,
            "max_holding_time_secs": 180,
            "exit_reversal_threshold": 0.80,
            "min_volatility_bps": 4.5,
            "loss_cooldown_secs": 120,
            "coentry_group": "queue_replenishment",
        },
        "QDAP_Maker": {
            "enabled": True,
            "description": "Passive quoting targeting depleted queue imbalances with order count anti-spoofing",
            "signal_key": "QDAP",
            "execution_type": "MAKER",
            "entry_threshold": 0.35,
            "order_size_btc": 0.1,
        },
        "Composite_Maker": {
            "enabled": True,
            "description": "Passive Avellaneda-Stoikov spread capture and maker rebate quoting off Composite Alpha ensemble",
            "signal_key": "CompositeAlpha",
            "execution_type": "MAKER",
            "entry_threshold": 0.35,
            "order_size_btc": 0.1,
        },
        "AdaptiveML_Maker": {
            "enabled": True,
            "description": "Passive maker execution driven by machine-learning online feature drift prediction",
            "signal_key": "AdaptiveML",
            "execution_type": "MAKER",
            "entry_threshold": 0.35,
            "order_size_btc": 0.1,
        },
        "WOBI_Maker": {
            "enabled": True,
            "description": "Passive quoting biased by anti-spoofed Weighted Order Book Imbalance",
            "signal_key": "WOBI",
            "execution_type": "MAKER",
            "entry_threshold": 0.35,
            "order_size_btc": 0.1,
        },
        "MicroPrice_Maker": {
            "enabled": True,
            "description": "Passive quoting tracking Stoikov MicroPrice fair value drift",
            "signal_key": "MicroPrice",
            "execution_type": "MAKER",
            "entry_threshold": 0.35,
            "order_size_btc": 0.1,
        },
        "Absorption_Fade": {
            "enabled": True,
            "description": "Passive fade strategy entering when aggressive market orders are absorbed by resting limit walls",
            "signal_key": "Absorption",
            "execution_type": "MAKER",
            "entry_threshold": 0.30,
            "order_size_btc": 0.1,
        },
        "AdaptiveML_Taker": {
            "enabled": True,
            "description": "Aggressive market entry on strong ML model conviction with trailing stop",
            "signal_key": "AdaptiveML",
            "execution_type": "SMART_TAKER",
            "entry_threshold": 0.50,
            "order_size_btc": 0.1,
        },
        "Composite_Taker": {
            "enabled": True,
            "description": "Aggressive market entry on extreme multi-factor composite dislocation",
            "signal_key": "CompositeAlpha",
            "execution_type": "SMART_TAKER",
            "entry_threshold": 0.50,
            "order_size_btc": 0.1,
        },
    },
    "alpha_signals": {
        "QDAP": {
            "enabled": True,
            "weight": 0.25,
            "description": "Queue Depletion & Asymmetric Pressure (non-linear log touch exhaustion & order count anti-spoofing)",
        },
        "WOBI": {
            "enabled": True,
            "weight": 0.25,
            "description": "Weighted Order Book Imbalance (multi-tier decaying depth)",
        },
        "VOI": {
            "enabled": True,
            "weight": 0.25,
            "description": "Volume Order Imbalance (Cont-Kukanov-Stoikov delta queues)",
        },
        "MicroPrice": {
            "enabled": True,
            "weight": 0.20,
            "description": "Stoikov Micro-Price fair value drift estimator",
        },
        "Absorption": {
            "enabled": True,
            "weight": 0.15,
            "description": "CVD vs Price Divergence (Passive Limit Wall Absorption)",
        },
        "VPIN": {
            "enabled": True,
            "weight": 0.15,
            "description": "Volume-Synchronized Probability of Toxicity (Easley et al.)",
        },
        "Sweep": {
            "enabled": True,
            "description": "Aggressive multi-level book sweep and elasticity detector",
        },
        "AdaptiveML": {
            "enabled": True,
            "description": "Online adaptive machine learning model with real-time gradient updates",
        },
        "MomentumExpansion": {
            "enabled": True,
            "description": "Momentum Expansion (QDAP queue exhaustion + rolling CVD volume impulse + 2-min trend alignment)",
        },
        "ConvexityCascade": {
            "enabled": True,
            "description": "Order Book Convexity & Liquidity Hole Cascade (queue depletion + depth slope + hole vacuum + CVD impulse)",
        },
        "HedgedConvexity": {
            "enabled": True,
            "description": "Hedged Convexity Alpha (depth curvature + order count dispersion + dynamic VPIN toxicity shielding & defensive maker hedge triggers)",
        },
        "QueueReplenishment": {
            "enabled": True,
            "description": "Dynamic L1/L3 queue replenishment delta, multi-tier cancellation asymmetry, and trade depletion persistence",
        },
    },
}


@dataclass
class ExecutionStrategyConfig:
    name: str
    enabled: bool = True
    description: str = ""
    signal_key: str = "CompositeAlpha"
    execution_type: str = "MAKER"
    entry_threshold: float = 0.35
    order_size_btc: float = 0.1
    take_profit_bps: Optional[float] = None
    stop_loss_bps: Optional[float] = None
    trailing_stop_activation_bps: Optional[float] = None
    trailing_stop_distance_bps: Optional[float] = None
    max_holding_time_secs: Optional[int] = None
    exit_reversal_threshold: Optional[float] = None
    hedge_trigger_loss_bps: Optional[float] = None
    hedge_reversal_threshold: Optional[float] = None
    min_volatility_bps: Optional[float] = None
    loss_cooldown_secs: Optional[int] = None
    coentry_group: Optional[str] = None


@dataclass
class QueueReplenishmentConfig:
    """Configuration dataclass for Queue Replenishment execution strategy and signal hyperparameters."""
    # Execution strategy parameters
    enabled: bool = True
    description: str = "Orthogonal queue replenishment dynamics with multi-tier cancellation asymmetry, depletion persistence, and defensive maker hedging"
    signal_key: str = "QueueReplenishment"
    execution_type: str = "HEDGED_MAKER"
    entry_threshold: float = 0.985
    order_size_btc: float = 0.1
    take_profit_bps: float = 30.0
    stop_loss_bps: float = 8.0
    trailing_stop_activation_bps: float = 4.0
    trailing_stop_distance_bps: float = 1.5
    hedge_trigger_loss_bps: float = -3.5
    hedge_reversal_threshold: float = -0.15
    max_holding_time_secs: int = 180
    exit_reversal_threshold: float = 0.80
    min_volatility_bps: float = 4.5
    loss_cooldown_secs: int = 120
    coentry_group: str = "queue_replenishment"

    # Microstructure alpha hyperparameters
    kappa_touch_btc: float = 0.05
    kappa_multi_btc: float = 0.10
    kappa_lat: float = 2.0
    depletion_threshold: float = 0.30
    baseline_window: int = 30
    cvd_window_secs: float = 15.0
    cvd_scale_btc: float = 2.0
    min_flow_hurdle: float = 0.18
    trend_window_secs: float = 120.0
    trend_scale_bps: float = 6.0
    w_rep1: float = 0.40
    w_rep3: float = 0.30
    w_lat: float = 0.15
    w_canc: float = 0.15


@dataclass
class AlphaSignalConfig:
    name: str
    enabled: bool = True
    weight: float = 0.0
    description: str = ""


@dataclass
class LiveExecutionConfig:
    active_strategy: str = "Composite_Maker"
    order_size_btc: float = 0.0005
    max_position_btc: float = 0.05


@dataclass
class StrategiesConfig:
    """Manages strategy selection, enabling/disabling, and weight parameters from strategies.json."""
    filepath: str = "strategies.json"
    live_execution: LiveExecutionConfig = field(default_factory=LiveExecutionConfig)
    execution_strategies: Dict[str, ExecutionStrategyConfig] = field(default_factory=dict)
    alpha_signals: Dict[str, AlphaSignalConfig] = field(default_factory=dict)
    queue_replenishment: QueueReplenishmentConfig = field(default_factory=QueueReplenishmentConfig)

    @classmethod
    def load(cls, filepath: str = "strategies.json") -> "StrategiesConfig":
        if not os.path.exists(filepath):
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_STRATEGIES_JSON, f, indent=2)
            except Exception:
                pass
            raw_data = DEFAULT_STRATEGIES_JSON
        else:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
            except Exception:
                raw_data = DEFAULT_STRATEGIES_JSON

        # Parse live_execution
        live_raw = raw_data.get("live_execution", {})
        live_cfg = LiveExecutionConfig(
            active_strategy=live_raw.get("active_strategy", "Composite_Maker"),
            order_size_btc=float(live_raw.get("order_size_btc", 0.0005)),
            max_position_btc=float(live_raw.get("max_position_btc", 0.05)),
        )

        # Parse execution_strategies
        exec_strategies: Dict[str, ExecutionStrategyConfig] = {}
        defaults_exec = DEFAULT_STRATEGIES_JSON["execution_strategies"]
        exec_raw = raw_data.get("execution_strategies", defaults_exec)

        for s_name, s_info in exec_raw.items():
            fallback = defaults_exec.get(s_name, {})
            exec_strategies[s_name] = ExecutionStrategyConfig(
                name=s_name,
                enabled=bool(s_info.get("enabled", fallback.get("enabled", True))),
                description=str(s_info.get("description", fallback.get("description", ""))),
                signal_key=str(s_info.get("signal_key", fallback.get("signal_key", "CompositeAlpha"))),
                execution_type=str(s_info.get("execution_type", fallback.get("execution_type", "MAKER"))),
                entry_threshold=float(s_info.get("entry_threshold", fallback.get("entry_threshold", 0.35))),
                order_size_btc=float(s_info.get("order_size_btc", fallback.get("order_size_btc", 0.1))),
                take_profit_bps=float(s_info["take_profit_bps"]) if "take_profit_bps" in s_info else fallback.get("take_profit_bps"),
                stop_loss_bps=float(s_info["stop_loss_bps"]) if "stop_loss_bps" in s_info else fallback.get("stop_loss_bps"),
                trailing_stop_activation_bps=float(s_info["trailing_stop_activation_bps"]) if "trailing_stop_activation_bps" in s_info else fallback.get("trailing_stop_activation_bps"),
                trailing_stop_distance_bps=float(s_info["trailing_stop_distance_bps"]) if "trailing_stop_distance_bps" in s_info else fallback.get("trailing_stop_distance_bps"),
                max_holding_time_secs=int(s_info["max_holding_time_secs"]) if "max_holding_time_secs" in s_info else fallback.get("max_holding_time_secs"),
                exit_reversal_threshold=float(s_info["exit_reversal_threshold"]) if "exit_reversal_threshold" in s_info else fallback.get("exit_reversal_threshold"),
                hedge_trigger_loss_bps=float(s_info["hedge_trigger_loss_bps"]) if "hedge_trigger_loss_bps" in s_info else fallback.get("hedge_trigger_loss_bps"),
                hedge_reversal_threshold=float(s_info["hedge_reversal_threshold"]) if "hedge_reversal_threshold" in s_info else fallback.get("hedge_reversal_threshold"),
                min_volatility_bps=float(s_info["min_volatility_bps"]) if "min_volatility_bps" in s_info else fallback.get("min_volatility_bps"),
                loss_cooldown_secs=int(s_info["loss_cooldown_secs"]) if "loss_cooldown_secs" in s_info else fallback.get("loss_cooldown_secs"),
                coentry_group=str(s_info["coentry_group"]) if "coentry_group" in s_info else fallback.get("coentry_group"),
            )

        # Parse alpha_signals
        alpha_signals: Dict[str, AlphaSignalConfig] = {}
        defaults_alpha = DEFAULT_STRATEGIES_JSON["alpha_signals"]
        alpha_raw = raw_data.get("alpha_signals", defaults_alpha)

        for a_name, a_info in alpha_raw.items():
            fallback = defaults_alpha.get(a_name, {})
            alpha_signals[a_name] = AlphaSignalConfig(
                name=a_name,
                enabled=bool(a_info.get("enabled", fallback.get("enabled", True))),
                weight=float(a_info.get("weight", fallback.get("weight", 0.0))),
                description=str(a_info.get("description", fallback.get("description", ""))),
            )

        return cls(
            filepath=filepath,
            live_execution=live_cfg,
            execution_strategies=exec_strategies,
            alpha_signals=alpha_signals,
        )

    def is_strategy_enabled(self, name: str) -> bool:
        s = self.execution_strategies.get(name)
        return s.enabled if s else False

    def is_signal_enabled(self, name: str) -> bool:
        s = self.alpha_signals.get(name)
        return s.enabled if s else False

    def get_enabled_strategy_defs(self) -> Dict[str, Tuple[str, str]]:
        """Returns dict of {strategy_name: (signal_key, execution_type)} for enabled strategies."""
        return {
            s.name: (s.signal_key, s.execution_type)
            for s in self.execution_strategies.values()
            if s.enabled
        }

    def get_strategy_params(self) -> Dict[str, Dict[str, Any]]:
        """Returns dict of custom per-strategy parameters."""
        res = {}
        for s in self.execution_strategies.values():
            p = {
                "entry_threshold": s.entry_threshold,
                "order_size_btc": s.order_size_btc,
                "execution_type": s.execution_type,
                "signal_key": s.signal_key,
            }
            if s.take_profit_bps is not None:
                p["take_profit_bps"] = s.take_profit_bps
            if s.stop_loss_bps is not None:
                p["stop_loss_bps"] = s.stop_loss_bps
            if s.trailing_stop_activation_bps is not None:
                p["trailing_stop_activation_bps"] = s.trailing_stop_activation_bps
            if s.trailing_stop_distance_bps is not None:
                p["trailing_stop_distance_bps"] = s.trailing_stop_distance_bps
            if s.max_holding_time_secs is not None:
                p["max_holding_time_secs"] = s.max_holding_time_secs
            if s.exit_reversal_threshold is not None:
                p["exit_reversal_threshold"] = s.exit_reversal_threshold
            if s.hedge_trigger_loss_bps is not None:
                p["hedge_trigger_loss_bps"] = s.hedge_trigger_loss_bps
            if s.hedge_reversal_threshold is not None:
                p["hedge_reversal_threshold"] = s.hedge_reversal_threshold
            if s.min_volatility_bps is not None:
                p["min_volatility_bps"] = s.min_volatility_bps
            if s.loss_cooldown_secs is not None:
                p["loss_cooldown_secs"] = s.loss_cooldown_secs
            if hasattr(s, "coentry_group") and s.coentry_group is not None:
                p["coentry_group"] = s.coentry_group
            res[s.name] = p
        return res

    def get_enabled_signals_map(self) -> Dict[str, bool]:
        """Returns map of {signal_name: bool_is_enabled}."""
        return {s.name: s.enabled for s in self.alpha_signals.values()}

    def get_signal_weights(self) -> Dict[str, float]:
        """Returns normalized weights for all enabled alpha signals."""
        active = {s.name: s.weight for s in self.alpha_signals.values() if s.enabled and s.weight > 0}
        total = sum(active.values())
        if total > 0:
            return {k: v / total for k, v in active.items()}
        return active


@dataclass
class AppConfig:
    hyperliquid: HyperliquidConfig = field(default_factory=HyperliquidConfig)
    account: AccountConfig = field(default_factory=AccountConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    signals: SignalConfig = field(default_factory=SignalConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    strategies: StrategiesConfig = field(default_factory=lambda: StrategiesConfig.load("strategies.json"))
    queue_replenishment: QueueReplenishmentConfig = field(default_factory=QueueReplenishmentConfig)
    
    # Logging & storage
    data_dir: str = "data"
    log_dir: str = "logs"
    sample_rate_hz: float = 10.0  # Sampling frequency for engine loop

    @property
    def coin_data_dir(self) -> str:
        """Returns the coin-specific data directory (e.g. data/btc)."""
        return os.path.join(self.data_dir, self.market.coin.lower())

