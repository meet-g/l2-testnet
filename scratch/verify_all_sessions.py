import glob
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, ".")

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


def run_session_verification(coin: str, file_pattern: str, max_files: int = None):
    all_files = sorted(glob.glob(file_pattern))
    if max_files:
        all_files = all_files[:max_files]

    print(f"\n" + "=" * 90)
    print(f"VERIFYING SESSION FOR {coin.upper()}: {len(all_files)} files")
    print("=" * 90)

    cfg = AppConfig()
    cfg.market.coin = coin.upper()
    cfg.sample_rate_hz = 10.0
    cfg.strategies = StrategiesConfig.load("strategies.json")
    if "AdaptiveML" in cfg.strategies.alpha_signals:
        cfg.strategies.alpha_signals["AdaptiveML"].enabled = False

    strat_trades = defaultdict(list)
    start_time = time.time()

    for i, fpath in enumerate(all_files, 1):
        fname = os.path.basename(fpath)
        runner = L2EngineRunner(config=cfg, record_data=False, enable_audit=False)
        replay = L2ReplayEngine(fpath, speed_multiplier=25000.0)

        eval_interval_ms = 100
        last_eval_ms = 0
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

        if runner.book.is_valid:
            runner.evaluator.close_open_positions(
                runner.book.mid_price,
                runner.book.last_update_time_ms or 0,
                reason="SESSION_SHUTDOWN",
            )

        for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
            st = runner.evaluator.strategies.get(s_name)
            if st and st.trades:
                strat_trades[s_name].extend(st.trades)

        if i % 10 == 0 or i == len(all_files):
            print(f"  Processed {i}/{len(all_files)} files ({time.time() - start_time:.1f}s elapsed)...")

    print("\n" + "-" * 90)
    print(f"FINAL AUDIT PERFORMANCE SUMMARY: {coin.upper()}")
    print("-" * 90)
    print(f"{'Strategy':<22} {'Trades':<8} {'Win Rate':<10} {'Gross ($)':<12} {'Fees ($)':<12} {'Net PnL ($)':<14} {'Profit Factor'}")
    print("-" * 90)

    for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
        trs = strat_trades[s_name]
        total = len(trs)
        wins = sum(1 for t in trs if t.net_pnl_usd > 0)
        gross = sum(t.gross_pnl_usd for t in trs)
        fees = sum(t.fees_usd for t in trs)
        net = sum(t.net_pnl_usd for t in trs)
        wr = (wins / total * 100.0) if total else 0.0

        gross_wins = sum(t.gross_pnl_usd for t in trs if t.gross_pnl_usd > 0)
        gross_losses = abs(sum(t.gross_pnl_usd for t in trs if t.gross_pnl_usd < 0))
        pf = (gross_wins / gross_losses) if gross_losses > 0 else 99.9

        print(f"{s_name:<22} {total:<8} {wr:>5.1f}%     {gross:>+10.2f}  {fees:>10.2f}  {net:>+12.2f}  {pf:>6.2f}")

    print("\n" + "-" * 90)
    print("EXIT REASON BREAKDOWN:")
    print("-" * 90)
    for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
        trs = strat_trades[s_name]
        reasons = defaultdict(int)
        for t in trs:
            reasons[t.exit_reason] += 1
        print(f"{s_name}:")
        for r, cnt in sorted(reasons.items()):
            print(f"   {r:<24}: {cnt} trades")


if __name__ == "__main__":
    # Test full BTC session (all files from 20261005 to 20261006)
    run_session_verification("btc", "data/btc/hl_btc_l2_2026100[56]*.jsonl")
    # Test full HYPE session (all files from 20261005 to 20261006)
    run_session_verification("hype", "data/hype/hl_hype_l2_2026100[56]*.jsonl")
