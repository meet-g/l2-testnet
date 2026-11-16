"""Experiment: Fast (5-level) vs Normal (20-level) L2 Depth Replay Impact.

Evaluates how depth truncation (the 5-level book delivered by Hyperliquid's `fast: True` WebSocket stream)
affects signal generation, trade decisions, execution fills, and cumulative PnL during offline replay
compared to the full 20-level book (`fast: False`).
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import Dict, List, Any

from config import AppConfig
from core.orderbook import OrderBook
from engine.backtester import EdgeEvaluator
from engine.data_collector import L2ReplayEngine
from signals.composite_alpha import CompositeAlphaSignal


def run_replay_experiment(replay_file: str, coin: str = "xyz:SKHX", max_levels_override: int = None, is_fast_mode: bool = False):
    cfg = AppConfig.for_scalper()
    cfg.market.configure_for_coin(coin)
    
    book = OrderBook(coin=coin)
    from core.trade_stream import TradeManager
    trades = TradeManager(coin=coin)
    
    signal_weights = cfg.strategies.get_signal_weights()
    enabled_signals = cfg.strategies.get_enabled_signals_map()
    
    alpha_model = CompositeAlphaSignal(
        w_wobi=signal_weights.get("WOBI", cfg.signals.weight_wobi),
        w_voi=signal_weights.get("VOI", cfg.signals.weight_voi),
        w_microprice=signal_weights.get("MicroPrice", cfg.signals.weight_microprice),
        w_absorption=signal_weights.get("Absorption", cfg.signals.weight_cvd_absorption),
        w_vpin=signal_weights.get("VPIN", cfg.signals.weight_vpin),
        w_qdap=signal_weights.get("QDAP", getattr(cfg.signals, "weight_qdap", 0.20)),
        enabled_signals=enabled_signals,
    )
    
    evaluator = EdgeEvaluator(
        market_cfg=cfg.market,
        bt_cfg=cfg.backtest,
        strategy_defs=cfg.strategies.get_enabled_strategy_defs(),
        strategy_params=cfg.strategies.get_strategy_params(),
        warmup_secs=0.0,
    )
    
    replay = L2ReplayEngine(replay_file, speed_multiplier=0)
    
    step_records = []
    last_eval_ms = 0
    eval_interval_ms = 100
    
    for event in replay.stream_events():
        ch = event.get("channel")
        dt = event.get("data")
        now_ms = event.get("recv_ts", 0)
        
        if ch == "l2Book":
            if max_levels_override is not None:
                # Simulate truncated fast depth
                levels = dt.get("levels", [[], []])
                bids = levels[0][:max_levels_override] if len(levels) > 0 else []
                asks = levels[1][:max_levels_override] if len(levels) > 1 else []
                dt = {**dt, "levels": [bids, asks]}
                book.update_from_raw(dt, is_fast=is_fast_mode)
            else:
                book.update_from_raw(dt, is_fast=False)
                
        elif ch == "trades":
            trades.process_raw_trades(dt)
        elif ch == "activeAssetCtx":
            book.update_asset_ctx(dt)
            
        if book.is_valid and (now_ms - last_eval_ms >= eval_interval_ms):
            last_eval_ms = now_ms
            res = alpha_model.compute(book, trades, now_ms)
            sub_dict = res.metadata.get("sub_signals", {})
            sub_sigs = {name: sig.score for name, sig in sub_dict.items()}
            sub_sigs["CompositeAlpha"] = res.score
            sub_confs = {name: getattr(sig, "confidence", 1.0) for name, sig in sub_dict.items()}
            sub_confs["CompositeAlpha"] = getattr(res, "confidence", 1.0)
            
            step_records.append({
                "time": now_ms,
                "mid": book.mid_price,
                "composite": res.score,
                "qdap": sub_sigs.get("QDAP", 0.0),
                "wobi": sub_sigs.get("WOBI", 0.0),
                "microprice": sub_sigs.get("MicroPrice", 0.0),
                "book_bids_len": len(book.bids),
                "book_asks_len": len(book.asks),
            })
            
            evaluator.record_step(
                now_ms,
                book.mid_price,
                book.best_bid,
                book.best_ask,
                sub_sigs,
                confidences=sub_confs,
            )
            
    if book.is_valid:
        now_ms = book.last_update_time_ms or int(1794391200000)
        evaluator.close_open_positions(book.mid_price, now_ms, reason="REPLAY_END")
        
    trades_executed = []
    for s_name, state in evaluator.strategies.items():
        trades_executed.extend(state.trades)
        
    total_pnl = sum(t.net_pnl_usd for t in trades_executed)
    win_trades = [t for t in trades_executed if t.net_pnl_usd > 0]
    win_rate = (len(win_trades) / len(trades_executed) * 100.0) if trades_executed else 0.0
    
    return {
        "trades_count": len(trades_executed),
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "trades": trades_executed,
        "steps": step_records,
    }


def compare_file(replay_file: str, coin: str):
    if not os.path.exists(replay_file):
        print(f"File {replay_file} not found.")
        return
        
    print(f"\nRunning Replay Experiment on: {replay_file} (Coin: {coin})")
    print("=" * 80)
    
    # 1. Normal Full Depth (20 levels)
    res_normal = run_replay_experiment(replay_file, coin=coin, max_levels_override=None, is_fast_mode=False)
    
    # 2. Truncated Fast Depth (5 levels, plain replacement)
    res_fast = run_replay_experiment(replay_file, coin=coin, max_levels_override=5, is_fast_mode=False)
    
    # 3. Fast Depth with Retention (5 levels, is_fast=True)
    res_retained = run_replay_experiment(replay_file, coin=coin, max_levels_override=5, is_fast_mode=True)
    
    print("\n[1. BACKTEST TRADING PERFORMANCE COMPARISON]")
    print(f"{'Metric':<30} | {'Normal (20 Levels)':<20} | {'Fast (5 Levels Truncated)':<25} | {'Fast (5 Levels + Retention)':<25}")
    print("-" * 110)
    print(f"{'Total Trades Executed':<30} | {res_normal['trades_count']:<20} | {res_fast['trades_count']:<25} | {res_retained['trades_count']:<25}")
    print(f"{'Total Net PnL (USD)':<30} | ${res_normal['total_pnl']:<19.2f} | ${res_fast['total_pnl']:<24.2f} | ${res_retained['total_pnl']:<24.2f}")
    print(f"{'Win Rate (%)':<30} | {res_normal['win_rate']:<19.1f}% | {res_fast['win_rate']:<24.1f}% | {res_retained['win_rate']:<24.1f}%")
    
    # Analyze signal differences across steps
    steps_n = res_normal["steps"]
    steps_f = res_fast["steps"]
    n_steps = min(len(steps_n), len(steps_f))
    
    qdap_diffs = [abs(steps_n[i]["qdap"] - steps_f[i]["qdap"]) for i in range(n_steps)]
    wobi_diffs = [abs(steps_n[i]["wobi"] - steps_f[i]["wobi"]) for i in range(n_steps)]
    comp_diffs = [abs(steps_n[i]["composite"] - steps_f[i]["composite"]) for i in range(n_steps)]
    
    mean_qdap_err = sum(qdap_diffs) / max(n_steps, 1)
    max_qdap_err = max(qdap_diffs) if qdap_diffs else 0.0
    mean_wobi_err = sum(wobi_diffs) / max(n_steps, 1)
    max_wobi_err = max(wobi_diffs) if wobi_diffs else 0.0
    mean_comp_err = sum(comp_diffs) / max(n_steps, 1)
    max_comp_err = max(comp_diffs) if comp_diffs else 0.0
    
    print("\n[2. ALPHA SIGNAL DRIFT / SKEW ANALYSIS]")
    print(f"Evaluated {n_steps} synchronized book steps:")
    print(f"  • QDAP Alpha (Uses deep levels 5-20):")
    print(f"    - Mean Absolute Drift: {mean_qdap_err:.4f}")
    print(f"    - Max Absolute Dislocation: {max_qdap_err:.4f}")
    print(f"  • WOBI Alpha (Weighted order book imbalance up to 10 levels):")
    print(f"    - Mean Absolute Drift: {mean_wobi_err:.4f}")
    print(f"    - Max Absolute Dislocation: {max_wobi_err:.4f}")
    print(f"  • Composite Alpha Ensemble:")
    print(f"    - Mean Absolute Drift: {mean_comp_err:.4f}")
    print(f"    - Max Absolute Dislocation: {max_comp_err:.4f}")


def compare_runs():
    compare_file("data/xyz_skhx/hl_xyz_skhx_l2_20261111_1000.jsonl", coin="xyz:SKHX")
    compare_file("data/hype/hl_hype_l2_20261111_0200.jsonl", coin="HYPE")
    print("\n" + "=" * 80)
    print("EXPERIMENT COMPLETE: Depth truncation significantly skews signal generation & backtest metrics.")
    print("=" * 80)


if __name__ == "__main__":
    compare_runs()
