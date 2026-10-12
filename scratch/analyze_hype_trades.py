import glob
import sys
sys.path.insert(0, ".")

from scratch.grid_test_hype import replay_single_hype

files = sorted(glob.glob("data/hype/hl_hype_l2_*.jsonl"))
print(f"Analyzing {len(files)} HYPE files...")

trades = []
for f in files:
    trades.extend(replay_single_hype(f, {
        "min_volatility_bps": 4.5,
        "trailing_stop_activation_bps": 2.5,
        "trailing_stop_distance_bps": 1.0,
        "max_holding_time_secs": 180,
    }))

by_strat = {}
for t in trades:
    s = t["strategy"]
    by_strat.setdefault(s, []).append(t)

print("\n--- Strategy Breakdown on HYPE ---")
for s, trs in sorted(by_strat.items()):
    wins = sum(1 for x in trs if x["net_pnl"] > 0)
    net = sum(x["net_pnl"] for x in trs)
    gross = sum(x["gross_pnl"] for x in trs)
    fees = sum(x["fees"] for x in trs)
    reasons = {}
    for x in trs:
        reasons[x["exit_reason"]] = reasons.get(x["exit_reason"], 0) + 1
    print(f"{s:20s}: {len(trs):2d} trades | Win: {wins/len(trs)*100:4.1f}% | Gross: ${gross:+6.2f} | Fees: -${fees:5.2f} | Net: ${net:+6.2f} | Exits: {reasons}")

print("\n--- Sample Trades Details (first 10) ---")
for t in trades[:10]:
    print(f"{t['strategy']:18s} | ret: {t['return_bps']:+5.2f} bps | Gross: ${t['gross_pnl']:+5.2f} | Net: ${t['net_pnl']:+5.2f} | Exit: {t['exit_reason']}")
