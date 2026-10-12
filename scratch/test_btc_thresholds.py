import glob
import sys
sys.path.insert(0, ".")

from scratch.grid_test_btc import eval_config

def main():
    btc_files = sorted(glob.glob("data/btc/hl_btc_l2_20261004_*.jsonl") + glob.glob("data/btc/hl_btc_l2_20261003_2*.jsonl"))
    print(f"Loaded {len(btc_files)} BTC files.")

    for eth in [0.75, 0.80, 0.82, 0.85, 0.88]:
        cfg = {
            "min_volatility_bps": 3.8,
            "trailing_stop_activation_bps": 2.5,
            "trailing_stop_distance_bps": 1.0,
            "entry_threshold": eth,
            "max_holding_time_secs": 180,
        }
        res = eval_config(btc_files, cfg)
        print(f"Thresh: {eth:4.2f} | Trades: {res['total']:2d} | Win: {res['wr']:4.1f}% | Gross: ${res['gross']:+6.2f} | Fees: -${res['fees']:5.2f} | Net: ${res['net']:+6.2f} | Trails: {res['trails']:2d} | TimeLimits: {res['tlimits']:2d}")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
