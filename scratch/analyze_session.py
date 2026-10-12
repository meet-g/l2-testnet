import pandas as pd
import numpy as np

df = pd.read_csv('audits/session_20261001_005652/all_trades.csv')
print(f"Total trades: {len(df)}")
for strat in df['strategy_name'].unique():
    sdf = df[df['strategy_name'] == strat]
    print(f"\n==========================================")
    print(f"=== Strategy: {strat} ===")
    print(f"==========================================")
    print(f"Trades: {len(sdf)}")
    print(f"Gross PnL: ${sdf['gross_pnl_usd'].sum():.2f}")
    print(f"Total Fees: ${sdf['total_fees_usd'].sum():.2f}")
    print(f"Net PnL: ${sdf['net_pnl_usd'].sum():.2f}")
    print(f"Win rate (gross > 0): {(sdf['gross_pnl_usd'] > 0).mean()*100:.1f}%")
    print(f"Win rate (net > 0): {(sdf['net_pnl_usd'] > 0).mean()*100:.1f}%")
    print(f"Avg trade gross: ${sdf['gross_pnl_usd'].mean():.2f}")
    print(f"Avg trade net: ${sdf['net_pnl_usd'].mean():.2f}")
    print(f"Avg fee per trade: ${sdf['total_fees_usd'].mean():.2f}")
    
    print("\nBreakdown by Exit Reason:")
    grouped = sdf.groupby('exit_reason').agg(
        count=('trade_id', 'count'),
        gross=('gross_pnl_usd', 'sum'),
        fees=('total_fees_usd', 'sum'),
        net=('net_pnl_usd', 'sum'),
        avg_gross=('gross_pnl_usd', 'mean'),
        avg_net=('net_pnl_usd', 'mean'),
        avg_hold=('holding_secs', 'mean'),
        gross_winrate=('gross_pnl_usd', lambda x: (x > 0).mean() * 100),
        net_winrate=('net_pnl_usd', lambda x: (x > 0).mean() * 100)
    )
    print(grouped.to_string())

    print("\nSignal conviction analysis:")
    print(f"Entry signal abs mean: {sdf['entry_signal'].abs().mean():.3f}, min: {sdf['entry_signal'].abs().min():.3f}, max: {sdf['entry_signal'].abs().max():.3f}")
    print(f"Exit signal abs mean: {sdf['exit_signal'].abs().mean():.3f}")
    
    print("\nPeak vs Trough Unrealized bps (MFE / MAE):")
    print(f"Mean peak MFE bps: {sdf['peak_mfe_bps'].mean():.2f} bps")
    print(f"Mean trough MAE bps: {sdf['trough_mae_bps'].mean():.2f} bps")
    print(f"Max peak MFE bps: {sdf['peak_mfe_bps'].max():.2f} bps")
