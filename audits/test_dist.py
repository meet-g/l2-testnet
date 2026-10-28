import sys, os, glob, time, json
from multiprocessing import Pool, cpu_count
sys.path.insert(0, ".")

import scripts.test_all_strategies_all_data as mod

files = glob.glob("data/hype/*.jsonl")
files.sort(key=lambda f: os.path.getsize(f), reverse=True)
tasks = [(f, 5.0) for f in files]

candidates = [
    # (name, tr_act, tr_dist, tp)
    ("tr4.0_dist1.2_tp30", 4.0, 1.2, 30.0),
    ("tr3.8_dist1.2_tp30", 3.8, 1.2, 30.0),
    ("tr3.6_dist1.1_tp30", 3.6, 1.1, 30.0),
    ("tr4.0_dist1.3_tp30", 4.0, 1.3, 30.0),
    ("tr4.0_dist1.5_tp32", 4.0, 1.5, 32.0),
]

def eval_cand(cand):
    name, tr_act, tr_dist, tp = cand
    with open("strategies.json", "r", encoding="utf-8") as f:
        strat_data = json.load(f)

    qr = strat_data["execution_strategies"]["Queue_Replenishment"]
    qr["entry_threshold"] = 0.985
    qr["take_profit_bps"] = tp
    qr["trailing_stop_activation_bps"] = tr_act
    qr["trailing_stop_distance_bps"] = tr_dist
    qr["hedge_trigger_loss_bps"] = -3.5
    qr["hedge_reversal_threshold"] = -0.15
    qr["max_holding_time_secs"] = 180

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

    print(f"[{name:<20}] Standalone: Trds={qr_standalone_trds:3d}, Net=${qr_standalone_net:+7.2f} | Combined: Trds={port_trds:4d}, Net=${port_net:+8.2f}", flush=True)

if __name__ == "__main__":
    for c in candidates:
        eval_cand(c)
