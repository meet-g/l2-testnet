import glob, json, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.test_all_btc_parallel import replay_single_file

data_dir = os.path.join("data", "btc") if os.path.isdir(os.path.join("data", "btc")) else "data"
files_oct3 = sorted(glob.glob(os.path.join(data_dir, "hl_btc_l2_20261003_*.jsonl")))
print(f"Testing {len(files_oct3)} Oct 3 files...")

reasons = {}
for f in files_oct3:
    res = replay_single_file(f)
    for t in res.get("all_trades", []):
        r = t["exit_reason"]
        reasons.setdefault(r, []).append(t)

print("\n--- EXIT REASONS FOR OCT 3 ONLY ---")
for r, tlist in sorted(reasons.items(), key=lambda x: sum(t['net_pnl'] for t in x[1])):
    net = sum(t["net_pnl"] for t in tlist)
    gross = sum(t["gross_pnl"] for t in tlist)
    fees = sum(t["fees"] for t in tlist)
    wins = sum(1 for t in tlist if t["net_pnl"] > 0)
    print(f"[{r:<23}] N={len(tlist):<2} | Win: {wins/len(tlist)*100:4.1f}% | Gross: ${gross:+7.2f} | Fees: -${fees:6.2f} | Net: ${net:+7.2f}")
