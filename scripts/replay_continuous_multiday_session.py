"""Continuous Multi-Day Session Replay across all 142 Chronological HYPE Files.

Replays the full 5.87-day session (2026-10-14 20:15:33 to 2026-10-20 17:16:42)
using a single persistent L2EngineRunner instance.
Positions and risk guardrails persist across hour boundaries, exactly mirroring
the runtime environment of baseline session_20261014_201533_720_a484.
"""

import glob
import json
import math
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


def run_continuous_replay() -> Dict[str, Any]:
    console = Console()
    console.print("[bold cyan]═══════════════════════════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]   CONTINUOUS MULTI-DAY HYPE SESSION REPLAY (142 CHRONOLOGICAL FILES) [/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════════════════════════════[/bold cyan]\n")

    # 1. Discover all matching chronological files
    pattern = os.path.join("data", "hype", "hl_hype_l2_202610*.jsonl")
    all_files = sorted(glob.glob(pattern))
    session_files = [
        f for f in all_files
        if "20261014_2000" <= os.path.basename(f)[11:24] <= "20261020_1700"
    ]

    if not session_files:
        console.print("[bold red]Error: No HYPE files found for the target session window![/bold red]")
        sys.exit(1)

    total_size_mb = sum(os.path.getsize(f) for f in session_files) / (1024.0 * 1024.0)
    console.print(f"Target Session Range: 2026-10-14 20:15:33 to 2026-10-20 17:16:42")
    console.print(f"Files to replay: [bold green]{len(session_files)}[/bold green] ({total_size_mb:.1f} MB)")
    console.print(f"First: {os.path.basename(session_files[0])}")
    console.print(f"Last:  {os.path.basename(session_files[-1])}\n")

    # 2. Configure engine runner
    cfg = AppConfig()
    cfg.market.coin = "HYPE"
    cfg.backtest.order_size_btc = 0.1  # Normalizes dynamically to ~$8,500 notional (105-108 HYPE)
    cfg.backtest.horizons_seconds = []  # Eliminate forward IC tracking overhead
    cfg.strategies = StrategiesConfig.load("strategies.json")
    cfg.strategies.alpha_signals["AdaptiveML"].enabled = False  # Avoid redundant LightGBM inference

    enabled_strats = list(cfg.strategies.get_enabled_strategy_defs().keys())
    console.print(f"Enabled Strategies: [bold yellow]{', '.join(enabled_strats)}[/bold yellow]")

    # Single persistent runner across all 142 files
    runner = L2EngineRunner(config=cfg, record_data=False, enable_audit=True)

    eval_interval_ms = int(1000 / max(cfg.sample_rate_hz, 1))  # 100ms
    last_eval_ms = 0
    total_events = 0
    t_start = time.time()

    # 3. Stream files sequentially
    console.print("[bold green]Starting continuous event playback...[/bold green]\n")

    for file_idx, filepath in enumerate(session_files, 1):
        file_t0 = time.time()
        file_events = 0
        fname = os.path.basename(filepath)

        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                file_events += 1
                try:
                    event = json.loads(line)
                except Exception:
                    continue

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

        total_events += file_events
        file_elapsed = time.time() - file_t0

        # Periodic progress logging
        if file_idx % 10 == 0 or file_idx == len(session_files) or file_idx == 1:
            elapsed_total = time.time() - t_start
            rate = file_idx / max(elapsed_total, 0.001)
            eta_s = (len(session_files) - file_idx) / max(rate, 0.001)

            # Snapshot stats
            stats_str = []
            for s_name in enabled_strats:
                st = runner.evaluator.strategies.get(s_name)
                n = len(st.trades) if st else 0
                net_p = sum(t.net_pnl_usd for t in st.trades) if st else 0.0
                stats_str.append(f"{s_name[:3]}: {n} trds (${net_p:+.1f})")

            console.print(
                f"[{file_idx:3d}/{len(session_files):3d}] {fname} | "
                f"{file_events:5d} evts ({file_elapsed:.2f}s) | "
                f"ETA: {int(eta_s // 60)}m {int(eta_s % 60):02d}s | "
                f"{' | '.join(stats_str)}"
            )

    # 4. Final close of any remaining open positions
    if runner.book.is_valid:
        now_ms = runner.book.last_update_time_ms or int(time.time() * 1000)
        runner.evaluator.close_open_positions(runner.book.mid_price, now_ms, reason="SESSION_SHUTDOWN")

    if runner.auditor:
        runner.auditor.close_session()

    total_time = time.time() - t_start
    console.print(f"\n[bold green]Replay completed in {total_time:.1f}s ({total_events:,} events processed).[/bold green]\n")

    # 5. Extract strategy metrics
    results: Dict[str, Any] = {}
    for s_name in enabled_strats:
        st = runner.evaluator.strategies.get(s_name)
        trades = st.trades if st else []
        n = len(trades)
        wins = [t for t in trades if t.net_pnl_usd > 0]
        losses = [t for t in trades if t.net_pnl_usd <= 0]
        win_rate = (len(wins) / n * 100.0) if n > 0 else 0.0

        gross_pnl = sum(t.gross_pnl_usd for t in trades)
        fees = sum(t.fees_usd for t in trades)
        net_pnl = sum(t.net_pnl_usd for t in trades)

        gross_wins = sum(t.gross_pnl_usd for t in wins)
        gross_losses = abs(sum(t.gross_pnl_usd for t in losses))
        pf = (gross_wins / gross_losses) if gross_losses > 1e-4 else 99.9

        tps = [t for t in trades if t.exit_reason == "TAKE_PROFIT"]
        trails = [t for t in trades if t.exit_reason == "TRAILING_STOP"]
        hedges = [t for t in trades if t.exit_reason == "DEFENSIVE_MAKER_HEDGE"]
        stops = [t for t in trades if t.exit_reason == "STOP_LOSS"]
        shutdowns = [t for t in trades if t.exit_reason == "SESSION_SHUTDOWN"]

        results[s_name] = {
            "trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": win_rate,
            "gross_pnl_usd": gross_pnl,
            "fees_usd": fees,
            "net_pnl_usd": net_pnl,
            "profit_factor": pf,
            "exits": {
                "TAKE_PROFIT": len(tps),
                "TRAILING_STOP": len(trails),
                "DEFENSIVE_MAKER_HEDGE": len(hedges),
                "STOP_LOSS": len(stops),
                "SESSION_SHUTDOWN": len(shutdowns),
            },
        }

    # 6. Baseline metrics from session_20261014_201533_720_a484
    baseline = {
        "Convexity_Cascade": {
            "trades": 293, "wins": 167, "losses": 126, "win_rate_pct": 57.0,
            "gross_pnl_usd": 691.07, "fees_usd": 725.48, "net_pnl_usd": -34.41,
            "profit_factor": 0.96,
        },
        "Hedged_Convexity": {
            "trades": 92, "wins": 60, "losses": 32, "win_rate_pct": 65.2,
            "gross_pnl_usd": 352.40, "fees_usd": 246.06, "net_pnl_usd": 106.34,
            "profit_factor": 1.43,
        },
        "Momentum_Expansion": {
            "trades": 361, "wins": 213, "losses": 148, "win_rate_pct": 59.0,
            "gross_pnl_usd": 1059.38, "fees_usd": 858.13, "net_pnl_usd": 201.25,
            "profit_factor": 1.21,
        },
    }

    # 7. Print Comparative Rich Table
    tbl = Table(title="Continuous Multi-Day Session Replay: Baseline vs. Improved", show_header=True)
    tbl.add_column("Strategy", style="bold white", width=20)
    tbl.add_column("Baseline Trades", justify="right")
    tbl.add_column("Replay Trades", justify="right")
    tbl.add_column("Baseline Win%", justify="right")
    tbl.add_column("Replay Win%", justify="right")
    tbl.add_column("Baseline Net PnL", justify="right")
    tbl.add_column("Replay Net PnL", justify="right")
    tbl.add_column("PnL Delta", justify="right")
    tbl.add_column("Replay PF", justify="right")
    tbl.add_column("Exits (TP/Trail/Hedge/Stop)", justify="center")

    for s_name in enabled_strats:
        b = baseline.get(s_name, {})
        r = results.get(s_name, {})

        b_trd = b.get("trades", 0)
        r_trd = r.get("trades", 0)
        b_wr = b.get("win_rate_pct", 0.0)
        r_wr = r.get("win_rate_pct", 0.0)
        b_pnl = b.get("net_pnl_usd", 0.0)
        r_pnl = r.get("net_pnl_usd", 0.0)
        delta_pnl = r_pnl - b_pnl
        r_pf = r.get("profit_factor", 0.0)

        ex = r.get("exits", {})
        exit_str = f"{ex.get('TAKE_PROFIT', 0)} / {ex.get('TRAILING_STOP', 0)} / {ex.get('DEFENSIVE_MAKER_HEDGE', 0)} / {ex.get('STOP_LOSS', 0)}"

        delta_style = "green" if delta_pnl > 0 else ("red" if delta_pnl < 0 else "white")
        pnl_style = "green" if r_pnl > 0 else "red"

        tbl.add_row(
            s_name,
            str(b_trd),
            f"[bold]{r_trd}[/bold]",
            f"{b_wr:.1f}%",
            f"{r_wr:.1f}%",
            f"${b_pnl:+.2f}",
            f"[{pnl_style}]${r_pnl:+.2f}[/{pnl_style}]",
            f"[{delta_style}]${delta_pnl:+.2f}[/{delta_style}]",
            f"{r_pf:.2f}",
            exit_str,
        )

    console.print(tbl)

    # Save summary artifact
    out_file = "audits/continuous_replay_results.json"
    summary_data = {
        "session_window": "2026-10-14 20:15:33 to 2026-10-20 17:16:42",
        "files_count": len(session_files),
        "total_events": total_events,
        "elapsed_seconds": total_time,
        "baseline": baseline,
        "replay_results": results,
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)
    console.print(f"\nSaved full results to [bold cyan]{out_file}[/bold cyan]")

    return summary_data


if __name__ == "__main__":
    run_continuous_replay()
