"""Replay testing adjusted signals and fine-tuned ML model across the largest live sessions."""

import glob
import os
import sys
import time
from typing import Any, Dict, List

from rich.console import Console
from rich.table import Table

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


def run_large_sessions_replay():
    console = Console()
    data_dir = os.path.join("data", "btc") if os.path.isdir(os.path.join("data", "btc")) else "data"

    # Select the largest live session files
    candidate_files = sorted(
        glob.glob(os.path.join(data_dir, "hl_btc_l2_2026100*.jsonl")),
        key=os.path.getsize,
        reverse=True,
    )
    # Pick the top 6 largest sessions
    large_files = candidate_files[:6]

    console.print("\n[bold cyan]===============================================================================[/bold cyan]")
    console.print("[bold green]REPLAY TEST: Adjusted Signals & Fine-Tuned ML Model on Largest Live Sessions[/bold green]")
    console.print("[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"Total Large Sessions Selected: [bold yellow]{len(large_files)} files[/bold yellow]\n")

    cfg = AppConfig()
    cfg.strategies = StrategiesConfig.load("strategies.json")

    results_table = Table(
        title="Replay Performance Matrix Across Largest Live Recording Sessions",
        header_style="bold magenta",
        show_header=True,
    )
    results_table.add_column("Session File", justify="left", style="dim")
    results_table.add_column("Size", justify="right")
    results_table.add_column("HC Trd", justify="right")
    results_table.add_column("HC Win%", justify="right")
    results_table.add_column("HC Net PnL", justify="right")
    results_table.add_column("CC Trd", justify="right")
    results_table.add_column("CC Win%", justify="right")
    results_table.add_column("CC Net PnL", justify="right")
    results_table.add_column("ME Trd", justify="right")
    results_table.add_column("ME Win%", justify="right")
    results_table.add_column("ME Net PnL", justify="right")
    results_table.add_column("Total Net ($)", justify="right", style="bold")

    totals = {
        "hc_trades": 0, "hc_wins": 0, "hc_net": 0.0, "hc_fees": 0.0,
        "cc_trades": 0, "cc_wins": 0, "cc_net": 0.0, "cc_fees": 0.0,
        "me_trades": 0, "me_wins": 0, "me_net": 0.0, "me_fees": 0.0,
    }

    # Sort files chronologically for replay
    large_files.sort(key=lambda x: os.path.basename(x))

    for filepath in large_files:
        filename = os.path.basename(filepath)
        size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)

        runner = L2EngineRunner(config=cfg, record_data=False)
        replay = L2ReplayEngine(filepath, speed_multiplier=5000.0)

        last_eval_ms = 0
        eval_interval_ms = int(1000 / max(cfg.sample_rate_hz, 1))

        t0 = time.time()
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

        elapsed = time.time() - t0

        # Stats for Hedged_Convexity
        hc_state = runner.evaluator.strategies.get("Hedged_Convexity")
        hc_trades = hc_state.trades if hc_state else []
        hc_n = len(hc_trades)
        hc_w = sum(1 for t in hc_trades if t.net_pnl_usd > 0)
        hc_win = (hc_w / hc_n * 100.0) if hc_n > 0 else 0.0
        hc_net = sum(t.net_pnl_usd for t in hc_trades)

        # Stats for Convexity_Cascade
        cc_state = runner.evaluator.strategies.get("Convexity_Cascade")
        cc_trades = cc_state.trades if cc_state else []
        cc_n = len(cc_trades)
        cc_w = sum(1 for t in cc_trades if t.net_pnl_usd > 0)
        cc_win = (cc_w / cc_n * 100.0) if cc_n > 0 else 0.0
        cc_net = sum(t.net_pnl_usd for t in cc_trades)

        # Stats for Momentum_Expansion
        me_state = runner.evaluator.strategies.get("Momentum_Expansion")
        me_trades = me_state.trades if me_state else []
        me_n = len(me_trades)
        me_w = sum(1 for t in me_trades if t.net_pnl_usd > 0)
        me_win = (me_w / me_n * 100.0) if me_n > 0 else 0.0
        me_net = sum(t.net_pnl_usd for t in me_trades)

        total_file_net = hc_net + cc_net + me_net

        totals["hc_trades"] += hc_n
        totals["hc_wins"] += hc_w
        totals["hc_net"] += hc_net

        totals["cc_trades"] += cc_n
        totals["cc_wins"] += cc_w
        totals["cc_net"] += cc_net

        totals["me_trades"] += me_n
        totals["me_wins"] += me_w
        totals["me_net"] += me_net

        c_hc = "green" if hc_net > 0 else ("red" if hc_net < 0 else "dim")
        c_cc = "green" if cc_net > 0 else ("red" if cc_net < 0 else "dim")
        c_me = "green" if me_net > 0 else ("red" if me_net < 0 else "dim")
        c_tot = "bold green" if total_file_net > 0 else ("bold red" if total_file_net < 0 else "dim")

        results_table.add_row(
            filename,
            f"{size_mb:.1f} MB",
            str(hc_n),
            f"{hc_win:.0f}%",
            f"[{c_hc}]${hc_net:+.2f}[/{c_hc}]",
            str(cc_n),
            f"{cc_win:.0f}%",
            f"[{c_cc}]${cc_net:+.2f}[/{c_cc}]",
            str(me_n),
            f"{me_win:.0f}%",
            f"[{c_me}]${me_net:+.2f}[/{c_me}]",
            f"[{c_tot}]${total_file_net:+.2f}[/{c_tot}]",
        )
        console.print(f"✓ Completed {filename} in {elapsed:.1f}s | Net: ${total_file_net:+.2f}")

    console.print("\n")
    console.print(results_table)

    # Summary table
    summary_table = Table(title="Aggregate Strategy Results Across Large Sessions", header_style="bold cyan")
    summary_table.add_column("Strategy", justify="left")
    summary_table.add_column("Trades", justify="right")
    summary_table.add_column("Win Rate", justify="right")
    summary_table.add_column("Total Net PnL ($)", justify="right")
    summary_table.add_column("Avg PnL / Trade", justify="right")

    for name, pfx in [("Hedged_Convexity", "hc"), ("Convexity_Cascade", "cc"), ("Momentum_Expansion", "me")]:
        n = totals[f"{pfx}_trades"]
        w = totals[f"{pfx}_wins"]
        win_rate = (w / n * 100.0) if n > 0 else 0.0
        net = totals[f"{pfx}_net"]
        avg = (net / n) if n > 0 else 0.0
        c = "bold green" if net > 0 else "bold red"
        summary_table.add_row(
            name,
            str(n),
            f"{win_rate:.1f}%",
            f"[{c}]${net:+.2f}[/{c}]",
            f"[{c}]${avg:+.2f}[/{c}]",
        )

    all_trd = totals["hc_trades"] + totals["cc_trades"] + totals["me_trades"]
    all_win = totals["hc_wins"] + totals["cc_wins"] + totals["me_wins"]
    all_rate = (all_win / all_trd * 100.0) if all_trd > 0 else 0.0
    all_net = totals["hc_net"] + totals["cc_net"] + totals["me_net"]
    all_c = "bold green" if all_net > 0 else "bold red"

    summary_table.add_section()
    summary_table.add_row(
        "[bold]COMBINED PORTFOLIO[/bold]",
        f"[bold]{all_trd}[/bold]",
        f"[bold]{all_rate:.1f}%[/bold]",
        f"[{all_c}]${all_net:+.2f}[/{all_c}]",
        f"[{all_c}]${(all_net/all_trd if all_trd>0 else 0):+.2f}[/{all_c}]",
    )

    console.print(summary_table)


if __name__ == "__main__":
    run_large_sessions_replay()
