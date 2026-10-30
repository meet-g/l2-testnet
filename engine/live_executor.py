"""Live Order Execution Manager for Hyperliquid Testnet & Mainnet.

Bridges high-conviction microstructure alpha signals (Hedged Convexity, Convexity Cascade,
Momentum Expansion, Queue Replenishment, Composite Alpha) directly to the live Hyperliquid
order book via the official SDK with comprehensive risk guardrails.
"""

import logging
import math
import sys
import time
from typing import Any, Dict, List, Optional

# Ensure standard output and error support unicode symbols (✓ / ✗) on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import eth_account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from rich.console import Console

from config import AppConfig, canonicalize_coin_symbol


class LiveOrderExecutor:
    """Manages real-time order placement, cancellation, stateful tracking, and risk management on Hyperliquid."""

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        console: Optional[Console] = None,
        max_position_btc: float = 0.05,
        default_order_size_btc: float = 0.0005,
        capital_usd: Optional[float] = None,
        allocation_pct: float = 1.0,
        order_cooldown_secs: float = 2.0,
        auditor: Optional[Any] = None,
        strategy_name: str = "LiveExecution",
    ):
        self.config = config or AppConfig()
        self.console = console or Console()
        self.max_position_btc = max_position_btc
        self.default_order_size_btc = default_order_size_btc
        self.capital_usd = capital_usd if capital_usd is not None else getattr(self.config.backtest, "capital_usd", None)
        self.allocation_pct = allocation_pct if allocation_pct is not None else getattr(self.config.backtest, "capital_allocation_pct", 1.0)
        self.order_cooldown_secs = order_cooldown_secs
        self.auditor = auditor
        self.strategy_name = strategy_name

        self.account_address = self.config.account.account_address
        self.secret_key = self.config.account.secret_key
        self.coin = canonicalize_coin_symbol(self.config.market.coin)
        self.dex = self.coin.split(":")[0] if ":" in self.coin else ""
        self.base_url = (
            constants.TESTNET_API_URL
            if self.config.hyperliquid.use_testnet
            else constants.MAINNET_API_URL
        )

        self.last_order_time: float = 0.0
        self.active_order_oids: List[int] = []
        self.exchange: Optional[Exchange] = None
        self.info: Optional[Info] = None
        self.is_initialized: bool = False

        # Asset metadata specifications
        self.sz_decimals: int = 5
        self.max_price_decimals: int = 1
        self.max_leverage: int = 40

        # Margin and account state
        self.account_value: float = 0.0
        self.available_margin: float = 0.0

        # Stateful local position & order management (prevents hot-loop REST blocking)
        self.cached_position: float = 0.0
        self.entry_price: float = 0.0
        self.peak_price: float = 0.0
        self.trough_price: float = 0.0
        self.trailing_stop_active: bool = False
        self.stop_loss_trigger_time: float = 0.0
        self.last_sync_time: float = 0.0
        self.active_order: Optional[Dict[str, Any]] = None  # {"oid": int, "is_buy": bool, "price": float, "size": float, "time": float}
        self.position_strategy: Optional[str] = None  # Strategy that opened current position

        self._initialize()

    def _initialize(self) -> None:
        """Initializes Hyperliquid SDK client with configured wallet, account address, and coin metadata."""
        if not self.secret_key:
            self.console.print("[dim yellow][LiveExecutor] No secret key configured; live execution disabled.[/dim yellow]")
            return

        try:
            wallet = eth_account.Account.from_key(self.secret_key)
            perp_dexs = ["", "xyz"] if self.coin.startswith("xyz:") else None
            self.info = Info(self.base_url, skip_ws=True, perp_dexs=perp_dexs)
            self.exchange = Exchange(
                wallet=wallet,
                base_url=self.base_url,
                account_address=self.account_address if self.account_address else None,
                perp_dexs=perp_dexs,
            )

            # Retrieve asset decimals and specifications from exchange metadata
            try:
                if self.coin.startswith("xyz:"):
                    meta = self.info.meta(dex="xyz")
                else:
                    meta = self.info.meta()
                universe = meta.get("universe", [])
                coin_meta = next((c for c in universe if c.get("name") == self.coin), None)
                if not coin_meta and not self.coin.startswith("xyz:"):
                    # Check builder DEX 'xyz' as fallback
                    try:
                        meta_xyz = self.info.meta(dex="xyz")
                        coin_meta = next((c for c in meta_xyz.get("universe", []) if c.get("name") in (self.coin, f"xyz:{self.coin}")), None)
                    except Exception:
                        pass

                if coin_meta:
                    self.sz_decimals = int(coin_meta.get("szDecimals", 2 if self.coin.startswith("xyz:") else 5))
                    self.max_price_decimals = max(0, 6 - self.sz_decimals)
                    self.max_leverage = int(coin_meta.get("maxLeverage", 10 if self.coin.startswith("xyz:") else 40))
            except Exception as meta_err:
                logging.warning(f"[LiveExecutor] Could not retrieve meta specifications for {self.coin}: {meta_err}")

            self.is_initialized = True
            signer_addr = wallet.address
            network_label = "TESTNET" if self.config.hyperliquid.use_testnet else "MAINNET"
            self.console.print(
                f"[bold green]✓ [LiveExecutor] Connected to Hyperliquid {network_label}![/bold green] "
                f"Master: [dim]{self.account_address[:8]}...[/dim] | Signer: [dim]{signer_addr[:8]}...[/dim] | "
                f"Coin: [bold cyan]{self.coin}[/bold cyan] (szDec: {self.sz_decimals}, maxPxDec: {self.max_price_decimals})"
            )

            # Perform initial state sync
            self.sync_state(force=True)

        except Exception as e:
            self.console.print(f"[bold red]✗ [LiveExecutor] Initialization failed: {e}[/bold red]")
            self.is_initialized = False

    def format_price(self, price: float) -> float:
        """Formats price conforming to Hyperliquid's 5 significant figures and max decimal rules."""
        if price <= 0:
            return 0.0
        # Hyperliquid requires max 5 significant figures
        formatted = f"{price:.5g}"
        val = float(formatted)
        return round(val, self.max_price_decimals)

    def format_size(self, size: float) -> float:
        """Formats order size conforming to asset's szDecimals."""
        if self.sz_decimals == 0:
            return float(int(round(size)))
        return round(size, self.sz_decimals)

    def ensure_min_notional(self, size: float, price: float) -> float:
        """Ensures order size achieves at least $15.00 notional (safely above the $10 exchange minimum)."""
        if price <= 0:
            return self.format_size(size)
        notional = size * price
        if notional < 15.0:
            # Upgrade size to achieve ~$20.00 notional
            target_size = 20.0 / price
            upgraded = self.format_size(target_size)
            if self.sz_decimals == 0 and upgraded < 1.0:
                upgraded = 1.0
            return max(self.format_size(size), upgraded)
        return self.format_size(size)

    def sync_state(self, force: bool = False) -> None:
        """Synchronizes on-chain positions and open orders. Throttled to max once every 5.0s to avoid rate limiting."""
        if not self.is_initialized or not self.info or not self.account_address:
            return

        now = time.time()
        if not force and (now - self.last_sync_time < 5.0):
            return
        self.last_sync_time = now

        try:
            # Sync user position and margin summary
            user_state = self.info.user_state(self.account_address, dex=self.dex) if self.dex else self.info.user_state(self.account_address)
            if isinstance(user_state, dict):
                margin_summary = user_state.get("marginSummary", {})
                if isinstance(margin_summary, dict):
                    try:
                        self.account_value = float(margin_summary.get("accountValue", 0.0))
                    except (ValueError, TypeError):
                        pass
                withdrawable_val = user_state.get("withdrawable")
                if withdrawable_val is not None:
                    try:
                        self.available_margin = float(withdrawable_val)
                    except (ValueError, TypeError):
                        self.available_margin = self.account_value
                elif self.account_value > 0:
                    self.available_margin = self.account_value

            pos_found = False
            raw_positions = user_state.get("assetPositions", []) if isinstance(user_state, dict) else (user_state.get("assetPositions", []) if hasattr(user_state, "get") else [])
            for p in raw_positions:
                pos = p.get("position", {}) if isinstance(p, dict) else (p.get("position", {}) if hasattr(p, "get") else {})
                if isinstance(pos, dict) and pos.get("coin") == self.coin:
                    self.cached_position = float(pos.get("szi", 0.0))
                    entry_px = float(pos.get("entryPx", 0.0))
                    if entry_px > 0:
                        self.entry_price = entry_px
                    pos_found = True
                    break

            if not pos_found:
                self.cached_position = 0.0
                self.entry_price = 0.0
                self.trailing_stop_active = False

            # Sync open orders for this coin
            open_orders = self.info.open_orders(self.account_address, dex=self.dex) if self.dex else self.info.open_orders(self.account_address)
            if isinstance(open_orders, list):
                coin_orders = [o for o in open_orders if isinstance(o, dict) and o.get("coin") == self.coin]
                self.active_order_oids = [int(o["oid"]) for o in coin_orders if "oid" in o]

                if not coin_orders:
                    self.active_order = None
                else:
                    first_o = coin_orders[0]
                    oid_val = int(first_o["oid"])
                    is_buy_order = first_o.get("side", "B") == "B"
                    prev_strat = self.active_order.get("strategy_name", self.strategy_name) if (self.active_order and self.active_order.get("oid") == oid_val) else self.strategy_name
                    prev_is_exit = self.active_order.get("is_exit", abs(self.cached_position) > 1e-6) if (self.active_order and self.active_order.get("oid") == oid_val) else (abs(self.cached_position) > 1e-6)
                    prev_time = self.active_order.get("time", now) if (self.active_order and self.active_order.get("oid") == oid_val) else now
                    self.active_order = {
                        "oid": oid_val,
                        "is_buy": is_buy_order,
                        "price": float(first_o.get("limitPx", 0.0)),
                        "size": float(first_o.get("sz", 0.0)),
                        "time": prev_time,
                        "strategy_name": prev_strat,
                        "is_exit": prev_is_exit,
                    }
        except Exception as e:
            logging.debug(f"[LiveExecutor] State sync exception: {e}")

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """Fetches active resting limit orders from Hyperliquid exchange."""
        if not self.info or not self.account_address:
            return []
        try:
            return self.info.open_orders(self.account_address, dex=self.dex) if self.dex else self.info.open_orders(self.account_address)
        except Exception:
            return []

    def close_position(self, slippage: float = 0.05) -> Optional[Dict[str, Any]]:
        """Closes any active live on-chain position immediately via market close order."""
        if not self.is_initialized or not self.exchange:
            return None
        self.cancel_all_orders()
        try:
            res = self.exchange.market_close(self.coin, slippage=slippage)
            self.sync_state(force=True)
            self.console.print(f"[bold yellow][LiveExecutor] Closed live position on {self.coin}: {res}[/bold yellow]")
            return res
        except Exception as e:
            self.console.print(f"[bold red][LiveExecutor] Failed to market close position on {self.coin}: {e}[/bold red]")
            return None

    def get_current_position(self) -> float:
        """Returns the current net position size in asset units (from fast local cache or exchange)."""
        self.sync_state(force=False)
        return self.cached_position

    def cancel_order(self, oid: int) -> bool:
        """Cancels a specific order by ID and updates local tracking."""
        if not self.is_initialized or not self.exchange:
            return False

        try:
            res = self.exchange.cancel(self.coin, oid)
            if res.get("status") == "ok":
                if self.active_order and self.active_order.get("oid") == oid:
                    self.active_order = None
                if oid in self.active_order_oids:
                    self.active_order_oids.remove(oid)
                self.console.print(f"[dim yellow][LiveExecutor] Cancelled order {oid} for {self.coin}[/dim yellow]")
                if self.auditor:
                    self.auditor.record_live_order_event(
                        strategy_name=self.strategy_name,
                        event_type="CANCEL",
                        side="UNKNOWN",
                        size_btc=0.0,
                        price=0.0,
                        order_id=oid,
                        status="ok",
                    )
                return True
            else:
                self.console.print(f"[dim red][LiveExecutor] Failed to cancel order {oid}: {res}[/dim red]")
        except Exception as e:
            self.console.print(f"[dim red][LiveExecutor] Exception cancelling order {oid}: {e}[/dim red]")
        return False

    def cancel_all_orders(self) -> int:
        """Cancels all open orders for the configured coin."""
        if not self.is_initialized or not self.exchange:
            return 0

        cancelled_count = 0
        open_orders = self.get_open_orders()
        for o in open_orders:
            if o.get("coin") == self.coin:
                oid = int(o.get("oid"))
                if self.cancel_order(oid):
                    cancelled_count += 1

        self.active_order = None
        self.active_order_oids.clear()
        return cancelled_count

    def place_limit_order(
        self,
        is_buy: bool,
        size_btc: float,
        price: float,
        post_only: bool = True,
        signal_score: float = 0.0,
        is_exit: bool = False,
        reduce_only: Optional[bool] = None,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """Places a limit order on Hyperliquid (Testnet or Mainnet) with post-only, reduce-only, and cooldown protection."""
        if not self.is_initialized or not self.exchange:
            self.console.print("[dim red][LiveExecutor] Cannot place order: executor not initialized.[/dim red]")
            return None

        # Check order cooldown
        now = time.time()
        if now - self.last_order_time < self.order_cooldown_secs:
            return None

        # Format price and size conforming to Hyperliquid tick rules
        px_fmt = self.format_price(price)
        sz_fmt = self.ensure_min_notional(self.format_size(size_btc), px_fmt)

        notional = sz_fmt * px_fmt
        if notional < 10.0:
            self.console.print(f"[dim yellow][LiveExecutor] Order notional ${notional:.2f} is below $10 minimum requirement.[/dim yellow]")
            return None

        tif = "Alo" if post_only else "Gtc"
        side_str = "BUY" if is_buy else "SELL"
        side_color = "green" if is_buy else "red"
        net_label = "TESTNET" if self.config.hyperliquid.use_testnet else "MAINNET"
        order_reduce_only = is_exit if reduce_only is None else bool(reduce_only)

        self.console.print(
            f"[bold {side_color}][LIVE {net_label} ORDER] [{self.strategy_name}] Submitting {side_str} {sz_fmt} {self.coin} @ ${px_fmt:,.4f} "
            f"(${notional:,.2f} notional, TIF: {tif}{', ReduceOnly' if order_reduce_only else ''})...[/bold {side_color}]"
        )

        if self.auditor:
            self.auditor.record_live_order_event(
                strategy_name=self.strategy_name,
                event_type="SUBMIT",
                side=side_str,
                size_btc=sz_fmt,
                price=px_fmt,
                tif=tif,
                status="submitting",
                signal_score=signal_score,
            )

        try:
            res = self.exchange.order(
                name=self.coin,
                is_buy=is_buy,
                sz=sz_fmt,
                limit_px=px_fmt,
                order_type={"limit": {"tif": tif}},
                reduce_only=order_reduce_only,
            )
            self.last_order_time = now

            if res.get("status") == "ok":
                data = res.get("response", {}).get("data", {})
                statuses = data.get("statuses", [{}])
                first_status = statuses[0] if statuses else {}

                if "resting" in first_status:
                    oid = int(first_status["resting"].get("oid"))
                    self.active_order_oids.append(oid)
                    self.active_order = {
                        "oid": oid,
                        "is_buy": is_buy,
                        "price": px_fmt,
                        "size": sz_fmt,
                        "time": now,
                        "strategy_name": self.strategy_name,
                        "is_exit": is_exit,
                    }
                    self.console.print(f"[bold green]✓ [LiveExecutor] [{self.strategy_name}] Order RESTING on {net_label} Book! OID: {oid}[/bold green]")
                    if self.auditor:
                        self.auditor.record_live_order_event(
                            strategy_name=self.strategy_name,
                            event_type="RESTING",
                            side=side_str,
                            size_btc=sz_fmt,
                            price=px_fmt,
                            tif=tif,
                            order_id=oid,
                            status="ok",
                            signal_score=signal_score,
                        )
                    return res

                elif "filled" in first_status:
                    fill = first_status["filled"]
                    avg_px = float(fill.get("avgPx", px_fmt))
                    total_sz = float(fill.get("totalSz", sz_fmt))
                    oid = int(fill.get("oid", 0))
                    self.cached_position += (total_sz if is_buy else -total_sz)
                    self.entry_price = avg_px
                    self.peak_price = avg_px
                    self.trough_price = avg_px
                    self.trailing_stop_active = False
                    self.active_order = None

                    self.console.print(f"[bold green]✓ [LiveExecutor] Order FILLED immediately! Px: ${avg_px:,.4f} | Sz: {total_sz}[/bold green]")
                    if self.auditor:
                        self.auditor.record_live_order_event(
                            strategy_name=self.strategy_name,
                            event_type="FILLED",
                            side=side_str,
                            size_btc=total_sz,
                            price=avg_px,
                            tif=tif,
                            order_id=oid,
                            status="ok",
                            fill_price=avg_px,
                            fill_size=total_sz,
                            signal_score=signal_score,
                        )
                    return res

                elif "error" in first_status:
                    err_msg = first_status.get("error")
                    self.console.print(f"[bold red]✗ [LiveExecutor] Exchange rejected order: {err_msg}[/bold red]")
                    if "Post only order would have immediately matched" in str(err_msg):
                        self.active_order = None
                    if self.auditor:
                        self.auditor.record_live_order_event(
                            strategy_name=self.strategy_name,
                            event_type="REJECTED",
                            side=side_str,
                            size_btc=sz_fmt,
                            price=px_fmt,
                            tif=tif,
                            status="rejected",
                            error_message=str(err_msg),
                            signal_score=signal_score,
                        )
                    return res
            else:
                self.console.print(f"[bold red]✗ [LiveExecutor] Order failed: {res}[/bold red]")
                if self.auditor:
                    self.auditor.record_live_order_event(
                        strategy_name=self.strategy_name,
                        event_type="REJECTED",
                        side=side_str,
                        size_btc=sz_fmt,
                        price=px_fmt,
                        tif=tif,
                        status="failed",
                        error_message=str(res),
                        signal_score=signal_score,
                    )
                return res

        except Exception as e:
            self.console.print(f"[bold red]✗ [LiveExecutor] Exception during order placement: {e}[/bold red]")
            if self.auditor:
                self.auditor.record_live_order_event(
                    strategy_name=self.strategy_name,
                    event_type="ERROR",
                    side=side_str,
                    size_btc=sz_fmt,
                    price=px_fmt,
                    tif=tif,
                    status="exception",
                    error_message=str(e),
                    signal_score=signal_score,
                )
            return None

    def on_signal_update(
        self,
        signal_score: float,
        best_bid: float,
        best_ask: float,
        spread: float,
        scores: Optional[Dict[str, float]] = None,
    ) -> None:
        """Evaluates signal score, manages resting quotes, inventory positions, and executes full strategy lifecycle.
        
        Fixes:
        1. Stateful Resting Order Persistence: Does NOT cancel active resting maker quotes unless price moves away.
        2. Non-blocking Local Position Tracking: Uses cached state to avoid synchronous HTTP stalls in the async loop.
        3. Full Lifecycle Management: Includes Take Profit, Stop Loss, Trailing Stops, and Defensive Maker Hedges.
        """
        if not self.is_initialized:
            return

        # Periodic background sync (throttled to 5s)
        self.sync_state(force=False)
        pos = self.cached_position
        if abs(pos) > 1e-6 and not self.position_strategy:
            self.position_strategy = self.strategy_name

        strat_cfg = self.config.strategies.get_strategy(self.strategy_name) if hasattr(self.config, "strategies") else None
        maker_threshold = strat_cfg.entry_threshold if (strat_cfg and strat_cfg.entry_threshold is not None) else self.config.backtest.entry_threshold
        hedge_rev = getattr(strat_cfg, "hedge_reversal_threshold", None)
        if hedge_rev is None:
            hedge_rev = -maker_threshold
        tp_bps = getattr(strat_cfg, "take_profit_bps", None) or self.config.backtest.take_profit_bps
        sl_bps = getattr(strat_cfg, "stop_loss_bps", None) or self.config.backtest.stop_loss_bps
        trail_act_bps = getattr(strat_cfg, "trailing_stop_activation_bps", None) or self.config.backtest.trailing_stop_activation_bps
        trail_dist_bps = getattr(strat_cfg, "trailing_stop_distance_bps", None) or self.config.backtest.trailing_stop_distance_bps
        reversal_thresh = getattr(strat_cfg, "exit_reversal_threshold", None)
        if reversal_thresh is None:
            reversal_thresh = getattr(self.config.backtest, "exit_reversal_threshold", 0.35)
        hedge_loss_bps = getattr(strat_cfg, "hedge_trigger_loss_bps", -3.5)
        fee_hurdle_bps = getattr(getattr(self.config, "market", None), "taker_fee_bps", 0.90 if getattr(getattr(self.config, "market", None), "is_xyz_stock", False) else 4.5)

        mid_price = (best_bid + best_ask) / 2.0 if (best_bid > 0 and best_ask > 0) else best_bid
        if self.capital_usd is not None and self.capital_usd > 0 and mid_price > 0:
            target_notional = self.capital_usd * self.allocation_pct
            # Margin safety guard: Never attempt entry notional that exceeds 80% of maximum theoretical account leverage
            if self.available_margin > 0 and self.max_leverage > 0:
                max_safe_notional = self.available_margin * self.max_leverage * 0.80
                if target_notional > max_safe_notional:
                    target_notional = max_safe_notional

            computed_sz = self.format_size(target_notional / mid_price)
            order_size = self.ensure_min_notional(computed_sz, mid_price)
        else:
            order_size = self.ensure_min_notional(self.default_order_size_btc, mid_price)

        # ---------------------------------------------------------------------
        # 1. POSITION MANAGEMENT (ACTIVE EXITS: TP, SL, TRAILING STOP, HEDGE, REVERSAL)
        # ---------------------------------------------------------------------
        if abs(pos) > 1e-6:
            # If an active resting order is NOT an exit quote (e.g. leftover entry quote), cancel it
            if self.active_order and not self.active_order.get("is_exit", False):
                self.cancel_order(self.active_order["oid"])

            is_long = pos > 0
            entry_px = self.entry_price if self.entry_price > 0 else mid_price

            if is_long:
                self.peak_price = max(self.peak_price, mid_price)
                gain_bps = ((mid_price - entry_px) / entry_px) * 10_000.0

                exit_triggered = False
                target_exit_px = self.format_price(best_ask)

                # 1A. Emergency Stop Loss (Immediate Taker Sell at Best Bid)
                if gain_bps <= -sl_bps:
                    self.console.print(f"[bold red][LiveExecutor] [{self.strategy_name}] Emergency Stop Loss triggered ({gain_bps:.1f} bps)![/bold red]")
                    if self.active_order:
                        self.cancel_order(self.active_order["oid"])
                    self.place_limit_order(is_buy=False, size_btc=abs(pos), price=best_bid, post_only=False, signal_score=signal_score, is_exit=True)
                    return

                # 1B. Take Profit (Passive Maker Limit Sell at Best Ask)
                target_exit_px = self.format_price(best_ask)
                exit_triggered = False

                if gain_bps >= tp_bps:
                    self.console.print(f"[bold green][LiveExecutor] [{self.strategy_name}] Take Profit reached (+{gain_bps:.1f} bps)! Quoting maker exit...[/bold green]")
                    exit_triggered = True

                # 1C. Trailing Stop Ratchet
                elif gain_bps >= trail_act_bps:
                    self.trailing_stop_active = True
                if not exit_triggered and self.trailing_stop_active:
                    trail_floor = self.peak_price * (1.0 - (trail_dist_bps / 10_000.0))
                    if mid_price <= trail_floor:
                        self.console.print(f"[bold yellow][LiveExecutor] [{self.strategy_name}] Trailing Stop triggered at ${trail_floor:,.4f}![/bold yellow]")
                        exit_triggered = True

                # 1D. Defensive Maker Hedge (Adverse Flow Reversal)
                if not exit_triggered and signal_score <= hedge_rev:
                    self.console.print(f"[bold magenta][LiveExecutor] [{self.strategy_name}] Defensive Maker Hedge triggered (signal: {signal_score:.3f})![/bold magenta]")
                    exit_triggered = True

                # 1E. Signal Reversal (Alpha Conviction Inverted: Quote Passive Maker Exit)
                if not exit_triggered and reversal_thresh is not None and signal_score <= -reversal_thresh:
                    if gain_bps >= fee_hurdle_bps or gain_bps <= -3.0:
                        self.console.print(f"[bold cyan][LiveExecutor] [{self.strategy_name}] Signal Reversal triggered (signal: {signal_score:.3f} <= -{reversal_thresh:.2f}, gain: {gain_bps:+.1f} bps)! Quoting maker exit...[/bold cyan]")
                        exit_triggered = True

                if exit_triggered:
                    # Check resting exit order persistence
                    if self.active_order and self.active_order.get("is_exit") and not self.active_order.get("is_buy"):
                        cur_px = self.active_order.get("price")
                        # Already resting at target exit price: KEEP IT RESTING (preserve queue priority!)
                        if abs(cur_px - target_exit_px) < 1e-6:
                            return
                        # Price drifted: cancel and re-quote at new best ask
                        self.cancel_order(self.active_order["oid"])
                    elif self.active_order:
                        self.cancel_order(self.active_order["oid"])

                    self.place_limit_order(is_buy=False, size_btc=abs(pos), price=target_exit_px, post_only=True, signal_score=signal_score, is_exit=True)
                    return
                else:
                    # No exit condition active. If an exit quote is lingering, cancel it
                    if self.active_order and self.active_order.get("is_exit"):
                        self.cancel_order(self.active_order["oid"])
                    return

            else:
                # SHORT POSITION MANAGEMENT
                self.trough_price = min(self.trough_price, mid_price) if self.trough_price > 0 else mid_price
                gain_bps = ((entry_px - mid_price) / entry_px) * 10_000.0

                # 1A. Emergency Stop Loss (Immediate Taker Buy at Best Ask)
                if gain_bps <= -sl_bps:
                    self.console.print(f"[bold red][LiveExecutor] [{self.strategy_name}] Emergency Stop Loss triggered ({gain_bps:.1f} bps)![/bold red]")
                    if self.active_order:
                        self.cancel_order(self.active_order["oid"])
                    self.place_limit_order(is_buy=True, size_btc=abs(pos), price=best_ask, post_only=False, signal_score=signal_score, is_exit=True)
                    return

                # 1B. Take Profit (Passive Maker Limit Buy at Best Bid)
                target_exit_px = self.format_price(best_bid)
                exit_triggered = False

                if gain_bps >= tp_bps:
                    self.console.print(f"[bold green][LiveExecutor] [{self.strategy_name}] Take Profit reached (+{gain_bps:.1f} bps)! Quoting maker exit...[/bold green]")
                    exit_triggered = True

                # 1C. Trailing Stop Ratchet
                elif gain_bps >= trail_act_bps:
                    self.trailing_stop_active = True
                if not exit_triggered and self.trailing_stop_active:
                    trail_ceiling = self.trough_price * (1.0 + (trail_dist_bps / 10_000.0))
                    if mid_price >= trail_ceiling:
                        self.console.print(f"[bold yellow][LiveExecutor] [{self.strategy_name}] Trailing Stop triggered at ${trail_ceiling:,.4f}![/bold yellow]")
                        exit_triggered = True

                # 1D. Defensive Maker Hedge (Adverse Flow Reversal)
                if not exit_triggered and signal_score >= -hedge_rev:
                    self.console.print(f"[bold magenta][LiveExecutor] [{self.strategy_name}] Defensive Maker Hedge triggered (signal: {signal_score:.3f})![/bold magenta]")
                    exit_triggered = True

                # 1E. Signal Reversal (Alpha Conviction Inverted: Quote Passive Maker Exit)
                if not exit_triggered and reversal_thresh is not None and signal_score >= reversal_thresh:
                    if gain_bps >= fee_hurdle_bps or gain_bps <= -3.0:
                        self.console.print(f"[bold cyan][LiveExecutor] [{self.strategy_name}] Signal Reversal triggered (signal: {signal_score:.3f} >= +{reversal_thresh:.2f}, gain: {gain_bps:+.1f} bps)! Quoting maker exit...[/bold cyan]")
                        exit_triggered = True

                if exit_triggered:
                    # Check resting exit order persistence
                    if self.active_order and self.active_order.get("is_exit") and self.active_order.get("is_buy"):
                        cur_px = self.active_order.get("price")
                        # Already resting at target exit price: KEEP IT RESTING (preserve queue priority!)
                        if abs(cur_px - target_exit_px) < 1e-6:
                            return
                        # Price drifted: cancel and re-quote at new best bid
                        self.cancel_order(self.active_order["oid"])
                    elif self.active_order:
                        self.cancel_order(self.active_order["oid"])

                    self.place_limit_order(is_buy=True, size_btc=abs(pos), price=target_exit_px, post_only=True, signal_score=signal_score, is_exit=True)
                    return
                else:
                    # No exit condition active. If an exit quote is lingering, cancel it
                    if self.active_order and self.active_order.get("is_exit"):
                        self.cancel_order(self.active_order["oid"])
                    return

            return

        # ---------------------------------------------------------------------
        # 2. ENTRY QUOTE MANAGEMENT (WHEN FLAT: MAINTAIN PERSISTENT RESTING QUOTES)
        # ---------------------------------------------------------------------
        self.entry_price = 0.0
        self.trailing_stop_active = False
        self.stop_loss_trigger_time = 0.0
        self.position_strategy = None

        # Hysteresis parameters
        cancel_decay_floor = maker_threshold * 0.45
        max_rest_duration_secs = 60.0

        # Bullish Entry: Post passive maker quote at Best Bid
        if signal_score >= maker_threshold:
            target_px = self.format_price(best_bid)

            # Check existing resting order persistence
            if self.active_order and self.active_order.get("is_buy"):
                cur_px = self.active_order.get("price")
                # If existing resting order is already at best bid, KEEP IT RESTING (preserve queue priority!)
                if abs(cur_px - target_px) < 1e-6:
                    return
                # Price has drifted -> cancel and re-post at new best bid
                self.cancel_order(self.active_order["oid"])

            elif self.active_order and not self.active_order.get("is_buy"):
                # Active order is on opposite side -> cancel it
                self.cancel_order(self.active_order["oid"])

            # Place persistent resting maker buy
            self.place_limit_order(
                is_buy=True,
                size_btc=order_size,
                price=target_px,
                post_only=True,
                signal_score=signal_score,
                is_exit=False,
            )

        # Bearish Entry: Post passive maker quote at Best Ask
        elif signal_score <= -maker_threshold:
            target_px = self.format_price(best_ask)

            # Check existing resting order persistence
            if self.active_order and not self.active_order.get("is_buy"):
                cur_px = self.active_order.get("price")
                # If existing resting order is already at best ask, KEEP IT RESTING (preserve queue priority!)
                if abs(cur_px - target_px) < 1e-6:
                    return
                # Price has drifted -> cancel and re-post at new best ask
                self.cancel_order(self.active_order["oid"])

            elif self.active_order and self.active_order.get("is_buy"):
                # Active order is on opposite side -> cancel it
                self.cancel_order(self.active_order["oid"])

            # Place persistent resting maker sell
            self.place_limit_order(
                is_buy=False,
                size_btc=order_size,
                price=target_px,
                post_only=True,
                signal_score=signal_score,
                is_exit=False,
            )

        else:
            # Signal is in neutral zone: apply hysteresis
            # Only cancel if signal decayed below hysteresis floor or flipped opposite, OR price drifted
            if self.active_order:
                cur_px = self.active_order.get("price")
                is_buy = self.active_order.get("is_buy", True)
                target_px = self.format_price(best_bid if is_buy else best_ask)
                should_cancel = False
                if abs(cur_px - target_px) >= 1e-6:
                    should_cancel = True
                elif is_buy and signal_score < cancel_decay_floor:
                    should_cancel = True
                elif not is_buy and signal_score > -cancel_decay_floor:
                    should_cancel = True

                if should_cancel:
                    self.cancel_order(self.active_order["oid"])
