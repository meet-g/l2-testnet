"""Replay evaluation of tuned strategies against the completed 40.5-hour live session (session_20261002_012102).

Benchmarks the adjusted alpha signals, fine-tuned ML model, macro trend shield,
and trailing stop logic against the exact 40 raw data files (225.3 MB) recorded
during the recent extended live session, comparing before vs after.
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
    """Worker function: Replays a single session file and returns trade outcomes."""
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

    # Select the exact files corresponding to session_20261002_012102 (from Oct 2 01:00 to Oct 3 17:00)
    all_oct2 = sorted(glob.glob(os.path.join(data_dir, "hl_btc_l2_20261002_*.jsonl")))
    all_oct3 = sorted(glob.glob(os.path.join(data_dir, "hl_btc_l2_20261003_*.jsonl")))
    session_files = [f for f in (all_oct2 + all_oct3) if not f.endswith("1800.jsonl")]

    total_mb = sum(os.path.getsize(f) for f in session_files) / (1024.0 * 1024.0)
    workers = min(8, os.cpu_count() or 4)

    console.print("\n[bold cyan]===============================================================================[/bold cyan]")
    console.print("[bold green]REPLAY TEST: Benchmark Against Recent 40.5-Hour Live Session (session_20261002_012102)[/bold green]")
    console.print("[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"Target Session:   [bold yellow]session_20261002_012102[/bold yellow] (2026-10-02 01:21:02 to 2026-10-03 17:48:30)")
    console.print(f"Dataset Files:    [bold yellow]{len(session_files)} hourly files[/bold yellow] ({total_mb:.1f} MB)")
    console.print(f"Parallel Workers: [bold yellow]{workers} processes[/bold yellow] (12-core CPU)")
    console.print(f"Original Live:    [dim]271 trades | Win: 48.0% | Gross: +$571.39 | Net: -$142.80 | PF: 0.80[/dim]\n")

    start_time = time.time()
    results = []

    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_file = {executor.submit(replay_single_file, f): f for f in session_files}
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
                    console.print(f"[{completed:2d}/{len(session_files):2d}] [bold red]Error in {res['filename']}: {res['error']}[/bold red]")
                else:
                    file_net = sum(s["net_pnl"] for s in res["strategies"].values())
                    file_trd = sum(s["trades"] for s in res["strategies"].values())
                    running_net += file_net
                    running_trades += file_trd
                    c = "green" if file_net > 0 else ("red" if file_net < 0 else "dim")
                    console.print(
                        f"[{completed:2d}/{len(session_files):2d}] ✓ {res['filename']:<32} "
                        f"({res['size_mb']:4.1f} MB in {res['elapsed_s']:4.1f}s) | "
                        f"Trd: {file_trd:2d} | Net: [{c}]${file_net:+6.2f}[/{c}] | "
                        f"Cumul: [bold {'green' if running_net >= 0 else 'red'}]${running_net:+7.2f}[/bold {'green' if running_net >= 0 else 'red'}]"
                    )
            except Exception as exc:
                console.print(f"[{completed:2d}/{len(session_files):2d}] [bold red]Exception for {os.path.basename(fpath)}: {exc}[/bold red]")

    total_duration = time.time() - start_time
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

    comb_trades = sum(t["trades"] for t in totals.values())
    comb_wins = sum(t["wins"] for t in totals.values())
    comb_gross = sum(t["gross_pnl"] for t in totals.values())
    comb_fees = sum(t["fees"] for t in totals.values())
    comb_net = sum(t["net_pnl"] for t in totals.values())
    comb_gw = sum(t["gw"] for t in totals.values())
    comb_gl = sum(t["gl"] for t in totals.values())
    comb_win_rate = (comb_wins / comb_trades * 100.0) if comb_trades > 0 else 0.0
    comb_pf = (comb_gw / comb_gl) if comb_gl > 0 else (99.0 if comb_gw > 0 else 0.0)

    # Strategy Results Table
    console.print("\n")
    strat_table = Table(
        title=f"Replay Results Across Session session_20261002_012102 ({total_duration:.1f}s Replay)",
        header_style="bold cyan",
        show_header=True,
    )
    strat_table.add_column("Strategy", justify="left")
    strat_table.add_column("Trades", justify="right")
    strat_table.add_column("Win Rate", justify="right")
    strat_table.add_column("Gross PnL ($)", justify="right")
    strat_table.add_column("Fees ($)", justify="right")
    strat_table.add_column("Net PnL ($)", justify="right")
    strat_table.add_column("Profit Factor", justify="right")
    strat_table.add_column("Avg PnL / Trd", justify="right")

    for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
        t = totals[s_name]
        n = t["trades"]
        w = t["wins"]
        win_rate = (w / n * 100.0) if n > 0 else 0.0
        pf = (t["gw"] / t["gl"]) if t["gl"] > 0 else (99.0 if t["gw"] > 0 else 0.0)
        avg_pnl = (t["net_pnl"] / n) if n > 0 else 0.0
        c = "bold green" if t["net_pnl"] > 0 else "bold red"

        strat_table.add_row(
            s_name,
            str(n),
            f"{win_rate:.1f}%",
            f"${t['gross_pnl']:+8.2f}",
            f"-${t['fees']:7.2f}",
            f"[{c}]${t['net_pnl']:+8.2f}[/{c}]",
            f"{pf:.2f}",
            f"[{c}]${avg_pnl:+.2f}[/{c}]",
        )

    comb_c = "bold green" if comb_net > 0 else "bold red"
    strat_table.add_section()
    strat_table.add_row(
        "[bold]COMBINED REPLAY[/bold]",
        f"[bold]{comb_trades}[/bold]",
        f"[bold]{comb_win_rate:.1f}%[/bold]",
        f"[bold]${comb_gross:+8.2f}[/bold]",
        f"[bold]-${comb_fees:7.2f}[/bold]",
        f"[{comb_c}]${comb_net:+8.2f}[/{comb_c}]",
        f"[bold]{comb_pf:.2f}[/bold]",
        f"[{comb_c}]${(comb_net/comb_trades if comb_trades>0 else 0):+.2f}[/{comb_c}]",
    )
    console.print(strat_table)

    # Before vs After Comparison Table
    console.print("\n")
    comp_table = Table(
        title="Direct Comparison: Original Live Session Run vs Tuned Replay Run",
        header_style="bold magenta",
        show_header=True,
    )
    comp_table.add_column("Metric", justify="left")
    comp_table.add_column("Original Live Run (Un-tuned)", justify="right", style="red")
    comp_table.add_column("Tuned Strategies Replay", justify="right", style="green")
    comp_table.add_column("Improvement (Delta)", justify="right", style="bold cyan")

    # Original live stats from session_manifest.json
    orig_trades = 271
    orig_win_rate = 48.0
    orig_gross = 571.39
    orig_fees = 714.18
    orig_net = -142.80
    orig_pf = 0.80

    comp_table.add_row("Total Trades", str(orig_trades), str(comb_trades), f"{comb_trades - orig_trades:+d}")
    comp_table.add_row("Win Rate", f"{orig_win_rate:.1f}%", f"{comb_win_rate:.1f}%", f"{comb_win_rate - orig_win_rate:+.1f}%")
    comp_table.add_row("Gross PnL ($)", f"${orig_gross:+8.2f}", f"${comb_gross:+8.2f}", f"${comb_gross - orig_gross:+8.2f}")
    comp_table.add_row("Fees Incurred ($)", f"-${orig_fees:7.2f}", f"-${comb_fees:7.2f}", f"${orig_fees - comb_fees:+8.2f}")
    comp_table.add_row("Net PnL ($)", f"${orig_net:+8.2f}", f"${comb_net:+8.2f}", f"${comb_net - orig_net:+8.2f}")
    comp_table.add_row("Gross Profit Factor", f"{orig_pf:.2f}", f"{comb_pf:.2f}", f"{comb_pf - orig_pf:+.2f}")

    console.print(comp_table)

    # Exit Reason Diagnostics Table
    console.print("\n")
    exit_table = Table(
        title="Exit Reason Breakdown on session_20261002_012102",
        header_style="bold yellow",
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

    # Save summary
    out_dir = "audits/session_20261002_012102_replay"
    os.makedirs(out_dir, exist_ok=True)
    summary_path = os.path.join(out_dir, "recent_session_replay_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "session_id": "session_20261002_012102",
            "files_count": len(session_files),
            "total_mb": total_mb,
            "duration_s": total_duration,
            "orig_live": {
                "trades": orig_trades,
                "win_rate": orig_win_rate,
                "gross_pnl": orig_gross,
                "fees": orig_fees,
                "net_pnl": orig_net,
                "profit_factor": orig_pf,
            },
            "tuned_replay": {
                "trades": comb_trades,
                "win_rate": comb_win_rate,
                "gross_pnl": comb_gross,
                "fees": comb_fees,
                "net_pnl": comb_net,
                "profit_factor": comb_pf,
            },
            "strategy_breakdown": totals,
            "exit_reasons": {
                r: {
                    "count": len(t_list),
                    "win_rate": sum(1 for t in t_list if t["net_pnl"] > 0) / len(t_list),
                    "net_pnl": sum(t["net_pnl"] for t in t_list),
                    "gross_pnl": sum(t["gross_pnl"] for t in t_list),
                    "fees": sum(t["fees"] for t in t_list),
                } for r, t_list in exit_reasons.items()
            },
        }, f, indent=2)

    console.print(f"\n[bold green]✓ Replay complete. Saved to {summary_path}[/bold green]\n")


if __name__ == "__main__":
    main()
