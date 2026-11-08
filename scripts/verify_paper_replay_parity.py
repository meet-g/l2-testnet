"""Verify Paper vs. Replay Parity for HYPE Session 20261107_163615.

Compares:
1. Paper Trading Session (recorded in audits/session_20261107_163615_948_84cf)
2. Replay with 250ms event throttle (exact live paper trading logic)
3. Replay with 100ms sample rate (standard 10 Hz offline replay)
"""

import glob
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import AppConfig, BacktestConfig, MarketConfig, StrategiesConfig
from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from engine.backtester import EdgeEvaluator, TradeRecord
from engine.data_collector import L2ReplayEngine
from signals.composite_alpha import CompositeAlphaSignal

SESSION_ID = "session_20261107_163615_948_84cf"
PAPER_TRADES_CSV = f"audits/{SESSION_ID}/all_trades.csv"

FILES = [
    "data/hype/hl_hype_l2_20261107_1600.jsonl",
    "data/hype/hl_hype_l2_20261107_1700.jsonl",
    "data/hype/hl_hype_l2_20261107_1800.jsonl",
    "data/hype/hl_hype_l2_20261107_1900.jsonl",
    "data/hype/hl_hype_l2_20261107_2000.jsonl",
    "data/hype/hl_hype_l2_20261107_2100.jsonl",
    "data/hype/hl_hype_l2_20261107_2200.jsonl",
    "data/hype/hl_hype_l2_20261107_2300.jsonl",
    "data/hype/hl_hype_l2_20261108_0000.jsonl",
    "data/hype/hl_hype_l2_20261108_0100.jsonl",
    "data/hype/hl_hype_l2_20261108_0200.jsonl",
    "data/hype/hl_hype_l2_20261108_0300.jsonl",
    "data/hype/hl_hype_l2_20261108_0400.jsonl",
    "data/hype/hl_hype_l2_20261108_0500.jsonl",
    "data/hype/hl_hype_l2_20261108_0600.jsonl",
    "data/hype/hl_hype_l2_20261108_0700.jsonl",
    "data/hype/hl_hype_l2_20261108_0800.jsonl",
    "data/hype/hl_hype_l2_20261108_0900.jsonl",
    "data/hype/hl_hype_l2_20261108_1000.jsonl",
    "data/hype/hl_hype_l2_20261108_1100.jsonl",
    "data/hype/hl_hype_l2_20261108_1200.jsonl",
    "data/hype/hl_hype_l2_20261108_1300.jsonl",
    "data/hype/hl_hype_l2_20261108_1400.jsonl",
    "data/hype/hl_hype_l2_20261108_1500.jsonl",
]

def run_replay(eval_mode: str, throttle_ms: int = 250, enable_qr_from_start: bool = True):
    print(f"\n=======================================================")
    print(f"Running Replay: mode={eval_mode}, throttle_ms={throttle_ms}, qr_from_start={enable_qr_from_start}")
    print(f"=======================================================")

    m_cfg = MarketConfig(coin="HYPE")
    bt_cfg = BacktestConfig(
        capital_usd=10000.0,
        order_size_btc=0.1,
        horizons_seconds=[],
    )
    strat_cfg = StrategiesConfig.load("strategies.json")
    all_defs = strat_cfg.get_enabled_strategy_defs()
    if not enable_qr_from_start and "Queue_Replenishment" in all_defs:
        del all_defs["Queue_Replenishment"]
    all_params = strat_cfg.get_strategy_params()

    evaluator = EdgeEvaluator(
        market_cfg=m_cfg,
        bt_cfg=bt_cfg,
        strategy_defs=all_defs,
        strategy_params=all_params,
    )

    book = OrderBook("HYPE")
    trades = TradeManager("HYPE")
    alpha = CompositeAlphaSignal(enabled_signals={"AdaptiveML": False})

    last_eval_ms = 0
    t0 = time.time()
    total_events = 0

    # Timestamp when QR was toggled on: 2026-11-07 18:51:11 UTC -> ms
    qr_toggle_ms = 1794077471000  # approximate, or we can check

    for fpath in FILES:
        if not os.path.exists(fpath):
            print(f"Warning: {fpath} not found")
            continue
        replay = L2ReplayEngine(fpath, speed_multiplier=1000000.0)
        for event in replay.stream_events():
            total_events += 1
            ch = event.get("channel")
            dt = event.get("data")
            now_ms = event.get("recv_ts", 0)

            if not enable_qr_from_start and "Queue_Replenishment" not in evaluator.strategy_names:
                if now_ms >= qr_toggle_ms:
                    qr_cfg = strat_cfg.get_strategy("Queue_Replenishment")
                    if qr_cfg:
                        evaluator.strategy_defs["Queue_Replenishment"] = (qr_cfg.signal_key, qr_cfg.execution_type)
                        evaluator.strategy_names.append("Queue_Replenishment")
                        from engine.backtester import StrategyState
                        evaluator.strategies["Queue_Replenishment"] = StrategyState(
                            name="Queue_Replenishment",
                            execution_type=qr_cfg.execution_type,
                            signal_key=qr_cfg.signal_key,
                            cash_usd=10000.0,
                            category="execution",
                        )

            if ch == "l2Book":
                book.update_from_raw(dt)
            elif ch == "trades":
                if isinstance(dt, list):
                    trades.process_raw_trades(dt)
            elif ch == "activeAssetCtx":
                book.update_asset_ctx(dt)

            should_eval = False
            if eval_mode == "event_driven":
                if ch in ("l2Book", "trades") and (now_ms - last_eval_ms >= throttle_ms):
                    should_eval = True
                    last_eval_ms = now_ms
            elif eval_mode == "periodic":
                if now_ms - last_eval_ms >= throttle_ms:
                    should_eval = True
                    last_eval_ms = now_ms

            if should_eval and book.is_valid:
                res = alpha.compute(book, trades, now_ms)
                sub_sigs = {name: sig.score for name, sig in res.metadata.get("sub_signals", {}).items()}
                sub_sigs["CompositeAlpha"] = res.score
                confidences = {name: getattr(sig, "confidence", 0.0) for name, sig in res.metadata.get("sub_signals", {}).items()}
                evaluator.record_step(now_ms, book.mid_price, book.best_bid, book.best_ask, sub_sigs, confidences)

    if book.is_valid:
        now_ms = book.last_update_time_ms or int(time.time() * 1000)
        evaluator.close_open_positions(book.mid_price, now_ms, reason="SESSION_SHUTDOWN")

    elapsed = time.time() - t0
    print(f"Replay finished in {elapsed:.2f}s ({total_events} events).")

    summary = {}
    total_trades = 0
    total_net = 0.0
    total_gross = 0.0
    total_fees = 0.0
    all_trade_records = []

    for s_name, st in evaluator.strategies.items():
        trades_list = st.trades
        n = len(trades_list)
        wins = [t for t in trades_list if t.net_pnl_usd > 0]
        wr = (len(wins) / n * 100.0) if n > 0 else 0.0
        net = sum(t.net_pnl_usd for t in trades_list)
        gross = sum(t.gross_pnl_usd for t in trades_list)
        fees = sum(t.fees_usd for t in trades_list)

        total_trades += n
        total_net += net
        total_gross += gross
        total_fees += fees

        summary[s_name] = {
            "trades": n,
            "win_rate": wr,
            "gross_pnl": gross,
            "fees": fees,
            "net_pnl": net,
        }
        all_trade_records.extend(trades_list)

    return {
        "mode": eval_mode,
        "throttle_ms": throttle_ms,
        "total_trades": total_trades,
        "total_gross": total_gross,
        "total_fees": total_fees,
        "total_net": total_net,
        "strategies": summary,
        "trades": all_trade_records,
    }

if __name__ == "__main__":
    paper_df = pd.read_csv(PAPER_TRADES_CSV)
    print("=======================================================")
    print("PAPER TRADING RECORDED SESSION SUMMARY:")
    print("=======================================================")
    print(f"Total Trades: {len(paper_df)}")
    print(f"Gross PnL:   ${paper_df['gross_pnl_usd'].sum():.2f}")
    print(f"Total Fees:  ${paper_df['total_fees_usd'].sum():.2f}")
    print(f"Net PnL:     ${paper_df['net_pnl_usd'].sum():.2f}")
    print("\nPer-Strategy Breakdown:")
    print(paper_df.groupby('strategy_name')[['gross_pnl_usd', 'total_fees_usd', 'net_pnl_usd']].sum())

    # Run Replay 1: Event-driven 250ms (Paper live simulation logic)
    r_event = run_replay("event_driven", throttle_ms=250, enable_qr_from_start=True)
    print("\n--- REPLAY: Event-Driven (250ms throttle) ---")
    print(f"Total Trades: {r_event['total_trades']}")
    print(f"Gross PnL:   ${r_event['total_gross']:.2f}")
    print(f"Total Fees:  ${r_event['total_fees']:.2f}")
    print(f"Net PnL:     ${r_event['total_net']:.2f}")
    for s, d in r_event["strategies"].items():
        print(f"  {s:<22}: trades={d['trades']:<3} gross=${d['gross_pnl']:<7.2f} fees=${d['fees']:<7.2f} net=${d['net_pnl']:<7.2f}")

    # Run Replay 2: Standard 10Hz (100ms periodic)
    r_10hz = run_replay("periodic", throttle_ms=100, enable_qr_from_start=True)
    print("\n--- REPLAY: Standard 10Hz Replay (100ms periodic) ---")
    print(f"Total Trades: {r_10hz['total_trades']}")
    print(f"Gross PnL:   ${r_10hz['total_gross']:.2f}")
    print(f"Total Fees:  ${r_10hz['total_fees']:.2f}")
    print(f"Net PnL:     ${r_10hz['total_net']:.2f}")
    for s, d in r_10hz["strategies"].items():
        print(f"  {s:<22}: trades={d['trades']:<3} gross=${d['gross_pnl']:<7.2f} fees=${d['fees']:<7.2f} net=${d['net_pnl']:<7.2f}")
