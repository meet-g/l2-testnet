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

    with Pool(processes=min(8, cpu_count()), initializer=mod._init_worker, initargs=("strategies.json", ["Queue_Replenishment"])) as pool:
        results = pool.map(mod.replay_single_dataset, tasks)

    tot_exits = defaultdict(lambda: [0, 0.0]) # count, net
    tot_stops = 0
    tot_hedges = 0
    tot_tps = 0
    tot_trails = 0
    for r in results:
        st = r["strategies"].get("Queue_Replenishment", {})
        tot_stops += st.get("stops", 0)
        tot_hedges += st.get("hedges", 0)
        tot_tps += st.get("tps", 0)
        tot_trails += st.get("trails", 0)
        for rsn, vals in r.get("exit_stats", {}).items():
            tot_exits[rsn][0] += int(vals[0])
            tot_exits[rsn][1] += float(vals[1])

    print(f"Stops: {tot_stops}, Hedges: {tot_hedges}, TPs: {tot_tps}, Trails: {tot_trails}")
    for rsn, (cnt, net) in tot_exits.items():
        print(f"  {rsn:<25}: count={cnt:3d}, net={net:+8.2f}")

if __name__ == "__main__":
    main()
