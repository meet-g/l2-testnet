import sys, os, glob
sys.path.insert(0, ".")
from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner

cfg = AppConfig()
cfg.strategies = StrategiesConfig.load("strategies.json")
data_dir = os.path.join("data", "btc") if os.path.isdir(os.path.join("data", "btc")) else "data"
all_files = sorted(glob.glob(os.path.join(data_dir, "hl_btc_l2_*.jsonl")))

hc_w_tot, hc_n_tot = 0, 0
cc_w_tot, cc_n_tot = 0, 0
me_w_tot, me_n_tot = 0, 0

for idx, filepath in enumerate(all_files):
    runner = L2EngineRunner(config=cfg, record_data=False)
    replay = L2ReplayEngine(filepath, speed_multiplier=10000.0)
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
        if runner.book.is_valid and (now_ms - last_eval_ms >= eval_interval_ms):
            last_eval_ms = now_ms
            res = runner.alpha_model.compute(runner.book, runner.trades, now_ms)
            sub_sigs = {name: sig.score for name, sig in res.metadata.get("sub_signals", {}).items()}
            sub_sigs["CompositeAlpha"] = res.score
            runner.evaluator.record_step(now_ms, runner.book.mid_price, runner.book.best_bid, runner.book.best_ask, sub_sigs)

    if runner.book.is_valid:
        runner.evaluator.close_open_positions(runner.book.mid_price, runner.book.last_update_time_ms, reason="SESSION_SHUTDOWN")

    hc_t = runner.evaluator.strategies.get("Hedged_Convexity").trades
    cc_t = runner.evaluator.strategies.get("Convexity_Cascade").trades
    me_t = runner.evaluator.strategies.get("Momentum_Expansion").trades

    hc_w = sum(1 for t in hc_t if t.net_pnl_usd > 0)
    cc_w = sum(1 for t in cc_t if t.net_pnl_usd > 0)
    me_w = sum(1 for t in me_t if t.net_pnl_usd > 0)

    hc_w_tot += hc_w
    hc_n_tot += len(hc_t)
    cc_w_tot += cc_w
    cc_n_tot += len(cc_t)
    me_w_tot += me_w
    me_n_tot += len(me_t)

    fn = os.path.basename(filepath)
    print(f"{fn:30s} | HC: {hc_w}/{len(hc_t)} | CC: {cc_w}/{len(cc_t)} | ME: {me_w}/{len(me_t)}")

print("="*60)
print(f"HC Total: {hc_w_tot}/{hc_n_tot} = {hc_w_tot/hc_n_tot*100:.3f}%" if hc_n_tot else "HC 0")
print(f"CC Total: {cc_w_tot}/{cc_n_tot} = {cc_w_tot/cc_n_tot*100:.3f}%" if cc_n_tot else "CC 0")
print(f"ME Total: {me_w_tot}/{me_n_tot} = {me_w_tot/me_n_tot*100:.3f}%" if me_n_tot else "ME 0")
