import json

files = [
    'audits/all_hype_505_baseline.json',
    'audits/all_hype_505_optimized.json',
    'audits/queue_replenishment_505_eval.json',
    'audits/standalone_qr_505_eval.json',
]

for p in files:
    with open(p, 'r', encoding='utf-8') as f:
        d = json.load(f)
    print('FILE:', p)
    print(f"  comb_net: {d.get('comb_net')} | comb_trades: {d.get('comb_trades')} | comb_gross: {d.get('comb_gross')} | comb_fees: {d.get('comb_fees')} | comb_wr: {d.get('comb_wr')}")
    st = d.get('strat_totals', {})
    for k, v in st.items():
        print(f"    {k:22s}: trades={v.get('trades'):4d} | net_pnl={v.get('net_pnl'):8.2f} | gross={v.get('gross_pnl'):8.2f} | fees={v.get('fees'):8.2f} | pf={v.get('profit_factor')}")
    print()
