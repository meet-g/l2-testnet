import json

with open('audits/session_20261111_160439_914_d4e9/session_manifest.json') as f:
    live = json.load(f)

with open('audits/session_20261111_165314_402_43df/session_manifest.json') as f:
    replay = json.load(f)

print('=== OVERALL SESSION RECONCILIATION ===')
print(f"{'Metric':<25} | {'Live Session':<18} | {'Replay Session':<18} | {'Delta':<12}")
print('-' * 80)

metrics = [
    ('total_trades', 'Total Trades', '{:.0f}'),
    ('winning_trades', 'Winning Trades', '{:.0f}'),
    ('losing_trades', 'Losing Trades', '{:.0f}'),
    ('win_rate_pct', 'Win Rate (%)', '{:.1f}%'),
    ('gross_pnl_usd', 'Gross PnL ($)', '${:+.2f}'),
    ('total_fees_usd', 'Total Fees ($)', '${:.2f}'),
    ('net_pnl_usd', 'Net PnL ($)', '${:+.2f}'),
    ('profit_factor', 'Profit Factor', '{:.2f}'),
    ('total_volume_btc', 'Volume (SKHX)', '{:.2f}'),
]

for key, label, fmt in metrics:
    v_l = live['session_summary'].get(key, 0)
    v_r = replay['session_summary'].get(key, 0)
    delta = v_r - v_l
    str_l = fmt.format(v_l)
    str_r = fmt.format(v_r)
    str_d = f"{delta:+.2f}"
    print(f"{label:<25} | {str_l:<18} | {str_r:<18} | {str_d:<12}")

print('\n=== STRATEGY-BY-STRATEGY BREAKDOWN ===')
header = f"{'Strategy':<24} | {'Live Trd':<8} {'Live WR':<8} {'Live Net$':<11} | {'Rep Trd':<8} {'Rep WR':<8} {'Rep Net$':<11} | {'P&L Direction':<14}"
print(header)
print('-' * len(header))

all_strats = sorted(set(list(live['strategies'].keys()) + list(replay['strategies'].keys())))
for s in all_strats:
    s_live = live['strategies'].get(s, {})
    s_rep = replay['strategies'].get(s, {})
    
    t_l = s_live.get('trades', 0)
    wr_l = s_live.get('win_rate_pct', 0.0)
    net_l = s_live.get('net_pnl_usd', 0.0)
    
    t_r = s_rep.get('trades', 0)
    wr_r = s_rep.get('win_rate_pct', 0.0)
    net_r = s_rep.get('net_pnl_usd', 0.0)
    
    if net_l > 0 and net_r > 0:
        match = "MATCH (Profit)"
    elif net_l < 0 and net_r < 0:
        match = "MATCH (Loss)"
    elif net_l == 0 and net_r == 0:
        match = "MATCH (Flat)"
    else:
        match = "DIVERGED"
        
    print(f"{s:<24} | {t_l:<8} {wr_l:<7.1f}% ${net_l:<9.2f} | {t_r:<8} {wr_r:<7.1f}% ${net_r:<9.2f} | {match:<14}")
