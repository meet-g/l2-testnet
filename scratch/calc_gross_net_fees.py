import sys, os, glob
sys.path.insert(0, ".")
from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner

cfg = AppConfig()
cfg.strategies = StrategiesConfig.load("strategies.json")
data_dir = os.path.join("data", "btc") if os.path.isdir(os.path.join("data", "btc")) else "data"
all_files = sorted(glob.glob(os.path.join(data_dir, "hl_btc_l2_*.jsonl")))

strat_stats = {
    "Hedged_Convexity": {"trades": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "wins": 0},
    "Convexity_Cascade": {"trades": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "wins": 0},
    "Momentum_Expansion": {"trades": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "wins": 0},
}

for filepath in all_files:
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

    for s_name in strat_stats:
        st = runner.evaluator.strategies.get(s_name)
        if not st:
            continue
        trades = st.trades
        strat_stats[s_name]["trades"] += len(trades)
        strat_stats[s_name]["gross_pnl"] += sum(t.gross_pnl_usd for t in trades)
        strat_stats[s_name]["fees"] += sum(t.fees_usd for t in trades)
        strat_stats[s_name]["net_pnl"] += sum(t.net_pnl_usd for t in trades)
        strat_stats[s_name]["wins"] += sum(1 for t in trades if t.net_pnl_usd > 0)

print("\n" + "="*80)
print(f"{'Strategy':22s} | {'Trades':6s} | {'Gross PnL ($)':14s} | {'Net Fees ($)':12s} | {'Net PnL ($)':12s}")
print("="*80)
for s_name, data in strat_stats.items():
    print(f"{s_name:22s} | {data['trades']:6d} | ${data['gross_pnl']:+12.2f}  | -${data['fees']:10.2f} | ${data['net_pnl']:+10.2f}")
print("="*80)
tot_trades = sum(d["trades"] for d in strat_stats.values())
tot_gross = sum(d["gross_pnl"] for d in strat_stats.values())
tot_fees = sum(d["fees"] for d in strat_stats.values())
tot_net = sum(d["net_pnl"] for d in strat_stats.values())
print(f"{'PORTFOLIO TOTAL':22s} | {tot_trades:6d} | ${tot_gross:+12.2f}  | -${tot_fees:10.2f} | ${tot_net:+10.2f}")
print("="*80)
