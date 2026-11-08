"""High-Throughput Parallel Replay Evaluation for ALL Scalping Strategies across SKHYNIX Data.

Evaluates all 9 scalping strategies:
1. MicroPrice_FastFill
2. MicroPrice_Maker
3. QDAP_Maker
4. Composite_Maker
5. AdaptiveML_Maker
6. WOBI_Maker
7. Absorption_Fade
8. AdaptiveML_Taker
9. Composite_Taker

Across all Hyperliquid SKHYNIX datasets:
- Primary SK Hynix Equity Contract (xyz:SKHX)
- SK Hynix American Depositary Shares (xyz:SKHY)
Using XYZ equity fee structure: 0.30 bps maker fee, 0.90 bps taker fee.
"""

import collections
from concurrent.futures import ProcessPoolExecutor, as_completed
import glob
import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

# Set OpenMP and math runtime threading policies
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

# Force UTF-8 stdout/stderr on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rich.console import Console
from rich.table import Table

from config import BacktestConfig, MarketConfig, StrategiesConfig, LEGACY_SCALPING_STRATEGIES
from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from engine.backtester import EdgeEvaluator
from engine.data_collector import L2ReplayEngine
from signals.composite_alpha import CompositeAlphaSignal


def get_all_skhynix_files() -> List[Tuple[str, str]]:
    """Discovers all non-empty SKHYNIX recording files and assigns coin symbol."""
    files: List[Tuple[str, str]] = []

    # 1. Primary Equity Contract (xyz:SKHX)
    skhx_files = sorted(glob.glob("data/xyz_skhx/hl_xyz_skhx_l2_*.jsonl"))
    for f in skhx_files:
        if os.path.isfile(f) and os.path.getsize(f) > 5000:
            files.append((f, "xyz:SKHX"))

    # 2. ADS Contract (xyz:SKHY)
    skhy_files = sorted(glob.glob("data/xyz_skhy/hl_xyz_skhy_l2_*.jsonl"))
    for f in skhy_files:
        if os.path.isfile(f) and os.path.getsize(f) > 5000:
            files.append((f, "xyz:SKHY"))

    # 3. Snippets if substantial and not redundant
    existing_basenames = {os.path.basename(f) for f, _ in files}
    for snip in sorted(glob.glob("data/xyz_skhx/snippets/hl_xyz_skhx_l2_*.jsonl")):
        if os.path.basename(snip) not in existing_basenames and os.path.isfile(snip) and os.path.getsize(snip) > 100000:
            files.append((snip, "xyz:SKHX"))
            existing_basenames.add(os.path.basename(snip))

    for snip in sorted(glob.glob("data/xyz_skhy/snippets/hl_xyz_skhy_l2_*.jsonl")):
        if os.path.basename(snip) not in existing_basenames and os.path.isfile(snip) and os.path.getsize(snip) > 100000:
            files.append((snip, "xyz:SKHY"))
            existing_basenames.add(os.path.basename(snip))

    return files


def replay_single_skhynix_file(args: Tuple[str, str]) -> Dict[str, Any]:
    """Worker process: Replays a single SKHYNIX dataset file across all 9 scalping strategies."""
    filepath, coin = args
    filename = os.path.basename(filepath)
    size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)

    m_cfg = MarketConfig(coin=coin)
    bt_cfg = BacktestConfig(
        capital_usd=10000.0,
        max_spread_bps=5.0,
        horizons_seconds=[],  # Bypass forward IC tracking for pure execution speed
    )

    strat_cfg = StrategiesConfig.load("strategies.json")
    scalp_defs = {s.name: (s.signal_key, s.execution_type) for s in strat_cfg.scalping_strategies.values()}
    scalp_params = strat_cfg.get_strategy_params(include_scalping=True)

    evaluator = EdgeEvaluator(
        market_cfg=m_cfg,
        bt_cfg=bt_cfg,
        strategy_defs=scalp_defs,
        strategy_params=scalp_params,
    )

    book = OrderBook(coin)
    trades = TradeManager(coin=coin)
    alpha = CompositeAlphaSignal()

    last_eval_ms = 0
    t0 = time.time()
    events_count = 0

    try:
        replay = L2ReplayEngine(filepath, speed_multiplier=100000.0)
        for event in replay.stream_events():
            events_count += 1
            ch = event.get("channel")
            dt = event.get("data")
            now_ms = event.get("recv_ts", 0)

            if ch == "l2Book":
                book.update_from_raw(dt)
            elif ch == "trades":
                trades.process_raw_trades(dt)

            if book.is_valid and (now_ms - last_eval_ms >= 100):
                last_eval_ms = now_ms
                res = alpha.compute(book, trades, now_ms)
                sub_dict = res.metadata.get("sub_signals", {})
                sigs = {name: s.score for name, s in sub_dict.items()}
                sigs["CompositeAlpha"] = res.score
                confs = {name: getattr(s, "confidence", 1.0) for name, s in sub_dict.items()}
                confs["CompositeAlpha"] = getattr(res, "confidence", 1.0)
                evaluator.record_step(now_ms, book.mid_price, book.best_bid, book.best_ask, sigs, confidences=confs)

        if book.is_valid:
            now_ms = book.last_update_time_ms or int(time.time() * 1000)
            evaluator.close_open_positions(book.mid_price, now_ms, reason="SESSION_SHUTDOWN")

    except Exception as e:
        return {
            "filename": filename,
            "filepath": filepath,
            "coin": coin,
            "size_mb": size_mb,
            "events": events_count,
            "elapsed_sec": time.time() - t0,
            "error": str(e),
            "strategies": {},
        }

    elapsed = time.time() - t0
    strat_results = {}

    for s_name in scalp_defs.keys():
        state = evaluator.strategies.get(s_name)
        if not state:
            continue

        trade_list = []
        gross_pnl = 0.0
        fees = 0.0
        net_pnl = 0.0
        wins = 0
        losses = 0
        gross_win = 0.0
        gross_loss = 0.0
        returns_bps = []
        durations_sec = []
        exit_counts = collections.defaultdict(int)

        for tr in state.trades:
            gross_pnl += tr.gross_pnl_usd
            fees += tr.fees_usd
            net_pnl += tr.net_pnl_usd
            returns_bps.append(tr.return_bps)
            dur = max(0.0, (tr.exit_time_ms - tr.entry_time_ms) / 1000.0)
            durations_sec.append(dur)
            exit_counts[tr.exit_reason] += 1

            if tr.net_pnl_usd > 0:
                wins += 1
                gross_win += tr.gross_pnl_usd
            else:
                losses += 1
                gross_loss += abs(tr.gross_pnl_usd)

        total_trades = len(state.trades)
        win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
        pf = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
        avg_ret = (sum(returns_bps) / len(returns_bps)) if returns_bps else 0.0
        avg_dur = (sum(durations_sec) / len(durations_sec)) if durations_sec else 0.0

        strat_results[s_name] = {
            "trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "gross_pnl": gross_pnl,
            "fees": fees,
            "net_pnl": net_pnl,
            "gross_win": gross_win,
            "gross_loss": gross_loss,
            "profit_factor": pf,
            "max_drawdown": state.max_drawdown_usd,
            "avg_return_bps": avg_ret,
            "avg_duration_sec": avg_dur,
            "exit_reasons": dict(exit_counts),
        }

    return {
        "filename": filename,
        "filepath": filepath,
        "coin": coin,
        "size_mb": size_mb,
        "events": events_count,
        "elapsed_sec": elapsed,
        "error": None,
        "strategies": strat_results,
    }


def main():
    console = Console()
    all_files = get_all_skhynix_files()

    if not all_files:
        console.print("[bold red]No SKHYNIX dataset files found![/bold red]")
        sys.exit(1)

    total_size_mb = sum(os.path.getsize(f) for f, _ in all_files) / (1024.0 * 1024.0)
    skhx_count = sum(1 for _, c in all_files if c == "xyz:SKHX")
    skhy_count = sum(1 for _, c in all_files if c == "xyz:SKHY")

    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f"[bold green]HIGH-THROUGHPUT REPLAY: All 9 Scalping Strategies against SKHYNIX Data[/bold green]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]")
    console.print(f"Total Recording Datasets: [bold yellow]{len(all_files)} files[/bold yellow] ({total_size_mb:.2f} MB)")
    console.print(f"  • Primary SK Hynix Equity (xyz:SKHX): [bold yellow]{skhx_count} files[/bold yellow]")
    console.print(f"  • SK Hynix ADS Contract  (xyz:SKHY): [bold yellow]{skhy_count} files[/bold yellow]")
    console.print(f"Fee Structure: Maker Fee = [bold green]0.30 bps[/bold green] (0.0030%), Taker Fee = [bold green]0.90 bps[/bold green] (0.0090%)")
    console.print(f"Target Strategies: {', '.join(LEGACY_SCALPING_STRATEGIES)}\n")

    max_workers = min(os.cpu_count() or 4, 8)
    console.print(f"Dispatching parallel execution across [bold yellow]{max_workers} worker processes[/bold yellow]...")

    t_start = time.time()
    results = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(replay_single_skhynix_file, item): item for item in all_files}

        completed_count = 0
        total_events = 0
        for fut in as_completed(future_map):
            completed_count += 1
            item = future_map[fut]
            try:
                res = fut.result()
                results.append(res)
                total_events += res.get("events", 0)
                err_marker = f"[red]ERR: {res['error']}[/red]" if res.get("error") else "[green]OK[/green]"
                console.print(
                    f" [{completed_count:2d}/{len(all_files):2d}] {res['coin']:8s} | "
                    f"{res['filename']:36s} | {res['size_mb']:5.2f} MB | {res['events']:7d} ev | "
                    f"{res['elapsed_sec']:5.1f}s | {err_marker}"
                )
            except Exception as exc:
                console.print(f"[bold red]Exception running {item[0]}: {exc}[/bold red]")

    total_wall_time = time.time() - t_start
    console.print(f"\n[bold green]Replay complete in {total_wall_time:.2f}s! ({total_events:,} events processed)[/bold green]\n")

    # Aggregate by strategy for (1) SKHX, (2) SKHY, and (3) Grand Total
    def aggregate_results(subset: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        agg: Dict[str, Dict[str, Any]] = {}
        for s_name in LEGACY_SCALPING_STRATEGIES:
            agg[s_name] = {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "gross_pnl": 0.0,
                "fees": 0.0,
                "net_pnl": 0.0,
                "gross_win": 0.0,
                "gross_loss": 0.0,
                "max_drawdown": 0.0,
                "weighted_dur_sum": 0.0,
                "exit_reasons": collections.defaultdict(int),
            }

        for r in subset:
            if r.get("error"):
                continue
            for s_name, data in r.get("strategies", {}).items():
                if s_name not in agg:
                    continue
                a = agg[s_name]
                a["trades"] += data["trades"]
                a["wins"] += data["wins"]
                a["losses"] += data["losses"]
                a["gross_pnl"] += data["gross_pnl"]
                a["fees"] += data["fees"]
                a["net_pnl"] += data["net_pnl"]
                a["gross_win"] += data["gross_win"]
                a["gross_loss"] += data["gross_loss"]
                a["max_drawdown"] = max(a["max_drawdown"], data["max_drawdown"])
                a["weighted_dur_sum"] += data["avg_duration_sec"] * data["trades"]
                for reason, count in data["exit_reasons"].items():
                    a["exit_reasons"][reason] += count

        # Compute derived metrics
        for s_name, a in agg.items():
            tot = a["trades"]
            a["win_rate"] = (a["wins"] / tot * 100.0) if tot > 0 else 0.0
            a["profit_factor"] = (a["gross_win"] / a["gross_loss"]) if a["gross_loss"] > 0 else (99.0 if a["gross_win"] > 0 else 0.0)
            a["avg_holding_sec"] = (a["weighted_dur_sum"] / tot) if tot > 0 else 0.0

        return agg

    skhx_results = [r for r in results if r["coin"] == "xyz:SKHX"]
    skhy_results = [r for r in results if r["coin"] == "xyz:SKHY"]

    agg_total = aggregate_results(results)
    agg_skhx = aggregate_results(skhx_results)
    agg_skhy = aggregate_results(skhy_results)

    # 1. Main Leaderboard Table across ALL SKHYNIX data
    table_all = Table(
        title="ALL SKHYNIX DATA (xyz:SKHX + xyz:SKHY): Scalping Strategy Performance Ranking",
        header_style="bold magenta",
        show_header=True,
    )
    table_all.add_column("Rank", justify="center", style="bold")
    table_all.add_column("Scalping Strategy", justify="left", style="bold cyan")
    table_all.add_column("Execution", justify="center")
    table_all.add_column("Trades", justify="right")
    table_all.add_column("Win Rate", justify="right")
    table_all.add_column("Gross PnL ($)", justify="right")
    table_all.add_column("Fees ($)", justify="right", style="dim")
    table_all.add_column("Net PnL ($)", justify="right", style="bold")
    table_all.add_column("PF", justify="right")
    table_all.add_column("Max DD ($)", justify="right", style="dim")
    table_all.add_column("Avg Hold", justify="right")

    # Sort by Net PnL descending
    strat_cfg = StrategiesConfig.load("strategies.json")
    scalp_defs = {s.name: (s.signal_key, s.execution_type) for s in strat_cfg.scalping_strategies.values()}
    ranked_total = sorted(agg_total.items(), key=lambda kv: kv[1]["net_pnl"], reverse=True)

    for rank, (s_name, m) in enumerate(ranked_total, 1):
        exec_type = scalp_defs.get(s_name, ("", "MAKER"))[1]
        pnl_style = "bold green" if m["net_pnl"] >= 0 else "bold red"
        pf_style = "green" if m["profit_factor"] >= 1.5 else ("yellow" if m["profit_factor"] >= 1.0 else "red")
        table_all.add_row(
            f"#{rank}",
            s_name,
            exec_type,
            f"{m['trades']:,}",
            f"{m['win_rate']:.1f}%",
            f"${m['gross_pnl']:+,.2f}",
            f"${m['fees']:,.2f}",
            f"[{pnl_style}]${m['net_pnl']:+,.2f}[/{pnl_style}]",
            f"[{pf_style}]{m['profit_factor']:.2f}[/{pf_style}]",
            f"${m['max_drawdown']:,.2f}",
            f"{m['avg_holding_sec']:.1f}s",
        )

    console.print(table_all)

    # 2. Sub-Table: Primary Equity Contract (xyz:SKHX)
    table_skhx = Table(
        title="PRIMARY EQUITY (xyz:SKHX - Mark ~$1,060): Scalping Strategy Performance",
        header_style="bold blue",
        show_header=True,
    )
    table_skhx.add_column("Rank", justify="center", style="bold")
    table_skhx.add_column("Scalping Strategy", justify="left", style="bold")
    table_skhx.add_column("Trades", justify="right")
    table_skhx.add_column("Win Rate", justify="right")
    table_skhx.add_column("Gross PnL ($)", justify="right")
    table_skhx.add_column("Fees ($)", justify="right", style="dim")
    table_skhx.add_column("Net PnL ($)", justify="right", style="bold")
    table_skhx.add_column("PF", justify="right")
    table_skhx.add_column("Max DD ($)", justify="right")

    ranked_skhx = sorted(agg_skhx.items(), key=lambda kv: kv[1]["net_pnl"], reverse=True)
    for rank, (s_name, m) in enumerate(ranked_skhx, 1):
        pnl_style = "bold green" if m["net_pnl"] >= 0 else "bold red"
        pf_style = "green" if m["profit_factor"] >= 1.5 else ("yellow" if m["profit_factor"] >= 1.0 else "red")
        table_skhx.add_row(
            f"#{rank}",
            s_name,
            f"{m['trades']:,}",
            f"{m['win_rate']:.1f}%",
            f"${m['gross_pnl']:+,.2f}",
            f"${m['fees']:,.2f}",
            f"[{pnl_style}]${m['net_pnl']:+,.2f}[/{pnl_style}]",
            f"[{pf_style}]{m['profit_factor']:.2f}[/{pf_style}]",
            f"${m['max_drawdown']:,.2f}",
        )
    console.print(table_skhx)

    # 3. Sub-Table: ADS Contract (xyz:SKHY)
    table_skhy = Table(
        title="ADS CONTRACT (xyz:SKHY - Mark ~$163): Scalping Strategy Performance",
        header_style="bold yellow",
        show_header=True,
    )
    table_skhy.add_column("Rank", justify="center", style="bold")
    table_skhy.add_column("Scalping Strategy", justify="left", style="bold")
    table_skhy.add_column("Trades", justify="right")
    table_skhy.add_column("Win Rate", justify="right")
    table_skhy.add_column("Gross PnL ($)", justify="right")
    table_skhy.add_column("Fees ($)", justify="right", style="dim")
    table_skhy.add_column("Net PnL ($)", justify="right", style="bold")
    table_skhy.add_column("PF", justify="right")
    table_skhy.add_column("Max DD ($)", justify="right")

    ranked_skhy = sorted(agg_skhy.items(), key=lambda kv: kv[1]["net_pnl"], reverse=True)
    for rank, (s_name, m) in enumerate(ranked_skhy, 1):
        pnl_style = "bold green" if m["net_pnl"] >= 0 else "bold red"
        pf_style = "green" if m["profit_factor"] >= 1.5 else ("yellow" if m["profit_factor"] >= 1.0 else "red")
        table_skhy.add_row(
            f"#{rank}",
            s_name,
            f"{m['trades']:,}",
            f"{m['win_rate']:.1f}%",
            f"${m['gross_pnl']:+,.2f}",
            f"${m['fees']:,.2f}",
            f"[{pnl_style}]${m['net_pnl']:+,.2f}[/{pnl_style}]",
            f"[{pf_style}]{m['profit_factor']:.2f}[/{pf_style}]",
            f"${m['max_drawdown']:,.2f}",
        )
    console.print(table_skhy)

    # 4. Exit Reasons Distribution Table
    table_exits = Table(
        title="EXIT MECHANISM BREAKDOWN: Containment & Risk Control Across All SKHYNIX Trades",
        header_style="bold green",
        show_header=True,
    )
    table_exits.add_column("Scalping Strategy", justify="left", style="bold cyan")
    table_exits.add_column("Total Exits", justify="right")
    table_exits.add_column("Take Profit", justify="right", style="green")
    table_exits.add_column("Flow Exhaust", justify="right", style="bold green")
    table_exits.add_column("Defensive Hedge", justify="right", style="yellow")
    table_exits.add_column("Trailing Stop", justify="right", style="blue")
    table_exits.add_column("Signal Reversal", justify="right")
    table_exits.add_column("Profit Decay", justify="right")
    table_exits.add_column("Time Limit", justify="right", style="dim")
    table_exits.add_column("Hard Stop Loss", justify="right", style="bold red")

    for s_name, m in ranked_total:
        ex = m["exit_reasons"]
        tot = m["trades"]
        tp = ex.get("TAKE_PROFIT", 0)
        exh = ex.get("EXHAUSTION_EXIT", 0)
        dmh = ex.get("DEFENSIVE_MAKER_HEDGE", 0)
        ts = ex.get("TRAILING_STOP", 0)
        sr = ex.get("SIGNAL_REVERSAL", 0)
        pd = ex.get("PROFIT_DECAY_EXIT", 0)
        tl = ex.get("TIME_LIMIT", 0)
        sl = ex.get("STOP_LOSS", 0)

        def pct(c: int) -> str:
            return f"{c:,} ({(c/tot*100):.1f}%)" if tot > 0 else "0"

        table_exits.add_row(
            s_name,
            f"{tot:,}",
            pct(tp),
            pct(exh),
            pct(dmh),
            pct(ts),
            pct(sr),
            pct(pd),
            pct(tl),
            pct(sl),
        )
    console.print(table_exits)

    # Save full JSON report
    os.makedirs("audits", exist_ok=True)
    report_file = os.path.join("audits", "skhynix_all_scalping_replay_report.json")
    with open(report_file, "w") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_files": len(all_files),
                "total_size_mb": total_size_mb,
                "total_events": total_events,
                "wall_time_sec": total_wall_time,
                "grand_total": {k: {**v, "exit_reasons": dict(v["exit_reasons"])} for k, v in agg_total.items()},
                "skhx_total": {k: {**v, "exit_reasons": dict(v["exit_reasons"])} for k, v in agg_skhx.items()},
                "skhy_total": {k: {**v, "exit_reasons": dict(v["exit_reasons"])} for k, v in agg_skhy.items()},
                "per_file_results": results,
            },
            f,
            indent=2,
        )
    console.print(f"[bold green]Saved detailed audit report to {report_file}[/bold green]\n")


if __name__ == "__main__":
    main()
