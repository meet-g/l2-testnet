"""Empirical Verification: Isolated vs. Concurrent Triad Execution.

Runs the 29 benchmark sessions comparing:
1. True isolated execution of each strategy (Hedged_Convexity alone, Convexity_Cascade alone, Momentum_Expansion alone)
2. Concurrent execution with co-entry protection (+0.04 hurdle, 50% size discount)

Measures:
- Combined Net PnL
- Win Rate & Profit Factor
- Maximum Portfolio Drawdown (chronological equity curve)
- Capital Efficiency (Net Return / Max Drawdown)
- Stop Loss exit rates (<= 3.0% threshold)
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import glob
import os
import sys
import time
from typing import Any, Dict, List, Tuple

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


def run_session_modes(args: Tuple[str, str, Dict[str, Any]]) -> Dict[str, Any]:
    filepath, coin, overrides = args
    filename = os.path.basename(filepath)
    size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)

    # We run 4 modes:
    # 'concurrent': HC + CC + ME active together
    # 'iso_HC': only Hedged_Convexity active
    # 'iso_CC': only Convexity_Cascade active
    # 'iso_ME': only Momentum_Expansion active
    modes = ["concurrent", "iso_HC", "iso_CC", "iso_ME"]
    mode_active_strats = {
        "concurrent": ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"],
        "iso_HC": ["Hedged_Convexity"],
        "iso_CC": ["Convexity_Cascade"],
        "iso_ME": ["Momentum_Expansion"],
    }

    base_order_size = get_coin_order_size(coin)

    # Prepare runners
    runners = {}
    for m in modes:
        cfg = AppConfig()
        cfg.market.coin = coin
        cfg.backtest.order_size_btc = base_order_size
        cfg.strategies = StrategiesConfig.load("strategies.json")

        if "AdaptiveML" in cfg.strategies.alpha_signals:
            cfg.strategies.alpha_signals["AdaptiveML"].enabled = False

        active_list = mode_active_strats[m]
        for s_name, s_cfg in cfg.strategies.execution_strategies.items():
            if s_name in active_list:
                s_cfg.enabled = True
                if s_name in overrides:
                    for k, v in overrides[s_name].items():
                        setattr(s_cfg, k, v)
            else:
                s_cfg.enabled = False

        r = L2EngineRunner(config=cfg, record_data=False, enable_audit=False)
        if hasattr(r.alpha_model, "signal_mom") and r.alpha_model.signal_mom:
            r.alpha_model.signal_mom.flow_hurdle = overrides.get("me_flow_hurdle", 0.35)
            r.alpha_model.signal_mom.min_trade_vol_window = overrides.get("me_min_trade_vol", 8.0)
        runners[m] = r

    replay = L2ReplayEngine(filepath, speed_multiplier=100000.0)
    last_eval_ms = 0
    sample_rate = AppConfig().sample_rate_hz
    eval_interval_ms = int(1000 / max(sample_rate, 1))

    # Single pass replay feeding all 4 runners
    try:
        for event in replay.stream_events():
            ch = event.get("channel")
            dt = event.get("data")
            now_ms = event.get("recv_ts", 0)

            # Update book & trades in primary runner
            primary = runners["concurrent"]
            if ch == "l2Book":
                primary.book.update_from_raw(dt)
            elif ch == "trades":
                primary.trades.process_raw_trades(dt)
            elif ch == "activeAssetCtx":
                primary.book.update_asset_ctx(dt)

            if primary.book.is_valid and (now_ms - last_eval_ms >= eval_interval_ms):
                last_eval_ms = now_ms
                res = primary.alpha_model.compute(primary.book, primary.trades, now_ms)
                sub_sigs = {name: sig.score for name, sig in res.metadata.get("sub_signals", {}).items()}
                sub_sigs["CompositeAlpha"] = res.score

                # Feed each evaluator
                for m, r in runners.items():
                    r.evaluator.record_step(
                        now_ms,
                        primary.book.mid_price,
                        primary.book.best_bid,
                        primary.book.best_ask,
                        sub_sigs,
                    )

        if runners["concurrent"].book.is_valid:
            mid = runners["concurrent"].book.mid_price
            now_ms = runners["concurrent"].book.last_update_time_ms or int(time.time() * 1000)
            for m, r in runners.items():
                r.evaluator.close_open_positions(mid, now_ms, reason="SESSION_SHUTDOWN")

    except Exception as e:
        return {"filename": filename, "error": str(e)}

    # Collect trades per mode
    mode_results = {}
    for m, r in runners.items():
        mode_trades = []
        for s_name in mode_active_strats[m]:
            st = r.evaluator.strategies.get(s_name)
            if not st:
                continue
            for t in st.trades:
                is_co = (t.size_btc < (base_order_size * 0.75))
                mode_trades.append({
                    "strategy": s_name,
                    "mode": m,
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
                    "is_co_entry": is_co,
                })
        mode_results[m] = mode_trades

    return {
        "filename": filename,
        "coin": coin,
        "size_mb": size_mb,
        "error": None,
        "mode_results": mode_results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    console = Console()
    console.print("\n[bold cyan]========================================================================================[/bold cyan]")
    console.print("[bold yellow]EMPIRICAL CHALLENGER: ISOLATED VS CONCURRENT PORTFOLIO TRIAD VERIFICATION[/bold yellow]")
    console.print("[bold cyan]========================================================================================[/bold cyan]\n")

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

    console.print(f"Target Datasets: {len(target_sessions)} sessions ({total_mb:.1f} MB)")
    console.print(f"Workers:         {args.workers}\n")

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

    tasks = [(f, c, strat_overrides) for f, c, _ in target_sessions]
    results = []

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(run_session_modes, task): task for task in tasks}
        completed = 0
        for fut in as_completed(future_map):
            completed += 1
            res = fut.result()
            results.append(res)
            console.print(f"[{completed:2d}/{len(tasks):2d}] Processed {res['filename']} ({res.get('size_mb', 0):.1f} MB)")
            sys.stdout.flush()

    duration = time.time() - t0
    console.print(f"\nExecution finished in {duration:.1f}s\n")

    # Aggregate trades across sessions
    all_concurrent_trades = []
    all_iso_hc_trades = []
    all_iso_cc_trades = []
    all_iso_me_trades = []

    for r in results:
        if r.get("error"):
            continue
        mr = r["mode_results"]
        all_concurrent_trades.extend(mr.get("concurrent", []))
        all_iso_hc_trades.extend(mr.get("iso_HC", []))
        all_iso_cc_trades.extend(mr.get("iso_CC", []))
        all_iso_me_trades.extend(mr.get("iso_ME", []))

    # All isolated trades combined (running all three in isolation without co-entry limits)
    all_isolated_sum_trades = all_iso_hc_trades + all_iso_cc_trades + all_iso_me_trades

    def compute_metrics(trades: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
        n = len(trades)
        wins = [t for t in trades if t["net_pnl"] > 0]
        losses = [t for t in trades if t["net_pnl"] <= 0]
        stops = [t for t in trades if t["exit_reason"] == "STOP_LOSS"]
        hedges = [t for t in trades if t["exit_reason"] == "DEFENSIVE_MAKER_HEDGE"]
        tps = [t for t in trades if t["exit_reason"] == "TAKE_PROFIT"]
        trails = [t for t in trades if t["exit_reason"] == "TRAILING_STOP"]

        gross_pnl = sum(t["gross_pnl"] for t in trades)
        fees = sum(t["fees"] for t in trades)
        net_pnl = sum(t["net_pnl"] for t in trades)
        gross_wins = sum(t["gross_pnl"] for t in wins)
        gross_losses = abs(sum(t["gross_pnl"] for t in losses))
        pf = (gross_wins / gross_losses) if gross_losses > 0 else (99.0 if gross_wins > 0 else 0.0)
        wr = (len(wins) / n * 100.0) if n > 0 else 0.0
        stop_rate = (len(stops) / n * 100.0) if n > 0 else 0.0

        # Drawdown calculation
        sorted_t = sorted(trades, key=lambda x: x["exit_time_ms"])
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in sorted_t:
            cum += t["net_pnl"]
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        ret_to_dd = (net_pnl / max_dd) if max_dd > 0 else 99.0

        return {
            "name": name,
            "trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": wr,
            "gross_pnl": gross_pnl,
            "fees": fees,
            "net_pnl": net_pnl,
            "profit_factor": pf,
            "stops": len(stops),
            "stop_rate": stop_rate,
            "hedges": len(hedges),
            "trails_tps": len(tps) + len(trails),
            "peak_equity": peak,
            "max_drawdown": max_dd,
            "ret_to_dd": ret_to_dd,
        }

    m_conc = compute_metrics(all_concurrent_trades, "CONCURRENT TRIAD (Co-Entry Active)")
    m_hc = compute_metrics(all_iso_hc_trades, "Isolated: Hedged_Convexity")
    m_cc = compute_metrics(all_iso_cc_trades, "Isolated: Convexity_Cascade")
    m_me = compute_metrics(all_iso_me_trades, "Isolated: Momentum_Expansion")
    m_iso_sum = compute_metrics(all_isolated_sum_trades, "ISOLATED SUMMED (No Co-Entry Protection)")

    # Print Comparison Table
    tbl = Table(title="TRIAD PORTFOLIO SYNERGY: ISOLATED VS CONCURRENT EXECUTION", header_style="bold yellow")
    tbl.add_column("Configuration", style="bold")
    tbl.add_column("Trades", justify="right")
    tbl.add_column("Win Rate", justify="right")
    tbl.add_column("Gross PnL", justify="right")
    tbl.add_column("Fees", justify="right")
    tbl.add_column("Net PnL ($)", justify="right", style="bold")
    tbl.add_column("Profit Factor", justify="right")
    tbl.add_column("Stop Rate", justify="right")
    tbl.add_column("Max DD ($)", justify="right", style="bold red")
    tbl.add_column("Return/MaxDD", justify="right", style="bold cyan")

    for m in [m_hc, m_cc, m_me, m_iso_sum, m_conc]:
        style = "bold green" if m["net_pnl"] > 0 else "bold red"
        tbl.add_row(
            m["name"],
            str(m["trades"]),
            f"{m['win_rate']:.1f}% ({m['wins']}/{m['trades']})",
            f"${m['gross_pnl']:+8.2f}",
            f"${m['fees']:8.2f}",
            f"[{style}]${m['net_pnl']:+8.2f}[/{style}]",
            f"{m['profit_factor']:.2f}",
            f"{m['stops']} ({m['stop_rate']:.1f}%)",
            f"${m['max_drawdown']:.2f}",
            f"{m['ret_to_dd']:.2f}x",
        )

    console.print(tbl)

    # Co-entry comparison within concurrent mode
    co_trades = [t for t in all_concurrent_trades if t["is_co_entry"]]
    iso_trades = [t for t in all_concurrent_trades if not t["is_co_entry"]]

    console.print("\n[bold yellow]Co-Entry Verification Details:[/bold yellow]")
    console.print(f"  - Total Concurrent Trades:     {len(all_concurrent_trades)}")
    console.print(f"  - Co-Entry Trades (50% size):   {len(co_trades)} ({len(co_trades)/len(all_concurrent_trades)*100.0:.1f}%)")
    console.print(f"  - Isolated Trades (100% size): {len(iso_trades)} ({len(iso_trades)/len(all_concurrent_trades)*100.0:.1f}%)")
    if co_trades:
        co_w = len([t for t in co_trades if t["net_pnl"] > 0])
        co_net = sum(t["net_pnl"] for t in co_trades)
        console.print(f"  - Co-Entry Win Rate:           {co_w/len(co_trades)*100.0:.1f}% ({co_w}/{len(co_trades)})")
        console.print(f"  - Co-Entry Net PnL:            ${co_net:+.2f}")

    # Net PnL and Drawdown comparison
    pnl_diff = m_conc["net_pnl"] - m_iso_sum["net_pnl"]
    dd_diff = m_iso_sum["max_drawdown"] - m_conc["max_drawdown"]
    console.print("\n[bold yellow]Synergy Audit Verdict Metrics:[/bold yellow]")
    console.print(f"  - Concurrent Net PnL:          ${m_conc['net_pnl']:+.2f} vs Isolated Sum: ${m_iso_sum['net_pnl']:+.2f} (Diff: ${pnl_diff:+.2f})")
    console.print(f"  - Concurrent Max Drawdown:     ${m_conc['max_drawdown']:.2f} vs Isolated Sum: ${m_iso_sum['max_drawdown']:.2f} (DD Reduction: ${dd_diff:+.2f})")
    console.print(f"  - Concurrent Return / Max DD:  {m_conc['ret_to_dd']:.2f}x vs Isolated Sum: {m_iso_sum['ret_to_dd']:.2f}x")
    console.print(f"  - Stop Loss Rate (All Modes):  Concurrent={m_conc['stop_rate']:.1f}%, Isolated Sum={m_iso_sum['stop_rate']:.1f}% (<= 3.0% Hurdle)")


if __name__ == "__main__":
    main()
