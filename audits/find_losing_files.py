import sys, os, glob, json
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
    qr["take_profit_bps"] = 20.0
    qr["trailing_stop_activation_bps"] = 4.0
    qr["trailing_stop_distance_bps"] = 1.5
    qr["hedge_trigger_loss_bps"] = -3.5
    qr["hedge_reversal_threshold"] = -0.12
    qr["min_volatility_bps"] = 4.5

    with open("strategies.json", "w", encoding="utf-8") as f:
        json.dump(strat_data, f, indent=2)

    with Pool(processes=min(8, cpu_count()), initializer=mod._init_worker, initargs=("strategies.json", ["Queue_Replenishment"])) as pool:
        results = pool.map(mod.replay_single_dataset, tasks)

    groups = {
        "Files 0-75 (Large)": results[:76],
        "Files 76-200 (Medium)": results[76:201],
        "Files 201-505 (Small)": results[201:]
    }

    for grp_name, grp_res in groups.items():
        trds = sum(r["strategies"].get("Queue_Replenishment", {}).get("trades", 0) for r in grp_res)
        gross = sum(r["strategies"].get("Queue_Replenishment", {}).get("gross_pnl", 0.0) for r in grp_res)
        fees = sum(r["strategies"].get("Queue_Replenishment", {}).get("fees", 0.0) for r in grp_res)
        net = sum(r["strategies"].get("Queue_Replenishment", {}).get("net_pnl", 0.0) for r in grp_res)
        wins = sum(r["strategies"].get("Queue_Replenishment", {}).get("wins", 0) for r in grp_res)
        wr = (wins / trds * 100) if trds > 0 else 0
        print(f"[{grp_name:<22}] Files: {len(grp_res):3d} | Trds: {trds:3d} | WR: {wr:4.1f}% | Gross: {gross:+8.2f} | Fees: {fees:7.2f} | Net: {net:+8.2f}")

if __name__ == "__main__":
    main()
