import sys, os, glob, time, json
from multiprocessing import Pool, cpu_count
sys.path.insert(0, ".")

import scripts.test_all_strategies_all_data as mod

files = glob.glob("data/hype/*.jsonl")
files.sort(key=lambda f: os.path.getsize(f), reverse=True)
tasks = [(f, 5.0) for f in files]

candidates = [
    # (name, cd, min_vol)
    ("cd180_vol4.5", 180, 4.5),
    ("cd120_vol5.0", 120, 5.0),
    ("cd180_vol5.0", 180, 5.0),
    ("cd240_vol4.5", 240, 4.5),
    ("cd60_vol4.5",   60, 4.5),
]

def eval_cand(cand):
    name, cd, min_vol = cand
    with open("strategies.json", "r", encoding="utf-8") as f:
        strat_data = json.load(f)

    qr = strat_data["execution_strategies"]["Queue_Replenishment"]
    qr["entry_threshold"] = 0.985
    qr["take_profit_bps"] = 30.0
    qr["trailing_stop_activation_bps"] = 4.0
    qr["trailing_stop_distance_bps"] = 1.5
    qr["hedge_trigger_loss_bps"] = -3.5
    qr["hedge_reversal_threshold"] = -0.15
    qr["max_holding_time_secs"] = 180
    qr["loss_cooldown_secs"] = cd
    qr["min_volatility_bps"] = min_vol

    with open("strategies.json", "w", encoding="utf-8") as f:
        json.dump(strat_data, f, indent=2)

    all_strats = ["Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion", "Queue_Replenishment"]
    with Pool(processes=min(12, cpu_count()), initializer=mod._init_worker, initargs=("strategies.json", all_strats)) as pool:
        portfolio_res = pool.map(mod.replay_single_dataset, tasks)

    port_net = sum(r["file_net"] for r in portfolio_res)
    port_trds = sum(r["file_trades"] for r in portfolio_res)
    qr_net = sum(r["strategies"].get("Queue_Replenishment", {}).get("net_pnl", 0.0) for r in portfolio_res)
    hc_net = sum(r["strategies"].get("Hedged_Convexity", {}).get("net_pnl", 0.0) for r in portfolio_res)
    cc_net = sum(r["strategies"].get("Convexity_Cascade", {}).get("net_pnl", 0.0) for r in portfolio_res)
    me_net = sum(r["strategies"].get("Momentum_Expansion", {}).get("net_pnl", 0.0) for r in portfolio_res)

    print(f"[{name:<14}] Port Net: ${port_net:+8.2f} (Trds: {port_trds:4d}) | QR: ${qr_net:+7.2f}, HC: ${hc_net:+7.2f}, CC: ${cc_net:+7.2f}, ME: ${me_net:+7.2f}", flush=True)

if __name__ == "__main__":
    for c in candidates:
        eval_cand(c)
