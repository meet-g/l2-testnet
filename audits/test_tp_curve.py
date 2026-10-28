import sys, os, glob, time, json
from multiprocessing import Pool, cpu_count
sys.path.insert(0, ".")

import scripts.test_all_strategies_all_data as mod

files = glob.glob("data/hype/*.jsonl")
files.sort(key=lambda f: os.path.getsize(f), reverse=True)
tasks = [(f, 5.0) for f in files]

candidates = [
    # (name, tp)
    ("tp28.0", 28.0),
    ("tp30.0", 30.0),
    ("tp32.0", 32.0),
    ("tp35.0", 35.0),
]

def eval_cand(cand):
    name, tp = cand
    with open("strategies.json", "r", encoding="utf-8") as f:
        strat_data = json.load(f)

    qr = strat_data["execution_strategies"]["Queue_Replenishment"]
    qr["entry_threshold"] = 0.985
    qr["take_profit_bps"] = tp
    qr["trailing_stop_activation_bps"] = 4.0
    qr["trailing_stop_distance_bps"] = 1.5
    qr["hedge_trigger_loss_bps"] = -3.5
    qr["hedge_reversal_threshold"] = -0.15
    qr["max_holding_time_secs"] = 180
    qr["min_volatility_bps"] = 4.5
    qr["loss_cooldown_secs"] = 120

    with open("strategies.json", "w", encoding="utf-8") as f:
        json.dump(strat_data, f, indent=2)

    t0 = time.time()
    with Pool(processes=min(8, cpu_count()), initializer=mod._init_worker, initargs=("strategies.json", ["Queue_Replenishment"])) as pool:
        results = pool.map(mod.replay_single_dataset, tasks)

    tot_trades = 0
    tot_gross = 0.0
    tot_fees = 0.0
    tot_net = 0.0
    tot_wins = 0
    tot_losses = 0
    tot_stops = 0
    tot_hedges = 0
    tot_tps = 0
    tot_trails = 0

    for r in results:
        st = r["strategies"].get("Queue_Replenishment", {})
        tot_trades += st.get("trades", 0)
        tot_gross += st.get("gross_pnl", 0.0)
        tot_fees += st.get("fees", 0.0)
        tot_net += st.get("net_pnl", 0.0)
        tot_wins += st.get("wins", 0)
        tot_losses += st.get("losses", 0)
        tot_stops += st.get("stops", 0)
        tot_hedges += st.get("hedges", 0)
        tot_tps += st.get("tps", 0)
        tot_trails += st.get("trails", 0)

    wr = (tot_wins / tot_trades * 100) if tot_trades > 0 else 0.0
    elapsed = time.time() - t0
    print(f"[{name:<12}] {elapsed:4.1f}s | Trds: {tot_trades:3d} (W:{tot_wins}/L:{tot_losses}, Stp:{tot_stops}/Hdg:{tot_hedges}/TP:{tot_tps}/Trl:{tot_trails}) | WR: {wr:4.1f}% | Gross: {tot_gross:+8.2f} | Fees: {tot_fees:7.2f} | NET: {tot_net:+8.2f}", flush=True)

if __name__ == "__main__":
    print(f"Testing TP curve on {len(files)} files...", flush=True)
    for c in candidates:
        eval_cand(c)
