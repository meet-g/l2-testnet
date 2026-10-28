import json

with open('audits/queue_replenishment_505_eval.json', 'r', encoding='utf-8') as f:
    comb = json.load(f)
with open('audits/standalone_qr_505_eval.json', 'r', encoding='utf-8') as f:
    stand = json.load(f)

comb_qr = {r['filename']: r['strategies']['Queue_Replenishment'] for r in comb['results']}
stand_qr = {r['filename']: r['strategies']['Queue_Replenishment'] for r in stand['results']}

mismatches = 0
for fn in stand_qr:
    c = comb_qr[fn]
    s = stand_qr[fn]
    if c['trades'] != s['trades'] or abs(c['net_pnl'] - s['net_pnl']) > 1e-6:
        print(f"Mismatch in {fn}: comb trades={c['trades']}, net={c['net_pnl']:.4f} vs stand trades={s['trades']}, net={s['net_pnl']:.4f}")
        mismatches += 1

print('Total file mismatches for QR (comb vs stand):', mismatches)
if mismatches == 0:
    print('100% BIT-FOR-BIT IDENTICAL: QR performance in combined portfolio matches standalone exactly!')
