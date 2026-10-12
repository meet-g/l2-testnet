import glob
import os
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, ".")

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


def replay_single_hype(fpath, override):
    cfg = AppConfig()
    cfg.market.coin = "HYPE"
    cfg.backtest.order_size_btc = 50.0  # 50 HYPE ~ $4,500 notional
    cfg.sample_rate_hz = 10.0
    cfg.strategies = StrategiesConfig.load("strategies.json")
    if "AdaptiveML" in cfg.strategies.alpha_signals:
        cfg.strategies.alpha_signals["AdaptiveML"].enabled = False

    for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
        st = cfg.strategies.execution_strategies.get(s_name)
        if st:
            for k, v in override.items():
                setattr(st, k, v)

    runner = L2EngineRunner(config=cfg, record_data=False, enable_audit=False)
    replay = L2ReplayEngine(fpath, speed_multiplier=10000.0)

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
            runner.evaluator.record_step(now_ms, runner.book.mid_price, runner.book.best_bid, runner.book.best_ask, sub_sigs)

    if runner.book.is_valid:
        runner.evaluator.close_open_positions(runner.book.mid_price, runner.book.last_update_time_ms or 0, reason="SESSION_SHUTDOWN")

    trades = []
    for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
        st = runner.evaluator.strategies.get(s_name)
        if st and st.trades:
            for t in st.trades:
                trades.append({
                    "strategy": s_name,
                    "gross_pnl": t.gross_pnl_usd,
                    "fees": t.fees_usd,
                    "net_pnl": t.net_pnl_usd,
                    "exit_reason": t.exit_reason,
                    "return_bps": t.return_bps,
                })
    return trades


def eval_config(files, override):
    all_trades = []
    with ProcessPoolExecutor(max_workers=6) as ex:
        futures = [ex.submit(replay_single_hype, f, override) for f in files]
        for fut in futures:
            all_trades.extend(fut.result())

    total = len(all_trades)
    wins = sum(1 for t in all_trades if t["net_pnl"] > 0)
    gross = sum(t["gross_pnl"] for t in all_trades)
    fees = sum(t["fees"] for t in all_trades)
    net = sum(t["net_pnl"] for t in all_trades)
    wr = (wins / total * 100.0) if total else 0.0
    trails = sum(1 for t in all_trades if t["exit_reason"] == "TRAILING_STOP")
    tlimits = sum(1 for t in all_trades if t["exit_reason"] == "TIME_LIMIT")
    stops = sum(1 for t in all_trades if t["exit_reason"] == "STOP_LOSS")
    return {
        "total": total,
        "wins": wins,
        "wr": wr,
        "gross": gross,
        "fees": fees,
        "net": net,
        "trails": trails,
        "tlimits": tlimits,
        "stops": stops,
    }


def main():
    hype_files = sorted(glob.glob("data/hype/hl_hype_l2_*.jsonl"))
    print(f"Loaded {len(hype_files)} HYPE recording files.")

    # 1. Baseline (Uncalibrated: vol=4.5, act=3.2, dist=1.2, hold=180)
    print("\n--- 1. Baseline Test (Uncalibrated) ---")
    baseline_cfg = {
        "min_volatility_bps": 4.5,
        "trailing_stop_activation_bps": 3.2,
        "trailing_stop_distance_bps": 1.2,
        "entry_threshold": 0.80,
        "max_holding_time_secs": 180,
    }
    b_res = eval_config(hype_files, baseline_cfg)
    print(f"Baseline: Trades: {b_res['total']:2d} | Win: {b_res['wr']:4.1f}% | Gross: ${b_res['gross']:+6.2f} | Fees: -${b_res['fees']:5.2f} | Net: ${b_res['net']:+6.2f} | Trails: {b_res['trails']:2d} | TimeLimits: {b_res['tlimits']:2d}")

    # 2. Volatility Gate Sweep
    print("\n--- 2. Volatility Gate Sweep (with Act=2.5, Dist=1.0) ---")
    for vol in [0.0, 1.5, 2.5, 3.5, 4.5, 6.0, 8.0]:
        cfg = {
            "min_volatility_bps": vol,
            "trailing_stop_activation_bps": 2.5,
            "trailing_stop_distance_bps": 1.0,
            "entry_threshold": 0.80,
            "max_holding_time_secs": 180,
        }
        res = eval_config(hype_files, cfg)
        print(f"Vol: {vol:4.1f}b | Trades: {res['total']:2d} | Win: {res['wr']:4.1f}% | Gross: ${res['gross']:+6.2f} | Fees: -${res['fees']:5.2f} | Net: ${res['net']:+6.2f} | Trails: {res['trails']:2d} | TimeLimits: {res['tlimits']:2d}")
        sys.stdout.flush()

    # 3. Trailing Stop Activation Sweep
    print("\n--- 3. Trailing Stop Activation Sweep (Vol=3.5) ---")
    for act in [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
        cfg = {
            "min_volatility_bps": 3.5,
            "trailing_stop_activation_bps": act,
            "trailing_stop_distance_bps": 1.0,
            "entry_threshold": 0.80,
            "max_holding_time_secs": 180,
        }
        res = eval_config(hype_files, cfg)
        print(f"Act: {act:4.1f}b | Trades: {res['total']:2d} | Win: {res['wr']:4.1f}% | Gross: ${res['gross']:+6.2f} | Fees: -${res['fees']:5.2f} | Net: ${res['net']:+6.2f} | Trails: {res['trails']:2d} | TimeLimits: {res['tlimits']:2d}")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
