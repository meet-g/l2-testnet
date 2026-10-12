"""Test and optimize Volatility Gating on the recent 40.5-hour completed live session.

Evaluates how filtering entries based on rolling 3-minute price amplitude (volatility in bps)
impacts Net PnL, Win Rate, and TIME_LIMIT fee drain across multiple thresholds [0.0 to 5.0 bps].
"""

import glob
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, List

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rich.console import Console
from rich.table import Table

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


def run_session_with_vol_hurdle(session_files: List[str], min_vol_bps: float) -> Dict[str, Any]:
    """Replays the session files with a specific min_volatility_bps threshold."""
    cfg = AppConfig()
    cfg.strategies = StrategiesConfig.load("strategies.json")

    # Set min_volatility_bps on all active execution strategies
    for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
        s = cfg.strategies.execution_strategies.get(s_name)
        if s:
            s.min_volatility_bps = min_vol_bps

    total_trades = 0
    total_wins = 0
    total_gross = 0.0
    total_fees = 0.0
    total_net = 0.0
    gross_wins = 0.0
    gross_losses = 0.0
    time_limit_count = 0
    time_limit_net = 0.0
    trailing_count = 0
    trailing_net = 0.0

    eval_interval_ms = int(1000 / max(cfg.sample_rate_hz, 1))

    for fpath in session_files:
        runner = L2EngineRunner(config=cfg, record_data=False)
        replay = L2ReplayEngine(fpath, speed_multiplier=5000.0)

        last_eval_ms = 0
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

        # Aggregate trades
        for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
            st = runner.evaluator.strategies.get(s_name)
            if not st:
                continue
            for t in st.trades:
                total_trades += 1
                if t.net_pnl_usd > 0:
                    total_wins += 1
                    gross_wins += t.gross_pnl_usd
                elif t.net_pnl_usd < 0:
                    gross_losses += abs(t.gross_pnl_usd)

                total_gross += t.gross_pnl_usd
                total_fees += t.fees_usd
                total_net += t.net_pnl_usd

                if t.exit_reason == "TIME_LIMIT":
                    time_limit_count += 1
                    time_limit_net += t.net_pnl_usd
                elif t.exit_reason == "TRAILING_STOP":
                    trailing_count += 1
                    trailing_net += t.net_pnl_usd

    win_rate = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0
    pf = (gross_wins / gross_losses) if gross_losses > 0 else (99.0 if gross_wins > 0 else 0.0)

    return {
        "min_vol_bps": min_vol_bps,
        "trades": total_trades,
        "win_rate": win_rate,
        "gross_pnl": total_gross,
        "fees": total_fees,
        "net_pnl": total_net,
        "profit_factor": pf,
        "time_limit_count": time_limit_count,
        "time_limit_net": time_limit_net,
        "trailing_count": trailing_count,
        "trailing_net": trailing_net,
    }


def worker_eval(args):
    session_files, v = args
    return run_session_with_vol_hurdle(session_files, v)


def main():
    console = Console()
    data_dir = os.path.join("data", "btc") if os.path.isdir(os.path.join("data", "btc")) else "data"

    # Select the 40 files for session_20261002_012102
    all_oct2 = sorted(glob.glob(os.path.join(data_dir, "hl_btc_l2_20261002_*.jsonl")))
    all_oct3 = sorted(glob.glob(os.path.join(data_dir, "hl_btc_l2_20261003_*.jsonl")))
    session_files = [f for f in (all_oct2 + all_oct3) if not f.endswith("1800.jsonl")]

    thresholds = [0.0, 2.5, 3.2, 3.8, 4.5, 5.0]

    console.print("\n[bold cyan]===============================================================================[/bold cyan]")
    console.print("[bold green]VOLATILITY GATING EXPERIMENT: Testing Rolling 3-Minute Amplitude Gate[/bold green]")
    console.print("[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"Dataset:         [bold yellow]session_20261002_012102[/bold yellow] (40 files, 225 MB, 40.5 hours)")
    console.print(f"Filter Logic:    Only enter when rolling 3-minute price amplitude >= threshold bps")
    console.print(f"Tested Hurdle:   [bold yellow]{thresholds} bps[/bold yellow]\n")

    t0 = time.time()
    results = []

    # Run in parallel across thresholds
    with ProcessPoolExecutor(max_workers=min(6, os.cpu_count() or 4)) as executor:
        tasks = [(session_files, v) for v in thresholds]
        futures = {executor.submit(worker_eval, t): t[1] for t in tasks}

        for fut in futures:
            v_val = futures[fut]
            try:
                res = fut.result()
                results.append(res)
                c = "green" if res["net_pnl"] > 0 else "red"
                console.print(
                    f"✓ Evaluated Hurdle: [bold]{v_val:4.1f} bps[/bold] | "
                    f"Trd: {res['trades']:3d} | Win: {res['win_rate']:4.1f}% | "
                    f"Gross: ${res['gross_pnl']:+7.2f} | Fees: -${res['fees']:6.2f} | "
                    f"Net: [{c}]${res['net_pnl']:+7.2f}[/{c}] | PF: {res['profit_factor']:4.2f} | "
                    f"TimeLimits: {res['time_limit_count']:2d} (${res['time_limit_net']:+6.2f}) | "
                    f"Trails: {res['trailing_count']:2d} (${res['trailing_net']:+6.2f})"
                )
            except Exception as e:
                console.print(f"[bold red]Failed threshold {v_val}: {e}[/bold red]")

    results.sort(key=lambda x: x["min_vol_bps"])

    console.print("\n")
    tbl = Table(
        title="Volatility Gating Optimization Matrix (session_20261002_012102)",
        header_style="bold magenta",
        show_header=True,
    )
    tbl.add_column("Min Vol Hurdle", justify="left", style="bold")
    tbl.add_column("Trades", justify="right")
    tbl.add_column("Win Rate", justify="right")
    tbl.add_column("Gross PnL ($)", justify="right")
    tbl.add_column("Fees ($)", justify="right")
    tbl.add_column("Net PnL ($)", justify="right")
    tbl.add_column("Profit Factor", justify="right")
    tbl.add_column("Time Limit Trds", justify="right")
    tbl.add_column("Time Limit Net ($)", justify="right")
    tbl.add_column("Trailing Net ($)", justify="right")

    for r in results:
        c = "bold green" if r["net_pnl"] > 0 else "bold red"
        tbl.add_row(
            f"{r['min_vol_bps']:.1f} bps" if r["min_vol_bps"] > 0 else "0.0 bps (No Gate)",
            str(r["trades"]),
            f"{r['win_rate']:.1f}%",
            f"${r['gross_pnl']:+8.2f}",
            f"-${r['fees']:7.2f}",
            f"[{c}]${r['net_pnl']:+8.2f}[/{c}]",
            f"{r['profit_factor']:.2f}",
            str(r["time_limit_count"]),
            f"${r['time_limit_net']:+7.2f}",
            f"${r['trailing_net']:+7.2f}",
        )

    console.print(tbl)
    total_time = time.time() - t0
    console.print(f"\n[bold green]✓ Volatility experiment complete in {total_time:.1f}s[/bold green]\n")

    # Save to audits
    out_dir = "audits/volatility_gating_experiment"
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "volatility_sweep_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
