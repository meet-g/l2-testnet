import sys, os
sys.path.insert(0, ".")
from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner
import glob

cfg = AppConfig()
cfg.strategies = StrategiesConfig.load("strategies.json")

# Test on 3 files
data_dir = os.path.join("data", "btc") if os.path.isdir(os.path.join("data", "btc")) else "data"
all_files = sorted(glob.glob(os.path.join(data_dir, "hl_btc_l2_*.jsonl")))

for filepath in all_files[10:14]:
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

    print(os.path.basename(filepath))
    for name in ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"]:
        st = runner.evaluator.strategies.get(name)
        trades = st.trades if st else []
        n = len(trades)
        w = sum(1 for t in trades if t.net_pnl_usd > 0)
        pct = (w / n * 100) if n else 0
        pnl = sum(t.net_pnl_usd for t in trades)
        print(f"  {name:20s}: trades={n:2d}, wins={w:2d} ({pct:.1f}%), net={pnl:+.2f}")
