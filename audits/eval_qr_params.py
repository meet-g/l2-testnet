import sys, os, glob
sys.path.insert(0, ".")
from config import StrategiesConfig
import scripts.test_all_strategies_all_data as mod

files = glob.glob("data/hype/*.jsonl")
files.sort(key=lambda f: os.path.getsize(f), reverse=True)
test_files = files[:35] # 35 representative files
tasks = [(f, 5.0) for f in test_files]

def test_config(name, eth, h_rev, h_loss, tr_act, tr_dist, min_vol, cd_sec):
    cfg = StrategiesConfig.load("strategies.json")
    s = cfg.execution_strategies["Queue_Replenishment"]
    s.entry_threshold = eth
    s.hedge_reversal_threshold = h_rev
    s.hedge_trigger_loss_bps = h_loss
    s.trailing_stop_activation_bps = tr_act
    s.trailing_stop_distance_bps = tr_dist
    s.min_volatility_bps = min_vol
    s.loss_cooldown_secs = cd_sec
    
    # Save to temp strategies json so worker pool sees it
    import json
    with open("strategies_sweep.json", "w") as f:
        json.dump(cfg.to_dict() if hasattr(cfg, "to_dict") else {
            "execution_strategies": {k: vars(v) for k, v in cfg.execution_strategies.items()}
        }, f)
        
    for k in cfg.execution_strategies:
        cfg.execution_strategies[k].enabled = (k == "Queue_Replenishment")
    mod._GLOBAL_STRATEGIES_CFG = cfg
    
    import multiprocessing
    with multiprocessing.Pool(processes=8) as pool:
        results = pool.map(mod.replay_single_dataset, tasks)
        
    total_net = 0.0
    total_trd = 0
    total_gross = 0.0
    total_fees = 0.0
    total_wins = 0
    
    for res in results:
        st = res["strategies"].get("Queue_Replenishment", {})
        total_net += st.get("net_pnl", 0.0)
        total_trd += st.get("trades", 0)
        total_gross += st.get("gross_pnl", 0.0)
        total_fees += st.get("fees", 0.0)
        total_wins += st.get("wins", 0)
        
    wr = (total_wins / total_trd * 100) if total_trd > 0 else 0
    print(f"[{name:<18}] Trd: {total_trd:3d} | WR: {wr:4.1f}% | Gross: {total_gross:+8.2f} | Fees: {total_fees:7.2f} | Net: {total_net:+8.2f}")
    return total_net

if __name__ == "__main__":
    configs = [
        ("Base 0.90, -0.05", 0.90, -0.05, -4.0, 6.0, 2.5, 4.5, 120),
        ("Vol 5.5",         0.90, -0.05, -4.0, 6.0, 2.5, 5.5, 120),
        ("Vol 6.5",         0.90, -0.05, -4.0, 6.0, 2.5, 6.5, 120),
        ("Eth 0.92",        0.92, -0.05, -4.0, 6.0, 2.5, 4.5, 120),
        ("Eth 0.94",        0.94, -0.05, -4.0, 6.0, 2.5, 4.5, 120),
        ("Trail 5.0/2.0",   0.90, -0.05, -4.0, 5.0, 2.0, 4.5, 120),
        ("Hedge -4.5",      0.90, -0.05, -4.5, 6.0, 2.5, 4.5, 120),
        ("Hedge -5.0",      0.90, -0.05, -5.0, 6.0, 2.5, 4.5, 120),
        ("CD 180s",         0.90, -0.05, -4.0, 6.0, 2.5, 4.5, 180),
        ("HRev -0.15",      0.90, -0.15, -4.0, 6.0, 2.5, 4.5, 120),
    ]
    for c in configs:
        test_config(*c)
