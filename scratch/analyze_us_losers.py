import pandas as pd
df = pd.read_csv('audits/latest_session_all_trades.csv')
losers = df[df['exit_reason'].isin(['STOP_LOSS', 'DEFENSIVE_MAKER_HEDGE'])]
print(f"Total Stop Loss / Hedge trades: {len(losers)}")
print(f"By strategy:\n{losers['strategy_name'].value_counts()}")
print(f"By side:\n{losers['side'].value_counts()}")
print(f"Holding secs: mean={losers['holding_secs'].mean():.1f}s, median={losers['holding_secs'].median():.1f}s")
print(f"Peak MFE: mean={losers['peak_mfe_bps'].mean():.2f} bps, max={losers['peak_mfe_bps'].max():.2f} bps")
print(f"Trades with peak MFE >= 2.0 bps: {(losers['peak_mfe_bps'] >= 2.0).sum()} of {len(losers)}")
print(f"Trades with peak MFE >= 3.0 bps: {(losers['peak_mfe_bps'] >= 3.0).sum()} of {len(losers)}")
print(f"Trades with peak MFE >= 4.0 bps: {(losers['peak_mfe_bps'] >= 4.0).sum()} of {len(losers)}")

print("\nSample 10 stop loss trades:")
print(losers[['trade_id', 'strategy_name', 'side', 'entry_time', 'entry_price', 'exit_price', 'holding_secs', 'return_bps', 'exit_reason']].head(10).to_string())
