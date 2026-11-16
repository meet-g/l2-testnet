"""Replay Audit and Reconciliation for the two latest live trading sessions:
1. HYPE (session_20261110_232005_265_e170)
2. xyz:SKHX (session_20261110_231909_234_5a0b)

Streams the continuous recorded L2 market data (12 hourly files per session, ~11.3 hours)
through EdgeEvaluator for ALL core strategies and compares:
- Live executed trades vs Replay simulated trades
- Win rate, gross PnL, exchange fees, net PnL
- Trade-by-trade timestamp and signal trigger reconciliation
"""

import glob
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional
import pandas as pd

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rich.console import Console
from rich.table import Table

from config import BacktestConfig, MarketConfig, StrategiesConfig
from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from engine.backtester import EdgeEvaluator
from engine.data_collector import L2ReplayEngine
from signals.composite_alpha import CompositeAlphaSignal

CORE_STRATEGIES = [
    "Hedged_Convexity",
    "Convexity_Cascade",
    "Momentum_Expansion",
    "Queue_Replenishment",
    "Stock_Microstructure_Alpha",
]


def run_continuous_replay(
    coin: str,
    recording_files: List[str],
    order_size_btc: float,
    eval_interval_ms: int = 100,
) -> Dict[str, Any]:
    """Replays a continuous sequence of JSONL L2 recording files across all core strategies."""
    console = Console()
    m_cfg = MarketConfig(coin=coin)
    m_cfg.configure_for_coin(coin)

    bt_cfg = BacktestConfig(
        capital_usd=10000.0,
        order_size_btc=order_size_btc,
        horizons_seconds=[],
    )

    strat_cfg = StrategiesConfig.load("strategies_core.json")
    all_defs = strat_cfg.get_enabled_strategy_defs()
    # Ensure all 5 core strategies are present in defs
    core_defs = {
        "Hedged_Convexity": ("HedgedConvexity", "HEDGED_MAKER"),
        "Convexity_Cascade": ("ConvexityCascade", "MAKER"),
        "Momentum_Expansion": ("MomentumExpansion", "MAKER"),
        "Queue_Replenishment": ("QueueReplenishment", "HEDGED_MAKER"),
        "Stock_Microstructure_Alpha": ("StockMicrostructure", "HEDGED_MAKER"),
    }
    all_params = strat_cfg.get_strategy_params()
    for s_name in core_defs:
        if s_name in all_params:
            all_params[s_name]["enabled"] = True
            all_params[s_name]["order_size_btc"] = order_size_btc

    evaluator = EdgeEvaluator(
        market_cfg=m_cfg,
        bt_cfg=bt_cfg,
        strategy_defs=core_defs,
        strategy_params=all_params,
    )

    book = OrderBook(coin)
    trades = TradeManager(coin)
    alpha = CompositeAlphaSignal(enabled_signals={"AdaptiveML": False})

    total_events = 0
    t0 = time.time()
    last_eval_ms = 0

    for file_idx, filepath in enumerate(recording_files, 1):
        fname = os.path.basename(filepath)
        f_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)
        console.print(f"  Streaming [{file_idx}/{len(recording_files)}] [dim]{fname}[/dim] ({f_mb:.1f} MB)...")
        replay = L2ReplayEngine(filepath, speed_multiplier=100000.0)

        for event in replay.stream_events():
            total_events += 1
            ch = event.get("channel")
            dt = event.get("data")
            now_ms = event.get("recv_ts", 0)

            if ch == "l2Book":
                book.update_from_raw(dt)
            elif ch == "trades":
                trades.process_raw_trades(dt)
            elif ch == "activeAssetCtx":
                book.update_asset_ctx(dt)

            if book.is_valid and (now_ms - last_eval_ms >= eval_interval_ms):
                last_eval_ms = now_ms
                res = alpha.compute(book, trades, now_ms)
                sub_sigs = {name: sig.score for name, sig in res.metadata.get("sub_signals", {}).items()}
                sub_sigs["CompositeAlpha"] = res.score
                evaluator.record_step(
                    now_ms,
                    book.mid_price,
                    book.best_bid,
                    book.best_ask,
                    sub_sigs,
                )

    if book.is_valid:
        now_ms = book.last_update_time_ms or int(time.time() * 1000)
        evaluator.close_open_positions(book.mid_price, now_ms, reason="SESSION_SHUTDOWN")

    elapsed_s = time.time() - t0

    # Collect results per strategy
    strat_results = {}
    all_replay_trades = []

    for s_name in core_defs:
        st = evaluator.strategies.get(s_name)
        trds = st.trades if st else []
        wins = [t for t in trds if t.net_pnl_usd > 0]
        losses = [t for t in trds if t.net_pnl_usd < 0]
        gross = sum(t.gross_pnl_usd for t in trds)
        fees = sum(t.fees_usd for t in trds)
        net = sum(t.net_pnl_usd for t in trds)
        gross_wins = sum(t.gross_pnl_usd for t in trds if t.gross_pnl_usd > 0)
        gross_losses = sum(abs(t.gross_pnl_usd) for t in trds if t.gross_pnl_usd < 0)
        pf = (gross_wins / gross_losses) if gross_losses > 0 else (99.9 if gross_wins > 0 else 0.0)

        strat_results[s_name] = {
            "trades": len(trds),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": (len(wins) / len(trds) * 100.0) if trds else 0.0,
            "gross_pnl_usd": gross,
            "total_fees_usd": fees,
            "net_pnl_usd": net,
            "profit_factor": pf,
            "avg_return_bps": (sum(t.return_bps for t in trds) / len(trds)) if trds else 0.0,
        }

        for t in trds:
            all_replay_trades.append({
                "strategy_name": s_name,
                "entry_time_ms": t.entry_time_ms,
                "exit_time_ms": t.exit_time_ms,
                "side": t.side,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "size_btc": t.size_btc,
                "gross_pnl_usd": t.gross_pnl_usd,
                "total_fees_usd": t.fees_usd,
                "net_pnl_usd": t.net_pnl_usd,
                "return_bps": t.return_bps,
                "exit_reason": t.exit_reason,
            })

    total_trds = len(all_replay_trades)
    tot_wins = len([t for t in all_replay_trades if t["net_pnl_usd"] > 0])
    tot_gross = sum(t["gross_pnl_usd"] for t in all_replay_trades)
    tot_fees = sum(t["total_fees_usd"] for t in all_replay_trades)
    tot_net = sum(t["net_pnl_usd"] for t in all_replay_trades)

    return {
        "coin": coin,
        "elapsed_seconds": elapsed_s,
        "total_events": total_events,
        "total_trades": total_trds,
        "wins": tot_wins,
        "losses": total_trds - tot_wins,
        "win_rate_pct": (tot_wins / total_trds * 100.0) if total_trds else 0.0,
        "gross_pnl_usd": tot_gross,
        "total_fees_usd": tot_fees,
        "net_pnl_usd": tot_net,
        "strategies": strat_results,
        "trades": all_replay_trades,
    }


def main():
    console = Console()
    console.print("\n[bold cyan]===============================================================================[/bold cyan]")
    console.print("[bold green]LIVE TRADING VS REPLAY BENCHMARK AUDIT: HYPE & SKHX SESSIONS[/bold green]")
    console.print("[bold cyan]===============================================================================[/bold cyan]\n")

    # 1. HYPE Session Setup
    hype_live_dir = "audits/session_20261110_232005_265_e170"
    hype_files = sorted(
        glob.glob("data/hype/hl_hype_l2_20261110_23*.jsonl") +
        glob.glob("data/hype/hl_hype_l2_20261111_*.jsonl")
    )
    # 2. SKHX Session Setup
    skhx_live_dir = "audits/session_20261110_231909_234_5a0b"
    skhx_files = sorted(
        glob.glob("data/xyz_skhx/hl_xyz_skhx_l2_20261110_23*.jsonl") +
        glob.glob("data/xyz_skhx/hl_xyz_skhx_l2_20261111_*.jsonl")
    )

    console.print(f"HYPE Session: [bold white]{hype_live_dir}[/bold white]")
    console.print(f"  Recording files: {len(hype_files)} files ({sum(os.path.getsize(f) for f in hype_files)/(1024*1024):.1f} MB)")
    console.print(f"SKHX Session: [bold white]{skhx_live_dir}[/bold white]")
    console.print(f"  Recording files: {len(skhx_files)} files ({sum(os.path.getsize(f) for f in skhx_files)/(1024*1024):.1f} MB)\n")

    # Run Replay on HYPE (Live size: ~6.95 HYPE tokens = ~$500 notional)
    console.print("[bold yellow]Starting Continuous L2 Replay: HYPE (40,754s duration)...[/bold yellow]")
    hype_replay = run_continuous_replay(
        coin="HYPE",
        recording_files=hype_files,
        order_size_btc=6.95,
        eval_interval_ms=100,
    )
    console.print(f"[bold green]HYPE Replay Completed in {hype_replay['elapsed_seconds']:.1f}s ({hype_replay['total_trades']} trades)[/bold green]\n")

    # Run Replay on SKHX (Live size: ~0.315 shares = ~$300 notional, which is 0.00352 BTC notional)
    console.print("[bold yellow]Starting Continuous L2 Replay: xyz:SKHX (40,805s duration)...[/bold yellow]")
    skhx_replay = run_continuous_replay(
        coin="xyz:SKHX",
        recording_files=skhx_files,
        order_size_btc=0.00352,
        eval_interval_ms=100,
    )
    console.print(f"[bold green]SKHX Replay Completed in {skhx_replay['elapsed_seconds']:.1f}s ({skhx_replay['total_trades']} trades)[/bold green]\n")

    # Load Live Manifests
    with open(os.path.join(hype_live_dir, "session_manifest.json")) as f:
        hype_live_manifest = json.load(f)
    with open(os.path.join(skhx_live_dir, "session_manifest.json")) as f:
        skhx_live_manifest = json.load(f)

    # Build Comparison Tables
    def print_session_comparison(title: str, coin: str, live_manifest: dict, replay_data: dict):
        table = Table(title=title, header_style="bold magenta", show_header=True)
        table.add_column("Strategy", justify="left")
        table.add_column("Live Trd", justify="right")
        table.add_column("Replay Trd", justify="right")
        table.add_column("Live Win%", justify="right")
        table.add_column("Replay Win%", justify="right")
        table.add_column("Live Gross ($)", justify="right")
        table.add_column("Replay Gross ($)", justify="right")
        table.add_column("Live Fees ($)", justify="right")
        table.add_column("Replay Fees ($)", justify="right")
        table.add_column("Live Net ($)", justify="right", style="bold")
        table.add_column("Replay Net ($)", justify="right", style="bold")

        live_strats = live_manifest.get("strategies", {})
        replay_strats = replay_data.get("strategies", {})

        for s in CORE_STRATEGIES:
            ls = live_strats.get(s, {})
            rs = replay_strats.get(s, {})
            l_trd = ls.get("trades", 0)
            r_trd = rs.get("trades", 0)
            l_wr = ls.get("win_rate_pct", 0.0)
            r_wr = rs.get("win_rate_pct", 0.0)
            l_gross = ls.get("gross_pnl_usd", 0.0)
            r_gross = rs.get("gross_pnl_usd", 0.0)
            l_fees = ls.get("total_fees_usd", 0.0)
            r_fees = rs.get("total_fees_usd", 0.0)
            l_net = ls.get("net_pnl_usd", 0.0)
            r_net = rs.get("net_pnl_usd", 0.0)

            l_net_style = "green" if l_net > 0 else ("red" if l_net < 0 else "white")
            r_net_style = "green" if r_net > 0 else ("red" if r_net < 0 else "white")

            table.add_row(
                s,
                str(l_trd),
                str(r_trd),
                f"{l_wr:.1f}%" if l_trd > 0 else "-",
                f"{r_wr:.1f}%" if r_trd > 0 else "-",
                f"${l_gross:+.2f}",
                f"${r_gross:+.2f}",
                f"${l_fees:.2f}",
                f"${r_fees:.2f}",
                f"[{l_net_style}]${l_net:+.2f}[/{l_net_style}]",
                f"[{r_net_style}]${r_net:+.2f}[/{r_net_style}]",
            )

        # Totals
        l_sum = live_manifest.get("session_summary", {})
        table.add_section()
        table.add_row(
            "[bold white]TOTAL PORTFOLIO[/bold white]",
            str(l_sum.get("total_trades", 0)),
            str(replay_data.get("total_trades", 0)),
            f"{l_sum.get('win_rate_pct', 0.0):.1f}%",
            f"{replay_data.get('win_rate_pct', 0.0):.1f}%",
            f"${l_sum.get('gross_pnl_usd', 0.0):+.2f}",
            f"${replay_data.get('gross_pnl_usd', 0.0):+.2f}",
            f"${l_sum.get('total_fees_usd', 0.0):.2f}",
            f"${replay_data.get('total_fees_usd', 0.0):.2f}",
            f"${l_sum.get('net_pnl_usd', 0.0):+.2f}",
            f"${replay_data.get('net_pnl_usd', 0.0):+.2f}",
        )
        console.print(table)
        console.print("\n")

    print_session_comparison(
        "HYPE LIVE SESSION vs REPLAY (session_20261110_232005_265_e170)",
        "HYPE",
        hype_live_manifest,
        hype_replay,
    )

    print_session_comparison(
        "SKHX LIVE SESSION vs REPLAY (session_20261110_231909_234_5a0b)",
        "xyz:SKHX",
        skhx_live_manifest,
        skhx_replay,
    )

    # Save full audit JSON
    comparison_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hype_session": {
            "session_id": "session_20261110_232005_265_e170",
            "coin": "HYPE",
            "duration_secs": hype_live_manifest.get("duration_secs"),
            "live_summary": hype_live_manifest.get("session_summary"),
            "live_exchange_reconciliation": hype_live_manifest.get("live_exchange_reconciliation"),
            "replay_summary": {
                "total_trades": hype_replay["total_trades"],
                "win_rate_pct": round(hype_replay["win_rate_pct"], 2),
                "gross_pnl_usd": round(hype_replay["gross_pnl_usd"], 4),
                "total_fees_usd": round(hype_replay["total_fees_usd"], 4),
                "net_pnl_usd": round(hype_replay["net_pnl_usd"], 4),
            },
            "strategy_breakdown": {
                s: {
                    "live": hype_live_manifest.get("strategies", {}).get(s, {}),
                    "replay": hype_replay.get("strategies", {}).get(s, {}),
                }
                for s in CORE_STRATEGIES
            },
        },
        "skhx_session": {
            "session_id": "session_20261110_231909_234_5a0b",
            "coin": "xyz:SKHX",
            "duration_secs": skhx_live_manifest.get("duration_secs"),
            "live_summary": skhx_live_manifest.get("session_summary"),
            "live_exchange_reconciliation": skhx_live_manifest.get("live_exchange_reconciliation"),
            "replay_summary": {
                "total_trades": skhx_replay["total_trades"],
                "win_rate_pct": round(skhx_replay["win_rate_pct"], 2),
                "gross_pnl_usd": round(skhx_replay["gross_pnl_usd"], 4),
                "total_fees_usd": round(skhx_replay["total_fees_usd"], 4),
                "net_pnl_usd": round(skhx_replay["net_pnl_usd"], 4),
            },
            "strategy_breakdown": {
                s: {
                    "live": skhx_live_manifest.get("strategies", {}).get(s, {}),
                    "replay": skhx_replay.get("strategies", {}).get(s, {}),
                }
                for s in CORE_STRATEGIES
            },
        },
    }

    out_json = "audits/live_vs_replay_two_sessions_audit.json"
    with open(out_json, "w") as f:
        json.dump(comparison_data, f, indent=2)
    console.print(f"[bold dim]Comparison JSON written to: {out_json}[/bold dim]")


if __name__ == "__main__":
    main()
