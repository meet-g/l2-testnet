import glob
import json
import os

data_dir = os.path.join("data", "btc") if os.path.isdir(os.path.join("data", "btc")) else "data"
files = sorted(glob.glob(os.path.join(data_dir, "hl_btc_l2_*.jsonl")))
records = []

for f in files:
    sz = os.path.getsize(f) / (1024 * 1024)
    if sz == 0:
        continue
    t0, t1 = None, None
    with open(f, "r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            if t0 is None:
                t0 = json.loads(line).get("recv_ts", 0)
            t1 = json.loads(line).get("recv_ts", 0)
    dur = (t1 - t0) / 60000.0 if (t0 and t1) else 0.0
    records.append((f, sz, dur))

print(f"Total BTC sessions analyzed: {len(records)}")
for cutoff in [15, 30, 45, 50, 55]:
    subset = [r for r in records if r[2] >= cutoff]
    mb = sum(r[1] for r in subset)
    print(f"  Duration >= {cutoff:2d} mins: {len(subset):2d} files | {mb:5.1f} MB")

print("\nFiles with Duration < 30 mins:")
short_files = [r for r in records if r[2] < 30]
for r in short_files:
    print(f"  {os.path.basename(r[0]):<35} Size: {r[1]:4.2f} MB | Duration: {r[2]:4.1f} mins")
