"""Comprehensive Multi-Strategy Synergy & Co-Entry Replay Evaluation.

Evaluates the triad of core production alpha strategies:
1. Hedged_Convexity (HEDGED_MAKER, entry_threshold=0.86, signal=HedgedConvexity)
2. Convexity_Cascade (HEDGED_MAKER, entry_threshold=0.80, signal=ConvexityCascade)
3. Momentum_Expansion (HEDGED_MAKER, entry_threshold=0.70, signal=MomentumExpansion, volume-gated)

Concurrently active to verify:
- Cross-strategy synergy & portfolio PnL
- Co-entry protection (+0.04 conviction hurdle and 50% size discount)
- Defensive maker hedge frequency and stop-loss mitigation
- Portfolio equity curve, max drawdown, and capital efficiency
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
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


def detect_coin(filepath: str) -> str:
    fpath_lower = filepath.lower().replace("\\", "/")
    for c in ["btc", "hype", "sol", "eth"]:
        if f"hl_{c}_" in fpath_lower or f"/{c}/" in fpath_lower:
            return c.upper()
    return "HYPE"


def get_coin_order_size(coin: str) -> float:
    c = coin.upper()
    if c == "HYPE":
        return 95.0
    elif c == "SOL":
        return 50.0
    elif c == "ETH":
        return 3.0
    else:
        return 0.1


def replay_synergy_session(args: Tuple[str, str, Dict[str, Any]]) -> Dict[str, Any]:
    filepath, coin, overrides = args
    filename = os.path.basename(filepath)
    size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)
    t0 = time.time()

    cfg = AppConfig()
    cfg.market.coin = coin
    base_order_size = get_coin_order_size(coin)
    cfg.backtest.order_size_btc = base_order_size
    cfg.strategies = StrategiesConfig.load("strategies.json")

    # Disable AdaptiveML to maximize replay throughput since triad strategies use their dedicated signals
    if "AdaptiveML" in cfg.strategies.alpha_signals:
        cfg.strategies.alpha_signals["AdaptiveML"].enabled = False

    # Ensure triad strategies are enabled and calibrated
    strat_keys = ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]
    for s_name, s_cfg in cfg.strategies.execution_strategies.items():
        if s_name in strat_keys:
            s_cfg.enabled = True
            if s_name in overrides:
                for k, v in overrides[s_name].items():
                    setattr(s_cfg, k, v)
        else:
            s_cfg.enabled = False

    runner = L2EngineRunner(config=cfg, record_data=False, enable_audit=False)

    # Set calibrated volume gating on MomentumExpansionSignal
    if hasattr(runner.alpha_model, "signal_mom") and runner.alpha_model.signal_mom:
        runner.alpha_model.signal_mom.flow_hurdle = overrides.get("me_flow_hurdle", 0.35)
        runner.alpha_model.signal_mom.min_trade_vol_window = overrides.get("me_min_trade_vol", 8.0)

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
        return {
            "filename": filename,
            "filepath": filepath,
            "coin": coin,
            "size_mb": size_mb,
            "events_count": events_count,
            "elapsed_s": time.time() - t0,
            "error": str(e),
            "strategies": {},
            "trades": [],
        }

    elapsed_s = time.time() - t0
    strat_results = {}
    all_trades = []

    for s_name in strat_keys:
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

        # Check co-entry trades (trades entered with discounted size <= 60% of base size)
        co_entry_trades = [t for t in trades if t.size_btc < (base_order_size * 0.75)]
        isolated_trades = [t for t in trades if t.size_btc >= (base_order_size * 0.75)]

        strat_results[s_name] = {
            "trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / n * 100.0) if n > 0 else 0.0,
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
            "co_entry_count": len(co_entry_trades),
            "co_entry_wins": len([t for t in co_entry_trades if t.net_pnl_usd > 0]),
            "co_entry_net_pnl": sum(t.net_pnl_usd for t in co_entry_trades),
            "isolated_count": len(isolated_trades),
            "isolated_wins": len([t for t in isolated_trades if t.net_pnl_usd > 0]),
            "isolated_net_pnl": sum(t.net_pnl_usd for t in isolated_trades),
        }

        for t in trades:
            is_co_entry = (t.size_btc < (base_order_size * 0.75))
            all_trades.append({
                "strategy": s_name,
                "coin": coin,
                "file": filename,
                "side": t.side,
                "entry_time_ms": t.entry_time_ms,
                "exit_time_ms": t.exit_time_ms,
                "size": t.size_btc,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "gross_pnl": t.gross_pnl_usd,
                "fees": t.fees_usd,
                "net_pnl": t.net_pnl_usd,
                "return_bps": t.return_bps,
                "exit_reason": t.exit_reason,
                "is_co_entry": is_co_entry,
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
        "trades": all_trades,
    }


def main():
    parser = argparse.ArgumentParser(description="Multi-Strategy Synergy & Co-Entry Replay")
    parser.add_argument("--workers", type=int, default=10, help="Multiprocessing workers")
    parser.add_argument("--all-hype", action="store_true", help="Replay across all large HYPE files (>= 7.0MB)")
    parser.add_argument("--recent-only", action="store_true", default=True, help="Replay across recent large sessions (Oct 20-23 HYPE + Oct 08-09 BTC)")
    args = parser.parse_args()

    console = Console()
    console.print("\n[bold cyan]========================================================================================[/bold cyan]")
    console.print("[bold green]TRIAD MULTI-STRATEGY REPLAY: HEDGED CONVEXITY + CONVEXITY CASCADE + MOMENTUM EXPANSION[/bold green]")
    console.print("[bold cyan]========================================================================================[/bold cyan]\n")

    # Discover target sessions
    if args.all_hype:
        hype_files = sorted(
            [f for f in glob.glob("data/hype/hl_hype_l2_*.jsonl") if os.path.getsize(f) >= 7.0 * 1024 * 1024],
            key=os.path.getmtime,
            reverse=True,
        )
        btc_files = sorted(
            [f for f in glob.glob("data/btc/hl_btc_l2_*.jsonl") if os.path.getsize(f) >= 8.0 * 1024 * 1024],
            key=os.path.getmtime,
            reverse=True,
        )[:8]
    else:
        # Default: 26 recent large sessions (Oct 20-23 HYPE >= 6.0MB + Oct 08-09 BTC >= 6.5MB)
        hype_files = sorted(
            [f for f in glob.glob("data/hype/hl_hype_l2_2026102*.jsonl") if os.path.getsize(f) >= 6.0 * 1024 * 1024],
            key=os.path.getmtime,
            reverse=True,
        )
        btc_files = sorted(
            [f for f in glob.glob("data/btc/hl_btc_l2_2026100*.jsonl") if os.path.getsize(f) >= 6.5 * 1024 * 1024],
            key=os.path.getmtime,
            reverse=True,
        )[:8]

    target_sessions = [(f, "HYPE", {}) for f in hype_files] + [(f, "BTC", {}) for f in btc_files]
    total_mb = sum(os.path.getsize(f) for f, _, _ in target_sessions) / (1024.0 * 1024.0)

    console.print(f"Target Sessions:   [bold yellow]{len(target_sessions)} datasets[/bold yellow] ([bold cyan]{total_mb:.1f} MB[/bold cyan])")
    console.print(f"  - HYPE Sessions: [bold yellow]{len(hype_files)} files[/bold yellow] ({sum(os.path.getsize(f) for f in hype_files)/(1024*1024):.1f} MB)")
    console.print(f"  - BTC Sessions:  [bold yellow]{len(btc_files)} files[/bold yellow] ({sum(os.path.getsize(f) for f in btc_files)/(1024*1024):.1f} MB)")
    console.print(f"Parallel Workers:  [bold yellow]{args.workers} CPU processes[/bold yellow]\n")

    strat_overrides = {
        "Momentum_Expansion": {
            "entry_threshold": 0.70,
            "min_volatility_bps": 4.5,
            "hedge_trigger_loss_bps": -3.5,
            "hedge_reversal_threshold": 0.20,
        },
        "me_flow_hurdle": 0.35,
        "me_min_trade_vol": 8.0,
    }

    t0 = time.time()
    results = []
    tasks = [(f, c, strat_overrides) for f, c, _ in target_sessions]

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(replay_synergy_session, task): task for task in tasks}
        completed = 0
        for fut in as_completed(future_map):
            completed += 1
            res = fut.result()
            results.append(res)
            sess_net = sum(s["net_pnl"] for s in res["strategies"].values()) if not res.get("error") else 0.0
            sess_trd = sum(s["trades"] for s in res["strategies"].values()) if not res.get("error") else 0
            style = "green" if sess_net > 0 else ("red" if sess_net < 0 else "dim")
            console.print(
                f"[{completed:2d}/{len(tasks):2d}] {res['filename']} ({res['size_mb']:4.1f} MB, {res['coin']}) -> "
                f"Trd: {sess_trd:2d} | Net: [{style}]${sess_net:+6.2f}[/{style}] | ({res['elapsed_s']:.1f}s)"
            )
            sys.stdout.flush()

    total_duration = time.time() - t0

    # Sort results by filename
    results.sort(key=lambda r: r["filename"])

    # 1. Per-Session Matrix Table
    console.print("\n[bold cyan]========================================================================================[/bold cyan]")
    console.print("[bold yellow]CROSS-SESSION REPLAY MATRIX: TRIAD CONCURRENT PERFORMANCE[/bold yellow]")
    console.print("[bold cyan]========================================================================================[/bold cyan]")

    tbl = Table(show_header=True, header_style="bold magenta")
    tbl.add_column("Session File", style="dim")
    tbl.add_column("Coin", justify="center")
    tbl.add_column("Size", justify="right")
    tbl.add_column("HC Trd", justify="right")
    tbl.add_column("HC Net", justify="right")
    tbl.add_column("CC Trd", justify="right")
    tbl.add_column("CC Net", justify="right")
    tbl.add_column("ME Trd", justify="right")
    tbl.add_column("ME Net", justify="right")
    tbl.add_column("Tot Trd", justify="right")
    tbl.add_column("Combined Net ($)", justify="right", style="bold")

    strat_keys = ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]
    strat_totals = {
        s: {
            "trades": 0, "wins": 0, "losses": 0, "stops": 0, "hedges": 0, "tps": 0, "trails": 0,
            "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "gross_wins": 0.0, "gross_losses": 0.0,
            "co_entry_count": 0, "co_entry_wins": 0, "co_entry_net_pnl": 0.0,
            "isolated_count": 0, "isolated_wins": 0, "isolated_net_pnl": 0.0,
        }
        for s in strat_keys
    }

    all_trades_flat = []

    for r in results:
        if r.get("error"):
            continue
        all_trades_flat.extend(r["trades"])
        fn = r["filename"]
        cn = r["coin"]
        sz = f"{r['size_mb']:.1f}MB"

        hc = r["strategies"].get("Hedged_Convexity", {})
        cc = r["strategies"].get("Convexity_Cascade", {})
        me = r["strategies"].get("Momentum_Expansion", {})

        s_net = hc.get("net_pnl", 0.0) + cc.get("net_pnl", 0.0) + me.get("net_pnl", 0.0)
        s_trd = hc.get("trades", 0) + cc.get("trades", 0) + me.get("trades", 0)

        for s in strat_keys:
            st = r["strategies"].get(s, {})
            for k in strat_totals[s]:
                strat_totals[s][k] += st.get(k, 0)

        hc_style = "green" if hc.get("net_pnl", 0.0) > 0 else "red"
        cc_style = "green" if cc.get("net_pnl", 0.0) > 0 else "red"
        me_style = "green" if me.get("net_pnl", 0.0) > 0 else "red"
        s_style = "bold green" if s_net > 0 else "bold red"

        tbl.add_row(
            fn,
            cn,
            sz,
            str(hc.get("trades", 0)),
            f"[{hc_style}]${hc.get('net_pnl', 0.0):+6.2f}[/{hc_style}]",
            str(cc.get("trades", 0)),
            f"[{cc_style}]${cc.get('net_pnl', 0.0):+6.2f}[/{cc_style}]",
            str(me.get("trades", 0)),
            f"[{me_style}]${me.get('net_pnl', 0.0):+6.2f}[/{me_style}]",
            str(s_trd),
            f"[{s_style}]${s_net:+6.2f}[/{s_style}]",
        )

    console.print(tbl)

    # 2. Executive Strategy Breakdown Table
    console.print("\n[bold cyan]========================================================================================[/bold cyan]")
    console.print("[bold green]EXECUTIVE STRATEGY BREAKDOWN (TRIAD PORTFOLIO)[/bold green]")
    console.print("[bold cyan]========================================================================================[/bold cyan]")

    sum_tbl = Table(show_header=True, header_style="bold yellow")
    sum_tbl.add_column("Strategy", style="bold")
    sum_tbl.add_column("Trades", justify="right")
    sum_tbl.add_column("Win Rate", justify="right")
    sum_tbl.add_column("Gross PnL ($)", justify="right")
    sum_tbl.add_column("Fees ($)", justify="right")
    sum_tbl.add_column("Net PnL ($)", justify="right", style="bold")
    sum_tbl.add_column("Profit Factor", justify="right")
    sum_tbl.add_column("Stop Losses", justify="right")
    sum_tbl.add_column("Maker Hedges", justify="right")
    sum_tbl.add_column("Trailing/TP", justify="right")

    tot_trades = 0
    tot_wins = 0
    tot_gross = 0.0
    tot_fees = 0.0
    tot_net = 0.0
    tot_gross_wins = 0.0
    tot_gross_losses = 0.0
    tot_stops = 0
    tot_hedges = 0
    tot_exits = 0

    for s_name in strat_keys:
        st = strat_totals[s_name]
        n = st["trades"]
        w = st["wins"]
        wr = (w / n * 100.0) if n > 0 else 0.0
        pf = (st["gross_wins"] / st["gross_losses"]) if st["gross_losses"] > 0 else (99.0 if st["gross_wins"] > 0 else 0.0)
        c_style = "green" if st["net_pnl"] > 0 else "red"

        tot_trades += n
        tot_wins += w
        tot_gross += st["gross_pnl"]
        tot_fees += st["fees"]
        tot_net += st["net_pnl"]
        tot_gross_wins += st["gross_wins"]
        tot_gross_losses += st["gross_losses"]
        tot_stops += st["stops"]
        tot_hedges += st["hedges"]
        tot_exits += (st["trails"] + st["tps"])

        sum_tbl.add_row(
            s_name,
            str(n),
            f"{wr:.1f}% ({w}/{n})",
            f"${st['gross_pnl']:+8.2f}",
            f"${st['fees']:8.2f}",
            f"[{c_style}]${st['net_pnl']:+8.2f}[/{c_style}]",
            f"{pf:.2f}",
            f"{st['stops']} ({(st['stops']/n*100.0) if n else 0:.1f}%)",
            f"{st['hedges']} ({(st['hedges']/n*100.0) if n else 0:.1f}%)",
            f"{st['trails'] + st['tps']} ({((st['trails']+st['tps'])/n*100.0) if n else 0:.1f}%)",
        )

    tot_wr = (tot_wins / tot_trades * 100.0) if tot_trades > 0 else 0.0
    tot_pf = (tot_gross_wins / tot_gross_losses) if tot_gross_losses > 0 else 0.0
    tot_style = "bold green" if tot_net > 0 else "bold red"

    sum_tbl.add_row(
        "[bold cyan]PORTFOLIO COMBINED[/bold cyan]",
        f"[bold]{tot_trades}[/bold]",
        f"[bold]{tot_wr:.1f}% ({tot_wins}/{tot_trades})[/bold]",
        f"[bold]${tot_gross:+8.2f}[/bold]",
        f"[bold]${tot_fees:8.2f}[/bold]",
        f"[{tot_style}]${tot_net:+8.2f}[/{tot_style}]",
        f"[bold]{tot_pf:.2f}[/bold]",
        f"[bold]{tot_stops} ({(tot_stops/tot_trades*100.0) if tot_trades else 0:.1f}%)[/bold]",
        f"[bold]{tot_hedges} ({(tot_hedges/tot_trades*100.0) if tot_trades else 0:.1f}%)[/bold]",
        f"[bold]{tot_exits} ({(tot_exits/tot_trades*100.0) if tot_trades else 0:.1f}%)[/bold]",
    )

    console.print(sum_tbl)

    # 3. Co-Entry Discounting & Synergy Breakdown
    console.print("\n[bold cyan]========================================================================================[/bold cyan]")
    console.print("[bold yellow]CO-ENTRY DISCOUNTING & CONCURRENCY ANALYSIS[/bold yellow]")
    console.print("[bold cyan]========================================================================================[/bold cyan]")

    co_tbl = Table(show_header=True, header_style="bold cyan")
    co_tbl.add_column("Execution Mode", style="bold")
    co_tbl.add_column("Trades", justify="right")
    co_tbl.add_column("Win Rate", justify="right")
    co_tbl.add_column("Net PnL ($)", justify="right", style="bold")
    co_tbl.add_column("Avg Return", justify="right")
    co_tbl.add_column("Avg Trade PnL", justify="right")

    all_co_trades = [t for t in all_trades_flat if t["is_co_entry"]]
    all_iso_trades = [t for t in all_trades_flat if not t["is_co_entry"]]

    co_w = len([t for t in all_co_trades if t["net_pnl"] > 0])
    co_wr = (co_w / len(all_co_trades) * 100.0) if all_co_trades else 0.0
    co_net = sum(t["net_pnl"] for t in all_co_trades)
    co_avg_ret = (sum(t["return_bps"] for t in all_co_trades) / len(all_co_trades)) if all_co_trades else 0.0
    co_avg_pnl = (co_net / len(all_co_trades)) if all_co_trades else 0.0

    iso_w = len([t for t in all_iso_trades if t["net_pnl"] > 0])
    iso_wr = (iso_w / len(all_iso_trades) * 100.0) if all_iso_trades else 0.0
    iso_net = sum(t["net_pnl"] for t in all_iso_trades)
    iso_avg_ret = (sum(t["return_bps"] for t in all_iso_trades) / len(all_iso_trades)) if all_iso_trades else 0.0
    iso_avg_pnl = (iso_net / len(all_iso_trades)) if all_iso_trades else 0.0

    co_style = "green" if co_net > 0 else "red"
    iso_style = "green" if iso_net > 0 else "red"

    co_tbl.add_row(
        "Isolated Position (100% Size)",
        str(len(all_iso_trades)),
        f"{iso_wr:.1f}% ({iso_w}/{len(all_iso_trades)})",
        f"[{iso_style}]${iso_net:+8.2f}[/{iso_style}]",
        f"{iso_avg_ret:+5.1f} bps",
        f"${iso_avg_pnl:+5.2f}",
    )
    co_tbl.add_row(
        "Co-Entry Position (50% Size, +0.04 Hurdle)",
        str(len(all_co_trades)),
        f"{co_wr:.1f}% ({co_w}/{len(all_co_trades)})",
        f"[{co_style}]${co_net:+8.2f}[/{co_style}]",
        f"{co_avg_ret:+5.1f} bps",
        f"${co_avg_pnl:+5.2f}",
    )

    console.print(co_tbl)

    # 4. Portfolio Drawdown and Synergy Metrics
    # Sort all trades chronologically to compute continuous equity curve & max drawdown
    all_trades_flat.sort(key=lambda t: t["exit_time_ms"])
    cum_equity = 0.0
    peak_equity = 0.0
    max_drawdown = 0.0
    equity_curve = []

    for t in all_trades_flat:
        cum_equity += t["net_pnl"]
        if cum_equity > peak_equity:
            peak_equity = cum_equity
        dd = peak_equity - cum_equity
        if dd > max_drawdown:
            max_drawdown = dd
        equity_curve.append((t["exit_time_ms"], cum_equity))

    return_to_dd = (tot_net / max_drawdown) if max_drawdown > 0 else 99.0

    console.print(f"\n[bold yellow]Portfolio Risk & Capital Efficiency Metrics:[/bold yellow]")
    console.print(f"  - Total Elapsed Replay Time:  [bold white]{total_duration:.1f}s[/bold white] across [bold cyan]{len(target_sessions)} sessions ({total_mb:.1f} MB)[/bold cyan]")
    console.print(f"  - Combined Net Profit:        [bold green]${tot_net:+.2f}[/bold green]")
    console.print(f"  - Peak Combined Equity:       [bold green]${peak_equity:+.2f}[/bold green]")
    console.print(f"  - Maximum Portfolio Drawdown: [bold red]${max_drawdown:.2f}[/bold red]")
    console.print(f"  - Net Return / Max Drawdown:  [bold yellow]{return_to_dd:.2f}x[/bold yellow]")
    console.print(f"  - Co-Entry Protection Rate:   [bold yellow]{(len(all_co_trades)/len(all_trades_flat)*100.0) if all_trades_flat else 0:.1f}%[/bold yellow] of all trades discounted\n")


if __name__ == "__main__":
    main()
