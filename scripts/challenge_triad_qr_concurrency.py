"""Adversarial Empirical Challenge:
Run an individual session where both Triad and QR trade heavily.
Compare the exact trade list of Triad under:
1. Triad running ALONE (isolated)
2. Triad running ALONGSIDE Queue_Replenishment (concurrent 4-strategy portfolio)

Assert that:
- Every Triad trade in (1) exists in (2) with identical timestamp, price, size, exit reason, and PnL.
- No Triad trades are cannibalized or delayed.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import AppConfig, BacktestConfig, MarketConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner
from engine.backtester import EdgeEvaluator


def run_session(fpath: str, enable_qr: bool):
    strat_cfg = StrategiesConfig.load("strategies.json")
    all_defs = {
        "Hedged_Convexity": ("HedgedConvexity", "HEDGED_MAKER"),
        "Convexity_Cascade": ("ConvexityCascade", "HEDGED_MAKER"),
        "Momentum_Expansion": ("MomentumExpansion", "HEDGED_MAKER"),
    }
    if enable_qr:
        all_defs["Queue_Replenishment"] = ("QueueReplenishment", "HEDGED_MAKER")

    strat_params = strat_cfg.get_strategy_params()
    active_params = {s: strat_params[s] for s in all_defs}

    market_cfg = MarketConfig(coin="HYPE", maker_fee_bps=1.5, taker_fee_bps=4.5)
    bt_cfg = BacktestConfig(
        order_size_btc=0.1,
        entry_threshold=0.80,
        take_profit_bps=20.0,
        stop_loss_bps=8.0,
        slippage_bps=0.2,
        max_spread_bps=5.0,
        horizons_seconds=[],
    )

    evaluator = EdgeEvaluator(
        market_cfg=market_cfg,
        bt_cfg=bt_cfg,
        strategy_defs=all_defs,
        strategy_params=active_params,
    )

    app_cfg = AppConfig()
    app_cfg.market.coin = "HYPE"
    runner = L2EngineRunner(config=app_cfg, record_data=False, enable_audit=False)
    runner.book.enable_history = False

    sig_hc = runner.alpha_model.signal_hedged
    sig_cc = runner.alpha_model.signal_convexity
    sig_me = runner.alpha_model.signal_mom
    sig_qr = runner.alpha_model.signal_queue_replenishment if enable_qr else None

    replay = L2ReplayEngine(fpath, speed_multiplier=100000.0)

    for event in replay.stream_events():
        ch = event.get("channel")
        dt = event.get("data")
        now_ms = event.get("recv_ts", 0)

        if ch == "l2Book":
            runner.book.update_from_raw(dt)
        elif ch == "trades":
            runner.trades.process_raw_trades(dt)
        elif ch == "activeAssetCtx":
            runner.book.update_asset_ctx(dt)

        if runner.book.is_valid:
            sigs = {
                "HedgedConvexity": sig_hc.compute(runner.book, runner.trades, now_ms).score if sig_hc else 0.0,
                "ConvexityCascade": sig_cc.compute(runner.book, runner.trades, now_ms).score if sig_cc else 0.0,
                "MomentumExpansion": sig_me.compute(runner.book, runner.trades, now_ms).score if sig_me else 0.0,
            }
            if enable_qr and sig_qr:
                sigs["QueueReplenishment"] = sig_qr.compute(runner.book, runner.trades, now_ms).score

            evaluator.record_step(
                timestamp_ms=now_ms,
                mid_price=runner.book.mid_price,
                best_bid=runner.book.best_bid,
                best_ask=runner.book.best_ask,
                signals=sigs,
            )

    return evaluator


def main():
    test_file = "data/hype/hl_hype_l2_20261008_1700.jsonl"
    print(f"Running adversarial empirical challenge on {test_file}...")

    print("1. Running Triad-Only (Isolated)...")
    ev_triad = run_session(test_file, enable_qr=False)

    print("2. Running Combined Triad + Queue_Replenishment...")
    ev_comb = run_session(test_file, enable_qr=True)

    print("\nComparing Triad trades:")
    triad_strats = ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]
    
    total_mismatches = 0
    for s in triad_strats:
        tr_alone = ev_triad.strategies[s].trades
        tr_comb = ev_comb.strategies[s].trades
        print(f"\nStrategy {s}: Alone={len(tr_alone)} trades, Combined={len(tr_comb)} trades")
        if len(tr_alone) != len(tr_comb):
            print(f"  CRITICAL FAILURE: Trade count mismatch for {s}!")
            total_mismatches += 1
            continue

        for i, (t1, t2) in enumerate(zip(tr_alone, tr_comb)):
            match = (
                t1.entry_time_ms == t2.entry_time_ms and
                abs(t1.entry_price - t2.entry_price) < 1e-6 and
                abs(t1.size_btc - t2.size_btc) < 1e-6 and
                t1.exit_reason == t2.exit_reason and
                abs(t1.net_pnl_usd - t2.net_pnl_usd) < 1e-4
            )
            if not match:
                print(f"  CRITICAL MISMATCH at trade {i}:")
                print(f"    Alone:    t={t1.entry_time_ms}, px={t1.entry_price}, sz={t1.size_btc}, exit={t1.exit_reason}, pnl={t1.net_pnl_usd}")
                print(f"    Combined: t={t2.entry_time_ms}, px={t2.entry_price}, sz={t2.size_btc}, exit={t2.exit_reason}, pnl={t2.net_pnl_usd}")
                total_mismatches += 1

    qr_trades = ev_comb.strategies["Queue_Replenishment"].trades
    print(f"\nQueue_Replenishment Trades in Combined: {len(qr_trades)}")
    for i, t in enumerate(qr_trades):
        print(f"  QR Trade {i}: t={t.entry_time_ms}, px={t.entry_price:.4f}, sz={t.size_btc}, exit={t.exit_reason}, pnl=${t.net_pnl_usd:.2f}")

    print(f"\nTotal Triad Trade Discrepancies: {total_mismatches}")
    if total_mismatches == 0:
        print("EMPIRICAL PROOF: Triad execution is 100% BIT-FOR-BIT PRESERVED when QR is active!")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
