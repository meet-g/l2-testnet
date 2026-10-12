import pandas as pd
df = pd.read_csv('audits/latest_session_all_trades.csv')
t64 = df[df['trade_id'].isin(['HC-0065', 'HC-0066', 'HC-0077'])]
print(t64[['trade_id', 'entry_time', 'side', 'entry_price', 'entry_signal', 'exit_reason']].to_string())
