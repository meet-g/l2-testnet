"""Hyperliquid L2 Microstructure Alpha Engine — Core Execution Strategy Program.

Dedicated program executing the 4 primary microstructure execution strategies:
1. Hedged_Convexity (Multi-tier convex quoting with toxic-flow maker hedging)
2. Convexity_Cascade (Multi-level book convexity with hole cascades)
3. Momentum_Expansion (High-conviction taker momentum capture)
4. Queue_Replenishment (L1/L3 queue replenishment delta & cancellation asymmetry)
"""

import argparse
import asyncio
import os
import sys

# Configure OpenMP & BLAS threading runtimes to eliminate CPU spin-waiting loops
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

from typing import Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table

from config import (
    AppConfig,
    CoreStrategiesConfig,
    CORE_EXECUTION_STRATEGIES,
)
from main import (
    L2EngineRunner,
    check_hyperliquid_account,
    transfer_spot_to_perp,
    test_hyperliquid_connection,
    handle_audit_mode,
)


def print_core_strategies_status(cfg: Optional[AppConfig] = None, console: Optional[Console] = None) -> None:
    """Displays active and configured core execution strategies and alpha signals."""
    cfg = cfg or AppConfig.for_core()
    console = console or Console()
    strat_cfg = cfg.strategies

    console.print()
    console.print("[bold cyan]================================================================================[/bold cyan]")
    console.print(f"[bold cyan]        CORE EXECUTION STRATEGY CONFIGURATION ({strat_cfg.filepath})        [/bold cyan]")
    console.print("[bold cyan]================================================================================[/bold cyan]\n")

    active_live = strat_cfg.get_effective_live_strategy()
    active_strat = strat_cfg.get_strategy(active_live)
    live_status = "[bold green]ENABLED[/bold green]" if (active_strat and active_strat.enabled) else "[bold red]DISABLED[/bold red]"
    coin = cfg.market.coin.upper()
    console.print(f"Active Live Strategy:    [bold yellow]{active_live}[/bold yellow] ({live_status}) - [dim cyan]Primary Execution Strategy[/dim cyan]")
    console.print(f"Default Live Order Size: [white]{strat_cfg.live_execution.order_size_btc} {coin}[/white]")
    console.print(f"Max Position Guardrail:  [white]{strat_cfg.live_execution.max_position_btc} {coin}[/white]")
    mkt_forced = getattr(strat_cfg.live_execution, "force_market_orders", False)
    mkt_slip = getattr(strat_cfg.live_execution, "market_slippage_pct", 0.0005)
    if mkt_forced:
        console.print(f"Forced Market Orders:    [bold red]ENABLED (Taker IOC)[/bold red] [dim]|[/dim] Slippage Tolerance: [bold yellow]{mkt_slip*100:.2f}%[/bold yellow] ({mkt_slip*10000:.1f} bps)\n")
    else:
        console.print(f"Forced Market Orders:    [dim green]DISABLED (Passive Maker / Smart Hedged Hybrid)[/dim green]\n")

    table_exec = Table(title="Primary Execution Strategies (4 Core Microstructure Strategies)", header_style="bold cyan")
    table_exec.add_column("Strategy Name", justify="left", style="bold", no_wrap=True)
    table_exec.add_column("Status", justify="center")
    table_exec.add_column("Type", justify="center", style="dim")
    table_exec.add_column("Underlying Signal", justify="left")
    table_exec.add_column("Threshold", justify="right")
    table_exec.add_column(f"Size ({coin})", justify="right")
    table_exec.add_column("Description", justify="left", style="dim")

    for s_name in CORE_EXECUTION_STRATEGIES:
        s = strat_cfg.get_strategy(s_name)
        if not s:
            continue
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

    table_alpha = Table(title="Core Alpha Signals (Predictive Factors)", header_style="bold magenta")
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
    console.print("\n")


def build_parser() -> argparse.ArgumentParser:
    """Builds argument parser for the Core Execution Strategy program."""
    parser = argparse.ArgumentParser(
        description="Hyperliquid L2 Microstructure Alpha Engine — Core Execution System"
    )
    parser.add_argument(
        "mode",
        nargs="?",
        choices=[
            "live", "test-connection", "testnet", "check-account",
            "transfer-to-perp", "place-order", "cancel-orders",
            "benchmark", "replay", "train-ml", "collect", "strategies", "audit"
        ],
        default="strategies",
        help="Execution mode (default: strategies)",
    )
    parser.add_argument(
        "--strategies-config",
        type=str,
        default="strategies_core.json",
        help="Path to core strategies configuration JSON (default: strategies_core.json)",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default="",
        help=f"Active core strategy override. Options: {', '.join(CORE_EXECUTION_STRATEGIES)}",
    )
    parser.add_argument("--session", type=str, default="", help="Session ID or 'latest' to inspect in audit mode")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of trades to display in audit tables (default: 50)")
    parser.add_argument("--amount", type=float, default=0.0, help="Amount of USDC to transfer between Spot and Perp (default: max)")
    parser.add_argument("--coin", type=str, default="BTC", help="Target coin symbol (default: BTC)")
    parser.add_argument("--account", type=str, default="", help="Hyperliquid master wallet address (0x...)")
    parser.add_argument("--secret-key", type=str, default="", help="Hyperliquid API Agent or wallet private key")
    parser.add_argument("--live-orders", action="store_true", help="Execute real live orders on Hyperliquid Testnet / Mainnet")
    parser.add_argument("--order-size", type=float, default=0.0005, help="Order size in BTC for live execution (default: 0.0005 BTC)")
    parser.add_argument("--side", type=str, choices=["BUY", "SELL"], default="BUY", help="Order side for place-order mode")
    parser.add_argument("--price", type=float, default=0.0, help="Limit price for place-order mode")
    parser.add_argument("--testnet", dest="use_testnet", action="store_true", default=None, help="Connect to Hyperliquid Testnet")
    parser.add_argument("--mainnet", dest="use_testnet", action="store_false", default=None, help="Connect to Hyperliquid Mainnet")
    parser.add_argument("--duration", type=int, default=0, help="Run duration in seconds (0 = infinite)")
    parser.add_argument("--hours", type=float, default=0.0, help="Max collection duration in hours (0 = continuous)")
    parser.add_argument("--horizon", type=float, default=5.0, help="Forward prediction horizon in seconds for ML training")
    parser.add_argument(
        "--ui",
        type=str,
        choices=["cli", "browser", "web", "none", "no-ui"],
        default=None,
        help="Interface display mode: 'cli' (terminal dashboard), 'browser' (web dashboard), or 'no-ui' (headless)",
    )
    parser.add_argument("--cli", action="store_true", help="Display interactive Rich CLI terminal dashboard")
    parser.add_argument("--browser", action="store_true", help="Launch Web Dashboard (alias for --web)")
    parser.add_argument("--no-ui", action="store_true", help="Disable visual UI (run in headless mode)")
    parser.add_argument("--web", action="store_true", help="Launch Web Dashboard (FastAPI + WebSocket)")
    parser.add_argument("--port", type=int, default=8000, help="Web dashboard port (default: 8000)")
    parser.add_argument("--open-browser", action="store_true", help="Automatically open web dashboard in default browser")
    parser.add_argument("--replay-file", type=str, default="", help="Path to recording file for replay mode")
    parser.add_argument("--speed", type=float, default=1.0, help="Replay speed multiplier")
    parser.add_argument("--size", type=float, default=0.1, help="Simulated order size in BTC (default: 0.1 BTC)")
    parser.add_argument("--cash", type=float, default=10000.0, help="Initial simulated account capital in USD (default: $10,000)")
    parser.add_argument("--capital", type=float, default=0.0, help="Total trading capital in USD to dynamically scale order sizes")
    parser.add_argument("--allocation", type=float, default=1.0, help="Fraction of capital per trade")
    parser.add_argument("--save-model", type=str, default="models/l2_trained_weights.json", help="Model weights save path")
    parser.add_argument("--max-files", type=int, default=0, help="Maximum number of files to ingest for ML training")
    parser.add_argument("--prune-empty", action="store_true", help="Remove empty audit session directories")
    parser.add_argument("--repair", action="store_true", help="Repair and backfill stalled audit manifests")
    parser.add_argument("--include-empty", action="store_true", help="Include 0-trade sessions in audit listing")
    parser.add_argument("--no-audit", action="store_true", help="Disable audit recording in live/replay")
    parser.add_argument("--save-config", action="store_true", help="Persist modified strategy configuration to JSON")
    parser.add_argument("--no-save", action="store_true", help="Do not persist strategy configuration changes (in-memory run only)")
    parser.add_argument(
        "--stock", "--xyz-stock",
        dest="xyz_stock",
        action="store_true",
        help="Flag asset as an XYZ stock/equity on Hyperliquid",
    )
    parser.add_argument("--taker-fee", type=float, default=None, help="Custom taker fee in bps")
    parser.add_argument("--maker-fee", type=float, default=None, help="Custom maker fee in bps")
    parser.add_argument("--priority-fee", type=float, default=None, help="Sequencer priority fee in bps")
    parser.add_argument(
        "--market",
        nargs="?",
        const="true",
        default=None,
        type=str,
        help="Force program to execute via market orders (aggressive IOC taker). Usage: --market true/false.",
    )
    parser.add_argument("--slippage", type=float, default=None, help="Market order slippage tolerance percentage (e.g. 0.05 for 5 bps)")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    cfg = AppConfig.for_core(strategies_config=args.strategies_config)

    # Strategy override validation
    if args.strategy:
        strat_name = args.strategy.strip()
        if args.mode not in ("audit",) and strat_name not in CORE_EXECUTION_STRATEGIES:
            Console().print(f"[bold red]Error: Strategy '{strat_name}' is not a Core execution strategy. Valid options: {', '.join(CORE_EXECUTION_STRATEGIES)}[/bold red]")
            sys.exit(1)
        cfg.strategies.live_execution.active_strategy = strat_name
        s = cfg.strategies.get_strategy(strat_name)
        if s:
            s.enabled = True

    # Market order and slippage configuration
    force_market = None
    if args.market is not None:
        force_market = str(args.market).strip().lower() in ("true", "1", "yes", "t", "on")
    elif args.slippage is not None:
        force_market = True

    market_slippage = None
    if args.slippage is not None:
        market_slippage = float(args.slippage) / 100.0 if float(args.slippage) > 0.05 else float(args.slippage)

    if force_market is not None:
        cfg.strategies.live_execution.force_market_orders = force_market
        cfg.backtest.force_market_orders = force_market

    if market_slippage is not None:
        cfg.strategies.live_execution.market_slippage_pct = market_slippage
        cfg.backtest.market_slippage_pct = market_slippage

    # Priority fee override
    if args.priority_fee is not None:
        cfg.strategies.live_execution.priority_fee_bps = args.priority_fee
        cfg.backtest.priority_fee_bps = args.priority_fee

    if (args.save_config or force_market is not None or market_slippage is not None) and not args.no_save and args.save_config:
        cfg.strategies.save()

    # Configure network environment
    if args.use_testnet is not None:
        cfg.hyperliquid.use_testnet = args.use_testnet

    if args.account:
        cfg.account.account_address = args.account.strip()
    if args.secret_key:
        cfg.account.secret_key = args.secret_key.strip()

    # Configure asset and fee schedule
    is_stock_override = True if args.xyz_stock else None
    cfg.market.configure_for_coin(
        args.coin,
        is_stock=is_stock_override,
        taker_fee_bps=args.taker_fee,
        maker_fee_bps=args.maker_fee,
    )

    if cfg.market.is_xyz_stock:
        Console().print(
            f"[bold cyan]Resolved XYZ Market:[/bold cyan] '{args.coin}' -> canonical Hyperliquid ticker '[bold green]{cfg.market.coin}[/bold green]' "
            f"(Fees: [bold yellow]{cfg.market.maker_fee_bps:.2f} bps maker / {cfg.market.taker_fee_bps:.2f} bps taker[/bold yellow])"
        )

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
            base_shares = 8.0 if cfg.market.coin == "xyz:SKHX" else 50.0
            if args.size == 0.1:
                args.size = round(base_shares * ratio, 2)
            if args.order_size == 0.0005:
                args.order_size = max(0.1 if cfg.market.coin == "xyz:SKHX" else 1.0, round(base_shares * 0.5 * ratio * args.allocation, 2))
    else:
        if cfg.market.coin == "HYPE":
            if args.order_size == 0.0005:
                args.order_size = 1.0
            if args.size == 0.1:
                args.size = 95.0
        elif cfg.market.is_xyz_stock:
            base_shares = 8.0 if cfg.market.coin == "xyz:SKHX" else 50.0
            if args.order_size == 0.0005:
                args.order_size = 0.8 if cfg.market.coin == "xyz:SKHX" else 1.0
            if args.size == 0.1:
                args.size = base_shares

    cfg.backtest.order_size_btc = args.size

    # UI display mode resolution
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
        print_core_strategies_status(cfg, console=console)
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
        p_fee = args.priority_fee if args.priority_fee is not None else cfg.strategies.live_execution.priority_fee_bps
        force_mkt = getattr(cfg.strategies.live_execution, "force_market_orders", False)
        mkt_slip = getattr(cfg.strategies.live_execution, "market_slippage_pct", 0.0005)
        executor = LiveOrderExecutor(
            config=cfg,
            console=console,
            default_order_size_btc=args.order_size,
            priority_fee_bps=p_fee,
            force_market_orders=force_mkt,
            market_slippage_pct=mkt_slip,
        )
        is_buy = args.side.upper() == "BUY"
        if force_mkt:
            executor.place_market_order(
                is_buy=is_buy,
                size_btc=args.order_size,
                slippage_pct=mkt_slip,
                strategy_name="ManualMarketOrder",
            )
        else:
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
        en_exec = list(cfg.strategies.get_enabled_strategy_defs().keys())
        dis_exec = [s for s in CORE_EXECUTION_STRATEGIES if s not in en_exec]
        console.print(f"[bold cyan]Core Strategies Configuration ({cfg.strategies.filepath}):[/bold cyan]")
        console.print(f"  • [bold cyan]Core Execution (4 Primary):[/bold cyan] [green]{len(en_exec)} active[/green] ({', '.join(en_exec) if en_exec else 'none'}) | [dim red]{len(dis_exec)} deselected[/dim red]")
        ui_label = {
            "cli": "CLI (Interactive Terminal Dashboard)",
            "browser": f"BROWSER (Web Dashboard running on http://localhost:{args.port})",
            "no-ui": "NO-UI (Headless Background Mode)",
        }.get(ui_mode, ui_mode.upper())
        console.print(f"[bold cyan]Interface Mode:[/bold cyan] [bold green]{ui_label}[/bold green]")
        fee_profile_name = "XYZ Stock / Equities" if cfg.market.is_xyz_stock else "Crypto Perps"
        console.print(f"[bold cyan]Asset & Fees:[/bold cyan] [bold green]{cfg.market.coin}[/bold green] ([yellow]{fee_profile_name}[/yellow]) | Maker: [green]{cfg.market.maker_fee_bps:.2f} bps[/green] | Taker: [yellow]{cfg.market.taker_fee_bps:.2f} bps[/yellow]")
        p_fee = cfg.strategies.live_execution.priority_fee_bps
        if p_fee > 0:
            console.print(f"[bold cyan]Priority Fee:[/bold cyan] [bold yellow]{p_fee:.1f} bps[/bold yellow] (p={int(round(p_fee * 10000))})")
        else:
            console.print(f"[bold cyan]Priority Fee:[/bold cyan] [dim]0.0 bps (Standard Consensus Queue)[/dim]")

        if args.live_orders:
            cfg.backtest.order_size_btc = args.order_size
            net = cfg.hyperliquid.network_name.upper()
            active_live = cfg.strategies.get_effective_live_strategy()
            console.print(f"\n[bold red blink]⚠ LIVE {net} ORDER EXECUTION ENABLED! Primary Core Strategy: {active_live}[/bold red blink]\n")

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
        console.print(f"[bold yellow]Running core benchmark on {cfg.market.coin} ({cfg.hyperliquid.network_name}) for {duration} seconds...[/bold yellow]")
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
        fpath_lower = args.replay_file.lower().replace("\\", "/")
        if args.coin == "BTC":
            if any(k in fpath_lower for k in ("xyz_skhx", "skhx", "skhynix")):
                cfg.market.configure_for_coin("xyz:SKHX", taker_fee_bps=args.taker_fee, maker_fee_bps=args.maker_fee)
            elif any(k in fpath_lower for k in ("xyz_skhy", "skhy")):
                cfg.market.configure_for_coin("xyz:SKHY", taker_fee_bps=args.taker_fee, maker_fee_bps=args.maker_fee)
            else:
                for c in ["btc", "hype", "sol", "eth"]:
                    if f"hl_{c}_" in fpath_lower or f"/{c}/" in fpath_lower:
                        cfg.market.coin = c.upper()
                        break
        ratio = (cfg.backtest.capital_usd / 10000.0) if (cfg.backtest.capital_usd and cfg.backtest.capital_usd > 0) else 1.0
        if cfg.market.coin == "HYPE" and (args.size == 0.1 or args.size == 95.0):
            cfg.backtest.order_size_btc = round(95.0 * ratio, 2)
        elif cfg.market.coin == "SOL" and (args.size == 0.1 or args.size == 50.0):
            cfg.backtest.order_size_btc = round(50.0 * ratio, 2)
        elif cfg.market.coin == "ETH" and (args.size == 0.1 or args.size == 3.0):
            cfg.backtest.order_size_btc = round(3.0 * ratio, 4)
        elif cfg.market.is_xyz_stock and args.size == 0.1:
            base_shares = 8.0 if cfg.market.coin == "xyz:SKHX" else 50.0
            cfg.backtest.order_size_btc = round(base_shares * ratio, 2)

        import time
        from engine.data_collector import L2ReplayEngine
        runner = L2EngineRunner(
            config=cfg,
            record_data=False,
            enable_audit=not args.no_audit,
            web_mode=enable_web,
            web_port=args.port,
            open_browser=args.open_browser,
        )
        replay = L2ReplayEngine(args.replay_file, speed_multiplier=args.speed)
        console.print(f"[bold yellow]Replaying {args.replay_file} on Core strategies at {args.speed}x speed...[/bold yellow]")
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
                sub_dict = res.metadata.get("sub_signals", {})
                sub_sigs = {name: sig.score for name, sig in sub_dict.items()}
                sub_sigs["CompositeAlpha"] = res.score
                sub_confs = {name: getattr(sig, "confidence", 1.0) for name, sig in sub_dict.items()}
                sub_confs["CompositeAlpha"] = getattr(res, "confidence", 1.0)
                runner.evaluator.record_step(
                    now_ms,
                    runner.book.mid_price,
                    runner.book.best_bid,
                    runner.book.best_ask,
                    sub_sigs,
                    confidences=sub_confs,
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
