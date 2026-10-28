import sys, os, glob, json
from collections import defaultdict
from multiprocessing import Pool, cpu_count
sys.path.insert(0, ".")

import scripts.test_all_strategies_all_data as mod

def main():
    files = glob.glob("data/hype/*.jsonl")
    files.sort(key=lambda f: os.path.getsize(f), reverse=True)
    tasks = [(f, 5.0) for f in files]

    with open("strategies.json", "r", encoding="utf-8") as f:
        strat_data = json.load(f)

    qr = strat_data["execution_strategies"]["Queue_Replenishment"]
    qr["entry_threshold"] = 0.985
    qr["hedge_reversal_threshold"] = -0.10
    qr["hedge_trigger_loss_bps"] = -3.5
    qr["trailing_stop_activation_bps"] = 4.0
    qr["trailing_stop_distance_bps"] = 1.5
    qr["min_volatility_bps"] = 4.5
    qr["take_profit_bps"] = 20.0

    with open("strategies.json", "w", encoding="utf-8") as f:
        json.dump(strat_data, f, indent=2)

    print("Running 506 files to inspect trade exit distributions...", flush=True)
    with Pool(processes=min(8, cpu_count()), initializer=mod._init_worker, initargs=("strategies.json", ["Queue_Replenishment"])) as pool:
        results = pool.map(mod.replay_single_dataset, tasks)

    exit_stats = defaultdict(lambda: {"count": 0, "gross": 0.0, "fees": 0.0, "net": 0.0})
    total_trades = 0

    for r in results:
        for tr in r.get("detailed_trades", []):
            if tr.get("strategy") == "Queue_Replenishment":
                reason = tr.get("exit_reason", "UNKNOWN")
                exit_stats[reason]["count"] += 1
                exit_stats[reason]["gross"] += tr.get("gross_pnl", 0.0)
                exit_stats[reason]["fees"] += tr.get("fees", 0.0)
                exit_stats[reason]["net"] += tr.get("net_pnl", 0.0)
                total_trades += 1

    print(f"\nTotal Trades Inspected: {total_trades}")
    print(f"{'Exit Reason':<24} | {'Count':<5} | {'Gross ($)':<10} | {'Fees ($)':<10} | {'Net ($)':<10}")
    print("-" * 70)
    for reason, d in sorted(exit_stats.items(), key=lambda x: x[1]["net"]):
        cnt = d["count"]
        print(f"{reason:<24} | {cnt:<5} | {d['gross']:+10.2f} | {d['fees']:10.2f} | {d['net']:+10.2f}")

if __name__ == "__main__":
    main()
