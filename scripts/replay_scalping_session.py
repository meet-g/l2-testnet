"""Replay all scalping strategies on the Nov 5 SKHYNIX session data.

Evaluates all 11 scalping strategies across:
1. The exact live session window: 2026-11-05 11:56:30 to 12:02:40 UTC
2. The full extended session files: 2026-11-05 11:43:41 to 12:54:43 UTC
"""

import collections
import datetime
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rich.console import Console
from rich.table import Table

from config import BacktestConfig, MarketConfig, StrategiesConfig
from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from engine.backtester import EdgeEvaluator
from engine.data_collector import L2ReplayEngine
from signals.composite_alpha import CompositeAlphaSignal


def run_session_replay(
    file_paths: List[str],
    coin: str = "xyz:SKHX",
    window_start_ms: Optional[int] = None,
    window_end_ms: Optional[int] = None,
    window_name: str = "Live Session Window",
) -> Dict[str, Any]:
    console = Console()
    console.print(f"\n[bold cyan]Starting Replay: {window_name}[/bold cyan]")
    if window_start_ms and window_end_ms:
        dt_start = datetime.datetime.fromtimestamp(window_start_ms / 1000, tz=datetime.timezone.utc)
        dt_end = datetime.datetime.fromtimestamp(window_end_ms / 1000, tz=datetime.timezone.utc)
        console.print(f"Time Range: {dt_start.strftime('%Y-%m-%d %H:%M:%S')} to {dt_end.strftime('%Y-%m-%d %H:%M:%S')} UTC")

    m_cfg = MarketConfig(coin=coin)
    bt_cfg = BacktestConfig(
        capital_usd=10000.0,
        max_spread_bps=5.0,
        horizons_seconds=[],
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
    events_processed = 0
    events_in_window = 0

    for f_path in file_paths:
        if not os.path.exists(f_path):
            console.print(f"[red]Warning: file {f_path} not found![/red]")
            continue

        replay = L2ReplayEngine(f_path, speed_multiplier=100000.0)
        for event in replay.stream_events():
            events_processed += 1
            ch = event.get("channel")
            dt = event.get("data")
            now_ms = event.get("recv_ts", 0)

            # Extract book/trade timestamp if present
            if ch == "l2Book" and isinstance(dt, dict):
                pkt_time = dt.get("time", now_ms)
            elif ch == "trades" and isinstance(dt, list) and len(dt) > 0:
                pkt_time = dt[0].get("time", now_ms)
            else:
                pkt_time = now_ms

            if pkt_time <= 0:
                pkt_time = now_ms

            # Apply state updates always to warm up order book and CVD
            if ch == "l2Book":
                book.update_from_raw(dt)
            elif ch == "trades":
                trades.process_raw_trades(dt)

            # Check if event falls inside specified window
            if window_start_ms is not None and pkt_time < window_start_ms:
                continue
            if window_end_ms is not None and pkt_time > window_end_ms:
                continue

            events_in_window += 1

            if book.is_valid and (pkt_time - last_eval_ms >= 100):
                last_eval_ms = pkt_time
                res = alpha.compute(book, trades, pkt_time)
                sub_dict = res.metadata.get("sub_signals", {})
                sigs = {name: s.score for name, s in sub_dict.items()}
                sigs["CompositeAlpha"] = res.score
                confs = {name: getattr(s, "confidence", 1.0) for name, s in sub_dict.items()}
                confs["CompositeAlpha"] = getattr(res, "confidence", 1.0)

                evaluator.record_step(
                    pkt_time,
                    book.mid_price,
                    book.best_bid,
                    book.best_ask,
                    sigs,
                    confidences=confs,
                )

    if book.is_valid:
        last_ms = book.last_update_time_ms or int(time.time() * 1000)
        evaluator.close_open_positions(book.mid_price, last_ms, reason="SESSION_END")

    elapsed = time.time() - t0
    console.print(f"Events processed: {events_processed:,} | Events in window: {events_in_window:,} | Elapsed: {elapsed:.2f}s")

    # Aggregate metrics
    results: Dict[str, Any] = {}
    table = Table(title=f"Scalping Strategy Performance — {window_name}")
    table.add_column("Strategy", style="cyan bold", no_wrap=True)
    table.add_column("Type", style="dim")
    table.add_column("Trades", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("Gross PnL", justify="right")
    table.add_column("Fees", justify="right")
    table.add_column("Net PnL", justify="right")
    table.add_column("Profit Factor", justify="right")
    table.add_column("Avg Return", justify="right")
    table.add_column("Max DD", justify="right")
    table.add_column("Primary Exits", style="dim")

    for s_name in scalp_defs.keys():
        st = evaluator.strategies.get(s_name)
        if not st:
            continue

        num_trades = len(st.trades)
        wins = sum(1 for tr in st.trades if tr.net_pnl_usd > 0)
        losses = sum(1 for tr in st.trades if tr.net_pnl_usd < 0)
        wr = (wins / num_trades * 100.0) if num_trades > 0 else 0.0

        gross = sum(tr.gross_pnl_usd for tr in st.trades)
        fees = sum(tr.fees_usd for tr in st.trades)
        net = sum(tr.net_pnl_usd for tr in st.trades)

        gross_win = sum(tr.gross_pnl_usd for tr in st.trades if tr.gross_pnl_usd > 0)
        gross_loss = abs(sum(tr.gross_pnl_usd for tr in st.trades if tr.gross_pnl_usd < 0))
        pf = (gross_win / gross_loss) if gross_loss > 1e-6 else (99.9 if gross_win > 0 else 0.0)

        ret_bps = [tr.return_bps for tr in st.trades]
        avg_ret = (sum(ret_bps) / len(ret_bps)) if ret_bps else 0.0

        exit_counts = collections.Counter(tr.exit_reason for tr in st.trades)
        primary_exits = ", ".join(f"{k}:{v}" for k, v in exit_counts.most_common(2))

        results[s_name] = {
            "trades": num_trades,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": wr,
            "gross_pnl_usd": gross,
            "fees_usd": fees,
            "net_pnl_usd": net,
            "profit_factor": pf,
            "avg_return_bps": avg_ret,
            "max_drawdown_usd": st.max_drawdown_usd,
            "exit_counts": dict(exit_counts),
        }

        pnl_style = "green bold" if net > 0 else ("red bold" if net < 0 else "white")
        table.add_row(
            s_name,
            scalp_defs[s_name][1],
            str(num_trades),
            f"{wr:.1f}%",
            f"${gross:+.2f}",
            f"${fees:.2f}",
            f"[{pnl_style}]${net:+.2f}[/{pnl_style}]",
            f"{pf:.2f}",
            f"{avg_ret:+.1f} bps",
            f"${st.max_drawdown_usd:.2f}",
            primary_exits or "None",
        )

    console.print(table)
    return results


if __name__ == "__main__":
    files = [
        "data/xyz_skhx/hl_xyz_skhx_l2_20261105_1100.jsonl",
        "data/xyz_skhx/hl_xyz_skhx_l2_20261105_1200.jsonl",
    ]

    # Live session timestamps: 2026-11-05 11:56:30 to 12:02:40 UTC
    t_start = int(datetime.datetime(2026, 11, 5, 11, 56, 30, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    t_end = int(datetime.datetime(2026, 11, 5, 12, 2, 40, tzinfo=datetime.timezone.utc).timestamp() * 1000)

    print("=" * 80)
    print("SKHYNIX LIVE SESSION REPLAY: ALL SCALPING STRATEGIES")
    print("=" * 80)

    # Replay 1: Exact Live Session Window (11:56:30 to 12:02:40 UTC)
    res_exact = run_session_replay(
        file_paths=files,
        coin="xyz:SKHX",
        window_start_ms=t_start,
        window_end_ms=t_end,
        window_name="Exact Live Session Window (11:56:30 - 12:02:40 UTC)",
    )

    # Replay 2: Full Continuous Session Period (11:43:41 to 12:54:43 UTC)
    res_full = run_session_replay(
        file_paths=files,
        coin="xyz:SKHX",
        window_start_ms=None,
        window_end_ms=None,
        window_name="Full Recorded Session (11:43:41 - 12:54:43 UTC, 71 mins)",
    )

    # Save to JSON report
    out_path = "audits/session_skhynix_scalping_replay_comparison.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "exact_live_window": res_exact,
                "full_session_period": res_full,
            },
            f,
            indent=2,
        )
    print(f"\nSaved replay report to: {out_path}")
