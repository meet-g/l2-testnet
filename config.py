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


# Real On-Chain Fee Schedules on Hyperliquid
# 1. Standard Crypto Perps (Hyperliquid VIP 0 Tier)
CRYPTO_TAKER_FEE_BPS: float = 4.50   # 0.0450% real live taker fee
CRYPTO_MAKER_FEE_BPS: float = 1.50   # 0.0150% real live maker fee
CRYPTO_MAKER_REBATE_BPS: float = 1.50

# 2. Stocks & Equities listed under XYZ on Hyperliquid (e.g. SKHYNIX)
# Verified Hyperliquid XYZ fee tier: 0.0090% taker fee (0.90 bps) and 0.0030% maker fee (0.30 bps)
XYZ_STOCK_TAKER_FEE_BPS: float = 0.90   # 0.0090% taker fee
XYZ_STOCK_MAKER_FEE_BPS: float = 0.30   # 0.0030% maker fee
XYZ_STOCK_MAKER_REBATE_BPS: float = 0.30

# Known stock/equity symbols listed on Hyperliquid under XYZ
XYZ_STOCKS: Tuple[str, ...] = (
    "SKHYNIX",
    "SKHY",
    "SKHX",
    "XYZ",
    "XYZ100",
    "SAMSUNG",
    "NVDA",
    "TSLA",
    "AAPL",
    "MSFT",
    "PLTR",
    "AMZN",
    "GOOGL",
    "AMD",
    "COIN",
    "MSTR",
    "SPY",
    "QQQ",
    "META",
    "TSM",
    "BABA",
)


def canonicalize_coin_symbol(coin: str) -> str:
    """Canonicalizes asset ticker symbols to their exact on-chain Hyperliquid identifier.

    HIP-3 builder assets (e.g. XYZ equities) strictly require lowercase prefix 'xyz:'
    and uppercase asset ticker (e.g. 'xyz:SKHX', 'xyz:SKHY', 'xyz:NVDA').
    Passing uppercase 'XYZ:' or omitting the prefix for known XYZ stocks leads to WebSocket disconnection.

    SK Hynix contracts on Hyperliquid (Two distinct markets):
      1. Primary SK Hynix Equity Contract (KRX underlying, Mark ~$1,075, 24h Vol ~$600M+):
         - URL: 'https://app.hyperliquid.xyz/trade/xyz:SKHYNIX'
         - Frontend Display: 'SKHYNIX-USDC'
         - Hyperliquid On-Chain Ticker: 'xyz:SKHX'
         - Aliases: 'SKHYNIX', 'xyz:SKHYNIX', 'SKHYNIX-USDC', 'SKHX', 'xyz:SKHX', 'SKHX-USDC' -> 'xyz:SKHX'

      2. SK Hynix American Depositary Shares (ADS) Contract (Mark ~$154, 24h Vol ~$160M+):
         - URL: 'https://app.hyperliquid.xyz/trade/xyz:SKHY'
         - Frontend Display: 'SKHY-USDC'
         - Hyperliquid On-Chain Ticker: 'xyz:SKHY'
         - Aliases: 'SKHY', 'xyz:SKHY', 'SKHY-USDC', 'SKHY-PERP' -> 'xyz:SKHY'

    Also extracts tickers from full trading URLs and strips quote suffixes (-USDC, /USDC, -PERP, etc.).
    """
    if not coin:
        return "BTC"

    c = coin.strip().strip("'\"")

    # 1. Clean URLs (e.g. https://app.hyperliquid.xyz/trade/xyz:SKHYNIX, trade.xyz, etc.)
    if "://" in c or "/trade/" in c or "trade.xyz" in c or "hyperliquid.xyz" in c:
        if "/trade/" in c:
            c = c.split("/trade/")[-1].split("?")[0].split("#")[0].strip("/")
        elif "/" in c:
            c = c.rstrip("/").split("/")[-1].split("?")[0].split("#")[0].strip()

    # 2. Extract DEX prefix if present (e.g. 'xyz:SKHY', 'xyz-SKHY', 'XYZ:SKHYNIX')
    c_upper = c.upper()
    has_xyz_prefix = False
    prefix = ""

    if c_upper.startswith("XYZ:") or c_upper.startswith("XYZ-") or c.lower().startswith("xyz:"):
        has_xyz_prefix = True
        prefix = "xyz:"
        c = c[4:].strip()
        c_upper = c.upper()
    elif ":" in c or "-" in c:
        # Check other builder DEX prefixes like flx:, vntl:, hyna:, etc.
        parts = c.split(":", 1) if ":" in c else c.split("-", 1)
        if len(parts) == 2 and parts[0].strip().lower() in ("flx", "vntl", "hyna", "km", "abcd", "cash", "para", "mkts", "io"):
            prefix = f"{parts[0].strip().lower()}:"
            c = parts[1].strip()
            c_upper = c.upper()

    # 3. Strip quote currency and contract suffixes (-USDC, /USDC, _USDC, -USD, -PERP, etc.)
    for sfx in (
        "-USDC", "/USDC", "_USDC", ":USDC",
        "-USD", "/USD", "_USD", ":USD",
        "-PERP", "/PERP", "_PERP", ":PERP",
        "-USDT", "/USDT", "_USDT", ":USDT",
        "-SPOT", "/SPOT", "_SPOT", ":SPOT",
    ):
        if c_upper.endswith(sfx):
            c_upper = c_upper[:-len(sfx)].strip()
            break

    # 4. Canonicalize known aliases
    # SK Hynix has two distinct contracts on Hyperliquid:
    # 1. SKHYNIX / SKHX (URL: xyz:SKHYNIX, UI: SKHYNIX-USDC) -> on-chain contract 'xyz:SKHX' (~$1,075 mark px)
    # 2. SKHY (URL: xyz:SKHY, UI: SKHY-USDC)                 -> on-chain contract 'xyz:SKHY' (~$154 mark px)
    if c_upper in ("SKHYNIX", "SK-HYNIX", "SK_HYNIX", "SKHX", "SK-HX", "SK_HX"):
        return "xyz:SKHX"
    if c_upper in ("SKHY", "SK-HY", "SK_HY"):
        return "xyz:SKHY"

    # If an explicit builder DEX prefix was passed
    if prefix:
        return f"{prefix}{c_upper}"
    if has_xyz_prefix:
        return f"xyz:{c_upper}"

    # Auto-prefix known XYZ stock tickers if passed directly (e.g. NVDA -> xyz:NVDA)
    if c_upper in XYZ_STOCKS:
        return f"xyz:{c_upper}"

    return c_upper


def is_xyz_stock_symbol(coin: str) -> bool:
    """Returns True if the coin symbol represents an XYZ-listed stock/equity on Hyperliquid."""
    if not coin:
        return False
    canon = canonicalize_coin_symbol(coin)
    return canon.startswith("xyz:")


@dataclass
class MarketConfig:
    coin: str = "BTC"
    depth_levels: int = 25  # Extended order book depth (up to 25 levels)
    subscribe_macro_book: bool = False  # Disabled by default in live trading to prevent WebSocket channel collisions
    macro_sig_figs: int = 4  # nSigFigs for macro order book subscription (4 = $10 buckets on BTC)
    tick_size: float = 1.0  # Hyperliquid BTC tick size is $1.00
    lot_size: float = 0.0001  # Minimum BTC order size fraction
    
    # Real On-Chain Fee Schedule
    taker_fee_bps: float = 4.5  # 0.0450% real live taker fee
    maker_fee_bps: float = 1.5  # 0.0150% real live maker fee (positive = fee paid)
    maker_rebate_bps: float = 1.5  # Positive fee paid on standard VIP 0 tier
    is_xyz_stock: bool = False

    @property
    def safe_coin(self) -> str:
        """Filesystem-safe coin identifier (replaces ':' with '_', e.g. 'xyz_SKHY')."""
        return self.coin.replace(":", "_")

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name == "coin" and hasattr(self, "taker_fee_bps") and value:
            canon = canonicalize_coin_symbol(str(value))
            if canon != value:
                super().__setattr__("coin", canon)
            if is_xyz_stock_symbol(canon):
                self.is_xyz_stock = True
                self.taker_fee_bps = XYZ_STOCK_TAKER_FEE_BPS
                self.maker_fee_bps = XYZ_STOCK_MAKER_FEE_BPS
                self.maker_rebate_bps = XYZ_STOCK_MAKER_REBATE_BPS
            elif hasattr(self, "is_xyz_stock") and not canon.startswith("xyz:"):
                self.is_xyz_stock = False
                self.taker_fee_bps = CRYPTO_TAKER_FEE_BPS
                self.maker_fee_bps = CRYPTO_MAKER_FEE_BPS
                self.maker_rebate_bps = CRYPTO_MAKER_FEE_BPS

    def __post_init__(self):
        if self.coin:
            self.coin = canonicalize_coin_symbol(self.coin)
        if self.coin and is_xyz_stock_symbol(self.coin):
            self.configure_for_coin(self.coin, is_stock=True)

    def configure_for_coin(
        self,
        coin: str,
        is_stock: Optional[bool] = None,
        taker_fee_bps: Optional[float] = None,
        maker_fee_bps: Optional[float] = None,
    ) -> None:
        """Configures market specifications and fee schedules for the designated asset.

        For XYZ stocks (such as SKHYNIX / xyz:SKHY):
            - Taker Fee: 0.0090% (0.90 bps)
            - Maker Fee: 0.0030% (0.30 bps)
            - Default tick size: $0.01
            - Default lot size: 1.0 share
        For Standard Crypto (such as BTC, ETH, SOL, HYPE):
            - Taker Fee: 0.0450% (4.50 bps)
            - Maker Fee: 0.0150% (1.50 bps)
        """
        canonical_coin = canonicalize_coin_symbol(coin)
        self.coin = canonical_coin
        if is_stock is not None:
            self.is_xyz_stock = bool(is_stock)
        else:
            self.is_xyz_stock = is_xyz_stock_symbol(self.coin)

        if self.is_xyz_stock:
            self.taker_fee_bps = XYZ_STOCK_TAKER_FEE_BPS if taker_fee_bps is None else float(taker_fee_bps)
            self.maker_fee_bps = XYZ_STOCK_MAKER_FEE_BPS if maker_fee_bps is None else float(maker_fee_bps)
            self.maker_rebate_bps = self.maker_fee_bps
            self.tick_size = 0.01
            self.lot_size = 1.0
        else:
            self.taker_fee_bps = CRYPTO_TAKER_FEE_BPS if taker_fee_bps is None else float(taker_fee_bps)
            self.maker_fee_bps = CRYPTO_MAKER_FEE_BPS if maker_fee_bps is None else float(maker_fee_bps)
            self.maker_rebate_bps = self.maker_fee_bps
            if self.coin == "BTC":
                self.tick_size = 1.0
                self.lot_size = 0.0001
            elif self.coin in ("ETH", "HYPE", "SOL"):
                self.tick_size = 0.01
                self.lot_size = 0.01


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
    capital_usd: Optional[float] = None
    capital_allocation_pct: float = 1.0
    
    # Execution modes: 'MAKER' (spread capture + rebate) or 'SMART_TAKER' (dislocation with trailing stop)
    default_execution_mode: str = "MAKER"
    slippage_bps: float = 0.2  # Realistic top-of-book slippage for 0.1 BTC on liquid BTC-PERP
    max_spread_bps: float = 1.5  # Reject entries when spread exceeds 1.5 bps
    priority_fee_bps: float = 0.0  # Hyperliquid write priority fee (Optimization 5) in basis points
    priority_fee_on_exit: bool = False  # Whether priority fee is also bid on exit orders
    force_market_orders: bool = False  # Forces all strategy entries and exits to use aggressive IOC market orders
    market_slippage_pct: float = 0.0005  # Slippage percentage for market orders (0.0005 = 0.05% = 5 bps)
    dynamic_slippage: bool = True  # Volatility-calibrated dynamic slippage modeling
    warmup_secs: float = 0.0  # Warmup wait time in seconds (0.0 for immediate backtests, >0 for live runner)
    
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


NEW_EXECUTION_STRATEGIES: Tuple[str, ...] = (
    "Hedged_Convexity",
    "Convexity_Cascade",
    "Momentum_Expansion",
    "Queue_Replenishment",
    "Stock_Microstructure_Alpha",
)

LEGACY_SCALPING_STRATEGIES: Tuple[str, ...] = (
    "QDAP_Maker",
    "Composite_Maker",
    "AdaptiveML_Maker",
    "WOBI_Maker",
    "MicroPrice_Maker",
    "MicroPrice_FastFill",
    "Absorption_Fade",
    "AdaptiveML_Taker",
    "Composite_Taker",
    "Instant_FastFill",
    "Dynamic_Spread_Scalper",
)

# Canonical aliases for program separation
CORE_EXECUTION_STRATEGIES: Tuple[str, ...] = NEW_EXECUTION_STRATEGIES
SCALPING_STRATEGIES: Tuple[str, ...] = LEGACY_SCALPING_STRATEGIES


DEFAULT_STRATEGIES_JSON = {
    "_comment": "Hyperliquid L2 Microstructure Alpha Engine - Strategy & Signal Configuration",
    "_instructions": "Execution Strategies contains the 4 new primary execution strategies (Hedged_Convexity, Convexity_Cascade, Momentum_Expansion, Queue_Replenishment). Scalping Strategies contains the older legacy micro-scalping strategies (QDAP_Maker, Composite_Maker, AdaptiveML_Maker, WOBI_Maker, MicroPrice_Maker, Absorption_Fade, AdaptiveML_Taker, Composite_Taker). Set 'enabled': true or false to select/deselect any strategy.",
    "version": "1.1",
    "live_execution": {
        "_comment": "Configuration for live exchange execution when running with --live-orders",
        "active_strategy": "Hedged_Convexity",
        "order_size_btc": 0.0005,
        "max_position_btc": 0.05,
        "penny_jumping": True,
        "use_ioc_on_marketable": True,
        "use_native_tpsl": True,
        "priority_fee_bps": 0.0,
        "force_market_orders": False,
        "market_slippage_pct": 0.0005,
        "warmup_secs": 10.0,
    },
    "execution_strategies": {
        "Hedged_Convexity": {
            "enabled": True,
            "description": "Multi-tier order book convexity with automated defensive maker hedging on adverse toxic flow and liquidity wall decay",
            "signal_key": "HedgedConvexity",
            "execution_type": "HEDGED_MAKER",
            "entry_threshold": 0.86,
            "order_size_btc": 0.1,
            "take_profit_bps": 20.0,
            "stop_loss_bps": 8.0,
            "trailing_stop_activation_bps": 5.0,
            "trailing_stop_distance_bps": 2.0,
            "hedge_trigger_loss_bps": -3.5,
            "hedge_reversal_threshold": 0.20,
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
            "entry_threshold": 0.80,
            "order_size_btc": 0.1,
            "take_profit_bps": 20.0,
            "stop_loss_bps": 8.0,
            "trailing_stop_activation_bps": 6.0,
            "trailing_stop_distance_bps": 2.5,
            "hedge_trigger_loss_bps": -4.0,
            "hedge_reversal_threshold": 0.15,
            "max_holding_time_secs": 180,
            "exit_reversal_threshold": 0.80,
            "min_volatility_bps": 4.5,
            "loss_cooldown_secs": 60,
            "coentry_group": "triad",
        },
        "Momentum_Expansion": {
            "enabled": True,
            "description": "Multi-minute structural trend expansion entering on order book queue exhaustion, 25-level depth support, and CVD acceleration with absorption trap shielding",
            "signal_key": "MomentumExpansion",
            "execution_type": "HEDGED_MAKER",
            "entry_threshold": 0.70,
            "order_size_btc": 0.1,
            "take_profit_bps": 20.0,
            "stop_loss_bps": 8.0,
            "trailing_stop_activation_bps": 5.0,
            "trailing_stop_distance_bps": 2.0,
            "hedge_trigger_loss_bps": -3.5,
            "hedge_reversal_threshold": 0.20,
            "max_holding_time_secs": 180,
            "exit_reversal_threshold": 0.65,
            "min_volatility_bps": 4.5,
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
            "trailing_stop_activation_bps": 3.5,
            "trailing_stop_distance_bps": 1.2,
            "hedge_trigger_loss_bps": -3.5,
            "hedge_reversal_threshold": -0.10,
            "max_holding_time_secs": 180,
            "exit_reversal_threshold": 0.80,
            "min_volatility_bps": 4.5,
            "loss_cooldown_secs": 120,
            "coentry_group": "queue_replenishment",
        },
        "Stock_Microstructure_Alpha": {
            "enabled": True,
            "description": "High-frequency microstructure alpha engineered specifically for Hyperliquid lower-fee stock pairs (XYZ equities), harvesting MicroPrice fair-value drift, 5-level depth imbalance, VOI delta queues, and tight fee-hurdle trailing ratchets",
            "signal_key": "StockMicrostructure",
            "execution_type": "HEDGED_MAKER",
            "price_offset": 0.01,
            "entry_threshold": 0.55,
            "order_size_btc": 10.0,
            "take_profit_bps": 7.0,
            "stop_loss_bps": 5.5,
            "trailing_stop_activation_bps": 1.8,
            "trailing_stop_distance_bps": 0.8,
            "max_holding_time_secs": 35,
            "exit_reversal_threshold": 0.20,
            "hedge_trigger_loss_bps": -3.5,
            "hedge_reversal_threshold": -0.15,
            "min_volatility_bps": 0.0,
            "loss_cooldown_secs": 30,
            "coentry_group": "stock_alpha",
            "trend_filter_enabled": True,
            "trend_window_secs": 60.0,
            "max_counter_trend_bps": 1.5,
        },
    },
    "scalping_strategies": {
        "QDAP_Maker": {
            "enabled": False,
            "description": "Passive quoting targeting depleted queue imbalances with order count anti-spoofing",
            "signal_key": "QDAP",
            "execution_type": "MAKER",
            "entry_threshold": 0.75,
            "order_size_btc": 0.1,
            "take_profit_bps": 18.0,
            "stop_loss_bps": 12.0,
            "trailing_stop_activation_bps": 2.5,
            "trailing_stop_distance_bps": 1.0,
            "max_holding_time_secs": 180,
            "min_volatility_bps": 3.8,
        },
        "Composite_Maker": {
            "enabled": False,
            "description": "Passive Avellaneda-Stoikov spread capture and maker rebate quoting off Composite Alpha ensemble",
            "signal_key": "CompositeAlpha",
            "execution_type": "MAKER",
            "entry_threshold": 0.75,
            "order_size_btc": 0.1,
            "take_profit_bps": 18.0,
            "stop_loss_bps": 12.0,
            "trailing_stop_activation_bps": 2.5,
            "trailing_stop_distance_bps": 1.0,
            "max_holding_time_secs": 180,
            "min_volatility_bps": 3.8,
        },
        "AdaptiveML_Maker": {
            "enabled": False,
            "description": "Passive maker execution driven by machine-learning online feature drift prediction",
            "signal_key": "AdaptiveML",
            "execution_type": "MAKER",
            "entry_threshold": 0.65,
            "order_size_btc": 0.1,
            "take_profit_bps": 18.0,
            "stop_loss_bps": 12.0,
            "trailing_stop_activation_bps": 2.5,
            "trailing_stop_distance_bps": 1.0,
            "max_holding_time_secs": 180,
            "min_volatility_bps": 3.8,
        },
        "WOBI_Maker": {
            "enabled": False,
            "description": "Passive quoting biased by anti-spoofed Weighted Order Book Imbalance",
            "signal_key": "WOBI",
            "execution_type": "MAKER",
            "entry_threshold": 0.75,
            "order_size_btc": 0.1,
            "take_profit_bps": 5.0,
            "stop_loss_bps": 8.0,
            "trailing_stop_activation_bps": 2.5,
            "trailing_stop_distance_bps": 1.0,
            "max_holding_time_secs": 180,
            "exit_reversal_threshold": 0.75,
            "min_volatility_bps": 3.8,
            "dynamic_tp_enabled": True,
            "dynamic_tp_spread_mult": 2.0,
            "dynamic_tp_vol_mult": 0.8,
            "dynamic_tp_min_bps": 2.5,
            "dynamic_tp_max_bps": 6.0,
            "exhaustion_exit_enabled": True,
            "exhaustion_min_gain_bps": 2.0,
            "exhaustion_score_threshold": 0.15,
            "require_cvd_alignment": True,
            "fast_fill_enabled": True,
            "exit_escalate_secs": 1.5,
            "emergency_slippage_pct": 0.0020,
            "trend_filter_enabled": True,
            "trend_window_secs": 60.0,
            "max_counter_trend_bps": 1.0,
            "tiered_trailing_ratchet": True,
            "loss_cooldown_secs": 30,
        },
        "MicroPrice_Maker": {
            "enabled": False,
            "description": "Passive quoting tracking Stoikov MicroPrice fair value drift",
            "signal_key": "MicroPrice",
            "execution_type": "MAKER",
            "entry_threshold": 0.75,
            "order_size_btc": 0.1,
            "take_profit_bps": 18.0,
            "stop_loss_bps": 12.0,
            "trailing_stop_activation_bps": 2.5,
            "trailing_stop_distance_bps": 1.0,
            "max_holding_time_secs": 180,
            "min_volatility_bps": 3.8,
            "trend_filter_enabled": True,
            "trend_window_secs": 60.0,
            "max_counter_trend_bps": 1.0,
            "require_cvd_alignment": True,
        },
        "MicroPrice_FastFill": {
            "enabled": False,
            "description": "High-confidence fast-filling Stoikov MicroPrice with multi-factor gating and defensive hedge",
            "signal_key": "MicroPrice",
            "execution_type": "MAKER",
            "entry_threshold": 0.80,
            "min_confidence": 0.75,
            "order_size_btc": 0.1,
            "take_profit_bps": 16.0,
            "stop_loss_bps": 12.0,
            "trailing_stop_activation_bps": 7.0,
            "trailing_stop_distance_bps": 2.0,
            "max_holding_time_secs": 120,
            "min_volatility_bps": 3.5,
            "exit_reversal_threshold": 0.75,
            "hedge_trigger_loss_bps": -6.0,
            "hedge_reversal_threshold": 0.10,
            "loss_cooldown_secs": 60,
            "fast_fill_enabled": True,
            "entry_escalate_secs": 6.0,
            "exit_escalate_secs": 3.0,
            "defensive_hedge_market": False,
            "trend_filter_enabled": True,
            "trend_window_secs": 60.0,
            "max_counter_trend_bps": 1.0,
            "require_cvd_alignment": True,
        },
        "Absorption_Fade": {
            "enabled": False,
            "description": "Passive fade strategy entering when aggressive market orders are absorbed by resting limit walls",
            "signal_key": "Absorption",
            "execution_type": "MAKER",
            "entry_threshold": 0.70,
            "order_size_btc": 0.1,
            "take_profit_bps": 18.0,
            "stop_loss_bps": 12.0,
            "trailing_stop_activation_bps": 2.5,
            "trailing_stop_distance_bps": 1.0,
            "max_holding_time_secs": 180,
            "min_volatility_bps": 3.8,
        },
        "AdaptiveML_Taker": {
            "enabled": False,
            "description": "Aggressive market entry on strong ML model conviction with trailing stop",
            "signal_key": "AdaptiveML",
            "execution_type": "SMART_TAKER",
            "entry_threshold": 0.75,
            "order_size_btc": 0.1,
            "take_profit_bps": 22.0,
            "stop_loss_bps": 12.0,
            "trailing_stop_activation_bps": 3.5,
            "trailing_stop_distance_bps": 1.2,
            "max_holding_time_secs": 120,
            "min_volatility_bps": 4.5,
        },
        "Composite_Taker": {
            "enabled": False,
            "description": "Aggressive market entry on extreme multi-factor composite dislocation",
            "signal_key": "CompositeAlpha",
            "execution_type": "SMART_TAKER",
            "entry_threshold": 0.80,
            "order_size_btc": 0.1,
            "take_profit_bps": 22.0,
            "stop_loss_bps": 12.0,
            "trailing_stop_activation_bps": 3.5,
            "trailing_stop_distance_bps": 1.2,
            "max_holding_time_secs": 120,
            "min_volatility_bps": 4.5,
        },
        "Instant_FastFill": {
            "enabled": False,
            "description": "Ultra-fast immediate marketable fill on opposing queue depletion with passive maker take-profit quoting and defensive hedge",
            "signal_key": "InstantFill",
            "execution_type": "SMART_TAKER",
            "entry_threshold": 0.70,
            "min_confidence": 0.65,
            "order_size_btc": 0.1,
            "take_profit_bps": 8.0,
            "stop_loss_bps": 10.0,
            "trailing_stop_activation_bps": 4.0,
            "trailing_stop_distance_bps": 1.5,
            "max_holding_time_secs": 90,
            "exit_reversal_threshold": 0.70,
            "hedge_trigger_loss_bps": -4.0,
            "hedge_reversal_threshold": 0.0,
            "min_volatility_bps": 3.0,
            "loss_cooldown_secs": 30,
            "fast_fill_enabled": True,
        },
        "Dynamic_Spread_Scalper": {
            "enabled": False,
            "description": "Adaptive variable take-profit maker scalping scaled off real-time spread, volatility, and order flow exhaustion",
            "signal_key": "DynamicSpread",
            "execution_type": "MAKER",
            "entry_threshold": 0.70,
            "order_size_btc": 0.1,
            "take_profit_bps": 6.5,
            "stop_loss_bps": 10.0,
            "trailing_stop_activation_bps": 3.0,
            "trailing_stop_distance_bps": 1.0,
            "max_holding_time_secs": 120,
            "min_volatility_bps": 2.5,
            "hedge_trigger_loss_bps": -4.0,
            "hedge_reversal_threshold": 0.0,
            "loss_cooldown_secs": 30,
            "dynamic_tp_enabled": True,
            "dynamic_tp_spread_mult": 2.0,
            "dynamic_tp_vol_mult": 0.8,
            "dynamic_tp_min_bps": 4.0,
            "dynamic_tp_max_bps": 12.0,
            "tiered_trailing_ratchet": True,
            "exhaustion_exit_enabled": True,
            "exhaustion_min_gain_bps": 3.0,
            "exhaustion_score_threshold": 0.15,
            "fast_fill_enabled": True,
            "exit_escalate_secs": 1.5,
            "emergency_slippage_pct": 0.0020,
            "trend_filter_enabled": True,
            "trend_window_secs": 60.0,
            "max_counter_trend_bps": 1.0,
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
        "InstantFill": {
            "enabled": True,
            "weight": 0.20,
            "description": "Flow Depletion, Queue Exhaustion, and Immediate Sweep alpha detector",
        },
        "DynamicSpread": {
            "enabled": True,
            "weight": 0.20,
            "description": "Dynamic spread capture, microprice flow impulse, and multi-tier queue exhaustion",
        },
        "StockMicrostructure": {
            "enabled": True,
            "weight": 0.0,
            "description": "Stock Microstructure Alpha (MicroPrice fair-value drift + D5 order book imbalance + VOI queue deltas + 10s CVD flow)",
        },
    },
}

DEFAULT_CORE_STRATEGIES_JSON = {
    "_comment": "Hyperliquid L2 Microstructure Alpha Engine - Core Execution Strategy Configuration",
    "_instructions": "Configuration for the 4 core execution strategies: Hedged_Convexity, Convexity_Cascade, Momentum_Expansion, Queue_Replenishment.",
    "version": "1.1",
    "program": "core_execution",
    "live_execution": {
        "active_strategy": "Hedged_Convexity",
        "order_size_btc": DEFAULT_STRATEGIES_JSON["live_execution"]["order_size_btc"],
        "max_position_btc": DEFAULT_STRATEGIES_JSON["live_execution"]["max_position_btc"],
        "penny_jumping": DEFAULT_STRATEGIES_JSON["live_execution"]["penny_jumping"],
        "use_ioc_on_marketable": DEFAULT_STRATEGIES_JSON["live_execution"]["use_ioc_on_marketable"],
        "use_native_tpsl": DEFAULT_STRATEGIES_JSON["live_execution"]["use_native_tpsl"],
        "priority_fee_bps": DEFAULT_STRATEGIES_JSON["live_execution"]["priority_fee_bps"],
        "force_market_orders": DEFAULT_STRATEGIES_JSON["live_execution"]["force_market_orders"],
        "market_slippage_pct": DEFAULT_STRATEGIES_JSON["live_execution"]["market_slippage_pct"],
        "warmup_secs": DEFAULT_STRATEGIES_JSON["live_execution"].get("warmup_secs", 10.0),
    },
    "execution_strategies": {
        k: dict(v) for k, v in DEFAULT_STRATEGIES_JSON["execution_strategies"].items()
        if k in NEW_EXECUTION_STRATEGIES
    },
    "alpha_signals": {
        k: dict(v) for k, v in DEFAULT_STRATEGIES_JSON["alpha_signals"].items()
        if k in ("HedgedConvexity", "ConvexityCascade", "MomentumExpansion", "QueueReplenishment", "StockMicrostructure", "VPIN", "VOI", "Absorption")
    },
}

DEFAULT_SCALPER_STRATEGIES_JSON = {
    "_comment": "Hyperliquid L2 Microstructure Alpha Engine - Scalping Strategy Configuration",
    "_instructions": "Configuration for the 11 high-frequency scalping strategies (maker & smart taker).",
    "version": "1.1",
    "program": "scalper",
    "live_execution": {
        "active_strategy": "Composite_Maker",
        "order_size_btc": DEFAULT_STRATEGIES_JSON["live_execution"]["order_size_btc"],
        "max_position_btc": DEFAULT_STRATEGIES_JSON["live_execution"]["max_position_btc"],
        "penny_jumping": DEFAULT_STRATEGIES_JSON["live_execution"]["penny_jumping"],
        "use_ioc_on_marketable": DEFAULT_STRATEGIES_JSON["live_execution"]["use_ioc_on_marketable"],
        "use_native_tpsl": DEFAULT_STRATEGIES_JSON["live_execution"]["use_native_tpsl"],
        "priority_fee_bps": DEFAULT_STRATEGIES_JSON["live_execution"]["priority_fee_bps"],
        "force_market_orders": DEFAULT_STRATEGIES_JSON["live_execution"]["force_market_orders"],
        "market_slippage_pct": DEFAULT_STRATEGIES_JSON["live_execution"]["market_slippage_pct"],
        "warmup_secs": DEFAULT_STRATEGIES_JSON["live_execution"].get("warmup_secs", 10.0),
    },
    "scalping_strategies": {
        k: dict(v) for k, v in DEFAULT_STRATEGIES_JSON.get("scalping_strategies", {}).items()
        if k in LEGACY_SCALPING_STRATEGIES
    },
    "alpha_signals": {
        k: dict(v) for k, v in DEFAULT_STRATEGIES_JSON["alpha_signals"].items()
        if k in ("WOBI", "VOI", "MicroPrice", "Absorption", "VPIN", "Sweep", "AdaptiveML", "CompositeAlpha", "InstantFill", "DynamicSpread", "QDAP")
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
    price_offset: Optional[float] = None
    price_concession: Optional[float] = None
    exit_concession: Optional[float] = None
    price_concession_ratio: Optional[float] = None
    exit_concession_ratio: Optional[float] = None
    fast_fill_enabled: Optional[bool] = None
    entry_escalate_secs: Optional[float] = None
    exit_escalate_secs: Optional[float] = None
    defensive_hedge_market: Optional[bool] = None
    min_confidence: Optional[float] = None
    coentry_group: Optional[str] = None
    trend_filter_enabled: Optional[bool] = None
    trend_window_secs: Optional[float] = None
    max_counter_trend_bps: Optional[float] = None
    require_cvd_alignment: Optional[bool] = None
    dynamic_tp_enabled: Optional[bool] = None
    dynamic_tp_spread_mult: Optional[float] = None
    dynamic_tp_vol_mult: Optional[float] = None
    dynamic_tp_min_bps: Optional[float] = None
    dynamic_tp_max_bps: Optional[float] = None
    tiered_trailing_ratchet: Optional[bool] = None
    exhaustion_exit_enabled: Optional[bool] = None
    exhaustion_min_gain_bps: Optional[float] = None
    exhaustion_score_threshold: Optional[float] = None
    emergency_slippage_pct: Optional[float] = None
    is_scalping: bool = False


@dataclass
class ScalpingStrategyConfig(ExecutionStrategyConfig):
    """Configuration dataclass specifically for legacy micro-scalping strategies."""
    is_scalping: bool = True


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
    trailing_stop_activation_bps: float = 3.5
    trailing_stop_distance_bps: float = 1.2
    hedge_trigger_loss_bps: float = -3.5
    hedge_reversal_threshold: float = -0.10
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
    penny_jumping: bool = True
    use_ioc_on_marketable: bool = True
    use_native_tpsl: bool = True
    priority_fee_bps: float = 0.0
    force_market_orders: bool = False
    market_slippage_pct: float = 0.0005
    warmup_secs: float = 10.0


@dataclass
class StrategiesConfig:
    """Manages strategy selection, enabling/disabling, and weight parameters from strategies.json.
    
    Provides explicit distinction between the 4 new primary execution strategies
    (Hedged_Convexity, Convexity_Cascade, Momentum_Expansion, Queue_Replenishment)
    and older legacy scalping strategies (QDAP_Maker, Composite_Maker, AdaptiveML_Maker, etc.).
    """
    filepath: str = "strategies.json"
    live_execution: LiveExecutionConfig = field(default_factory=LiveExecutionConfig)
    execution_strategies: Dict[str, ExecutionStrategyConfig] = field(default_factory=dict)
    scalping_strategies: Dict[str, ScalpingStrategyConfig] = field(default_factory=dict)
    alpha_signals: Dict[str, AlphaSignalConfig] = field(default_factory=dict)
    queue_replenishment: QueueReplenishmentConfig = field(default_factory=QueueReplenishmentConfig)

    @property
    def program_name(self) -> str:
        return "unified"

    @classmethod
    def load(cls, filepath: str = "strategies.json") -> "StrategiesConfig":
        if cls is CoreStrategiesConfig:
            return CoreStrategiesConfig._load_core(filepath)
        if cls in (ScalperStrategiesConfig, ScalpingStrategiesConfig):
            return ScalperStrategiesConfig._load_scalper(filepath)

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

        # Auto-dispatch based on filename or program metadata
        fname = os.path.basename(filepath).lower()
        if raw_data.get("program") == "core_execution" or (fname.startswith("strategies_core") and fname.endswith(".json")):
            return CoreStrategiesConfig._load_core(filepath, raw_data=raw_data)
        if raw_data.get("program") in ("scalper", "scalping") or (fname.startswith("strategies_scalp") and fname.endswith(".json")):
            return ScalperStrategiesConfig._load_scalper(filepath, raw_data=raw_data)

        # Parse live_execution
        live_raw = raw_data.get("live_execution", {})
        live_cfg = LiveExecutionConfig(
            active_strategy=live_raw.get("active_strategy", "Hedged_Convexity"),
            order_size_btc=float(live_raw.get("order_size_btc", 0.0005)),
            max_position_btc=float(live_raw.get("max_position_btc", 0.05)),
            penny_jumping=bool(live_raw.get("penny_jumping", True)),
            use_ioc_on_marketable=bool(live_raw.get("use_ioc_on_marketable", True)),
            use_native_tpsl=bool(live_raw.get("use_native_tpsl", True)),
            priority_fee_bps=float(live_raw.get("priority_fee_bps", 0.0)),
            force_market_orders=bool(live_raw.get("force_market_orders", False)),
            market_slippage_pct=float(live_raw.get("market_slippage_pct", 0.01)),
            warmup_secs=float(live_raw.get("warmup_secs", 10.0)),
        )

        def _parse_strat_item(s_name: str, s_info: dict, fallback: dict, is_scalp: bool = False) -> ExecutionStrategyConfig:
            cfg_cls = ScalpingStrategyConfig if is_scalp else ExecutionStrategyConfig
            return cfg_cls(
                name=s_name,
                enabled=bool(s_info.get("enabled", fallback.get("enabled", False))),
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
                price_offset=float(s_info["price_offset"]) if "price_offset" in s_info else fallback.get("price_offset"),
                price_concession=float(s_info["price_concession"]) if "price_concession" in s_info else fallback.get("price_concession"),
                exit_concession=float(s_info["exit_concession"]) if "exit_concession" in s_info else fallback.get("exit_concession"),
                price_concession_ratio=float(s_info["price_concession_ratio"]) if "price_concession_ratio" in s_info else fallback.get("price_concession_ratio"),
                exit_concession_ratio=float(s_info["exit_concession_ratio"]) if "exit_concession_ratio" in s_info else fallback.get("exit_concession_ratio"),
                fast_fill_enabled=bool(s_info["fast_fill_enabled"]) if "fast_fill_enabled" in s_info else fallback.get("fast_fill_enabled"),
                entry_escalate_secs=float(s_info["entry_escalate_secs"]) if "entry_escalate_secs" in s_info else fallback.get("entry_escalate_secs"),
                exit_escalate_secs=float(s_info["exit_escalate_secs"]) if "exit_escalate_secs" in s_info else fallback.get("exit_escalate_secs"),
                defensive_hedge_market=bool(s_info["defensive_hedge_market"]) if "defensive_hedge_market" in s_info else fallback.get("defensive_hedge_market"),
                min_confidence=float(s_info["min_confidence"]) if "min_confidence" in s_info else fallback.get("min_confidence"),
                coentry_group=str(s_info["coentry_group"]) if "coentry_group" in s_info else fallback.get("coentry_group"),
                trend_filter_enabled=bool(s_info["trend_filter_enabled"]) if "trend_filter_enabled" in s_info else fallback.get("trend_filter_enabled"),
                trend_window_secs=float(s_info["trend_window_secs"]) if "trend_window_secs" in s_info else fallback.get("trend_window_secs"),
                max_counter_trend_bps=float(s_info["max_counter_trend_bps"]) if "max_counter_trend_bps" in s_info else fallback.get("max_counter_trend_bps"),
                require_cvd_alignment=bool(s_info["require_cvd_alignment"]) if "require_cvd_alignment" in s_info else fallback.get("require_cvd_alignment"),
                dynamic_tp_enabled=bool(s_info["dynamic_tp_enabled"]) if "dynamic_tp_enabled" in s_info else fallback.get("dynamic_tp_enabled"),
                dynamic_tp_spread_mult=float(s_info["dynamic_tp_spread_mult"]) if "dynamic_tp_spread_mult" in s_info else fallback.get("dynamic_tp_spread_mult"),
                dynamic_tp_vol_mult=float(s_info["dynamic_tp_vol_mult"]) if "dynamic_tp_vol_mult" in s_info else fallback.get("dynamic_tp_vol_mult"),
                dynamic_tp_min_bps=float(s_info["dynamic_tp_min_bps"]) if "dynamic_tp_min_bps" in s_info else fallback.get("dynamic_tp_min_bps"),
                dynamic_tp_max_bps=float(s_info["dynamic_tp_max_bps"]) if "dynamic_tp_max_bps" in s_info else fallback.get("dynamic_tp_max_bps"),
                tiered_trailing_ratchet=bool(s_info["tiered_trailing_ratchet"]) if "tiered_trailing_ratchet" in s_info else fallback.get("tiered_trailing_ratchet"),
                exhaustion_exit_enabled=bool(s_info["exhaustion_exit_enabled"]) if "exhaustion_exit_enabled" in s_info else fallback.get("exhaustion_exit_enabled"),
                exhaustion_min_gain_bps=float(s_info["exhaustion_min_gain_bps"]) if "exhaustion_min_gain_bps" in s_info else fallback.get("exhaustion_min_gain_bps"),
                exhaustion_score_threshold=float(s_info["exhaustion_score_threshold"]) if "exhaustion_score_threshold" in s_info else fallback.get("exhaustion_score_threshold"),
                emergency_slippage_pct=float(s_info["emergency_slippage_pct"]) if "emergency_slippage_pct" in s_info else fallback.get("emergency_slippage_pct"),
                is_scalping=is_scalp,
            )

        # Parse execution_strategies (The 4 New Primary Execution Strategies)
        exec_strategies: Dict[str, ExecutionStrategyConfig] = {}
        defaults_exec = DEFAULT_STRATEGIES_JSON["execution_strategies"]
        exec_raw = raw_data.get("execution_strategies", defaults_exec)

        # Parse scalping_strategies (Legacy Scalping Strategies)
        scalp_strategies: Dict[str, ScalpingStrategyConfig] = {}
        defaults_scalp = DEFAULT_STRATEGIES_JSON.get("scalping_strategies", {})
        scalp_raw = raw_data.get("scalping_strategies", {})

        # Handle backward-compatibility: if legacy scalping strategies were under execution_strategies
        migrated_legacy_from_exec: Dict[str, dict] = {}
        cleaned_exec_raw: Dict[str, dict] = {}
        for s_name, s_info in exec_raw.items():
            if s_name in LEGACY_SCALPING_STRATEGIES and s_name not in scalp_raw:
                migrated_legacy_from_exec[s_name] = s_info
            elif s_name not in LEGACY_SCALPING_STRATEGIES:
                cleaned_exec_raw[s_name] = s_info

        # Populate execution strategies (4 new strategies)
        for s_name, s_info in cleaned_exec_raw.items():
            fallback = defaults_exec.get(s_name, {})
            exec_strategies[s_name] = _parse_strat_item(s_name, s_info, fallback, is_scalp=False)

        # Populate scalping strategies (legacy strategies)
        combined_scalp_raw = {}
        for k in LEGACY_SCALPING_STRATEGIES:
            if k in scalp_raw:
                combined_scalp_raw[k] = scalp_raw[k]
            elif k in migrated_legacy_from_exec:
                combined_scalp_raw[k] = migrated_legacy_from_exec[k]
            elif k in defaults_scalp:
                combined_scalp_raw[k] = defaults_scalp[k]

        # In case raw has any extra custom scalping strategies
        for k, v in scalp_raw.items():
            if k not in combined_scalp_raw:
                combined_scalp_raw[k] = v

        for s_name, s_info in combined_scalp_raw.items():
            fallback = defaults_scalp.get(s_name, {})
            scalp_strategies[s_name] = _parse_strat_item(s_name, s_info, fallback, is_scalp=True)

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
            scalping_strategies=scalp_strategies,
            alpha_signals=alpha_signals,
        )

    @property
    def all_strategies(self) -> Dict[str, ExecutionStrategyConfig]:
        """Returns union mapping of both 4 new execution strategies and legacy scalping strategies."""
        combined = dict(self.execution_strategies)
        combined.update(self.scalping_strategies)
        return combined

    def is_execution_strategy(self, name: str) -> bool:
        """Returns True if the strategy belongs to the 4 new primary execution strategies."""
        return name in self.execution_strategies

    def is_scalping_strategy(self, name: str) -> bool:
        """Returns True if the strategy belongs to the legacy scalping strategies list."""
        return name in self.scalping_strategies

    @property
    def is_scalping_mode_active(self) -> bool:
        """Returns True if any scalping strategy is enabled and all 4 core strategies are disabled."""
        scalp_any = any(s.enabled for s in self.scalping_strategies.values())
        core_any = any(s.enabled for s in self.execution_strategies.values())
        return scalp_any and not core_any

    def set_scalping_mode(self, enabled: bool = True, save: bool = False, enable_queue_replenishment: bool = True) -> None:
        """Selects all scalping strategies and disables the 4 core execution strategies (or vice versa).

        Args:
            enabled: If True, enables all legacy scalping strategies (11) and disables the 4 core execution strategies.
                     If False, enables the primary core execution strategies and disables all scalping strategies.
            save: If True, immediately persists changes to strategies.json.
            enable_queue_replenishment: If False when core mode is activated, keeps Queue_Replenishment off by default (Triad active).
        """
        if enabled:
            # Enable all legacy scalping strategies
            for s in self.scalping_strategies.values():
                s.enabled = True
            # Disable the 4 core execution strategies
            for s in self.execution_strategies.values():
                s.enabled = False
            # Switch active live strategy to primary scalping strategy if it was core
            if self.is_execution_strategy(self.live_execution.active_strategy):
                self.live_execution.active_strategy = "Composite_Maker"
        else:
            # Enable core execution strategies (all 4 primary execution strategies enabled or triad active)
            for name, s in self.execution_strategies.items():
                if name == "Queue_Replenishment":
                    s.enabled = enable_queue_replenishment
                else:
                    s.enabled = True
            # Disable all legacy scalping strategies
            for s in self.scalping_strategies.values():
                s.enabled = False
            # Switch active live strategy to core if it was scalping
            if self.is_scalping_strategy(self.live_execution.active_strategy):
                self.live_execution.active_strategy = "Hedged_Convexity"

        if save:
            self.save()

    def get_strategy(self, name: str) -> Optional[ExecutionStrategyConfig]:
        """Lookup strategy in execution_strategies first, then scalping_strategies."""
        return self.execution_strategies.get(name) or self.scalping_strategies.get(name)

    def get_strategy_category(self, name: str) -> str:
        """Returns 'execution' for 4 new strategies, 'scalping' for legacy scalping strategies, or 'unknown'."""
        if self.is_execution_strategy(name):
            return "execution"
        if self.is_scalping_strategy(name):
            return "scalping"
        return "unknown"

    def is_strategy_enabled(self, name: str) -> bool:
        """Checks enabled state across either execution or scalping strategies."""
        s = self.get_strategy(name)
        return s.enabled if s else False

    def get_effective_live_strategy(self) -> str:
        """Returns the configured live strategy if enabled; otherwise dynamically resolves to the first enabled strategy.

        This prevents strategy contamination where a disabled strategy (e.g. Hedged_Convexity)
        is inadvertently assigned to live orders and exits when running in single-strategy mode (e.g. MicroPrice_FastFill).
        """
        current = self.live_execution.active_strategy
        current_cfg = self.get_strategy(current)
        if current_cfg and current_cfg.enabled:
            return current
        # If in scalping mode or current was scalping, check enabled scalping strategies first
        if self.is_scalping_mode_active or (current_cfg and current_cfg.is_scalping):
            for name, s in self.scalping_strategies.items():
                if s.enabled:
                    return name
            for name, s in self.execution_strategies.items():
                if s.enabled:
                    return name
        else:
            # Check enabled execution strategies first
            for name, s in self.execution_strategies.items():
                if s.enabled:
                    return name
            for name, s in self.scalping_strategies.items():
                if s.enabled:
                    return name
        return current

    def is_signal_enabled(self, name: str) -> bool:
        s = self.alpha_signals.get(name)
        return s.enabled if s else False

    def get_enabled_execution_strategy_defs(self) -> Dict[str, Tuple[str, str]]:
        """Returns dict of {strategy_name: (signal_key, execution_type)} for enabled 4 new execution strategies."""
        return {
            s.name: (s.signal_key, s.execution_type)
            for s in self.execution_strategies.values()
            if s.enabled
        }

    def get_enabled_scalping_strategy_defs(self) -> Dict[str, Tuple[str, str]]:
        """Returns dict of {strategy_name: (signal_key, execution_type)} for enabled legacy scalping strategies."""
        return {
            s.name: (s.signal_key, s.execution_type)
            for s in self.scalping_strategies.values()
            if s.enabled
        }

    def get_enabled_strategy_defs(self, include_scalping: bool = True) -> Dict[str, Tuple[str, str]]:
        """Returns dict of {strategy_name: (signal_key, execution_type)} for enabled strategies.
        
        Args:
            include_scalping: If True (default), includes enabled legacy scalping strategies
                              in addition to primary execution strategies.
        """
        defs = self.get_enabled_execution_strategy_defs()
        if include_scalping:
            defs.update(self.get_enabled_scalping_strategy_defs())
        return defs

    def get_strategy_params(self, include_scalping: bool = True) -> Dict[str, Dict[str, Any]]:
        """Returns dict of custom per-strategy parameters across execution and optionally scalping strategies."""
        res = {}
        strats_to_process = list(self.execution_strategies.values())
        if include_scalping:
            strats_to_process.extend(self.scalping_strategies.values())

        for s in strats_to_process:
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
            if getattr(s, "price_offset", None) is not None:
                p["price_offset"] = s.price_offset
            if getattr(s, "price_concession", None) is not None:
                p["price_concession"] = s.price_concession
            if getattr(s, "exit_concession", None) is not None:
                p["exit_concession"] = s.exit_concession
            if getattr(s, "price_concession_ratio", None) is not None:
                p["price_concession_ratio"] = s.price_concession_ratio
            if getattr(s, "exit_concession_ratio", None) is not None:
                p["exit_concession_ratio"] = s.exit_concession_ratio
            if getattr(s, "fast_fill_enabled", None) is not None:
                p["fast_fill_enabled"] = s.fast_fill_enabled
            if getattr(s, "entry_escalate_secs", None) is not None:
                p["entry_escalate_secs"] = s.entry_escalate_secs
            if getattr(s, "exit_escalate_secs", None) is not None:
                p["exit_escalate_secs"] = s.exit_escalate_secs
            if getattr(s, "defensive_hedge_market", None) is not None:
                p["defensive_hedge_market"] = s.defensive_hedge_market
            if getattr(s, "min_confidence", None) is not None:
                p["min_confidence"] = s.min_confidence
            if getattr(s, "dynamic_tp_enabled", None) is not None:
                p["dynamic_tp_enabled"] = s.dynamic_tp_enabled
            if getattr(s, "dynamic_tp_spread_mult", None) is not None:
                p["dynamic_tp_spread_mult"] = s.dynamic_tp_spread_mult
            if getattr(s, "dynamic_tp_vol_mult", None) is not None:
                p["dynamic_tp_vol_mult"] = s.dynamic_tp_vol_mult
            if getattr(s, "dynamic_tp_min_bps", None) is not None:
                p["dynamic_tp_min_bps"] = s.dynamic_tp_min_bps
            if getattr(s, "dynamic_tp_max_bps", None) is not None:
                p["dynamic_tp_max_bps"] = s.dynamic_tp_max_bps
            if getattr(s, "tiered_trailing_ratchet", None) is not None:
                p["tiered_trailing_ratchet"] = s.tiered_trailing_ratchet
            if getattr(s, "exhaustion_exit_enabled", None) is not None:
                p["exhaustion_exit_enabled"] = s.exhaustion_exit_enabled
            if getattr(s, "exhaustion_min_gain_bps", None) is not None:
                p["exhaustion_min_gain_bps"] = s.exhaustion_min_gain_bps
            if getattr(s, "exhaustion_score_threshold", None) is not None:
                p["exhaustion_score_threshold"] = s.exhaustion_score_threshold
            if getattr(s, "trend_filter_enabled", None) is not None:
                p["trend_filter_enabled"] = s.trend_filter_enabled
            if getattr(s, "trend_window_secs", None) is not None:
                p["trend_window_secs"] = s.trend_window_secs
            if getattr(s, "max_counter_trend_bps", None) is not None:
                p["max_counter_trend_bps"] = s.max_counter_trend_bps
            if getattr(s, "require_cvd_alignment", None) is not None:
                p["require_cvd_alignment"] = s.require_cvd_alignment
            if getattr(s, "emergency_slippage_pct", None) is not None:
                p["emergency_slippage_pct"] = s.emergency_slippage_pct
            if hasattr(s, "coentry_group") and s.coentry_group is not None:
                p["coentry_group"] = s.coentry_group
            res[s.name] = p
        return res

    def get_execution_strategy_params(self) -> Dict[str, Dict[str, Any]]:
        """Returns dict of custom per-strategy parameters specifically for the 4 new execution strategies."""
        return self.get_strategy_params(include_scalping=False)

    def get_scalping_strategy_params(self) -> Dict[str, Dict[str, Any]]:
        """Returns dict of custom per-strategy parameters specifically for legacy scalping strategies."""
        res = self.get_strategy_params(include_scalping=True)
        return {k: v for k, v in res.items() if k in self.scalping_strategies}

    def to_dict(self) -> Dict[str, Any]:
        """Serializes current configuration preserving execution_strategies and scalping_strategies separation."""
        exec_dict = {}
        for k, v in self.execution_strategies.items():
            exec_dict[k] = {
                "enabled": v.enabled,
                "description": v.description,
                "signal_key": v.signal_key,
                "execution_type": v.execution_type,
                "entry_threshold": v.entry_threshold,
                "order_size_btc": v.order_size_btc,
            }
            if v.take_profit_bps is not None:
                exec_dict[k]["take_profit_bps"] = v.take_profit_bps
            if v.stop_loss_bps is not None:
                exec_dict[k]["stop_loss_bps"] = v.stop_loss_bps
            if v.trailing_stop_activation_bps is not None:
                exec_dict[k]["trailing_stop_activation_bps"] = v.trailing_stop_activation_bps
            if v.trailing_stop_distance_bps is not None:
                exec_dict[k]["trailing_stop_distance_bps"] = v.trailing_stop_distance_bps
            if v.max_holding_time_secs is not None:
                exec_dict[k]["max_holding_time_secs"] = v.max_holding_time_secs
            if v.exit_reversal_threshold is not None:
                exec_dict[k]["exit_reversal_threshold"] = v.exit_reversal_threshold
            if v.hedge_trigger_loss_bps is not None:
                exec_dict[k]["hedge_trigger_loss_bps"] = v.hedge_trigger_loss_bps
            if v.hedge_reversal_threshold is not None:
                exec_dict[k]["hedge_reversal_threshold"] = v.hedge_reversal_threshold
            if v.min_volatility_bps is not None:
                exec_dict[k]["min_volatility_bps"] = v.min_volatility_bps
            if v.loss_cooldown_secs is not None:
                exec_dict[k]["loss_cooldown_secs"] = v.loss_cooldown_secs
            if v.coentry_group is not None:
                exec_dict[k]["coentry_group"] = v.coentry_group
            if getattr(v, "min_confidence", None) is not None:
                exec_dict[k]["min_confidence"] = v.min_confidence
            if getattr(v, "dynamic_tp_enabled", None) is not None:
                exec_dict[k]["dynamic_tp_enabled"] = v.dynamic_tp_enabled
            if getattr(v, "dynamic_tp_spread_mult", None) is not None:
                exec_dict[k]["dynamic_tp_spread_mult"] = v.dynamic_tp_spread_mult
            if getattr(v, "dynamic_tp_vol_mult", None) is not None:
                exec_dict[k]["dynamic_tp_vol_mult"] = v.dynamic_tp_vol_mult
            if getattr(v, "dynamic_tp_min_bps", None) is not None:
                exec_dict[k]["dynamic_tp_min_bps"] = v.dynamic_tp_min_bps
            if getattr(v, "dynamic_tp_max_bps", None) is not None:
                exec_dict[k]["dynamic_tp_max_bps"] = v.dynamic_tp_max_bps
            if getattr(v, "tiered_trailing_ratchet", None) is not None:
                exec_dict[k]["tiered_trailing_ratchet"] = v.tiered_trailing_ratchet
            if getattr(v, "exhaustion_exit_enabled", None) is not None:
                exec_dict[k]["exhaustion_exit_enabled"] = v.exhaustion_exit_enabled
            if getattr(v, "exhaustion_min_gain_bps", None) is not None:
                exec_dict[k]["exhaustion_min_gain_bps"] = v.exhaustion_min_gain_bps
            if getattr(v, "exhaustion_score_threshold", None) is not None:
                exec_dict[k]["exhaustion_score_threshold"] = v.exhaustion_score_threshold
            if getattr(v, "trend_filter_enabled", None) is not None:
                exec_dict[k]["trend_filter_enabled"] = v.trend_filter_enabled
            if getattr(v, "trend_window_secs", None) is not None:
                exec_dict[k]["trend_window_secs"] = v.trend_window_secs
            if getattr(v, "max_counter_trend_bps", None) is not None:
                exec_dict[k]["max_counter_trend_bps"] = v.max_counter_trend_bps
            if getattr(v, "require_cvd_alignment", None) is not None:
                exec_dict[k]["require_cvd_alignment"] = v.require_cvd_alignment
            if getattr(v, "emergency_slippage_pct", None) is not None:
                exec_dict[k]["emergency_slippage_pct"] = v.emergency_slippage_pct

        scalp_dict = {}
        for k, v in self.scalping_strategies.items():
            scalp_dict[k] = {
                "enabled": v.enabled,
                "description": v.description,
                "signal_key": v.signal_key,
                "execution_type": v.execution_type,
                "entry_threshold": v.entry_threshold,
                "order_size_btc": v.order_size_btc,
            }
            if v.take_profit_bps is not None:
                scalp_dict[k]["take_profit_bps"] = v.take_profit_bps
            if v.stop_loss_bps is not None:
                scalp_dict[k]["stop_loss_bps"] = v.stop_loss_bps
            if v.trailing_stop_activation_bps is not None:
                scalp_dict[k]["trailing_stop_activation_bps"] = v.trailing_stop_activation_bps
            if v.trailing_stop_distance_bps is not None:
                scalp_dict[k]["trailing_stop_distance_bps"] = v.trailing_stop_distance_bps
            if v.max_holding_time_secs is not None:
                scalp_dict[k]["max_holding_time_secs"] = v.max_holding_time_secs
            if v.exit_reversal_threshold is not None:
                scalp_dict[k]["exit_reversal_threshold"] = v.exit_reversal_threshold
            if v.min_volatility_bps is not None:
                scalp_dict[k]["min_volatility_bps"] = v.min_volatility_bps
            if getattr(v, "hedge_trigger_loss_bps", None) is not None:
                scalp_dict[k]["hedge_trigger_loss_bps"] = v.hedge_trigger_loss_bps
            if getattr(v, "hedge_reversal_threshold", None) is not None:
                scalp_dict[k]["hedge_reversal_threshold"] = v.hedge_reversal_threshold
            if getattr(v, "loss_cooldown_secs", None) is not None:
                scalp_dict[k]["loss_cooldown_secs"] = v.loss_cooldown_secs
            if getattr(v, "price_offset", None) is not None:
                scalp_dict[k]["price_offset"] = v.price_offset
            if getattr(v, "price_concession", None) is not None:
                scalp_dict[k]["price_concession"] = v.price_concession
            if getattr(v, "exit_concession", None) is not None:
                scalp_dict[k]["exit_concession"] = v.exit_concession
            if getattr(v, "price_concession_ratio", None) is not None:
                scalp_dict[k]["price_concession_ratio"] = v.price_concession_ratio
            if getattr(v, "exit_concession_ratio", None) is not None:
                scalp_dict[k]["exit_concession_ratio"] = v.exit_concession_ratio
            if getattr(v, "fast_fill_enabled", None) is not None:
                scalp_dict[k]["fast_fill_enabled"] = v.fast_fill_enabled
            if getattr(v, "entry_escalate_secs", None) is not None:
                scalp_dict[k]["entry_escalate_secs"] = v.entry_escalate_secs
            if getattr(v, "exit_escalate_secs", None) is not None:
                scalp_dict[k]["exit_escalate_secs"] = v.exit_escalate_secs
            if getattr(v, "defensive_hedge_market", None) is not None:
                scalp_dict[k]["defensive_hedge_market"] = v.defensive_hedge_market
            if getattr(v, "min_confidence", None) is not None:
                scalp_dict[k]["min_confidence"] = v.min_confidence
            if getattr(v, "dynamic_tp_enabled", None) is not None:
                scalp_dict[k]["dynamic_tp_enabled"] = v.dynamic_tp_enabled
            if getattr(v, "dynamic_tp_spread_mult", None) is not None:
                scalp_dict[k]["dynamic_tp_spread_mult"] = v.dynamic_tp_spread_mult
            if getattr(v, "dynamic_tp_vol_mult", None) is not None:
                scalp_dict[k]["dynamic_tp_vol_mult"] = v.dynamic_tp_vol_mult
            if getattr(v, "dynamic_tp_min_bps", None) is not None:
                scalp_dict[k]["dynamic_tp_min_bps"] = v.dynamic_tp_min_bps
            if getattr(v, "dynamic_tp_max_bps", None) is not None:
                scalp_dict[k]["dynamic_tp_max_bps"] = v.dynamic_tp_max_bps
            if getattr(v, "tiered_trailing_ratchet", None) is not None:
                scalp_dict[k]["tiered_trailing_ratchet"] = v.tiered_trailing_ratchet
            if getattr(v, "exhaustion_exit_enabled", None) is not None:
                scalp_dict[k]["exhaustion_exit_enabled"] = v.exhaustion_exit_enabled
            if getattr(v, "exhaustion_min_gain_bps", None) is not None:
                scalp_dict[k]["exhaustion_min_gain_bps"] = v.exhaustion_min_gain_bps
            if getattr(v, "exhaustion_score_threshold", None) is not None:
                scalp_dict[k]["exhaustion_score_threshold"] = v.exhaustion_score_threshold
            if getattr(v, "trend_filter_enabled", None) is not None:
                scalp_dict[k]["trend_filter_enabled"] = v.trend_filter_enabled
            if getattr(v, "trend_window_secs", None) is not None:
                scalp_dict[k]["trend_window_secs"] = v.trend_window_secs
            if getattr(v, "max_counter_trend_bps", None) is not None:
                scalp_dict[k]["max_counter_trend_bps"] = v.max_counter_trend_bps
            if getattr(v, "require_cvd_alignment", None) is not None:
                scalp_dict[k]["require_cvd_alignment"] = v.require_cvd_alignment
            if getattr(v, "emergency_slippage_pct", None) is not None:
                scalp_dict[k]["emergency_slippage_pct"] = v.emergency_slippage_pct

        alpha_dict = {
            k: {
                "enabled": v.enabled,
                "weight": v.weight,
                "description": v.description,
            }
            for k, v in self.alpha_signals.items()
        }

        return {
            "_comment": "Hyperliquid L2 Microstructure Alpha Engine - Strategy & Signal Configuration",
            "_instructions": "Set 'enabled': true or false to select/deselect any execution strategy, scalping strategy, or alpha signal.",
            "version": "1.1",
            "live_execution": {
                "active_strategy": self.live_execution.active_strategy,
                "order_size_btc": self.live_execution.order_size_btc,
                "max_position_btc": self.live_execution.max_position_btc,
                "penny_jumping": self.live_execution.penny_jumping,
                "use_ioc_on_marketable": self.live_execution.use_ioc_on_marketable,
                "use_native_tpsl": self.live_execution.use_native_tpsl,
                "priority_fee_bps": self.live_execution.priority_fee_bps,
                "force_market_orders": getattr(self.live_execution, "force_market_orders", False),
                "market_slippage_pct": getattr(self.live_execution, "market_slippage_pct", 0.01),
                "warmup_secs": getattr(self.live_execution, "warmup_secs", 10.0),
            },
            "execution_strategies": exec_dict,
            "scalping_strategies": scalp_dict,
            "alpha_signals": alpha_dict,
        }

    def save(self, filepath: Optional[str] = None):
        """Saves configuration to JSON preserving execution and scalping distinction."""
        target_path = filepath or self.filepath
        data = self.to_dict()
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

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
class CoreStrategiesConfig(StrategiesConfig):
    """Configuration specifically managing the 4 core execution strategies for Program 1."""
    filepath: str = "strategies_core.json"

    @classmethod
    def load(cls, filepath: str = "strategies_core.json") -> "CoreStrategiesConfig":
        return cls._load_core(filepath)

    @classmethod
    def _load_core(cls, filepath: str = "strategies_core.json", raw_data: Optional[dict] = None) -> "CoreStrategiesConfig":
        if raw_data is None:
            if not os.path.exists(filepath):
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(DEFAULT_CORE_STRATEGIES_JSON, f, indent=2)
                except Exception:
                    pass
                raw_data = DEFAULT_CORE_STRATEGIES_JSON
            else:
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        raw_data = json.load(f)
                except Exception:
                    raw_data = DEFAULT_CORE_STRATEGIES_JSON

        live_raw = raw_data.get("live_execution", {})
        live_cfg = LiveExecutionConfig(
            active_strategy=live_raw.get("active_strategy", "Hedged_Convexity"),
            order_size_btc=float(live_raw.get("order_size_btc", 0.0005)),
            max_position_btc=float(live_raw.get("max_position_btc", 0.05)),
            penny_jumping=bool(live_raw.get("penny_jumping", True)),
            use_ioc_on_marketable=bool(live_raw.get("use_ioc_on_marketable", True)),
            use_native_tpsl=bool(live_raw.get("use_native_tpsl", True)),
            priority_fee_bps=float(live_raw.get("priority_fee_bps", 0.0)),
            force_market_orders=bool(live_raw.get("force_market_orders", False)),
            market_slippage_pct=float(live_raw.get("market_slippage_pct", 0.0005)),
            warmup_secs=float(live_raw.get("warmup_secs", 10.0)),
        )

        def _parse_strat_item(s_name: str, s_info: dict, fallback: dict) -> ExecutionStrategyConfig:
            return ExecutionStrategyConfig(
                name=s_name,
                enabled=bool(s_info.get("enabled", fallback.get("enabled", True))),
                description=str(s_info.get("description", fallback.get("description", ""))),
                signal_key=str(s_info.get("signal_key", fallback.get("signal_key", "CompositeAlpha"))),
                execution_type=str(s_info.get("execution_type", fallback.get("execution_type", "HEDGED_MAKER"))),
                entry_threshold=float(s_info.get("entry_threshold", fallback.get("entry_threshold", 0.8))),
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
                price_offset=float(s_info["price_offset"]) if "price_offset" in s_info else fallback.get("price_offset"),
                price_concession=float(s_info["price_concession"]) if "price_concession" in s_info else fallback.get("price_concession"),
                exit_concession=float(s_info["exit_concession"]) if "exit_concession" in s_info else fallback.get("exit_concession"),
                price_concession_ratio=float(s_info["price_concession_ratio"]) if "price_concession_ratio" in s_info else fallback.get("price_concession_ratio"),
                exit_concession_ratio=float(s_info["exit_concession_ratio"]) if "exit_concession_ratio" in s_info else fallback.get("exit_concession_ratio"),
                fast_fill_enabled=bool(s_info["fast_fill_enabled"]) if "fast_fill_enabled" in s_info else fallback.get("fast_fill_enabled"),
                entry_escalate_secs=float(s_info["entry_escalate_secs"]) if "entry_escalate_secs" in s_info else fallback.get("entry_escalate_secs"),
                exit_escalate_secs=float(s_info["exit_escalate_secs"]) if "exit_escalate_secs" in s_info else fallback.get("exit_escalate_secs"),
                defensive_hedge_market=bool(s_info["defensive_hedge_market"]) if "defensive_hedge_market" in s_info else fallback.get("defensive_hedge_market"),
                min_confidence=float(s_info["min_confidence"]) if "min_confidence" in s_info else fallback.get("min_confidence"),
                coentry_group=str(s_info["coentry_group"]) if "coentry_group" in s_info else fallback.get("coentry_group"),
                trend_filter_enabled=bool(s_info["trend_filter_enabled"]) if "trend_filter_enabled" in s_info else fallback.get("trend_filter_enabled"),
                trend_window_secs=float(s_info["trend_window_secs"]) if "trend_window_secs" in s_info else fallback.get("trend_window_secs"),
                max_counter_trend_bps=float(s_info["max_counter_trend_bps"]) if "max_counter_trend_bps" in s_info else fallback.get("max_counter_trend_bps"),
                require_cvd_alignment=bool(s_info["require_cvd_alignment"]) if "require_cvd_alignment" in s_info else fallback.get("require_cvd_alignment"),
                dynamic_tp_enabled=bool(s_info["dynamic_tp_enabled"]) if "dynamic_tp_enabled" in s_info else fallback.get("dynamic_tp_enabled"),
                dynamic_tp_spread_mult=float(s_info["dynamic_tp_spread_mult"]) if "dynamic_tp_spread_mult" in s_info else fallback.get("dynamic_tp_spread_mult"),
                dynamic_tp_vol_mult=float(s_info["dynamic_tp_vol_mult"]) if "dynamic_tp_vol_mult" in s_info else fallback.get("dynamic_tp_vol_mult"),
                dynamic_tp_min_bps=float(s_info["dynamic_tp_min_bps"]) if "dynamic_tp_min_bps" in s_info else fallback.get("dynamic_tp_min_bps"),
                dynamic_tp_max_bps=float(s_info["dynamic_tp_max_bps"]) if "dynamic_tp_max_bps" in s_info else fallback.get("dynamic_tp_max_bps"),
                tiered_trailing_ratchet=bool(s_info["tiered_trailing_ratchet"]) if "tiered_trailing_ratchet" in s_info else fallback.get("tiered_trailing_ratchet"),
                exhaustion_exit_enabled=bool(s_info["exhaustion_exit_enabled"]) if "exhaustion_exit_enabled" in s_info else fallback.get("exhaustion_exit_enabled"),
                exhaustion_min_gain_bps=float(s_info["exhaustion_min_gain_bps"]) if "exhaustion_min_gain_bps" in s_info else fallback.get("exhaustion_min_gain_bps"),
                exhaustion_score_threshold=float(s_info["exhaustion_score_threshold"]) if "exhaustion_score_threshold" in s_info else fallback.get("exhaustion_score_threshold"),
                emergency_slippage_pct=float(s_info["emergency_slippage_pct"]) if "emergency_slippage_pct" in s_info else fallback.get("emergency_slippage_pct"),
                is_scalping=False,
            )

        exec_strategies: Dict[str, ExecutionStrategyConfig] = {}
        defaults_exec = DEFAULT_CORE_STRATEGIES_JSON["execution_strategies"]
        exec_raw = raw_data.get("execution_strategies", defaults_exec)
        for s_name in NEW_EXECUTION_STRATEGIES:
            s_info = exec_raw.get(s_name, defaults_exec.get(s_name, {}))
            fallback = defaults_exec.get(s_name, {})
            exec_strategies[s_name] = _parse_strat_item(s_name, s_info, fallback)

        alpha_signals: Dict[str, AlphaSignalConfig] = {}
        defaults_alpha = DEFAULT_CORE_STRATEGIES_JSON["alpha_signals"]
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
            scalping_strategies={},
            alpha_signals=alpha_signals,
        )

    @property
    def all_strategies(self) -> Dict[str, ExecutionStrategyConfig]:
        return self.execution_strategies

    def is_execution_strategy(self, name: str) -> bool:
        return name in self.execution_strategies

    def is_scalping_strategy(self, name: str) -> bool:
        return False

    @property
    def is_scalping_mode_active(self) -> bool:
        return False

    def get_strategy(self, name: str) -> Optional[ExecutionStrategyConfig]:
        return self.execution_strategies.get(name)

    def get_strategy_category(self, name: str) -> str:
        return "execution" if name in self.execution_strategies else "unknown"

    def get_effective_live_strategy(self) -> str:
        current = self.live_execution.active_strategy
        current_cfg = self.execution_strategies.get(current)
        if current_cfg and current_cfg.enabled:
            return current
        for name, s in self.execution_strategies.items():
            if s.enabled:
                return name
        return current or "Hedged_Convexity"

    def get_enabled_strategy_defs(self, include_scalping: bool = False) -> Dict[str, Tuple[str, str]]:
        return {
            s.name: (s.signal_key, s.execution_type)
            for s in self.execution_strategies.values()
            if s.enabled
        }

    @property
    def program_name(self) -> str:
        return "core_execution"

    def set_scalping_mode(self, enabled: bool = False, save: bool = False, enable_queue_replenishment: bool = True):
        """In CoreStrategiesConfig, scalping mode cannot be enabled. Preserves core strategies."""
        if not enabled:
            for name, s in self.execution_strategies.items():
                if name == "Queue_Replenishment":
                    s.enabled = enable_queue_replenishment
                else:
                    s.enabled = True
            if self.live_execution.active_strategy not in self.execution_strategies:
                self.live_execution.active_strategy = "Hedged_Convexity"
        if save:
            self.save()

    def get_strategy_params(self, include_scalping: bool = False) -> Dict[str, Dict[str, Any]]:
        return super().get_strategy_params(include_scalping=False)

    def to_dict(self) -> Dict[str, Any]:
        exec_dict = {}
        for k, v in self.execution_strategies.items():
            exec_dict[k] = {
                "enabled": v.enabled,
                "description": v.description,
                "signal_key": v.signal_key,
                "execution_type": v.execution_type,
                "entry_threshold": v.entry_threshold,
                "order_size_btc": v.order_size_btc,
            }
            for attr in (
                "take_profit_bps", "stop_loss_bps", "trailing_stop_activation_bps",
                "trailing_stop_distance_bps", "max_holding_time_secs", "exit_reversal_threshold",
                "hedge_trigger_loss_bps", "hedge_reversal_threshold", "min_volatility_bps",
                "loss_cooldown_secs", "coentry_group", "fast_fill_enabled", "entry_escalate_secs",
                "exit_escalate_secs", "defensive_hedge_market", "min_confidence", "trend_filter_enabled",
                "trend_window_secs", "max_counter_trend_bps", "require_cvd_alignment", "dynamic_tp_enabled",
                "dynamic_tp_spread_mult", "dynamic_tp_vol_mult", "dynamic_tp_min_bps", "dynamic_tp_max_bps",
                "tiered_trailing_ratchet", "exhaustion_exit_enabled", "exhaustion_min_gain_bps",
                "exhaustion_score_threshold", "emergency_slippage_pct"
            ):
                val = getattr(v, attr, None)
                if val is not None:
                    exec_dict[k][attr] = val

        alpha_dict = {
            k: {
                "enabled": v.enabled,
                "weight": v.weight,
                "description": v.description,
            }
            for k, v in self.alpha_signals.items()
        }

        return {
            "_comment": "Hyperliquid L2 Microstructure Alpha Engine - Core Execution Strategy Configuration",
            "_instructions": "Configuration for the 4 core execution strategies: Hedged_Convexity, Convexity_Cascade, Momentum_Expansion, Queue_Replenishment.",
            "version": "1.1",
            "program": "core_execution",
            "live_execution": {
                "active_strategy": self.live_execution.active_strategy,
                "order_size_btc": self.live_execution.order_size_btc,
                "max_position_btc": self.live_execution.max_position_btc,
                "penny_jumping": self.live_execution.penny_jumping,
                "use_ioc_on_marketable": self.live_execution.use_ioc_on_marketable,
                "use_native_tpsl": self.live_execution.use_native_tpsl,
                "priority_fee_bps": self.live_execution.priority_fee_bps,
                "force_market_orders": getattr(self.live_execution, "force_market_orders", False),
                "market_slippage_pct": getattr(self.live_execution, "market_slippage_pct", 0.0005),
                "warmup_secs": getattr(self.live_execution, "warmup_secs", 10.0),
            },
            "execution_strategies": exec_dict,
            "alpha_signals": alpha_dict,
        }


@dataclass
class ScalperStrategiesConfig(StrategiesConfig):
    """Configuration specifically managing the 11 scalping strategies for Program 2."""
    filepath: str = "strategies_scalper.json"

    @classmethod
    def load(cls, filepath: str = "strategies_scalper.json") -> "ScalperStrategiesConfig":
        return cls._load_scalper(filepath)

    @classmethod
    def _load_scalper(cls, filepath: str = "strategies_scalper.json", raw_data: Optional[dict] = None) -> "ScalperStrategiesConfig":
        if raw_data is None:
            if not os.path.exists(filepath):
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(DEFAULT_SCALPER_STRATEGIES_JSON, f, indent=2)
                except Exception:
                    pass
                raw_data = DEFAULT_SCALPER_STRATEGIES_JSON
            else:
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        raw_data = json.load(f)
                except Exception:
                    raw_data = DEFAULT_SCALPER_STRATEGIES_JSON

        live_raw = raw_data.get("live_execution", {})
        live_cfg = LiveExecutionConfig(
            active_strategy=live_raw.get("active_strategy", "Composite_Maker"),
            order_size_btc=float(live_raw.get("order_size_btc", 0.0005)),
            max_position_btc=float(live_raw.get("max_position_btc", 0.05)),
            penny_jumping=bool(live_raw.get("penny_jumping", True)),
            use_ioc_on_marketable=bool(live_raw.get("use_ioc_on_marketable", True)),
            use_native_tpsl=bool(live_raw.get("use_native_tpsl", True)),
            priority_fee_bps=float(live_raw.get("priority_fee_bps", 0.0)),
            force_market_orders=bool(live_raw.get("force_market_orders", False)),
            market_slippage_pct=float(live_raw.get("market_slippage_pct", 0.0005)),
            warmup_secs=float(live_raw.get("warmup_secs", 10.0)),
        )

        def _parse_strat_item(s_name: str, s_info: dict, fallback: dict) -> ScalpingStrategyConfig:
            return ScalpingStrategyConfig(
                name=s_name,
                enabled=bool(s_info.get("enabled", fallback.get("enabled", False))),
                description=str(s_info.get("description", fallback.get("description", ""))),
                signal_key=str(s_info.get("signal_key", fallback.get("signal_key", "CompositeAlpha"))),
                execution_type=str(s_info.get("execution_type", fallback.get("execution_type", "MAKER"))),
                entry_threshold=float(s_info.get("entry_threshold", fallback.get("entry_threshold", 0.4))),
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
                price_offset=float(s_info["price_offset"]) if "price_offset" in s_info else fallback.get("price_offset"),
                price_concession=float(s_info["price_concession"]) if "price_concession" in s_info else fallback.get("price_concession"),
                exit_concession=float(s_info["exit_concession"]) if "exit_concession" in s_info else fallback.get("exit_concession"),
                price_concession_ratio=float(s_info["price_concession_ratio"]) if "price_concession_ratio" in s_info else fallback.get("price_concession_ratio"),
                exit_concession_ratio=float(s_info["exit_concession_ratio"]) if "exit_concession_ratio" in s_info else fallback.get("exit_concession_ratio"),
                fast_fill_enabled=bool(s_info["fast_fill_enabled"]) if "fast_fill_enabled" in s_info else fallback.get("fast_fill_enabled"),
                entry_escalate_secs=float(s_info["entry_escalate_secs"]) if "entry_escalate_secs" in s_info else fallback.get("entry_escalate_secs"),
                exit_escalate_secs=float(s_info["exit_escalate_secs"]) if "exit_escalate_secs" in s_info else fallback.get("exit_escalate_secs"),
                defensive_hedge_market=bool(s_info["defensive_hedge_market"]) if "defensive_hedge_market" in s_info else fallback.get("defensive_hedge_market"),
                min_confidence=float(s_info["min_confidence"]) if "min_confidence" in s_info else fallback.get("min_confidence"),
                coentry_group=str(s_info["coentry_group"]) if "coentry_group" in s_info else fallback.get("coentry_group"),
                trend_filter_enabled=bool(s_info["trend_filter_enabled"]) if "trend_filter_enabled" in s_info else fallback.get("trend_filter_enabled"),
                trend_window_secs=float(s_info["trend_window_secs"]) if "trend_window_secs" in s_info else fallback.get("trend_window_secs"),
                max_counter_trend_bps=float(s_info["max_counter_trend_bps"]) if "max_counter_trend_bps" in s_info else fallback.get("max_counter_trend_bps"),
                require_cvd_alignment=bool(s_info["require_cvd_alignment"]) if "require_cvd_alignment" in s_info else fallback.get("require_cvd_alignment"),
                dynamic_tp_enabled=bool(s_info["dynamic_tp_enabled"]) if "dynamic_tp_enabled" in s_info else fallback.get("dynamic_tp_enabled"),
                dynamic_tp_spread_mult=float(s_info["dynamic_tp_spread_mult"]) if "dynamic_tp_spread_mult" in s_info else fallback.get("dynamic_tp_spread_mult"),
                dynamic_tp_vol_mult=float(s_info["dynamic_tp_vol_mult"]) if "dynamic_tp_vol_mult" in s_info else fallback.get("dynamic_tp_vol_mult"),
                dynamic_tp_min_bps=float(s_info["dynamic_tp_min_bps"]) if "dynamic_tp_min_bps" in s_info else fallback.get("dynamic_tp_min_bps"),
                dynamic_tp_max_bps=float(s_info["dynamic_tp_max_bps"]) if "dynamic_tp_max_bps" in s_info else fallback.get("dynamic_tp_max_bps"),
                tiered_trailing_ratchet=bool(s_info["tiered_trailing_ratchet"]) if "tiered_trailing_ratchet" in s_info else fallback.get("tiered_trailing_ratchet"),
                exhaustion_exit_enabled=bool(s_info["exhaustion_exit_enabled"]) if "exhaustion_exit_enabled" in s_info else fallback.get("exhaustion_exit_enabled"),
                exhaustion_min_gain_bps=float(s_info["exhaustion_min_gain_bps"]) if "exhaustion_min_gain_bps" in s_info else fallback.get("exhaustion_min_gain_bps"),
                exhaustion_score_threshold=float(s_info["exhaustion_score_threshold"]) if "exhaustion_score_threshold" in s_info else fallback.get("exhaustion_score_threshold"),
                emergency_slippage_pct=float(s_info["emergency_slippage_pct"]) if "emergency_slippage_pct" in s_info else fallback.get("emergency_slippage_pct"),
                is_scalping=True,
            )

        scalp_strategies: Dict[str, ScalpingStrategyConfig] = {}
        defaults_scalp = DEFAULT_SCALPER_STRATEGIES_JSON["scalping_strategies"]
        scalp_raw = raw_data.get("scalping_strategies", defaults_scalp)
        for s_name in LEGACY_SCALPING_STRATEGIES:
            s_info = scalp_raw.get(s_name, defaults_scalp.get(s_name, {}))
            fallback = defaults_scalp.get(s_name, {})
            scalp_strategies[s_name] = _parse_strat_item(s_name, s_info, fallback)

        alpha_signals: Dict[str, AlphaSignalConfig] = {}
        defaults_alpha = DEFAULT_SCALPER_STRATEGIES_JSON["alpha_signals"]
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
            execution_strategies={},
            scalping_strategies=scalp_strategies,
            alpha_signals=alpha_signals,
        )

    @property
    def all_strategies(self) -> Dict[str, ScalpingStrategyConfig]:
        return self.scalping_strategies

    def is_execution_strategy(self, name: str) -> bool:
        return False

    def is_scalping_strategy(self, name: str) -> bool:
        return name in self.scalping_strategies

    @property
    def is_scalping_mode_active(self) -> bool:
        return True

    def get_strategy(self, name: str) -> Optional[ScalpingStrategyConfig]:
        return self.scalping_strategies.get(name)

    def get_strategy_category(self, name: str) -> str:
        return "scalping" if name in self.scalping_strategies else "unknown"

    def get_effective_live_strategy(self) -> str:
        current = self.live_execution.active_strategy
        current_cfg = self.scalping_strategies.get(current)
        if current_cfg and current_cfg.enabled:
            return current
        for name, s in self.scalping_strategies.items():
            if s.enabled:
                return name
        return current or "Composite_Maker"

    def get_enabled_strategy_defs(self, include_scalping: bool = True) -> Dict[str, Tuple[str, str]]:
        return {
            s.name: (s.signal_key, s.execution_type)
            for s in self.scalping_strategies.values()
            if s.enabled
        }

    @property
    def program_name(self) -> str:
        return "scalper"

    def set_scalping_mode(self, enabled: bool = True, save: bool = False, enable_queue_replenishment: bool = False):
        """In ScalperStrategiesConfig, core mode cannot be enabled. Preserves scalping strategies."""
        if enabled:
            for s in self.scalping_strategies.values():
                s.enabled = True
            if self.live_execution.active_strategy not in self.scalping_strategies:
                self.live_execution.active_strategy = "Composite_Maker"
        if save:
            self.save()

    def get_strategy_params(self, include_scalping: bool = True) -> Dict[str, Dict[str, Any]]:
        return super().get_strategy_params(include_scalping=True)

    def to_dict(self) -> Dict[str, Any]:
        scalp_dict = {}
        for k, v in self.scalping_strategies.items():
            scalp_dict[k] = {
                "enabled": v.enabled,
                "description": v.description,
                "signal_key": v.signal_key,
                "execution_type": v.execution_type,
                "entry_threshold": v.entry_threshold,
                "order_size_btc": v.order_size_btc,
            }
            for attr in (
                "take_profit_bps", "stop_loss_bps", "trailing_stop_activation_bps",
                "trailing_stop_distance_bps", "max_holding_time_secs", "exit_reversal_threshold",
                "min_volatility_bps", "loss_cooldown_secs", "price_offset", "price_concession", "exit_concession", "price_concession_ratio", "exit_concession_ratio",
                "fast_fill_enabled", "entry_escalate_secs", "exit_escalate_secs", "defensive_hedge_market",
                "min_confidence", "trend_filter_enabled", "trend_window_secs", "max_counter_trend_bps",
                "require_cvd_alignment", "dynamic_tp_enabled", "dynamic_tp_spread_mult", "dynamic_tp_vol_mult",
                "dynamic_tp_min_bps", "dynamic_tp_max_bps", "tiered_trailing_ratchet", "exhaustion_exit_enabled",
                "exhaustion_min_gain_bps", "exhaustion_score_threshold", "emergency_slippage_pct"
            ):
                val = getattr(v, attr, None)
                if val is not None:
                    scalp_dict[k][attr] = val

        alpha_dict = {
            k: {
                "enabled": v.enabled,
                "weight": v.weight,
                "description": v.description,
            }
            for k, v in self.alpha_signals.items()
        }

        return {
            "_comment": "Hyperliquid L2 Microstructure Alpha Engine - Scalping Strategy Configuration",
            "_instructions": "Configuration for the 11 high-frequency scalping strategies (maker & smart taker).",
            "version": "1.1",
            "program": "scalper",
            "live_execution": {
                "active_strategy": self.live_execution.active_strategy,
                "order_size_btc": self.live_execution.order_size_btc,
                "max_position_btc": self.live_execution.max_position_btc,
                "penny_jumping": self.live_execution.penny_jumping,
                "use_ioc_on_marketable": self.live_execution.use_ioc_on_marketable,
                "use_native_tpsl": self.live_execution.use_native_tpsl,
                "priority_fee_bps": self.live_execution.priority_fee_bps,
                "force_market_orders": getattr(self.live_execution, "force_market_orders", False),
                "market_slippage_pct": getattr(self.live_execution, "market_slippage_pct", 0.0005),
                "warmup_secs": getattr(self.live_execution, "warmup_secs", 10.0),
            },
            "scalping_strategies": scalp_dict,
            "alpha_signals": alpha_dict,
        }


# Canonical alias for scalping config
ScalpingStrategiesConfig = ScalperStrategiesConfig


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
    sample_rate_hz: float = 20.0  # Sampling frequency for engine loop (20Hz = 50ms evaluation tick)

    @property
    def live_execution(self) -> LiveExecutionConfig:
        """Convenience property exposing strategies.live_execution directly on AppConfig."""
        return self.strategies.live_execution

    @live_execution.setter
    def live_execution(self, value: LiveExecutionConfig) -> None:
        self.strategies.live_execution = value

    @property
    def coin_data_dir(self) -> str:
        """Returns the coin-specific data directory (e.g. data/btc or data/xyz_skhy)."""
        safe_coin = self.market.safe_coin.lower()
        return os.path.join(self.data_dir, safe_coin)

    @classmethod
    def for_core(cls, strategies_config: str = "strategies_core.json", **kwargs) -> "AppConfig":
        """Instantiates an AppConfig configured for the Core Execution Strategy program."""
        strat_cfg = CoreStrategiesConfig.load(strategies_config)
        cfg = cls(strategies=strat_cfg, **kwargs)
        return cfg

    @classmethod
    def for_scalper(cls, strategies_config: str = "strategies_scalper.json", **kwargs) -> "AppConfig":
        """Instantiates an AppConfig configured for the Scalping Strategy program."""
        strat_cfg = ScalperStrategiesConfig.load(strategies_config)
        cfg = cls(strategies=strat_cfg, **kwargs)
        return cfg

