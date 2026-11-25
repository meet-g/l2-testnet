"""Live CLI tool to compare order capture between Fast and Normal Hyperliquid WebSockets.

Usage:
    python scripts/compare_dual_websocket.py --interval 10 --coin BTC
    python scripts/compare_dual_websocket.py --interval 15 --coin ETH
    python scripts/compare_dual_websocket.py --interval 20 --coin xyz:SKHX --testnet
"""

import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import AppConfig
from core.dual_ws_comparator import DualWebSocketOrderComparator


def parse_args():
    parser = argparse.ArgumentParser(
        description="Empirical Dual-WebSocket Order Capture Comparison on Hyperliquid"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Evaluation interval in seconds to capture orders (default: 10.0s)",
    )
    parser.add_argument(
        "--coin",
        type=str,
        default="BTC",
        help="Asset symbol to track (e.g., BTC, ETH, SOL, xyz:SKHX)",
    )
    parser.add_argument(
        "--testnet",
        action="store_true",
        help="Use Hyperliquid Testnet instead of Mainnet",
    )
    parser.add_argument(
        "--ws-url",
        type=str,
        default=None,
        help="Override WebSocket endpoint URL directly",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=5,
        help="Number of sample missed/captured orders to display (default: 5)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    cfg = AppConfig()

    ws_url = args.ws_url
    if not ws_url:
        if args.testnet:
            ws_url = cfg.hyperliquid.TESTNET_WS_URL
        else:
            ws_url = cfg.hyperliquid.ws_url

    print("=" * 82)
    print("HYPERLIQUID DUAL-WEBSOCKET ORDER CAPTURE COMPARISON")
    print("=" * 82)
    print(f"Target Coin         : {args.coin}")
    print(f"Sampling Interval   : {args.interval:.1f} seconds")
    print(f"WebSocket Endpoint  : {ws_url}")
    print("Connecting concurrent streams: Normal (20 levels) & Fast (top 5 levels)...")
    print("Listening for incoming l2Book ticks...")

    comparator = DualWebSocketOrderComparator(coin=args.coin)
    report = await comparator.run_live(interval_secs=args.interval, ws_url=ws_url)

    print("\n" + report.summary())

    print("\n[DETAILED ORDER CAPTURE BREAKDOWN]")
    print("-" * 82)
    print(f"1. ORDERS SEEN BY FAST BUT MISSED BY NORMAL: {len(report.fast_only_orders)}")
    if report.fast_only_prices:
        print(f"   ► Brand New Price Levels completely missed by Normal ({len(report.fast_only_prices)} levels):")
        for side, px in report.fast_only_prices[: args.sample_limit]:
            print(f"       • {side.upper()} @ {px:.4f}")
        if len(report.fast_only_prices) > args.sample_limit:
            print(f"       ... and {len(report.fast_only_prices) - args.sample_limit} more price levels")

    if report.fast_only_intermediate_updates:
        print(f"   ► Intermediate Queue States missed by Normal ({len(report.fast_only_intermediate_updates)} states):")
        for order in report.fast_only_intermediate_updates[: args.sample_limit]:
            print(f"       • {order}")
        if len(report.fast_only_intermediate_updates) > args.sample_limit:
            print(f"       ... and {len(report.fast_only_intermediate_updates) - args.sample_limit} more queue states")

    print(f"\n2. ORDERS SEEN BY NORMAL BUT MISSED BY FAST: {len(report.normal_only_orders)}")
    print(f"   ► Deep Resting Liquidity beyond Top 5 ({len(report.normal_only_deep_orders)} levels):")
    for order in report.normal_only_deep_orders[: args.sample_limit]:
        depth = comparator.normal_order_depth.get(order, 0) + 1
        print(f"       • Depth Level {depth:02d}: {order}")
    if len(report.normal_only_deep_orders) > args.sample_limit:
        print(f"       ... and {len(report.normal_only_deep_orders) - args.sample_limit} more deep levels")

    print("\n[VERDICT]")
    print("-" * 82)
    if report.fast_only_orders:
        pct_fast_unique = (len(report.fast_only_orders) / max(report.unique_orders_fast, 1)) * 100.0
        print(
            f"✓ CONFIRMED: The fast WebSocket captured {len(report.fast_only_orders)} resting order states "
            f"({pct_fast_unique:.1f}% of all fast orders) that the normal WebSocket NEVER captured "
            f"within this {args.interval:.1f}s interval."
        )
    else:
        print(
            f"Notice: In this quiet market interval, fast did not detect unshared orders. Try a longer interval or more volatile asset."
        )

    if report.avg_lead_time_ms > 0:
        print(
            f"✓ LATENCY ADVANTAGE: The fast WebSocket observed common price changes "
            f"an average of {report.avg_lead_time_ms:.1f}ms (up to {report.max_lead_time_ms:.1f}ms) BEFORE the normal WebSocket."
        )
    print("=" * 82)


if __name__ == "__main__":
    asyncio.run(main())
