"""Hyperliquid L2 Microstructure Alpha Engine - Main CLI and Real-Time Runner."""

import argparse
import asyncio
import json
import os
import signal
import sys
import time

# Configure OpenMP & BLAS threading runtimes to eliminate CPU spin-waiting loops
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

from typing import Any, Dict, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.live import Live
from rich.table import Table
import requests
import websockets

from config import AppConfig
from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from engine.backtester import EdgeEvaluator
from engine.data_collector import L2DataRecorder, L2ReplayEngine
from engine.trade_auditor import SessionAuditor
from signals.composite_alpha import CompositeAlphaSignal
from ui.dashboard import TerminalDashboard


class L2EngineRunner:
    """Orchestrates Hyperliquid WebSocket connection, state maintenance, signal processing, and live edge evaluation."""

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        record_data: bool = True,
        live_orders: bool = False,
        order_size_btc: float = 0.0005,
        enable_audit: Optional[bool] = None,
        session_id: Optional[str] = None,
        web_mode: bool = False,
        web_port: int = 8000,
        open_browser: bool = False,
    ):
        self.config = config or AppConfig()
        self.record_data = record_data
        self.live_orders = live_orders
        self.enable_audit = (live_orders or record_data) if enable_audit is None else enable_audit
        self.web_mode = web_mode
        self.web_port = web_port
        self.open_browser = open_browser
        self.console = Console()

        self.book = OrderBook(coin=self.config.market.coin)
        self.trades = TradeManager(
            coin=self.config.market.coin,
            vpin_bucket_size_btc=self.config.signals.vpin_bucket_size_btc,
            max_vpin_buckets=self.config.signals.vpin_window_buckets,
        )

        signal_weights = self.config.strategies.get_signal_weights()
        enabled_signals = self.config.strategies.get_enabled_signals_map()

        self.alpha_model = CompositeAlphaSignal(
            w_wobi=signal_weights.get("WOBI", self.config.signals.weight_wobi),
            w_voi=signal_weights.get("VOI", self.config.signals.weight_voi),
            w_microprice=signal_weights.get("MicroPrice", self.config.signals.weight_microprice),
            w_absorption=signal_weights.get("Absorption", self.config.signals.weight_cvd_absorption),
            w_vpin=signal_weights.get("VPIN", self.config.signals.weight_vpin),
            w_qdap=signal_weights.get("QDAP", getattr(self.config.signals, "weight_qdap", 0.20)),
            enabled_signals=enabled_signals,
        )

        enabled_strategy_defs = self.config.strategies.get_enabled_strategy_defs()
        strategy_params = self.config.strategies.get_strategy_params()

        self.auditor: Optional[SessionAuditor] = None
        if enable_audit:
            self.auditor = SessionAuditor(
                session_id=session_id,
                coin=self.config.market.coin,
                network=self.config.hyperliquid.network_name,
                is_live_mode=self.live_orders,
                enabled_strategies=list(enabled_strategy_defs.keys()),
                lazy_init=not self.live_orders,
            )

        self.evaluator = EdgeEvaluator(
            market_cfg=self.config.market,
            bt_cfg=self.config.backtest,
            strategy_defs=enabled_strategy_defs,
            strategy_params=strategy_params,
            auditor=self.auditor,
        )

        self.recorder: Optional[L2DataRecorder] = (
            L2DataRecorder(output_dir=self.config.data_dir, coin=self.config.market.coin)
            if record_data
            else None
        )

        self.live_executor = None
        if live_orders:
            from engine.live_executor import LiveOrderExecutor
            active_name = self.config.strategies.live_execution.active_strategy
            self.live_executor = LiveOrderExecutor(
                config=self.config,
                console=self.console,
                default_order_size_btc=order_size_btc,
                capital_usd=getattr(self.config.backtest, "capital_usd", None),
                allocation_pct=getattr(self.config.backtest, "capital_allocation_pct", 1.0),
                auditor=self.auditor,
                strategy_name=active_name,
            )

        self.dashboard = TerminalDashboard(console=self.console)
        self.web_server = None
        if self.web_mode:
            from ui.web_server import DashboardWebServer
            self.web_server = DashboardWebServer(runner=self, port=self.web_port)
        self.latest_display_signals: Dict[str, Any] = {}
        self.is_running = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self) -> None:
        """Closes all runner resources including auditor and data recorder."""
        if self.web_server and self.web_server.server:
            self.web_server.server.should_exit = True
        if self.auditor:
            self.auditor.close_session()
        if self.recorder:
            self.recorder.close()

    async def _handle_message(self, raw_msg: str) -> None:
        """Processes an incoming WebSocket message from Hyperliquid."""
        try:
            msg = json.loads(raw_msg)
        except Exception:
            return

        channel = msg.get("channel")
        if channel == "pong":
            return

        data = msg.get("data")
        if not channel or not data:
            return

        # Record event if recording enabled
        if self.recorder:
            self.recorder.record_event(channel, data)

        if channel == "l2Book":
            self.book.update_from_raw(data)

        elif channel == "trades":
            if isinstance(data, list):
                self.trades.process_raw_trades(data)

        elif channel == "activeAssetCtx":
            self.book.update_asset_ctx(data)

    async def _evaluation_loop(self) -> None:
        """Runs at fixed frequency (e.g. 10Hz) to compute signals and evaluate forward edge."""
        dt = 1.0 / self.config.sample_rate_hz
        while self.is_running:
            start_t = time.perf_counter()

            if self.book.is_valid:
                now_ms = int(time.time() * 1000)
                # Compute composite alpha
                res = self.alpha_model.compute(self.book, self.trades, now_ms)
                sub_sigs = res.metadata.get("sub_signals", {})
                self.latest_display_signals = {**sub_sigs, "Composite": res}

                # Extract score dictionary
                scores = {name: sig.score for name, sig in sub_sigs.items()}
                scores["CompositeAlpha"] = res.score

                # Feed edge evaluator & paper trading simulator
                self.evaluator.record_step(
                    timestamp_ms=now_ms,
                    mid_price=self.book.mid_price,
                    best_bid=self.book.best_bid,
                    best_ask=self.book.best_ask,
                    signals=scores,
                )

                # Feed live order executor if enabled
                if self.live_executor:
                    # 1. If holding an active position, preserve the owning strategy
                    if abs(self.live_executor.cached_position) > 1e-6 and self.live_executor.position_strategy:
                        strat_to_use = self.live_executor.position_strategy
                        active_strat = self.config.strategies.get_strategy(strat_to_use)
                        sig_score = scores.get(active_strat.signal_key, 0.0) if active_strat else 0.0
                    # 2. If an entry order is resting on the book, preserve its owning strategy
                    elif self.live_executor.active_order and self.live_executor.active_order.get("strategy_name"):
                        strat_to_use = self.live_executor.active_order.get("strategy_name")
                        active_strat = self.config.strategies.get_strategy(strat_to_use)
                        sig_score = scores.get(active_strat.signal_key, 0.0) if active_strat else 0.0
                    # 3. When completely flat with no resting order, dispatch across enabled strategies
                    else:
                        active_name = self.config.strategies.live_execution.active_strategy
                        active_strat = self.config.strategies.get_strategy(active_name)

                        strat_to_use = active_name
                        sig_score = scores.get(active_strat.signal_key, 0.0) if (active_strat and active_strat.enabled) else 0.0
                        threshold = active_strat.entry_threshold if active_strat else 0.85

                        if abs(sig_score) < threshold:
                            for s_name, s_def in self.config.strategies.all_strategies.items():
                                if s_def.enabled and s_name != active_name:
                                    s_score = scores.get(s_def.signal_key, 0.0)
                                    if abs(s_score) >= s_def.entry_threshold and abs(s_score) > abs(sig_score):
                                        sig_score = s_score
                                        strat_to_use = s_name

                    self.live_executor.strategy_name = strat_to_use
                    self.live_executor.on_signal_update(
                        signal_score=sig_score,
                        best_bid=self.book.best_bid,
                        best_ask=self.book.best_ask,
                        spread=self.book.spread,
                        scores=scores,
                    )

            elapsed = time.perf_counter() - start_t
            await asyncio.sleep(max(0.001, dt - elapsed))

    async def run_live(self, duration_secs: Optional[int] = None, show_ui: bool = True) -> None:
        """Connects to Hyperliquid WS and runs live microstructure engine with automated reconnection and keepalive."""
        self.is_running = True
        ws_url = self.config.hyperliquid.ws_url
        network_name = self.config.hyperliquid.network_name
        self.console.print(f"[bold cyan]Connecting to Hyperliquid {network_name.upper()} ({ws_url})...[/bold cyan]")

        eval_task = asyncio.create_task(self._evaluation_loop())
        start_time = time.time()
        reconnect_delay = 1.0

        stop_event = asyncio.Event()

        def _sig_handler(s, f):
            self.is_running = False
            stop_event.set()

        orig_sigint = None
        orig_sigterm = None
        try:
            orig_sigint = signal.signal(signal.SIGINT, _sig_handler)
            orig_sigterm = signal.signal(signal.SIGTERM, _sig_handler)
        except Exception:
            pass

        if self.web_server:
            await self.web_server.start()
            dashboard_url = f"http://localhost:{self.web_port}"
            self.console.print(f"[bold green]✓ Web Dashboard running on: [bold cyan]{dashboard_url}[/bold cyan][/bold green]")
            if self.open_browser:
                try:
                    import webbrowser
                    webbrowser.open(dashboard_url)
                except Exception:
                    pass

        async def _ping_heartbeat(ws):
            """Hyperliquid application-level JSON ping heartbeat sent every 20 seconds."""
            while self.is_running:
                try:
                    await asyncio.sleep(20.0)
                    if hasattr(ws, "closed") and ws.closed:
                        break
                    await ws.send(json.dumps({"method": "ping"}))
                except (asyncio.CancelledError, Exception):
                    break

        try:
            if show_ui:
                with Live(
                    self.dashboard.render(self.book, self.trades, {}, self.evaluator, network=network_name),
                    console=self.console,
                    refresh_per_second=4,
                    screen=False,
                ) as live:
                    while self.is_running:
                        if duration_secs and (time.time() - start_time) >= duration_secs:
                            break
                        try:
                            async with websockets.connect(
                                ws_url,
                                ping_interval=20,
                                ping_timeout=20,
                                max_size=20_000_000,
                            ) as ws:
                                reconnect_delay = 1.0
                                # Subscriptions: Granular 1-tick book, trades, and deep macro book
                                sub_l2 = {
                                    "method": "subscribe",
                                    "subscription": {"type": "l2Book", "coin": self.config.market.coin},
                                }
                                sub_trades = {
                                    "method": "subscribe",
                                    "subscription": {"type": "trades", "coin": self.config.market.coin},
                                }
                                sub_ctx = {
                                    "method": "subscribe",
                                    "subscription": {"type": "activeAssetCtx", "coin": self.config.market.coin},
                                }
                                await ws.send(json.dumps(sub_l2))
                                await ws.send(json.dumps(sub_trades))
                                await ws.send(json.dumps(sub_ctx))

                                if getattr(self.config.market, "subscribe_macro_book", False):
                                    sub_macro = {
                                        "method": "subscribe",
                                        "subscription": {
                                            "type": "l2Book",
                                            "coin": self.config.market.coin,
                                            "nSigFigs": getattr(self.config.market, "macro_sig_figs", 4),
                                        },
                                    }
                                    await ws.send(json.dumps(sub_macro))

                                # Launch application-level ping heartbeat
                                ping_task = asyncio.create_task(_ping_heartbeat(ws))

                                try:
                                    while self.is_running:
                                        if stop_event.is_set() or (self.web_server and self.web_server.server and self.web_server.server.should_exit):
                                            self.is_running = False
                                            break
                                        if duration_secs and (time.time() - start_time) >= duration_secs:
                                            break
                                        try:
                                            msg = await asyncio.wait_for(ws.recv(), timeout=0.1)
                                            await self._handle_message(msg)
                                        except asyncio.TimeoutError:
                                            pass

                                        display_signals = self.latest_display_signals
                                        live.update(
                                            self.dashboard.render(
                                                self.book,
                                                self.trades,
                                                display_signals,
                                                self.evaluator,
                                                network=network_name,
                                            )
                                        )
                                        if self.web_server and self.book.is_valid and self.web_server.broadcaster.should_broadcast(time.time()):
                                            await self.web_server.emit_telemetry(
                                                self.book,
                                                self.trades,
                                                display_signals,
                                                self.evaluator,
                                                network=network_name,
                                            )
                                finally:
                                    ping_task.cancel()

                        except (asyncio.CancelledError, KeyboardInterrupt):
                            self.is_running = False
                            break
                        except (ConnectionResetError, websockets.ConnectionClosed, OSError, Exception) as e:
                            if not self.is_running:
                                break
                            await asyncio.sleep(reconnect_delay)
                            reconnect_delay = min(15.0, reconnect_delay * 1.5)
            else:
                while self.is_running:
                    if duration_secs and (time.time() - start_time) >= duration_secs:
                        break
                    try:
                        async with websockets.connect(
                            ws_url,
                            ping_interval=20,
                            ping_timeout=20,
                            max_size=20_000_000,
                        ) as ws:
                            reconnect_delay = 1.0
                            sub_l2 = {
                                "method": "subscribe",
                                "subscription": {"type": "l2Book", "coin": self.config.market.coin},
                            }
                            sub_trades = {
                                "method": "subscribe",
                                "subscription": {"type": "trades", "coin": self.config.market.coin},
                            }
                            sub_ctx = {
                                "method": "subscribe",
                                "subscription": {"type": "activeAssetCtx", "coin": self.config.market.coin},
                            }
                            await ws.send(json.dumps(sub_l2))
                            await ws.send(json.dumps(sub_trades))
                            await ws.send(json.dumps(sub_ctx))

                            if getattr(self.config.market, "subscribe_macro_book", False):
                                sub_macro = {
                                    "method": "subscribe",
                                    "subscription": {
                                        "type": "l2Book",
                                        "coin": self.config.market.coin,
                                        "nSigFigs": getattr(self.config.market, "macro_sig_figs", 4),
                                    },
                                }
                                await ws.send(json.dumps(sub_macro))

                            ping_task = asyncio.create_task(_ping_heartbeat(ws))
                            try:
                                while self.is_running:
                                    if stop_event.is_set() or (self.web_server and self.web_server.server and self.web_server.server.should_exit):
                                        self.is_running = False
                                        break
                                    if duration_secs and (time.time() - start_time) >= duration_secs:
                                        break
                                    try:
                                        msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                                        await self._handle_message(msg)
                                    except asyncio.TimeoutError:
                                        pass

                                    if self.web_server and self.book.is_valid and self.web_server.broadcaster.should_broadcast(time.time()):
                                        await self.web_server.emit_telemetry(
                                            self.book,
                                            self.trades,
                                            self.latest_display_signals,
                                            self.evaluator,
                                            network=network_name,
                                        )
                            finally:
                                ping_task.cancel()

                    except (asyncio.CancelledError, KeyboardInterrupt):
                        self.is_running = False
                        break
                    except (ConnectionResetError, websockets.ConnectionClosed, OSError, Exception) as e:
                        if not self.is_running:
                            break
                        self.console.print(f"[bold yellow][WebSocket Alert] Connection lost ({type(e).__name__}: {e}). Reconnecting in {reconnect_delay:.1f}s...[/bold yellow]")
                        await asyncio.sleep(reconnect_delay)
                        reconnect_delay = min(15.0, reconnect_delay * 1.5)

        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            self.is_running = False
            eval_task.cancel()
            try:
                await eval_task
            except (asyncio.CancelledError, Exception):
                pass
            if orig_sigint is not None:
                try:
                    signal.signal(signal.SIGINT, orig_sigint)
                except Exception:
                    pass
            if orig_sigterm is not None:
                try:
                    signal.signal(signal.SIGTERM, orig_sigterm)
                except Exception:
                    pass
            if self.web_server:
                await self.web_server.stop()
            if self.live_executor:
                net = self.config.hyperliquid.network_name
                self.console.print(f"\n[bold yellow][LiveExecutor] Shutting down: cancelling all open {net} orders...[/bold yellow]")
                self.live_executor.cancel_all_orders()
            if self.book.is_valid:
                now_ms = int(time.time() * 1000)
                self.evaluator.close_open_positions(self.book.mid_price, now_ms, reason="SESSION_SHUTDOWN")
            if self.live_executor and self.live_executor.info and self.live_orders:
                try:
                    await asyncio.sleep(1.0)
                    all_fills = self.live_executor.info.user_fills(self.live_executor.account_address)
                    if self.auditor:
                        self.auditor.reconcile_live_exchange_fills(all_fills)
                except Exception as e:
                    self.console.print(f"[dim red]Failed to reconcile live exchange fills: {e}[/dim red]")
            if self.auditor:
                self.auditor.close_session()
            if self.recorder:
                self.recorder.close()

    def print_summary_report(self) -> None:
        """Prints a comprehensive terminal summary of strategy edge and performance, and saves a markdown report."""
        network_str = self.config.hyperliquid.network_name
        self.console.print("\n" + "=" * 80)
        self.console.print(f"[bold yellow]HYPERLIQUID L2 STRATEGY EDGE & PERFORMANCE REPORT ({self.config.market.coin} - {network_str.upper()})[/bold yellow]")
        self.console.print("=" * 80 + "\n")

        mid = self.book.mid_price

        # 1. Performance Table
        table_perf = Table(title="Paper Trading Performance (Realistic Fees & Slippage)", header_style="bold cyan")
        table_perf.add_column("Strategy", justify="left")
        table_perf.add_column("Type", justify="center", style="dim")
        table_perf.add_column("Trades", justify="right")
        table_perf.add_column("Win%", justify="right")
        table_perf.add_column("Gross PnL ($)", justify="right")
        table_perf.add_column("Net Fees ($)", justify="right")
        table_perf.add_column("Net PnL ($)", justify="right", style="bold")
        table_perf.add_column("Profit Factor", justify="right")
        table_perf.add_column("Sharpe Ratio", justify="right")
        table_perf.add_column("Max DD ($)", justify="right")

        perf_rows = []
        for s in self.evaluator.strategy_names:
            p = self.evaluator.get_strategy_performance(s, mid)
            gross = p.get("gross_pnl_usd", 0.0)
            gross_c = "green" if gross >= 0 else "red"
            pnl = p.get("total_pnl_usd", 0.0)
            pnl_c = "green" if pnl >= 0 else "red"
            fees = p.get("fees_paid_usd", 0.0)
            fees_str = f"[green]+${abs(fees):.2f}[/green]" if fees <= 0 else f"[red]-${fees:.2f}[/red]"
            table_perf.add_row(
                s,
                p.get("type", "MAKER"),
                str(p.get("trades", 0)),
                f"{p.get('win_rate_pct', 0.0):.1f}%",
                f"[{gross_c}]${gross:+.2f}[/{gross_c}]",
                fees_str,
                f"[{pnl_c}]${pnl:+.2f}[/{pnl_c}]",
                f"{p.get('profit_factor', 0.0):.2f}",
                f"{p.get('sharpe_ratio', 0.0):.2f}",
                f"${p.get('max_drawdown_usd', 0.0):.2f}",
            )
            perf_rows.append(p)

        self.console.print(table_perf)
        self.console.print("\n")

        # 2. Predictive Edge Matrix Table (compact for terminal: 1s, 5s, 15s)
        table_ic = Table(title="Predictive Alpha Matrix: IC & Directional Hit Rate (1s, 5s, 10s)", header_style="bold magenta")
        table_ic.add_column("Signal Factor", justify="left")
        key_horizons = [1, 5, 10]
        for h in key_horizons:
            table_ic.add_column(f"{h}s IC", justify="right")
            table_ic.add_column(f"{h}s Hit%", justify="right")

        ic_data_all = {}
        for s in self.evaluator.strategy_names:
            row = [s]
            ic_data_all[s] = {}
            for h in self.config.backtest.horizons_seconds:
                m = self.evaluator.get_signal_metrics(s, horizon_secs=h)
                ic_data_all[s][h] = m
                if h in key_horizons:
                    ic = m.get("ic", 0.0)
                    hit = m.get("hit_rate", 50.0)
                    ic_c = "green" if ic > 0.02 else ("red" if ic < -0.02 else "white")
                    hit_c = "green" if hit >= 52.0 else ("red" if hit < 48.0 else "white")
                    row.append(f"[{ic_c}]{ic:+.3f}[/{ic_c}]")
                    row.append(f"[{hit_c}]{hit:.1f}%[/{hit_c}]")
            table_ic.add_row(*row)

        self.console.print(table_ic)
        self.console.print("\n")

        # 3. Position Trade Log Table (Executed Closed Trades)
        events = self.evaluator.get_recent_position_events(limit=30)
        close_events = [ev for ev in events if ev["event"] == "CLOSE"]
        if close_events:
            table_trades = Table(title="Executed Strategy Positions (Recent Closed Trades)", header_style="bold green")
            table_trades.add_column("Exit Time", justify="left", style="dim")
            table_trades.add_column("Strategy", justify="left")
            table_trades.add_column("Side / Size", justify="center")
            table_trades.add_column("Exit Price", justify="right")
            table_trades.add_column("Exec", justify="center")
            table_trades.add_column("Exit Reason", justify="left")
            table_trades.add_column("Net PnL ($)", justify="right")
            table_trades.add_column("Return", justify="right")

            for ev in close_events:
                t_str = time.strftime("%H:%M:%S", time.localtime(ev["time_ms"] / 1000))
                pnl = ev.get("net_pnl", 0.0)
                pnl_c = "green" if pnl >= 0 else "red"
                bps = ev.get("return_bps", 0.0)
                table_trades.add_row(
                    t_str,
                    ev["strategy"],
                    f"{ev['side']} {ev['size_btc']:.2f}",
                    f"${ev['price']:,.1f}",
                    ev.get("exec", "MAKER"),
                    ev.get("reason", "TIME_LIMIT"),
                    f"[{pnl_c}]${pnl:+.2f}[/{pnl_c}]",
                    f"[{pnl_c}]{bps:+.1f} bps[/{pnl_c}]",
                )
            self.console.print(table_trades)
            self.console.print("\n")

        # 4. Save comprehensive Markdown Report
        os.makedirs("reports", exist_ok=True)
        report_path = os.path.join("reports", "latest_edge_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# Hyperliquid L2 Alpha Edge & Performance Report ({self.config.market.coin} - {network_str})\n\n")
            f.write(f"- **Network**: Hyperliquid {network_str}\n")
            f.write(f"- **Asset**: {self.config.market.coin}-PERP\n")
            f.write(f"- **Timestamp**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- **Mid Price**: ${mid:,.2f}\n")
            f.write(f"- **Book Spread**: ${self.book.spread:.2f} ({self.book.spread_bps:.2f} bps)\n")
            f.write(f"- **Total Cumulative CVD**: {self.trades.total_cvd:+.4f} {self.config.market.coin.upper()}\n\n")

            f.write("## 1. Paper-Trading Performance Summary\n\n")
            f.write("| Strategy | Trades | Win Rate | Gross PnL ($) | Net Fees ($) | Net PnL ($) | Profit Factor | Sharpe Ratio | Max Drawdown ($) |\n")
            f.write("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
            for p in perf_rows:
                fees_val = p.get('fees_paid_usd', 0.0)
                fees_fmt = f"-${fees_val:.2f}" if fees_val > 0 else f"+${abs(fees_val):.2f}"
                f.write(
                    f"| {p['strategy']} | {p['trades']} | {p['win_rate_pct']:.1f}% | "
                    f"${p.get('gross_pnl_usd', 0.0):+.2f} | {fees_fmt} | "
                    f"${p['total_pnl_usd']:+.2f} | {p['profit_factor']:.2f} | {p['sharpe_ratio']:.2f} | "
                    f"${p['max_drawdown_usd']:.2f} |\n"
                )

            f.write("\n## 2. Predictive Edge Matrix (Information Coefficient & Directional Hit Rate)\n\n")
            header_line = "| Signal Factor | " + " | ".join([f"{h}s IC | {h}s Hit%" for h in self.config.backtest.horizons_seconds]) + " |\n"
            sep_line = "| :--- | " + " | ".join([":---: | :---:" for _ in self.config.backtest.horizons_seconds]) + " |\n"
            f.write(header_line)
            f.write(sep_line)

            for s in self.evaluator.strategy_names:
                cols = [s]
                for h in self.config.backtest.horizons_seconds:
                    m = ic_data_all[s][h]
                    cols.append(f"{m['ic']:+.3f}")
                    cols.append(f"{m['hit_rate']:.1f}%")
                f.write("| " + " | ".join(cols) + " |\n")

            if close_events:
                f.write("\n## 3. Position Trade Log (Executed Positions)\n\n")
                f.write("| Exit Time | Strategy | Side & Size | Exit Price | Exec Type | Exit Reason | Net PnL ($) | Return (bps) |\n")
                f.write("| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: |\n")
                for ev in close_events:
                    t_str = time.strftime("%H:%M:%S", time.localtime(ev["time_ms"] / 1000))
                    f.write(
                        f"| {t_str} | {ev['strategy']} | {ev['side']} {ev['size_btc']:.2f} BTC | "
                        f"${ev['price']:,.1f} | {ev.get('exec', 'MAKER')} | {ev.get('reason', '')} | "
                        f"${ev.get('net_pnl', 0.0):+.2f} | {ev.get('return_bps', 0.0):+.1f} bps |\n"
                    )

        self.console.print(f"[bold green]Saved detailed Markdown report to: {report_path}[/bold green]")
        if self.auditor:
            self.console.print(f"[bold cyan]Session Audit Logs saved to: {self.auditor.session_path}/[/bold cyan]")
            self.console.print(f"  - Master Trade Audit CSV: [dim]{self.auditor.master_csv_file}[/dim]")
            self.console.print(f"  - Strategy Audit CSVs:   [dim]{self.auditor.strategies_path}/*.csv[/dim]")
            self.console.print(f"  - Session Audit Report:   [dim]{self.auditor.report_markdown_file}[/dim]\n")



async def test_hyperliquid_connection(
    cfg: Optional[AppConfig] = None,
    console: Optional[Console] = None,
) -> bool:
    """Verifies complete REST API and WebSocket connectivity to Hyperliquid Testnet (or configured network)."""
    cfg = cfg or AppConfig()
    console = console or Console()
    network_str = cfg.hyperliquid.network_name
    coin = cfg.market.coin
    rest_url = cfg.hyperliquid.rest_url
    ws_url = cfg.hyperliquid.ws_url

    console.print()
    console.print(f"[bold cyan]================================================================================[/bold cyan]")
    console.print(f"[bold cyan]           HYPERLIQUID {network_str.upper()} CONNECTIVITY VERIFICATION ({coin})           [/bold cyan]")
    console.print(f"[bold cyan]================================================================================[/bold cyan]")
    console.print(f"Network:        [bold magenta]{network_str}[/bold magenta]")
    console.print(f"REST Endpoint:  [dim]{rest_url}[/dim]")
    console.print(f"WS Endpoint:    [dim]{ws_url}[/dim]")
    console.print(f"Target Coin:    [bold yellow]{coin}[/bold yellow]\n")

    success_rest_meta = False
    success_rest_book = False
    success_ws = False

    # 1. REST API - Metadata & Asset Context
    console.print(f"[bold cyan]1. Checking REST API & Market Metadata...[/bold cyan]")
    try:
        t0 = time.perf_counter()
        payload = {"type": "metaAndAssetCtxs", "dex": "xyz"} if coin.startswith("xyz:") else {"type": "metaAndAssetCtxs"}
        resp = requests.post(
            rest_url,
            json=payload,
            timeout=8,
        )
        latency_meta_ms = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        data = resp.json()

        universe = data[0].get("universe", [])
        contexts = data[1] if len(data) > 1 else []

        coin_meta = None
        coin_ctx = None
        for i, meta in enumerate(universe):
            if meta.get("name") == coin:
                coin_meta = meta
                coin_ctx = contexts[i] if i < len(contexts) else {}
                break

        if not coin_meta and not coin.startswith("xyz:"):
            try:
                resp_xyz = requests.post(rest_url, json={"type": "metaAndAssetCtxs", "dex": "xyz"}, timeout=8)
                if resp_xyz.ok:
                    data_xyz = resp_xyz.json()
                    u_xyz = data_xyz[0].get("universe", [])
                    ctx_xyz = data_xyz[1] if len(data_xyz) > 1 else []
                    for i, meta in enumerate(u_xyz):
                        if meta.get("name") in (coin, f"xyz:{coin}"):
                            coin_meta = meta
                            coin_ctx = ctx_xyz[i] if i < len(ctx_xyz) else {}
                            break
            except Exception:
                pass

        if coin_meta:
            mark_px = float(coin_ctx.get("markPx", 0.0))
            oracle_px = float(coin_ctx.get("oraclePx", 0.0))
            funding = float(coin_ctx.get("funding", 0.0))
            oi = float(coin_ctx.get("openInterest", 0.0))
            vol_24h = float(coin_ctx.get("dayNtlVlm", 0.0))
            leverage = coin_meta.get("maxLeverage", "N/A")

            console.print(f"   [bold green]✓[/bold green] REST API connected ({latency_meta_ms:.1f} ms latency)")
            console.print(
                f"   [bold green]✓[/bold green] Asset {coin}: Mark Px = [bold white]${mark_px:,.2f}[/bold white] | "
                f"Oracle = [dim]${oracle_px:,.2f}[/dim] | 24h Vol = [dim]${vol_24h:,.0f}[/dim] | "
                f"Open Interest = [dim]{oi:.2f} {coin}[/dim] | Max Lev = [dim]{leverage}x[/dim] | Funding = [dim]{funding:+.6f}[/dim]"
            )
            success_rest_meta = True
        else:
            console.print(f"   [bold yellow]![/bold yellow] REST API responded in {latency_meta_ms:.1f}ms, but coin '{coin}' was not in universe of {len(universe)} assets.")
            success_rest_meta = True
    except Exception as e:
        console.print(f"   [bold red]✗ REST API connection failed: {e}[/bold red]")

    # 2. REST API - L2 Order Book Snapshot
    console.print(f"\n[bold cyan]2. Checking REST L2 Order Book Snapshot ({coin})...[/bold cyan]")
    try:
        t0 = time.perf_counter()
        resp = requests.post(
            rest_url,
            json={"type": "l2Book", "coin": coin},
            timeout=8,
        )
        latency_book_ms = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        book_data = resp.json()
        bids = book_data.get("levels", [[], []])[0]
        asks = book_data.get("levels", [[], []])[1]

        if bids and asks:
            best_bid_px = float(bids[0]["px"])
            best_bid_sz = float(bids[0]["sz"])
            best_bid_n = bids[0].get("n", 1)
            best_ask_px = float(asks[0]["px"])
            best_ask_sz = float(asks[0]["sz"])
            best_ask_n = asks[0].get("n", 1)
            spread = best_ask_px - best_bid_px
            mid = (best_bid_px + best_ask_px) / 2.0
            spread_bps = (spread / mid) * 10_000 if mid > 0 else 0.0

            console.print(f"   [bold green]✓[/bold green] L2 Book received ({latency_book_ms:.1f} ms latency)")
            console.print(f"   [bold green]✓[/bold green] Depth Levels: [bold green]{len(bids)} bids[/bold green] / [bold red]{len(asks)} asks[/bold red]")
            console.print(
                f"   [bold green]✓[/bold green] Best Bid: [green]${best_bid_px:,.2f}[/green] (sz: {best_bid_sz:.4f}, n: {best_bid_n}) | "
                f"Best Ask: [red]${best_ask_px:,.2f}[/red] (sz: {best_ask_sz:.4f}, n: {best_ask_n})"
            )
            console.print(f"   [bold green]✓[/bold green] Spread: [yellow]${spread:.2f}[/yellow] ({spread_bps:.2f} bps) | Mid: [bold white]${mid:,.2f}[/bold white]")
            success_rest_book = True
        else:
            console.print(f"   [bold yellow]![/bold yellow] L2 Book empty for coin '{coin}'.")
    except Exception as e:
        console.print(f"   [bold red]✗ REST L2 Book request failed: {e}[/bold red]")

    # 2b. REST API - Macro L2 Order Book Snapshot (nSigFigs=4)
    console.print(f"\n[bold cyan]2b. Checking REST Macro L2 Order Book (nSigFigs=4, {coin})...[/bold cyan]")
    success_rest_macro = False
    try:
        t0 = time.perf_counter()
        resp_m = requests.post(
            rest_url,
            json={"type": "l2Book", "coin": coin, "nSigFigs": 4},
            timeout=8,
        )
        latency_macro_ms = (time.perf_counter() - t0) * 1000
        resp_m.raise_for_status()
        macro_data = resp_m.json()
        m_bids = macro_data.get("levels", [[], []])[0]
        m_asks = macro_data.get("levels", [[], []])[1]
        if m_bids and m_asks:
            top_px = float(m_bids[0]["px"])
            bot_px = float(m_bids[-1]["px"])
            macro_span = top_px - bot_px
            macro_span_bps = (macro_span / top_px) * 10_000.0 if top_px > 0 else 0.0
            console.print(f"   [bold green]✓[/bold green] Macro L2 Book received ({latency_macro_ms:.1f} ms latency)")
            console.print(f"   [bold green]✓[/bold green] Macro Depth Span: [bold cyan]${macro_span:,.1f}[/bold cyan] ({macro_span_bps:.1f} bps) across {len(m_bids)} levels")
            console.print(f"   [bold green]✓[/bold green] Macro Range: ${bot_px:,.1f} -> ${top_px:,.1f}")
            success_rest_macro = True
    except Exception as e:
        console.print(f"   [bold yellow]! Macro L2 request warning: {e}[/bold yellow]")

    # 3. WebSocket Real-Time Handshake & Streaming Subscription
    console.print(f"\n[bold cyan]3. Checking WebSocket Handshake & Live Stream...[/bold cyan]")
    try:
        t0 = time.perf_counter()
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10, max_size=10_000_000) as ws:
            ws_handshake_ms = (time.perf_counter() - t0) * 1000
            console.print(f"   [bold green]✓[/bold green] WebSocket connection established ({ws_handshake_ms:.1f} ms handshake)")

            # Send subscriptions: granular book, trades, and deep macro book
            sub_l2 = {"method": "subscribe", "subscription": {"type": "l2Book", "coin": coin}}
            sub_trades = {"method": "subscribe", "subscription": {"type": "trades", "coin": coin}}
            sub_macro = {"method": "subscribe", "subscription": {"type": "l2Book", "coin": coin, "nSigFigs": 4}}
            await ws.send(json.dumps(sub_l2))
            await ws.send(json.dumps(sub_trades))
            await ws.send(json.dumps(sub_macro))

            # Await subscription confirmation & initial book stream
            received_sub_ack = False
            received_book_feed = False
            received_macro_feed = False
            start_wait = time.time()

            while time.time() - start_wait < 5.0 and not (received_sub_ack and received_book_feed):
                try:
                    raw_msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    msg = json.loads(raw_msg)
                    ch = msg.get("channel")
                    if ch == "subscriptionResponse":
                        received_sub_ack = True
                    elif ch == "l2Book":
                        received_book_feed = True
                except asyncio.TimeoutError:
                    break

            if received_sub_ack:
                console.print(f"   [bold green]✓[/bold green] Subscriptions acknowledged by Hyperliquid server (Granular + Macro)")
            if received_book_feed:
                console.print(f"   [bold green]✓[/bold green] Real-time L2 order book data streams flowing smoothly")

            success_ws = received_sub_ack or received_book_feed
    except Exception as e:
        console.print(f"   [bold red]✗ WebSocket connection failed: {e}[/bold red]")

    # Final Summary Table
    console.print()
    all_ok = success_rest_meta and success_rest_book and success_ws
    summary_table = Table(title=f"Hyperliquid {network_str} Connection Status", box=None, padding=(0, 2))
    summary_table.add_column("Component", justify="left")
    summary_table.add_column("Endpoint", justify="left")
    summary_table.add_column("Status", justify="center")

    summary_table.add_row(
        "REST API (Metadata)",
        rest_url,
        "[bold green]HEALTHY[/bold green]" if success_rest_meta else "[bold red]FAILED[/bold red]",
    )
    summary_table.add_row(
        "REST API (L2 Book)",
        rest_url,
        "[bold green]HEALTHY[/bold green]" if success_rest_book else "[bold red]FAILED[/bold red]",
    )
    summary_table.add_row(
        "WebSocket (Streaming)",
        ws_url,
        "[bold green]HEALTHY[/bold green]" if success_ws else "[bold red]FAILED[/bold red]",
    )
    console.print(summary_table)

    if all_ok:
        console.print(f"\n[bold green]================================================================================[/bold green]")
        console.print(f"[bold green]      ALL CHECKS PASSED: HYPERLIQUID {network_str.upper()} READY FOR ENGINE EXECUTION    [/bold green]")
        console.print(f"[bold green]================================================================================[/bold green]\n")
    else:
        console.print(f"\n[bold red]Some connection checks failed. Check network or endpoint settings.[/bold red]\n")

    return all_ok


def check_hyperliquid_account(
    cfg: Optional[AppConfig] = None,
    console: Optional[Console] = None,
) -> bool:
    """Inspects and validates connected Hyperliquid Testnet account, balance, margin, positions, and API agent."""
    cfg = cfg or AppConfig()
    console = console or Console()
    network_str = cfg.hyperliquid.network_name
    rest_url = cfg.hyperliquid.rest_url
    acct_address = cfg.account.account_address
    secret_key = cfg.account.secret_key

    console.print()
    console.print(f"[bold cyan]================================================================================[/bold cyan]")
    console.print(f"[bold cyan]           HYPERLIQUID {network_str.upper()} ACCOUNT CONNECTION STATUS                [/bold cyan]")
    console.print(f"[bold cyan]================================================================================[/bold cyan]")

    if not acct_address or not cfg.account.has_account:
        console.print(f"[bold yellow]No account address configured.[/bold yellow]\n")
        console.print("[bold white]To connect your Hyperliquid Testnet account to the program:[/bold white]")
        console.print("  1. Visit [bold cyan]https://app.hyperliquid-testnet.xyz/[/bold cyan] and connect your wallet.")
        console.print("  2. Claim testnet USDC via faucet: [bold cyan]https://app.hyperliquid-testnet.xyz/drip[/bold cyan]")
        console.print("  3. (Recommended) Create an API Agent at: [bold cyan]https://app.hyperliquid-testnet.xyz/agents[/bold cyan]")
        console.print("  4. Set your credentials in [bold green].env[/bold green]:")
        console.print("     [dim]HYPERLIQUID_ACCOUNT_ADDRESS=0xYourMasterWalletAddress[/dim]")
        console.print("     [dim]HYPERLIQUID_SECRET_KEY=0xYourAgentPrivateKey[/dim]")
        console.print("  Or run directly via CLI: [bold green]python main.py check-account --account 0x...[/bold green]\n")
        return False

    console.print(f"Master Account: [bold yellow]{acct_address}[/bold yellow]")
    console.print(f"Network:        [bold magenta]{network_str}[/bold magenta] ({rest_url})\n")

    # 1. Query clearinghouse state
    try:
        resp = requests.post(
            rest_url,
            json={"type": "clearinghouseState", "user": acct_address},
            timeout=8,
        )
        resp.raise_for_status()
        state = resp.json()
    except Exception as e:
        console.print(f"[bold red]Failed to fetch account state: {e}[/bold red]\n")
        return False

    margin_summary = state.get("marginSummary", {})
    account_value = float(margin_summary.get("accountValue", 0.0))
    margin_used = float(margin_summary.get("totalMarginUsed", 0.0))
    withdrawable = float(state.get("withdrawable", 0.0))
    total_ntl_pos = float(margin_summary.get("totalNtlPos", 0.0))
    asset_positions = state.get("assetPositions", [])

    # Query spot balances as well
    spot_usdc = 0.0
    try:
        resp_spot = requests.post(
            rest_url,
            json={"type": "spotClearinghouseState", "user": acct_address},
            timeout=8,
        )
        if resp_spot.status_code == 200:
            for b in resp_spot.json().get("balances", []):
                if b.get("coin") == "USDC":
                    spot_usdc = float(b.get("total", 0.0))
    except Exception:
        pass

    # Display Balance Table
    bal_table = Table(title="Account Margin & Collateral Summary", box=None, padding=(0, 2))
    bal_table.add_column("Metric", justify="left")
    bal_table.add_column("Value (USD)", justify="right", style="bold white")

    bal_table.add_row("Perp Equity (Account Value)", f"${account_value:,.2f}")
    bal_table.add_row("Perp Available / Withdrawable Margin", f"[green]${withdrawable:,.2f}[/green]")
    bal_table.add_row("Perp Margin Used", f"[yellow]${margin_used:,.2f}[/yellow]")
    bal_table.add_row("Perp Notional Position Value", f"${total_ntl_pos:,.2f}")
    bal_table.add_row("Spot USDC Balance", f"[bold cyan]${spot_usdc:,.2f}[/bold cyan]")
    console.print(bal_table)
    console.print()

    # Display Open Positions
    if asset_positions:
        pos_table = Table(title=f"Active Perpetual Positions ({len(asset_positions)})", box=None, padding=(0, 2))
        pos_table.add_column("Coin", justify="left")
        pos_table.add_column("Side / Size", justify="right")
        pos_table.add_column("Entry Px", justify="right")
        pos_table.add_column("Unrealized PnL", justify="right")
        pos_table.add_column("Liq Px", justify="right")

        for ap in asset_positions:
            pos = ap.get("position", {})
            coin = pos.get("coin", "UNKNOWN")
            sz = float(pos.get("szi", 0.0))
            entry_px = float(pos.get("entryPx", 0.0))
            upnl = float(pos.get("unrealizedPnl", 0.0))
            liq_px = float(pos.get("liquidationPx", 0.0)) if pos.get("liquidationPx") else 0.0

            side_str = f"[green]LONG {sz:+.4f}[/green]" if sz > 0 else f"[red]SHORT {abs(sz):.4f}[/red]"
            pnl_c = "green" if upnl >= 0 else "red"
            liq_str = f"${liq_px:,.2f}" if liq_px > 0 else "None"

            pos_table.add_row(
                coin,
                side_str,
                f"${entry_px:,.2f}",
                f"[{pnl_c}]${upnl:+.2f}[/{pnl_c}]",
                liq_str,
            )
        console.print(pos_table)
    else:
        console.print("[dim green]● No active perpetual positions.[/dim green]")

    console.print()

    # 2. Check Open Limit Orders
    try:
        resp_orders = requests.post(
            rest_url,
            json={"type": "openOrders", "user": acct_address},
            timeout=8,
        )
        if resp_orders.status_code == 200:
            open_orders = resp_orders.json()
            if open_orders:
                orders_table = Table(title=f"Open Limit Orders ({len(open_orders)})", box=None, padding=(0, 2))
                orders_table.add_column("Coin", justify="left")
                orders_table.add_column("Side", justify="center")
                orders_table.add_column("Price", justify="right")
                orders_table.add_column("Size", justify="right")
                orders_table.add_column("Order ID", justify="right", style="dim")

                for o in open_orders:
                    side_str = "[green]BUY[/green]" if o.get("side") == "B" else "[red]SELL[/red]"
                    orders_table.add_row(
                        o.get("coin", "N/A"),
                        side_str,
                        f"${float(o.get('limitPx', 0)):,.2f}",
                        str(o.get("sz", 0)),
                        str(o.get("oid", "")),
                    )
                console.print(orders_table)
            else:
                console.print("[dim]● No open limit orders pending.[/dim]")
    except Exception:
        pass

    console.print()

    # 3. Check Signer / API Agent credentials if provided
    if secret_key:
        try:
            import eth_account
            signer = eth_account.Account.from_key(secret_key)
            signer_address = signer.address
            console.print(f"Signer Address: [bold cyan]{signer_address}[/bold cyan]")

            if signer_address.lower() == acct_address.lower():
                console.print("[bold green]✓ Signer matches Master Account address directly (Master Key connected)[/bold green]")
            else:
                # Query extra agents to check authorization
                try:
                    resp_agents = requests.post(
                        rest_url,
                        json={"type": "extraAgents", "user": acct_address},
                        timeout=8,
                    )
                    agents = resp_agents.json() if resp_agents.status_code == 200 else []
                    agent_addresses = [a.get("address", "").lower() for a in agents if isinstance(a, dict)]

                    if signer_address.lower() in agent_addresses:
                        console.print(f"[bold green]✓ Signer verified as an AUTHORIZED API AGENT for {acct_address}[/bold green]")
                    else:
                        agents_url = "https://app.hyperliquid-testnet.xyz/agents" if cfg.hyperliquid.use_testnet else "https://app.hyperliquid.xyz/API"
                        console.print(
                            f"[bold yellow]! Signer address {signer_address} is NOT yet listed as an authorized API Agent for {acct_address}.[/bold yellow]\n"
                            f"  Please approve it at: {agents_url}"
                        )
                except Exception:
                    console.print("[dim]Could not query agent authorization list.[/dim]")
        except Exception as e:
            console.print(f"[bold red]✗ Invalid private key: {e}[/bold red]")
    else:
        console.print("[dim yellow]Note: No HYPERLIQUID_SECRET_KEY provided (read-only mode active).[/dim yellow]")
        console.print("[dim]To enable live trade execution, configure an API Agent private key in .env.[/dim]")

    console.print()
    app_url = "https://app.hyperliquid-testnet.xyz/" if cfg.hyperliquid.use_testnet else "https://app.hyperliquid.xyz/"
    if account_value == 0.0 and spot_usdc > 0.0:
        console.print(f"[bold yellow]● Found ${spot_usdc:,.2f} USDC in your SPOT account balance![/bold yellow]")
        console.print("  Perpetual trading (BTC-PERP) uses your Perp Margin account.")
        console.print("  To move this USDC into Perps, either:")
        console.print(f"    1. On the web app ({app_url}): click 'Transfer' and choose Spot -> Perp.")
        console.print("    2. Or run CLI command: [bold green]python main.py transfer-to-perp[/bold green]\n")
    elif account_value == 0.0 and withdrawable == 0.0:
        if cfg.hyperliquid.use_testnet:
            console.print(f"[bold yellow]Testnet account has $0.00 balance. Claim mock USDC from: https://app.hyperliquid-testnet.xyz/drip[/bold yellow]\n")
        else:
            console.print(f"[bold yellow]Mainnet account has $0.00 Perp balance. Deposit USDC at: https://app.hyperliquid.xyz/[/bold yellow]\n")

    return True


def transfer_spot_to_perp(
    amount: Optional[float] = None,
    cfg: Optional[AppConfig] = None,
    console: Optional[Console] = None,
) -> bool:
    """Transfers mock USDC from Spot balance to Perpetual Margin balance on Hyperliquid Testnet."""
    cfg = cfg or AppConfig()
    console = console or Console()
    acct_address = cfg.account.account_address
    secret_key = cfg.account.secret_key
    rest_url = cfg.hyperliquid.rest_url

    network_str = cfg.hyperliquid.network_name.upper()
    console.print()
    console.print(f"[bold cyan]================================================================================[/bold cyan]")
    console.print(f"[bold cyan]           HYPERLIQUID {network_str}: TRANSFER SPOT USDC -> PERP MARGIN               [/bold cyan]")
    console.print(f"[bold cyan]================================================================================[/bold cyan]")

    if not acct_address or not secret_key:
        console.print("[bold red]Both HYPERLIQUID_ACCOUNT_ADDRESS and HYPERLIQUID_SECRET_KEY must be set in .env[/bold red]\n")
        return False

    import eth_account
    from hyperliquid.exchange import Exchange
    from hyperliquid.utils import constants

    # 1. Check Spot balance
    spot_usdc = 0.0
    try:
        resp_spot = requests.post(
            rest_url,
            json={"type": "spotClearinghouseState", "user": acct_address},
            timeout=8,
        )
        if resp_spot.status_code == 200:
            for b in resp_spot.json().get("balances", []):
                if b.get("coin") == "USDC":
                    spot_usdc = float(b.get("total", 0.0))
    except Exception as e:
        console.print(f"[bold red]Failed to check spot balance: {e}[/bold red]\n")
        return False

    if spot_usdc <= 0.0:
        console.print(f"[bold yellow]No USDC found in Spot balance for {acct_address}.[/bold yellow]")
        if cfg.hyperliquid.use_testnet:
            console.print("Claim mock USDC from the faucet first: https://app.hyperliquid-testnet.xyz/drip\n")
        else:
            console.print("Deposit USDC into your account first at: https://app.hyperliquid.xyz/\n")
        return False

    transfer_amt = amount if (amount is not None and amount > 0) else spot_usdc
    transfer_amt = min(transfer_amt, spot_usdc)

    console.print(f"Account:        [bold yellow]{acct_address}[/bold yellow]")
    console.print(f"Network:        [bold magenta]{cfg.hyperliquid.network_name}[/bold magenta]")
    console.print(f"Available Spot: [cyan]${spot_usdc:,.2f} USDC[/cyan]")
    console.print(f"Transferring:   [bold green]${transfer_amt:,.2f} USDC[/bold green] -> Perpetual Margin\n")

    try:
        wallet = eth_account.Account.from_key(secret_key)
        base_url = constants.TESTNET_API_URL if cfg.hyperliquid.use_testnet else constants.MAINNET_API_URL
        exchange = Exchange(wallet, base_url, account_address=acct_address)
        res = exchange.usd_class_transfer(transfer_amt, to_perp=True)
        if res.get("status") == "ok":
            console.print(f"[bold green]✓ Transfer confirmed on Hyperliquid {cfg.hyperliquid.network_name}![/bold green]")
            console.print(f"[bold green]✓ ${transfer_amt:,.2f} USDC is now available as Perpetual Margin.[/bold green]\n")
            # Refresh account status
            check_hyperliquid_account(cfg, console=console)
            return True
        else:
            console.print(f"[bold red]Transfer rejected: {res}[/bold red]\n")
            return False
    except Exception as e:
        console.print(f"[bold red]Transfer failed: {e}[/bold red]\n")
        return False


def connect_testnet(coin: str = "BTC") -> bool:
    """Convenience synchronous function to test and establish connection to Hyperliquid Testnet."""
    cfg = AppConfig()
    cfg.hyperliquid.use_testnet = True
    cfg.market.coin = coin
    return asyncio.run(test_hyperliquid_connection(cfg))


def connect_mainnet(coin: str = "BTC") -> bool:
    """Convenience synchronous function to test and establish connection to Hyperliquid Mainnet (Live)."""
    cfg = AppConfig()
    cfg.hyperliquid.use_testnet = False
    cfg.market.coin = coin
    return asyncio.run(test_hyperliquid_connection(cfg))


def print_strategies_status(cfg: Optional[AppConfig] = None, console: Optional[Console] = None) -> None:
    """Displays active and deselected strategies and alpha signals from the configuration file."""
    cfg = cfg or AppConfig()
    console = console or Console()
    strat_cfg = cfg.strategies

    console.print()
    console.print("[bold cyan]================================================================================[/bold cyan]")
    console.print(f"[bold cyan]           STRATEGY & ALPHA SIGNAL CONFIGURATION ({strat_cfg.filepath})           [/bold cyan]")
    console.print("[bold cyan]================================================================================[/bold cyan]\n")

    active_live = strat_cfg.live_execution.active_strategy
    active_strat = strat_cfg.get_strategy(active_live)
    live_status = "[bold green]ENABLED[/bold green]" if (active_strat and active_strat.enabled) else "[bold red]DISABLED[/bold red]"
    active_category = "Primary Execution Strategy" if strat_cfg.is_execution_strategy(active_live) else ("Scalping Strategy" if strat_cfg.is_scalping_strategy(active_live) else "Custom Strategy")
    coin = cfg.market.coin.upper()
    console.print(f"Active Live Strategy:    [bold yellow]{active_live}[/bold yellow] ({live_status}) - [dim cyan]{active_category}[/dim cyan]")
    console.print(f"Default Live Order Size: [white]{strat_cfg.live_execution.order_size_btc} {coin}[/white]")
    console.print(f"Max Position Guardrail:  [white]{strat_cfg.live_execution.max_position_btc} {coin}[/white]\n")

    table_exec = Table(title="Primary Execution Strategies (4 New Core Microstructure Strategies)", header_style="bold cyan")
    table_exec.add_column("Strategy Name", justify="left", style="bold")
    table_exec.add_column("Status", justify="center")
    table_exec.add_column("Type", justify="center", style="dim")
    table_exec.add_column("Underlying Signal", justify="left")
    table_exec.add_column("Threshold", justify="right")
    table_exec.add_column(f"Size ({coin})", justify="right")
    table_exec.add_column("Description", justify="left", style="dim")

    for s_name, s in strat_cfg.execution_strategies.items():
        status = "[bold green]ENABLED[/bold green]" if s.enabled else "[dim red]DISABLED[/dim red]"
        table_exec.add_row(
            s_name,
            status,
            s.execution_type,
            s.signal_key,
            f"{s.entry_threshold:.2f}",
            f"{s.order_size_btc:.4f}",
            s.description,
        )
    console.print(table_exec)
    console.print("\n")

    table_scalp = Table(title="Scalping Strategies (Legacy Micro-Scalp Maker & Taker Strategies)", header_style="bold yellow")
    table_scalp.add_column("Strategy Name", justify="left", style="bold")
    table_scalp.add_column("Status", justify="center")
    table_scalp.add_column("Type", justify="center", style="dim")
    table_scalp.add_column("Underlying Signal", justify="left")
    table_scalp.add_column("Threshold", justify="right")
    table_scalp.add_column(f"Size ({coin})", justify="right")
    table_scalp.add_column("Description", justify="left", style="dim")

    for s_name, s in strat_cfg.scalping_strategies.items():
        status = "[bold green]ENABLED[/bold green]" if s.enabled else "[dim red]DISABLED[/dim red]"
        table_scalp.add_row(
            s_name,
            status,
            s.execution_type,
            s.signal_key,
            f"{s.entry_threshold:.2f}",
            f"{s.order_size_btc:.4f}",
            s.description,
        )
    console.print(table_scalp)
    console.print("\n")

    table_alpha = Table(title="Microstructure Alpha Signals (Predictive Factors)", header_style="bold magenta")
    table_alpha.add_column("Signal Factor", justify="left", style="bold")
    table_alpha.add_column("Status", justify="center")
    table_alpha.add_column("Weight", justify="right")
    table_alpha.add_column("Description", justify="left", style="dim")

    weights = strat_cfg.get_signal_weights()
    for a_name, a in strat_cfg.alpha_signals.items():
        status = "[bold green]ENABLED[/bold green]" if a.enabled else "[dim red]DISABLED[/dim red]"
        wt_str = f"{weights.get(a_name, 0.0):.2f}" if (a.enabled and a_name in weights) else "-"
        table_alpha.add_row(
            a_name,
            status,
            wt_str,
            a.description,
        )
    console.print(table_alpha)
    console.print(f"\n[dim white]To select or deselect strategies, edit [bold yellow]{strat_cfg.filepath}[/bold yellow] and toggle 'enabled': true / false.[/dim white]\n")


def handle_audit_mode(cfg: AppConfig, args: argparse.Namespace, console: Console) -> None:
    """CLI handler for inspecting and auditing trade logs across sessions and strategies."""
    audit_dir = "audits"
    session_id = args.session.strip() if getattr(args, "session", None) else ""
    strategy_filter = args.strategy.strip() if getattr(args, "strategy", None) else None

    # Handle maintenance actions
    if getattr(args, "prune_empty", False):
        console.print("\n[bold yellow]Scanning and pruning empty audit sessions (0 trades)...[/bold yellow]")
        deleted = SessionAuditor.prune_empty_sessions(audit_dir=audit_dir)
        console.print(f"[bold green]Successfully pruned {deleted} empty session folders from {audit_dir}/.[/bold green]\n")
        return

    if getattr(args, "repair", False):
        console.print("\n[bold yellow]Scanning and repairing stalled session manifests from all_trades.csv...[/bold yellow]")
        repaired = SessionAuditor.repair_stalled_manifests(audit_dir=audit_dir)
        console.print(f"[bold green]Successfully repaired and backfilled {repaired} session manifests.[/bold green]\n")
        return

    # If --session latest or --strategy specified without session, resolve latest session
    if session_id.lower() == "latest" or (not session_id and strategy_filter):
        latest_id = SessionAuditor.get_latest_session_id(audit_dir=audit_dir)
        if not latest_id:
            console.print("[bold red]No audit sessions found in audits/.[/bold red]")
            return
        session_id = latest_id

    # If no session specified: list historical sessions
    if not session_id:
        limit = args.limit if getattr(args, "limit", None) else 50
        include_empty = getattr(args, "include_empty", False)
        all_active_sessions = SessionAuditor.list_all_sessions(audit_dir=audit_dir, include_empty=include_empty)
        if not all_active_sessions:
            console.print("\n[bold yellow]No trade audit sessions found in audits/.[/bold yellow]")
            console.print("Run a live session ([bold cyan]python main.py live[/bold cyan]) or replay ([bold cyan]python main.py replay --replay-file <path>[/bold cyan]) first to generate auditable sessions.\n")
            return

        sessions = all_active_sessions[:limit]
        count_label = f"SHOWING {len(sessions)} OF {len(all_active_sessions)}" if len(all_active_sessions) > len(sessions) else f"{len(sessions)}"
        console.print("\n" + "=" * 95)
        console.print(f"[bold cyan]HYPERLIQUID L2 AUDIT SYSTEM - RECORDED TRADING SESSIONS ({count_label} SESSIONS FOUND)[/bold cyan]")
        console.print("=" * 95 + "\n")

        table = Table(title="Historical Trading Sessions", header_style="bold cyan")
        table.add_column("Session ID", justify="left", style="bold")
        table.add_column("Start Time", justify="left")
        table.add_column("Duration", justify="center")
        table.add_column("Net", justify="center")
        table.add_column("Mode", justify="center")
        table.add_column("Trades", justify="right")
        table.add_column("Win%", justify="right")
        table.add_column("Net PnL ($)", justify="right")
        table.add_column("Volume (BTC)", justify="right")
        table.add_column("Active Strategies", justify="left", style="dim")

        for s in sessions:
            s_id = s.get("session_id", "unknown")
            dur = s.get("duration_secs", 0.0)
            dur_str = f"{int(dur // 60)}m {int(dur % 60)}s" if dur >= 60 else f"{dur:.1f}s"
            net = s.get("network", "Testnet")
            is_live = s.get("is_live_mode", False)
            mode_str = "[bold red]LIVE[/bold red]" if is_live else "[green]PAPER[/green]"
            sum_data = s.get("session_summary", {})
            total_tr = sum_data.get("total_trades", 0)
            win_pct = sum_data.get("win_rate_pct", 0.0)
            net_pnl = sum_data.get("net_pnl_usd", 0.0)
            vol = sum_data.get("total_volume_btc", 0.0)
            pnl_c = "green" if net_pnl >= 0 else "red"
            strats = s.get("enabled_strategies", [])
            strat_str = ", ".join(strats[:3]) + (f" (+{len(strats)-3})" if len(strats) > 3 else "")

            table.add_row(
                s_id,
                s.get("start_time_iso", "")[:19].replace("T", " "),
                dur_str,
                net,
                mode_str,
                str(total_tr),
                f"{win_pct:.1f}%",
                f"[{pnl_c}]${net_pnl:+.2f}[/{pnl_c}]",
                f"{vol:.4f}",
                strat_str,
            )

        console.print(table)
        console.print("\n[dim white]To inspect individual trades for a session:[/dim white]")
        console.print("  [bold yellow]python main.py audit --session latest[/bold yellow]")
        console.print("  [bold yellow]python main.py audit --session <session_id> [--strategy <strategy_name>][/bold yellow]\n")
        return

    # Specific session inspection
    session_path = os.path.join(audit_dir, session_id)
    if not os.path.exists(session_path):
        console.print(f"[bold red]Session '{session_id}' not found at {session_path}[/bold red]")
        return

    manifest = SessionAuditor.load_session_manifest(session_id, audit_dir=audit_dir)
    trades = SessionAuditor.load_session_trades(session_id, strategy_name=strategy_filter, audit_dir=audit_dir)

    console.print("\n" + "=" * 95)
    console.print(f"[bold cyan]SESSION AUDIT INSPECTION: {session_id}[/bold cyan]")
    console.print("=" * 95)

    if manifest:
        live_recon = manifest.get("live_exchange_reconciliation")
        if live_recon:
            real_pnl = float(live_recon.get("real_net_realized_usd", 0.0))
            real_pnl_c = "green" if real_pnl >= 0 else "red"
            recon_table = Table(title="REAL ON-CHAIN HYPERLIQUID PERFORMANCE (Exchange Reconciled)", header_style="bold green")
            recon_table.add_column("Fills", justify="center")
            recon_table.add_column("Volume", justify="center")
            recon_table.add_column("Real Closed PnL ($)", justify="right")
            recon_table.add_column("Real Fees Paid ($)", justify="right")
            recon_table.add_column("Real Net Realized PnL ($)", justify="right", style=f"bold {real_pnl_c}")
            recon_table.add_column("Fills Ledger CSV", justify="left", style="dim")

            recon_table.add_row(
                f"{live_recon.get('total_fills', 0)} ({live_recon.get('maker_fills', 0)} M / {live_recon.get('taker_fills', 0)} T)",
                f"{float(live_recon.get('total_volume_btc', 0.0)):.4f} BTC",
                f"${float(live_recon.get('real_closed_pnl_usd', 0.0)):+.4f}",
                f"${float(live_recon.get('real_fees_paid_usd', 0.0)):.4f}",
                f"[{real_pnl_c}]${real_pnl:+.4f}[/{real_pnl_c}]",
                live_recon.get("fills_csv", "live_exchange_fills.csv"),
            )
            console.print(recon_table)
            console.print("\n")

        s_sum = manifest.get("session_summary", {})
        net_mode = "LIVE REAL ORDERS" if manifest.get("is_live_mode") else "PAPER TRADING SIMULATION"
        console.print(f"Network:      [bold magenta]Hyperliquid {manifest.get('network', 'Testnet')}[/bold magenta] ({net_mode})")
        console.print(f"Start Time:   [dim]{manifest.get('start_time_iso')}[/dim] | End Time: [dim]{manifest.get('end_time_iso')}[/dim]")
        dur = manifest.get("duration_secs", 0.0)
        console.print(f"Duration:     [dim]{int(dur // 60)}m {int(dur % 60)}s ({dur:.1f}s)[/dim]")
        pnl = s_sum.get("net_pnl_usd", 0.0)
        pnl_c = "green" if pnl >= 0 else "red"
        paper_label = "Paper Benchmark" if live_recon else "Overview"
        console.print(
            f"{paper_label}: Total Trades: [bold]{s_sum.get('total_trades', 0)}[/bold] | "
            f"Win Rate: [bold]{s_sum.get('win_rate_pct', 0.0):.1f}%[/bold] | "
            f"Net PnL: [bold {pnl_c}]${pnl:+.2f}[/bold {pnl_c}] | "
            f"Fees: [dim]${s_sum.get('total_fees_usd', 0.0):.4f}[/dim] | "
            f"Volume: [dim]{s_sum.get('total_volume_btc', 0.0):.4f} BTC[/dim]\n"
        )

        # 1. Per-Strategy Summary Table
        strat_metrics = manifest.get("strategies", {})
        if strat_metrics and not strategy_filter:
            coin = manifest.get("coin", getattr(args, "coin", "BTC")).upper() if manifest else getattr(args, "coin", "BTC").upper()
            strat_table = Table(title="Strategy Audit Breakdown (Session Aggregates)", header_style="bold cyan")
            strat_table.add_column("Strategy Name", justify="left", style="bold")
            strat_table.add_column("Trades", justify="right")
            strat_table.add_column("Win%", justify="right")
            strat_table.add_column(f"Volume ({coin})", justify="right")
            strat_table.add_column("Fees ($)", justify="right")
            strat_table.add_column("Net PnL ($)", justify="right")
            strat_table.add_column("Avg Ret", justify="right")
            strat_table.add_column("Profit Factor", justify="right")
            strat_table.add_column("Audit CSV", justify="left", style="dim")

            for st_name, st in sorted(strat_metrics.items()):
                st_pnl = st.get("net_pnl_usd", 0.0)
                st_c = "green" if st_pnl >= 0 else "red"
                fees = st.get("total_fees_usd", 0.0)
                fee_str = f"+${abs(fees):.2f}" if fees <= 0 else f"-${fees:.2f}"
                strat_table.add_row(
                    st_name,
                    str(st.get("trades", 0)),
                    f"{st.get('win_rate_pct', 0.0):.1f}%",
                    f"{st.get('total_volume_btc', 0.0):.4f}",
                    fee_str,
                    f"[{st_c}]${st_pnl:+.2f}[/{st_c}]",
                    f"{st.get('avg_return_bps', 0.0):+.1f} bps",
                    f"{st.get('profit_factor', 0.0):.2f}",
                    f"strategies/{st_name}.csv",
                )
            console.print(strat_table)
            console.print("\n")

    # 2. Individual Trades Table
    limit = getattr(args, "limit", 50) or 50
    display_trades = trades[-limit:] if len(trades) > limit else trades
    strat_label = f"Strategy '{strategy_filter}'" if strategy_filter else "All Strategies"
    title_suffix = f" (Showing last {len(display_trades)} of {len(trades)})" if len(trades) > len(display_trades) else f" (Total {len(trades)})"

    if display_trades:
        coin = manifest.get("coin", getattr(args, "coin", "BTC")).upper() if manifest else getattr(args, "coin", "BTC").upper()
        trade_table = Table(title=f"Individual Executed Trades - {strat_label}{title_suffix}", header_style="bold green")
        trade_table.add_column("Trade ID", justify="left", style="bold")
        if not strategy_filter:
            trade_table.add_column("Strategy", justify="left")
        trade_table.add_column("Side", justify="center")
        trade_table.add_column(f"Size ({coin})", justify="right")
        trade_table.add_column("Entry Time", justify="center", style="dim")
        trade_table.add_column("Entry Px", justify="right")
        trade_table.add_column("Exit Time", justify="center", style="dim")
        trade_table.add_column("Exit Px", justify="right")
        trade_table.add_column("Hold", justify="right")
        trade_table.add_column("Exit Reason", justify="left")
        trade_table.add_column("Total Fee", justify="right")
        trade_table.add_column("Net PnL ($)", justify="right")
        trade_table.add_column("Return", justify="right")

        for tr in display_trades:
            net_pnl = float(tr.get("net_pnl_usd", 0.0))
            pnl_c = "green" if net_pnl >= 0 else "red"
            side = tr.get("side", "LONG")
            side_c = "green" if side == "LONG" else "red"
            fee = float(tr.get("total_fees_usd", 0.0))
            fee_str = f"+${abs(fee):.4f}" if fee <= 0 else f"-${fee:.4f}"
            ret_bps = float(tr.get("return_bps", 0.0))

            row = [
                tr.get("trade_id", ""),
            ]
            if not strategy_filter:
                row.append(tr.get("strategy_name", ""))
            row.extend([
                f"[{side_c}]{side}[/{side_c}]",
                tr.get("size_btc", "0.0000"),
                tr.get("entry_time", "")[11:19],
                f"${float(tr.get('entry_price', 0.0)):,.1f}",
                tr.get("exit_time", "")[11:19],
                f"${float(tr.get('exit_price', 0.0)):,.1f}",
                f"{float(tr.get('holding_secs', 0.0)):.1f}s",
                tr.get("exit_reason", ""),
                fee_str,
                f"[{pnl_c}]${net_pnl:+.2f}[/{pnl_c}]",
                f"[{pnl_c}]{ret_bps:+.1f} bps[/{pnl_c}]",
            ])
            trade_table.add_row(*row)

        console.print(trade_table)
    else:
        filter_msg = f" for strategy '{strategy_filter}'" if strategy_filter else ""
        console.print(f"[dim yellow]No executed trades found in this session{filter_msg}.[/dim yellow]")

    # 3. Live Exchange Orders (if any)
    live_csv = os.path.join(session_path, "live_orders.csv")
    if os.path.exists(live_csv):
        import csv
        live_orders = []
        try:
            with open(live_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    live_orders.append(row)
        except Exception:
            pass

        if live_orders:
            disp_orders = live_orders[-limit:]
            console.print("\n")
            live_table = Table(title=f"Live Exchange Orders - Hyperliquid Testnet/Mainnet (Total {len(live_orders)})", header_style="bold magenta")
            live_table.add_column("Event ID", justify="left")
            live_table.add_column("Time", justify="center", style="dim")
            live_table.add_column("Event", justify="center")
            live_table.add_column("Side", justify="center")
            live_table.add_column("Size", justify="right")
            live_table.add_column("Price", justify="right")
            live_table.add_column("TIF", justify="center")
            live_table.add_column("Order ID", justify="center")
            live_table.add_column("Status", justify="center")
            live_table.add_column("Fill Px", justify="right")

            for o in disp_orders:
                ev_type = o.get("event_type", "")
                ev_c = "green" if ev_type in ("RESTING", "FILLED") else ("yellow" if ev_type == "SUBMIT" else "red")
                live_table.add_row(
                    o.get("event_id", ""),
                    o.get("timestamp", "")[11:19],
                    f"[{ev_c}]{ev_type}[/{ev_c}]",
                    o.get("side", ""),
                    o.get("size_btc", ""),
                    f"${float(o.get('price', 0.0)):,.1f}",
                    o.get("tif", ""),
                    o.get("order_id", "-") or "-",
                    o.get("status", ""),
                    f"${float(o.get('fill_price', 0.0)):,.1f}" if o.get("fill_price") else "-",
                )
            console.print(live_table)

    # 4. Audit File Locations
    console.print("\n[bold cyan]Session Audit Artifacts:[/bold cyan]")
    console.print(f"  - Session Folder:        [yellow]{session_path}[/yellow]")
    console.print(f"  - Master Trades CSV:     [dim]{os.path.join(session_path, 'all_trades.csv')}[/dim]")
    console.print(f"  - Per-Strategy CSVs:     [dim]{os.path.join(session_path, 'strategies')}/<strategy_name>.csv[/dim]")
    console.print(f"  - JSONL Event Stream:    [dim]{os.path.join(session_path, 'trades_audit.jsonl')}[/dim]")
    console.print(f"  - Formatted Report:      [dim]{os.path.join(session_path, 'session_audit_report.md')}[/dim]\n")


def main():
    parser = argparse.ArgumentParser(description="Hyperliquid L2 Microstructure Alpha Engine")
    parser.add_argument("mode", choices=["live", "test-connection", "testnet", "check-account", "transfer-to-perp", "place-order", "cancel-orders", "benchmark", "replay", "train-ml", "collect", "strategies", "audit"], help="Execution mode")
    parser.add_argument("--strategies-config", type=str, default="strategies.json", help="Path to strategies configuration JSON (default: strategies.json)")
    parser.add_argument("--strategy", type=str, default="", help="Active strategy to use for live execution or audit filter (overrides config)")
    parser.add_argument("--session", type=str, default="", help="Session ID or 'latest' to inspect in audit mode")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of trades to display in audit tables (default: 50)")
    parser.add_argument("--amount", type=float, default=0.0, help="Amount of USDC to transfer between Spot and Perp (default: max)")
    parser.add_argument("--coin", type=str, default="BTC", help="Target coin symbol (default: BTC)")
    parser.add_argument("--account", type=str, default="", help="Hyperliquid master wallet address (0x...)")
    parser.add_argument("--secret-key", type=str, default="", help="Hyperliquid API Agent or wallet private key")
    parser.add_argument("--live-orders", action="store_true", help="Execute real live orders on Hyperliquid Testnet")
    parser.add_argument("--order-size", type=float, default=0.0005, help="Order size in BTC for live execution (default: 0.0005 BTC ~ $40)")
    parser.add_argument("--side", type=str, choices=["BUY", "SELL"], default="BUY", help="Order side for place-order mode")
    parser.add_argument("--price", type=float, default=0.0, help="Limit price for place-order mode (default: 2%% below/above mid)")
    parser.add_argument("--testnet", dest="use_testnet", action="store_true", default=None, help="Connect to Hyperliquid Testnet (default)")
    parser.add_argument("--mainnet", dest="use_testnet", action="store_false", default=None, help="Connect to Hyperliquid Mainnet")
    parser.add_argument("--duration", type=int, default=0, help="Run duration in seconds (0 = infinite)")
    parser.add_argument("--hours", type=float, default=0.0, help="Max collection duration in hours (0 = continuous)")
    parser.add_argument("--horizon", type=float, default=5.0, help="Forward prediction horizon in seconds for ML training")
    parser.add_argument(
        "--ui",
        type=str,
        choices=["cli", "browser", "web", "none", "no-ui"],
        default=None,
        help="Interface display mode: 'cli' (interactive terminal UI), 'browser' (web dashboard), or 'no-ui'/'none' (headless)",
    )
    parser.add_argument("--cli", action="store_true", help="Display interactive Rich CLI terminal dashboard")
    parser.add_argument("--browser", action="store_true", help="Launch lightweight hardware-accelerated Web Dashboard (alias for --web)")
    parser.add_argument("--no-ui", action="store_true", help="Disable visual UI (run in headless mode)")
    parser.add_argument("--web", action="store_true", help="Launch lightweight hardware-accelerated Web Dashboard (FastAPI + WebSocket)")
    parser.add_argument("--port", type=int, default=8000, help="Web dashboard port (default: 8000)")
    parser.add_argument("--open-browser", action="store_true", help="Automatically open web dashboard in default browser")
    parser.add_argument("--replay-file", type=str, default="", help="Path to recording file for replay mode")
    parser.add_argument("--speed", type=float, default=1.0, help="Replay speed multiplier")
    parser.add_argument("--size", type=float, default=0.1, help="Simulated order size in BTC (default: 0.1 BTC)")
    parser.add_argument("--cash", type=float, default=10000.0, help="Initial simulated account capital in USD (default: $10,000)")
    parser.add_argument("--capital", type=float, default=0.0, help="Total trading capital in USD to dynamically scale order sizes (e.g. 5000 for $5,000)")
    parser.add_argument("--allocation", type=float, default=1.0, help="Fraction of capital per trade (default: 1.0 for 100%, 0.2 for 20%)")
    parser.add_argument("--save-model", type=str, default="models/l2_trained_weights.json", help="Model weights save path")
    parser.add_argument("--max-files", type=int, default=0, help="Maximum number of files to ingest for ML training (0 = all)")
    parser.add_argument("--prune-empty", action="store_true", help="Remove empty audit session directories (0 trades)")
    parser.add_argument("--repair", action="store_true", help="Repair and backfill stalled audit manifests from trade CSVs")
    parser.add_argument("--include-empty", action="store_true", help="Include 0-trade sessions in audit listing")
    parser.add_argument("--no-audit", action="store_true", help="Disable audit recording in live/replay")
    parser.add_argument(
        "--scalping",
        nargs="?",
        const="true",
        default=None,
        type=str,
        help="Toggle scalping mode: --scalping true (or --scalping) enables all 8 scalping strategies and disables the 4 core execution strategies; --scalping false enables core strategies and disables scalping strategies.",
    )
    parser.add_argument(
        "--save-config",
        action="store_true",
        help="Persist modified strategy configuration to strategies.json",
    )
    parser.add_argument(
        "--stock", "--xyz-stock",
        dest="xyz_stock",
        action="store_true",
        help="Flag asset as an XYZ stock/equity on Hyperliquid (auto-configures 0.009% taker and 0.003% maker fees)",
    )
    parser.add_argument(
        "--taker-fee",
        type=float,
        default=None,
        help="Custom taker fee in bps (e.g. 0.9 for 0.009% on XYZ stocks like SKHYNIX, 4.5 for crypto)",
    )
    parser.add_argument(
        "--maker-fee",
        type=float,
        default=None,
        help="Custom maker fee in bps (e.g. 0.3 for 0.003% on XYZ stocks like SKHYNIX, 1.5 for crypto)",
    )
    args = parser.parse_args()

    cfg = AppConfig()
    if args.strategies_config:
        from config import StrategiesConfig
        cfg.strategies = StrategiesConfig.load(args.strategies_config)

    if args.scalping is not None:
        scalp_flag = str(args.scalping).strip().lower() in ("true", "1", "yes", "t", "on")
        cfg.strategies.set_scalping_mode(enabled=scalp_flag, save=args.save_config)
        console = Console()
        if scalp_flag:
            save_msg = f" (Saved to {cfg.strategies.filepath})" if args.save_config else ""
            console.print(f"[bold yellow]⚡ Scalping Mode Activated (--scalping true): 8 scalping strategies ENABLED, 4 core execution strategies DISABLED.{save_msg}[/bold yellow]")
        else:
            save_msg = f" (Saved to {cfg.strategies.filepath})" if args.save_config else ""
            console.print(f"[bold cyan]🛡️ Core Mode Activated (--scalping false): Core execution strategies ENABLED, 8 scalping strategies DISABLED.{save_msg}[/bold cyan]")

    if args.strategy:
        strat_name = args.strategy.strip()
        valid_strats = list(cfg.strategies.all_strategies.keys())
        if args.mode not in ("audit",) and strat_name not in valid_strats:
            Console().print(f"[bold red]Error: Unknown strategy '{strat_name}'. Valid strategies: {', '.join(valid_strats)}[/bold red]")
            sys.exit(1)
        strat_obj = cfg.strategies.get_strategy(strat_name)
        if strat_obj:
            strat_obj.enabled = True
        cfg.strategies.live_execution.active_strategy = strat_name

    if args.use_testnet is not None:
        cfg.hyperliquid.use_testnet = args.use_testnet
    if args.account:
        cfg.account.account_address = args.account.strip()
    if args.secret_key:
        cfg.account.secret_key = args.secret_key.strip()
    
    # Configure asset and fee schedule (auto-detects XYZ stocks like SKHYNIX)
    is_stock_override = True if args.xyz_stock else None
    cfg.market.configure_for_coin(
        args.coin,
        is_stock=is_stock_override,
        taker_fee_bps=args.taker_fee,
        maker_fee_bps=args.maker_fee,
    )

    if cfg.market.is_xyz_stock:
        console = Console()
        console.print(
            f"[bold cyan]Resolved XYZ Market:[/bold cyan] '{args.coin}' -> canonical Hyperliquid ticker '[bold green]{cfg.market.coin}[/bold green]' "
            f"(Fees: [bold yellow]{cfg.market.maker_fee_bps:.2f} bps maker / {cfg.market.taker_fee_bps:.2f} bps taker[/bold yellow])"
        )
        if cfg.market.coin == "xyz:SKHY":
            console.print("   [dim cyan]ℹ Note: Hyperliquid also supports 'xyz:SKHX' (SK Hynix ADS contract).[/dim cyan]")

    if args.capital > 0:
        args.cash = args.capital
    cfg.backtest.initial_cash_usd = args.cash
    cfg.backtest.capital_usd = args.capital if args.capital > 0 else (args.cash if args.cash != 10000.0 else None)
    cfg.backtest.capital_allocation_pct = args.allocation

    # Dynamic scaling for backtesting & live trading based on capital
    if cfg.backtest.capital_usd is not None and cfg.backtest.capital_usd > 0:
        ratio = cfg.backtest.capital_usd / 10000.0
        if cfg.market.coin == "HYPE":
            if args.size == 0.1:
                args.size = round(95.0 * ratio, 2)
            if args.order_size == 0.0005:
                args.order_size = round(60.0 * ratio * args.allocation, 2)
        elif cfg.market.coin == "BTC":
            if args.size == 0.1:
                args.size = round(0.1 * ratio, 5)
            if args.order_size == 0.0005:
                args.order_size = round(0.06 * ratio * args.allocation, 5)
        elif cfg.market.coin == "SOL" and args.size == 0.1:
            args.size = round(50.0 * ratio, 2)
        elif cfg.market.coin == "ETH" and args.size == 0.1:
            args.size = round(3.0 * ratio, 4)
        elif cfg.market.is_xyz_stock:
            if args.size == 0.1:
                args.size = round(50.0 * ratio, 2)
            if args.order_size == 0.0005:
                args.order_size = max(1.0, round(25.0 * ratio * args.allocation, 2))
    else:
        if cfg.market.coin == "HYPE":
            if args.order_size == 0.0005:
                args.order_size = 1.0  # 1.0 HYPE (~$90 notional, exceeds $10 minimum)
            if args.size == 0.1:
                args.size = 95.0       # 95.0 HYPE (~$8,550 notional, matching 0.1 BTC baseline)
        elif cfg.market.is_xyz_stock:
            if args.order_size == 0.0005:
                args.order_size = 1.0  # 1.0 share default for live execution
            if args.size == 0.1:
                args.size = 50.0       # 50 shares default for simulated backtesting (~$5,000-$10,000 notional)

    cfg.backtest.order_size_btc = args.size

    # Resolve UI display mode (3 explicit choices: 'cli', 'browser', 'no-ui')
    ui_mode = "cli"
    if args.ui:
        m = args.ui.lower()
        if m in ("none", "no-ui"):
            ui_mode = "no-ui"
        elif m in ("browser", "web"):
            ui_mode = "browser"
        elif m == "cli":
            ui_mode = "cli"
    elif args.no_ui:
        ui_mode = "no-ui"
    elif args.browser or args.web:
        ui_mode = "browser"
    elif args.cli:
        ui_mode = "cli"

    show_cli_ui = (ui_mode == "cli")
    enable_web = (ui_mode == "browser" or args.web or args.browser)

    console = Console()

    if args.mode == "strategies":
        print_strategies_status(cfg, console=console)
        return

    elif args.mode == "audit":
        handle_audit_mode(cfg, args, console=console)
        return

    if args.mode in ("test-connection", "testnet"):
        asyncio.run(test_hyperliquid_connection(cfg, console=console))

    elif args.mode == "check-account":
        check_hyperliquid_account(cfg, console=console)

    elif args.mode == "transfer-to-perp":
        transfer_spot_to_perp(amount=args.amount if args.amount > 0 else None, cfg=cfg, console=console)

    elif args.mode == "place-order":
        from engine.live_executor import LiveOrderExecutor
        executor = LiveOrderExecutor(config=cfg, console=console, default_order_size_btc=args.order_size)
        is_buy = args.side.upper() == "BUY"
        px = args.price
        if px <= 0:
            info = executor.info
            mids = info.all_mids() if info else {}
            mid = float(mids.get(cfg.market.coin, 83000.0))
            px = round(mid * 0.95 if is_buy else mid * 1.05, 1)
        executor.place_limit_order(is_buy=is_buy, size_btc=args.order_size, price=px, post_only=True)

    elif args.mode == "cancel-orders":
        from engine.live_executor import LiveOrderExecutor
        executor = LiveOrderExecutor(config=cfg, console=console)
        cnt = executor.cancel_all_orders()
        console.print(f"[bold green]✓ Cancelled {cnt} open orders on {cfg.market.coin}.[/bold green]")

    elif args.mode == "live":
        en_exec = list(cfg.strategies.get_enabled_execution_strategy_defs().keys())
        en_scalp = list(cfg.strategies.get_enabled_scalping_strategy_defs().keys())
        dis_exec = [s for s in cfg.strategies.execution_strategies if s not in en_exec]
        dis_scalp = [s for s in cfg.strategies.scalping_strategies if s not in en_scalp]
        en_strats = en_exec + en_scalp
        console.print(f"[bold cyan]Strategies Configuration ({cfg.strategies.filepath}):[/bold cyan]")
        console.print(f"  • [bold cyan]Core Execution (4 New):[/bold cyan] [green]{len(en_exec)} active[/green] ({', '.join(en_exec) if en_exec else 'none'}) | [dim red]{len(dis_exec)} deselected[/dim red]")
        console.print(f"  • [bold yellow]Scalping (Legacy):[/bold yellow] [green]{len(en_scalp)} active[/green] ({', '.join(en_scalp) if en_scalp else 'none'}) | [dim red]{len(dis_scalp)} deselected[/dim red]")
        ui_label = {
            "cli": "CLI (Interactive Terminal Dashboard)",
            "browser": f"BROWSER (Web Dashboard running on http://localhost:{args.port})",
            "no-ui": "NO-UI (Headless Background Mode)",
        }.get(ui_mode, ui_mode.upper())
        console.print(f"[bold cyan]Interface Mode:[/bold cyan] [bold green]{ui_label}[/bold green]")
        fee_profile_name = "XYZ Stock / Equities" if cfg.market.is_xyz_stock else "Crypto Perps"
        console.print(f"[bold cyan]Asset & Fees:[/bold cyan] [bold green]{cfg.market.coin}[/bold green] ([yellow]{fee_profile_name}[/yellow]) | Maker: [green]{cfg.market.maker_fee_bps:.2f} bps[/green] ({cfg.market.maker_fee_bps/100:.4f}%) | Taker: [yellow]{cfg.market.taker_fee_bps:.2f} bps[/yellow] ({cfg.market.taker_fee_bps/100:.4f}%)")
        if args.live_orders:
            cfg.backtest.order_size_btc = args.order_size
            net = cfg.hyperliquid.network_name.upper()
            active_live = cfg.strategies.live_execution.active_strategy
            other_active = [s for s in en_strats if s != active_live]
            if other_active:
                strats_desc = f"{active_live} (Primary) + {', '.join(other_active)} (Dynamic Multi-Strategy Dispatch)"
            else:
                strats_desc = active_live
            console.print(f"\n[bold red blink]⚠ LIVE {net} ORDER EXECUTION ENABLED! Active Strategies: {strats_desc}[/bold red blink]\n")
        runner = L2EngineRunner(
            config=cfg,
            record_data=True,
            live_orders=args.live_orders,
            order_size_btc=args.order_size,
            enable_audit=not args.no_audit,
            web_mode=enable_web,
            web_port=args.port,
            open_browser=args.open_browser,
        )
        try:
            asyncio.run(runner.run_live(duration_secs=args.duration if args.duration > 0 else None, show_ui=show_cli_ui))
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            runner.close()
            runner.print_summary_report()
            sys.exit(0)

    elif args.mode == "benchmark":
        duration = args.duration if args.duration > 0 else 30
        console.print(f"[bold yellow]Running live benchmark on {cfg.market.coin} ({cfg.hyperliquid.network_name}) for {duration} seconds...[/bold yellow]")
        ui_label = {
            "cli": "CLI (Interactive Terminal Dashboard)",
            "browser": f"BROWSER (Web Dashboard running on http://localhost:{args.port})",
            "no-ui": "NO-UI (Headless Background Mode)",
        }.get(ui_mode, ui_mode.upper())
        console.print(f"[bold cyan]Interface Mode:[/bold cyan] [bold green]{ui_label}[/bold green]")
        fee_profile_name = "XYZ Stock / Equities" if cfg.market.is_xyz_stock else "Crypto Perps"
        console.print(f"[bold cyan]Asset & Fees:[/bold cyan] [bold green]{cfg.market.coin}[/bold green] ([yellow]{fee_profile_name}[/yellow]) | Maker: [green]{cfg.market.maker_fee_bps:.2f} bps[/green] ({cfg.market.maker_fee_bps/100:.4f}%) | Taker: [yellow]{cfg.market.taker_fee_bps:.2f} bps[/yellow] ({cfg.market.taker_fee_bps/100:.4f}%)")
        runner = L2EngineRunner(
            config=cfg,
            record_data=True,
            enable_audit=not args.no_audit,
            web_mode=enable_web,
            web_port=args.port,
            open_browser=args.open_browser,
        )
        try:
            asyncio.run(runner.run_live(duration_secs=duration, show_ui=show_cli_ui))
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            runner.close()
            runner.print_summary_report()
            sys.exit(0)

    elif args.mode == "replay":
        if not args.replay_file:
            print("Please specify --replay-file")
            sys.exit(1)
        # Auto-detect coin from file path if not explicitly overridden
        fpath_lower = args.replay_file.lower().replace("\\", "/")
        for c in ["btc", "hype", "sol", "eth"]:
            if f"hl_{c}_" in fpath_lower or f"/{c}/" in fpath_lower:
                cfg.market.coin = c.upper()
                ratio = (cfg.backtest.capital_usd / 10000.0) if (cfg.backtest.capital_usd and cfg.backtest.capital_usd > 0) else 1.0
                if c == "hype" and (args.size == 0.1 or args.size == 95.0):
                    cfg.backtest.order_size_btc = round(95.0 * ratio, 2)
                elif c == "sol" and (args.size == 0.1 or args.size == 50.0):
                    cfg.backtest.order_size_btc = round(50.0 * ratio, 2)
                elif c == "eth" and (args.size == 0.1 or args.size == 3.0):
                    cfg.backtest.order_size_btc = round(3.0 * ratio, 4)
                break

        # Offline replay
        runner = L2EngineRunner(config=cfg, record_data=False, enable_audit=not args.no_audit)
        replay = L2ReplayEngine(args.replay_file, speed_multiplier=args.speed)
        print(f"Replaying {args.replay_file} at {args.speed}x speed...")
        last_eval_ms = 0
        eval_interval_ms = int(1000 / max(cfg.sample_rate_hz, 1))

        for event in replay.stream_events():
            ch = event.get("channel")
            dt = event.get("data")
            now_ms = event.get("recv_ts", 0)

            if ch == "l2Book":
                runner.book.update_from_raw(dt)
            elif ch == "trades":
                runner.trades.process_raw_trades(dt)
            elif ch == "activeAssetCtx":
                runner.book.update_asset_ctx(dt)

            if runner.book.is_valid and (now_ms - last_eval_ms >= eval_interval_ms):
                last_eval_ms = now_ms
                res = runner.alpha_model.compute(runner.book, runner.trades, now_ms)
                sub_sigs = {name: sig.score for name, sig in res.metadata.get("sub_signals", {}).items()}
                sub_sigs["CompositeAlpha"] = res.score
                runner.evaluator.record_step(
                    now_ms,
                    runner.book.mid_price,
                    runner.book.best_bid,
                    runner.book.best_ask,
                    sub_sigs,
                )
        if runner.book.is_valid:
            now_ms = runner.book.last_update_time_ms or int(time.time() * 1000)
            runner.evaluator.close_open_positions(runner.book.mid_price, now_ms, reason="SESSION_SHUTDOWN")
        if runner.auditor:
            runner.auditor.close_session()
        runner.print_summary_report()

    elif args.mode == "train-ml":
        from ml.batch_trainer import L2BatchTrainer, L2DatasetBuilder
        console = Console()
        console.print(f"\n[bold yellow]Training Adaptive L2 ML Model on Recorded Data (Horizon: {args.horizon}s)...[/bold yellow]\n")

        builder = L2DatasetBuilder(data_dir=cfg.data_dir, coin=cfg.market.coin, horizon_secs=args.horizon)
        try:
            X, y, _ = builder.build_dataset_from_files(max_files=args.max_files if args.max_files > 0 else None)
        except Exception as e:
            console.print(f"[bold red]Failed to build dataset: {e}[/bold red]")
            sys.exit(1)

        trainer = L2BatchTrainer(horizon_secs=args.horizon)
        results = trainer.train_and_evaluate(X, y)

        # Print model metrics comparison
        table_m = Table(title="Model Cross-Validation & Out-of-Sample Performance Comparison", header_style="bold cyan")
        table_m.add_column("Metric / Horizon", justify="left")
        table_m.add_column("Ridge (L2 Linear)", justify="right")
        table_m.add_column("LightGBM (Trees)", justify="right")

        r = results.get("ridge", {})
        l = results.get("lightgbm", {})

        table_m.add_row("Horizon", f"{results['horizon_secs']} seconds", f"{results['horizon_secs']} seconds")
        table_m.add_row("Train Samples", str(results["train_samples"]), str(results["train_samples"]))
        table_m.add_row("Test Samples (OOS)", str(results["test_samples"]), str(results["test_samples"]))
        table_m.add_row("In-Sample IC", f"{r.get('in_sample_ic', 0.0):+.4f}", f"{l.get('in_sample_ic', 0.0):+.4f}")
        table_m.add_row("Out-of-Sample IC", f"[bold green]{r.get('out_of_sample_ic', 0.0):+.4f}[/bold green]", f"[bold green]{l.get('out_of_sample_ic', 0.0):+.4f}[/bold green]")
        table_m.add_row("Out-of-Sample Rank IC", f"[bold green]{r.get('out_of_sample_rank_ic', 0.0):+.4f}[/bold green]", f"[bold green]{l.get('out_of_sample_rank_ic', 0.0):+.4f}[/bold green]")
        table_m.add_row("Directional Hit Rate % (All)", f"[bold green]{r.get('out_of_sample_hit_rate_pct', 0.0):.1f}%[/bold green]", f"[bold green]{l.get('out_of_sample_hit_rate_pct', 0.0):.1f}%[/bold green]")
        table_m.add_row("Active Hit Rate % (|ret|>0)", f"[bold green]{r.get('out_of_sample_active_hit_rate_pct', 0.0):.1f}%[/bold green]", f"[bold green]{l.get('out_of_sample_active_hit_rate_pct', 0.0):.1f}%[/bold green]")
        console.print(table_m)
        console.print("\n")

        # Print feature weights & importance leaderboard
        table_w = Table(title="Learned Feature Importance: Ridge vs LightGBM", header_style="bold magenta")
        table_w.add_column("Rank", justify="center")
        table_w.add_column("Feature Name", justify="left")
        table_w.add_column("Ridge Scaled Coef", justify="right")
        table_w.add_column("Ridge Natural Coef", justify="right")
        table_w.add_column("LightGBM Splits", justify="right")

        lgb_dict = dict(l.get("importance_ranked", []))

        for rank, (name, imp) in enumerate(results["feature_importance_ranked"], 1):
            w_nat = results["feature_weights"].get(name, 0.0)
            c = "green" if w_nat > 0 else "red"
            lgb_imp = lgb_dict.get(name, 0.0)
            table_w.add_row(str(rank), name, f"{imp:.4f}", f"[{c}]{w_nat:+.4f}[/{c}]", f"{int(lgb_imp)}")

        console.print(table_w)
        console.print("\n")

        trainer.save_model(args.save_model)
        console.print(f"[bold green]Successfully saved trained model to: {args.save_model}[/bold green]")

    elif args.mode == "collect":
        from engine.data_collector import ContinuousCollectorDaemon
        console = Console()
        net = cfg.hyperliquid.network_name
        hours_str = f"{args.hours} hours" if args.hours > 0 else "continuous (indefinite)"
        console.print(f"\n[bold green]Starting Continuous L2 Data Collector Daemon on {net} ({hours_str})...[/bold green]")
        console.print(f"Connecting to: [bold cyan]{cfg.hyperliquid.ws_url}[/bold cyan]")
        console.print(f"Subscribing to {cfg.market.coin} L2 Book & Trades on Hyperliquid {net}...")
        console.print(f"Data will be saved with hourly rotation to: [bold cyan]{cfg.coin_data_dir}/[/bold cyan]\n")

        daemon = ContinuousCollectorDaemon(
            ws_url=cfg.hyperliquid.ws_url,
            coin=cfg.market.coin,
            output_dir=cfg.data_dir,
        )
        try:
            asyncio.run(daemon.run(max_duration_hours=args.hours))
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Data collection stopped by user.[/bold yellow]")



if __name__ == "__main__":
    main()
