import re
from collections import defaultdict

log_path = r"C:\Users\M\.gemini\antigravity-cli\brain\1d967696-532a-45b0-9d40-fc939435a1ad\.system_generated\tasks\task-379.log"
with open(log_path, "r", encoding="utf-8") as f:
    log = f.read()

# Pattern matching: ✓ hl_btc_l2_20260927_192035.jsonl  ( 0.1 MB in  0.2s) | Trd:  2 | \nNet: $ -7.79
pattern = re.compile(r"hl_btc_l2_(\d{8})_.*?\|\s*Trd:\s*(\d+)\s*\|\s*\n?\s*Net:\s*\$\s*([+-]?\d+\.\d+)")
day_pnl = defaultdict(float)
day_trd = defaultdict(int)

matches = pattern.findall(log)
print(f"Total matching session entries parsed: {len(matches)}")

for d, trd, pnl in matches:
    day_pnl[d] += float(pnl)
    day_trd[d] += int(trd)

print("\n=== DAILY PERFORMANCE BREAKDOWN ACROSS 101 BTC SESSIONS ===")
for d in sorted(day_pnl.keys()):
    print(f"Date {d[:4]}-{d[4:6]}-{d[6:]}: {day_trd[d]:3d} Trades | Net PnL: ${day_pnl[d]:+7.2f}")
