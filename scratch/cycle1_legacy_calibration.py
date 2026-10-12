import glob
import os
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, ".")

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner


def test_strat_calibration(args):
    fpath, strat_name, params = args
    cfg = AppConfig()
    cfg.market.coin = "BTC"
    cfg.sample_rate_hz = 10.0
    cfg.strategies = StrategiesConfig.load("strategies.json")
    if "AdaptiveML" in cfg.strategies.alpha_signals:
        cfg.strategies.alpha_signals["AdaptiveML"].enabled = False

    for s_name, st in cfg.strategies.execution_strategies.items():
        if s_name == strat_name:
            st.enabled = True
            for k, v in params.items():
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

    st = runner.evaluator.strategies.get(strat_name)
    trades = []
    if st and st.trades:
        for t in st.trades:
            trades.append({
                "strategy": strat_name,
                "gross_pnl": t.gross_pnl_usd,
                "fees": t.fees_usd,
                "net_pnl": t.net_pnl_usd,
                "exit_reason": t.exit_reason,
            })
    return trades


def eval_candidate(strat_name, params, files, max_workers=6):
    tasks = [(f, strat_name, params) for f in files]
    all_trades = []
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        for res in ex.map(test_strat_calibration, tasks):
            all_trades.extend(res)

    total = len(all_trades)
    wins = sum(1 for t in all_trades if t["net_pnl"] > 0)
    gross = sum(t["gross_pnl"] for t in all_trades)
    fees = sum(t["fees"] for t in all_trades)
    net = sum(t["net_pnl"] for t in all_trades)
    wr = (wins / total * 100.0) if total else 0.0
    trails = sum(1 for t in all_trades if t["exit_reason"] == "TRAILING_STOP")
    stops = sum(1 for t in all_trades if t["exit_reason"] == "STOP_LOSS")
    tlimits = sum(1 for t in all_trades if t["exit_reason"] == "TIME_LIMIT")
    return {
        "strat": strat_name,
        "total": total,
        "wins": wins,
        "wr": wr,
        "gross": gross,
        "fees": fees,
        "net": net,
        "trails": trails,
        "stops": stops,
        "tlimits": tlimits,
    }


def main():
    files = sorted(glob.glob("data/btc/hl_btc_l2_20261002_0*.jsonl") + glob.glob("data/btc/hl_btc_l2_20261004_0*.jsonl"))

    print("CYCLE 1: CALIBRATING LEGACY STRATEGIES WITH HIGH-CONVICTION GATING")
    print("=" * 95)
    print(f"{'Strategy Name':22s} | {'Thresh':6s} | {'Trades':6s} | {'Win Rate':8s} | {'Gross PnL':10s} | {'Fees':9s} | {'Net PnL':10s} | {'Trails':6s} | {'Stops':5s}")
    print("=" * 95)

    legacy_strats = ["QDAP_Maker", "Composite_Maker", "WOBI_Maker", "MicroPrice_Maker", "Absorption_Fade", "Composite_Taker"]

    for s_name in legacy_strats:
        for eth in [0.65, 0.75, 0.80]:
            p = {
                "entry_threshold": eth,
                "min_volatility_bps": 3.8,
                "trailing_stop_activation_bps": 2.5,
                "trailing_stop_distance_bps": 1.0,
                "max_holding_time_secs": 180,
                "take_profit_bps": 18.0,
                "stop_loss_bps": 12.0,
            }
            res = eval_candidate(s_name, p, files)
            print(f"{res['strat']:22s} | {eth:6.2f} | {res['total']:6d} | {res['wr']:7.1f}% | ${res['gross']:>+9.2f} | -${res['fees']:>7.2f} | ${res['net']:>+9.2f} | {res['trails']:6d} | {res['stops']:5d}")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
