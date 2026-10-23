"""Parallel Batch Replay across the entire 6-Day HYPE Session (Oct 14 - Oct 20, 2026).

Replays all 142 chronological recording sessions from data/hype/
spanning 2026-10-14 20:00 through 2026-10-20 17:00 using multi-core parallel execution.
Evaluates the improved Convexity_Cascade alongside Hedged_Convexity and Momentum_Expansion.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
import glob
import json
import os
import sys
import time
from typing import Any, Dict, List

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rich.console import Console
from rich.table import Table

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


def replay_single_hype_file(filepath: str) -> Dict[str, Any]:
    """Worker function: Replays a single HYPE JSONL dataset."""
    filename = os.path.basename(filepath)
    size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)

    cfg = AppConfig()
    cfg.market.coin = "HYPE"
    cfg.backtest.order_size_btc = 95.0
    cfg.strategies = StrategiesConfig.load("strategies.json")

    runner = L2EngineRunner(config=cfg, record_data=False, enable_audit=False)
    replay = L2ReplayEngine(filepath, speed_multiplier=100000.0)

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

    for s_name in ["Convexity_Cascade", "Hedged_Convexity", "Momentum_Expansion"]:
        st = runner.evaluator.strategies.get(s_name)
        trades = st.trades if st else []
        n = len(trades)
        wins = [t for t in trades if t.net_pnl_usd > 0]
        losses = [t for t in trades if t.net_pnl_usd <= 0]
        stops = [t for t in trades if t.exit_reason == "STOP_LOSS"]
        hedges = [t for t in trades if t.exit_reason == "DEFENSIVE_MAKER_HEDGE"]
        tps = [t for t in trades if t.exit_reason == "TAKE_PROFIT"]
        trails = [t for t in trades if t.exit_reason == "TRAILING_STOP"]

        gross_pnl = sum(t.gross_pnl_usd for t in trades)
        fees = sum(t.fees_usd for t in trades)
        net_pnl = sum(t.net_pnl_usd for t in trades)

        strat_results[s_name] = {
            "trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "stops": len(stops),
            "hedges": len(hedges),
            "tp": len(tps),
            "trailing": len(trails),
            "gross_pnl": gross_pnl,
            "fees": fees,
            "net_pnl": net_pnl,
            "win_rate": (len(wins) / n * 100.0) if n > 0 else 0.0,
            "profit_factor": (gross_pnl / max(abs(gross_pnl - net_pnl), 1e-4)) if n > 0 else 0.0,
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


def run_full_session_replay():
    console = Console()
    data_dir = os.path.join("data", "hype")

    # Target exactly the multi-day period (Oct 14 20:00 to Oct 20 17:00)
    all_files = sorted(
        [
            f for f in glob.glob(os.path.join(data_dir, "hl_hype_l2_*.jsonl"))
            if "20261014_2000" <= os.path.basename(f)[11:24] <= "20261020_1700"
        ]
    )

    if not all_files:
        console.print("[bold red]No matching session files found in data/hype![/bold red]")
        return

    total_mb = sum(os.path.getsize(f) for f in all_files) / (1024.0 * 1024.0)

    console.print("\n[bold cyan]===============================================================================[/bold cyan]")
    console.print("[bold green]MULTI-DAY HYPE SESSION FULL REPLAY: Oct 14 - Oct 20, 2026[/bold green]")
    console.print("[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"Total Session Files:  [bold yellow]{len(all_files)} hourly files[/bold yellow]")
    console.print(f"Total Dataset Volume: [bold yellow]{total_mb:.1f} MB[/bold yellow]")
    console.print(f"CPU Workers:          [bold yellow]{min(os.cpu_count() or 4, 10)} parallel processes[/bold yellow]\n")

    t_start = time.time()
    workers = min(os.cpu_count() or 4, 10)

    results = []
    completed_count = 0

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(replay_single_hype_file, f): f for f in all_files}
        for future in as_completed(futures):
            res = future.result()
            results.append(res)
            completed_count += 1
            if completed_count % 20 == 0 or completed_count == len(all_files):
                elapsed = time.time() - t_start
                console.print(f"Progress: [bold green]{completed_count}/{len(all_files)}[/bold green] files replayed ({completed_count/len(all_files)*100:.1f}%) in {elapsed:.1f}s...")

    # Sort results chronologically
    results.sort(key=lambda r: r["filename"])

    total_trades_all = []
    strat_totals: Dict[str, Dict[str, Any]] = {
        s: {"trades": 0, "wins": 0, "losses": 0, "stops": 0, "hedges": 0, "tp": 0, "trailing": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0}
        for s in ["Convexity_Cascade", "Hedged_Convexity", "Momentum_Expansion"]
    }

    for r in results:
        if r.get("error"):
            continue
        total_trades_all.extend(r["all_trades"])
        for s, data in r["strategies"].items():
            for k in ["trades", "wins", "losses", "stops", "hedges", "tp", "trailing", "gross_pnl", "fees", "net_pnl"]:
                strat_totals[s][k] += data[k]

    # Daily breakdown table
    daily_table = Table(
        title="Daily Performance Breakdown Across the 6-Day Period",
        header_style="bold magenta",
        show_header=True,
    )
    daily_table.add_column("Date", justify="center", style="bold")
    daily_table.add_column("CC Trd", justify="right")
    daily_table.add_column("CC Win%", justify="right")
    daily_table.add_column("CC Hdg", justify="right")
    daily_table.add_column("CC Net ($)", justify="right")
    daily_table.add_column("HC Net ($)", justify="right")
    daily_table.add_column("ME Net ($)", justify="right")
    daily_table.add_column("Combined Net ($)", justify="right", style="bold")

    # Group trades by date
    from collections import defaultdict
    import datetime

    daily_trades = defaultdict(lambda: defaultdict(list))
    for t in total_trades_all:
        d_str = datetime.datetime.fromtimestamp(t["entry_time_ms"] / 1000.0).strftime("%Y-%m-%d")
        daily_trades[d_str][t["strategy"]].append(t)

    for d_str in sorted(daily_trades.keys()):
        cc_t = daily_trades[d_str]["Convexity_Cascade"]
        hc_t = daily_trades[d_str]["Hedged_Convexity"]
        me_t = daily_trades[d_str]["Momentum_Expansion"]

        cc_trd = len(cc_t)
        cc_wins = len([t for t in cc_t if t["net_pnl"] > 0])
        cc_winrate = (cc_wins / cc_trd * 100.0) if cc_trd > 0 else 0.0
        cc_hdg = len([t for t in cc_t if t["exit_reason"] == "DEFENSIVE_MAKER_HEDGE"])
        cc_net = sum(t["net_pnl"] for t in cc_t)

        hc_net = sum(t["net_pnl"] for t in hc_t)
        me_net = sum(t["net_pnl"] for t in me_t)
        tot_day = cc_net + hc_net + me_net

        cc_style = "green" if cc_net > 0 else ("red" if cc_net < 0 else "dim")
        hc_style = "green" if hc_net > 0 else ("red" if hc_net < 0 else "dim")
        me_style = "green" if me_net > 0 else ("red" if me_net < 0 else "dim")
        tot_style = "bold green" if tot_day > 0 else "bold red"

        daily_table.add_row(
            d_str,
            str(cc_trd),
            f"{cc_winrate:.1f}%" if cc_trd else "-",
            str(cc_hdg),
            f"[{cc_style}]${cc_net:+6.2f}[/{cc_style}]",
            f"[{hc_style}]${hc_net:+6.2f}[/{hc_style}]",
            f"[{me_style}]${me_net:+6.2f}[/{me_style}]",
            f"[{tot_style}]${tot_day:+6.2f}[/{tot_style}]",
        )

    console.print("\n")
    console.print(daily_table)

    # Executive Summary Table
    exec_table = Table(
        title="Executive Summary: Multi-Day Replay (Oct 14 - Oct 20, 2026)",
        header_style="bold cyan",
        show_header=True,
    )
    exec_table.add_column("Strategy", justify="left", style="bold")
    exec_table.add_column("Trades", justify="right")
    exec_table.add_column("Win Rate", justify="right")
    exec_table.add_column("Gross ($)", justify="right")
    exec_table.add_column("Fees ($)", justify="right")
    exec_table.add_column("Net PnL ($)", justify="right")
    exec_table.add_column("Profit Factor", justify="right")
    exec_table.add_column("TP / Trail", justify="center")
    exec_table.add_column("Hedge / SL", justify="center")

    for s_name, data in strat_totals.items():
        n = data["trades"]
        wr = (data["wins"] / n * 100.0) if n > 0 else 0.0
        pf = (data["gross_pnl"] / max(abs(data["gross_pnl"] - data["net_pnl"]), 1e-4)) if n > 0 else 0.0
        net_style = "bold green" if data["net_pnl"] > 0 else "bold red"

        exec_table.add_row(
            s_name,
            str(n),
            f"{wr:.1f}%",
            f"${data['gross_pnl']:+7.2f}",
            f"-${data['fees']:6.2f}",
            f"[{net_style}]${data['net_pnl']:+7.2f}[/{net_style}]",
            f"{pf:4.2f}",
            f"{data['tp']} / {data['trailing']}",
            f"{data['hedges']} / {data['stops']}",
        )

    console.print("\n")
    console.print(exec_table)

    elapsed_all = time.time() - t_start
    total_net_all = sum(data["net_pnl"] for data in strat_totals.values())
    total_trades_count = sum(data["trades"] for data in strat_totals.values())

    console.print("\n[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"Total Replay Runtime: [bold white]{elapsed_all:.1f}s[/bold white] across [bold white]{len(all_files)}[/bold white] chronological datasets")
    console.print(f"Total Executed Trades: [bold white]{total_trades_count}[/bold white]")
    console.print(f"Combined Multi-Day Net PnL: [{'bold green' if total_net_all > 0 else 'bold red'}]${total_net_all:+.2f}[/]")
    console.print(f"[bold cyan]===============================================================================[/bold cyan]\n")

    # Save summary report
    report_path = os.path.join("reports", "hype_multiday_replay_report.json")
    with open(report_path, "w") as f:
        json.dump({
            "session_range": "20261014_2000 - 20261020_1700",
            "files_count": len(all_files),
            "runtime_s": elapsed_all,
            "strategies": strat_totals,
            "total_trades": len(total_trades_all),
            "combined_net_pnl": total_net_all,
        }, f, indent=2)
    console.print(f"Saved full audit JSON to: [bold underline]{report_path}[/bold underline]")


if __name__ == "__main__":
    run_full_session_replay()
