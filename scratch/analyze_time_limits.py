import pandas as pd
df = pd.read_csv('audits/latest_session_all_trades.csv')
tl = df[df['exit_reason'] == 'TIME_LIMIT']
print(f"TIME_LIMIT trades count: {len(tl)}")
print(f"Gross PnL: ${tl['gross_pnl_usd'].sum():.2f}")
print(f"Fees: ${tl['total_fees_usd'].sum():.2f}")
print(f"Net PnL: ${tl['net_pnl_usd'].sum():.2f}")
print(f"Gross return bps: mean={tl['return_bps'].mean():.2f}, median={tl['return_bps'].median():.2f}")
print(f"Peak MFE: mean={tl['peak_mfe_bps'].mean():.2f}, median={tl['peak_mfe_bps'].median():.2f}, max={tl['peak_mfe_bps'].max():.2f}")
print(f"Trough MAE: mean={tl['trough_mae_bps'].mean():.2f}, median={tl['trough_mae_bps'].median():.2f}, min={tl['trough_mae_bps'].min():.2f}")
print(f"MFE >= 3.0 bps: {(tl['peak_mfe_bps'] >= 3.0).sum()} of {len(tl)}")
print(f"MFE >= 4.0 bps: {(tl['peak_mfe_bps'] >= 4.0).sum()} of {len(tl)}")
print(f"MFE >= 4.5 bps: {(tl['peak_mfe_bps'] >= 4.5).sum()} of {len(tl)}")
