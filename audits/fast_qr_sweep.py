import sys, os, glob, time, json
from multiprocessing import Pool, cpu_count
sys.path.insert(0, ".")

import scripts.test_all_strategies_all_data as mod
from config import StrategiesConfig

files = glob.glob("data/hype/*.jsonl")
files.sort(key=lambda f: os.path.getsize(f), reverse=True)
tasks = [(f, 5.0) for f in files]

candidates = [
    # (name, eth, h_rev, h_loss, tr_act, tr_dist, min_vol, tp_bps)
    ("eth0.98_tr4.0_1.5_vol4.5",  0.98,  -0.10, -3.5, 4.0, 1.5, 4.5, 20.0),
    ("eth0.98_tr5.0_2.0_vol4.5",  0.98,  -0.10, -3.5, 5.0, 2.0, 4.5, 20.0),
    ("eth0.98_tr6.0_2.5_vol4.5",  0.98,  -0.10, -3.5, 6.0, 2.5, 4.5, 20.0),
    ("eth0.98_tr5.0_2.0_vol5.5",  0.98,  -0.10, -3.5, 5.0, 2.0, 5.5, 20.0),
    ("eth0.985_tr4.0_1.5_vol4.5", 0.985, -0.10, -3.5, 4.0, 1.5, 4.5, 20.0),
    ("eth0.985_tr5.0_2.0_vol4.5", 0.985, -0.10, -3.5, 5.0, 2.0, 4.5, 20.0),
    ("eth0.985_tr5.0_2.0_vol5.5", 0.985, -0.10, -3.5, 5.0, 2.0, 5.5, 20.0),
    ("eth0.99_tr4.0_1.5_vol4.5",  0.99,  -0.10, -3.5, 4.0, 1.5, 4.5, 20.0),
    ("eth0.99_tr5.0_2.0_vol4.5",  0.99,  -0.10, -3.5, 5.0, 2.0, 4.5, 20.0),
    ("eth0.99_tr5.0_2.0_vol5.5",  0.99,  -0.10, -3.5, 5.0, 2.0, 5.5, 20.0),
]

def eval_candidate(cand):
    name, eth, h_rev, h_loss, tr_act, tr_dist, min_vol, tp_bps = cand
    # Load base strategies.json and override
    with open("strategies.json", "r", encoding="utf-8") as f:
        strat_data = json.load(f)
    
    qr = strat_data["execution_strategies"]["Queue_Replenishment"]
    qr["entry_threshold"] = eth
    qr["hedge_reversal_threshold"] = h_rev
    qr["hedge_trigger_loss_bps"] = h_loss
    qr["trailing_stop_activation_bps"] = tr_act
    qr["trailing_stop_distance_bps"] = tr_dist
    qr["min_volatility_bps"] = min_vol
    qr["take_profit_bps"] = tp_bps
    
    with open("strategies.json", "w", encoding="utf-8") as f:
        json.dump(strat_data, f, indent=2)
        
    num_proc = min(8, cpu_count())
    t0 = time.time()
    with Pool(processes=num_proc, initializer=mod._init_worker, initargs=("strategies.json", ["Queue_Replenishment"])) as pool:
        results = pool.map(mod.replay_single_dataset, tasks)
        
    tot_trades = 0
    tot_gross = 0.0
    tot_fees = 0.0
    tot_net = 0.0
    tot_wins = 0
    tot_losses = 0
    gross_wins = 0.0
    gross_losses = 0.0
    
    for r in results:
        st = r["strategies"].get("Queue_Replenishment", {})
        tot_trades += st.get("trades", 0)
        tot_gross += st.get("gross_pnl", 0.0)
        tot_fees += st.get("fees", 0.0)
        tot_net += st.get("net_pnl", 0.0)
        tot_wins += st.get("wins", 0)
        tot_losses += st.get("losses", 0)
        gross_wins += st.get("gross_wins", 0.0)
        gross_losses += st.get("gross_losses", 0.0)
        
    wr = (tot_wins / tot_trades * 100) if tot_trades > 0 else 0.0
    pf = (gross_wins / gross_losses) if gross_losses > 0 else (999.0 if gross_wins > 0 else 0.0)
    elapsed = time.time() - t0
    
    print(f"[{name:<26}] {elapsed:4.1f}s | Trds: {tot_trades:3d} | WR: {wr:4.1f}% | PF: {pf:4.2f} | Gross: {tot_gross:+8.2f} | Fees: {tot_fees:7.2f} | Net: {tot_net:+8.2f}", flush=True)
    return {
        "name": name,
        "trades": tot_trades,
        "wr": wr,
        "pf": pf,
        "gross": tot_gross,
        "fees": tot_fees,
        "net": tot_net
    }

if __name__ == "__main__":
    print(f"Starting sweep across {len(files)} files...")
    for cand in candidates:
        eval_candidate(cand)
