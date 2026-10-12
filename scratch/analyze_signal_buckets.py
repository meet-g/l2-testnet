import pandas as pd
import numpy as np

df = pd.read_csv('audits/session_20261001_005652/all_trades.csv')
for s in ['Convexity_Cascade', 'Hedged_Convexity', 'Momentum_Expansion']:
    sdf = df[df['strategy_name'] == s].copy()
    sdf['abs_entry_signal'] = sdf['entry_signal'].abs()
    
    # Bin by entry signal
    bins = [0.50, 0.60, 0.70, 0.80, 0.90, 1.01]
    labels = ['0.50-0.60', '0.60-0.70', '0.70-0.80', '0.80-0.90', '0.90-1.00']
    sdf['signal_bucket'] = pd.cut(sdf['abs_entry_signal'], bins=bins, labels=labels, right=False)
    
    print(f"\n==========================================")
    print(f"=== {s} Performance by Entry Signal Score ===")
    print(f"==========================================")
    grouped = sdf.groupby('signal_bucket', observed=False).agg(
        trades=('trade_id', 'count'),
        gross=('gross_pnl_usd', 'sum'),
        fees=('total_fees_usd', 'sum'),
        net=('net_pnl_usd', 'sum'),
        avg_gross=('gross_pnl_usd', 'mean'),
        avg_net=('net_pnl_usd', 'mean'),
        win_rate_gross=('gross_pnl_usd', lambda x: (x > 0).mean() * 100),
        win_rate_net=('net_pnl_usd', lambda x: (x > 0).mean() * 100),
    )
    print(grouped.to_string())
