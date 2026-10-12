import pandas as pd
df = pd.read_csv('audits/latest_session_all_trades.csv')
tl = df[df['exit_reason'] == 'TIME_LIMIT']
print(f"TIME_LIMIT count: {len(tl)}")
print(f"Holding secs: mean={tl['holding_secs'].mean():.1f}s, min={tl['holding_secs'].min():.1f}s, max={tl['holding_secs'].max():.1f}s")
print(f"Gross PnL: mean=${tl['gross_pnl_usd'].mean():.2f}, sum=${tl['gross_pnl_usd'].sum():.2f}")
print(f"Peak MFE: mean={tl['peak_mfe_bps'].mean():.2f} bps, median={tl['peak_mfe_bps'].median():.2f} bps, max={tl['peak_mfe_bps'].max():.2f} bps")
print(f"Trough MAE: mean={tl['trough_mae_bps'].mean():.2f} bps, median={tl['trough_mae_bps'].median():.2f} bps, min={tl['trough_mae_bps'].min():.2f} bps")
print(f"Gross return bps: mean={tl['return_bps'].mean():.2f} bps")
print("\nSample 10 TIME_LIMIT trades:")
print(tl[['trade_id', 'strategy_name', 'side', 'holding_secs', 'gross_pnl_usd', 'net_pnl_usd', 'peak_mfe_bps', 'trough_mae_bps']].head(10).to_string())
