"""Live Order Execution Manager for Hyperliquid Testnet.

Bridges high-conviction microstructure alpha signals (WOBI, MicroPrice, Composite Alpha, Adaptive ML)
directly to the live Hyperliquid Testnet orderbook via the official SDK with risk guardrails.
"""

import logging
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

from config import AppConfig


class LiveOrderExecutor:
    """Manages real-time order placement, cancellation, and risk management on Hyperliquid Testnet."""

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        console: Optional[Console] = None,
        max_position_btc: float = 0.05,
        default_order_size_btc: float = 0.0005,  # ~$40 notional (above $10 minimum)
        order_cooldown_secs: float = 5.0,
        auditor: Optional[Any] = None,
        strategy_name: str = "LiveExecution",
    ):
        self.config = config or AppConfig()
        self.console = console or Console()
        self.max_position_btc = max_position_btc
        self.default_order_size_btc = default_order_size_btc
        self.order_cooldown_secs = order_cooldown_secs
        self.auditor = auditor
        self.strategy_name = strategy_name

        self.account_address = self.config.account.account_address
        self.secret_key = self.config.account.secret_key
        self.coin = self.config.market.coin
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

        self._initialize()

    def _initialize(self) -> None:
        """Initializes Hyperliquid SDK client with configured wallet and account address."""
        if not self.secret_key:
            self.console.print("[dim yellow][LiveExecutor] No secret key configured; live execution disabled.[/dim yellow]")
            return

        try:
            wallet = eth_account.Account.from_key(self.secret_key)
            self.info = Info(self.base_url, skip_ws=True)
            self.exchange = Exchange(
                wallet=wallet,
                base_url=self.base_url,
                account_address=self.account_address if self.account_address else None,
            )
            self.is_initialized = True
            signer_addr = wallet.address
            network_label = "TESTNET" if self.config.hyperliquid.use_testnet else "MAINNET"
            self.console.print(
                f"[bold green]✓ [LiveExecutor] Connected to Hyperliquid {network_label}![/bold green] "
                f"Master: [dim]{self.account_address[:8]}...[/dim] | Signer: [dim]{signer_addr[:8]}...[/dim]"
            )
        except Exception as e:
            self.console.print(f"[bold red]✗ [LiveExecutor] Initialization failed: {e}[/bold red]")
            self.is_initialized = False

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """Fetches active resting limit orders from Hyperliquid exchange."""
        if not self.info or not self.account_address:
            return []
        try:
            return self.info.open_orders(self.account_address)
        except Exception:
            return []

    def get_current_position(self) -> float:
        """Fetches active net position size in BTC from Hyperliquid exchange."""
        if not self.info or not self.account_address:
            return 0.0
        try:
            user_state = self.info.user_state(self.account_address)
            for p in user_state.get("assetPositions", []):
                pos = p.get("position", {})
                if pos.get("coin") == self.coin:
                    return float(pos.get("szi", 0.0))
            return 0.0
        except Exception:
            return 0.0

    def cancel_all_orders(self) -> int:
        """Cancels all open orders for the configured coin."""
        if not self.is_initialized or not self.exchange:
            return 0

        cancelled_count = 0
        open_orders = self.get_open_orders()
        for o in open_orders:
            if o.get("coin") == self.coin:
                oid = o.get("oid")
                try:
                    res = self.exchange.cancel(self.coin, oid)
                    if res.get("status") == "ok":
                        cancelled_count += 1
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
                except Exception as e:
                    self.console.print(f"[dim red][LiveExecutor] Failed to cancel order {oid}: {e}[/dim red]")

        self.active_order_oids.clear()
        return cancelled_count

    def place_limit_order(
        self,
        is_buy: bool,
        size_btc: float,
        price: float,
        post_only: bool = True,
        signal_score: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        """Places a limit order on Hyperliquid Testnet.
        
        Args:
            is_buy: True for BUY, False for SELL.
            size_btc: Size in BTC (must exceed $10 notional).
            price: Limit price in USD.
            post_only: If True, uses 'Alo' (Add Liquidity Only / Post Only) to guarantee maker execution.
            signal_score: Alpha signal score triggering this order.
        """
        if not self.is_initialized or not self.exchange:
            self.console.print("[dim red][LiveExecutor] Cannot place order: executor not initialized.[/dim red]")
            return None

        # Check order cooldown
        now = time.time()
        if now - self.last_order_time < self.order_cooldown_secs:
            return None

        # Check notional value (Hyperliquid requires >= $10)
        notional = size_btc * price
        if notional < 10.0:
            self.console.print(f"[dim yellow][LiveExecutor] Order notional ${notional:.2f} is below $10 minimum requirement.[/dim yellow]")
            return None

        tif = "Alo" if post_only else "Gtc"
        side_str = "BUY" if is_buy else "SELL"
        side_color = "green" if is_buy else "red"

        net_label = "TESTNET" if self.config.hyperliquid.use_testnet else "MAINNET"
        self.console.print(
            f"[bold {side_color}][LIVE {net_label} ORDER] Submitting {side_str} {size_btc:.4f} {self.coin} @ ${price:,.1f} "
            f"(${notional:,.1f} notional, TIF: {tif})...[/bold {side_color}]"
        )

        if self.auditor:
            self.auditor.record_live_order_event(
                strategy_name=self.strategy_name,
                event_type="SUBMIT",
                side=side_str,
                size_btc=size_btc,
                price=price,
                tif=tif,
                status="submitting",
                signal_score=signal_score,
            )

        try:
            res = self.exchange.order(
                name=self.coin,
                is_buy=is_buy,
                sz=size_btc,
                limit_px=round(price, 1),
                order_type={"limit": {"tif": tif}},
                reduce_only=False,
            )
            self.last_order_time = now

            if res.get("status") == "ok":
                data = res.get("response", {}).get("data", {})
                statuses = data.get("statuses", [{}])
                first_status = statuses[0] if statuses else {}

                if "resting" in first_status:
                    oid = first_status["resting"].get("oid")
                    self.active_order_oids.append(oid)
                    self.console.print(f"[bold green]✓ [LiveExecutor] Order RESTING on {net_label} Book! OID: {oid}[/bold green]")
                    if self.auditor:
                        self.auditor.record_live_order_event(
                            strategy_name=self.strategy_name,
                            event_type="RESTING",
                            side=side_str,
                            size_btc=size_btc,
                            price=price,
                            tif=tif,
                            order_id=oid,
                            status="ok",
                            signal_score=signal_score,
                        )
                    return res
                elif "filled" in first_status:
                    fill = first_status["filled"]
                    avg_px = float(fill.get("avgPx", price))
                    total_sz = float(fill.get("totalSz", size_btc))
                    oid = fill.get("oid")
                    self.console.print(f"[bold green]✓ [LiveExecutor] Order FILLED immediately! Px: ${avg_px:,.1f} | Sz: {total_sz:.4f}[/bold green]")
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
                    if self.auditor:
                        self.auditor.record_live_order_event(
                            strategy_name=self.strategy_name,
                            event_type="REJECTED",
                            side=side_str,
                            size_btc=size_btc,
                            price=price,
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
                        size_btc=size_btc,
                        price=price,
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
                    size_btc=size_btc,
                    price=price,
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
    ) -> None:
        """Evaluates signal score, manages inventory/positions, and posts quotes on the live order book."""
        if not self.is_initialized:
            return

        # Fetch current live position from exchange
        pos_btc = self.get_current_position()
        strat_cfg = self.config.strategies.execution_strategies.get(self.strategy_name) if hasattr(self.config, "strategies") else None
        maker_threshold = strat_cfg.entry_threshold if strat_cfg else self.config.backtest.entry_threshold
        hedge_rev = getattr(strat_cfg, "hedge_reversal_threshold", None) or -maker_threshold
        size = self.default_order_size_btc

        # 1. Manage Active Long Position
        if pos_btc > 0:
            # If signal reverses or triggers defensive hedge -> Place passive maker SELL limit order at best ask
            if signal_score <= hedge_rev:
                self.cancel_all_orders()
                exit_sz = min(pos_btc, size)
                self.place_limit_order(
                    is_buy=False,
                    size_btc=exit_sz,
                    price=best_ask,
                    post_only=True,
                    signal_score=signal_score,
                )
                return

            # If already at or above max_position_btc, DO NOT add more buys
            if pos_btc >= self.max_position_btc:
                return

        # 2. Manage Active Short Position
        elif pos_btc < 0:
            # If signal reverses or triggers defensive hedge -> Place passive maker BUY limit order at best bid
            if signal_score >= -hedge_rev:
                self.cancel_all_orders()
                exit_sz = min(abs(pos_btc), size)
                self.place_limit_order(
                    is_buy=True,
                    size_btc=exit_sz,
                    price=best_bid,
                    post_only=True,
                    signal_score=signal_score,
                )
                return

            # If already at or below -max_position_btc, DO NOT add more sells
            if abs(pos_btc) >= self.max_position_btc:
                return

        # 3. New Entry Quotes (Capped by max_position_btc)
        # High bullish conviction -> Post at Best Bid
        if signal_score >= maker_threshold:
            if pos_btc + size <= self.max_position_btc:
                self.cancel_all_orders()
                self.place_limit_order(
                    is_buy=True,
                    size_btc=size,
                    price=best_bid,
                    post_only=True,
                    signal_score=signal_score,
                )

        # High bearish conviction -> Post at Best Ask
        elif signal_score <= -maker_threshold:
            if abs(pos_btc - size) <= self.max_position_btc:
                self.cancel_all_orders()
                self.place_limit_order(
                    is_buy=False,
                    size_btc=size,
                    price=best_ask,
                    post_only=True,
                    signal_score=signal_score,
                )
