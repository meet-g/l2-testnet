"""High-Throughput Parallel Replay Evaluation for ALL Core Execution Strategies across ALL 568 HYPE Datasets.

Evaluates the 4 core execution strategies:
1. Hedged_Convexity
2. Convexity_Cascade
3. Momentum_Expansion
4. Queue_Replenishment

Evaluates both:
A. Unified Portfolio Mode (All 4 core strategies running concurrently with co-entry gating, size discounts, and portfolio risk management).
B. Standalone Mode (Each of the 4 core strategies evaluated in total isolation across all 568 files).
"""

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import glob
import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

# Set OpenMP and math runtime threading policies for max multiprocessing throughput
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

# Force UTF-8 stdout/stderr on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rich.console import Console
from rich.table import Table

from config import AppConfig, BacktestConfig, MarketConfig, StrategiesConfig
from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from engine.backtester import EdgeEvaluator
from engine.data_collector import L2ReplayEngine
from signals.composite_alpha import CompositeAlphaSignal

CORE_STRATEGIES = [
    "Hedged_Convexity",
    "Convexity_Cascade",
    "Momentum_Expansion",
    "Queue_Replenishment",
]


def replay_single_file_worker(filepath: str) -> Dict[str, Any]:
    """Worker process: Replays a single HYPE recording file across all core execution strategies."""
    filename = os.path.basename(filepath)
    size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)
    t0 = time.time()

    m_cfg = MarketConfig(coin="HYPE")
    bt_cfg = BacktestConfig(
        capital_usd=10000.0,
        order_size_btc=0.1,
        horizons_seconds=[],  # Bypass IC buffer for pure backtest speed
    )

    strat_cfg = StrategiesConfig.load("strategies.json")
    all_defs = strat_cfg.get_enabled_strategy_defs()
    all_params = strat_cfg.get_strategy_params()

    # 1. Portfolio Evaluator (All 4 Core Strategies Running Concurrently)
    eval_portfolio = EdgeEvaluator(
        market_cfg=m_cfg,
        bt_cfg=bt_cfg,
        strategy_defs=all_defs,
        strategy_params=all_params,
    )

    # 2. Standalone Evaluators (Each strategy running in isolation without co-entry interactions)
    eval_standalone: Dict[str, EdgeEvaluator] = {}
    for s_name in CORE_STRATEGIES:
        if s_name in all_defs:
            eval_standalone[s_name] = EdgeEvaluator(
                market_cfg=m_cfg,
                bt_cfg=bt_cfg,
                strategy_defs={s_name: all_defs[s_name]},
                strategy_params=all_params,
            )

    book = OrderBook("HYPE")
    trades = TradeManager("HYPE")
    # Disable AdaptiveML to avoid heavy tree re-evaluations since core strategies do not use ML
    alpha = CompositeAlphaSignal(enabled_signals={"AdaptiveML": False})

    last_eval_ms = 0
    events_count = 0

    try:
        replay = L2ReplayEngine(filepath, speed_multiplier=100000.0)
        for event in replay.stream_events():
            events_count += 1
            ch = event.get("channel")
            dt = event.get("data")
            now_ms = event.get("recv_ts", 0)

            if ch == "l2Book":
                book.update_from_raw(dt)
            elif ch == "trades":
                trades.process_raw_trades(dt)

            if book.is_valid and (now_ms - last_eval_ms >= 100):
                last_eval_ms = now_ms
                res = alpha.compute(book, trades, now_ms)
                sub_sigs = {name: sig.score for name, sig in res.metadata.get("sub_signals", {}).items()}
                sub_sigs["CompositeAlpha"] = res.score

                # Step Portfolio
                eval_portfolio.record_step(now_ms, book.mid_price, book.best_bid, book.best_ask, sub_sigs)

                # Step Standalones
                for ev in eval_standalone.values():
                    ev.record_step(now_ms, book.mid_price, book.best_bid, book.best_ask, sub_sigs)

        if book.is_valid:
            now_ms = book.last_update_time_ms or int(time.time() * 1000)
            eval_portfolio.close_open_positions(book.mid_price, now_ms, reason="SESSION_SHUTDOWN")
            for ev in eval_standalone.values():
                ev.close_open_positions(book.mid_price, now_ms, reason="SESSION_SHUTDOWN")

    except Exception as e:
        return {
            "filename": filename,
            "filepath": filepath,
            "size_mb": size_mb,
            "events_count": events_count,
            "elapsed_s": time.time() - t0,
            "error": str(e),
            "portfolio_trades": [],
            "standalone_trades": {s: [] for s in CORE_STRATEGIES},
        }

    def serialize_trades(trade_list):
        return [
            {
                "strategy_name": t.strategy_name,
                "entry_time_ms": t.entry_time_ms,
                "exit_time_ms": t.exit_time_ms,
                "side": t.side,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "size_btc": t.size_btc,
                "gross_pnl_usd": t.gross_pnl_usd,
                "fees_usd": t.fees_usd,
                "net_pnl_usd": t.net_pnl_usd,
                "return_bps": t.return_bps,
                "exit_reason": t.exit_reason,
                "execution_type": t.execution_type,
            }
            for t in trade_list
        ]

    port_trades = []
    for s_name, st in eval_portfolio.strategies.items():
        port_trades.extend(serialize_trades(st.trades))

    std_trades = {}
    for s_name, ev in eval_standalone.items():
        st = ev.strategies.get(s_name)
        std_trades[s_name] = serialize_trades(st.trades) if st else []

    return {
        "filename": filename,
        "filepath": filepath,
        "size_mb": size_mb,
        "events_count": events_count,
        "elapsed_s": time.time() - t0,
        "error": None,
        "portfolio_trades": port_trades,
        "standalone_trades": std_trades,
    }


def aggregate_trade_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes comprehensive quantitative performance metrics from a list of trades."""
    n = len(trades)
    if n == 0:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "gross_pnl": 0.0,
            "fees": 0.0,
            "net_pnl": 0.0,
            "net_per_trade": 0.0,
            "profit_factor": 0.0,
            "avg_return_bps": 0.0,
            "long_trades": 0,
            "long_wins": 0,
            "long_wr": 0.0,
            "long_net_pnl": 0.0,
            "short_trades": 0,
            "short_wins": 0,
            "short_wr": 0.0,
            "short_net_pnl": 0.0,
            "max_drawdown_usd": 0.0,
            "max_drawdown_pct": 0.0,
            "exit_reasons": {},
            "exec_types": {},
        }

    wins = [t for t in trades if t["net_pnl_usd"] > 0]
    losses = [t for t in trades if t["net_pnl_usd"] < 0]

    gross_pnl = sum(t["gross_pnl_usd"] for t in trades)
    fees = sum(t["fees_usd"] for t in trades)
    net_pnl = sum(t["net_pnl_usd"] for t in trades)
    gross_wins = sum(t["gross_pnl_usd"] for t in wins)
    gross_losses = abs(sum(t["gross_pnl_usd"] for t in losses))

    pf = (gross_wins / gross_losses) if gross_losses > 1e-9 else (99.0 if gross_wins > 0 else 0.0)

    long_trades = [t for t in trades if t["side"] == "LONG"]
    short_trades = [t for t in trades if t["side"] == "SHORT"]

    long_wins = [t for t in long_trades if t["net_pnl_usd"] > 0]
    short_wins = [t for t in short_trades if t["net_pnl_usd"] > 0]

    # Calculate Drawdown
    # Sort trades chronologically by exit time
    sorted_trades = sorted(trades, key=lambda x: x["exit_time_ms"])
    cum_pnl = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted_trades:
        cum_pnl += t["net_pnl_usd"]
        if cum_pnl > peak:
            peak = cum_pnl
        dd = peak - cum_pnl
        if dd > max_dd:
            max_dd = dd

    exits = defaultdict(int)
    exec_types = defaultdict(int)
    for t in trades:
        exits[t["exit_reason"]] += 1
        exec_types[t["execution_type"]] += 1

    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / n * 100.0) if n > 0 else 0.0,
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_pnl": net_pnl,
        "net_per_trade": (net_pnl / n) if n > 0 else 0.0,
        "profit_factor": pf,
        "avg_return_bps": (sum(t["return_bps"] for t in trades) / n) if n > 0 else 0.0,
        "long_trades": len(long_trades),
        "long_wins": len(long_wins),
        "long_wr": (len(long_wins) / len(long_trades) * 100.0) if long_trades else 0.0,
        "long_net_pnl": sum(t["net_pnl_usd"] for t in long_trades),
        "short_trades": len(short_trades),
        "short_wins": len(short_wins),
        "short_wr": (len(short_wins) / len(short_trades) * 100.0) if short_trades else 0.0,
        "short_net_pnl": sum(t["net_pnl_usd"] for t in short_trades),
        "max_drawdown_usd": max_dd,
        "exit_reasons": dict(exits),
        "exec_types": dict(exec_types),
    }


def main():
    console = Console()
    console.print("\n[bold cyan]=========================================================================[/bold cyan]")
    console.print("[bold cyan]   Hyperliquid L2 Microstructure - All Core Strategies Replay Engine   [/bold cyan]")
    console.print("[bold cyan]=========================================================================[/bold cyan]\n")

    files = sorted(glob.glob("data/hype/hl_hype_l2_*.jsonl"))
    valid_files = [f for f in files if os.path.isfile(f) and os.path.getsize(f) > 1000]
    total_files = len(valid_files)

    cpu_cores = os.cpu_count() or 4
    console.print(f"[bold yellow]Discovered {total_files} HYPE L2 sessions across {sum(os.path.getsize(f) for f in valid_files)/1e9:.2f} GB data.[/bold yellow]")
    console.print(f"[bold yellow]Executing parallel replay across {cpu_cores} worker cores...[/bold yellow]\n")

    start_time = time.time()
    results: List[Dict[str, Any]] = []

    with ProcessPoolExecutor(max_workers=cpu_cores) as executor:
        futures = {executor.submit(replay_single_file_worker, f): f for f in valid_files}
        completed = 0

        for future in as_completed(futures):
            res = future.result()
            results.append(res)
            completed += 1
            if completed % 50 == 0 or completed == total_files:
                elapsed = time.time() - start_time
                fps = completed / elapsed if elapsed > 0 else 0
                eta = (total_files - completed) / fps if fps > 0 else 0
                console.print(f"[{completed}/{total_files}] Completed {completed/total_files*100:.1f}% ({fps:.1f} sessions/s, ETA: {eta:.0f}s)...")

    total_time = time.time() - start_time
    console.print(f"\n[bold green]✓ Successfully replayed all {total_files} sessions in {total_time:.1f}s ({total_files/total_time:.2f} sessions/s)![/bold green]\n")

    # 1. Aggregate Portfolio Trades
    all_portfolio_trades = []
    strat_portfolio_trades = defaultdict(list)
    for r in results:
        for t in r.get("portfolio_trades", []):
            all_portfolio_trades.append(t)
            strat_portfolio_trades[t["strategy_name"]].append(t)

    # 2. Aggregate Standalone Trades
    strat_standalone_trades = defaultdict(list)
    for r in results:
        for s_name, trades in r.get("standalone_trades", {}).items():
            strat_standalone_trades[s_name].extend(trades)

    # Compute Metrics
    portfolio_overall_metrics = aggregate_trade_metrics(all_portfolio_trades)
    port_per_strat_metrics = {s: aggregate_trade_metrics(strat_portfolio_trades[s]) for s in CORE_STRATEGIES}
    standalone_per_strat_metrics = {s: aggregate_trade_metrics(strat_standalone_trades[s]) for s in CORE_STRATEGIES}

    # ---------------------------------------------------------
    # PRINT RESULTS TABLE: UNIFIED PORTFOLIO MODE
    # ---------------------------------------------------------
    table_port = Table(title="[bold green]UNIFIED PORTFOLIO MODE: ALL 4 CORE STRATEGIES RUNNING TOGETHER[/bold green]", header_style="bold cyan")
    table_port.add_column("Strategy / Metric", justify="left")
    table_port.add_column("Trades", justify="right")
    table_port.add_column("Win Rate", justify="right")
    table_port.add_column("Gross PnL", justify="right")
    table_port.add_column("Retail Fees", justify="right")
    table_port.add_column("Net PnL", justify="right")
    table_port.add_column("Net/Trade", justify="right")
    table_port.add_column("Profit Factor", justify="right")
    table_port.add_column("Max Drawdown", justify="right")

    for s in CORE_STRATEGIES:
        m = port_per_strat_metrics[s]
        net_col = f"[green]${m['net_pnl']:+,.2f}[/green]" if m['net_pnl'] >= 0 else f"[red]${m['net_pnl']:+,.2f}[/red]"
        table_port.add_row(
            s,
            str(m["trades"]),
            f"{m['win_rate']:.1f}%",
            f"${m['gross_pnl']:+,.2f}",
            f"${m['fees']:,.2f}",
            net_col,
            f"${m['net_per_trade']:+,.3f}",
            f"{m['profit_factor']:.2f}",
            f"${m['max_drawdown_usd']:,.2f}",
        )

    # Total row
    tot = portfolio_overall_metrics
    tot_col = f"[bold green]${tot['net_pnl']:+,.2f}[/bold green]" if tot['net_pnl'] >= 0 else f"[bold red]${tot['net_pnl']:+,.2f}[/bold red]"
    table_port.add_section()
    table_port.add_row(
        "[bold white]TOTAL PORTFOLIO[/bold white]",
        f"[bold]{tot['trades']}[/bold]",
        f"[bold]{tot['win_rate']:.1f}%[/bold]",
        f"[bold]${tot['gross_pnl']:+,.2f}[/bold]",
        f"[bold]${tot['fees']:,.2f}[/bold]",
        tot_col,
        f"[bold]${tot['net_per_trade']:+,.3f}[/bold]",
        f"[bold]{tot['profit_factor']:.2f}[/bold]",
        f"[bold]${tot['max_drawdown_usd']:,.2f}[/bold]",
    )
    console.print(table_port)
    console.print()

    # ---------------------------------------------------------
    # PRINT RESULTS TABLE: STANDALONE MODE
    # ---------------------------------------------------------
    table_std = Table(title="[bold yellow]STANDALONE MODE: EACH CORE STRATEGY EVALUATED IN ISOLATION[/bold yellow]", header_style="bold cyan")
    table_std.add_column("Strategy (Standalone)", justify="left")
    table_std.add_column("Trades", justify="right")
    table_std.add_column("Win Rate", justify="right")
    table_std.add_column("Gross PnL", justify="right")
    table_std.add_column("Retail Fees", justify="right")
    table_std.add_column("Net PnL", justify="right")
    table_std.add_column("Net/Trade", justify="right")
    table_std.add_column("Profit Factor", justify="right")
    table_std.add_column("Max Drawdown", justify="right")

    for s in CORE_STRATEGIES:
        m = standalone_per_strat_metrics[s]
        net_col = f"[green]${m['net_pnl']:+,.2f}[/green]" if m['net_pnl'] >= 0 else f"[red]${m['net_pnl']:+,.2f}[/red]"
        table_std.add_row(
            s,
            str(m["trades"]),
            f"{m['win_rate']:.1f}%",
            f"${m['gross_pnl']:+,.2f}",
            f"${m['fees']:,.2f}",
            net_col,
            f"${m['net_per_trade']:+,.3f}",
            f"{m['profit_factor']:.2f}",
            f"${m['max_drawdown_usd']:,.2f}",
        )
    console.print(table_std)
    console.print()

    # ---------------------------------------------------------
    # PRINT EXIT REASONS TABLE (PORTFOLIO)
    # ---------------------------------------------------------
    table_exit = Table(title="[bold magenta]PORTFOLIO EXIT REASON DISTRIBUTION[/bold magenta]", header_style="bold cyan")
    table_exit.add_column("Strategy", justify="left")
    table_exit.add_column("Take Profit", justify="right")
    table_exit.add_column("Trailing Stop", justify="right")
    table_exit.add_column("Defensive Hedge", justify="right")
    table_exit.add_column("Stop Loss", justify="right")
    table_exit.add_column("Signal Rev", justify="right")
    table_exit.add_column("Time Limit", justify="right")
    table_exit.add_column("Shutdown", justify="right")

    for s in CORE_STRATEGIES:
        ex = port_per_strat_metrics[s]["exit_reasons"]
        table_exit.add_row(
            s,
            str(ex.get("TAKE_PROFIT", 0)),
            str(ex.get("TRAILING_STOP", 0)),
            str(ex.get("DEFENSIVE_MAKER_HEDGE", 0)),
            str(ex.get("STOP_LOSS", 0)),
            str(ex.get("SIGNAL_REVERSAL", 0)),
            str(ex.get("TIME_LIMIT", 0)),
            str(ex.get("SESSION_SHUTDOWN", 0)),
        )
    console.print(table_exit)
    console.print()

    # Save full JSON report
    report_data = {
        "dataset_files": total_files,
        "total_data_gb": sum(os.path.getsize(f) for f in valid_files) / 1e9,
        "elapsed_seconds": total_time,
        "portfolio_overall": portfolio_overall_metrics,
        "portfolio_by_strategy": port_per_strat_metrics,
        "standalone_by_strategy": standalone_per_strat_metrics,
    }

    out_json = os.path.join("audits", "hype_all_core_strategies_replay_report.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    console.print(f"[bold green]✓ Full audit data saved to {out_json}[/bold green]\n")


if __name__ == "__main__":
    main()
