"""Detailed trade-by-trade forensic comparison between Paper Trading and Replay."""

import json
import os
import sys
import pandas as pd
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.verify_paper_replay_parity import run_replay, PAPER_TRADES_CSV

paper_df = pd.read_csv(PAPER_TRADES_CSV)

# Run event-driven replay
res = run_replay("event_driven", throttle_ms=250, enable_qr_from_start=True)
replay_trades = res["trades"]

# Convert replay trades to DataFrame
rows = []
for t in replay_trades:
    entry_iso = datetime.fromtimestamp(t.entry_time_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    exit_iso = datetime.fromtimestamp(t.exit_time_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    rows.append({
        "strategy_name": t.strategy_name,
        "side": t.side,
        "entry_time": entry_iso,
        "entry_time_ms": t.entry_time_ms,
        "entry_price": t.entry_price,
        "size_btc": t.size_btc,
        "exit_time": exit_iso,
        "exit_time_ms": t.exit_time_ms,
        "exit_price": t.exit_price,
        "exit_reason": t.exit_reason,
        "gross_pnl_usd": t.gross_pnl_usd,
        "fees_usd": t.fees_usd,
        "net_pnl_usd": t.net_pnl_usd,
        "return_bps": t.return_bps,
    })

replay_df = pd.DataFrame(rows)
replay_df.to_csv("audits/session_20261107_replay_trades.csv", index=False)

print("\n=======================================================")
print(f"Paper Total Trades: {len(paper_df)} | Replay Total Trades: {len(replay_df)}")
print("=======================================================")

# Compare strategy by strategy
for strat in ["Convexity_Cascade", "Hedged_Convexity", "Momentum_Expansion", "Queue_Replenishment"]:
    p_s = paper_df[paper_df['strategy_name'] == strat]
    r_s = replay_df[replay_df['strategy_name'] == strat]
    print(f"\n--- STRATEGY: {strat} ---")
    print(f"Paper:  trades={len(p_s):<2} gross=${p_s['gross_pnl_usd'].sum():>7.2f} fees=${p_s['total_fees_usd'].sum():>7.2f} net=${p_s['net_pnl_usd'].sum():>7.2f}")
    print(f"Replay: trades={len(r_s):<2} gross=${r_s['gross_pnl_usd'].sum():>7.2f} fees=${r_s['fees_usd'].sum():>7.2f} net=${r_s['net_pnl_usd'].sum():>7.2f}")
    print(f"Delta (Replay - Paper): Net PnL = ${r_s['net_pnl_usd'].sum() - p_s['net_pnl_usd'].sum():>+7.2f}")

# Match trades by approximate entry time (+- 5 seconds)
print("\n=======================================================")
print("EXACT TRADE-BY-TRADE MATCHING & DRIFT ANALYSIS:")
print("=======================================================")
unmatched_paper = []
matched = []

for idx, p_trade in paper_df.iterrows():
    p_time = pd.to_datetime(p_trade['entry_time']).timestamp() * 1000.0
    strat = p_trade['strategy_name']
    
    # Find matching replay trade
    candidates = replay_df[
        (replay_df['strategy_name'] == strat) &
        (replay_df['side'] == p_trade['side']) &
        (abs(replay_df['entry_time_ms'] - p_time) < 15000) # within 15s
    ]
    
    if len(candidates) > 0:
        r_trade = candidates.iloc[0]
        matched.append((p_trade, r_trade))
    else:
        unmatched_paper.append(p_trade)

print(f"Successfully matched: {len(matched)} / {len(paper_df)} paper trades")
print(f"Paper trades with NO replay match ({len(unmatched_paper)}):")
for p in unmatched_paper:
    print(f"  [PAPER ONLY] {p['trade_id']} | {p['strategy_name']:<20} | {p['side']} | Entry: {p['entry_time']} @ ${p['entry_price']} | Exit: {p['exit_time']} ({p['exit_reason']}) | Net: ${p['net_pnl_usd']:.2f}")

# Replay trades with no paper match
unmatched_replay = []
for idx, r_trade in replay_df.iterrows():
    r_time = r_trade['entry_time_ms']
    strat = r_trade['strategy_name']
    candidates = paper_df[
        (paper_df['strategy_name'] == strat) &
        (paper_df['side'] == r_trade['side']) &
        (abs(pd.to_datetime(paper_df['entry_time']).apply(lambda x: x.timestamp() * 1000.0) - r_time) < 15000)
    ]
    if len(candidates) == 0:
        unmatched_replay.append(r_trade)

print(f"\nReplay trades with NO paper match ({len(unmatched_replay)}):")
for r in unmatched_replay:
    print(f"  [REPLAY ONLY] {r['strategy_name']:<20} | {r['side']} | Entry: {r['entry_time']} @ ${r['entry_price']} | Exit: {r['exit_time']} ({r['exit_reason']}) | Net: ${r['net_pnl_usd']:.2f}")

# Compare matched trades
print(f"\nDifferences among {len(matched)} matched trades:")
differing_exits = 0
for p, r in matched:
    net_diff = r['net_pnl_usd'] - p['net_pnl_usd']
    if abs(net_diff) > 0.05 or p['exit_reason'] != r['exit_reason']:
        differing_exits += 1
        print(f"  {p['trade_id']} ({p['strategy_name']}): Paper={p['exit_reason']} (${p['net_pnl_usd']:.2f}) vs Replay={r['exit_reason']} (${r['net_pnl_usd']:.2f}) | Diff=${net_diff:+.2f}")
print(f"Total matched trades with divergent exits/pnl: {differing_exits}")
