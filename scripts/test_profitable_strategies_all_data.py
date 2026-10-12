"""Batch Replay Evaluation of Profitable L2 Strategies across all historical recordings.

Executes 'Hedged_Convexity', 'Convexity_Cascade', and 'Momentum_Expansion' across every BTC L2 dataset
in data/, recording trade outcomes, win rates, fee drag, net PnL, profit factors,
and multi-horizon IC metrics.
"""

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


def run_batch_evaluation():
    console = Console()
    data_dir = os.path.join("data", "btc") if os.path.isdir(os.path.join("data", "btc")) else "data"
    all_files = sorted(glob.glob(os.path.join(data_dir, "hl_btc_l2_*.jsonl")))

    if not all_files:
        console.print("[bold red]No BTC L2 recording files found in data/![/bold red]")
        return

    console.print(f"\n[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"[bold green]BATCH REPLAY: Testing Hedged & Unhedged Alpha Strategies Across ALL Recorded Datasets[/bold green]")
    console.print(f"[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"Target Strategies: [bold yellow]Hedged_Convexity[/bold yellow], [bold yellow]Convexity_Cascade[/bold yellow], [bold yellow]Momentum_Expansion[/bold yellow]")
    console.print(f"Total Datasets:    [bold yellow]{len(all_files)} files[/bold yellow]\n")

    cfg = AppConfig()
    cfg.strategies = StrategiesConfig.load("strategies.json")

    results_table = Table(
        title="Cross-Dataset Microstructure Alpha Performance Matrix",
        header_style="bold magenta",
        show_header=True,
    )
    results_table.add_column("Dataset File", justify="left", style="dim")
    results_table.add_column("Size", justify="right")
    results_table.add_column("HC Trd", justify="right")
    results_table.add_column("HC Win%", justify="right")
    results_table.add_column("HC PnL ($)", justify="right")
    results_table.add_column("HC PF", justify="right")
    results_table.add_column("CC Net ($)", justify="right")
    results_table.add_column("ME Net ($)", justify="right")
    results_table.add_column("Total Net ($)", justify="right", style="bold")

    hc_all_trades = 0
    hc_all_wins = 0
    hc_all_gross_pnl = 0.0
    hc_all_fees = 0.0
    hc_all_net = 0.0
    hc_all_gross_win = 0.0
    hc_all_gross_loss = 0.0

    cc_all_trades = 0
    cc_all_wins = 0
    cc_all_gross_pnl = 0.0
    cc_all_fees = 0.0
    cc_all_net = 0.0
    cc_all_gross_win = 0.0
    cc_all_gross_loss = 0.0

    me_all_trades = 0
    me_all_wins = 0
    me_all_gross_pnl = 0.0
    me_all_fees = 0.0
    me_all_net = 0.0
    me_all_gross_win = 0.0
    me_all_gross_loss = 0.0

    session_start_time = time.time()

    for idx, filepath in enumerate(all_files, 1):
        filename = os.path.basename(filepath)
        size_kb = os.path.getsize(filepath) / 1024.0
        size_str = f"{size_kb:.0f} KB" if size_kb < 1024 else f"{size_kb/1024.0:.1f} MB"

        t0 = time.time()
        runner = L2EngineRunner(config=cfg, record_data=False)
        replay = L2ReplayEngine(filepath, speed_multiplier=2500.0)

        last_eval_ms = 0
        eval_interval_ms = int(1000 / max(cfg.sample_rate_hz, 1))

        try:
            for event in replay.stream_events():
                ch = event.get("channel")
                dt = event.get("data")
                now_ms = event.get("recv_ts", 0)

                if ch == "l2Book":
                    runner.book.update_from_raw(dt)
                elif ch == "trades":
                    runner.trades.process_raw_trades(dt)

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
            console.print(f"[bold red]Error replaying {filename}: {e}[/bold red]")
            continue

        elapsed = time.time() - t0

        # Extract Hedged_Convexity stats
        hc_state = runner.evaluator.strategies.get("Hedged_Convexity")
        hc_trades = hc_state.trades if hc_state else []
        hc_n = len(hc_trades)
        hc_w = sum(1 for t in hc_trades if t.net_pnl_usd > 0)
        hc_win_pct = (hc_w / hc_n * 100.0) if hc_n > 0 else 0.0
        hc_net = sum(t.net_pnl_usd for t in hc_trades)
        hc_fees = sum(t.fees_usd for t in hc_trades)
        hc_gw = sum(t.net_pnl_usd for t in hc_trades if t.net_pnl_usd > 0)
        hc_gl = abs(sum(t.net_pnl_usd for t in hc_trades if t.net_pnl_usd < 0))
        hc_pf = (hc_gw / hc_gl) if hc_gl > 0 else (99.0 if hc_gw > 0 else 0.0)

        hc_gross = sum(t.gross_pnl_usd for t in hc_trades)
        hc_all_trades += hc_n
        hc_all_wins += hc_w
        hc_all_gross_pnl += hc_gross
        hc_all_fees += hc_fees
        hc_all_net += hc_net
        hc_all_gross_win += hc_gw
        hc_all_gross_loss += hc_gl

        # Extract Convexity_Cascade stats
        cc_state = runner.evaluator.strategies.get("Convexity_Cascade")
        cc_trades = cc_state.trades if cc_state else []
        cc_n = len(cc_trades)
        cc_w = sum(1 for t in cc_trades if t.net_pnl_usd > 0)
        cc_win_pct = (cc_w / cc_n * 100.0) if cc_n > 0 else 0.0
        cc_net = sum(t.net_pnl_usd for t in cc_trades)
        cc_fees = sum(t.fees_usd for t in cc_trades)
        cc_gw = sum(t.net_pnl_usd for t in cc_trades if t.net_pnl_usd > 0)
        cc_gl = abs(sum(t.net_pnl_usd for t in cc_trades if t.net_pnl_usd < 0))
        cc_pf = (cc_gw / cc_gl) if cc_gl > 0 else (99.0 if cc_gw > 0 else 0.0)

        cc_gross = sum(t.gross_pnl_usd for t in cc_trades)
        cc_all_trades += cc_n
        cc_all_wins += cc_w
        cc_all_gross_pnl += cc_gross
        cc_all_fees += cc_fees
        cc_all_net += cc_net
        cc_all_gross_win += cc_gw
        cc_all_gross_loss += cc_gl

        # Extract Momentum_Expansion stats
        me_state = runner.evaluator.strategies.get("Momentum_Expansion")
        me_trades = me_state.trades if me_state else []
        me_n = len(me_trades)
        me_w = sum(1 for t in me_trades if t.net_pnl_usd > 0)
        me_win_pct = (me_w / me_n * 100.0) if me_n > 0 else 0.0
        me_net = sum(t.net_pnl_usd for t in me_trades)
        me_fees = sum(t.fees_usd for t in me_trades)
        me_gw = sum(t.net_pnl_usd for t in me_trades if t.net_pnl_usd > 0)
        me_gl = abs(sum(t.net_pnl_usd for t in me_trades if t.net_pnl_usd < 0))
        me_pf = (me_gw / me_gl) if me_gl > 0 else (99.0 if me_gw > 0 else 0.0)

        me_gross = sum(t.gross_pnl_usd for t in me_trades)
        me_all_trades += me_n
        me_all_wins += me_w
        me_all_gross_pnl += me_gross
        me_all_fees += me_fees
        me_all_net += me_net
        me_all_gross_win += me_gw
        me_all_gross_loss += me_gl

        combined_net = hc_net + cc_net + me_net
        comb_c = "green" if combined_net > 0 else ("red" if combined_net < 0 else "dim")
        hc_c = "green" if hc_net > 0 else ("red" if hc_net < 0 else "dim")
        cc_c = "green" if cc_net > 0 else ("red" if cc_net < 0 else "dim")
        me_c = "green" if me_net > 0 else ("red" if me_net < 0 else "dim")

        results_table.add_row(
            filename,
            size_str,
            str(hc_n),
            f"{hc_win_pct:.1f}%" if hc_n > 0 else "-",
            f"[{hc_c}]${hc_net:+.2f}[/{hc_c}]" if hc_n > 0 else "-",
            f"{hc_pf:.2f}" if hc_n > 0 else "-",
            f"[{cc_c}]${cc_net:+.2f}[/{cc_c}]" if cc_n > 0 else "-",
            f"[{me_c}]${me_net:+.2f}[/{me_c}]" if me_n > 0 else "-",
            f"[{comb_c}]${combined_net:+.2f}[/{comb_c}]",
        )
        console.print(f"[{idx:2d}/{len(all_files):2d}] Replayed [bold cyan]{filename}[/bold cyan] ({size_str}) in {elapsed:.1f}s -> HC: [{hc_c}]${hc_net:+.2f}[/{hc_c}], CC: [{cc_c}]${cc_net:+.2f}[/{cc_c}], ME: [{me_c}]${me_net:+.2f}[/{me_c}]")

    total_duration = time.time() - session_start_time

    # Add Totals row
    hc_tot_pf = (hc_all_gross_win / hc_all_gross_loss) if hc_all_gross_loss > 0 else (99.0 if hc_all_gross_win > 0 else 0.0)
    cc_tot_pf = (cc_all_gross_win / cc_all_gross_loss) if cc_all_gross_loss > 0 else (99.0 if cc_all_gross_win > 0 else 0.0)
    me_tot_pf = (me_all_gross_win / me_all_gross_loss) if me_all_gross_loss > 0 else (99.0 if me_all_gross_win > 0 else 0.0)
    hc_tot_win_pct = (hc_all_wins / hc_all_trades * 100.0) if hc_all_trades > 0 else 0.0
    cc_tot_win_pct = (cc_all_wins / cc_all_trades * 100.0) if cc_all_trades > 0 else 0.0
    me_tot_win_pct = (me_all_wins / me_all_trades * 100.0) if me_all_trades > 0 else 0.0
    total_portfolio_net = hc_all_net + cc_all_net + me_all_net
    tot_comb_c = "bold green" if total_portfolio_net > 0 else "bold red"
    tot_hc_c = "bold green" if hc_all_net > 0 else "bold red"
    tot_cc_c = "bold green" if cc_all_net > 0 else "bold red"
    tot_me_c = "bold green" if me_all_net > 0 else "bold red"

    results_table.add_section()
    results_table.add_row(
        "[bold]PORTFOLIO TOTALS[/bold]",
        "-",
        f"[bold]{hc_all_trades}[/bold]",
        f"[bold]{hc_tot_win_pct:.1f}%[/bold]",
        f"[{tot_hc_c}]${hc_all_net:+.2f}[/{tot_hc_c}]",
        f"[bold]{hc_tot_pf:.2f}[/bold]",
        f"[{tot_cc_c}]${cc_all_net:+.2f}[/{tot_cc_c}]",
        f"[{tot_me_c}]${me_all_net:+.2f}[/{tot_me_c}]",
        f"[{tot_comb_c}]${total_portfolio_net:+.2f}[/{tot_comb_c}]",
    )

    console.print("\n")
    console.print(results_table)

    total_portfolio_gross = hc_all_gross_pnl + cc_all_gross_pnl + me_all_gross_pnl
    total_portfolio_fees = hc_all_fees + cc_all_fees + me_all_fees
    tot_gross_c = "bold green" if total_portfolio_gross > 0 else "bold red"

    console.print(f"\n[bold cyan]Summary Across All {len(all_files)} Recorded Sessions (Completed in {total_duration:.1f}s):[/bold cyan]")
    console.print(f"  • [bold yellow]Hedged_Convexity[/bold yellow]:   {hc_all_trades:3d} Trades | Win Rate: {hc_tot_win_pct:.1f}% | Gross PnL: [green]${hc_all_gross_pnl:+8.2f}[/green] | Fees: [red]-${hc_all_fees:7.2f}[/red] | Net PnL: [{tot_hc_c}]${hc_all_net:+7.2f}[/{tot_hc_c}] | Profit Factor: {hc_tot_pf:.2f}")
    console.print(f"  • [bold yellow]Convexity_Cascade[/bold yellow]:  {cc_all_trades:3d} Trades | Win Rate: {cc_tot_win_pct:.1f}% | Gross PnL: [green]${cc_all_gross_pnl:+8.2f}[/green] | Fees: [red]-${cc_all_fees:7.2f}[/red] | Net PnL: [{tot_cc_c}]${cc_all_net:+7.2f}[/{tot_cc_c}] | Profit Factor: {cc_tot_pf:.2f}")
    console.print(f"  • [bold yellow]Momentum_Expansion[/bold yellow]: {me_all_trades:3d} Trades | Win Rate: {me_tot_win_pct:.1f}% | Gross PnL: [green]${me_all_gross_pnl:+8.2f}[/green] | Fees: [red]-${me_all_fees:7.2f}[/red] | Net PnL: [{tot_me_c}]${me_all_net:+7.2f}[/{tot_me_c}] | Profit Factor: {me_tot_pf:.2f}")
    console.print(f"  • [bold green]Combined Portfolio[/bold green]: {hc_all_trades + cc_all_trades + me_all_trades:3d} Trades | Gross PnL: [{tot_gross_c}]${total_portfolio_gross:+8.2f}[/{tot_gross_c}] | Fees: [red]-${total_portfolio_fees:7.2f}[/red] | Net PnL: [{tot_comb_c}]${total_portfolio_net:+7.2f}[/{tot_comb_c}]\n")


if __name__ == "__main__":
    run_batch_evaluation()
