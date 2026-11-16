"""High-Throughput Parallel Evaluation for Stock_Microstructure_Alpha across ALL Large HYPE Sessions.

Evaluates Stock_Microstructure_Alpha (signal: StockMicrostructure, exec: HEDGED_MAKER)
across large HYPE recordings (>= 10.0 MB or >= 8.0 MB) in data/hype/.
Analyzes:
- Win rate, profit factor, gross/net PnL, fee drag under Hyperliquid crypto fee structure (1.5 bps maker, 4.5 bps taker)
- Exit reason distribution (TAKE_PROFIT, TRAILING_STOP, STOP_LOSS, TIME_LIMIT, DEFENSIVE_MAKER_HEDGE)
- Holding duration, return in bps, and market regime stability.
"""

from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import glob
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

# Set threading policy for max multiprocessing throughput
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

from config import BacktestConfig, MarketConfig, StrategiesConfig
from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from engine.backtester import EdgeEvaluator
from engine.data_collector import L2ReplayEngine
from signals.composite_alpha import CompositeAlphaSignal


def replay_stock_alpha_file_worker(
    filepath: str,
    order_size_override: Optional[float] = None,
    param_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Worker process: Replays a single HYPE recording for Stock_Microstructure_Alpha."""
    filename = os.path.basename(filepath)
    size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)
    t0 = time.time()

    m_cfg = MarketConfig(coin="HYPE")
    bt_cfg = BacktestConfig(
        capital_usd=10000.0,
        horizons_seconds=[],  # Bypass IC buffer for pure backtest speed
    )

    strat_cfg = StrategiesConfig.load("strategies_core.json")
    all_params = strat_cfg.get_strategy_params()

    if "Stock_Microstructure_Alpha" in all_params:
        if order_size_override is not None:
            all_params["Stock_Microstructure_Alpha"]["order_size_btc"] = order_size_override
        if param_overrides:
            for k, v in param_overrides.items():
                if v is not None:
                    all_params["Stock_Microstructure_Alpha"][k] = v

    strategy_defs = {
        "Stock_Microstructure_Alpha": ("StockMicrostructure", "HEDGED_MAKER"),
    }

    evaluator = EdgeEvaluator(
        market_cfg=m_cfg,
        bt_cfg=bt_cfg,
        strategy_defs=strategy_defs,
        strategy_params=all_params,
    )

    book = OrderBook("HYPE")
    trades = TradeManager("HYPE")
    alpha = CompositeAlphaSignal(enabled_signals={"AdaptiveML": False})
    replay = L2ReplayEngine(filepath, speed_multiplier=100000.0)

    last_eval_ms = 0
    eval_interval_ms = 100  # 10 Hz matching live execution
    events_count = 0

    for event in replay.stream_events():
        events_count += 1
        ch = event.get("channel")
        dt = event.get("data")
        now_ms = event.get("recv_ts", 0)

        if ch == "l2Book":
            book.update_from_raw(dt)
        elif ch == "trades":
            trades.process_raw_trades(dt)
        elif ch == "activeAssetCtx":
            book.update_asset_ctx(dt)

        if book.is_valid and (now_ms - last_eval_ms >= eval_interval_ms):
            last_eval_ms = now_ms
            res = alpha.compute(book, trades, now_ms)
            sub_sigs = {name: sig.score for name, sig in res.metadata.get("sub_signals", {}).items()}
            sub_sigs["CompositeAlpha"] = res.score
            evaluator.record_step(
                now_ms,
                book.mid_price,
                book.best_bid,
                book.best_ask,
                sub_sigs,
            )

    if book.is_valid:
        now_ms = book.last_update_time_ms or int(time.time() * 1000)
        evaluator.close_open_positions(book.mid_price, now_ms, reason="SESSION_SHUTDOWN")

    elapsed_s = max(0.001, time.time() - t0)
    st = evaluator.strategies.get("Stock_Microstructure_Alpha")
    trade_list = st.trades if st else []

    wins = [t for t in trade_list if t.net_pnl_usd > 0]
    losses = [t for t in trade_list if t.net_pnl_usd < 0]
    evens = [t for t in trade_list if t.net_pnl_usd == 0]

    gross_pnl = sum(t.gross_pnl_usd for t in trade_list)
    fees = sum(t.fees_usd for t in trade_list)
    net_pnl = sum(t.net_pnl_usd for t in trade_list)

    gross_wins = sum(t.gross_pnl_usd for t in trade_list if t.gross_pnl_usd > 0)
    gross_losses = sum(abs(t.gross_pnl_usd) for t in trade_list if t.gross_pnl_usd < 0)
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else (99.9 if gross_wins > 0 else 0.0)

    exit_counts = Counter(t.exit_reason for t in trade_list)
    side_counts = Counter(t.side for t in trade_list)

    holding_times = [(t.exit_time_ms - t.entry_time_ms) / 1000.0 for t in trade_list if t.exit_time_ms >= t.entry_time_ms]
    avg_holding_s = (sum(holding_times) / len(holding_times)) if holding_times else 0.0

    return_bps_list = [t.return_bps for t in trade_list]
    avg_return_bps = (sum(return_bps_list) / len(return_bps_list)) if return_bps_list else 0.0

    trade_details = [
        {
            "side": t.side,
            "entry_time_ms": t.entry_time_ms,
            "exit_time_ms": t.exit_time_ms,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "size": t.size_btc,
            "gross_pnl": t.gross_pnl_usd,
            "fees": t.fees_usd,
            "net_pnl": t.net_pnl_usd,
            "return_bps": t.return_bps,
            "exit_reason": t.exit_reason,
            "holding_time_secs": (t.exit_time_ms - t.entry_time_ms) / 1000.0,
        }
        for t in trade_list
    ]

    return {
        "filename": filename,
        "filepath": filepath,
        "size_mb": size_mb,
        "elapsed_s": elapsed_s,
        "events_count": events_count,
        "total_trades": len(trade_list),
        "wins": len(wins),
        "losses": len(losses),
        "evens": len(evens),
        "win_rate_pct": (len(wins) / len(trade_list) * 100.0) if trade_list else 0.0,
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_pnl": net_pnl,
        "profit_factor": profit_factor,
        "avg_return_bps": avg_return_bps,
        "avg_holding_s": avg_holding_s,
        "exit_counts": dict(exit_counts),
        "side_counts": dict(side_counts),
        "trades": trade_details,
    }


def main():
    console = Console()
    import argparse

    parser = argparse.ArgumentParser(description="Test Stock_Microstructure_Alpha across large HYPE sessions.")
    parser.add_argument("--min-size-mb", type=float, default=10.0, help="Minimum file size in MB (default: 10.0)")
    parser.add_argument("--max-files", type=int, default=0, help="Max files to test (0 = all matching)")
    parser.add_argument("--order-size", type=float, default=None, help="Override order size (e.g. 10.0 or 95.0)")
    parser.add_argument("--workers", type=int, default=8, help="Number of parallel worker processes (default: 8)")
    parser.add_argument("--tp", type=float, default=None, help="Override take_profit_bps")
    parser.add_argument("--sl", type=float, default=None, help="Override stop_loss_bps")
    parser.add_argument("--trail-act", type=float, default=None, help="Override trailing_stop_activation_bps")
    parser.add_argument("--trail-dist", type=float, default=None, help="Override trailing_stop_distance_bps")
    parser.add_argument("--max-hold-s", type=int, default=None, help="Override max_holding_time_secs")
    parser.add_argument("--out", type=str, default="audits/stock_alpha_hype_large_summary.json", help="Summary output JSON path")
    args = parser.parse_args()

    param_overrides = {}
    if args.tp is not None: param_overrides["take_profit_bps"] = args.tp
    if args.sl is not None: param_overrides["stop_loss_bps"] = args.sl
    if args.trail_act is not None: param_overrides["trailing_stop_activation_bps"] = args.trail_act
    if args.trail_dist is not None: param_overrides["trailing_stop_distance_bps"] = args.trail_dist
    if args.max_hold_s is not None: param_overrides["max_holding_time_secs"] = args.max_hold_s

    data_dir = os.path.join("data", "hype")
    all_files = sorted(
        glob.glob(os.path.join(data_dir, "hl_hype_l2_*.jsonl")),
        key=os.path.getsize,
        reverse=True,
    )
    target_files = [f for f in all_files if os.path.getsize(f) >= args.min_size_mb * 1024 * 1024]
    if args.max_files > 0:
        target_files = target_files[:args.max_files]

    total_mb = sum(os.path.getsize(f) for f in target_files) / (1024.0 * 1024.0)

    console.print("[bold cyan]===============================================================================[/bold cyan]")
    console.print("[bold green]HYPE REPLAY AUDIT: Stock_Microstructure_Alpha Across Large Recording Sessions[/bold green]")
    console.print("[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"Target Sessions:    [bold yellow]{len(target_files)} sessions[/bold yellow] (Min Size: {args.min_size_mb:.1f} MB, Total: {total_mb:.1f} MB)")
    console.print(f"Parallel Workers:   [bold yellow]{args.workers}[/bold yellow] processes")
    console.print(f"Target Strategy:    [bold white]Stock_Microstructure_Alpha[/bold white] (Signal: StockMicrostructure, Exec: HEDGED_MAKER)")
    if param_overrides:
        console.print(f"Param Overrides:    [bold yellow]{param_overrides}[/bold yellow]")
    console.print(f"Exchange Fee Model: [bold white]Hyperliquid Perp (Maker: 1.50 bps, Taker: 4.50 bps)[/bold white]\n")

    t_start = time.time()
    results = []

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        future_to_file = {
            executor.submit(replay_stock_alpha_file_worker, f, args.order_size, param_overrides): f
            for f in target_files
        }

        completed = 0
        for future in as_completed(future_to_file):
            completed += 1
            fpath = future_to_file[future]
            try:
                res = future.result()
                results.append(res)
                fname = res["filename"]
                trd = res["total_trades"]
                wr = res["win_rate_pct"]
                net = res["net_pnl"]
                color = "green" if net > 0 else ("red" if net < 0 else "white")
                console.print(
                    f"[{completed:2d}/{len(target_files)}] [dim]{fname}[/dim] ({res['size_mb']:.1f}MB, {res['elapsed_s']:.1f}s): "
                    f"Trades={trd:2d} | WinRate={wr:5.1f}% | Net=[{color}]${net:+7.2f}[/{color}]"
                )
            except Exception as e:
                console.print(f"[bold red]Error replaying {fpath}: {e}[/bold red]")

    # Sort results by filename or size
    results.sort(key=lambda x: x["size_mb"], reverse=True)

    table = Table(
        title="Stock_Microstructure_Alpha Performance Matrix across Large HYPE Sessions",
        header_style="bold magenta",
        show_header=True,
    )
    table.add_column("Session File", justify="left", style="dim")
    table.add_column("Size", justify="right")
    table.add_column("Trades", justify="right")
    table.add_column("Win %", justify="right")
    table.add_column("Profit Fac", justify="right")
    table.add_column("TP", justify="right")
    table.add_column("Trail", justify="right")
    table.add_column("StopLoss", justify="right")
    table.add_column("TimeLim", justify="right")
    table.add_column("Gross ($)", justify="right")
    table.add_column("Fees ($)", justify="right")
    table.add_column("Net ($)", justify="right", style="bold")
    table.add_column("Avg Ret (bps)", justify="right")

    tot_trades = 0
    tot_wins = 0
    tot_losses = 0
    tot_gross = 0.0
    tot_fees = 0.0
    tot_net = 0.0
    tot_gross_wins = 0.0
    tot_gross_losses = 0.0
    tot_exit_counts = Counter()
    all_ret_bps = []

    for r in results:
        trd = r["total_trades"]
        wr = r["win_rate_pct"]
        pf = r["profit_factor"]
        gross = r["gross_pnl"]
        fees = r["fees"]
        net = r["net_pnl"]
        avg_ret = r["avg_return_bps"]
        exits = r["exit_counts"]

        tot_trades += trd
        tot_wins += r["wins"]
        tot_losses += r["losses"]
        tot_gross += gross
        tot_fees += fees
        tot_net += net
        all_ret_bps.extend([t["return_bps"] for t in r["trades"]])

        for k, v in exits.items():
            tot_exit_counts[k] += v

        for t in r["trades"]:
            if t["gross_pnl"] > 0:
                tot_gross_wins += t["gross_pnl"]
            elif t["gross_pnl"] < 0:
                tot_gross_losses += abs(t["gross_pnl"])

        net_style = "green" if net > 0 else ("red" if net < 0 else "white")
        pf_str = f"{pf:.2f}" if pf < 90 else "Inf"

        table.add_row(
            r["filename"],
            f"{r['size_mb']:.1f} MB",
            str(trd),
            f"{wr:.1f}%" if trd > 0 else "-",
            pf_str if trd > 0 else "-",
            str(exits.get("TAKE_PROFIT", 0)),
            str(exits.get("TRAILING_STOP", 0)),
            str(exits.get("STOP_LOSS", 0)),
            str(exits.get("TIME_LIMIT", 0)),
            f"${gross:+6.2f}",
            f"${fees:6.2f}",
            f"[{net_style}]${net:+6.2f}[/{net_style}]",
            f"{avg_ret:+5.1f}" if trd > 0 else "-",
        )

    console.print("\n")
    console.print(table)

    total_elapsed = time.time() - t_start
    overall_wr = (tot_wins / tot_trades * 100.0) if tot_trades > 0 else 0.0
    overall_pf = (tot_gross_wins / tot_gross_losses) if tot_gross_losses > 0 else (99.9 if tot_gross_wins > 0 else 0.0)
    overall_avg_ret = (sum(all_ret_bps) / len(all_ret_bps)) if all_ret_bps else 0.0

    console.print("\n[bold cyan]===============================================================================[/bold cyan]")
    console.print("[bold green]EXECUTIVE PERFORMANCE AUDIT SUMMARY[/bold green]")
    console.print("[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"Total Datasets Processed:   [bold white]{len(results)}[/bold white] ({total_mb:.1f} MB in {total_elapsed:.1f}s)")
    console.print(f"Total Trades Executed:      [bold white]{tot_trades}[/bold white]")
    console.print(f"Win / Loss Record:          [bold green]{tot_wins} Wins[/bold green] / [bold red]{tot_losses} Losses[/bold red] / [bold yellow]{tot_trades - tot_wins - tot_losses} Evens[/bold yellow]")
    console.print(f"Overall Win Rate:           [bold {'green' if overall_wr >= 50 else 'red'}]{overall_wr:.2f}%[/bold {'green' if overall_wr >= 50 else 'red'}]")
    console.print(f"Overall Profit Factor:      [bold {'green' if overall_pf >= 1.2 else 'red'}]{overall_pf:.2f}[/bold {'green' if overall_pf >= 1.2 else 'red'}]")
    console.print(f"Cumulative Gross PnL:       [bold {'green' if tot_gross > 0 else 'red'}]${tot_gross:+9.2f}[/bold {'green' if tot_gross > 0 else 'red'}]")
    console.print(f"Cumulative Exchange Fees:   [bold yellow]${tot_fees:9.2f}[/bold yellow] (Maker: 1.5 bps, Taker: 4.5 bps)")
    console.print(f"Cumulative Net PnL:         [bold {'green' if tot_net > 0 else 'red'}]${tot_net:+9.2f}[/bold {'green' if tot_net > 0 else 'red'}]")
    console.print(f"Average Return per Trade:   [bold {'green' if overall_avg_ret > 0 else 'red'}]{overall_avg_ret:+6.2f} bps[/bold {'green' if overall_avg_ret > 0 else 'red'}]")
    console.print(f"Exit Distribution:          {dict(tot_exit_counts)}")

    # Save to JSON
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    summary_data = {
        "strategy": "Stock_Microstructure_Alpha",
        "market": "HYPE",
        "min_size_mb": args.min_size_mb,
        "total_datasets": len(results),
        "total_size_mb": round(total_mb, 2),
        "elapsed_seconds": round(total_elapsed, 2),
        "total_trades": tot_trades,
        "wins": tot_wins,
        "losses": tot_losses,
        "win_rate_pct": round(overall_wr, 2),
        "profit_factor": round(overall_pf, 2),
        "cumulative_gross_pnl_usd": round(tot_gross, 4),
        "cumulative_fees_usd": round(tot_fees, 4),
        "cumulative_net_pnl_usd": round(tot_net, 4),
        "avg_return_bps": round(overall_avg_ret, 2),
        "exit_distribution": dict(tot_exit_counts),
        "session_results": [
            {
                "filename": r["filename"],
                "size_mb": round(r["size_mb"], 2),
                "trades": r["total_trades"],
                "wins": r["wins"],
                "losses": r["losses"],
                "win_rate_pct": round(r["win_rate_pct"], 2),
                "profit_factor": round(r["profit_factor"], 2),
                "gross_pnl": round(r["gross_pnl"], 4),
                "fees": round(r["fees"], 4),
                "net_pnl": round(r["net_pnl"], 4),
                "avg_return_bps": round(r["avg_return_bps"], 2),
                "exit_counts": r["exit_counts"],
            }
            for r in results
        ],
    }

    with open(args.out, "w") as f:
        json.dump(summary_data, f, indent=2)

    console.print(f"\n[bold dim]Audit summary JSON written to: {args.out}[/bold dim]")


if __name__ == "__main__":
    main()
