"""High-Throughput Parallel Replay Evaluation for MicroPrice_FastFill across ALL 560 HYPE Datasets.

Evaluates MicroPrice_FastFill across all recording sessions in data/hype/
using multiprocessing for maximum speed on multi-core CPU.
"""

import glob
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Dict, List

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rich.console import Console
from rich.table import Table

from config import MarketConfig, BacktestConfig, StrategiesConfig
from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.composite_alpha import CompositeAlphaSignal
from engine.backtester import EdgeEvaluator
from engine.data_collector import L2ReplayEngine


def replay_single_hype_file(filepath: str) -> Dict[str, Any]:
    """Worker function: Replays a single HYPE JSONL dataset and returns detailed metrics."""
    filename = os.path.basename(filepath)
    size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)

    m_cfg = MarketConfig(coin="HYPE")
    bt_cfg = BacktestConfig(capital_usd=10000.0, order_size_btc=95.0)
    strat_cfg = StrategiesConfig.load("strategies.json")
    mpff_def = strat_cfg.get_strategy("MicroPrice_FastFill")
    strat_params = {"MicroPrice_FastFill": mpff_def.__dict__ if mpff_def else {}}

    evaluator = EdgeEvaluator(
        market_cfg=m_cfg,
        bt_cfg=bt_cfg,
        strategy_defs={"MicroPrice_FastFill": ("MicroPrice", "MAKER")},
    )
    evaluator.strategy_params = strat_params

    book = OrderBook("HYPE")
    trades = TradeManager()
    alpha = CompositeAlphaSignal()

    last_eval_ms = 0
    t0 = time.time()
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
                sub_dict = res.metadata.get("sub_signals", {})
                sigs = {name: s.score for name, s in sub_dict.items()}
                confs = {name: getattr(s, "confidence", 1.0) for name, s in sub_dict.items()}
                mp_sig = sub_dict.get("MicroPrice")
                sigs["MicroPrice"] = mp_sig.score if mp_sig else 0.0
                confs["MicroPrice"] = mp_sig.confidence if mp_sig else 0.0
                evaluator.record_step(now_ms, book.mid_price, book.best_bid, book.best_ask, sigs, confidences=confs)

        if book.is_valid:
            now_ms = book.last_update_time_ms or int(time.time() * 1000)
            evaluator.close_open_positions(book.mid_price, now_ms, reason="SESSION_SHUTDOWN")

    except Exception as e:
        return {
            "filename": filename,
            "filepath": filepath,
            "size_mb": size_mb,
            "events_count": events_count,
            "elapsed_s": time.time() - t0,
            "error": str(e),
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "gross_pnl": 0.0,
            "fees": 0.0,
            "net_pnl": 0.0,
            "gross_wins": 0.0,
            "gross_losses": 0.0,
            "exits": {},
            "hold_secs": 0.0,
        }

    elapsed_s = time.time() - t0
    st = evaluator.strategies.get("MicroPrice_FastFill")
    trade_list = st.trades if st else []

    n = len(trade_list)
    wins = [t for t in trade_list if t.net_pnl_usd > 0]
    losses = [t for t in trade_list if t.net_pnl_usd < 0]

    gross_pnl = sum(t.gross_pnl_usd for t in trade_list)
    fees = sum(t.fees_usd for t in trade_list)
    net_pnl = sum(t.net_pnl_usd for t in trade_list)
    gross_wins = sum(t.gross_pnl_usd for t in wins)
    gross_losses = abs(sum(t.gross_pnl_usd for t in losses))

    exits = {}
    durations = []
    for t in trade_list:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1
        durations.append((t.exit_time_ms - t.entry_time_ms) / 1000.0)

    avg_hold = sum(durations) / len(durations) if durations else 0.0

    return {
        "filename": filename,
        "filepath": filepath,
        "size_mb": size_mb,
        "events_count": events_count,
        "elapsed_s": elapsed_s,
        "error": None,
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_pnl": net_pnl,
        "gross_wins": gross_wins,
        "gross_losses": gross_losses,
        "exits": exits,
        "hold_secs": avg_hold,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Parallel replay for MicroPrice_FastFill")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of files to replay")
    parser.add_argument("--workers", type=int, default=None, help="Number of worker processes")
    args = parser.parse_args()

    console = Console()
    data_dir = os.path.join("data", "hype")
    all_files = sorted(glob.glob(os.path.join(data_dir, "hl_hype_l2_*.jsonl")))

    # Filter out empty files (< 1000 bytes)
    valid_files = [f for f in all_files if os.path.getsize(f) > 1000]
    if args.limit:
        valid_files = valid_files[:args.limit]

    total_files = len(valid_files)
    total_mb = sum(os.path.getsize(f) for f in valid_files) / (1024.0 * 1024.0)
    workers = args.workers or min(os.cpu_count() or 8, 12)

    console.print("=" * 90)
    console.print(f"[bold green]PARALLEL REPLAY: MicroPrice_FastFill on {total_files} HYPE Datasets[/bold green]")
    console.print(f"Total Files: [bold yellow]{total_files}[/bold yellow] | Total Volume: [bold yellow]{total_mb:.1f} MB[/bold yellow] | CPU Workers: [bold yellow]{workers}[/bold yellow]")
    console.print("=" * 90)

    t_start = time.time()
    results = []
    completed_count = 0

    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(replay_single_hype_file, f): f for f in valid_files}

        for future in as_completed(future_map):
            completed_count += 1
            res = future.result()
            results.append(res)

            if completed_count % 25 == 0 or completed_count == total_files:
                pct = (completed_count / total_files) * 100.0
                elapsed = time.time() - t_start
                fps = completed_count / elapsed if elapsed > 0 else 0
                cum_trades = sum(r["trades"] for r in results)
                cum_pnl = sum(r["net_pnl"] for r in results)
                console.print(
                    f"[{completed_count:3d}/{total_files:3d}] ({pct:5.1f}%) | "
                    f"Trades: {cum_trades:5d} | Cum Net PnL: ${cum_pnl:+9.2f} | "
                    f"Speed: {fps:4.1f} files/s | Elapsed: {elapsed:5.1f}s"
                )

    total_time = time.time() - t_start
    console.print(f"\n[bold green]Replay completed across all {total_files} files in {total_time:.1f}s ({total_files/total_time:.1f} files/s)![/bold green]\n")

    # Aggregate overall metrics
    tot_trades = sum(r["trades"] for r in results)
    tot_wins = sum(r["wins"] for r in results)
    tot_losses = sum(r["losses"] for r in results)
    tot_gross = sum(r["gross_pnl"] for r in results)
    tot_fees = sum(r["fees"] for r in results)
    tot_net = sum(r["net_pnl"] for r in results)
    tot_gross_wins = sum(r["gross_wins"] for r in results)
    tot_gross_losses = sum(r["gross_losses"] for r in results)

    overall_win_rate = (tot_wins / tot_trades * 100.0) if tot_trades > 0 else 0.0
    overall_pf = (tot_gross_wins / tot_gross_losses) if tot_gross_losses > 0 else 0.0

    # Aggregate exit reasons
    exit_counts = {}
    for r in results:
        for reason, count in r["exits"].items():
            exit_counts[reason] = exit_counts.get(reason, 0) + count

    # Compute hold times
    all_holds = [r["hold_secs"] for r in results if r["trades"] > 0]
    avg_hold = sum(all_holds) / len(all_holds) if all_holds else 0.0

    # Print Summary Table
    table = Table(title="MicroPrice_FastFill Performance across ALL 560 HYPE Datasets", header_style="bold magenta")
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", justify="right")

    table.add_row("Total Files Evaluated", f"{total_files}")
    table.add_row("Total Events Processed", f"{sum(r['events_count'] for r in results):,}")
    table.add_row("Total Trades Executed", f"{tot_trades:,}")
    table.add_row("Win Rate (%)", f"{overall_win_rate:.1f}% ({tot_wins:,} W / {tot_losses:,} L)")
    table.add_row("Gross PnL ($)", f"${tot_gross:+,.2f}")
    table.add_row("Total Fees Paid ($)", f"${tot_fees:,.2f}")
    table.add_row("Net Realized PnL ($)", f"${tot_net:+,.2f}")
    table.add_row("Profit Factor (PF)", f"{overall_pf:.2f}")
    table.add_row("Average Holding Duration", f"{avg_hold:.1f}s")
    console.print(table)

    # Print Exits Table
    exit_table = Table(title="Exit Reason Breakdown (Defensive Hedges vs Take Profits vs Stops)", header_style="bold yellow")
    exit_table.add_column("Exit Reason", style="bold")
    exit_table.add_column("Count", justify="right")
    exit_table.add_column("Percentage", justify="right")

    for reason, count in sorted(exit_counts.items(), key=lambda x: x[1], reverse=True):
        pct = (count / max(tot_trades, 1)) * 100.0
        exit_table.add_row(reason, f"{count:,}", f"{pct:5.1f}%")

    console.print(exit_table)

    # Save results to JSON and CSV
    os.makedirs("reports", exist_ok=True)
    summary_path = "reports/hype_all_microprice_fastfill_summary.json"
    with open(summary_path, "w") as f:
        json.dump({
            "total_files": total_files,
            "total_trades": tot_trades,
            "win_rate_pct": overall_win_rate,
            "gross_pnl_usd": tot_gross,
            "fees_usd": tot_fees,
            "net_pnl_usd": tot_net,
            "profit_factor": overall_pf,
            "avg_holding_duration_secs": avg_hold,
            "exit_counts": exit_counts,
            "total_elapsed_secs": total_time,
        }, f, indent=2)

    console.print(f"[dim green]Saved comprehensive performance summary to {summary_path}[/dim green]")


if __name__ == "__main__":
    main()
