import json
import pandas as pd

trades = []
with open('audits/session_20261001_005652/trades_audit.jsonl', 'r') as f:
    for line in f:
        if line.strip():
            trades.append(json.loads(line))

df = pd.DataFrame(trades)
print(f"Loaded {len(df)} audit trade events")
print(df.columns.tolist()[:15])
