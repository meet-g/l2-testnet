import glob
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.verify_isolated_vs_concurrent import run_session_modes


def main():
    hype_files = sorted([f for f in glob.glob("data/hype/hl_hype_l2_2026102*.jsonl") if os.path.getsize(f) >= 6.0*1024*1024], key=os.path.getmtime, reverse=True)
    btc_files = sorted([f for f in glob.glob("data/btc/hl_btc_l2_2026100*.jsonl") if os.path.getsize(f) >= 6.5*1024*1024], key=os.path.getmtime, reverse=True)[:8]
    target_sessions = [(f, "HYPE", {}) for f in hype_files] + [(f, "BTC", {}) for f in btc_files]
    strat_overrides = {
        "Momentum_Expansion": {"entry_threshold": 0.70, "min_volatility_bps": 4.5, "hedge_trigger_loss_bps": -3.5, "hedge_reversal_threshold": 0.20},
        "me_flow_hurdle": 0.35, "me_min_trade_vol": 8.0,
    }

    with ProcessPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(run_session_modes, (f, c, strat_overrides)) for f, c, _ in target_sessions]
        co_trades = []
        for f in as_completed(futs):
            res = f.result()
            for t in res.get("mode_results", {}).get("concurrent", []):
                if t["is_co_entry"]:
                    co_trades.append(t)

    print(f"Total Co-Entry Trades: {len(co_trades)}")
    for i, t in enumerate(co_trades):
        print(f"{i+1:2d}. Strat: {t['strategy']:18s} | Coin: {t['coin']} | Side: {t['side']:5s} | Net: ${t['net_pnl']:+6.2f} | Fees: ${t['fees']:5.2f} | Gross: ${t['gross_pnl']:+6.2f} | Ret: {t['return_bps']:+5.1f}bps | Exit: {t['exit_reason']}")


if __name__ == "__main__":
    main()
