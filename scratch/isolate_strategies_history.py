import glob
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, ".")

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


def replay_single_strat(args):
    fpath, target_strat, override = args
    cfg = AppConfig()
    cfg.market.coin = "BTC"
    cfg.sample_rate_hz = 10.0
    cfg.strategies = StrategiesConfig.load("strategies.json")
    if "AdaptiveML" in cfg.strategies.alpha_signals:
        cfg.strategies.alpha_signals["AdaptiveML"].enabled = False

    for s_name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
        st = cfg.strategies.execution_strategies.get(s_name)
        if st:
            if s_name == target_strat:
                st.enabled = True
                for k, v in override.items():
                    setattr(st, k, v)
            else:
                st.enabled = False

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

    st = runner.evaluator.strategies.get(target_strat)
    trades = []
    if st and st.trades:
        for t in st.trades:
            trades.append({
                "strategy": target_strat,
                "gross_pnl": t.gross_pnl_usd,
                "fees": t.fees_usd,
                "net_pnl": t.net_pnl_usd,
                "exit_reason": t.exit_reason,
                "return_bps": t.return_bps,
            })
    return trades


def run_strategy_replay(files, target_strat, override, max_workers=6):
    all_trades = []
    tasks = [(f, target_strat, override) for f in files]
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        for res in ex.map(replay_single_strat, tasks):
            all_trades.extend(res)

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
    all_files = sorted(glob.glob("data/btc/hl_btc_l2_*.jsonl"))
    sessions = defaultdict(list)
    for f in all_files:
        m = re.search(r"hl_btc_l2_(\d{8})", os.path.basename(f))
        if m:
            sessions[m.group(1)].append(f)

    dates = ["20260928", "20260930", "20261001", "20261002", "20261003", "20261004"]
    strats = ["Momentum_Expansion", "Hedged_Convexity", "Convexity_Cascade"]

    cfg_calibrated = {
        "min_volatility_bps": 3.8,
        "trailing_stop_activation_bps": 2.5,
        "trailing_stop_distance_bps": 1.0,
        "entry_threshold": 0.80,
        "max_holding_time_secs": 180,
    }

    print("=" * 85)
    print("INDIVIDUAL STRATEGY ISOLATION ACROSS ENTIRE BTC HISTORY (123 Files)")
    print("=" * 85)

    for s in strats:
        print(f"\n========================================================")
        print(f"STRATEGY: {s.upper()}")
        print(f"========================================================")
        tot_trades = 0
        tot_wins = 0
        tot_gross = 0.0
        tot_fees = 0.0
        tot_net = 0.0
        tot_trails = 0
        tot_stops = 0
        tot_tl = 0

        for dt in dates:
            fl = sessions.get(dt, [])
            if not fl:
                continue
            res = run_strategy_replay(fl, s, cfg_calibrated)
            tot_trades += res["total"]
            tot_wins += res["wins"]
            tot_gross += res["gross"]
            tot_fees += res["fees"]
            tot_net += res["net"]
            tot_trails += res["trails"]
            tot_stops += res["stops"]
            tot_tl += res["tlimits"]
            print(f"  {dt}: {res['total']:2d} trs | Win: {res['wr']:5.1f}% | Gross: ${res['gross']:>+6.2f} | Fees: -${res['fees']:>5.2f} | Net: ${res['net']:>+6.2f} | Trails: {res['trails']:2d} | Stops: {res['stops']:2d} | TL: {res['tlimits']:2d}")

        overall_wr = (tot_wins / tot_trades * 100.0) if tot_trades else 0.0
        print(f"  => TOTAL {s}: {tot_trades:3d} trs | Win: {overall_wr:5.1f}% | Gross: ${tot_gross:>+8.2f} | Fees: -${tot_fees:>7.2f} | Net: ${tot_net:>+7.2f} | Trails: {tot_trails:2d} | Stops: {tot_stops:2d} | TL: {tot_tl:2d}")


if __name__ == "__main__":
    main()
