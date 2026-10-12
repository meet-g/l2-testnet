"""High-Throughput Parallel Replay Evaluation across ALL BTC L2 recording sessions.

Evaluates Hedged_Convexity, Convexity_Cascade, and Momentum_Expansion across all
101 BTC datasets in data/ using multiprocessing for maximum speed on multi-core CPU.
"""

import glob
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rich.console import Console
from rich.table import Table

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


def replay_single_file(filepath: str) -> Dict[str, Any]:
    """Worker function: Replays a single BTC JSONL dataset and returns detailed metrics."""
    filename = os.path.basename(filepath)
    size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)

    cfg = AppConfig()
    cfg.strategies = StrategiesConfig.load("strategies.json")

    runner = L2EngineRunner(config=cfg, record_data=False)
    replay = L2ReplayEngine(filepath, speed_multiplier=5000.0)

    last_eval_ms = 0
    eval_interval_ms = int(1000 / max(cfg.sample_rate_hz, 1))

    t0 = time.time()
    events_count = 0

    try:
        for event in replay.stream_events():
            events_count += 1
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

    except Exception as e:
        return {
            "filename": filename,
            "filepath": filepath,
            "size_mb": size_mb,
            "events_count": events_count,
            "elapsed_s": time.time() - t0,
            "error": str(e),
            "strategies": {},
            "all_trades": [],
        }

    elapsed_s = time.time() - t0
    strat_results = {}
    all_trades_list = []

    for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
        st = runner.evaluator.strategies.get(s_name)
        trades = st.trades if st else []
        n = len(trades)
        wins = [t for t in trades if t.net_pnl_usd > 0]
        losses = [t for t in trades if t.net_pnl_usd < 0]

        gross_pnl = sum(t.gross_pnl_usd for t in trades)
        fees = sum(t.fees_usd for t in trades)
        net_pnl = sum(t.net_pnl_usd for t in trades)
        gross_wins = sum(t.gross_pnl_usd for t in wins)
        gross_losses = abs(sum(t.gross_pnl_usd for t in losses))

        strat_results[s_name] = {
            "trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "gross_pnl": gross_pnl,
            "fees": fees,
            "net_pnl": net_pnl,
            "gross_wins": gross_wins,
            "gross_losses": gross_losses,
            "profit_factor": (gross_wins / gross_losses) if gross_losses > 0 else (99.0 if gross_wins > 0 else 0.0),
        }

        for t in trades:
            all_trades_list.append({
                "strategy": s_name,
                "file": filename,
                "side": t.side,
                "entry_time_ms": t.entry_time_ms,
                "exit_time_ms": t.exit_time_ms,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "gross_pnl": t.gross_pnl_usd,
                "fees": t.fees_usd,
                "net_pnl": t.net_pnl_usd,
                "return_bps": t.return_bps,
                "exit_reason": t.exit_reason,
            })

    return {
        "filename": filename,
        "filepath": filepath,
        "size_mb": size_mb,
        "events_count": events_count,
        "elapsed_s": elapsed_s,
        "error": None,
        "strategies": strat_results,
        "all_trades": all_trades_list,
    }


def main():
    console = Console()
    data_dir = os.path.join("data", "btc") if os.path.isdir(os.path.join("data", "btc")) else "data"
    all_files = sorted(glob.glob(os.path.join(data_dir, "hl_btc_l2_*.jsonl")))

    if not all_files:
        console.print("[bold red]No BTC L2 recording files found in data/![/bold red]")
        return

    total_mb = sum(os.path.getsize(f) for f in all_files) / (1024.0 * 1024.0)
    workers = min(8, os.cpu_count() or 4)

    console.print("\n[bold cyan]===============================================================================[/bold cyan]")
    console.print("[bold green]FULL PORTFOLIO REPLAY: All BTC Data Recordings (101 Files / 447 MB)[/bold green]")
    console.print("[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"Target Datasets:  [bold yellow]{len(all_files)} files[/bold yellow] ({total_mb:.1f} MB)")
    console.print(f"Parallel Workers: [bold yellow]{workers} processes[/bold yellow] (12-core CPU)")
    console.print(f"Strategies:       [bold yellow]Hedged_Convexity, Convexity_Cascade, Momentum_Expansion[/bold yellow]\n")

    start_time = time.time()
    results = []

    # Run in parallel using ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_file = {executor.submit(replay_single_file, f): f for f in all_files}
        completed = 0
        running_net = 0.0
        running_trades = 0

        for future in as_completed(future_to_file):
            fpath = future_to_file[future]
            completed += 1
            try:
                res = future.result()
                results.append(res)

                if res.get("error"):
                    console.print(f"[{completed:3d}/{len(all_files):3d}] [bold red]Error in {res['filename']}: {res['error']}[/bold red]")
                else:
                    file_net = sum(s["net_pnl"] for s in res["strategies"].values())
                    file_trd = sum(s["trades"] for s in res["strategies"].values())
                    running_net += file_net
                    running_trades += file_trd
                    c = "green" if file_net > 0 else ("red" if file_net < 0 else "dim")
                    console.print(
                        f"[{completed:3d}/{len(all_files):3d}] ✓ {res['filename']:<32} "
                        f"({res['size_mb']:4.1f} MB in {res['elapsed_s']:4.1f}s) | "
                        f"Trd: {file_trd:2d} | Net: [{c}]${file_net:+6.2f}[/{c}] | "
                        f"Cumul: [bold {'green' if running_net >= 0 else 'red'}]${running_net:+7.2f}[/bold {'green' if running_net >= 0 else 'red'}]"
                    )
            except Exception as exc:
                console.print(f"[{completed:3d}/{len(all_files):3d}] [bold red]Exception for {os.path.basename(fpath)}: {exc}[/bold red]")

    total_duration = time.time() - start_time

    # Sort results chronologically by filename
    results.sort(key=lambda x: x["filename"])

    # Aggregate Portfolio Metrics
    totals = {
        "Hedged_Convexity": {"trades": 0, "wins": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "gw": 0.0, "gl": 0.0},
        "Convexity_Cascade": {"trades": 0, "wins": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "gw": 0.0, "gl": 0.0},
        "Momentum_Expansion": {"trades": 0, "wins": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "gw": 0.0, "gl": 0.0},
    }

    all_trades = []
    exit_reasons = {}

    for r in results:
        if r.get("error"):
            continue
        for s_name, s_data in r["strategies"].items():
            t = totals[s_name]
            t["trades"] += s_data["trades"]
            t["wins"] += s_data["wins"]
            t["gross_pnl"] += s_data["gross_pnl"]
            t["fees"] += s_data["fees"]
            t["net_pnl"] += s_data["net_pnl"]
            t["gw"] += s_data["gross_wins"]
            t["gl"] += s_data["gross_losses"]

        for tr in r.get("all_trades", []):
            all_trades.append(tr)
            reason = tr["exit_reason"]
            exit_reasons.setdefault(reason, []).append(tr)

    # Print Summary Tables
    console.print("\n")
    summary_table = Table(
        title=f"Full Portfolio Performance Across All {len(all_files)} BTC Sessions ({total_duration:.1f}s Replay)",
        header_style="bold cyan",
        show_header=True,
    )
    summary_table.add_column("Strategy", justify="left")
    summary_table.add_column("Trades", justify="right")
    summary_table.add_column("Win Rate", justify="right")
    summary_table.add_column("Gross PnL ($)", justify="right")
    summary_table.add_column("Fees ($)", justify="right")
    summary_table.add_column("Net PnL ($)", justify="right")
    summary_table.add_column("Profit Factor", justify="right")
    summary_table.add_column("Avg PnL / Trd", justify="right")

    comb_trades = 0
    comb_wins = 0
    comb_gross = 0.0
    comb_fees = 0.0
    comb_net = 0.0
    comb_gw = 0.0
    comb_gl = 0.0

    for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
        t = totals[s_name]
        n = t["trades"]
        w = t["wins"]
        win_rate = (w / n * 100.0) if n > 0 else 0.0
        pf = (t["gw"] / t["gl"]) if t["gl"] > 0 else (99.0 if t["gw"] > 0 else 0.0)
        avg_pnl = (t["net_pnl"] / n) if n > 0 else 0.0
        c = "bold green" if t["net_pnl"] > 0 else "bold red"

        summary_table.add_row(
            s_name,
            str(n),
            f"{win_rate:.1f}%",
            f"${t['gross_pnl']:+8.2f}",
            f"-${t['fees']:7.2f}",
            f"[{c}]${t['net_pnl']:+8.2f}[/{c}]",
            f"{pf:.2f}",
            f"[{c}]${avg_pnl:+.2f}[/{c}]",
        )

        comb_trades += n
        comb_wins += w
        comb_gross += t["gross_pnl"]
        comb_fees += t["fees"]
        comb_net += t["net_pnl"]
        comb_gw += t["gw"]
        comb_gl += t["gl"]

    comb_win_rate = (comb_wins / comb_trades * 100.0) if comb_trades > 0 else 0.0
    comb_pf = (comb_gw / comb_gl) if comb_gl > 0 else (99.0 if comb_gw > 0 else 0.0)
    comb_avg = (comb_net / comb_trades) if comb_trades > 0 else 0.0
    comb_c = "bold green" if comb_net > 0 else "bold red"

    summary_table.add_section()
    summary_table.add_row(
        "[bold]COMBINED PORTFOLIO[/bold]",
        f"[bold]{comb_trades}[/bold]",
        f"[bold]{comb_win_rate:.1f}%[/bold]",
        f"[bold]${comb_gross:+8.2f}[/bold]",
        f"[bold]-${comb_fees:7.2f}[/bold]",
        f"[{comb_c}]${comb_net:+8.2f}[/{comb_c}]",
        f"[bold]{comb_pf:.2f}[/bold]",
        f"[{comb_c}]${comb_avg:+.2f}[/{comb_c}]",
    )
    console.print(summary_table)

    # Exit Reason Diagnostics Table
    console.print("\n")
    exit_table = Table(
        title="Exit Reason Attribution & Failure Mechanism Diagnostic Across All BTC Data",
        header_style="bold magenta",
        show_header=True,
    )
    exit_table.add_column("Exit Reason", justify="left")
    exit_table.add_column("Trades", justify="right")
    exit_table.add_column("Win Rate", justify="right")
    exit_table.add_column("Gross PnL ($)", justify="right")
    exit_table.add_column("Fees ($)", justify="right")
    exit_table.add_column("Net PnL ($)", justify="right")
    exit_table.add_column("Avg Ret (bps)", justify="right")

    for r_name, t_list in sorted(exit_reasons.items(), key=lambda x: sum(t['net_pnl'] for t in x[1]), reverse=True):
        rn = len(t_list)
        rw = sum(1 for t in t_list if t["net_pnl"] > 0)
        r_win_rate = (rw / rn * 100.0) if rn > 0 else 0.0
        r_gross = sum(t["gross_pnl"] for t in t_list)
        r_fees = sum(t["fees"] for t in t_list)
        r_net = sum(t["net_pnl"] for t in t_list)
        r_ret = sum(t["return_bps"] for t in t_list) / rn if rn > 0 else 0.0
        rc = "green" if r_net > 0 else "red"

        exit_table.add_row(
            r_name,
            str(rn),
            f"{r_win_rate:.1f}%",
            f"${r_gross:+8.2f}",
            f"-${r_fees:7.2f}",
            f"[{rc}]${r_net:+8.2f}[/{rc}]",
            f"{r_ret:+.2f} bps",
        )

    console.print(exit_table)

    # Save comprehensive results to audits directory
    out_dir = "audits/full_dataset_replay"
    os.makedirs(out_dir, exist_ok=True)
    summary_path = os.path.join(out_dir, "btc_full_replay_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_files": len(all_files),
            "total_mb": total_mb,
            "duration_s": total_duration,
            "combined_trades": comb_trades,
            "combined_win_rate": comb_win_rate,
            "combined_gross_pnl": comb_gross,
            "combined_fees": comb_fees,
            "combined_net_pnl": comb_net,
            "combined_profit_factor": comb_pf,
            "strategy_breakdown": totals,
            "exit_reason_breakdown": {
                r: {
                    "count": len(t_list),
                    "win_rate": sum(1 for t in t_list if t["net_pnl"] > 0) / len(t_list),
                    "net_pnl": sum(t["net_pnl"] for t in t_list),
                    "gross_pnl": sum(t["gross_pnl"] for t in t_list),
                    "fees": sum(t["fees"] for t in t_list),
                } for r, t_list in exit_reasons.items()
            },
        }, f, indent=2)

    console.print(f"\n[bold green]✓ Replay complete. Full summary saved to {summary_path}[/bold green]\n")


if __name__ == "__main__":
    main()
