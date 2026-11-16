"""Hyperliquid L2 Microstructure Engine - High-Performance Web Dashboard Server.

Provides a decoupled, ultra-fast FastAPI + WebSocket telemetry server that streams
microstructure state, orderbook depth, alpha signals, and strategy performance at a
throttled 10 Hz rate, offloading rendering completely from the Python asyncio loop to the browser.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

logger = logging.getLogger("web_server")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
INDEX_HTML = os.path.join(STATIC_DIR, "index.html")


class StrategyToggleRequest(BaseModel):
    strategy: str
    enabled: bool


class ScalpingModeRequest(BaseModel):
    scalping: bool
    save: bool = True


class MarketOrdersToggleRequest(BaseModel):
    enabled: bool
    slippage_pct: Optional[float] = None
    save: bool = True


class OrderSizeRequest(BaseModel):
    order_size_btc: Optional[float] = None
    order_size: Optional[float] = None


class TelemetryBroadcaster:
    """Decoupled high-frequency telemetry broadcaster with rate limiting."""

    def __init__(self, target_fps: float = 10.0):
        self.clients: Set[WebSocket] = set()
        self.target_interval: float = 1.0 / max(1.0, target_fps)
        self.last_broadcast_time: float = 0.0
        self.lock = asyncio.Lock()
        self.last_payload: Optional[str] = None
        self.is_closing: bool = False

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self.lock:
            self.clients.add(ws)
        # Send immediately the last known payload if available
        if self.last_payload:
            try:
                await ws.send_text(self.last_payload)
            except Exception:
                pass

    async def disconnect(self, ws: WebSocket) -> None:
        async with self.lock:
            self.clients.discard(ws)

    async def close_all(self) -> None:
        """Closes all active client WebSocket connections cleanly."""
        self.is_closing = True
        async with self.lock:
            active = list(self.clients)
            self.clients.clear()
        for ws in active:
            try:
                await ws.close(code=1000, reason="Server shutting down")
            except Exception:
                pass

    def should_broadcast(self, now: float) -> bool:
        return (now - self.last_broadcast_time) >= self.target_interval

    async def broadcast_snapshot(self, snapshot: Dict[str, Any], force: bool = False) -> None:
        """Broadcasts telemetry snapshot if interval elapsed or force=True."""
        now = time.time()
        if not force and not self.should_broadcast(now):
            return

        self.last_broadcast_time = now
        payload_str = json.dumps(snapshot, default=str)
        self.last_payload = payload_str

        async with self.lock:
            if not self.clients:
                return
            active_clients = list(self.clients)

        dead_clients = []
        for ws in active_clients:
            try:
                await ws.send_text(payload_str)
            except Exception:
                dead_clients.append(ws)

        if dead_clients:
            async with self.lock:
                for ws in dead_clients:
                    self.clients.discard(ws)


def create_web_app(runner_ref: Any, broadcaster: TelemetryBroadcaster) -> FastAPI:
    """Creates the FastAPI application wired to the runner instance."""
    app = FastAPI(title="Hyperliquid L2 Microstructure Alpha Dashboard", docs_url=None, redoc_url=None)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def get_index():
        if os.path.exists(INDEX_HTML):
            return FileResponse(INDEX_HTML, media_type="text/html")
        return JSONResponse(
            status_code=404,
            content={"error": f"Dashboard UI file not found at {INDEX_HTML}"},
        )

    @app.get("/api/status")
    async def get_status():
        runner = runner_ref()
        if not runner:
            raise HTTPException(status_code=503, detail="Engine runner unavailable")
        
        return {
            "coin": runner.config.market.coin,
            "network": runner.config.hyperliquid.network_name,
            "is_running": runner.is_running,
            "live_mode": runner.live_orders,
            "record_data": runner.record_data,
            "sample_rate_hz": runner.config.sample_rate_hz,
            "book_updates": runner.book.update_count if hasattr(runner, "book") else 0,
            "client_connections": len(broadcaster.clients),
        }

    @app.get("/api/strategies")
    async def get_strategies():
        runner = runner_ref()
        if not runner:
            raise HTTPException(status_code=503, detail="Engine runner unavailable")

        enabled_defs = runner.config.strategies.get_enabled_strategy_defs()
        all_defs = {}
        exec_defs = {}
        scalp_defs = {}

        for name, strat in runner.config.strategies.execution_strategies.items():
            exec_type = getattr(strat, "execution_type", getattr(strat, "execution_style", "MAKER"))
            info = {
                "enabled": strat.enabled,
                "signal_key": strat.signal_key,
                "execution_style": exec_type,
                "entry_threshold": strat.entry_threshold,
                "exit_reversal_threshold": getattr(strat, "exit_reversal_threshold", None),
                "take_profit_bps": strat.take_profit_bps,
                "stop_loss_bps": strat.stop_loss_bps,
                "category": "execution",
            }
            exec_defs[name] = info
            all_defs[name] = info

        for name, strat in runner.config.strategies.scalping_strategies.items():
            exec_type = getattr(strat, "execution_type", getattr(strat, "execution_style", "MAKER"))
            info = {
                "enabled": strat.enabled,
                "signal_key": strat.signal_key,
                "execution_style": exec_type,
                "entry_threshold": strat.entry_threshold,
                "exit_reversal_threshold": getattr(strat, "exit_reversal_threshold", None),
                "take_profit_bps": strat.take_profit_bps,
                "stop_loss_bps": strat.stop_loss_bps,
                "category": "scalping",
            }
            scalp_defs[name] = info
            all_defs[name] = info

        return {
            "strategies": all_defs,
            "execution_strategies": exec_defs,
            "scalping_strategies": scalp_defs,
            "is_scalping_mode": runner.config.strategies.is_scalping_mode_active,
            "program_name": getattr(runner.config.strategies, "program_name", "unified"),
            "active_live_strategy": getattr(runner.config.strategies.live_execution, "active_strategy", "Hedged_Convexity"),
        }

    @app.post("/api/strategies/mode/scalping")
    async def set_scalping_mode(req: ScalpingModeRequest):
        runner = runner_ref()
        if not runner:
            raise HTTPException(status_code=503, detail="Engine runner unavailable")

        runner.config.strategies.set_scalping_mode(enabled=req.scalping, save=req.save, enable_queue_replenishment=False)

        # Synchronize evaluator strategy definitions and close positions of newly disabled strategies
        if hasattr(runner, "evaluator") and runner.evaluator:
            evaluator = runner.evaluator
            if hasattr(evaluator, "strategies"):
                mid_px = runner.book.mid_price if hasattr(runner, "book") else 0.0
                now_ms = int(time.time() * 1000)
                for s_name, s_state in evaluator.strategies.items():
                    strat_cfg = runner.config.strategies.get_strategy(s_name)
                    if strat_cfg and not strat_cfg.enabled and s_state.is_in_position:
                        evaluator.close_open_positions(
                            mid_px,
                            now_ms,
                            reason=f"STRATEGY_DISABLED:{s_name}",
                        )

            # Rebuild strategy_defs and strategy_names
            if hasattr(evaluator, "strategy_defs"):
                evaluator.strategy_defs.clear()
            if hasattr(evaluator, "strategy_names"):
                evaluator.strategy_names.clear()

            for s_name, strat_cfg in runner.config.strategies.all_strategies.items():
                if strat_cfg.enabled:
                    exec_type = getattr(strat_cfg, "execution_type", getattr(strat_cfg, "execution_style", "MAKER"))
                    if hasattr(evaluator, "strategy_defs"):
                        evaluator.strategy_defs[s_name] = (strat_cfg.signal_key, exec_type)
                    if hasattr(evaluator, "strategy_names"):
                        evaluator.strategy_names.append(s_name)
                    if hasattr(evaluator, "strategies") and s_name not in evaluator.strategies:
                        from engine.backtester import StrategyState
                        init_cash = getattr(getattr(evaluator, "bt_cfg", None), "initial_cash_usd", 10000.0)
                        category = "scalping" if getattr(strat_cfg, "is_scalping", False) else "execution"
                        evaluator.strategies[s_name] = StrategyState(
                            name=s_name,
                            execution_type=exec_type,
                            signal_key=strat_cfg.signal_key,
                            cash_usd=init_cash,
                            category=category,
                        )

        # Cancel resting live order if active order's strategy is now disabled
        if hasattr(runner, "live_executor") and runner.live_executor:
            executor = runner.live_executor
            if executor.active_order:
                act_strat = executor.active_order.get("strategy_name")
                if act_strat and not runner.config.strategies.is_strategy_enabled(act_strat):
                    executor.cancel_order(executor.active_order["oid"])

        num_sc = len(runner.config.strategies.scalping_strategies)
        num_ex = len(runner.config.strategies.execution_strategies)
        mode_desc = f"Scalping Mode ({num_sc} scalping ON, {num_ex} core OFF)" if req.scalping else f"Core Mode ({num_ex} core ON, {num_sc} scalping OFF)"
        logger.info(f"Switched strategy preset to: {mode_desc} (Config saved: {req.save})")

        return {
            "status": "ok",
            "scalping_mode": req.scalping,
            "is_scalping_mode": runner.config.strategies.is_scalping_mode_active,
            "program_name": getattr(runner.config.strategies, "program_name", "unified"),
            "active_live_strategy": getattr(runner.config.strategies.live_execution, "active_strategy", "Hedged_Convexity"),
            "enabled_count": sum(1 for s in runner.config.strategies.all_strategies.values() if s.enabled),
            "disabled_count": sum(1 for s in runner.config.strategies.all_strategies.values() if not s.enabled),
            "message": f"Successfully activated {mode_desc}",
        }

    @app.post("/api/strategy/toggle")
    async def toggle_strategy(req: StrategyToggleRequest):
        runner = runner_ref()
        if not runner:
            raise HTTPException(status_code=503, detail="Engine runner unavailable")

        strat_name = req.strategy
        strat_cfg = runner.config.strategies.get_strategy(strat_name)
        if not strat_cfg:
            raise HTTPException(status_code=404, detail=f"Strategy '{strat_name}' not found")

        strat_cfg.enabled = req.enabled

        # Maintain alignment of active live execution strategy with enabled strategies
        if req.enabled:
            current_live = getattr(runner.config.strategies.live_execution, "active_strategy", None)
            curr_obj = runner.config.strategies.get_strategy(current_live) if current_live else None
            if not curr_obj or not curr_obj.enabled:
                runner.config.strategies.live_execution.active_strategy = strat_name
        elif not req.enabled and getattr(runner.config.strategies.live_execution, "active_strategy", None) == strat_name:
            runner.config.strategies.live_execution.active_strategy = runner.config.strategies.get_effective_live_strategy()

        # Persist change to strategies.json so it survives restart / reload
        try:
            runner.config.strategies.save()
        except Exception as e:
            logger.warning(f"Failed to auto-save strategies.json on toggle: {e}")

        # Update evaluator strategy definition
        if hasattr(runner, "evaluator"):
            evaluator = runner.evaluator
            exec_type = getattr(strat_cfg, "execution_type", getattr(strat_cfg, "execution_style", "MAKER"))
            if req.enabled:
                if hasattr(evaluator, "strategy_defs"):
                    evaluator.strategy_defs[strat_name] = (strat_cfg.signal_key, exec_type)
                if hasattr(evaluator, "strategy_names") and strat_name not in evaluator.strategy_names:
                    evaluator.strategy_names.append(strat_name)
                if hasattr(evaluator, "strategies"):
                    if strat_name not in evaluator.strategies:
                        from engine.backtester import StrategyState
                        init_cash = getattr(getattr(evaluator, "bt_cfg", None), "initial_cash_usd", 10000.0)
                        category = "scalping" if getattr(strat_cfg, "is_scalping", False) else "execution"
                        evaluator.strategies[strat_name] = StrategyState(
                            name=strat_name,
                            execution_type=exec_type,
                            signal_key=strat_cfg.signal_key,
                            cash_usd=init_cash,
                            category=category,
                        )
            else:
                # If disabling, close any open position first
                if hasattr(evaluator, "strategies") and strat_name in evaluator.strategies:
                    if evaluator.strategies[strat_name].is_in_position:
                        evaluator.close_open_positions(
                            runner.book.mid_price,
                            int(time.time() * 1000),
                            reason=f"STRATEGY_DISABLED:{strat_name}",
                        )
                if hasattr(evaluator, "strategy_defs"):
                    evaluator.strategy_defs.pop(strat_name, None)
                if hasattr(evaluator, "strategy_names") and strat_name in evaluator.strategy_names:
                    evaluator.strategy_names.remove(strat_name)

        # Cancel any resting live order for this strategy if disabled
        if hasattr(runner, "live_executor") and runner.live_executor:
            executor = runner.live_executor
            if not req.enabled:
                if executor.active_order and executor.active_order.get("strategy_name") == strat_name:
                    executor.cancel_order(executor.active_order["oid"])

        category = runner.config.strategies.get_strategy_category(strat_name)
        action_verb = "ENABLED" if req.enabled else "DISABLED"
        logger.info(f"Strategy '{strat_name}' ({category}) {action_verb} (Config saved to {runner.config.strategies.filepath})")

        return {
            "status": "ok",
            "strategy": strat_name,
            "enabled": req.enabled,
            "category": category,
            "message": f"Strategy {strat_name} successfully {action_verb.lower()}",
        }

    @app.post("/api/emergency/flatten")
    async def emergency_flatten():
        runner = runner_ref()
        if not runner:
            raise HTTPException(status_code=503, detail="Engine runner unavailable")

        now_ms = int(time.time() * 1000)
        mid_px = runner.book.mid_price if hasattr(runner, "book") else 0.0

        # Close all paper positions
        closed_paper = 0
        if hasattr(runner, "evaluator"):
            closed_paper = runner.evaluator.close_open_positions(
                mid_px, now_ms, reason="EMERGENCY_FLATTEN_USER"
            )

        # Cancel live orders and market close live position if live executor is active
        cancelled_live = 0
        closed_live = False
        if hasattr(runner, "live_executor") and runner.live_executor:
            cancelled_live = runner.live_executor.cancel_all_orders()
            if abs(getattr(runner.live_executor, "cached_position", 0.0)) > 1e-6:
                res = runner.live_executor.close_position()
                closed_live = bool(res and res.get("status") == "ok")

        return {
            "status": "ok",
            "message": "Emergency flatten initiated",
            "paper_positions_closed": closed_paper,
            "live_orders_cancelled": cancelled_live,
            "live_position_closed": closed_live,
            "price": mid_px,
        }

    @app.post("/api/config/market_orders")
    @app.post("/api/market_orders/toggle")
    async def toggle_market_orders(req: MarketOrdersToggleRequest):
        runner = runner_ref()
        if not runner:
            raise HTTPException(status_code=503, detail="Engine runner unavailable")

        force_mkt = bool(req.enabled)
        slip = float(req.slippage_pct) if req.slippage_pct is not None else None

        # Update strategies configuration
        if hasattr(runner, "config") and hasattr(runner.config, "strategies"):
            runner.config.strategies.set_market_orders(enabled=force_mkt, slippage_pct=slip, save=req.save)
        if hasattr(runner, "config") and hasattr(runner.config, "backtest"):
            runner.config.backtest.force_market_orders = force_mkt
            if slip is not None:
                runner.config.backtest.market_slippage_pct = slip

        # Propagate immediately to live order executor
        if hasattr(runner, "live_executor") and runner.live_executor:
            runner.live_executor.force_market_orders = force_mkt
            if slip is not None:
                runner.live_executor.market_slippage_pct = slip

        # Propagate to evaluator
        if hasattr(runner, "evaluator") and runner.evaluator and hasattr(runner.evaluator, "bt_cfg"):
            runner.evaluator.bt_cfg.force_market_orders = force_mkt
            if slip is not None:
                runner.evaluator.bt_cfg.market_slippage_pct = slip

        action_verb = "ENABLED (Taker IOC)" if force_mkt else "DISABLED (Passive Maker / Smart Taker)"
        cur_slip = getattr(getattr(runner.config.strategies, "live_execution", None), "market_slippage_pct", 0.0005)
        logger.info(f"Forced Market Orders {action_verb} (Slippage: {cur_slip*100:.2f}%, Saved: {req.save})")

        return {
            "status": "ok",
            "force_market_orders": force_mkt,
            "market_slippage_pct": cur_slip,
            "message": f"Forced market orders {action_verb}",
        }

    @app.post("/api/config/order_size")
    async def update_order_size(req: OrderSizeRequest):
        runner = runner_ref()
        if not runner:
            raise HTTPException(status_code=503, detail="Engine runner unavailable")

        raw_size = req.order_size if req.order_size is not None else req.order_size_btc
        if raw_size is None:
            raise HTTPException(status_code=400, detail="Missing order_size or order_size_btc")

        new_size = max(0.0001, float(raw_size))
        if hasattr(runner, "live_executor") and runner.live_executor:
            runner.live_executor.default_order_size_btc = new_size

        return {"status": "ok", "order_size": new_size, "order_size_btc": new_size}

    @app.websocket("/ws/telemetry")
    async def websocket_telemetry_endpoint(ws: WebSocket):
        await broadcaster.connect(ws)
        try:
            while not broadcaster.is_closing:
                try:
                    data = await asyncio.wait_for(ws.receive_text(), timeout=0.5)
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await ws.send_text(json.dumps({"type": "pong", "time": time.time()}))
                except asyncio.TimeoutError:
                    if broadcaster.is_closing:
                        break
                except Exception:
                    break
        except (WebSocketDisconnect, asyncio.CancelledError, Exception):
            pass
        finally:
            await broadcaster.disconnect(ws)

    return app


class NonInterferingServer(uvicorn.Server):
    """Custom Uvicorn server that avoids intercepting process-level signals."""

    import contextlib

    @contextlib.contextmanager
    def capture_signals(self):
        yield


class DashboardWebServer:
    """Wrapper that manages Uvicorn lifecycle inside the runner's asyncio loop."""

    def __init__(self, runner: Any, host: str = "127.0.0.1", port: int = 8000, target_fps: float = 10.0):
        self.runner = runner
        self.host = host
        self.port = port
        self.broadcaster = TelemetryBroadcaster(target_fps=target_fps)
        self.app = create_web_app(lambda: self.runner, self.broadcaster)
        self.server: Optional[uvicorn.Server] = None
        self.server_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Starts Uvicorn server in a background asyncio task."""
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
            loop="asyncio",
            lifespan="off",
            timeout_graceful_shutdown=0,
        )
        self.server = NonInterferingServer(config)
        self.server_task = asyncio.create_task(self.server.serve())

    async def stop(self) -> None:
        """Gracefully and promptly shuts down Uvicorn server."""
        if self.server:
            self.server.should_exit = True
            self.server.force_exit = True
        await self.broadcaster.close_all()
        if self.server_task and not self.server_task.done():
            self.server_task.cancel()
            try:
                await asyncio.wait_for(self.server_task, timeout=0.5)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass

    async def emit_telemetry(
        self,
        book: Any,
        trades: Any,
        display_signals: Dict[str, Any],
        evaluator: Any,
        network: str = "Testnet",
    ) -> None:
        """Constructs compact snapshot payload and broadcasts via WebSocket."""
        now = time.time()
        if not self.broadcaster.should_broadcast(now):
            return

        now_ms = int(now * 1000)
        coin = str(
            getattr(book, "coin", None)
            or getattr(trades, "coin", None)
            or (getattr(self.runner, "config", None) and getattr(self.runner.config.market, "coin", None))
            or "BTC"
        ).upper()

        # 1. Market & Depth Snapshot (Top 10 levels)
        bids_data = [[float(l.px), float(l.sz), int(l.n)] for l in getattr(book, "bids", [])[:10]]
        asks_data = [[float(l.px), float(l.sz), int(l.n)] for l in getattr(book, "asks", [])[:10]]

        vpin_val = trades.calculate_vpin(20) if trades else None

        market_data = {
            "coin": coin,
            "network": network,
            "mid_price": round(float(getattr(book, "mid_price", 0.0)), 2),
            "best_bid": round(float(getattr(book, "best_bid", 0.0)), 2),
            "best_ask": round(float(getattr(book, "best_ask", 0.0)), 2),
            "spread": round(float(getattr(book, "spread", 0.0)), 2),
            "spread_bps": round(float(getattr(book, "spread_bps", 0.0)), 2),
            "oracle_price": round(float(getattr(book, "oracle_price", 0.0)), 2),
            "basis_bps": round(float(getattr(book, "basis_bps", 0.0)), 2),
            "funding_rate": float(getattr(book, "funding_rate", 0.0)),
            "open_interest": round(float(getattr(book, "open_interest", 0.0)), 1),
            "cvd": round(float(getattr(trades, "total_cvd", 0.0)), 4),
            "vpin": round(float(vpin_val), 3) if vpin_val is not None else None,
            "updates": getattr(book, "update_count", 0),
            "is_xyz_stock": bool(getattr(getattr(self.runner, "config", None), "market", None) and getattr(self.runner.config.market, "is_xyz_stock", False)),
            "taker_fee_bps": float(getattr(getattr(self.runner, "config", None), "market", None) and getattr(self.runner.config.market, "taker_fee_bps", 4.5) or 4.5),
            "maker_fee_bps": float(getattr(getattr(self.runner, "config", None), "market", None) and getattr(self.runner.config.market, "maker_fee_bps", 1.5) or 1.5),
            "is_warming_up": bool(getattr(self.runner, "is_warming_up", False)),
            "warmup_remaining_secs": round(float(getattr(self.runner, "warmup_remaining_secs", 0.0)), 1),
            "force_market_orders": bool(getattr(getattr(getattr(self.runner, "config", None), "strategies", None), "live_execution", None) and getattr(self.runner.config.strategies.live_execution, "force_market_orders", False)),
            "market_slippage_pct": float(getattr(getattr(getattr(self.runner, "config", None), "strategies", None), "live_execution", None) and getattr(self.runner.config.strategies.live_execution, "market_slippage_pct", 0.0005) or 0.0005),
        }

        # 2. Signals
        signals_data = {}
        for k, v in display_signals.items():
            if hasattr(v, "score"):
                signals_data[k] = round(float(v.score), 4)
            elif isinstance(v, (int, float)):
                signals_data[k] = round(float(v), 4)

        # 3. Strategy Telemetry (Encompasses ALL configured strategies: Core Execution + Scalping)
        strategies_data = {}
        total_realized_pnl = 0.0
        total_unrealized_pnl = 0.0
        total_trades_count = 0

        is_live = bool(getattr(self.runner, "live_orders", False))
        mid_px = float(getattr(book, "mid_price", 0.0))
        runner_obj = self.runner
        all_configured = runner_obj.config.strategies.all_strategies if (runner_obj and hasattr(runner_obj, "config") and hasattr(runner_obj.config, "strategies")) else {}

        # Fallback to evaluator.strategies if runner.config is somehow not available
        if not all_configured and evaluator and hasattr(evaluator, "strategies"):
            all_configured = {name: None for name in evaluator.strategies.keys()}

        # Group live trades by strategy when in live mode
        live_strat_trades: Dict[str, List[Dict[str, Any]]] = {}
        if is_live:
            if getattr(self.runner, "auditor", None) and hasattr(self.runner.auditor, "trades") and self.runner.auditor.trades:
                for t in self.runner.auditor.trades:
                    sn = getattr(t, "strategy_name", "")
                    if sn not in live_strat_trades:
                        live_strat_trades[sn] = []
                    live_strat_trades[sn].append({
                        "net_pnl_usd": float(getattr(t, "net_pnl_usd", 0.0)),
                        "gross_pnl_usd": float(getattr(t, "gross_pnl_usd", 0.0)),
                        "fees_paid_usd": float(getattr(t, "total_fees_usd", 0.0)),
                    })
            elif hasattr(self.runner, "live_executor") and self.runner.live_executor and getattr(self.runner.live_executor, "completed_trades", None):
                for t in self.runner.live_executor.completed_trades:
                    sn = t.get("strategy", "")
                    if sn not in live_strat_trades:
                        live_strat_trades[sn] = []
                    live_strat_trades[sn].append({
                        "net_pnl_usd": float(t.get("net_pnl_usd", 0.0)),
                        "gross_pnl_usd": float(t.get("gross_pnl_usd", 0.0)),
                        "fees_paid_usd": float(t.get("total_fees_usd", 0.0)),
                    })

        for s_name, s_cfg in all_configured.items():
            state = evaluator.strategies.get(s_name) if (evaluator and hasattr(evaluator, "strategies")) else None

            if is_live:
                strat_trades = live_strat_trades.get(s_name, [])
                n_trades = len(strat_trades)
                wins = sum(1 for tr in strat_trades if tr["net_pnl_usd"] > 0)
                win_rate = (wins / n_trades * 100.0) if n_trades > 0 else 0.0
                realized_pnl = sum(tr["net_pnl_usd"] for tr in strat_trades)
                fees_paid = sum(tr["fees_paid_usd"] for tr in strat_trades)
                gross_wins = sum(tr["gross_pnl_usd"] for tr in strat_trades if tr["gross_pnl_usd"] > 0)
                gross_losses = sum(abs(tr["gross_pnl_usd"]) for tr in strat_trades if tr["gross_pnl_usd"] < 0)
                profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else (99.0 if gross_wins > 0 else 0.0)

                cum = 0.0
                peak = 0.0
                max_dd = 0.0
                for tr in strat_trades:
                    cum += tr["net_pnl_usd"]
                    if cum > peak:
                        peak = cum
                    dd = peak - cum
                    if dd > max_dd:
                        max_dd = dd

                in_pos = False
                pos_info = None
                lx = getattr(self.runner, "live_executor", None)
                if lx and abs(getattr(lx, "cached_position", 0.0)) > 1e-6:
                    act_strat = getattr(lx, "position_strategy", None) or getattr(lx, "strategy_name", "")
                    if act_strat == s_name:
                        in_pos = True
                        live_pos = getattr(lx, "cached_position", 0.0)
                        live_entry = getattr(lx, "entry_price", mid_px) or mid_px
                        live_unrealized = live_pos * (mid_px - live_entry) if mid_px > 0 else 0.0
                        live_bps = (live_unrealized / (abs(live_pos) * live_entry)) * 10_000.0 if (abs(live_pos) * live_entry > 0) else 0.0
                        hold_secs = (now_ms - getattr(lx, "entry_time_ms", now_ms)) / 1000.0 if getattr(lx, "entry_time_ms", 0) > 0 else 0.0
                        pos_info = {
                            "side": "LONG" if live_pos > 0 else "SHORT",
                            "size_btc": round(abs(live_pos), 4),
                            "entry_price": round(live_entry, 2),
                            "unrealized_usd": round(live_unrealized, 3),
                            "unrealized_bps": round(live_bps, 1),
                            "stop_price": 0.0,
                            "trailing_active": getattr(lx, "trailing_stop_active", False),
                            "hold_secs": round(hold_secs, 1),
                        }
                        total_unrealized_pnl += live_unrealized

                total_realized_pnl += realized_pnl
                total_trades_count += n_trades
            else:
                perf = evaluator.get_strategy_performance(s_name, mid_px) if (evaluator and hasattr(evaluator, "get_strategy_performance") and state) else {}

                in_pos = bool(state.is_in_position) if state else False
                pos_btc = float(state.position_btc) if state else 0.0
                entry_px = float(state.entry_price) if state else 0.0

                pos_info = None
                if in_pos:
                    unrealized_usd = pos_btc * (mid_px - entry_px)
                    unrealized_bps = (unrealized_usd / (abs(pos_btc) * entry_px)) * 10_000.0 if (abs(pos_btc) * entry_px) > 0 else 0.0
                    hold_secs = (now_ms - state.entry_time_ms) / 1000.0 if state else 0.0
                    pos_info = {
                        "side": "LONG" if pos_btc > 0 else "SHORT",
                        "size_btc": round(abs(pos_btc), 4),
                        "entry_price": round(entry_px, 2),
                        "unrealized_usd": round(unrealized_usd, 3),
                        "unrealized_bps": round(unrealized_bps, 1),
                        "stop_price": round(float(state.stop_price), 2),
                        "trailing_active": getattr(state, "trailing_stop_active", False),
                        "hold_secs": round(hold_secs, 1),
                    }
                    total_unrealized_pnl += unrealized_usd

                realized_pnl = float(perf.get("realized_pnl_usd", 0.0))
                total_realized_pnl += realized_pnl
                total_trades_count += int(perf.get("trades", 0))
                n_trades = perf.get("trades", 0)
                win_rate = float(perf.get("win_rate_pct", 0.0))
                profit_factor = float(perf.get("profit_factor", 0.0))
                fees_paid = float(perf.get("fees_paid_usd", 0.0))
                max_dd = float(perf.get("max_drawdown_usd", 0.0))

            category = "scalping" if (s_cfg and getattr(s_cfg, "is_scalping", False)) else "execution"
            if state and hasattr(state, "category"):
                category = state.category

            is_enabled = bool(s_cfg.enabled) if s_cfg else (s_name in getattr(evaluator, "strategy_names", []))

            strategies_data[s_name] = {
                "enabled": is_enabled,
                "category": category,
                "in_position": in_pos,
                "position": pos_info,
                "trades": n_trades,
                "win_rate": round(win_rate, 1),
                "profit_factor": round(profit_factor, 2),
                "realized_pnl": round(realized_pnl, 2),
                "fees_paid": round(fees_paid, 3),
                "drawdown": round(max_dd, 2),
                "signal_key": getattr(s_cfg, "signal_key", "CompositeAlpha") if s_cfg else getattr(state, "signal_key", "CompositeAlpha"),
                "entry_threshold": getattr(s_cfg, "entry_threshold", 0.8) if s_cfg else 0.8,
                "execution_style": getattr(s_cfg, "execution_type", "MAKER") if s_cfg else getattr(state, "execution_type", "MAKER"),
            }

        # 4. Recent Closed Trades (last 15)
        is_live = bool(getattr(self.runner, "live_orders", False))
        recent_trades = []
        if is_live and getattr(self.runner, "auditor", None) and hasattr(self.runner.auditor, "trades") and self.runner.auditor.trades:
            for t in reversed(self.runner.auditor.trades[-15:]):
                recent_trades.append({
                    "strategy": t.strategy_name,
                    "side": t.side,
                    "size_btc": round(float(t.size_btc), 4),
                    "size": round(float(t.size_btc), 4),
                    "coin": getattr(t, "coin", coin),
                    "entry_price": round(float(t.entry_price), 2),
                    "exit_price": round(float(t.exit_price), 2),
                    "net_pnl": round(float(t.net_pnl_usd), 2),
                    "return_bps": round(float(t.return_bps), 1),
                    "exit_reason": t.exit_reason,
                    "duration_s": round(t.holding_time_secs, 1),
                    "exit_time": t.exit_time_iso.split("T")[-1] if "T" in t.exit_time_iso else t.exit_time_iso,
                    "is_live": True,
                })
        elif is_live and hasattr(self.runner, "live_executor") and self.runner.live_executor and getattr(self.runner.live_executor, "completed_trades", None):
            for t in reversed(self.runner.live_executor.completed_trades[-15:]):
                dur_s = max(0.0, (t["exit_time_ms"] - t["entry_time_ms"]) / 1000.0)
                recent_trades.append({
                    "strategy": t["strategy"],
                    "side": t["side"],
                    "size_btc": round(float(t["size_btc"]), 4),
                    "size": round(float(t["size_btc"]), 4),
                    "coin": coin,
                    "entry_price": round(float(t["entry_price"]), 2),
                    "exit_price": round(float(t["exit_price"]), 2),
                    "net_pnl": round(float(t["net_pnl_usd"]), 2),
                    "return_bps": round(float(t["return_bps"]), 1),
                    "exit_reason": t["exit_reason"],
                    "duration_s": round(dur_s, 1),
                    "exit_time": time.strftime("%H:%M:%S", time.localtime(t["exit_time_ms"] / 1000.0)),
                    "is_live": True,
                })
        elif not is_live and evaluator and hasattr(evaluator, "strategies"):
            all_closed = []
            for s_name, state in evaluator.strategies.items():
                for t in getattr(state, "trades", []):
                    all_closed.append(t)
            all_closed.sort(key=lambda t: t.exit_time_ms, reverse=True)
            for t in all_closed[:15]:
                recent_trades.append({
                    "strategy": t.strategy_name,
                    "side": t.side,
                    "size_btc": round(float(t.size_btc), 4),
                    "size": round(float(t.size_btc), 4),
                    "coin": coin,
                    "entry_price": round(float(t.entry_price), 2),
                    "exit_price": round(float(t.exit_price), 2),
                    "net_pnl": round(float(t.net_pnl_usd), 2),
                    "return_bps": round(float(t.return_bps), 1),
                    "exit_reason": t.exit_reason,
                    "duration_s": round((t.exit_time_ms - t.entry_time_ms) / 1000.0, 1),
                    "exit_time": time.strftime("%H:%M:%S", time.localtime(t.exit_time_ms / 1000.0)),
                    "is_live": False,
                })

        # 5. Live Exchange Position (if running in live orders mode)
        live_position_data = None
        if hasattr(self.runner, "live_executor") and self.runner.live_executor:
            lx = self.runner.live_executor
            live_pos = getattr(lx, "cached_position", 0.0)
            in_pos = abs(live_pos) > 1e-6
            live_entry = getattr(lx, "entry_price", mid_px) or mid_px
            live_unrealized = live_pos * (mid_px - live_entry) if (mid_px > 0 and in_pos) else 0.0
            live_bps = (live_unrealized / (abs(live_pos) * live_entry)) * 10_000.0 if (abs(live_pos) * live_entry > 0 and in_pos) else 0.0
            live_position_data = {
                "coin": getattr(lx, "coin", coin),
                "in_position": in_pos,
                "side": ("LONG" if live_pos > 0 else "SHORT") if in_pos else "FLAT",
                "size": round(abs(live_pos), 4),
                "entry_price": round(live_entry, 2),
                "unrealized_usd": round(live_unrealized, 2),
                "unrealized_bps": round(live_bps, 1),
                "active_strategy": getattr(lx, "position_strategy", None) or getattr(lx, "strategy_name", "LiveExecution"),
                "account_value": round(getattr(lx, "account_value", 0.0), 2),
                "initial_account_value": round(getattr(lx, "initial_account_value", 0.0), 2),
                "session_realized_pnl": round(total_realized_pnl, 2),
                "available_margin": round(getattr(lx, "available_margin", 0.0), 2),
            }

            # Sync active strategy live position in strategies_data
            act_strat = live_position_data.get("active_strategy")
            if act_strat and act_strat in strategies_data and in_pos:
                strategies_data[act_strat]["in_position"] = True
                strategies_data[act_strat]["position"] = {
                    "side": live_position_data["side"],
                    "size_btc": live_position_data["size"],
                    "entry_price": live_position_data["entry_price"],
                    "unrealized_usd": live_position_data["unrealized_usd"],
                    "unrealized_bps": live_position_data["unrealized_bps"],
                    "stop_price": 0.0,
                    "trailing_active": getattr(lx, "trailing_stop_active", False),
                    "hold_secs": round((now_ms - getattr(lx, "entry_time_ms", now_ms)) / 1000.0, 1) if getattr(lx, "entry_time_ms", 0) > 0 else 0.0,
                }

        real_acct_val = round(getattr(self.runner.live_executor, "account_value", 0.0), 2) if (hasattr(self.runner, "live_executor") and self.runner.live_executor) else 0.0
        real_acct_delta = round(getattr(self.runner.live_executor, "account_equity_delta", 0.0), 2) if (hasattr(self.runner, "live_executor") and self.runner.live_executor) else 0.0

        portfolio_payload = {
            "total_realized_pnl": round(total_realized_pnl, 2),
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "total_pnl": round(total_realized_pnl + total_unrealized_pnl, 2),
            "total_trades": total_trades_count,
            "real_account_value": real_acct_val,
            "real_account_pnl": real_acct_delta,
            "is_live": is_live,
        }

        snapshot = {
            "timestamp": now_ms,
            "market": market_data,
            "book": {
                "bids": bids_data,
                "asks": asks_data,
            },
            "signals": signals_data,
            "strategies": strategies_data,
            "portfolio": portfolio_payload,
            "recent_trades": recent_trades,
            "live_position": live_position_data,
            "is_live_orders": getattr(self.runner, "live_orders", False),
            "is_scalping_mode": (
                getattr(self.runner.config.strategies, "is_scalping_mode_active", False)
                if hasattr(self.runner, "config") and hasattr(self.runner.config, "strategies")
                else False
            ),
            "force_market_orders": (
                getattr(self.runner.config.strategies.live_execution, "force_market_orders", False)
                if hasattr(self.runner, "config") and hasattr(self.runner.config, "strategies") and hasattr(self.runner.config.strategies, "live_execution")
                else False
            ),
            "market_slippage_pct": (
                getattr(self.runner.config.strategies.live_execution, "market_slippage_pct", 0.0005)
                if hasattr(self.runner, "config") and hasattr(self.runner.config, "strategies") and hasattr(self.runner.config.strategies, "live_execution")
                else 0.0005
            ),
            "program_name": (
                getattr(self.runner.config.strategies, "program_name", "unified")
                if hasattr(self.runner, "config") and hasattr(self.runner.config, "strategies")
                else "unified"
            ),
        }

        await self.broadcaster.broadcast_snapshot(snapshot)
