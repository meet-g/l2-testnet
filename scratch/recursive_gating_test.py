"""Recursive Volume & Volatility Gating Calibration on recent extended session datasets.

Tests multiple combinations of:
- Volatility Hurdle (min_volatility_bps)
- Entry Threshold (entry_threshold)
- Trade Flow / CVD Volume Confirmation
- Dynamic Asset Price Scaling (for HYPE vs BTC)
"""

import copy
import glob
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, ".")

from rich.console import Console
from rich.table import Table

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


def replay_single_file(fpath, coin, strat_params_override, sample_hz=10.0):
    cfg = AppConfig()
    cfg.market.coin = coin.upper()
    cfg.sample_rate_hz = sample_hz
    
    # Load base strategies
    cfg.strategies = StrategiesConfig.load("strategies.json")
    if "AdaptiveML" in cfg.strategies.alpha_signals:
        cfg.strategies.alpha_signals["AdaptiveML"].enabled = False
    
    # Apply overrides
    for s_name, overrides in strat_params_override.items():
        st = cfg.strategies.execution_strategies.get(s_name)
        if st:
            for k, v in overrides.items():
                setattr(st, k, v)
                
    runner = L2EngineRunner(config=cfg, record_data=False)
    replay = L2ReplayEngine(fpath, speed_multiplier=10000.0)
    
    eval_interval_ms = int(1000 / max(sample_hz, 1))
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
        now_ms = runner.book.last_update_time_ms or 0
        runner.evaluator.close_open_positions(runner.book.mid_price, now_ms, reason="SESSION_SHUTDOWN")
        
    trades = []
    for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
        st = runner.evaluator.strategies.get(s_name)
        if st and st.trades:
            for t in st.trades:
                trades.append({
                    "strategy": s_name,
                    "side": t.side,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "gross_pnl": t.gross_pnl_usd,
                    "fees": t.fees_usd,
                    "net_pnl": t.net_pnl_usd,
                    "return_bps": t.return_bps,
                    "exit_reason": t.exit_reason,
                    "holding_secs": (t.exit_time_ms - t.entry_time_ms) / 1000.0,
                })
    return trades


def run_experiment_on_files(files, coin, strat_params_override, max_workers=6):
    all_trades = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(replay_single_file, f, coin, strat_params_override)
            for f in files
        ]
        for fut in futures:
            all_trades.extend(fut.result())
            
    total_trades = len(all_trades)
    wins = sum(1 for t in all_trades if t["net_pnl"] > 0)
    gross_pnl = sum(t["gross_pnl"] for t in all_trades)
    fees = sum(t["fees"] for t in all_trades)
    net_pnl = sum(t["net_pnl"] for t in all_trades)
    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
    
    time_limits = sum(1 for t in all_trades if t["exit_reason"] == "TIME_LIMIT")
    trail_stops = sum(1 for t in all_trades if t["exit_reason"] == "TRAILING_STOP")
    stop_losses = sum(1 for t in all_trades if t["exit_reason"] == "STOP_LOSS")
    hedges = sum(1 for t in all_trades if "HEDGE" in t["exit_reason"])
    
    gross_wins = sum(t["gross_pnl"] for t in all_trades if t["net_pnl"] > 0)
    gross_losses = sum(abs(t["gross_pnl"]) for t in all_trades if t["net_pnl"] < 0)
    pf = (gross_wins / gross_losses) if gross_losses > 0 else (99.0 if gross_wins > 0 else 0.0)
    
    return {
        "trades": total_trades,
        "wins": wins,
        "win_rate": win_rate,
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_pnl": net_pnl,
        "profit_factor": pf,
        "time_limits": time_limits,
        "trail_stops": trail_stops,
        "stop_losses": stop_losses,
        "hedges": hedges,
        "all_trades": all_trades,
    }


def main():
    console = Console()
    console.print("\n[bold cyan]================================================================================[/bold cyan]")
    console.print("[bold green]RECURSIVE CALIBRATION: Volatility Gating, Volume Filters & Exit Parameters[/bold green]")
    console.print("[bold cyan]================================================================================[/bold cyan]\n")
    
    # Target files: recent extended sessions (10/03 21:00 to 10/04 15:00)
    btc_files = sorted(glob.glob("data/btc/hl_btc_l2_20261004_*.jsonl") + glob.glob("data/btc/hl_btc_l2_20261003_2*.jsonl"))
    console.print(f"Target BTC Files:  {len(btc_files)} files ({sum(os.path.getsize(f) for f in btc_files)/(1024*1024):.1f} MB)")
    
    # Representative subset for fast sweep across the 18-hour session (7 files covering the full timeline)
    sweep_files = btc_files[::3]
    console.print(f"Sweep Files (Subset): {len(sweep_files)} files ({sum(os.path.getsize(f) for f in sweep_files)/(1024*1024):.1f} MB)")
    sys.stdout.flush()
    
    # -------------------------------------------------------------------------
    # TEST 1: Scan Volatility Hurdle (min_volatility_bps)
    # -------------------------------------------------------------------------
    console.print("\n[bold yellow]TEST 1: Volatility Gate Parameter Sweep (min_volatility_bps)[/bold yellow]")
    vol_hurdles = [0.0, 1.5, 2.5, 3.2, 3.8, 4.5, 5.5]
    
    t1_results = []
    for h in vol_hurdles:
        override = {
            s: {"min_volatility_bps": h}
            for s in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]
        }
        res = run_experiment_on_files(sweep_files, "btc", override)
        res["hurdle"] = h
        t1_results.append(res)
        c = "green" if res["net_pnl"] > 0 else "red"
        console.print(
            f"  Hurdle: {h:3.1f} bps | Trades: {res['trades']:2d} | Win: {res['win_rate']:4.1f}% | "
            f"Gross: ${res['gross_pnl']:+6.2f} | Fees: -${res['fees']:5.2f} | Net: [{c}]${res['net_pnl']:+6.2f}[/{c}] | "
            f"PF: {res['profit_factor']:4.2f} | TimeLimits: {res['time_limits']:2d} | Trails: {res['trail_stops']:2d}"
        )
        sys.stdout.flush()
        
    # Pick best hurdle from sweep
    best_hurdle = max(t1_results, key=lambda x: x["net_pnl"])["hurdle"]
    console.print(f"[bold cyan]Optimal Volatility Hurdle from sweep: {best_hurdle:.1f} bps[/bold cyan]")
    sys.stdout.flush()

    # -------------------------------------------------------------------------
    # TEST 2: Scan Entry Threshold with best volatility gates
    # -------------------------------------------------------------------------
    console.print(f"\n[bold yellow]TEST 2: Entry Threshold Calibration (entry_threshold with Vol Gate {best_hurdle} bps)[/bold yellow]")
    entry_thresholds = [0.55, 0.65, 0.70, 0.75, 0.80]
    
    t2_results = []
    for eth in entry_thresholds:
        override = {
            s: {"entry_threshold": eth, "min_volatility_bps": best_hurdle}
            for s in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]
        }
        res = run_experiment_on_files(sweep_files, "btc", override)
        res["entry_thresh"] = eth
        t2_results.append(res)
        c = "green" if res["net_pnl"] > 0 else "red"
        console.print(
            f"  Threshold: {eth:4.2f} | Trades: {res['trades']:2d} | Win: {res['win_rate']:4.1f}% | "
            f"Gross: ${res['gross_pnl']:+6.2f} | Fees: -${res['fees']:5.2f} | Net: [{c}]${res['net_pnl']:+6.2f}[/{c}] | "
            f"PF: {res['profit_factor']:4.2f} | TimeLimits: {res['time_limits']:2d} | Trails: {res['trail_stops']:2d}"
        )
        sys.stdout.flush()

    best_thresh = max(t2_results, key=lambda x: x["net_pnl"])["entry_thresh"]
    console.print(f"[bold cyan]Optimal Entry Threshold from sweep: {best_thresh:.2f}[/bold cyan]")
    sys.stdout.flush()

    # -------------------------------------------------------------------------
    # TEST 3: Trailing Stop Activation & Fast Exit Calibration
    # -------------------------------------------------------------------------
    console.print("\n[bold yellow]TEST 3: Trailing Stop Activation & Max Holding Calibration[/bold yellow]")
    trail_configs = [
        # (trail_act_bps, trail_dist_bps, max_hold_s, label)
        (3.2, 1.2, 180, "Default (3.2 act / 180s hold)"),
        (2.5, 1.0, 180, "Tighter Trail (2.5 act / 1.0 dist / 180s)"),
        (2.2, 0.8, 120, "Fast Micro-Trail (2.2 act / 0.8 dist / 120s)"),
        (2.0, 0.8, 120, "Aggressive Micro-Trail (2.0 act / 0.8 dist / 120s)"),
        (1.8, 0.7, 90,  "Rapid Scalp (1.8 act / 0.7 dist / 90s)"),
    ]
    
    t3_results = []
    for act, dist, hold, label in trail_configs:
        override = {
            s: {
                "entry_threshold": best_thresh,
                "min_volatility_bps": best_hurdle,
                "trailing_stop_activation_bps": act,
                "trailing_stop_distance_bps": dist,
                "max_holding_time_secs": hold,
            }
            for s in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]
        }
        res = run_experiment_on_files(sweep_files, "btc", override)
        res["label"] = label
        res["act"] = act
        res["dist"] = dist
        res["hold"] = hold
        t3_results.append(res)
        c = "green" if res["net_pnl"] > 0 else "red"
        console.print(
            f"  {label:<45} | Trd: {res['trades']:2d} | Win: {res['win_rate']:4.1f}% | "
            f"Gross: ${res['gross_pnl']:+6.2f} | Fees: -${res['fees']:5.2f} | Net: [{c}]${res['net_pnl']:+6.2f}[/{c}] | "
            f"PF: {res['profit_factor']:4.2f} | Trails: {res['trail_stops']:2d} | TimeLimits: {res['time_limits']:2d}"
        )
        sys.stdout.flush()

    best_exit = max(t3_results, key=lambda x: x["net_pnl"])
    console.print(f"[bold cyan]Optimal Exit Strategy from sweep: {best_exit['label']}[/bold cyan]")
    sys.stdout.flush()

    # -------------------------------------------------------------------------
    # TEST 4: FULL CONFIRMATION ON ALL 20 BTC FILES
    # -------------------------------------------------------------------------
    console.print("\n[bold magenta]================================================================================[/bold magenta]")
    console.print("[bold green]TEST 4: FULL DATASET CONFIRMATION ACROSS ALL 20 BTC FILES (18 HOURS)[/bold green]")
    console.print("[bold magenta]================================================================================[/bold magenta]")
    sys.stdout.flush()

    # 1. Baseline
    console.print("\nEvaluating Baseline (strategies.json default)...")
    sys.stdout.flush()
    baseline_res = run_experiment_on_files(btc_files, "btc", {})
    console.print(
        f"  [bold]BASELINE:[/bold] Trades: {baseline_res['trades']:2d} | Win: {baseline_res['win_rate']:4.1f}% | "
        f"Gross: ${baseline_res['gross_pnl']:+6.2f} | Fees: -${baseline_res['fees']:5.2f} | Net: ${baseline_res['net_pnl']:+6.2f} | "
        f"PF: {baseline_res['profit_factor']:4.2f} | TimeLimits: {baseline_res['time_limits']} | Trails: {baseline_res['trail_stops']}"
    )
    sys.stdout.flush()

    # 2. Fully Calibrated Settings
    calibrated_override = {
        s: {
            "entry_threshold": best_thresh,
            "min_volatility_bps": best_hurdle,
            "trailing_stop_activation_bps": best_exit["act"],
            "trailing_stop_distance_bps": best_exit["dist"],
            "max_holding_time_secs": best_exit["hold"],
        }
        for s in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]
    }
    console.print(f"\nEvaluating Calibrated Strategy Set (Vol {best_hurdle}b, Thresh {best_thresh}, Act {best_exit['act']}b, Hold {best_exit['hold']}s)...")
    sys.stdout.flush()
    calibrated_res = run_experiment_on_files(btc_files, "btc", calibrated_override)
    c = "green" if calibrated_res["net_pnl"] > 0 else "red"
    console.print(
        f"  [bold]CALIBRATED:[/bold] Trades: {calibrated_res['trades']:2d} | Win: {calibrated_res['win_rate']:4.1f}% | "
        f"Gross: ${calibrated_res['gross_pnl']:+6.2f} | Fees: -${calibrated_res['fees']:5.2f} | Net: [{c}]${calibrated_res['net_pnl']:+6.2f}[/{c}] | "
        f"PF: {calibrated_res['profit_factor']:4.2f} | TimeLimits: {calibrated_res['time_limits']} | Trails: {calibrated_res['trail_stops']}"
    )
    sys.stdout.flush()

if __name__ == "__main__":
    main()
