"""Compare Original Momentum Expansion vs Calibrated Volume-Gated Version across ALL Large HYPE Sessions.

Replays all large HYPE recording sessions (>= 7.0 MB) in data/hype/
comparing the original strategy configuration against the new calibrated
volume-gated architecture.
"""

from concurrent.futures import ProcessPoolExecutor
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


def replay_file_worker(args: Tuple[str, Dict[str, Any]]) -> Dict[str, Any]:
    filepath, params = args
    filename = os.path.basename(filepath)
    size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)
    t0 = time.time()

    cfg = AppConfig()
    cfg.market.coin = "HYPE"
    cfg.backtest.order_size_btc = 95.0
    cfg.strategies = StrategiesConfig.load("strategies.json")
    if "AdaptiveML" in cfg.strategies.alpha_signals:
        cfg.strategies.alpha_signals["AdaptiveML"].enabled = False

    # Apply strategy configuration
    for s_name, s_cfg in cfg.strategies.execution_strategies.items():
        if s_name == "Momentum_Expansion":
            s_cfg.enabled = True
            s_cfg.entry_threshold = params.get("entry_threshold", 0.74)
            s_cfg.min_volatility_bps = params.get("min_volatility_bps", 4.5)
            s_cfg.hedge_trigger_loss_bps = params.get("hedge_trigger_loss_bps", -3.5)
            s_cfg.hedge_reversal_threshold = params.get("hedge_reversal_threshold", 0.20)
        else:
            s_cfg.enabled = False

    runner = L2EngineRunner(config=cfg, record_data=False, enable_audit=False)

    # Set volume gating on MomentumExpansionSignal
    if hasattr(runner.alpha_model, "signal_mom") and runner.alpha_model.signal_mom:
        runner.alpha_model.signal_mom.flow_hurdle = params.get("flow_hurdle", 0.35)
        runner.alpha_model.signal_mom.min_trade_vol_window = params.get("min_trade_vol", 8.0)

    replay = L2ReplayEngine(filepath, speed_multiplier=100000.0)

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
            "trades": [],
            "elapsed_s": time.time() - t0,
            "error": str(e),
        }

    st = runner.evaluator.strategies.get("Momentum_Expansion")
    trade_dicts = []
    if st and st.trades:
        for t in st.trades:
            trade_dicts.append({
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
            })

    return {
        "filename": filename,
        "filepath": filepath,
        "size_mb": size_mb,
        "trades": trade_dicts,
        "elapsed_s": time.time() - t0,
        "error": None,
    }


def aggregate_trades_list(all_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(all_trades)
    if n == 0:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "profit_factor": 0.0,
            "avg_return_bps": 0.0, "tp_count": 0, "trailing_count": 0,
            "hedge_count": 0, "stop_count": 0, "decay_count": 0, "time_limit_count": 0,
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

    cum_pnl = 0.0
    peak_pnl = 0.0
    max_dd = 0.0
    for t in all_trades:
        cum_pnl += t["net_pnl"]
        peak_pnl = max(peak_pnl, cum_pnl)
        dd = peak_pnl - cum_pnl
        max_dd = max(max_dd, dd)

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
        "tp_count": sum(1 for t in all_trades if t["exit_reason"] == "TAKE_PROFIT"),
        "trailing_count": sum(1 for t in all_trades if t["exit_reason"] == "TRAILING_STOP"),
        "hedge_count": sum(1 for t in all_trades if "HEDGE" in t["exit_reason"]),
        "stop_count": sum(1 for t in all_trades if t["exit_reason"] == "STOP_LOSS"),
        "decay_count": sum(1 for t in all_trades if "DECAY" in t["exit_reason"]),
        "time_limit_count": sum(1 for t in all_trades if "TIME" in t["exit_reason"]),
        "max_drawdown": max_dd,
    }


def main():
    console = Console()
    console.print("\n[bold cyan]========================================================================================[/bold cyan]")
    console.print("[bold green]COMPREHENSIVE HYPE AUDIT: ORIGINAL VS CALIBRATED MOMENTUM EXPANSION[/bold green]")
    console.print("[bold cyan]========================================================================================[/bold cyan]\n")

    # Discover ALL large HYPE sessions (>= 7.0 MB)
    data_dir = os.path.join("data", "hype")
    all_files = sorted(
        [f for f in glob.glob(os.path.join(data_dir, "hl_hype_l2_*.jsonl")) if os.path.getsize(f) >= 7.0 * 1024 * 1024],
        key=lambda x: os.path.basename(x),
    )
    total_mb = sum(os.path.getsize(f) for f in all_files) / (1024.0 * 1024.0)

    console.print(f"Target HYPE Large Sessions: [bold yellow]{len(all_files)} files[/bold yellow] ([bold cyan]{total_mb:.1f} MB[/bold cyan])")
    console.print(f"Filter Criteria:            Files >= [bold yellow]7.0 MB[/bold yellow] across entire historical dataset (Oct 5 - Oct 23)\n")

    orig_params = {
        "flow_hurdle": 0.18,
        "min_trade_vol": 0.0,
        "entry_threshold": 0.70,
        "hedge_trigger_loss_bps": -4.0,
        "hedge_reversal_threshold": -0.35,
        "min_volatility_bps": 4.5,
    }

    cal_params = {
        "flow_hurdle": 0.35,
        "min_trade_vol": 8.0,
        "entry_threshold": 0.74,
        "hedge_trigger_loss_bps": -3.5,
        "hedge_reversal_threshold": 0.20,
        "min_volatility_bps": 4.5,
    }

    console.print("[bold yellow]Configuration Comparison:[/bold yellow]")
    console.print("  [bold red]ORIGINAL:[/bold red]   Flow Hurdle = 0.18 | Trade Vol Gate = 0.0 | Entry Thresh = 0.70 | Hedge Trigger = -4.0 bps (Rev: -0.35)")
    console.print("  [bold green]CALIBRATED:[/bold green] Flow Hurdle = 0.35 | Trade Vol Gate = 8.0 | Entry Thresh = 0.74 | Hedge Trigger = -3.5 bps (Rev: +0.20)\n")
    sys.stdout.flush()

    # Pass 1: Replay ORIGINAL across all 76 files
    console.print(f"[bold cyan]Pass 1/2: Running ORIGINAL configuration across all {len(all_files)} large sessions...[/bold cyan]")
    t0 = time.time()
    orig_file_results = []
    with ProcessPoolExecutor(max_workers=10) as executor:
        tasks = [(f, orig_params) for f in all_files]
        for res in executor.map(replay_file_worker, tasks):
            orig_file_results.append(res)
    orig_time = time.time() - t0
    console.print(f"Pass 1 Completed in [bold green]{orig_time:.1f}s[/bold green]!\n")
    sys.stdout.flush()

    # Pass 2: Replay CALIBRATED across all 76 files
    console.print(f"[bold cyan]Pass 2/2: Running CALIBRATED configuration across all {len(all_files)} large sessions...[/bold cyan]")
    t0 = time.time()
    cal_file_results = []
    with ProcessPoolExecutor(max_workers=10) as executor:
        tasks = [(f, cal_params) for f in all_files]
        for res in executor.map(replay_file_worker, tasks):
            cal_file_results.append(res)
    cal_time = time.time() - t0
    console.print(f"Pass 2 Completed in [bold green]{cal_time:.1f}s[/bold green]!\n")
    sys.stdout.flush()

    # Aggregate total trades
    all_orig_trades = []
    for r in orig_file_results:
        all_orig_trades.extend(r["trades"])
    orig_agg = aggregate_trades_list(all_orig_trades)

    all_cal_trades = []
    for r in cal_file_results:
        all_cal_trades.extend(r["trades"])
    cal_agg = aggregate_trades_list(all_cal_trades)

    # -------------------------------------------------------------------------
    # Overall Executive Summary Table
    # -------------------------------------------------------------------------
    console.print("[bold magenta]========================================================================================[/bold magenta]")
    console.print("[bold green]EXECUTIVE SUMMARY: ALL 76 LARGE HYPE SESSIONS (701.9 MB REPLAYED)[/bold green]")
    console.print("[bold magenta]========================================================================================[/bold magenta]\n")

    summary_table = Table(title="Momentum Expansion: All Large HYPE Sessions Benchmark", header_style="bold cyan")
    summary_table.add_column("Performance Metric", justify="left")
    summary_table.add_column("Original Config", justify="right")
    summary_table.add_column("Calibrated (Volume Gated)", justify="right")
    summary_table.add_column("Absolute Delta", justify="right", style="bold")
    summary_table.add_column("Relative Improvement", justify="right", style="bold")

    metrics = [
        ("Total Trades", f"{orig_agg['trades']}", f"{cal_agg['trades']}", f"{cal_agg['trades'] - orig_agg['trades']:+d}", f"{(cal_agg['trades'] - orig_agg['trades'])/max(orig_agg['trades'],1)*100:+.1f}%"),
        ("Win Rate (%)", f"{orig_agg['win_rate']:.1f}%", f"{cal_agg['win_rate']:.1f}%", f"{cal_agg['win_rate'] - orig_agg['win_rate']:+.1f}%", f"{(cal_agg['win_rate'] - orig_agg['win_rate']):+.1f} pts"),
        ("Gross PnL ($)", f"${orig_agg['gross_pnl']:+8.2f}", f"${cal_agg['gross_pnl']:+8.2f}", f"${cal_agg['gross_pnl'] - orig_agg['gross_pnl']:+8.2f}", f"{(cal_agg['gross_pnl'] - orig_agg['gross_pnl'])/max(abs(orig_agg['gross_pnl']),1e-4)*100:+.1f}%"),
        ("Exchange Fees ($)", f"${orig_agg['fees']:8.2f}", f"${cal_agg['fees']:8.2f}", f"${cal_agg['fees'] - orig_agg['fees']:+8.2f}", f"{(cal_agg['fees'] - orig_agg['fees'])/max(orig_agg['fees'],1e-4)*100:+.1f}%"),
        ("Net PnL ($)", f"${orig_agg['net_pnl']:+8.2f}", f"${cal_agg['net_pnl']:+8.2f}", f"${cal_agg['net_pnl'] - orig_agg['net_pnl']:+8.2f}", f"{(cal_agg['net_pnl'] - orig_agg['net_pnl'])/max(abs(orig_agg['net_pnl']),1e-4)*100:+.1f}%"),
        ("Profit Factor", f"{orig_agg['profit_factor']:.2f}", f"{cal_agg['profit_factor']:.2f}", f"{cal_agg['profit_factor'] - orig_agg['profit_factor']:+.2f}", f"{(cal_agg['profit_factor'] - orig_agg['profit_factor'])/max(orig_agg['profit_factor'],1e-4)*100:+.1f}%"),
        ("Fee Drag Ratio (Fees/Gross)", f"{(orig_agg['fees']/max(orig_agg['gross_pnl'],1e-4)*100):.1f}%", f"{(cal_agg['fees']/max(cal_agg['gross_pnl'],1e-4)*100):.1f}%", f"{(cal_agg['fees']/max(cal_agg['gross_pnl'],1e-4)*100) - (orig_agg['fees']/max(orig_agg['gross_pnl'],1e-4)*100):+.1f}%", "Lower is better"),
        ("Max Drawdown ($)", f"${orig_agg['max_drawdown']:.2f}", f"${cal_agg['max_drawdown']:.2f}", f"${cal_agg['max_drawdown'] - orig_agg['max_drawdown']:+.2f}", f"{(cal_agg['max_drawdown'] - orig_agg['max_drawdown'])/max(orig_agg['max_drawdown'],1e-4)*100:+.1f}%"),
        ("Defensive Hedge Exits", f"{orig_agg['hedge_count']}", f"{cal_agg['hedge_count']}", f"{cal_agg['hedge_count'] - orig_agg['hedge_count']:+d}", f"{(cal_agg['hedge_count'] - orig_agg['hedge_count'])/max(orig_agg['hedge_count'],1)*100:+.1f}%"),
        ("Trailing Stop Exits", f"{orig_agg['trailing_count']}", f"{cal_agg['trailing_count']}", f"{cal_agg['trailing_count'] - orig_agg['trailing_count']:+d}", f"{(cal_agg['trailing_count'] - orig_agg['trailing_count'])/max(orig_agg['trailing_count'],1)*100:+.1f}%"),
        ("Take Profit Exits", f"{orig_agg['tp_count']}", f"{cal_agg['tp_count']}", f"{cal_agg['tp_count'] - orig_agg['tp_count']:+d}", f"{(cal_agg['tp_count'] - orig_agg['tp_count'])/max(orig_agg['tp_count'],1)*100:+.1f}%"),
        ("Decay / Chop Exits", f"{orig_agg['decay_count']}", f"{cal_agg['decay_count']}", f"{cal_agg['decay_count'] - orig_agg['decay_count']:+d}", f"{(cal_agg['decay_count'] - orig_agg['decay_count'])/max(orig_agg['decay_count'],1)*100:+.1f}%"),
    ]

    for label, orig_val, cal_val, abs_delta, rel_delta in metrics:
        summary_table.add_row(label, orig_val, cal_val, abs_delta, rel_delta)

    console.print(summary_table)

    # -------------------------------------------------------------------------
    # Session-by-Session Comparison Breakdown (Top 25 Largest Sessions)
    # -------------------------------------------------------------------------
    console.print("\n[bold magenta]========================================================================================[/bold magenta]")
    console.print("[bold green]SESSION-BY-SESSION BREAKDOWN (TOP 25 LARGEST HYPE SESSIONS)[/bold green]")
    console.print("[bold magenta]========================================================================================[/bold magenta]\n")

    session_table = Table(header_style="bold magenta")
    session_table.add_column("Session File", justify="left")
    session_table.add_column("Size", justify="right")
    session_table.add_column("Orig Trd", justify="right")
    session_table.add_column("Orig Win%", justify="right")
    session_table.add_column("Orig Net", justify="right")
    session_table.add_column("Cal Trd", justify="right")
    session_table.add_column("Cal Win%", justify="right")
    session_table.add_column("Cal Net", justify="right")
    session_table.add_column("Delta Net", justify="right", style="bold")
    session_table.add_column("Hedge Delta", justify="right")

    # Match by filename
    orig_by_file = {r["filename"]: r for r in orig_file_results}
    cal_by_file = {r["filename"]: r for r in cal_file_results}

    sorted_files = sorted(all_files, key=os.path.getsize, reverse=True)

    session_data_list = []
    for fpath in sorted_files:
        fn = os.path.basename(fpath)
        sz_mb = os.path.getsize(fpath) / (1024.0 * 1024.0)
        o_res = orig_by_file.get(fn, {"trades": []})
        c_res = cal_by_file.get(fn, {"trades": []})

        o_trds = o_res["trades"]
        c_trds = c_res["trades"]

        o_n = len(o_trds)
        c_n = len(c_trds)

        o_net = sum(t["net_pnl"] for t in o_trds)
        c_net = sum(t["net_pnl"] for t in c_trds)
        delta_net = c_net - o_net

        o_win = (sum(1 for t in o_trds if t["net_pnl"] > 0) / o_n * 100.0) if o_n > 0 else 0.0
        c_win = (sum(1 for t in c_trds if t["net_pnl"] > 0) / c_n * 100.0) if c_n > 0 else 0.0

        o_hedges = sum(1 for t in o_trds if "HEDGE" in t["exit_reason"])
        c_hedges = sum(1 for t in c_trds if "HEDGE" in t["exit_reason"])

        session_data_list.append({
            "filename": fn,
            "size_mb": sz_mb,
            "orig_trades": o_n,
            "orig_win_rate": o_win,
            "orig_net_pnl": o_net,
            "orig_hedges": o_hedges,
            "cal_trades": c_n,
            "cal_win_rate": c_win,
            "cal_net_pnl": c_net,
            "cal_hedges": c_hedges,
            "delta_net": delta_net,
        })

    for s in session_data_list[:25]:
        c_style = "green" if s["delta_net"] > 0 else ("red" if s["delta_net"] < 0 else "white")
        session_table.add_row(
            s["filename"],
            f"{s['size_mb']:.1f} MB",
            f"{s['orig_trades']}",
            f"{s['orig_win_rate']:.0f}%",
            f"${s['orig_net_pnl']:+6.2f}",
            f"{s['cal_trades']}",
            f"{s['cal_win_rate']:.0f}%",
            f"${s['cal_net_pnl']:+6.2f}",
            f"[{c_style}]${s['delta_net']:+6.2f}[/{c_style}]",
            f"{s['cal_hedges'] - s['orig_hedges']:+d}",
        )
    console.print(session_table)

    # -------------------------------------------------------------------------
    # Daily Chronological Breakdown Table
    # -------------------------------------------------------------------------
    console.print("\n[bold magenta]========================================================================================[/bold magenta]")
    console.print("[bold green]CHRONOLOGICAL DAILY PERFORMANCE BREAKDOWN ACROSS LARGE SESSIONS[/bold green]")
    console.print("[bold magenta]========================================================================================[/bold magenta]\n")

    daily_table = Table(header_style="bold yellow")
    daily_table.add_column("Trading Date", justify="left")
    daily_table.add_column("Large Sessions", justify="right")
    daily_table.add_column("Total Size", justify="right")
    daily_table.add_column("Orig Trd", justify="right")
    daily_table.add_column("Orig Win%", justify="right")
    daily_table.add_column("Orig Net", justify="right")
    daily_table.add_column("Cal Trd", justify="right")
    daily_table.add_column("Cal Win%", justify="right")
    daily_table.add_column("Cal Net", justify="right")
    daily_table.add_column("Net PnL Delta", justify="right", style="bold")

    daily_groups = {}
    for s in session_data_list:
        # date from filename: hl_hype_l2_YYYYMMDD_HHMM.jsonl
        parts = s["filename"].split("_")
        d_str = parts[3] if len(parts) >= 4 else "UNKNOWN"
        if d_str not in daily_groups:
            daily_groups[d_str] = []
        daily_groups[d_str].append(s)

    daily_summary_list = []
    for d_str in sorted(daily_groups.keys()):
        group = daily_groups[d_str]
        d_files = len(group)
        d_size = sum(g["size_mb"] for g in group)
        d_orig_trd = sum(g["orig_trades"] for g in group)
        d_cal_trd = sum(g["cal_trades"] for g in group)
        d_orig_net = sum(g["orig_net_pnl"] for g in group)
        d_cal_net = sum(g["cal_net_pnl"] for g in group)
        d_delta_net = d_cal_net - d_orig_net

        d_orig_wins = sum(round(g["orig_win_rate"] * g["orig_trades"] / 100.0) for g in group)
        d_cal_wins = sum(round(g["cal_win_rate"] * g["cal_trades"] / 100.0) for g in group)
        d_orig_win_pct = (d_orig_wins / d_orig_trd * 100.0) if d_orig_trd > 0 else 0.0
        d_cal_win_pct = (d_cal_wins / d_cal_trd * 100.0) if d_cal_trd > 0 else 0.0

        daily_summary_list.append({
            "date": d_str,
            "files": d_files,
            "size_mb": d_size,
            "orig_trades": d_orig_trd,
            "orig_win_rate": d_orig_win_pct,
            "orig_net_pnl": d_orig_net,
            "cal_trades": d_cal_trd,
            "cal_win_rate": d_cal_win_pct,
            "cal_net_pnl": d_cal_net,
            "delta_net": d_delta_net,
        })

        c_style = "green" if d_delta_net > 0 else ("red" if d_delta_net < 0 else "white")
        formatted_date = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]}"
        daily_table.add_row(
            formatted_date,
            f"{d_files}",
            f"{d_size:.1f} MB",
            f"{d_orig_trd}",
            f"{d_orig_win_pct:.1f}%",
            f"${d_orig_net:+7.2f}",
            f"{d_cal_trd}",
            f"{d_cal_win_pct:.1f}%",
            f"${d_cal_net:+7.2f}",
            f"[{c_style}]${d_delta_net:+7.2f}[/{c_style}]",
        )
    console.print(daily_table)

    # Save complete comparison report to JSON
    out_data = {
        "benchmark_name": "Momentum_Expansion_Large_HYPE_Sessions_Comparison",
        "total_files": len(all_files),
        "total_size_mb": total_mb,
        "orig_params": orig_params,
        "cal_params": cal_params,
        "orig_aggregate": orig_agg,
        "cal_aggregate": cal_agg,
        "daily_breakdown": daily_summary_list,
        "sessions": session_data_list,
    }

    os.makedirs("reports", exist_ok=True)
    out_path = "reports/hype_large_sessions_me_comparison.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)

    console.print(f"\n[bold green]Complete comparison data saved to {out_path}![/bold green]\n")


if __name__ == "__main__":
    main()
