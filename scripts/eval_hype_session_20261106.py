"""Replay evaluation of the 2026-11-06 HYPE paper session (01:25 to 10:25 UTC).

Replays the exact 10 raw data files recorded during the session:
data/hype/hl_hype_l2_20261106_0100.jsonl through 20261106_1000.jsonl

Evaluates both:
1. Standard 10 Hz Replay (100 ms step, standard offline replay benchmark)
2. Real-time Event-driven Replay (evaluating on every l2Book and trades event, matching main.py)
"""

import glob
import json
import os
import sys
import time
from typing import Any, Dict, List

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import AppConfig, BacktestConfig, MarketConfig, StrategiesConfig
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
]

def run_replay(eval_mode: str = "10hz") -> Dict[str, Any]:
    print(f"\n=======================================================")
    print(f"Running Replay Evaluation: mode={eval_mode}")
    print(f"=======================================================")
    
    files = sorted(glob.glob("data/hype/hl_hype_l2_20261106_*.jsonl"))
    print(f"Found {len(files)} files to replay.")
    
    m_cfg = MarketConfig(coin="HYPE")
    bt_cfg = BacktestConfig(
        capital_usd=10000.0,
        order_size_btc=0.1,
        horizons_seconds=[],
    )
    strat_cfg = StrategiesConfig.load("strategies.json")
    all_defs = {
        k: (s.signal_key, s.execution_type)
        for k, s in strat_cfg.execution_strategies.items()
        if k in CORE_STRATEGIES
    }
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

    for fpath in files:
        fname = os.path.basename(fpath)
        f_events = 0
        replay = L2ReplayEngine(fpath, speed_multiplier=1000000.0)
        for event in replay.stream_events():
            total_events += 1
            f_events += 1
            ch = event.get("channel")
            dt = event.get("data")
            now_ms = event.get("recv_ts", 0)

            if ch == "l2Book":
                book.update_from_raw(dt)
                if eval_mode == "event_driven" and book.is_valid and (now_ms - last_eval_ms >= 250):
                    last_eval_ms = now_ms
                    res = alpha.compute(book, trades, now_ms)
                    sub_sigs = {name: sig.score for name, sig in res.metadata.get("sub_signals", {}).items()}
                    sub_sigs["CompositeAlpha"] = res.score
                    confidences = {name: getattr(sig, "confidence", 0.0) for name, sig in res.metadata.get("sub_signals", {}).items()}
                    evaluator.record_step(now_ms, book.mid_price, book.best_bid, book.best_ask, sub_sigs, confidences)

            elif ch == "trades":
                if isinstance(dt, list):
                    trades.process_raw_trades(dt)
                if eval_mode == "event_driven" and book.is_valid and (now_ms - last_eval_ms >= 250):
                    last_eval_ms = now_ms
                    res = alpha.compute(book, trades, now_ms)
                    sub_sigs = {name: sig.score for name, sig in res.metadata.get("sub_signals", {}).items()}
                    sub_sigs["CompositeAlpha"] = res.score
                    confidences = {name: getattr(sig, "confidence", 0.0) for name, sig in res.metadata.get("sub_signals", {}).items()}
                    evaluator.record_step(now_ms, book.mid_price, book.best_bid, book.best_ask, sub_sigs, confidences)

            elif ch == "activeAssetCtx":
                book.update_asset_ctx(dt)

            if eval_mode == "10hz" and book.is_valid and (now_ms - last_eval_ms >= 100):
                last_eval_ms = now_ms
                res = alpha.compute(book, trades, now_ms)
                sub_sigs = {name: sig.score for name, sig in res.metadata.get("sub_signals", {}).items()}
                sub_sigs["CompositeAlpha"] = res.score
                confidences = {name: getattr(sig, "confidence", 0.0) for name, sig in res.metadata.get("sub_signals", {}).items()}
                evaluator.record_step(now_ms, book.mid_price, book.best_bid, book.best_ask, sub_sigs, confidences)
            
            elif eval_mode == "1hz" and book.is_valid and (now_ms - last_eval_ms >= 1000):
                last_eval_ms = now_ms
                res = alpha.compute(book, trades, now_ms)
                sub_sigs = {name: sig.score for name, sig in res.metadata.get("sub_signals", {}).items()}
                sub_sigs["CompositeAlpha"] = res.score
                confidences = {name: getattr(sig, "confidence", 0.0) for name, sig in res.metadata.get("sub_signals", {}).items()}
                evaluator.record_step(now_ms, book.mid_price, book.best_bid, book.best_ask, sub_sigs, confidences)

    if book.is_valid:
        now_ms = book.last_update_time_ms or int(time.time() * 1000)
        evaluator.close_open_positions(book.mid_price, now_ms, reason="SESSION_SHUTDOWN")

    elapsed = time.time() - t0
    print(f"Replay completed in {elapsed:.2f}s ({total_events} events).")

    # Aggregate stats
    results = {}
    total_trades = 0
    total_wins = 0
    total_gross = 0.0
    total_fees = 0.0
    total_net = 0.0

    print(f"\n{'Strategy':<24} | {'Trades':<6} | {'WinRate':<8} | {'Net PnL':<10} | {'Fees':<8} | {'PF':<6} | {'Avg Ret (bps)':<14}")
    print("-" * 85)

    for s_name in CORE_STRATEGIES:
        st = evaluator.strategies.get(s_name)
        trades_list = st.trades if st else []
        n = len(trades_list)
        wins = [t for t in trades_list if t.net_pnl_usd > 0]
        losses = [t for t in trades_list if t.net_pnl_usd <= 0]
        wr = (len(wins) / n * 100.0) if n > 0 else 0.0
        gross = sum(t.gross_pnl_usd for t in trades_list)
        fees = sum(t.fees_usd for t in trades_list)
        net = sum(t.net_pnl_usd for t in trades_list)
        gross_profit = sum(t.net_pnl_usd for t in wins)
        gross_loss = abs(sum(t.net_pnl_usd for t in losses))
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        avg_ret = (sum(t.return_bps for t in trades_list) / n) if n > 0 else 0.0

        total_trades += n
        total_wins += len(wins)
        total_gross += gross
        total_fees += fees
        total_net += net

        exit_reasons = {}
        for t in trades_list:
            exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

        results[s_name] = {
            "trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": wr,
            "gross_pnl": gross,
            "fees": fees,
            "net_pnl": net,
            "profit_factor": pf,
            "avg_return_bps": avg_ret,
            "exit_reasons": exit_reasons,
            "trades_detail": [
                {
                    "side": t.side,
                    "entry_time_ms": t.entry_time_ms,
                    "exit_time_ms": t.exit_time_ms,
                    "hold_s": (t.exit_time_ms - t.entry_time_ms) / 1000.0,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "exit_reason": t.exit_reason,
                    "net_pnl": t.net_pnl_usd,
                    "return_bps": t.return_bps,
                }
                for t in trades_list
            ]
        }
        print(f"{s_name:<24} | {n:<6} | {wr:6.1f}% | ${net:9.2f} | ${fees:7.2f} | {pf:6.2f} | {avg_ret:+8.2f} bps")

    tot_wr = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0
    tot_gl = abs(sum(r["losses"] for r in results.values()))
    tot_pnl_w = sum(sum(t["net_pnl"] for t in r["trades_detail"] if t["net_pnl"] > 0) for r in results.values())
    tot_pnl_l = abs(sum(sum(t["net_pnl"] for t in r["trades_detail"] if t["net_pnl"] <= 0) for r in results.values()))
    tot_pf = (tot_pnl_w / tot_pnl_l) if tot_pnl_l > 0 else 0.0
    print("-" * 85)
    print(f"{'TOTAL PORTFOLIO':<24} | {total_trades:<6} | {tot_wr:6.1f}% | ${total_net:9.2f} | ${total_fees:7.2f} | {tot_pf:6.2f}")
    
    return results

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "10hz"
    res = run_replay(mode)
    out_file = f"audits/replay_evaluation_{mode}.json"
    with open(out_file, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\nSaved results to {out_file}")
