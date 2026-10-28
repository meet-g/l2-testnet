import json

with open('audits/all_hype_505_optimized.json', 'r', encoding='utf-8') as f:
    base = json.load(f)
with open('audits/queue_replenishment_505_eval.json', 'r', encoding='utf-8') as f:
    comb = json.load(f)

base_files = {r['filename']: r for r in base['results']}
comb_files = {r['filename']: r for r in comb['results']}

common_files = set(base_files.keys()) & set(comb_files.keys())
print(f"Common files between base and comb: {len(common_files)}")

strat_mismatches = {s: [] for s in ['Hedged_Convexity', 'Convexity_Cascade', 'Momentum_Expansion']}

for fn in common_files:
    rb = base_files[fn]['strategies']
    rc = comb_files[fn]['strategies']
    for s in strat_mismatches:
        sb = rb[s]
        sc = rc[s]
        if sb['trades'] != sc['trades'] or abs(sb['net_pnl'] - sc['net_pnl']) > 1e-4:
            strat_mismatches[s].append({
                'filename': fn,
                'base_trades': sb['trades'],
                'comb_trades': sc['trades'],
                'base_net': sb['net_pnl'],
                'comb_net': sc['net_pnl'],
                'delta_net': sc['net_pnl'] - sb['net_pnl'],
            })

for s, diffs in strat_mismatches.items():
    print(f"\nStrategy {s}: {len(diffs)} files with differences out of {len(common_files)}")
    for d in diffs[:10]:
        print(f"  {d['filename']}: tr_base={d['base_trades']} tr_comb={d['comb_trades']} | net_base={d['base_net']:.2f} net_comb={d['comb_net']:.2f} (delta={d['delta_net']:.2f})")
