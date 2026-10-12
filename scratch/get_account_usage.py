import datetime
import sys
sys.path.insert(0, ".")
from config import AppConfig
from hyperliquid.info import Info
from hyperliquid.utils import constants


def main():
    cfg = AppConfig()
    addr = cfg.account.account_address
    base_url = constants.TESTNET_API_URL if cfg.hyperliquid.use_testnet else constants.MAINNET_API_URL
    info = Info(base_url, skip_ws=True)

    print("=" * 60)
    print("HYPERLIQUID ACCOUNT ALL-TIME USAGE & ACTIVITY")
    print("=" * 60)
    print(f"Master Account: {addr}")
    print(f"Network:        {cfg.hyperliquid.network_name}")

    user_state = info.user_state(addr)
    margin = user_state.get("marginSummary", {})
    acct_val = float(margin.get("accountValue", 0.0))
    avail_margin = float(margin.get("totalRawUsd", 0.0))
    print(f"Account Value:  ${acct_val:,.2f}")
    print(f"Available Cash: ${avail_margin:,.2f}")

    fills = info.user_fills(addr)
    print(f"\nTotal All-Time Fills: {len(fills)}")

    tot_vol = 0.0
    tot_fee = 0.0
    tot_pnl = 0.0
    by_coin = {}
    by_dir = {}

    first_time = None
    last_time = None

    for f in fills:
        px = float(f.get("px", 0))
        sz = float(f.get("sz", 0))
        fee = float(f.get("fee", 0))
        pnl = float(f.get("closedPnl", 0))
        notional = px * sz
        coin = f.get("coin", "UNKNOWN")
        d = f.get("dir", "UNKNOWN")
        t = f.get("time", 0)

        tot_vol += notional
        tot_fee += fee
        tot_pnl += pnl

        if first_time is None or t < first_time:
            first_time = t
        if last_time is None or t > last_time:
            last_time = t

        by_coin[coin] = by_coin.get(coin, 0.0) + notional
        by_dir[d] = by_dir.get(d, 0) + 1

    print(f"Total Traded Volume: ${tot_vol:,.2f}")
    print(f"Total Fees Paid:     ${tot_fee:,.4f}")
    print(f"Total Closed PnL:    ${tot_pnl:,.2f}")

    if first_time and last_time:
        t_start = datetime.datetime.fromtimestamp(first_time / 1000).strftime('%Y-%m-%d %H:%M:%S')
        t_end = datetime.datetime.fromtimestamp(last_time / 1000).strftime('%Y-%m-%d %H:%M:%S')
        print(f"Activity Window:     {t_start} to {t_end}")

    print("\nVolume by Asset:")
    for c, v in sorted(by_coin.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {c:6s}: ${v:,.2f}")

    print("\nTrade Actions:")
    for d, c in sorted(by_dir.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {d:15s}: {c} fills")


if __name__ == "__main__":
    main()
