"""Statistical predictive alpha evaluator (IC, t-stat) and advanced paper trading simulator.

Implements dual execution paradigms:
1. Passive Maker Execution (Avellaneda-Stoikov spread capture + maker rebates)
2. Smart Taker Execution (fee-hurdle gating, break-even ratchet, and trailing stops)
"""

from collections import deque
from dataclasses import dataclass, field
import math
import time
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

from config import BacktestConfig, MarketConfig, NEW_EXECUTION_STRATEGIES, LEGACY_SCALPING_STRATEGIES


@dataclass
class TradeRecord:
    strategy_name: str
    entry_time_ms: int
    exit_time_ms: int
    side: str  # 'LONG' or 'SHORT'
    entry_price: float
    exit_price: float
    size_btc: float
    gross_pnl_usd: float
    fees_usd: float
    net_pnl_usd: float
    return_bps: float
    exit_reason: str  # 'TAKE_PROFIT', 'TRAILING_STOP', 'STOP_LOSS', 'SIGNAL_REVERSAL', 'TIME_LIMIT'
    execution_type: str = "TAKER"  # 'MAKER' or 'TAKER'


@dataclass
class StrategyState:
    name: str
    execution_type: str = "MAKER"  # 'MAKER' or 'SMART_TAKER'
    signal_key: str = "CompositeAlpha"
    position_btc: float = 0.0
    entry_price: float = 0.0
    entry_time_ms: int = 0
    cash_usd: float = 10_000.0
    category: str = "execution"  # 'execution' for 4 new strategies or 'scalping' for legacy strategies
    trades: List[TradeRecord] = field(default_factory=list)
    peak_equity: float = 10_000.0
    max_drawdown_usd: float = 0.0

    # Dynamic trade management
    entry_fee_usd: float = 0.0  # Fee paid on entry leg
    peak_price: float = 0.0  # Peak price reached while long
    trough_price: float = 1e9  # Trough price reached while short
    trailing_stop_active: bool = False
    stop_price: float = 0.0
    take_profit_price: float = 0.0
    entry_signal_score: float = 0.0
    peak_unrealized_bps: float = 0.0
    trough_unrealized_bps: float = 0.0
    last_exit_time_ms: int = 0
    last_exit_was_loss: bool = False
    consecutive_losses: int = 0  # Track consecutive loss streak for escalated cooldown

    @property
    def is_in_position(self) -> bool:
        return abs(self.position_btc) > 1e-6

    def current_equity(self, current_price: float) -> float:
        unrealized = self.position_btc * (current_price - self.entry_price)
        return self.cash_usd + unrealized


@dataclass
class SignalObservation:
    timestamp_ms: int
    price: float
    signals: Dict[str, float]
    evaluated_horizons: set = field(default_factory=set)


class EdgeEvaluator:
    """Rigorous market microstructure alpha evaluator and advanced execution simulator.
    
    1. Multi-Horizon Predictive Edge:
       - Evaluates Information Coefficient (IC), Rank IC, t-statistic, and directional accuracy
         across [1s, 3s, 5s, 10s, 30s, 60s].
         
    2. Dual Execution Simulation:
       - Maker Strategies: Post passive limit quotes at best bid/ask, earning spread and maker rebates.
       - Smart Taker Strategies: Enter with market orders only on high conviction dislocations with
         dynamic trailing stops and break-even ratchets.
    """

    def __init__(
        self,
        market_cfg: Optional[MarketConfig] = None,
        bt_cfg: Optional[BacktestConfig] = None,
        strategy_defs: Optional[Dict[str, Tuple[str, str]]] = None,
        strategy_params: Optional[Dict[str, Dict[str, Any]]] = None,
        auditor: Optional[Any] = None,
    ):
        self.market_cfg = market_cfg or MarketConfig()
        self.bt_cfg = bt_cfg or BacktestConfig()
        self.strategy_params = strategy_params or {}
        self.auditor = auditor

        # Strategy definitions: mapping strategy name to (underlying signal, execution style)
        if strategy_defs is not None:
            self.strategy_defs = strategy_defs
        else:
            self.strategy_defs = {
                "Hedged_Convexity": ("HedgedConvexity", "HEDGED_MAKER"),
                "Convexity_Cascade": ("ConvexityCascade", "MAKER"),
                "Momentum_Expansion": ("MomentumExpansion", "MAKER"),
                "Queue_Replenishment": ("QueueReplenishment", "HEDGED_MAKER"),
                "QDAP_Maker": ("QDAP", "MAKER"),
                "AdaptiveML_Maker": ("AdaptiveML", "MAKER"),
                "Composite_Maker": ("CompositeAlpha", "MAKER"),
                "WOBI_Maker": ("WOBI", "MAKER"),
                "MicroPrice_Maker": ("MicroPrice", "MAKER"),
                "AdaptiveML_Taker": ("AdaptiveML", "SMART_TAKER"),
                "Composite_Taker": ("CompositeAlpha", "SMART_TAKER"),
                "Absorption_Fade": ("Absorption", "MAKER"),
            }

        self.strategy_names = list(self.strategy_defs.keys())

        # Strategy states
        self.strategies: Dict[str, StrategyState] = {
            s: StrategyState(
                name=s,
                execution_type=self.strategy_defs[s][1],
                signal_key=self.strategy_defs[s][0],
                cash_usd=self.bt_cfg.initial_cash_usd,
                category="scalping" if s in LEGACY_SCALPING_STRATEGIES else "execution",
            )
            for s in self.strategy_names
        }

        # Buffer for forward return IC tracking
        self.observations: Deque[SignalObservation] = deque(maxlen=2000)

        # Evaluations per horizon: signal_key -> horizon_secs -> list of (sig_val, return)
        unique_signals = set(sig_k for sig_k, _ in self.strategy_defs.values())
        unique_signals.update([
            "WOBI", "VOI", "MicroPrice", "VPIN", "Absorption", "Sweep",
            "CompositeAlpha", "AdaptiveML", "QDAP", "MomentumExpansion",
            "ConvexityCascade", "HedgedConvexity", "QueueReplenishment"
        ])

        self.eval_data: Dict[str, Dict[int, Deque[Tuple[float, float]]]] = {
            s: {h: deque(maxlen=20000) for h in self.bt_cfg.horizons_seconds}
            for s in unique_signals
        }

        # Position lifecycle event log (openings, closures, stop triggers)
        self.position_events: Deque[Dict[str, Any]] = deque(maxlen=200)

        # Rolling 3-minute price amplitude tracking for Volatility Gating
        self.rolling_prices: Deque[Tuple[int, float]] = deque()
        self._min_price_deque: Deque[Tuple[int, float]] = deque()
        self._max_price_deque: Deque[Tuple[int, float]] = deque()
        self.current_volatility_bps: float = 99.0

    def record_step(
        self,
        timestamp_ms: int,
        mid_price: float,
        best_bid: float,
        best_ask: float,
        signals: Dict[str, float],
    ) -> None:
        """Called on every sample step (e.g. 5-10 Hz). Updates forward returns and paper trading."""
        if mid_price <= 0:
            return

        # 1. Buffer observation and update forward returns (bypassed if horizons_seconds is empty)
        if self.bt_cfg.horizons_seconds:
            obs = SignalObservation(
                timestamp_ms=timestamp_ms,
                price=mid_price,
                signals=signals.copy(),
            )
            self.observations.append(obs)
            self._update_forward_returns(timestamp_ms, mid_price)

        # 3. Update rolling 3-minute price amplitude (volatility in bps)
        self.rolling_prices.append((timestamp_ms, mid_price))
        while self._min_price_deque and self._min_price_deque[-1][1] >= mid_price:
            self._min_price_deque.pop()
        self._min_price_deque.append((timestamp_ms, mid_price))

        while self._max_price_deque and self._max_price_deque[-1][1] <= mid_price:
            self._max_price_deque.pop()
        self._max_price_deque.append((timestamp_ms, mid_price))

        cutoff_ms = timestamp_ms - 180_000
        while self.rolling_prices and self.rolling_prices[0][0] < cutoff_ms:
            self.rolling_prices.popleft()
        while self._min_price_deque and self._min_price_deque[0][0] < cutoff_ms:
            self._min_price_deque.popleft()
        while self._max_price_deque and self._max_price_deque[0][0] < cutoff_ms:
            self._max_price_deque.popleft()

        if len(self.rolling_prices) >= 15:
            if not hasattr(self, "_last_vol_calc_ms") or (timestamp_ms - self._last_vol_calc_ms) >= 1000:
                self._last_vol_calc_ms = timestamp_ms
                p_min = self._min_price_deque[0][1]
                p_max = self._max_price_deque[0][1]
                self.current_volatility_bps = ((p_max - p_min) / mid_price) * 10_000.0 if mid_price > 0 else 0.0
        else:
            self.current_volatility_bps = 99.0  # Warmup

        # 4. Simulate paper trading with improved entry and exit
        self._update_paper_trading(timestamp_ms, mid_price, best_bid, best_ask, signals)

    def _update_forward_returns(self, current_time_ms: int, current_price: float) -> None:
        """Matches past observations with current price once horizon elapses."""
        num_horizons = len(self.bt_cfg.horizons_seconds)
        # Prune fully evaluated observations from the front of the queue
        while self.observations and len(self.observations[0].evaluated_horizons) >= num_horizons:
            self.observations.popleft()

        for obs in self.observations:
            if len(obs.evaluated_horizons) >= num_horizons:
                continue

            elapsed_secs = (current_time_ms - obs.timestamp_ms) / 1000.0
            if elapsed_secs < 1.0:
                continue

            for h in self.bt_cfg.horizons_seconds:
                if elapsed_secs >= h and h not in obs.evaluated_horizons:
                    obs.evaluated_horizons.add(h)
                    fwd_return = (current_price - obs.price) / obs.price
                    for s_name, s_val in obs.signals.items():
                        if s_name in self.eval_data and h in self.eval_data[s_name]:
                            self.eval_data[s_name][h].append((s_val, fwd_return))

    def _update_paper_trading(
        self,
        timestamp_ms: int,
        mid_price: float,
        best_bid: float,
        best_ask: float,
        signals: Dict[str, float],
    ) -> None:
        """Executes simulated paper trades with realistic fee, spread, and trailing stop mechanics."""
        taker_fee_pct = self.market_cfg.taker_fee_bps / 10_000.0
        maker_fee_pct = getattr(self.market_cfg, "maker_fee_bps", 1.5) / 10_000.0
        maker_rebate_pct = getattr(self.market_cfg, "maker_rebate_bps", 1.5) / 10_000.0
        fee_hurdle_bps = getattr(self.market_cfg, "taker_fee_bps", 4.5)
        slippage_pct = self.bt_cfg.slippage_bps / 10_000.0
        spread_bps = ((best_ask - best_bid) / mid_price) * 10_000.0 if mid_price > 0 else 1.0

        tp_bps = self.bt_cfg.take_profit_bps
        sl_bps = self.bt_cfg.stop_loss_bps
        trail_act_bps = self.bt_cfg.trailing_stop_activation_bps
        trail_dist_bps = self.bt_cfg.trailing_stop_distance_bps
        reversal_thresh = self.bt_cfg.exit_reversal_threshold

        for s_name in self.strategy_names:
            state = self.strategies[s_name]
            sig_k = state.signal_key
            score = signals.get(sig_k, 0.0)
            is_maker = (state.execution_type in ("MAKER", "HEDGED_MAKER"))

            # Strategy-specific execution parameters (with per-strategy overrides)
            params = self.strategy_params.get(s_name, {})
            if is_maker:
                entry_thresh = params.get("entry_threshold", self.bt_cfg.entry_threshold)
                tp_bps = params.get("take_profit_bps", self.bt_cfg.take_profit_bps)
                sl_bps = params.get("stop_loss_bps", self.bt_cfg.stop_loss_bps)
                trail_act_bps = params.get("trailing_stop_activation_bps", self.bt_cfg.trailing_stop_activation_bps)
                trail_dist_bps = params.get("trailing_stop_distance_bps", self.bt_cfg.trailing_stop_distance_bps)
                reversal_thresh = params.get("exit_reversal_threshold", self.bt_cfg.exit_reversal_threshold)
                max_hold_secs = params.get("max_holding_time_secs", self.bt_cfg.max_holding_time_secs)
                hedge_trigger_loss_bps = params.get("hedge_trigger_loss_bps", -3.0)
                hedge_reversal_threshold = params.get("hedge_reversal_threshold", -0.15)
            else:
                entry_thresh = params.get("entry_threshold", self.bt_cfg.entry_threshold_taker)
                tp_bps = params.get("take_profit_bps", self.bt_cfg.take_profit_bps_taker)
                sl_bps = params.get("stop_loss_bps", self.bt_cfg.stop_loss_bps_taker)
                trail_act_bps = params.get("trailing_stop_activation_bps", self.bt_cfg.trailing_stop_activation_bps_taker)
                trail_dist_bps = params.get("trailing_stop_distance_bps", self.bt_cfg.trailing_stop_distance_bps_taker)
                reversal_thresh = params.get("exit_reversal_threshold", self.bt_cfg.exit_reversal_threshold_taker)
                max_hold_secs = params.get("max_holding_time_secs", self.bt_cfg.max_holding_time_secs_taker)

            # Update drawdown tracking
            eq = state.current_equity(mid_price)
            if eq > state.peak_equity:
                state.peak_equity = eq
            dd = state.peak_equity - eq
            if dd > state.max_drawdown_usd:
                state.max_drawdown_usd = dd

            # =========================================================================
            # A. POSITION MANAGEMENT & ADVANCED EXITS
            # =========================================================================
            if state.is_in_position:
                is_long = state.position_btc > 0
                holding_time_secs = (timestamp_ms - state.entry_time_ms) / 1000.0

                if is_long:
                    # Long position tracking
                    state.peak_price = max(state.peak_price, mid_price)
                    gain_bps = ((mid_price - state.entry_price) / state.entry_price) * 10_000.0
                    state.peak_unrealized_bps = max(state.peak_unrealized_bps, gain_bps)
                    state.trough_unrealized_bps = min(state.trough_unrealized_bps, gain_bps)

                    # 1. Trailing Stop Activation & Ratchet
                    if gain_bps >= trail_act_bps:
                        state.trailing_stop_active = True
                        trailing_floor = state.peak_price * (1.0 - (trail_dist_bps / 10_000.0))
                        if not is_maker:
                            fee_pct = taker_fee_pct + (maker_rebate_pct if self.bt_cfg.taker_exit_as_maker_on_tp else taker_fee_pct)
                            fee_floor = state.entry_price * (1.0 + fee_pct)
                            if state.peak_price > fee_floor:
                                trailing_floor = max(trailing_floor, fee_floor)
                        else:
                            # Break-even fee ratchet for Maker: guarantees trailing floor clears 3 bps round-trip fee
                            round_trip_fee_pct = 2.0 * maker_fee_pct
                            fee_floor = state.entry_price * (1.0 + round_trip_fee_pct + 0.00005)
                            if state.peak_price > fee_floor:
                                trailing_floor = max(trailing_floor, fee_floor)
                        state.stop_price = max(state.stop_price, trailing_floor)

                    # 2. Check Exit Conditions
                    exit_reason = None
                    if gain_bps >= tp_bps:
                        exit_reason = "TAKE_PROFIT"
                    elif (state.execution_type == "HEDGED_MAKER" or "hedge_trigger_loss_bps" in params) and score <= hedge_reversal_threshold and gain_bps <= hedge_trigger_loss_bps:
                        exit_reason = "DEFENSIVE_MAKER_HEDGE"
                    elif mid_price <= state.stop_price:
                        exit_reason = "TRAILING_STOP" if state.trailing_stop_active else "STOP_LOSS"
                    elif score <= -reversal_thresh and (gain_bps >= fee_hurdle_bps or gain_bps <= -8.0):
                        exit_reason = "SIGNAL_REVERSAL"
                    elif state.peak_unrealized_bps >= 4.0 and gain_bps <= 0.5 and score <= 0.0:
                        exit_reason = "PROFIT_DECAY_EXIT"  # Was profitable, decayed back to breakeven
                    elif holding_time_secs >= max_hold_secs and gain_bps <= 0.0 and score <= 0.10:
                        exit_reason = "TIME_LIMIT"
                    elif holding_time_secs >= max_hold_secs * 2.0:
                        exit_reason = "TIME_LIMIT"

                    if exit_reason:
                        # Determine exit execution price and fees
                        if is_maker and exit_reason != "STOP_LOSS":
                            if exit_reason in ("TRAILING_STOP", "TAKE_PROFIT"):
                                # Passive resting maker limit fill: fills at or better than limit order price
                                target_limit = state.stop_price if exit_reason == "TRAILING_STOP" else state.entry_price * (1.0 + tp_bps / 10_000.0)
                                exit_price = max(best_ask, target_limit)
                            else:
                                exit_price = best_ask
                            fee = exit_price * state.position_btc * maker_fee_pct
                            exec_label = "MAKER"
                        elif not is_maker and exit_reason != "STOP_LOSS" and self.bt_cfg.taker_exit_as_maker_on_tp:
                            # Smart Taker exits all orderly conditions passively as Maker
                            exit_price = best_ask
                            fee = exit_price * state.position_btc * maker_fee_pct
                            exec_label = f"MAKER ({exit_reason[:4]})"
                        else:
                            # Emergency market stop loss at best bid
                            exit_price = best_bid * (1.0 - slippage_pct)
                            fee = exit_price * state.position_btc * taker_fee_pct
                            exec_label = "TAKER"

                        sz = state.position_btc
                        exit_fee = fee
                        total_fees = state.entry_fee_usd + exit_fee
                        gross_pnl = (exit_price - state.entry_price) * sz
                        net_pnl = gross_pnl - total_fees
                        state.cash_usd += (gross_pnl - exit_fee)
                        return_bps = (net_pnl / (state.entry_price * sz)) * 10_000.0

                        record = TradeRecord(
                            strategy_name=s_name,
                            entry_time_ms=state.entry_time_ms,
                            exit_time_ms=timestamp_ms,
                            side="LONG",
                            entry_price=state.entry_price,
                            exit_price=exit_price,
                            size_btc=sz,
                            gross_pnl_usd=gross_pnl,
                            fees_usd=total_fees,
                            net_pnl_usd=net_pnl,
                            return_bps=return_bps,
                            exit_reason=exit_reason,
                            execution_type=exec_label,
                        )
                        state.trades.append(record)

                        if self.auditor:
                            self.auditor.record_trade(
                                strategy_name=s_name,
                                side="LONG",
                                execution_type=exec_label,
                                entry_time_ms=state.entry_time_ms,
                                exit_time_ms=timestamp_ms,
                                entry_price=state.entry_price,
                                exit_price=exit_price,
                                size_btc=sz,
                                gross_pnl_usd=gross_pnl,
                                entry_fee_usd=state.entry_fee_usd,
                                exit_fee_usd=exit_fee,
                                net_pnl_usd=net_pnl,
                                return_bps=return_bps,
                                exit_reason=exit_reason,
                                entry_signal_score=state.entry_signal_score,
                                exit_signal_score=score,
                                peak_unrealized_bps=state.peak_unrealized_bps,
                                trough_unrealized_bps=state.trough_unrealized_bps,
                                strategy_equity_after=state.cash_usd,
                                strategy_drawdown_after=state.max_drawdown_usd,
                            )

                        self.position_events.append({
                            "time_ms": timestamp_ms,
                            "event": "CLOSE",
                            "strategy": s_name,
                            "side": "LONG",
                            "size_btc": sz,
                            "price": exit_price,
                            "exec": exec_label,
                            "reason": exit_reason,
                            "net_pnl": net_pnl,
                            "return_bps": return_bps,
                        })
                        state.position_btc = 0.0
                        state.entry_price = 0.0
                        state.entry_fee_usd = 0.0
                        state.trailing_stop_active = False
                        state.peak_unrealized_bps = 0.0
                        state.trough_unrealized_bps = 0.0
                        state.last_exit_time_ms = timestamp_ms
                        state.last_exit_was_loss = (net_pnl < 0.0)
                        if net_pnl < 0.0:
                            state.consecutive_losses += 1
                        else:
                            state.consecutive_losses = 0

                else:
                    # Short position tracking
                    state.trough_price = min(state.trough_price, mid_price)
                    gain_bps = ((state.entry_price - mid_price) / state.entry_price) * 10_000.0
                    state.peak_unrealized_bps = max(state.peak_unrealized_bps, gain_bps)
                    state.trough_unrealized_bps = min(state.trough_unrealized_bps, gain_bps)

                    # 1. Trailing Stop Activation & Ratchet
                    if gain_bps >= trail_act_bps:
                        state.trailing_stop_active = True
                        trailing_ceiling = state.trough_price * (1.0 + (trail_dist_bps / 10_000.0))
                        if not is_maker:
                            fee_pct = taker_fee_pct + (maker_rebate_pct if self.bt_cfg.taker_exit_as_maker_on_tp else taker_fee_pct)
                            fee_ceiling = state.entry_price * (1.0 - fee_pct)
                            if state.trough_price < fee_ceiling:
                                trailing_ceiling = min(trailing_ceiling, fee_ceiling)
                        else:
                            # Break-even fee ratchet for Maker Short: guarantees trailing ceiling clears 3 bps round-trip fee
                            round_trip_fee_pct = 2.0 * maker_fee_pct
                            fee_ceiling = state.entry_price * (1.0 - round_trip_fee_pct - 0.00005)
                            if state.trough_price < fee_ceiling:
                                trailing_ceiling = min(trailing_ceiling, fee_ceiling)
                        state.stop_price = min(state.stop_price, trailing_ceiling)

                    # 2. Check Exit Conditions
                    exit_reason = None
                    if gain_bps >= tp_bps:
                        exit_reason = "TAKE_PROFIT"
                    elif (state.execution_type == "HEDGED_MAKER" or "hedge_trigger_loss_bps" in params) and score >= -hedge_reversal_threshold and gain_bps <= hedge_trigger_loss_bps:
                        exit_reason = "DEFENSIVE_MAKER_HEDGE"
                    elif mid_price >= state.stop_price:
                        exit_reason = "TRAILING_STOP" if state.trailing_stop_active else "STOP_LOSS"
                    elif score >= reversal_thresh and (gain_bps >= fee_hurdle_bps or gain_bps <= -8.0):
                        exit_reason = "SIGNAL_REVERSAL"
                    elif state.peak_unrealized_bps >= 4.0 and gain_bps <= 0.5 and score >= 0.0:
                        exit_reason = "PROFIT_DECAY_EXIT"  # Was profitable, decayed back to breakeven
                    elif holding_time_secs >= max_hold_secs and gain_bps <= 0.0 and score >= -0.10:
                        exit_reason = "TIME_LIMIT"
                    elif holding_time_secs >= max_hold_secs * 2.0:
                        exit_reason = "TIME_LIMIT"

                    if exit_reason:
                        if is_maker and exit_reason != "STOP_LOSS":
                            if exit_reason in ("TRAILING_STOP", "TAKE_PROFIT"):
                                # Passive resting maker limit fill: fills at or better than limit order price
                                target_limit = state.stop_price if exit_reason == "TRAILING_STOP" else state.entry_price * (1.0 - tp_bps / 10_000.0)
                                exit_price = min(best_bid, target_limit)
                            else:
                                exit_price = best_bid
                            fee = exit_price * abs(state.position_btc) * maker_fee_pct
                            exec_label = "MAKER"
                        elif not is_maker and exit_reason != "STOP_LOSS" and self.bt_cfg.taker_exit_as_maker_on_tp:
                            # Smart Taker exits all orderly conditions passively as Maker
                            exit_price = best_bid
                            fee = exit_price * abs(state.position_btc) * maker_fee_pct
                            exec_label = f"MAKER ({exit_reason[:4]})"
                        else:
                            exit_price = best_ask * (1.0 + slippage_pct)
                            fee = exit_price * abs(state.position_btc) * taker_fee_pct
                            exec_label = "TAKER"

                        sz = abs(state.position_btc)
                        exit_fee = fee
                        total_fees = state.entry_fee_usd + exit_fee
                        gross_pnl = (state.entry_price - exit_price) * sz
                        net_pnl = gross_pnl - total_fees
                        state.cash_usd += (gross_pnl - exit_fee)
                        return_bps = (net_pnl / (state.entry_price * sz)) * 10_000.0

                        record = TradeRecord(
                            strategy_name=s_name,
                            entry_time_ms=state.entry_time_ms,
                            exit_time_ms=timestamp_ms,
                            side="SHORT",
                            entry_price=state.entry_price,
                            exit_price=exit_price,
                            size_btc=sz,
                            gross_pnl_usd=gross_pnl,
                            fees_usd=total_fees,
                            net_pnl_usd=net_pnl,
                            return_bps=return_bps,
                            exit_reason=exit_reason,
                            execution_type=exec_label,
                        )
                        state.trades.append(record)

                        if self.auditor:
                            self.auditor.record_trade(
                                strategy_name=s_name,
                                side="SHORT",
                                execution_type=exec_label,
                                entry_time_ms=state.entry_time_ms,
                                exit_time_ms=timestamp_ms,
                                entry_price=state.entry_price,
                                exit_price=exit_price,
                                size_btc=sz,
                                gross_pnl_usd=gross_pnl,
                                entry_fee_usd=state.entry_fee_usd,
                                exit_fee_usd=exit_fee,
                                net_pnl_usd=net_pnl,
                                return_bps=return_bps,
                                exit_reason=exit_reason,
                                entry_signal_score=state.entry_signal_score,
                                exit_signal_score=score,
                                peak_unrealized_bps=state.peak_unrealized_bps,
                                trough_unrealized_bps=state.trough_unrealized_bps,
                                strategy_equity_after=state.cash_usd,
                                strategy_drawdown_after=state.max_drawdown_usd,
                            )

                        self.position_events.append({
                            "time_ms": timestamp_ms,
                            "event": "CLOSE",
                            "strategy": s_name,
                            "side": "SHORT",
                            "size_btc": sz,
                            "price": exit_price,
                            "exec": exec_label,
                            "reason": exit_reason,
                            "net_pnl": net_pnl,
                            "return_bps": return_bps,
                        })
                        state.position_btc = 0.0
                        state.entry_price = 0.0
                        state.entry_fee_usd = 0.0
                        state.trailing_stop_active = False
                        state.peak_unrealized_bps = 0.0
                        state.trough_unrealized_bps = 0.0
                        state.last_exit_time_ms = timestamp_ms
                        state.last_exit_was_loss = (net_pnl < 0.0)
                        if net_pnl < 0.0:
                            state.consecutive_losses += 1
                        else:
                            state.consecutive_losses = 0

            # =========================================================================
            # B. SMART ENTRY GATING
            # =========================================================================
            else:
                # Spread Filter: Never enter if spread is abnormally wide
                if spread_bps > self.bt_cfg.max_spread_bps:
                    continue

                # Volatility Gate: Never enter during dead chop where amplitude cannot clear fee hurdle
                min_vol_bps = params.get("min_volatility_bps", getattr(self.bt_cfg, "min_volatility_bps", 0.0))
                if min_vol_bps > 0.0 and self.current_volatility_bps < min_vol_bps:
                    continue

                # Post-Loss Whipsaw Cooldown with Escalation: Prevent rapid-fire churn after loss
                base_cooldown_ms = params.get("loss_cooldown_secs", 60) * 1000
                # Escalate cooldown geometrically: 60s -> 120s -> 240s (cap at 4x base)
                escalation_factor = min(4, 2 ** max(0, state.consecutive_losses - 1)) if state.consecutive_losses > 0 else 1
                loss_cooldown_ms = base_cooldown_ms * escalation_factor
                if state.last_exit_was_loss and (timestamp_ms - state.last_exit_time_ms) < loss_cooldown_ms:
                    continue

                # Co-Entry Protection: If another strategy in the same coentry_group holds a position
                # in the same direction, require higher conviction (+0.04) or discount size
                is_bull_sig = score >= entry_thresh
                is_bear_sig = score <= -entry_thresh
                my_group = params.get("coentry_group", "triad" if s_name in ("Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion") else s_name)
                same_dir_active = any(
                    other_s != s_name and other_st.is_in_position and (
                        self.strategy_params.get(other_s, {}).get("coentry_group", "triad" if other_s in ("Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion") else other_s) == my_group
                    ) and (
                        (other_st.position_btc > 0 and is_bull_sig) or (other_st.position_btc < 0 and is_bear_sig)
                    )
                    for other_s, other_st in self.strategies.items()
                )
                if same_dir_active:
                    # Require elevated conviction hurdle (+0.04) with epsilon tolerance
                    hurdle = round(entry_thresh + 0.04, 6)
                    if (is_bull_sig and score < hurdle - 1e-7) or (is_bear_sig and score > -hurdle + 1e-7):
                        continue

                sz = self.strategy_params.get(s_name, {}).get("order_size_btc", self.bt_cfg.order_size_btc)
                if getattr(self.bt_cfg, "capital_usd", None) is not None and self.bt_cfg.capital_usd > 0:
                    capital_ratio = self.bt_cfg.capital_usd / 10_000.0
                    sz = sz * capital_ratio
                is_coin_units = (sz > 1.0)
                if same_dir_active:
                    sz = sz * 0.5  # 50% size discount on co-entry within the same group
                if self.market_cfg.coin.upper() != "BTC" and mid_price > 0 and not is_coin_units:
                    sz = round(sz * (85000.0 / mid_price), 2)
                elif self.market_cfg.coin.upper() == "BTC":
                    sz = round(sz, 4)
                else:
                    sz = round(sz, 2)


                # Bullish Entry Trigger
                if score >= entry_thresh:
                    if is_maker:
                        # Passive Maker Buy at best bid
                        entry_price = best_bid
                        fee = entry_price * sz * maker_fee_pct
                    else:
                        # Smart Taker Buy
                        entry_price = best_ask * (1.0 + slippage_pct)
                        fee = entry_price * sz * taker_fee_pct

                    state.entry_fee_usd = fee
                    state.cash_usd -= fee
                    state.position_btc = sz
                    state.entry_price = entry_price
                    state.entry_time_ms = timestamp_ms
                    state.peak_price = entry_price
                    state.trailing_stop_active = False
                    state.stop_price = entry_price * (1.0 - (sl_bps / 10_000.0))
                    state.entry_signal_score = score
                    state.peak_unrealized_bps = 0.0
                    state.trough_unrealized_bps = 0.0

                    self.position_events.append({
                        "time_ms": timestamp_ms,
                        "event": "OPEN",
                        "strategy": s_name,
                        "side": "LONG",
                        "size_btc": sz,
                        "price": entry_price,
                        "exec": "MAKER" if is_maker else "TAKER",
                        "reason": f"Sig {score:+.2f}",
                        "stop_price": state.stop_price,
                        "net_pnl": 0.0,
                        "return_bps": 0.0,
                    })

                # Bearish Entry Trigger
                elif score <= -entry_thresh:
                    if is_maker:
                        # Passive Maker Sell at best ask
                        entry_price = best_ask
                        fee = entry_price * sz * maker_fee_pct
                    else:
                        # Smart Taker Sell
                        entry_price = best_bid * (1.0 - slippage_pct)
                        fee = entry_price * sz * taker_fee_pct

                    state.entry_fee_usd = fee
                    state.cash_usd -= fee
                    state.position_btc = -sz
                    state.entry_price = entry_price
                    state.entry_time_ms = timestamp_ms
                    state.trough_price = entry_price
                    state.trailing_stop_active = False
                    state.stop_price = entry_price * (1.0 + (sl_bps / 10_000.0))
                    state.entry_signal_score = score
                    state.peak_unrealized_bps = 0.0
                    state.trough_unrealized_bps = 0.0

                    self.position_events.append({
                        "time_ms": timestamp_ms,
                        "event": "OPEN",
                        "strategy": s_name,
                        "side": "SHORT",
                        "size_btc": sz,
                        "price": entry_price,
                        "exec": "MAKER" if is_maker else "TAKER",
                        "reason": f"Sig {score:+.2f}",
                        "stop_price": state.stop_price,
                        "net_pnl": 0.0,
                        "return_bps": 0.0,
                    })

    def close_open_positions(
        self,
        mid_price: float,
        timestamp_ms: int,
        reason: str = "SESSION_SHUTDOWN",
    ) -> int:
        """Closes any active resting positions at market price upon session completion."""
        closed_count = 0
        taker_fee_pct = self.market_cfg.taker_fee_bps / 10_000.0
        slippage_pct = self.bt_cfg.slippage_bps / 10_000.0

        for s_name in self.strategy_names:
            state = self.strategies[s_name]
            if not state.is_in_position:
                continue

            sz = abs(state.position_btc)
            is_long = state.position_btc > 0
            if is_long:
                exit_price = mid_price * (1.0 - slippage_pct)
                gross_pnl = (exit_price - state.entry_price) * sz
            else:
                exit_price = mid_price * (1.0 + slippage_pct)
                gross_pnl = (state.entry_price - exit_price) * sz

            exit_fee = exit_price * sz * taker_fee_pct
            total_fees = state.entry_fee_usd + exit_fee
            net_pnl = gross_pnl - total_fees
            ret_bps = (net_pnl / (state.entry_price * sz)) * 10_000.0 if (state.entry_price * sz) > 0 else 0.0
            state.cash_usd += (gross_pnl - exit_fee)

            record = TradeRecord(
                strategy_name=s_name,
                entry_time_ms=state.entry_time_ms,
                exit_time_ms=timestamp_ms,
                side="LONG" if is_long else "SHORT",
                entry_price=state.entry_price,
                exit_price=exit_price,
                size_btc=sz,
                gross_pnl_usd=gross_pnl,
                fees_usd=total_fees,
                net_pnl_usd=net_pnl,
                return_bps=ret_bps,
                exit_reason=reason,
                execution_type="TAKER",
            )
            state.trades.append(record)

            if self.auditor:
                self.auditor.record_trade(
                    strategy_name=s_name,
                    side="LONG" if is_long else "SHORT",
                    execution_type=state.execution_type,
                    entry_time_ms=state.entry_time_ms,
                    exit_time_ms=timestamp_ms,
                    entry_price=state.entry_price,
                    exit_price=exit_price,
                    size_btc=sz,
                    gross_pnl_usd=gross_pnl,
                    entry_fee_usd=state.entry_fee_usd,
                    exit_fee_usd=exit_fee,
                    net_pnl_usd=net_pnl,
                    return_bps=ret_bps,
                    exit_reason=reason,
                    entry_signal_score=state.entry_signal_score,
                    exit_signal_score=0.0,
                    peak_unrealized_bps=state.peak_unrealized_bps,
                    trough_unrealized_bps=state.trough_unrealized_bps,
                    strategy_equity_after=state.cash_usd,
                    strategy_drawdown_after=state.max_drawdown_usd,
                    notes=f"Closed at session shutdown @ ${exit_price:,.1f}",
                )

            self.position_events.append({
                "time_ms": timestamp_ms,
                "event": "CLOSE",
                "strategy": s_name,
                "side": "LONG" if is_long else "SHORT",
                "size_btc": sz,
                "price": exit_price,
                "exec": "TAKER",
                "reason": reason,
                "net_pnl": net_pnl,
                "return_bps": ret_bps,
            })

            state.position_btc = 0.0
            state.entry_price = 0.0
            state.entry_fee_usd = 0.0
            state.trailing_stop_active = False
            state.peak_unrealized_bps = 0.0
            state.trough_unrealized_bps = 0.0
            closed_count += 1

        return closed_count

    def get_signal_metrics(self, strategy_or_signal_name: str, horizon_secs: int = 5) -> Dict[str, Any]:
        """Calculates IC, Rank IC, t-stat, p-value, and directional hit rate for the underlying signal."""
        # Resolve strategy name to signal key if applicable
        signal_key = strategy_or_signal_name
        if strategy_or_signal_name in self.strategy_defs:
            signal_key = self.strategy_defs[strategy_or_signal_name][0]

        pairs = self.eval_data.get(signal_key, {}).get(horizon_secs, [])
        if len(pairs) < 5:
            return {
                "samples": len(pairs),
                "ic": 0.0,
                "rank_ic": 0.0,
                "t_stat": 0.0,
                "p_val": 1.0,
                "hit_rate": 50.0,
            }

        sigs = np.array([p[0] for p in pairs])
        rets = np.array([p[1] for p in pairs])

        # Directional hit rate (evaluated on active price moves |ret| > 0.01 bps)
        active_mask = (np.abs(sigs) > 0.02) & (np.abs(rets) > 0.01)
        if np.sum(active_mask) >= 3:
            hits = (np.sign(sigs[active_mask]) == np.sign(rets[active_mask]))
            hit_rate = float(np.mean(hits)) * 100.0
        else:
            mask = np.abs(sigs) > 0.02
            if np.sum(mask) >= 3:
                hits = (np.sign(sigs[mask]) == np.sign(rets[mask]))
                hit_rate = float(np.mean(hits)) * 100.0
            else:
                hit_rate = 50.0

        # Pearson and Spearman IC
        if np.std(sigs) > 1e-7 and np.std(rets) > 1e-7:
            ic, p_val = stats.pearsonr(sigs, rets)
            rank_ic, _ = stats.spearmanr(sigs, rets)
            n = len(sigs)
            t_stat = ic * math.sqrt((n - 2) / max(1e-6, 1.0 - ic**2))
        else:
            ic, rank_ic, t_stat, p_val = 0.0, 0.0, 0.0, 1.0

        return {
            "samples": len(pairs),
            "ic": float(ic),
            "rank_ic": float(rank_ic),
            "t_stat": float(t_stat),
            "p_val": float(p_val),
            "hit_rate": float(hit_rate),
        }

    def get_strategy_performance(self, strategy_name: str, current_price: float) -> Dict[str, Any]:
        """Computes comprehensive paper-trading performance metrics."""
        state = self.strategies.get(strategy_name)
        if not state:
            return {}

        trades = state.trades
        n_trades = len(trades)
        net_pnl = sum(t.net_pnl_usd for t in trades)
        gross_pnl = sum(t.gross_pnl_usd for t in trades)
        unrealized = (
            state.position_btc * (current_price - state.entry_price)
            if state.is_in_position
            else 0.0
        )
        total_pnl = net_pnl + unrealized
        total_gross_pnl = gross_pnl + unrealized
        total_fees = sum(t.fees_usd for t in trades) + (state.entry_fee_usd if state.is_in_position else 0.0)

        if n_trades > 0:
            wins = [t for t in trades if t.net_pnl_usd > 0]
            losses = [t for t in trades if t.net_pnl_usd <= 0]
            win_rate = (len(wins) / n_trades) * 100.0
            gross_win = sum(t.net_pnl_usd for t in wins)
            gross_loss = abs(sum(t.net_pnl_usd for t in losses))
            profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 1.0)
            pnl_returns = [t.return_bps for t in trades]
            avg_return_bps = float(np.mean(pnl_returns))
            std_return_bps = float(np.std(pnl_returns)) if len(pnl_returns) > 1 else 1.0
            sharpe = (avg_return_bps / std_return_bps) * math.sqrt(252 * 24 * 60) if std_return_bps > 0 else 0.0
        else:
            win_rate = 0.0
            profit_factor = 0.0
            sharpe = 0.0
            avg_return_bps = 0.0

        return {
            "strategy": strategy_name,
            "type": state.execution_type,
            "trades": n_trades,
            "gross_pnl_usd": total_gross_pnl,
            "realized_gross_pnl_usd": gross_pnl,
            "total_pnl_usd": total_pnl,
            "net_pnl_usd": total_pnl,
            "realized_pnl_usd": net_pnl,
            "unrealized_pnl_usd": unrealized,
            "fees_paid_usd": total_fees,
            "win_rate_pct": win_rate,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe,
            "max_drawdown_usd": state.max_drawdown_usd,
            "in_position": state.is_in_position,
            "position_btc": state.position_btc,
            "avg_return_bps": avg_return_bps,
        }

    @property
    def execution_strategy_names(self) -> List[str]:
        """Returns list of the 4 new primary execution strategy names currently active in evaluator."""
        return [s for s in self.strategy_names if getattr(self.strategies.get(s), "category", "execution") == "execution"]

    @property
    def scalping_strategy_names(self) -> List[str]:
        """Returns list of legacy scalping strategy names currently active in evaluator."""
        return [s for s in self.strategy_names if getattr(self.strategies.get(s), "category", "execution") == "scalping"]

    def get_active_positions(self, current_price: float, now_ms: Optional[int] = None) -> List[Dict[str, Any]]:
        """Returns details on all currently open strategy positions."""
        now = now_ms or int(time.time() * 1000)
        positions = []
        for s_name in self.strategy_names:
            state = self.strategies[s_name]
            if state.is_in_position:
                is_long = state.position_btc > 0
                sz = abs(state.position_btc)
                unrealized = state.position_btc * (current_price - state.entry_price)
                unrealized_bps = (
                    ((current_price - state.entry_price) / state.entry_price)
                    * 10_000.0
                    * (1.0 if is_long else -1.0)
                )
                hold_secs = max(0.0, (now - state.entry_time_ms) / 1000.0)
                positions.append({
                    "strategy": s_name,
                    "side": "LONG" if is_long else "SHORT",
                    "size_btc": sz,
                    "entry_price": state.entry_price,
                    "current_price": current_price,
                    "unrealized_pnl_usd": unrealized,
                    "unrealized_bps": unrealized_bps,
                    "stop_price": state.stop_price,
                    "trailing_active": state.trailing_stop_active,
                    "hold_secs": hold_secs,
                    "exec": state.execution_type,
                })
        return positions

    def get_recent_position_events(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Returns the most recent position lifecycle events (OPEN & CLOSE)."""
        return list(self.position_events)[-limit:]


# Backwards compatibility alias
BacktesterEngine = EdgeEvaluator
