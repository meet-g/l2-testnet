import pandas as pd
df = pd.read_csv('audits/latest_session_all_trades.csv')
tl = df[df['exit_reason'] == 'TIME_LIMIT']
print(f"Total TIME_LIMIT trades: {len(tl)}")
for s in tl['strategy_name'].unique():
    stl = tl[tl['strategy_name'] == s]
    print(f"=== {s} TIME_LIMIT (n={len(stl)}) ===")
    print(stl[['trade_id', 'entry_time', 'side', 'entry_price', 'entry_signal', 'peak_mfe_bps', 'trough_mae_bps']].head(10).to_string())
