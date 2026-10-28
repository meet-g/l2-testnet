import sys, os, glob, time, json
from multiprocessing import Pool, cpu_count
sys.path.insert(0, ".")

import scripts.test_all_strategies_all_data as mod

files = glob.glob("data/hype/*.jsonl")
files.sort(key=lambda f: os.path.getsize(f), reverse=True)
tasks = [(f, 5.0) for f in files]

candidates = [
    ("hold90s", 90),
    ("hold120s", 120),
    ("hold150s", 150),
    ("hold180s", 180),
]

def eval_cand(cand):
    name, hold = cand
    with open("strategies.json", "r", encoding="utf-8") as f:
        strat_data = json.load(f)

    qr = strat_data["execution_strategies"]["Queue_Replenishment"]
    qr["entry_threshold"] = 0.985
    qr["take_profit_bps"] = 30.0
    qr["trailing_stop_activation_bps"] = 4.0
    qr["trailing_stop_distance_bps"] = 1.5
    qr["hedge_trigger_loss_bps"] = -3.5
    qr["hedge_reversal_threshold"] = -0.15
    qr["max_holding_time_secs"] = hold

    with open("strategies.json", "w", encoding="utf-8") as f:
        json.dump(strat_data, f, indent=2)

    # 1. Standalone
    with Pool(processes=min(12, cpu_count()), initializer=mod._init_worker, initargs=("strategies.json", ["Queue_Replenishment"])) as pool:
        standalone_res = pool.map(mod.replay_single_dataset, tasks)

    qr_standalone_net = sum(r["strategies"].get("Queue_Replenishment", {}).get("net_pnl", 0.0) for r in standalone_res)
    qr_standalone_trds = sum(r["strategies"].get("Queue_Replenishment", {}).get("trades", 0) for r in standalone_res)

    # 2. Portfolio
    all_strats = ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion", "Queue_Replenishment"]
    with Pool(processes=min(12, cpu_count()), initializer=mod._init_worker, initargs=("strategies.json", all_strats)) as pool:
        portfolio_res = pool.map(mod.replay_single_dataset, tasks)

    port_net = sum(r["file_net"] for r in portfolio_res)
    port_trds = sum(r["file_trades"] for r in portfolio_res)

    print(f"[{name:<12}] Standalone: Trds={qr_standalone_trds:3d}, Net=${qr_standalone_net:+7.2f} | Combined: Trds={port_trds:4d}, Net=${port_net:+8.2f}", flush=True)

if __name__ == "__main__":
    for c in candidates:
        eval_cand(c)
