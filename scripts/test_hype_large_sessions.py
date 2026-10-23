"""High-Throughput Replay Evaluation across ALL Large HYPE Sessions.

Evaluates Convexity_Cascade and Momentum_Expansion across all large HYPE L2
recording sessions in data/hype/ to measure win rate, net PnL, profit factor,
and verify the reduction in stop-loss hits via defensive maker hedging.
"""

import glob
import os
import sys
import time
from typing import Any, Dict, List
from collections import Counter

from rich.console import Console
from rich.table import Table

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


def run_hype_large_sessions_backtest(min_size_mb: float = 8.0, max_files: int = 15):
    console = Console()
    data_dir = os.path.join("data", "hype")

    all_files = sorted(
        glob.glob(os.path.join(data_dir, "hl_hype_l2_*.jsonl")),
        key=os.path.getsize,
        reverse=True,
    )
    target_files = [f for f in all_files if os.path.getsize(f) >= min_size_mb * 1024 * 1024]
    if max_files > 0:
        target_files = target_files[:max_files]

    if not target_files:
        console.print(f"[bold red]No HYPE recording files found >= {min_size_mb} MB in {data_dir}![/bold red]")
        return

    console.print(f"\n[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"[bold green]HYPE REPLAY EVALUATION: Convexity_Cascade & Momentum_Expansion Edge Audit[/bold green]")
    console.print(f"[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"Target Datasets: [bold yellow]{len(target_files)} sessions[/bold yellow] (Min Size: {min_size_mb} MB)\n")

    cfg = AppConfig()
    cfg.market.coin = "HYPE"
    cfg.backtest.order_size_btc = 95.0  # ~$9,000 USD position
    cfg.strategies = StrategiesConfig.load("strategies.json")

    results_table = Table(
        title="Cross-Session Microstructure Alpha Performance Matrix (HYPE)",
        header_style="bold magenta",
        show_header=True,
    )
    results_table.add_column("Session File", justify="left", style="dim")
    results_table.add_column("Size", justify="right")
    results_table.add_column("CC Trd", justify="right")
    results_table.add_column("CC Win%", justify="right")
    results_table.add_column("CC Stops", justify="right")
    results_table.add_column("CC Net ($)", justify="right")
    results_table.add_column("ME Trd", justify="right")
    results_table.add_column("ME Win%", justify="right")
    results_table.add_column("ME Stops", justify="right")
    results_table.add_column("ME Net ($)", justify="right")
    results_table.add_column("Total Net ($)", justify="right", style="bold")

    cc_all_trades = 0
    cc_all_wins = 0
    cc_all_stops = 0
    cc_all_hedges = 0
    cc_all_gross_pnl = 0.0
    cc_all_fees = 0.0
    cc_all_net_pnl = 0.0

    me_all_trades = 0
    me_all_wins = 0
    me_all_stops = 0
    me_all_hedges = 0
    me_all_gross_pnl = 0.0
    me_all_fees = 0.0
    me_all_net_pnl = 0.0

    t_start = time.time()

    for idx, filepath in enumerate(target_files, start=1):
        filename = os.path.basename(filepath)
        size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)

        runner = L2EngineRunner(config=cfg, record_data=False, enable_audit=False)
        replay = L2ReplayEngine(filepath, speed_multiplier=100000.0)

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

        st_cc = runner.evaluator.strategies.get("Convexity_Cascade")
        cc_trd = len(st_cc.trades) if st_cc else 0
        cc_wins = len([t for t in st_cc.trades if t.net_pnl_usd > 0]) if st_cc else 0
        cc_stops = len([t for t in st_cc.trades if t.exit_reason == "STOP_LOSS"]) if st_cc else 0
        cc_hedges = len([t for t in st_cc.trades if t.exit_reason == "DEFENSIVE_MAKER_HEDGE"]) if st_cc else 0
        cc_net = sum(t.net_pnl_usd for t in st_cc.trades) if st_cc else 0.0
        cc_gross = sum(t.gross_pnl_usd for t in st_cc.trades) if st_cc else 0.0
        cc_fees = sum(t.fees_usd for t in st_cc.trades) if st_cc else 0.0
        cc_winrate = (cc_wins / cc_trd * 100.0) if cc_trd > 0 else 0.0

        st_me = runner.evaluator.strategies.get("Momentum_Expansion")
        me_trd = len(st_me.trades) if st_me else 0
        me_wins = len([t for t in st_me.trades if t.net_pnl_usd > 0]) if st_me else 0
        me_stops = len([t for t in st_me.trades if t.exit_reason == "STOP_LOSS"]) if st_me else 0
        me_hedges = len([t for t in st_me.trades if t.exit_reason == "DEFENSIVE_MAKER_HEDGE"]) if st_me else 0
        me_net = sum(t.net_pnl_usd for t in st_me.trades) if st_me else 0.0
        me_gross = sum(t.gross_pnl_usd for t in st_me.trades) if st_me else 0.0
        me_fees = sum(t.fees_usd for t in st_me.trades) if st_me else 0.0
        me_winrate = (me_wins / me_trd * 100.0) if me_trd > 0 else 0.0

        session_net = cc_net + me_net

        cc_all_trades += cc_trd
        cc_all_wins += cc_wins
        cc_all_stops += cc_stops
        cc_all_hedges += cc_hedges
        cc_all_gross_pnl += cc_gross
        cc_all_fees += cc_fees
        cc_all_net_pnl += cc_net

        me_all_trades += me_trd
        me_all_wins += me_wins
        me_all_stops += me_stops
        me_all_hedges += me_hedges
        me_all_gross_pnl += me_gross
        me_all_fees += me_fees
        me_all_net_pnl += me_net

        cc_style = "green" if cc_net > 0 else "red"
        me_style = "green" if me_net > 0 else "red"
        tot_style = "bold green" if session_net > 0 else "bold red"

        results_table.add_row(
            filename,
            f"{size_mb:.1f} MB",
            str(cc_trd),
            f"{cc_winrate:.1f}%",
            str(cc_stops),
            f"[{cc_style}]${cc_net:+6.2f}[/{cc_style}]",
            str(me_trd),
            f"{me_winrate:.1f}%",
            str(me_stops),
            f"[{me_style}]${me_net:+6.2f}[/{me_style}]",
            f"[{tot_style}]${session_net:+6.2f}[/{tot_style}]",
        )

    console.print(results_table)

    elapsed_s = time.time() - t_start
    total_net = cc_all_net_pnl + me_all_net_pnl
    total_trades = cc_all_trades + me_all_trades
    total_wins = cc_all_wins + me_all_wins
    overall_winrate = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0

    cc_losses = cc_all_trades - cc_all_wins
    cc_gross_wins = cc_all_gross_pnl + (cc_all_fees if cc_all_net_pnl < 0 else 0.0) # approx
    cc_pf = (cc_all_gross_pnl / max(abs(cc_all_gross_pnl - cc_all_net_pnl), 1e-4)) if cc_all_trades > 0 else 0.0

    console.print("\n[bold cyan]===============================================================================[/bold cyan]")
    console.print("[bold green]EXECUTIVE PERFORMANCE SUMMARY ACROSS LARGE HYPE SESSIONS[/bold green]")
    console.print(f"[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"Elapsed Time:               [bold white]{elapsed_s:.1f}s[/bold white]")
    console.print(f"Total Datasets Processed:   [bold white]{len(target_files)}[/bold white]")
    console.print(f"Total Trades Executed:      [bold white]{total_trades}[/bold white]")
    console.print(f"Overall Win Rate:           [bold white]{overall_winrate:.1f}%[/bold white] ({total_wins} Wins / {total_trades - total_wins} Losses)")
    console.print(f"Combined Net PnL:           [bold green]${total_net:+.2f}[/bold green]\n")

    console.print(f"[bold yellow]Convexity_Cascade:[/bold yellow]")
    console.print(f"  Trades:        {cc_all_trades}  (Win Rate: {(cc_all_wins/cc_all_trades*100.0) if cc_all_trades else 0:.1f}%)")
    console.print(f"  Net PnL:       ${cc_all_net_pnl:+.2f}  (Gross: ${cc_all_gross_pnl:+.2f}, Fees: ${cc_all_fees:.2f})")
    console.print(f"  Stop Losses:   {cc_all_stops} trades ({(cc_all_stops/cc_all_trades*100.0) if cc_all_trades else 0:.1f}%)")
    console.print(f"  Maker Hedges:  {cc_all_hedges} trades ({(cc_all_hedges/cc_all_trades*100.0) if cc_all_trades else 0:.1f}%)")

    console.print(f"\n[bold yellow]Momentum_Expansion:[/bold yellow]")
    console.print(f"  Trades:        {me_all_trades}  (Win Rate: {(me_all_wins/me_all_trades*100.0) if me_all_trades else 0:.1f}%)")
    console.print(f"  Net PnL:       ${me_all_net_pnl:+.2f}  (Gross: ${me_all_gross_pnl:+.2f}, Fees: ${me_all_fees:.2f})")
    console.print(f"  Stop Losses:   {me_all_stops} trades ({(me_all_stops/me_all_trades*100.0) if me_all_trades else 0:.1f}%)")
    console.print(f"  Maker Hedges:  {me_all_hedges} trades ({(me_all_hedges/me_all_trades*100.0) if me_all_trades else 0:.1f}%)")


if __name__ == "__main__":
    min_size = float(sys.argv[1]) if len(sys.argv) > 1 else 9.0
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    run_hype_large_sessions_backtest(min_size_mb=min_size, max_files=count)
