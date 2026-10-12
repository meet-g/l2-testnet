"""Parallel Fast Volatility Gate optimizer across large sessions (>70 MB)."""

import glob
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rich.console import Console
from rich.table import Table

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


def test_vol_hurdle_on_large_files(hurdle: float):
    data_dir = os.path.join("data", "btc") if os.path.isdir(os.path.join("data", "btc")) else "data"
    candidate_files = sorted(
        glob.glob(os.path.join(data_dir, "hl_btc_l2_2026100*.jsonl")),
        key=os.path.getsize,
        reverse=True,
    )[:6]
    candidate_files.sort(key=lambda x: os.path.basename(x))

    cfg = AppConfig()
    cfg.strategies = StrategiesConfig.load("strategies.json")

    # Set hurdle
    for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
        s = cfg.strategies.execution_strategies.get(s_name)
        if s:
            s.min_volatility_bps = hurdle

    eval_interval_ms = int(1000 / max(cfg.sample_rate_hz, 1))

    total_trades = 0
    total_wins = 0
    total_gross = 0.0
    total_fees = 0.0
    total_net = 0.0
    time_limit_count = 0
    time_limit_net = 0.0
    trailing_count = 0
    trailing_net = 0.0
    gross_wins = 0.0
    gross_losses = 0.0

    t0 = time.time()
    for fpath in candidate_files:
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
        "hurdle": hurdle,
        "elapsed_s": time.time() - t0,
        "trades": total_trades,
        "win_rate": win_rate,
        "gross_pnl": total_gross,
        "fees": total_fees,
        "net_pnl": total_net,
        "profit_factor": pf,
        "time_limits": time_limit_count,
        "time_limit_net": time_limit_net,
        "trailing_count": trailing_count,
        "trailing_net": trailing_net,
    }


if __name__ == "__main__":
    console = Console()
    console.print("\n[bold cyan]Parallel Fast Volatility Gate Calibration (Top 6 Largest Files, >70 MB)[/bold cyan]")
    hurdles = [0.0, 3.0, 3.8, 4.5]
    
    t_start = time.time()
    results = []
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(test_vol_hurdle_on_large_files, h): h for h in hurdles}
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            c = "green" if res['net_pnl'] > 0 else "red"
            console.print(
                f"✓ Hurdle: [bold]{res['hurdle']:3.1f} bps[/bold] in {res['elapsed_s']:4.1f}s | "
                f"Trd: {res['trades']:2d} | Win: {res['win_rate']:4.1f}% | "
                f"Gross: ${res['gross_pnl']:+6.2f} | Fees: -${res['fees']:5.2f} | "
                f"Net: [{c}]${res['net_pnl']:+6.2f}[/{c}] | PF: {res['profit_factor']:4.2f} | "
                f"TimeLimits: {res['time_limits']:2d} (${res['time_limit_net']:+5.2f}) | "
                f"Trails: {res['trailing_count']:2d} (${res['trailing_net']:+6.2f})"
            )

    results.sort(key=lambda x: x["hurdle"])
    tbl = Table(title="Volatility Hurdle Calibration Matrix", header_style="bold magenta")
    tbl.add_column("Hurdle", justify="left")
    tbl.add_column("Trades", justify="right")
    tbl.add_column("Win Rate", justify="right")
    tbl.add_column("Gross PnL ($)", justify="right")
    tbl.add_column("Fees ($)", justify="right")
    tbl.add_column("Net PnL ($)", justify="right")
    tbl.add_column("Profit Factor", justify="right")
    tbl.add_column("Time Limits", justify="right")
    tbl.add_column("Time Limit Net", justify="right")
    tbl.add_column("Trailing Net", justify="right")

    for r in results:
        c = "bold green" if r["net_pnl"] > 0 else "bold red"
        tbl.add_row(
            f"{r['hurdle']:.1f} bps" if r["hurdle"] > 0 else "0.0 bps (No Gate)",
            str(r["trades"]),
            f"{r['win_rate']:.1f}%",
            f"${r['gross_pnl']:+7.2f}",
            f"-${r['fees']:6.2f}",
            f"[{c}]${r['net_pnl']:+7.2f}[/{c}]",
            f"{r['profit_factor']:.2f}",
            str(r["time_limits"]),
            f"${r['time_limit_net']:+6.2f}",
            f"${r['trailing_net']:+6.2f}",
        )
    console.print("\n")
    console.print(tbl)
    console.print(f"[bold green]Calibration complete in {time.time()-t_start:.1f}s[/bold green]\n")
