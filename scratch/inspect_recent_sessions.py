import os
import pandas as pd
import json

def inspect_session(session_path):
    s_id = os.path.basename(session_path)
    print("=" * 80)
    print(f"ANALYSIS OF SESSION: {s_id}")
    print("=" * 80)
    
    lo_p = os.path.join(session_path, 'live_orders.csv')
    ef_p = os.path.join(session_path, 'live_exchange_fills.csv')
    at_p = os.path.join(session_path, 'all_trades.csv')
    
    df_lo = pd.read_csv(lo_p) if os.path.exists(lo_p) else pd.DataFrame()
    df_ef = pd.read_csv(ef_p) if os.path.exists(ef_p) else pd.DataFrame()
    df_at = pd.read_csv(at_p) if os.path.exists(at_p) else pd.DataFrame()
    
    print("\n--- 1. Live Orders Event Types ---")
    if not df_lo.empty and 'event_type' in df_lo.columns:
        print(df_lo['event_type'].value_counts())
        if 'status' in df_lo.columns:
            print("\nStatuses:")
            print(df_lo['status'].value_counts())
        
        # Check rejections or errors
        rej = df_lo[df_lo['event_type'].isin(['REJECTED', 'ERROR']) | (df_lo['status'] == 'rejected')]
        if not rej.empty:
            print(f"\nRejections/Errors ({len(rej)}):")
            for _, r in rej.head(10).iterrows():
                print(f"  {r.get('timestamp')} | {r.get('event_type')} | Side: {r.get('side')} | Sz: {r.get('size_btc')} | Px: {r.get('price')} | Err: {r.get('error')}")

    print("\n--- 2. Live Exchange Fills Breakdown ---")
    if not df_ef.empty:
        print(f"Total Fills: {len(df_ef)}")
        print(df_ef['dir'].value_counts())
        print("\nCrossed (Liquidity Type):")
        print(df_ef['crossed'].value_counts())
        
        makers = df_ef[df_ef['crossed'] == 'MAKER']
        takers = df_ef[df_ef['crossed'] == 'TAKER']
        
        print(f"\nMaker fills: {len(makers)} | Total Fees: ${makers['fee_usd'].sum():.4f} | Gross PnL: ${makers['closed_pnl_usd'].sum():.4f}")
        print(f"Taker fills: {len(takers)} | Total Fees: ${takers['fee_usd'].sum():.4f} | Gross PnL: ${takers['closed_pnl_usd'].sum():.4f}")
        
        print("\nExits breakdown:")
        exits = df_ef[df_ef['dir'].str.startswith('Close', na=False)]
        print(f"Total Closing Fills: {len(exits)}")
        for crossed, grp in exits.groupby('crossed'):
            print(f"  {crossed}: {len(grp)} fills | PnL: ${grp['closed_pnl_usd'].sum():.4f} | Fee: ${grp['fee_usd'].sum():.4f} | Net: ${grp['closed_pnl_usd'].sum() - grp['fee_usd'].sum():.4f}")

    print("\n--- 3. Bot Simulated Trades in all_trades.csv ---")
    if not df_at.empty:
        print(f"Total Sim Trades: {len(df_at)}")
        print(f"Gross PnL: ${df_at['gross_pnl_usd'].sum():.4f}")
        print(f"Fees:      ${df_at['total_fees_usd'].sum():.4f}")
        print(f"Net PnL:   ${df_at['net_pnl_usd'].sum():.4f}")
        print("\nExit Reasons:")
        print(df_at['exit_reason'].value_counts())
        print("\nExecution Types in Sim:")
        print(df_at['execution_type'].value_counts())

inspect_session('audits/session_20261102_025622_340_ac8d')
inspect_session('audits/session_20261102_020540_176_937a')
