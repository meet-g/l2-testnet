import pandas as pd
df = pd.read_csv('audits/session_20261001_005652/all_trades.csv')
for s in ['Convexity_Cascade', 'Hedged_Convexity', 'Momentum_Expansion']:
    sdf = df[(df['strategy_name'] == s) & (df['exit_reason'] == 'SIGNAL_REVERSAL')]
    g_neg = sdf[sdf['gross_pnl_usd'] < 0]
    g_pos = sdf[sdf['gross_pnl_usd'] > 0]
    print(f"=== {s} SIGNAL_REVERSAL ===")
    print(f"Loss count: {len(g_neg)}, Gross: ${g_neg['gross_pnl_usd'].sum():.2f}, Fees: ${g_neg['total_fees_usd'].sum():.2f}, Net: ${g_neg['net_pnl_usd'].sum():.2f}")
    print(f"Win count: {len(g_pos)}, Gross: ${g_pos['gross_pnl_usd'].sum():.2f}, Fees: ${g_pos['total_fees_usd'].sum():.2f}, Net: ${g_pos['net_pnl_usd'].sum():.2f}")
    print(f"Win count Net > 0: {(g_pos['net_pnl_usd'] > 0).sum()}, Win count Net <= 0: {(g_pos['net_pnl_usd'] <= 0).sum()}")
    print(f"Losing trades Mean Peak MFE: {g_neg['peak_mfe_bps'].mean():.2f} bps, Max Peak MFE: {g_neg['peak_mfe_bps'].max():.2f} bps")
    print(f"Losing trades with Peak MFE >= 3.0 bps (was profitable!): {(g_neg['peak_mfe_bps'] >= 3.0).sum()} of {len(g_neg)} ({(g_neg['peak_mfe_bps'] >= 3.0).mean()*100:.1f}%)")
    print(f"Losing trades with Peak MFE >= 5.0 bps: {(g_neg['peak_mfe_bps'] >= 5.0).sum()} of {len(g_neg)} ({(g_neg['peak_mfe_bps'] >= 5.0).mean()*100:.1f}%)")
