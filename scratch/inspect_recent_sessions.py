import os
import json

for sid in ['session_20261003_211704', 'session_20261003_222606']:
    print('=' * 80)
    print(f'SESSION: {sid}')
    mpath = f'audits/{sid}/session_manifest.json'
    if os.path.exists(mpath):
        with open(mpath) as f:
            m = json.load(f)
        print('Coin:', m.get('coin'))
        dur_h = m.get('duration_secs', 0) / 3600.0
        print(f'Duration: {dur_h:.2f} hrs')
        print('Enabled Strategies:', m.get('enabled_strategies'))
        summary = m.get('session_summary', {})
        print('Summary:', summary)
        print('\nStrategy breakdown:')
        for strat, stats in m.get('strategies', {}).items():
            print(f"  {strat}: trades={stats.get('trades')} win_rate={stats.get('win_rate_pct')}% net_pnl=${stats.get('net_pnl_usd'):.2f}")
    
    tpath = f'audits/{sid}/all_trades.csv'
    if os.path.exists(tpath):
        with open(tpath) as f:
            print('\nTRADES CSV:')
            print(f.read().strip())
