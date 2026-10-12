import pandas as pd
df = pd.read_csv('audits/latest_session_all_trades.csv')
for s in df['strategy_name'].unique():
    sdf = df[df['strategy_name'] == s]
    winners = sdf[sdf['net_pnl_usd'] > 0]
    losers = sdf[sdf['net_pnl_usd'] <= 0]
    print(f"\n=== {s} ===")
    print(f"Total: {len(sdf)}, Net PnL: ${sdf['net_pnl_usd'].sum():.2f}")
    print(f"Winners: {len(winners)}, Net Win: ${winners['net_pnl_usd'].sum():.2f}, Avg Win: ${winners['net_pnl_usd'].mean():.2f}")
    print(f"Losers: {len(losers)}, Net Loss: ${losers['net_pnl_usd'].sum():.2f}, Avg Loss: ${losers['net_pnl_usd'].mean():.2f}")
    print("Top 5 Winners:")
    print(winners[['trade_id', 'side', 'holding_secs', 'gross_pnl_usd', 'net_pnl_usd', 'return_bps', 'exit_reason']].head())
    print("Top 5 Losers:")
    print(losers[['trade_id', 'side', 'holding_secs', 'gross_pnl_usd', 'net_pnl_usd', 'return_bps', 'exit_reason']].head())
