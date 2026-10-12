"""Detailed recursive forensic analysis of trade failure points."""

import json
import os
import sys

csv_path = "audits/session_20261002_012102/all_trades.csv"
jsonl_path = "audits/session_20261002_012102/trades_audit.jsonl"

if not os.path.exists(jsonl_path):
    print(f"File not found: {jsonl_path}")
    sys.exit(1)

trades = []
with open(jsonl_path, "r", encoding="utf-8") as f:
    for line in f:
        trades.append(json.loads(line))

print(f"=== FORENSIC FAILURE AUDIT: {len(trades)} TOTAL TRADES ===")

losers = [t for t in trades if t.get("net_pnl_usd", 0.0) < 0.0]
winners = [t for t in trades if t.get("net_pnl_usd", 0.0) > 0.0]

print(f"Total Winners: {len(winners)} (Sum: +${sum(t['net_pnl_usd'] for t in winners):.2f})")
print(f"Total Losers:  {len(losers)} (Sum: -${abs(sum(t['net_pnl_usd'] for t in losers)):.2f})")

# Breakdown by Exit Reason
reasons = {}
for t in trades:
    r = t["exit_reason"]
    reasons.setdefault(r, []).append(t)

print("\n--- EXIT REASON ATTRIBUTION ---")
for r, tlist in sorted(reasons.items(), key=lambda x: sum(t['net_pnl_usd'] for t in x[1])):
    net = sum(t["net_pnl_usd"] for t in tlist)
    gross = sum(t["gross_pnl_usd"] for t in tlist)
    fees = sum(t["total_fees_usd"] for t in tlist)
    mfe = sum(t.get("peak_unrealized_bps", t.get("peak_mfe_bps", 0.0)) for t in tlist) / len(tlist)
    mae = sum(t.get("trough_unrealized_bps", t.get("trough_mae_bps", 0.0)) for t in tlist) / len(tlist)
    hold = sum(t.get("holding_time_secs", 0.0) for t in tlist) / len(tlist)
    wins = sum(1 for t in tlist if t["net_pnl_usd"] > 0)
    print(f"[{r:<23}] N={len(tlist):<3} | Win: {wins/len(tlist)*100:4.1f}% | Gross: ${gross:+7.2f} | Fees: -${fees:6.2f} | Net: ${net:+7.2f} | MFE: {mfe:+5.1f} bps | MAE: {mae:+5.1f} bps | Hold: {hold:5.1f}s")

# Let's inspect the TIME_LIMIT trades:
time_limit_trades = [t for t in trades if t["exit_reason"] == "TIME_LIMIT"]
print(f"\n--- TIME_LIMIT DEEP DIVE (N={len(time_limit_trades)}) ---")
mfe_distribution = [t.get("peak_unrealized_bps", t.get("peak_mfe_bps", 0.0)) for t in time_limit_trades]
mfe_gt_2 = sum(1 for x in mfe_distribution if x >= 2.0)
mfe_gt_3 = sum(1 for x in mfe_distribution if x >= 3.0)
mfe_gt_4 = sum(1 for x in mfe_distribution if x >= 4.0)
print(f"Trades reaching MFE >= +2.0 bps: {mfe_gt_2} ({mfe_gt_2/len(time_limit_trades)*100:.1f}%)")
print(f"Trades reaching MFE >= +3.0 bps: {mfe_gt_3} ({mfe_gt_3/len(time_limit_trades)*100:.1f}%)")
print(f"Trades reaching MFE >= +4.0 bps: {mfe_gt_4} ({mfe_gt_4/len(time_limit_trades)*100:.1f}%)")

# Let's inspect the DEFENSIVE_MAKER_HEDGE trades:
hedge_trades = [t for t in trades if t["exit_reason"] == "DEFENSIVE_MAKER_HEDGE"]
print(f"\n--- DEFENSIVE_MAKER_HEDGE DEEP DIVE (N={len(hedge_trades)}) ---")
for t in hedge_trades[:5]:
    mae_val = t.get("trough_unrealized_bps", t.get("trough_mae_bps", 0.0))
    print(f"  {t['trade_id']} | {t['strategy_name']} | {t['side']} | Entry: {t['entry_time_iso']} @ ${t['entry_price']} | Exit: {t['exit_time_iso']} @ ${t['exit_price']} | Net: ${t['net_pnl_usd']:+.2f} ({t['return_bps']:+.1f} bps) | MAE: {mae_val:+.1f} bps")

# What happened to the price after DEFENSIVE_MAKER_HEDGE?

# Let's inspect the STOP_LOSS trades:
stop_trades = [t for t in trades if t["exit_reason"] == "STOP_LOSS"]
print(f"\n--- STOP_LOSS DEEP DIVE (N={len(stop_trades)}) ---")
for t in stop_trades:
    mae_val = t.get("trough_unrealized_bps", t.get("trough_mae_bps", 0.0))
    print(f"  {t['trade_id']} | {t['strategy_name']} | {t['side']} | Entry: {t['entry_time_iso']} @ ${t['entry_price']} | Exit: {t['exit_time_iso']} @ ${t['exit_price']} | Net: ${t['net_pnl_usd']:+.2f} ({t['return_bps']:+.1f} bps) | MAE: {mae_val:+.1f} bps")
