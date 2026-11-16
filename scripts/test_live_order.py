"""Instant Live Test Order Script for Hyperliquid Mainnet / Testnet.

Executes a small (~$15 notional) round-trip test trade on xyz:SKHX:
1. Places a Market BUY order (0.02 shares, crossing book with 20 bps slippage).
2. Verifies on-chain fill and records execution wire latency.
3. Pauses 2 seconds.
4. Places a Market SELL order (Reduce-Only) to close the position.
5. Verifies account returns to completely flat (+0.0000).
"""

import os
import sys
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import AppConfig
from engine.live_executor import LiveOrderExecutor

def run_test_order(coin: str = "xyz:SKHX", shares: float = 0.02, slippage: float = 0.002):
    cfg = AppConfig()
    cfg.market.configure_for_coin(coin)
    
    print("\n" + "=" * 65)
    print(f" HYPERLIQUID LIVE TEST TRADE: {coin}")
    print(f" Master Wallet: {cfg.account.account_address[:10]}...")
    print(f" Network:       {'TESTNET' if cfg.hyperliquid.use_testnet else 'MAINNET'}")
    print("=" * 65 + "\n")
    
    executor = LiveOrderExecutor(
        config=cfg,
        default_order_size_btc=shares,
        non_blocking=False,
        force_market_orders=True,
        market_slippage_pct=slippage,
    )
    
    if not executor.is_initialized or not executor.exchange:
        print("[ERROR] Live executor failed to initialize. Please check your .env credentials.")
        sys.exit(1)
        
    def get_market_prices():
        l2 = executor.info.l2_snapshot(coin) if executor.info else {}
        bids = l2.get("levels", [[]])[0] if l2 else []
        asks = l2.get("levels", [[], []])[1] if l2 else []
        bid = float(bids[0]["px"]) if bids else 0.0
        ask = float(asks[0]["px"]) if asks else 0.0
        executor.last_best_bid = bid
        executor.last_best_ask = ask
        return bid, ask

    best_bid, best_ask = get_market_prices()
    mid_px = (best_bid + best_ask) / 2.0 if (best_bid and best_ask) else 830.0
    notional = shares * mid_px
    print(f"Market Snapshot: Best Bid = ${best_bid:.2f} | Best Ask = ${best_ask:.2f} | Mid = ${mid_px:.2f}")
    print(f"Test Order Size: {shares} {coin} (~${notional:.2f} notional)\n")

    # 1. PLACE MARKET BUY
    print(f"[STEP 1/2] Sending Live MARKET BUY for {shares} {coin}...")
    t_start = time.perf_counter()
    get_market_prices()
    buy_res = executor.place_market_order(
        is_buy=True,
        size_btc=shares,
        slippage_pct=slippage,
        strategy_name="LiveTestOrder",
        non_blocking=False,
    )
    wire_buy_ms = (time.perf_counter() - t_start) * 1000.0
    
    time.sleep(2.0)
    executor.sync_state(force=True)
    open_pos = executor.cached_position
    
    if abs(open_pos) < 1e-6:
        print(f"[FAILED] Buy order was not filled. Response: {buy_res}")
        return
        
    print(f"\n>>> BUY FILLED! Current Position: {open_pos:+.4f} {coin} @ ${executor.entry_price:.2f} (Latency: {wire_buy_ms:.1f}ms)\n")

    # 2. PLACE MARKET SELL TO CLOSE
    print(f"[STEP 2/2] Sending Live MARKET SELL (Reduce-Only) to close {abs(open_pos):.4f} {coin}...")
    t_start = time.perf_counter()
    get_market_prices()
    sell_res = executor.place_market_order(
        is_buy=False,
        size_btc=abs(open_pos),
        slippage_pct=slippage,
        is_exit=True,
        reduce_only=True,
        strategy_name="LiveTestOrder",
        exit_reason="TEST_CLOSE",
        non_blocking=False,
    )
    wire_sell_ms = (time.perf_counter() - t_start) * 1000.0

    time.sleep(2.0)
    executor.sync_state(force=True)
    final_pos = executor.cached_position
    
    print("\n" + "=" * 65)
    print(" ROUND-TRIP TEST TRADE RESULTS")
    print("=" * 65)
    print(f" Final Position:      {final_pos:+.4f} {coin} ({'FLAT / CLEAN' if abs(final_pos) < 1e-6 else 'ATTENTION: POSITION OPEN'})")
    print(f" Buy Wire Latency:    {wire_buy_ms:.1f} ms")
    print(f" Sell Wire Latency:   {wire_sell_ms:.1f} ms")
    print(f" Status:              {'ALL SYSTEMS OPERATIONAL' if abs(final_pos) < 1e-6 else 'WARNING'}")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    run_test_order()
