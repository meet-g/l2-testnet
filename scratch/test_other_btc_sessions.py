import glob
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, ".")

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


def replay_single_btc_file(args):
    fpath, override = args
    cfg = AppConfig()
    cfg.market.coin = "BTC"
    cfg.sample_rate_hz = 10.0
    cfg.strategies = StrategiesConfig.load("strategies.json")
    if "AdaptiveML" in cfg.strategies.alpha_signals:
        cfg.strategies.alpha_signals["AdaptiveML"].enabled = False

    for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
        st = cfg.strategies.execution_strategies.get(s_name)
        if st:
            for k, v in override.items():
                setattr(st, k, v)

    runner = L2EngineRunner(config=cfg, record_data=False)
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
                    "side": t.side,
                })
    return trades


def run_session_replay(files, override, max_workers=6):
    all_trades = []
    tasks = [(f, override) for f in files]
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        for res in ex.map(replay_single_btc_file, tasks):
            all_trades.extend(res)

    total = len(all_trades)
    wins = sum(1 for t in all_trades if t["net_pnl"] > 0)
    gross = sum(t["gross_pnl"] for t in all_trades)
    fees = sum(t["fees"] for t in all_trades)
    net = sum(t["net_pnl"] for t in all_trades)
    wr = (wins / total * 100.0) if total else 0.0

    gross_wins = sum(t["gross_pnl"] for t in all_trades if t["net_pnl"] > 0)
    gross_losses = abs(sum(t["gross_pnl"] for t in all_trades if t["net_pnl"] <= 0))
    pf = (gross_wins / gross_losses) if gross_losses > 0 else (99.0 if gross_wins > 0 else 0.0)

    trails = sum(1 for t in all_trades if t["exit_reason"] == "TRAILING_STOP")
    tlimits = sum(1 for t in all_trades if t["exit_reason"] == "TIME_LIMIT")
    stops = sum(1 for t in all_trades if t["exit_reason"] == "STOP_LOSS")

    by_strat = defaultdict(list)
    for t in all_trades:
        by_strat[t["strategy"]].append(t)

    strat_stats = {}
    for s, trs in by_strat.items():
        s_total = len(trs)
        s_wins = sum(1 for x in trs if x["net_pnl"] > 0)
        s_gross = sum(x["gross_pnl"] for x in trs)
        s_fees = sum(x["fees"] for x in trs)
        s_net = sum(x["net_pnl"] for x in trs)
        s_wr = (s_wins / s_total * 100.0) if s_total else 0.0
        strat_stats[s] = {
            "total": s_total,
            "wins": s_wins,
            "wr": s_wr,
            "gross": s_gross,
            "fees": s_fees,
            "net": s_net,
        }

    return {
        "total": total,
        "wins": wins,
        "wr": wr,
        "gross": gross,
        "fees": fees,
        "net": net,
        "pf": pf,
        "trails": trails,
        "tlimits": tlimits,
        "stops": stops,
        "by_strat": strat_stats,
    }


def main():
    print("=" * 80)
    print("TESTING STRATEGIES AGAINST HISTORICAL BTC SESSIONS")
    print("=" * 80)

    all_files = sorted(glob.glob("data/btc/hl_btc_l2_*.jsonl"))
    sessions = defaultdict(list)
    for f in all_files:
        m = re.search(r"hl_btc_l2_(\d{8})", os.path.basename(f))
        if m:
            sessions[m.group(1)].append(f)

    baseline_override = {
        "min_volatility_bps": 4.5,
        "trailing_stop_activation_bps": 3.2,
        "trailing_stop_distance_bps": 1.2,
        "entry_threshold": 0.80,
        "max_holding_time_secs": 180,
    }

    calibrated_override = {
        "min_volatility_bps": 3.8,
        "trailing_stop_activation_bps": 2.5,
        "trailing_stop_distance_bps": 1.0,
        "entry_threshold": 0.80,
        "max_holding_time_secs": 180,
    }

    # Focus on the other large sessions as requested: 20261001, 20261002, 20261003, 20260930, 20260928
    target_dates = ["20261001", "20261002", "20261003", "20260930", "20260928"]

    grand_baseline_trades = 0
    grand_baseline_gross = 0.0
    grand_baseline_fees = 0.0
    grand_baseline_net = 0.0
    grand_baseline_wins = 0

    grand_calib_trades = 0
    grand_calib_gross = 0.0
    grand_calib_fees = 0.0
    grand_calib_net = 0.0
    grand_calib_wins = 0

    for dt in target_dates:
        fl = sessions.get(dt, [])
        if not fl:
            continue
        total_mb = sum(os.path.getsize(f) for f in fl) / (1024 * 1024)
        print(f"\n========================================================")
        print(f"SESSION {dt}: {len(fl)} files ({total_mb:.1f} MB)")
        print(f"========================================================")

        t0 = time.time()
        # 1. Baseline
        b_res = run_session_replay(fl, baseline_override)
        # 2. Calibrated
        c_res = run_session_replay(fl, calibrated_override)
        elapsed = time.time() - t0

        print(f"Completed replay in {elapsed:.1f}s")
        print(f"  [BASELINE]   Trades: {b_res['total']:2d} | Win: {b_res['wr']:5.1f}% | Gross: ${b_res['gross']:+7.2f} | Fees: -${b_res['fees']:6.2f} | Net: ${b_res['net']:+7.2f} | Trails: {b_res['trails']:2d} | Stops: {b_res['stops']:2d} | TimeLimits: {b_res['tlimits']:2d}")
        print(f"  [CALIBRATED] Trades: {c_res['total']:2d} | Win: {c_res['wr']:5.1f}% | Gross: ${c_res['gross']:+7.2f} | Fees: -${c_res['fees']:6.2f} | Net: ${c_res['net']:+7.2f} | Trails: {c_res['trails']:2d} | Stops: {c_res['stops']:2d} | TimeLimits: {c_res['tlimits']:2d}")

        if c_res["by_strat"]:
            print("  --- Calibrated Strategy Breakdown ---")
            for s_name, s_dat in sorted(c_res["by_strat"].items()):
                print(f"    - {s_name:20s}: {s_dat['total']:2d} trs | Win: {s_dat['wr']:5.1f}% | Gross: ${s_dat['gross']:+6.2f} | Fees: -${s_dat['fees']:5.2f} | Net: ${s_dat['net']:+6.2f}")

        grand_baseline_trades += b_res["total"]
        grand_baseline_wins += b_res["wins"]
        grand_baseline_gross += b_res["gross"]
        grand_baseline_fees += b_res["fees"]
        grand_baseline_net += b_res["net"]

        grand_calib_trades += c_res["total"]
        grand_calib_wins += c_res["wins"]
        grand_calib_gross += c_res["gross"]
        grand_calib_fees += c_res["fees"]
        grand_calib_net += c_res["net"]

    print("\n" + "=" * 80)
    print("GRAND TOTAL ACROSS ALL OTHER HISTORICAL BTC SESSIONS")
    print("=" * 80)
    b_wr = (grand_baseline_wins / grand_baseline_trades * 100.0) if grand_baseline_trades else 0.0
    c_wr = (grand_calib_wins / grand_calib_trades * 100.0) if grand_calib_trades else 0.0
    print(f"BASELINE:   Trades: {grand_baseline_trades:3d} | Win Rate: {b_wr:5.1f}% | Gross: ${grand_baseline_gross:+8.2f} | Fees: -${grand_baseline_fees:7.2f} | Net: ${grand_baseline_net:+8.2f}")
    print(f"CALIBRATED: Trades: {grand_calib_trades:3d} | Win Rate: {c_wr:5.1f}% | Gross: ${grand_calib_gross:+8.2f} | Fees: -${grand_calib_fees:7.2f} | Net: ${grand_calib_net:+8.2f}")


if __name__ == "__main__":
    main()
