import glob, os, sys
sys.path.insert(0, ".")

from scratch.grid_test_btc import eval_config

btc_files = sorted(glob.glob("data/btc/hl_btc_l2_20261004_*.jsonl") + glob.glob("data/btc/hl_btc_l2_20261003_2*.jsonl"))

configs = [
    {"min_volatility_bps": 3.5, "trailing_stop_activation_bps": 2.5, "trailing_stop_distance_bps": 1.0, "max_holding_time_secs": 180},
    {"min_volatility_bps": 3.5, "trailing_stop_activation_bps": 2.5, "trailing_stop_distance_bps": 1.0, "max_holding_time_secs": 120},
    {"min_volatility_bps": 3.5, "trailing_stop_activation_bps": 2.5, "trailing_stop_distance_bps": 1.0, "max_holding_time_secs": 90},
    {"min_volatility_bps": 3.8, "trailing_stop_activation_bps": 2.5, "trailing_stop_distance_bps": 1.0, "max_holding_time_secs": 120},
    {"min_volatility_bps": 3.8, "trailing_stop_activation_bps": 2.5, "trailing_stop_distance_bps": 1.0, "max_holding_time_secs": 90},
]

if __name__ == '__main__':
    for cfg in configs:
        res = eval_config(btc_files, cfg)
        print(f"Vol: {cfg['min_volatility_bps']}b | Hold: {cfg['max_holding_time_secs']:3d}s | Trades: {res['total']:2d} | Win: {res['wr']:4.1f}% | Gross: ${res['gross']:+6.2f} | Fees: -${res['fees']:5.2f} | Net: ${res['net']:+6.2f} | Trails: {res['trails']:2d} | TimeLimits: {res['tlimits']:2d}")
        sys.stdout.flush()
