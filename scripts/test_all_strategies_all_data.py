"""High-Throughput Parallel Evaluation across ALL recorded datasets (BTC, HYPE, ETH, SOL).

Runs multi-process parallel replay across all historical L2 JSONL files in data/
evaluating core alpha strategies (Hedged_Convexity, Convexity_Cascade, Momentum_Expansion)
and optional standalone factor strategies.
"""

import argparse
import glob
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from collections import Counter

from rich.console import Console
from rich.table import Table

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


def detect_coin(filepath: str) -> str:
    """Detects coin from filepath."""
    fpath_lower = filepath.lower().replace("\\", "/")
    for c in ["btc", "hype", "sol", "eth"]:
        if f"hl_{c}_" in fpath_lower or f"/{c}/" in fpath_lower:
            return c.upper()
    return "BTC"


def get_coin_order_size(coin: str) -> float:
    """Returns calibrated order size to approximate ~$8,500 - $9,500 USD notional."""
    c = coin.upper()
    if c == "HYPE":
        return 95.0
    elif c == "SOL":
        return 50.0
    elif c == "ETH":
        return 3.0
    else:  # BTC
        return 0.1


def replay_single_dataset(args_tuple: tuple) -> Dict[str, Any]:
    """Top-level worker function for ProcessPoolExecutor (Windows spawn-compatible)."""
    filepath, enabled_strategies_list = args_tuple
    filename = os.path.basename(filepath)
    size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)
    coin = detect_coin(filepath)

    cfg = AppConfig()
    cfg.market.coin = coin
    cfg.backtest.order_size_btc = get_coin_order_size(coin)
    cfg.strategies = StrategiesConfig.load("strategies.json")

    # If specific strategies were requested, enable them
    if enabled_strategies_list:
        for s_name in cfg.strategies.execution_strategies:
            cfg.strategies.execution_strategies[s_name].enabled = (s_name in enabled_strategies_list)

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
            "coin": coin,
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

    active_strats = [s for s, st in cfg.strategies.execution_strategies.items() if st.enabled]
    for s_name in active_strats:
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
        gross_wins = sum(t.gross_pnl_usd for t in wins)
        gross_losses = abs(sum(t.gross_pnl_usd for t in losses))

        strat_results[s_name] = {
            "trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "stops": len(stops),
            "hedges": len(hedges),
            "tps": len(tps),
            "trails": len(trails),
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
                "coin": coin,
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
        "coin": coin,
        "size_mb": size_mb,
        "events_count": events_count,
        "elapsed_s": elapsed_s,
        "error": None,
        "strategies": strat_results,
        "all_trades": all_trades_list,
    }


def run_full_backtest(
    coins: Optional[List[str]] = None,
    max_files_per_coin: int = 0,
    workers: int = 10,
    strategies_filter: Optional[List[str]] = None,
):
    console = Console()
    target_coins = coins or ["btc", "hype", "eth", "sol"]

    all_files = []
    for c in target_coins:
        cdir = os.path.join("data", c.lower())
        if os.path.isdir(cdir):
            c_files = sorted(glob.glob(os.path.join(cdir, "*.jsonl")), key=os.path.getsize, reverse=True)
            if max_files_per_coin > 0:
                c_files = c_files[:max_files_per_coin]
            all_files.extend(c_files)

    if not all_files:
        console.print("[bold red]No recording files found across target coins![/bold red]")
        return

    total_mb = sum(os.path.getsize(f) for f in all_files) / (1024.0 * 1024.0)
    num_workers = min(workers, os.cpu_count() or 4)

    console.print("\n[bold cyan]===============================================================================[/bold cyan]")
    console.print("[bold green]CROSS-ASSET FULL L2 MICROSTRUCTURE BACKTEST: ALL STRATEGIES & ALL DATA[/bold green]")
    console.print("[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"Target Datasets:  [bold yellow]{len(all_files)} recording sessions[/bold yellow] across {', '.join(c.upper() for c in target_coins)} ({total_mb:.1f} MB)")
    console.print(f"Parallel Workers: [bold yellow]{num_workers} processes[/bold yellow] (CPU: {os.cpu_count()} cores)")

    cfg_sample = StrategiesConfig.load("strategies.json")
    active_strats = [s for s, st in cfg_sample.execution_strategies.items() if st.enabled]
    if strategies_filter:
        active_strats = strategies_filter
    console.print(f"Active Strategies:[bold yellow] {', '.join(active_strats)}[/bold yellow]\n")

    start_time = time.time()
    results = []

    tasks = [(f, active_strats) for f in all_files]

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        future_to_file = {executor.submit(replay_single_dataset, task): task[0] for task in tasks}
        completed = 0
        running_net = 0.0
        running_trades = 0

        for future in as_completed(future_to_file):
            completed += 1
            res = future.result()
            results.append(res)

            if res.get("error"):
                console.print(f"[{completed:3d}/{len(all_files):3d}] [bold red]Error in {res['filename']}: {res['error']}[/bold red]")
            else:
                file_net = sum(s["net_pnl"] for s in res["strategies"].values())
                file_trd = sum(s["trades"] for s in res["strategies"].values())
                running_net += file_net
                running_trades += file_trd
                c_style = "green" if file_net > 0 else ("red" if file_net < 0 else "dim")
                console.print(
                    f"[{completed:3d}/{len(all_files):3d}] ✓ [{res['coin']:4s}] {res['filename']:<34} "
                    f"({res['size_mb']:4.1f} MB) | Trd: {file_trd:2d} | Net: [{c_style}]${file_net:+6.2f}[/{c_style}] | "
                    f"Running Net: [bold {'green' if running_net >= 0 else 'red'}]${running_net:+8.2f}[/bold {'green' if running_net >= 0 else 'red'}]"
                )

    total_duration = time.time() - start_time

    # Group by Coin
    coin_totals = {}
    strat_totals = {}
    for s_name in active_strats:
        strat_totals[s_name] = {
            "trades": 0, "wins": 0, "losses": 0, "stops": 0, "hedges": 0,
            "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "gw": 0.0, "gl": 0.0
        }

    all_trades = []
    exit_counter = Counter()

    for r in results:
        if r.get("error"):
            continue
        c = r["coin"]
        coin_totals.setdefault(c, {"trades": 0, "wins": 0, "losses": 0, "stops": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0})
        
        for s_name, s_data in r["strategies"].items():
            if s_name not in strat_totals:
                strat_totals[s_name] = {"trades": 0, "wins": 0, "losses": 0, "stops": 0, "hedges": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "gw": 0.0, "gl": 0.0}
            st = strat_totals[s_name]
            st["trades"] += s_data["trades"]
            st["wins"] += s_data["wins"]
            st["losses"] += s_data["losses"]
            st["stops"] += s_data["stops"]
            st["hedges"] += s_data["hedges"]
            st["gross_pnl"] += s_data["gross_pnl"]
            st["fees"] += s_data["fees"]
            st["net_pnl"] += s_data["net_pnl"]
            st["gw"] += s_data["gross_wins"]
            st["gl"] += s_data["gross_losses"]

            coin_totals[c]["trades"] += s_data["trades"]
            coin_totals[c]["wins"] += s_data["wins"]
            coin_totals[c]["losses"] += s_data["losses"]
            coin_totals[c]["stops"] += s_data["stops"]
            coin_totals[c]["gross_pnl"] += s_data["gross_pnl"]
            coin_totals[c]["fees"] += s_data["fees"]
            coin_totals[c]["net_pnl"] += s_data["net_pnl"]

        for tr in r.get("all_trades", []):
            all_trades.append(tr)
            exit_counter[tr["exit_reason"]] += 1

    # 1. Strategy Summary Table
    console.print("\n")
    summary_table = Table(
        title=f"Grand Strategy Performance Matrix Across All Datasets ({len(all_files)} Sessions, {total_duration:.1f}s Replay)",
        header_style="bold magenta",
        show_header=True,
    )
    summary_table.add_column("Strategy", justify="left")
    summary_table.add_column("Trades", justify="right")
    summary_table.add_column("Win Rate", justify="right")
    summary_table.add_column("Gross PnL ($)", justify="right")
    summary_table.add_column("Fees ($)", justify="right")
    summary_table.add_column("Net PnL ($)", justify="right", style="bold")
    summary_table.add_column("Profit Factor", justify="right")
    summary_table.add_column("Stop Losses", justify="right")
    summary_table.add_column("Maker Hedges", justify="right")

    comb_trades = 0
    comb_wins = 0
    comb_gross = 0.0
    comb_fees = 0.0
    comb_net = 0.0
    comb_stops = 0
    comb_hedges = 0
    comb_gw = 0.0
    comb_gl = 0.0

    for s_name, st in strat_totals.items():
        if st["trades"] == 0:
            continue
        wr = (st["wins"] / st["trades"]) * 100.0
        pf = (st["gw"] / max(st["gl"], 1e-4)) if st["gl"] > 0 else (99.0 if st["gw"] > 0 else 0.0)
        c = "green" if st["net_pnl"] > 0 else "red"

        summary_table.add_row(
            s_name,
            str(st["trades"]),
            f"{wr:.1f}%",
            f"${st['gross_pnl']:+8.2f}",
            f"${st['fees']:8.2f}",
            f"[{c}]${st['net_pnl']:+8.2f}[/{c}]",
            f"{pf:.2f}",
            str(st["stops"]),
            str(st["hedges"]),
        )
        comb_trades += st["trades"]
        comb_wins += st["wins"]
        comb_gross += st["gross_pnl"]
        comb_fees += st["fees"]
        comb_net += st["net_pnl"]
        comb_stops += st["stops"]
        comb_hedges += st["hedges"]
        comb_gw += st["gw"]
        comb_gl += st["gl"]

    comb_wr = (comb_wins / comb_trades * 100.0) if comb_trades > 0 else 0.0
    comb_pf = (comb_gw / max(comb_gl, 1e-4)) if comb_gl > 0 else 0.0
    summary_table.add_row(
        "[bold cyan]PORTFOLIO TOTAL[/bold cyan]",
        f"[bold]{comb_trades}[/bold]",
        f"[bold]{comb_wr:.1f}%[/bold]",
        f"[bold]${comb_gross:+8.2f}[/bold]",
        f"[bold]${comb_fees:8.2f}[/bold]",
        f"[bold {'green' if comb_net >= 0 else 'red'}]${comb_net:+8.2f}[/bold {'green' if comb_net >= 0 else 'red'}]",
        f"[bold]{comb_pf:.2f}[/bold]",
        f"[bold]{comb_stops}[/bold]",
        f"[bold]{comb_hedges}[/bold]",
    )
    console.print(summary_table)

    # 2. Coin Breakdown Table
    console.print("\n")
    coin_table = Table(
        title="Asset Breakdown Performance Matrix",
        header_style="bold cyan",
        show_header=True,
    )
    coin_table.add_column("Asset", justify="left")
    coin_table.add_column("Datasets", justify="right")
    coin_table.add_column("Trades", justify="right")
    coin_table.add_column("Win Rate", justify="right")
    coin_table.add_column("Gross PnL ($)", justify="right")
    coin_table.add_column("Fees ($)", justify="right")
    coin_table.add_column("Net PnL ($)", justify="right", style="bold")
    coin_table.add_column("Stop Losses", justify="right")

    for coin_name, c_data in sorted(coin_totals.items()):
        c_files_count = len([r for r in results if r.get("coin") == coin_name and not r.get("error")])
        if c_data["trades"] == 0:
            coin_table.add_row(coin_name, str(c_files_count), "0", "0.0%", "$0.00", "$0.00", "$0.00", "0")
            continue
        c_wr = (c_data["wins"] / c_data["trades"]) * 100.0
        c_style = "green" if c_data["net_pnl"] > 0 else "red"
        coin_table.add_row(
            f"[bold yellow]{coin_name}[/bold yellow]",
            str(c_files_count),
            str(c_data["trades"]),
            f"{c_wr:.1f}%",
            f"${c_data['gross_pnl']:+8.2f}",
            f"${c_data['fees']:8.2f}",
            f"[{c_style}]${c_data['net_pnl']:+8.2f}[/{c_style}]",
            str(c_data["stops"]),
        )
    console.print(coin_table)

    # 3. Exit Distribution Breakdown
    console.print("\n[bold yellow]Trade Exit Reason Distribution:[/bold yellow]")
    for reason, count in exit_counter.most_common():
        pct = (count / max(comb_trades, 1)) * 100.0
        sub_trades = [t for t in all_trades if t["exit_reason"] == reason]
        r_net = sum(t["net_pnl"] for t in sub_trades)
        r_avg = sum(t["return_bps"] for t in sub_trades) / len(sub_trades) if sub_trades else 0.0
        console.print(f"  - {reason:<24}: {count:4d} trades ({pct:4.1f}%) | Avg Return: {r_avg:+5.1f} bps | Net PnL: ${r_net:+8.2f}")

    console.print(f"\n[bold green]Cross-Asset Replay Completed in {total_duration:.1f} seconds across {len(all_files)} datasets![/bold green]\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Asset L2 Microstructure Backtest")
    parser.add_argument("--coins", type=str, default="btc,hype,eth,sol", help="Comma-separated coins to test")
    parser.add_argument("--max-files", type=int, default=0, help="Max files per coin (0 = all)")
    parser.add_argument("--workers", type=int, default=10, help="Multiprocessing workers")
    args = parser.parse_args()

    target_coins = [c.strip().lower() for c in args.coins.split(",") if c.strip()]
    run_full_backtest(coins=target_coins, max_files_per_coin=args.max_files, workers=args.workers)
