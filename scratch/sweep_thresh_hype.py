import glob
import sys
sys.path.insert(0, ".")

from scratch.grid_test_hype import eval_config

def main():
    hype_files = sorted(glob.glob("data/hype/hl_hype_l2_*.jsonl"))

    print(f"Testing Entry Thresholds across 18 HYPE files...")
    for eth in [0.75, 0.80, 0.82, 0.85, 0.88, 0.90]:
        cfg = {
            "min_volatility_bps": 4.5,
            "trailing_stop_activation_bps": 2.5,
            "trailing_stop_distance_bps": 1.0,
            "entry_threshold": eth,
            "max_holding_time_secs": 180,
        }
        res = eval_config(hype_files, cfg)
        print(f"Thresh: {eth:4.2f} | Trades: {res['total']:2d} | Win: {res['wr']:4.1f}% | Gross: ${res['gross']:+6.2f} | Fees: -${res['fees']:5.2f} | Net: ${res['net']:+6.2f} | Trails: {res['trails']:2d} | Stops: {res['stops']:2d} | TimeLimits: {res['tlimits']:2d}")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
