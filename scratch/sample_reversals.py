import pandas as pd
df = pd.read_csv('audits/session_20261001_005652/all_trades.csv')
sample = df[(df['strategy_name'] == 'Convexity_Cascade') & (df['exit_reason'] == 'SIGNAL_REVERSAL') & (df['peak_mfe_bps'] >= 7.0)]
print(sample[['trade_id', 'side', 'entry_price', 'exit_price', 'holding_secs', 'gross_pnl_usd', 'net_pnl_usd', 'peak_mfe_bps', 'return_bps']].head(10))
