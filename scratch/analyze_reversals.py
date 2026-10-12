import pandas as pd
import numpy as np

df = pd.read_csv('audits/session_20261001_005652/all_trades.csv')
for s in ['Convexity_Cascade', 'Hedged_Convexity', 'Momentum_Expansion']:
    sdf = df[(df['strategy_name'] == s) & (df['exit_reason'] == 'SIGNAL_REVERSAL')]
    print(f"\n=== {s} SIGNAL_REVERSAL ===")
    print(f"Count: {len(sdf)}")
    print(f"Gross PnL: ${sdf['gross_pnl_usd'].sum():.2f}, Fees: ${sdf['total_fees_usd'].sum():.2f}, Net: ${sdf['net_pnl_usd'].sum():.2f}")
    print(f"Return bps: mean={sdf['return_bps'].mean():.2f}, median={sdf['return_bps'].median():.2f}, min={sdf['return_bps'].min():.2f}, max={sdf['return_bps'].max():.2f}")
    print(f"Holding secs: mean={sdf['holding_secs'].mean():.1f}s, min={sdf['holding_secs'].min():.1f}s, max={sdf['holding_secs'].max():.1f}s")
    print(f"Exit signal: mean={sdf['exit_signal'].mean():.2f}, min={sdf['exit_signal'].min():.2f}, max={sdf['exit_signal'].max():.2f}")
    print(f"Peak MFE: mean={sdf['peak_mfe_bps'].mean():.2f}, Trough MAE: mean={sdf['trough_mae_bps'].mean():.2f}")
    pos_mfe = (sdf['peak_mfe_bps'] >= 7.0).mean() * 100
    print(f"Percentage where Peak MFE was >= 7.0 bps: {pos_mfe:.1f}%")
    pos_gross = (sdf['gross_pnl_usd'] > 0).mean() * 100
    print(f"Percentage of Gross Winners: {pos_gross:.1f}%")
    
    # What was the distribution of gross return in bps?
    gross_bps = (sdf['gross_pnl_usd'] / sdf['notional_usd']) * 10000.0
    print(f"Gross return bps: mean={gross_bps.mean():.2f}, median={gross_bps.median():.2f}")
    print(f"Trades with gross return < 3.0 bps (i.e. cannot cover 3.0 bps fee): {(gross_bps < 3.0).sum()} of {len(sdf)} ({(gross_bps < 3.0).mean()*100:.1f}%)")
