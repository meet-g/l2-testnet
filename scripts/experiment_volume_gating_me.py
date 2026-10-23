"""Rigorous High-Throughput Volume Gating Experimentation for Momentum Expansion Strategy.

Replays all large recent sessions across Hyperliquid L2 datasets (HYPE & BTC)
to benchmark, evaluate, and optimize different levels and mechanisms of Volume Gating:
1. Taker Flow / CVD Volume Impulse Hurdle (flow_hurdle)
2. Rolling Traded Gross Volume Gating (min_trade_vol_window)
3. Rolling Amplitude Volatility Gating (min_volatility_bps)
4. Combined Multi-Factor Gating Matrix
"""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import glob
import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rich.console import Console
from rich.table import Table

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


@dataclass
class ReplayFileResult:
    filename: str
    coin: str
    size_mb: float
    trades: List[Dict[str, Any]]
    events_count: int
    elapsed_s: float
    error: Optional[str] = None


def replay_single_session_worker(
    filepath: str,
    coin: str,
    flow_hurdle: float = 0.18,
    min_trade_vol: float = 0.0,
    min_vol_bps: float = 4.5,
    entry_threshold: float = 0.74,
) -> ReplayFileResult:
    """Worker function to replay a single L2 recording file with specific gating parameters."""
    filename = os.path.basename(filepath)
    size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)
    t0 = time.time()

    cfg = AppConfig()
    cfg.market.coin = coin.upper()
    if coin.upper() == "HYPE":
        cfg.backtest.order_size_btc = 95.0
    elif coin.upper() == "BTC":
        cfg.backtest.order_size_btc = 0.1
    elif coin.upper() == "ETH":
        cfg.backtest.order_size_btc = 3.0
    elif coin.upper() == "SOL":
        cfg.backtest.order_size_btc = 50.0

    cfg.strategies = StrategiesConfig.load("strategies.json")
    if "AdaptiveML" in cfg.strategies.alpha_signals:
        cfg.strategies.alpha_signals["AdaptiveML"].enabled = False

    # Configure Momentum_Expansion as the active focus strategy
    for s_name, s_cfg in cfg.strategies.execution_strategies.items():
        if s_name == "Momentum_Expansion":
            s_cfg.enabled = True
            s_cfg.min_volatility_bps = min_vol_bps
            s_cfg.entry_threshold = entry_threshold
        else:
            s_cfg.enabled = False

    runner = L2EngineRunner(config=cfg, record_data=False, enable_audit=False)

    # Set custom volume gating on MomentumExpansionSignal
    if hasattr(runner.alpha_model, "signal_mom") and runner.alpha_model.signal_mom:
        runner.alpha_model.signal_mom.flow_hurdle = flow_hurdle
        runner.alpha_model.signal_mom.min_trade_vol_window = min_trade_vol

    replay = L2ReplayEngine(filepath, speed_multiplier=100000.0)

    last_eval_ms = 0
    eval_interval_ms = int(1000 / max(cfg.sample_rate_hz, 1))
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
        return ReplayFileResult(
            filename=filename,
            coin=coin,
            size_mb=size_mb,
            trades=[],
            events_count=events_count,
            elapsed_s=time.time() - t0,
            error=str(e),
        )

    st = runner.evaluator.strategies.get("Momentum_Expansion")
    trade_dicts = []
    if st and st.trades:
        for t in st.trades:
            trade_dicts.append({
                "trade_id": getattr(t, "trade_id", ""),
                "side": t.side,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "size_btc": t.size_btc,
                "gross_pnl": t.gross_pnl_usd,
                "fees": t.fees_usd,
                "net_pnl": t.net_pnl_usd,
                "return_bps": t.return_bps,
                "exit_reason": t.exit_reason,
                "holding_secs": (t.exit_time_ms - t.entry_time_ms) / 1000.0,
                "session_file": filename,
                "coin": coin,
            })

    return ReplayFileResult(
        filename=filename,
        coin=coin,
        size_mb=size_mb,
        trades=trade_dicts,
        events_count=events_count,
        elapsed_s=time.time() - t0,
    )


def aggregate_trades(all_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(all_trades)
    if n == 0:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "gross_pnl": 0.0,
            "fees": 0.0,
            "net_pnl": 0.0,
            "profit_factor": 0.0,
            "avg_return_bps": 0.0,
            "avg_win_usd": 0.0,
            "avg_loss_usd": 0.0,
            "tp_count": 0,
            "trailing_count": 0,
            "hedge_count": 0,
            "stop_count": 0,
            "decay_count": 0,
            "time_limit_count": 0,
            "max_drawdown": 0.0,
        }

    wins = [t for t in all_trades if t["net_pnl"] > 0]
    losses = [t for t in all_trades if t["net_pnl"] <= 0]
    gross_wins = sum(t["gross_pnl"] for t in wins)
    gross_losses = sum(abs(t["gross_pnl"]) for t in losses)

    gross_pnl = sum(t["gross_pnl"] for t in all_trades)
    fees = sum(t["fees"] for t in all_trades)
    net_pnl = sum(t["net_pnl"] for t in all_trades)
    win_rate = (len(wins) / n) * 100.0
    pf = (gross_wins / gross_losses) if gross_losses > 0 else (99.0 if gross_wins > 0 else 0.0)
    avg_return_bps = sum(t["return_bps"] for t in all_trades) / n
    avg_win_usd = (sum(t["net_pnl"] for t in wins) / len(wins)) if wins else 0.0
    avg_loss_usd = (sum(t["net_pnl"] for t in losses) / len(losses)) if losses else 0.0

    # Drawdown calculation
    cum_pnl = 0.0
    peak_pnl = 0.0
    max_dd = 0.0
    for t in all_trades:
        cum_pnl += t["net_pnl"]
        peak_pnl = max(peak_pnl, cum_pnl)
        dd = peak_pnl - cum_pnl
        max_dd = max(max_dd, dd)

    tp_count = sum(1 for t in all_trades if t["exit_reason"] == "TAKE_PROFIT")
    trailing_count = sum(1 for t in all_trades if t["exit_reason"] == "TRAILING_STOP")
    hedge_count = sum(1 for t in all_trades if "HEDGE" in t["exit_reason"])
    stop_count = sum(1 for t in all_trades if t["exit_reason"] == "STOP_LOSS")
    decay_count = sum(1 for t in all_trades if "DECAY" in t["exit_reason"])
    time_limit_count = sum(1 for t in all_trades if "TIME" in t["exit_reason"])

    by_coin = {}
    for coin_name in sorted(list(set(t.get("coin", "UNKNOWN") for t in all_trades))):
        c_trds = [t for t in all_trades if t.get("coin") == coin_name]
        c_w = [t for t in c_trds if t["net_pnl"] > 0]
        c_gw = sum(t["gross_pnl"] for t in c_w)
        c_l = [t for t in c_trds if t["net_pnl"] <= 0]
        c_gl = sum(abs(t["gross_pnl"]) for t in c_l)
        by_coin[coin_name] = {
            "trades": len(c_trds),
            "wins": len(c_w),
            "win_rate": (len(c_w) / len(c_trds) * 100.0) if c_trds else 0.0,
            "net_pnl": sum(t["net_pnl"] for t in c_trds),
            "gross_pnl": sum(t["gross_pnl"] for t in c_trds),
            "fees": sum(t["fees"] for t in c_trds),
            "profit_factor": (c_gw / c_gl) if c_gl > 0 else (99.0 if c_gw > 0 else 0.0),
        }

    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_pnl": net_pnl,
        "profit_factor": pf,
        "avg_return_bps": avg_return_bps,
        "avg_win_usd": avg_win_usd,
        "avg_loss_usd": avg_loss_usd,
        "tp_count": tp_count,
        "trailing_count": trailing_count,
        "hedge_count": hedge_count,
        "stop_count": stop_count,
        "decay_count": decay_count,
        "time_limit_count": time_limit_count,
        "max_drawdown": max_dd,
        "by_coin": by_coin,
    }


def run_experiment_grid(
    sessions: List[Tuple[str, str]],
    flow_hurdles: List[float],
    min_trade_vols: List[float],
    min_vol_bps_list: List[float],
    max_workers: int = 10,
) -> List[Dict[str, Any]]:
    results = []

    for fh in flow_hurdles:
        for mtv in min_trade_vols:
            for mv in min_vol_bps_list:
                t0 = time.time()
                tasks = []
                with ProcessPoolExecutor(max_workers=max_workers) as executor:
                    futures = [
                        executor.submit(
                            replay_single_session_worker,
                            fpath,
                            coin,
                            flow_hurdle=fh,
                            min_trade_vol=mtv,
                            min_vol_bps=mv,
                        )
                        for fpath, coin in sessions
                    ]
                    all_trades = []
                    for fut in futures:
                        res = fut.result()
                        all_trades.extend(res.trades)

                agg = aggregate_trades(all_trades)
                elapsed = time.time() - t0
                agg["flow_hurdle"] = fh
                agg["min_trade_vol"] = mtv
                agg["min_vol_bps"] = mv
                agg["elapsed_s"] = elapsed
                agg["all_trades"] = all_trades
                results.append(agg)
                hype_pnl = agg["by_coin"].get("HYPE", {}).get("net_pnl", 0.0)
                btc_pnl = agg["by_coin"].get("BTC", {}).get("net_pnl", 0.0)
                print(
                    f"Flow: {fh:4.2f} | VolGate: {mtv:3.1f} | AmpGate: {mv:3.1f}b | "
                    f"Trd: {agg['trades']:3d} | Win%: {agg['win_rate']:4.1f}% | "
                    f"Gross: ${agg['gross_pnl']:+7.2f} | Fees: ${agg['fees']:6.2f} | "
                    f"Net: ${agg['net_pnl']:+7.2f} [HYPE: ${hype_pnl:+6.2f}, BTC: ${btc_pnl:+6.2f}] | "
                    f"PF: {agg['profit_factor']:4.2f} | Hedges: {agg['hedge_count']:2d} | Trails: {agg['trailing_count']:2d} | ({elapsed:.1f}s)"
                )
                sys.stdout.flush()

    return results


def main():
    console = Console()
    console.print("\n[bold cyan]========================================================================================[/bold cyan]")
    console.print("[bold green]MOMENTUM EXPANSION: ADVANCED VOLUME GATING & REPLAY EXPERIMENTATION ENGINE[/bold green]")
    console.print("[bold cyan]========================================================================================[/bold cyan]\n")

    # 1. Discover all large recent sessions
    # Recent HYPE sessions from Oct 20 to 23 >= 6.0 MB
    hype_files = sorted(
        [f for f in glob.glob("data/hype/hl_hype_l2_2026102*.jsonl") if os.path.getsize(f) >= 6.0 * 1024 * 1024],
        key=os.path.getmtime,
        reverse=True,
    )
    # Recent BTC sessions from Oct 08-09 >= 6.5 MB
    btc_files = sorted(
        [f for f in glob.glob("data/btc/hl_btc_l2_2026100*.jsonl") if os.path.getsize(f) >= 6.5 * 1024 * 1024],
        key=os.path.getmtime,
        reverse=True,
    )[:8]

    target_sessions = [(f, "HYPE") for f in hype_files] + [(f, "BTC") for f in btc_files]
    total_mb = sum(os.path.getsize(f) for f, _ in target_sessions) / (1024.0 * 1024.0)

    console.print(f"Total Large Recent Sessions: [bold yellow]{len(target_sessions)} files[/bold yellow] ([bold cyan]{total_mb:.1f} MB[/bold cyan])")
    console.print(f"  - HYPE Recent Large (Oct 20-23): [bold yellow]{len(hype_files)} files[/bold yellow] ({sum(os.path.getsize(f) for f in hype_files)/(1024*1024):.1f} MB)")
    console.print(f"  - BTC Recent Large (Oct 08-09):  [bold yellow]{len(btc_files)} files[/bold yellow] ({sum(os.path.getsize(f) for f in btc_files)/(1024*1024):.1f} MB)\n")

    # -------------------------------------------------------------------------
    # TEST 1: Taker Flow / CVD Volume Impulse Hurdle (flow_hurdle)
    # -------------------------------------------------------------------------
    console.print("[bold magenta]----------------------------------------------------------------------------------------[/bold magenta]")
    console.print("[bold yellow]EXPERIMENT 1: Taker Flow / CVD Impulse Volume Hurdle (flow_hurdle)[/bold yellow]")
    console.print("[bold magenta]----------------------------------------------------------------------------------------[/bold magenta]")
    console.print("Filters momentum entries to require minimum active institutional taker flow intensity [0.10 to 0.65]\n")
    sys.stdout.flush()

    flow_hurdles = [0.10, 0.18, 0.25, 0.35, 0.45, 0.55, 0.65]
    t1_results = run_experiment_grid(
        target_sessions,
        flow_hurdles=flow_hurdles,
        min_trade_vols=[0.0],
        min_vol_bps_list=[4.5],  # default volatility gate
        max_workers=10,
    )

    best_fh = max(t1_results, key=lambda x: x["net_pnl"])["flow_hurdle"]
    console.print(f"\n[bold green]>>> Optimal Flow Hurdle: {best_fh:.2f}[/bold green]\n")

    # -------------------------------------------------------------------------
    # TEST 2: Gross Rolling Traded Volume Gating (min_trade_vol)
    # -------------------------------------------------------------------------
    console.print("[bold magenta]----------------------------------------------------------------------------------------[/bold magenta]")
    console.print(f"[bold yellow]EXPERIMENT 2: Gross Rolling Traded Volume Gating (min_trade_vol with Flow {best_fh})[/bold yellow]")
    console.print("[bold magenta]----------------------------------------------------------------------------------------[/bold magenta]")
    console.print("Requires minimum total executed volume (buy+sell) in rolling 60s window before entry [0.0 to 8.0 units]\n")
    sys.stdout.flush()

    trade_vols = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0]
    t2_results = run_experiment_grid(
        target_sessions,
        flow_hurdles=[best_fh],
        min_trade_vols=trade_vols,
        min_vol_bps_list=[4.5],
        max_workers=10,
    )

    best_tv = max(t2_results, key=lambda x: x["net_pnl"])["min_trade_vol"]
    console.print(f"\n[bold green]>>> Optimal Rolling Trade Volume Gate: {best_tv:.1f}[/bold green]\n")

    # -------------------------------------------------------------------------
    # TEST 3: Volatility Amplitude Gating (min_volatility_bps)
    # -------------------------------------------------------------------------
    console.print("[bold magenta]----------------------------------------------------------------------------------------[/bold magenta]")
    console.print(f"[bold yellow]EXPERIMENT 3: Volatility Amplitude Gating (min_volatility_bps with Flow {best_fh}, Vol {best_tv})[/bold yellow]")
    console.print("[bold magenta]----------------------------------------------------------------------------------------[/bold magenta]")
    console.print("Filters out dead chop based on rolling 3-minute mid-price amplitude [0.0 to 6.5 bps]\n")
    sys.stdout.flush()

    vol_amps = [0.0, 2.5, 3.5, 4.5, 5.5, 6.5]
    t3_results = run_experiment_grid(
        target_sessions,
        flow_hurdles=[best_fh],
        min_trade_vols=[best_tv],
        min_vol_bps_list=vol_amps,
        max_workers=10,
    )

    best_va = max(t3_results, key=lambda x: x["net_pnl"])["min_vol_bps"]
    console.print(f"\n[bold green]>>> Optimal Volatility Gate: {best_va:.1f} bps[/bold green]\n")

    # -------------------------------------------------------------------------
    # TEST 4: Multi-Dimensional Cross-Optimization Grid
    # -------------------------------------------------------------------------
    console.print("[bold magenta]----------------------------------------------------------------------------------------[/bold magenta]")
    console.print("[bold yellow]EXPERIMENT 4: Multi-Dimensional Volume & Volatility Synergy Grid[/bold yellow]")
    console.print("[bold magenta]----------------------------------------------------------------------------------------[/bold magenta]\n")
    sys.stdout.flush()

    grid_fh = [best_fh, 0.35, 0.45]
    grid_tv = [0.0, 1.0, 2.0]
    grid_va = [3.5, 4.5, 5.5]
    # Deduplicate
    grid_fh = sorted(list(set(grid_fh)))
    grid_tv = sorted(list(set(grid_tv)))
    grid_va = sorted(list(set(grid_va)))

    t4_results = run_experiment_grid(
        target_sessions,
        flow_hurdles=grid_fh,
        min_trade_vols=grid_tv,
        min_vol_bps_list=grid_va,
        max_workers=10,
    )

    best_global = max(t4_results, key=lambda x: x["net_pnl"])
    console.print(
        f"\n[bold green]>>> GLOBAL OPTIMUM: Flow Hurdle = {best_global['flow_hurdle']:.2f} | "
        f"Trade Vol = {best_global['min_trade_vol']:.1f} | Volatility = {best_global['min_vol_bps']:.1f} bps[/bold green]\n"
    )

    # -------------------------------------------------------------------------
    # TEST 5: Baseline vs Calibrated Comparison
    # -------------------------------------------------------------------------
    console.print("[bold magenta]----------------------------------------------------------------------------------------[/bold magenta]")
    console.print("[bold yellow]EXPERIMENT 5: HEAD-TO-HEAD COMPARISON: Baseline vs Calibrated Volume Gating[/bold yellow]")
    console.print("[bold magenta]----------------------------------------------------------------------------------------[/bold magenta]\n")

    baseline_res = next((r for r in t1_results if r["flow_hurdle"] == 0.18 and r["min_trade_vol"] == 0.0 and r["min_vol_bps"] == 4.5), None)
    if not baseline_res:
        baseline_res = run_experiment_grid(
            target_sessions,
            flow_hurdles=[0.18],
            min_trade_vols=[0.0],
            min_vol_bps_list=[4.5],
            max_workers=10,
        )[0]

    comparison_table = Table(title="Momentum Expansion: Baseline vs Calibrated Volume Gating Matrix", header_style="bold cyan")
    comparison_table.add_column("Configuration", justify="left")
    comparison_table.add_column("Trades", justify="right")
    comparison_table.add_column("Win Rate", justify="right")
    comparison_table.add_column("Gross PnL", justify="right")
    comparison_table.add_column("Fees", justify="right")
    comparison_table.add_column("Net PnL", justify="right")
    comparison_table.add_column("Profit Factor", justify="right")
    comparison_table.add_column("Max DD", justify="right")
    comparison_table.add_column("Hedges", justify="right")
    comparison_table.add_column("Trails", justify="right")
    comparison_table.add_column("Decay Exits", justify="right")

    for name, res in [("BASELINE (Uncalibrated)", baseline_res), ("CALIBRATED (Optimal Volume Gate)", best_global)]:
        c = "green" if res["net_pnl"] > 0 else "red"
        comparison_table.add_row(
            name,
            str(res["trades"]),
            f"{res['win_rate']:.1f}%",
            f"${res['gross_pnl']:+.2f}",
            f"${res['fees']:.2f}",
            f"[{c}]${res['net_pnl']:+.2f}[/{c}]",
            f"{res['profit_factor']:.2f}",
            f"${res['max_drawdown']:.2f}",
            str(res["hedge_count"]),
            str(res["trailing_count"]),
            str(res["decay_count"]),
        )
    console.print(comparison_table)

    # Save results to json
    summary_data = {
        "dataset_files": [f for f, _ in target_sessions],
        "total_files": len(target_sessions),
        "total_mb": total_mb,
        "exp1_flow_hurdle": [{k: v for k, v in r.items() if k != "all_trades"} for r in t1_results],
        "exp2_trade_vol": [{k: v for k, v in r.items() if k != "all_trades"} for r in t2_results],
        "exp3_volatility_amp": [{k: v for k, v in r.items() if k != "all_trades"} for r in t3_results],
        "exp4_grid": [{k: v for k, v in r.items() if k != "all_trades"} for r in t4_results],
        "baseline": {k: v for k, v in baseline_res.items() if k != "all_trades"},
        "optimal": {k: v for k, v in best_global.items() if k != "all_trades"},
    }

    os.makedirs("reports", exist_ok=True)
    with open("reports/momentum_volume_gating_experiment.json", "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    console.print("\n[bold green]Experiment results successfully saved to reports/momentum_volume_gating_experiment.json![/bold green]\n")


if __name__ == "__main__":
    main()
