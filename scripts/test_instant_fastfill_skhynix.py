"""Targeted Microstructure Replay Test for Instant_FastFill Scalping Strategy."""

import os
import sys
import time
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from engine.backtester import EdgeEvaluator
from engine.data_collector import L2ReplayEngine
from config import MarketConfig, BacktestConfig, StrategiesConfig
from signals.composite_alpha import CompositeAlphaSignal


def run_test(file_path: str, coin: str = "xyz:SKHX"):
    print(f"\n========================================================")
    print(f"Testing Instant_FastFill on {file_path} ({coin})")
    print(f"========================================================")

    m_cfg = MarketConfig(coin=coin)
    bt_cfg = BacktestConfig(
        capital_usd=10000.0,
        max_spread_bps=5.0,
        horizons_seconds=[],
    )

    strat_cfg = StrategiesConfig.load("strategies.json")
    scalp_defs = {
        "Instant_FastFill": ("InstantFill", strat_cfg.scalping_strategies["Instant_FastFill"].execution_type),
        "MicroPrice_FastFill": ("MicroPrice", "MAKER"),
        "MicroPrice_Maker": ("MicroPrice", "MAKER"),
    }
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
    events = 0

    replay = L2ReplayEngine(file_path, speed_multiplier=100000.0)
    for event in replay.stream_events():
        events += 1
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

            evaluator.record_step(
                timestamp_ms=now_ms,
                mid_price=book.mid_price,
                best_bid=book.best_bid,
                best_ask=book.best_ask,
                signals=sigs,
                confidences=confs,
            )

    evaluator.close_open_positions(book.mid_price, now_ms)
    elapsed = time.time() - t0
    print(f"Replay completed in {elapsed:.2f}s ({events} events)")

    for name in ("Instant_FastFill", "MicroPrice_FastFill", "MicroPrice_Maker"):
        st = evaluator.strategies[name]
        n_trades = len(st.trades)
        wins = sum(1 for t in st.trades if t.net_pnl_usd > 0)
        losses = sum(1 for t in st.trades if t.net_pnl_usd <= 0)
        wr = (wins / n_trades * 100) if n_trades > 0 else 0.0
        gross = sum(t.gross_pnl_usd for t in st.trades)
        fees = sum(t.fees_usd for t in st.trades)
        net = sum(t.net_pnl_usd for t in st.trades)
        g_win = sum(t.gross_pnl_usd for t in st.trades if t.gross_pnl_usd > 0)
        g_loss = abs(sum(t.gross_pnl_usd for t in st.trades if t.gross_pnl_usd < 0))
        pf = (g_win / g_loss) if g_loss > 0 else (99.0 if g_win > 0 else 0.0)
        avg_dur = (sum((t.exit_time_ms - t.entry_time_ms) / 1000.0 for t in st.trades) / n_trades) if n_trades > 0 else 0.0

        print(f"\n--- Strategy: {name} ({st.execution_type}) ---")
        print(f"  Trades: {n_trades} | Win Rate: {wr:.1f}% ({wins}W / {losses}L)")
        print(f"  Gross PnL: ${gross:+.2f} | Fees: ${fees:.2f} | Net PnL: ${net:+.2f}")
        print(f"  Profit Factor: {pf:.2f} | Max Drawdown: ${st.max_drawdown_usd:.2f} | Avg Hold: {avg_dur:.1f}s")
        reasons = {}
        for t in st.trades:
            reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
        print(f"  Exits: {reasons}")


if __name__ == "__main__":
    import glob
    skhx_files = sorted(glob.glob("data/xyz_skhx/hl_xyz_skhx_l2_*.jsonl"))
    if skhx_files:
        run_test(skhx_files[0], "xyz:SKHX")

    skhy_files = sorted(glob.glob("data/xyz_skhy/hl_xyz_skhy_l2_*.jsonl"))
    if skhy_files:
        run_test(skhy_files[0], "xyz:SKHY")
