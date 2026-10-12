import glob
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from scratch.test_other_btc_sessions import run_session_replay


def main():
    all_files = sorted(glob.glob("data/btc/hl_btc_l2_*.jsonl"))
    sessions = defaultdict(list)
    for f in all_files:
        m = re.search(r"hl_btc_l2_(\d{8})", os.path.basename(f))
        if m:
            sessions[m.group(1)].append(f)

    dates = ["20260928", "20260930", "20261001", "20261002", "20261003", "20261004"]

    print("=" * 85)
    print("ENTRY THRESHOLD SENSITIVITY ACROSS ENTIRE BTC HISTORY (123 Files, 524 MB)")
    print("=" * 85)

    for eth in [0.80, 0.82, 0.85, 0.88]:
        cfg = {
            "min_volatility_bps": 3.8,
            "trailing_stop_activation_bps": 2.5,
            "trailing_stop_distance_bps": 1.0,
            "entry_threshold": eth,
            "max_holding_time_secs": 180,
        }

        tot_trades = 0
        tot_wins = 0
        tot_gross = 0.0
        tot_fees = 0.0
        tot_net = 0.0
        tot_trails = 0
        tot_tlimits = 0
        tot_stops = 0

        print(f"\n--- Threshold: {eth:.2f} ---")
        for dt in dates:
            fl = sessions.get(dt, [])
            if not fl:
                continue
            res = run_session_replay(fl, cfg)
            tot_trades += res["total"]
            tot_wins += res["wins"]
            tot_gross += res["gross"]
            tot_fees += res["fees"]
            tot_net += res["net"]
            tot_trails += res["trails"]
            tot_tlimits += res["tlimits"]
            tot_stops += res["stops"]
            print(f"  {dt}: {res['total']:3d} trs | Win: {res['wr']:5.1f}% | Gross: ${res['gross']:>+7.2f} | Fees: -${res['fees']:>6.2f} | Net: ${res['net']:>+7.2f} | Trails: {res['trails']:2d} | Stops: {res['stops']:2d} | TL: {res['tlimits']:2d}")

        overall_wr = (tot_wins / tot_trades * 100.0) if tot_trades else 0.0
        print(f"  => TOTAL (Thresh {eth:.2f}): {tot_trades:3d} trs | Win: {overall_wr:5.1f}% | Gross: ${tot_gross:>+8.2f} | Fees: -${tot_fees:>7.2f} | Net: ${tot_net:>+7.2f} | Trails: {tot_trails:2d} | Stops: {tot_stops:2d} | TL: {tot_tlimits:2d}")


if __name__ == "__main__":
    main()
