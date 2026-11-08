"""Diagnostic script: Isolates the root causes of performance degradation on the 2026-11-06 HYPE session.

Tests:
1. Current Event-Driven (live paper parity)
2. Current 10Hz (standard replay)
3. Current 1Hz (downsampled)
4. Legacy Trailing Stop Fee (Maker exit @ 1.5 bps, fills at best_ask)
5. Legacy CVD Timestamp (no decay to wall time, uses last_trade_time_ms)
6. Full Legacy Benchmark (Maker trailing stop + Legacy CVD @ 10Hz)
"""

import glob
import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import BacktestConfig, MarketConfig, StrategiesConfig
from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from engine.backtester import EdgeEvaluator, TradeRecord
from engine.data_collector import L2ReplayEngine
from signals.composite_alpha import CompositeAlphaSignal

CORE_STRATEGIES = [
    "Hedged_Convexity",
    "Convexity_Cascade",
    "Momentum_Expansion",
    "Queue_Replenishment",
]

def run_experiment(
    name: str,
    eval_mode: str = "10hz",
    legacy_trailing_stop: bool = False,
    legacy_cvd: bool = False,
) -> Dict[str, Any]:
    print(f"\n======================================================================")
    print(f"EXPERIMENT: {name} (eval_mode={eval_mode}, legacy_ts={legacy_trailing_stop}, legacy_cvd={legacy_cvd})")
    print(f"======================================================================")

    files = sorted(glob.glob("data/hype/hl_hype_l2_20261106_*.jsonl"))

    m_cfg = MarketConfig(coin="HYPE")
    bt_cfg = BacktestConfig(
        capital_usd=10000.0,
        order_size_btc=0.1,
        horizons_seconds=[],
    )
    strat_cfg = StrategiesConfig.load("strategies.json")
    all_defs = {k: v for k, v in strat_cfg.get_enabled_strategy_defs().items() if k in CORE_STRATEGIES}
    all_params = strat_cfg.get_strategy_params()

    # Monkey patch TradeManager if legacy_cvd requested
    orig_get_cvd = TradeManager.get_cvd_in_window
    if legacy_cvd:
        def legacy_get_cvd(self, window_secs: float, now_ms: Optional[int] = None):
            cutoff_ms = (self.last_trade_time_ms or 0) - int(window_secs * 1000)
            cvd = 0.0
            buy_vol = 0.0
            sell_vol = 0.0
            for t in reversed(self.trades):
                if t.timestamp_ms < cutoff_ms:
                    break
                if t.side == "B":
                    buy_vol += t.size
                    cvd += t.size
                else:
                    sell_vol += t.size
                    cvd -= t.size
            return (cvd, buy_vol, sell_vol)
        TradeManager.get_cvd_in_window = legacy_get_cvd

    evaluator = EdgeEvaluator(
        market_cfg=m_cfg,
        bt_cfg=bt_cfg,
        strategy_defs=all_defs,
        strategy_params=all_params,
    )

    orig_record_step = evaluator.record_step
    if legacy_trailing_stop:
        # Patch evaluator to post-process trades or override the trailing stop exit
        # We can subclass or wrap record_step to adjust trailing stop trades
        pass

    book = OrderBook("HYPE")
    trades = TradeManager("HYPE")
    alpha = CompositeAlphaSignal(enabled_signals={"AdaptiveML": False})

    last_eval_ms = 0
    t0 = time.time()
    total_events = 0

    for fpath in files:
        replay = L2ReplayEngine(fpath, speed_multiplier=1000000.0)
        for event in replay.stream_events():
            total_events += 1
            ch = event.get("channel")
            dt = event.get("data")
            now_ms = event.get("recv_ts", 0)

            if ch == "l2Book":
                book.update_from_raw(dt)
            elif ch == "trades":
                if isinstance(dt, list):
                    trades.process_raw_trades(dt)
            elif ch == "activeAssetCtx":
                book.update_asset_ctx(dt)

            should_eval = False
            if eval_mode == "event_driven" and ch in ("l2Book", "trades"):
                should_eval = True
            elif eval_mode == "10hz" and (now_ms - last_eval_ms >= 100):
                should_eval = True
                last_eval_ms = now_ms
            elif eval_mode == "1hz" and (now_ms - last_eval_ms >= 1000):
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

    # Restore patches
    TradeManager.get_cvd_in_window = orig_get_cvd

    elapsed = time.time() - t0

    # If legacy_trailing_stop requested, adjust the trades that exited on TRAILING_STOP
    # Old logic: exit as MAKER at max(best_ask, target_limit), fee = exit_price * sz * maker_fee_pct (1.5 bps)
    # New logic in evaluator was: best_bid * (1 - slippage), fee = taker_fee_pct (4.5 bps)
    if legacy_trailing_stop:
        for s_name, st in evaluator.strategies.items():
            for t in st.trades:
                if t.exit_reason == "TRAILING_STOP":
                    # Invert the taker fee and spread penalty to restore legacy Maker fill
                    # Delta fee: from 4.5 bps down to 1.5 bps (3.0 bps gain)
                    # Delta price: from best_bid * (1 - slip) up to mid/ask (~1.5 bps gain)
                    sz = abs(t.size_btc)
                    px = t.entry_price
                    notional = px * sz
                    # 4.5 bps of notional fee was charged, change to 1.5 bps
                    fee_delta = notional * (0.00045 - 0.00015)
                    # Slippage & spread delta was ~1.5 bps (half spread 0.75 bps + slippage 0.5 bps)
                    spread_slip_delta = notional * 0.00015
                    t.fees_usd -= fee_delta
                    t.net_pnl_usd += (fee_delta + spread_slip_delta)
                    t.gross_pnl_usd += spread_slip_delta
                    t.return_bps = (t.net_pnl_usd / notional) * 10_000.0

    # Summary
    strat_summary = {}
    tot_trades = 0
    tot_wins = 0
    tot_gross = 0.0
    tot_fees = 0.0
    tot_net = 0.0

    print(f"{'Strategy':<22} | {'Trades':<6} | {'WinRate':<8} | {'Net PnL':<10} | {'Fees':<8} | {'PF':<6} | {'Avg Ret':<10} | {'Exits'}")
    print("-" * 110)

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

        tot_trades += n
        tot_wins += len(wins)
        tot_gross += gross
        tot_fees += fees
        tot_net += net

        exit_reasons = {}
        for t in trades_list:
            exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

        strat_summary[s_name] = {
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
        }
        exits_str = ", ".join(f"{k}:{v}" for k, v in exit_reasons.items())
        print(f"{s_name:<22} | {n:<6} | {wr:6.1f}% | ${net:9.2f} | ${fees:7.2f} | {pf:6.2f} | {avg_ret:+7.2f}bp | {exits_str}")

    tot_wr = (tot_wins / tot_trades * 100.0) if tot_trades > 0 else 0.0
    tot_pnl_w = sum(sum(t.net_pnl_usd for t in st.trades if t.net_pnl_usd > 0) for st in evaluator.strategies.values())
    tot_pnl_l = abs(sum(sum(t.net_pnl_usd for t in st.trades if t.net_pnl_usd <= 0) for st in evaluator.strategies.values()))
    tot_pf = (tot_pnl_w / tot_pnl_l) if tot_pnl_l > 0 else 0.0

    print("-" * 110)
    print(f"{'TOTAL PORTFOLIO':<22} | {tot_trades:<6} | {tot_wr:6.1f}% | ${tot_net:9.2f} | ${tot_fees:7.2f} | {tot_pf:6.2f}")

    return {
        "name": name,
        "elapsed_s": elapsed,
        "total_trades": tot_trades,
        "win_rate": tot_wr,
        "gross_pnl": tot_gross,
        "fees": tot_fees,
        "net_pnl": tot_net,
        "profit_factor": tot_pf,
        "strategies": strat_summary,
    }

if __name__ == "__main__":
    experiments = [
        ("Current_EventDriven", "event_driven", False, False),
        ("Current_10Hz", "10hz", False, False),
        ("Current_1Hz_Downsampled", "1hz", False, False),
        ("Legacy_CVD_Timestamp_10Hz", "10hz", False, True),
        ("Legacy_TrailingStop_Fee_10Hz", "10hz", True, False),
        ("Full_Legacy_Benchmark_10Hz", "10hz", True, True),
    ]
    all_res = {}
    for name, mode, leg_ts, leg_cvd in experiments:
        res = run_experiment(name, eval_mode=mode, legacy_trailing_stop=leg_ts, legacy_cvd=leg_cvd)
        all_res[name] = res

    with open("audits/hype_session_diagnostic_comparison.json", "w") as f:
        json.dump(all_res, f, indent=2)
    print("\nSaved all diagnostic comparisons to audits/hype_session_diagnostic_comparison.json")
