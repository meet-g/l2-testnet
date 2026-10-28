import sys, os, glob, time, json
from multiprocessing import Pool, cpu_count
sys.path.insert(0, ".")

import scripts.test_all_strategies_all_data as mod

files = glob.glob("data/hype/*.jsonl")
files.sort(key=lambda f: os.path.getsize(f), reverse=True)
tasks = [(f, 5.0) for f in files]

candidates = [
    # (name, eth, tp, tr_act, tr_dist, h_loss, h_rev, cd)
    ("c1_tp15_tr4.0_1.2_hl-3.0_cd180", 0.985, 15.0, 4.0, 1.2, -3.0, -0.10, 180),
    ("c2_tp18_tr4.0_1.2_hl-3.0_cd180", 0.985, 18.0, 4.0, 1.2, -3.0, -0.10, 180),
    ("c3_tp20_tr4.0_1.2_hl-3.0_cd180", 0.985, 20.0, 4.0, 1.2, -3.0, -0.10, 180),
    ("c4_tp20_tr3.8_1.2_hl-3.0_cd180", 0.985, 20.0, 3.8, 1.2, -3.0, -0.10, 180),
    ("c5_eth0.986_tp20_tr4.0_1.2",     0.986, 20.0, 4.0, 1.2, -3.0, -0.10, 180),
    ("c6_eth0.986_tp16_tr4.0_1.2",     0.986, 16.0, 4.0, 1.2, -3.0, -0.10, 180),
    ("c7_eth0.988_tp20_tr4.0_1.2",     0.988, 20.0, 4.0, 1.2, -3.0, -0.10, 180),
    ("c8_tp20_tr4.0_1.2_hl-2.8_cd180", 0.985, 20.0, 4.0, 1.2, -2.8, -0.08, 180),
]

def eval_cand(cand):
    name, eth, tp, tr_act, tr_dist, h_loss, h_rev, cd = cand
    with open("strategies.json", "r", encoding="utf-8") as f:
        strat_data = json.load(f)

    qr = strat_data["execution_strategies"]["Queue_Replenishment"]
    qr["entry_threshold"] = eth
    qr["take_profit_bps"] = tp
    qr["trailing_stop_activation_bps"] = tr_act
    qr["trailing_stop_distance_bps"] = tr_dist
    qr["hedge_trigger_loss_bps"] = h_loss
    qr["hedge_reversal_threshold"] = h_rev
    qr["loss_cooldown_secs"] = cd

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
    pf = (tot_gross / tot_fees) if tot_fees > 0 else 0.0 # approx
    elapsed = time.time() - t0
    print(f"[{name:<32}] {elapsed:4.1f}s | Trds: {tot_trades:3d} (W:{tot_wins}/L:{tot_losses}, Stp:{tot_stops}/Hdg:{tot_hedges}/TP:{tot_tps}/Trl:{tot_trails}) | WR: {wr:4.1f}% | Gross: {tot_gross:+8.2f} | Fees: {tot_fees:7.2f} | NET: {tot_net:+8.2f}", flush=True)

if __name__ == "__main__":
    print(f"Testing fine-tuning candidates on {len(files)} files...", flush=True)
    for c in candidates:
        eval_cand(c)
