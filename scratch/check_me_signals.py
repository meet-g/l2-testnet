import pandas as pd
df = pd.read_csv('audits/latest_session_all_trades.csv')
me = df[df['strategy_name'] == 'Momentum_Expansion']
print(me[['trade_id', 'entry_time', 'side', 'entry_signal']].to_string())
