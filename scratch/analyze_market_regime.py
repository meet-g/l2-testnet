import glob
import json
import os
import sys

sys.path.insert(0, ".")

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.composite_alpha import CompositeAlphaSignal
from config import AppConfig

def analyze_coin(coin, pattern):
    files = sorted(glob.glob(pattern))
    print(f"\n{'='*70}\nANALYZING {coin.upper()} ({len(files)} files)\n{'='*70}")
    
    cfg = AppConfig()
    cfg.market.coin = coin.upper()
    book = OrderBook(coin=coin.upper())
    trades = TradeManager(coin=coin.upper())
    alpha_model = CompositeAlphaSignal(cfg.signals)
    
    # Track stats
    prices = []
    spreads_bps = []
    rolling_vol_3m = []
    trade_counts = 0
    trade_sizes = []
    
    price_buffer = []  # (ts, px)
    
    # We will sample 3 representative files: beginning, middle, and end
    sample_files = [files[0], files[len(files)//2], files[-1]] if len(files) >= 3 else files
    
    scores = {"HedgedConvexity": [], "ConvexityCascade": [], "MomentumExpansion": []}
    
    for fpath in sample_files:
        print(f"Reading {os.path.basename(fpath)} ({os.path.getsize(fpath)/(1024*1024):.1f} MB)...")
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                ev = json.loads(line)
                ch = ev.get("channel")
                dt = ev.get("data")
                ts = ev.get("recv_ts", 0)
                
                if ch == "l2Book":
                    book.update_from_raw(dt)
                    if book.is_valid:
                        mid = book.mid_price
                        prices.append(mid)
                        spreads_bps.append(book.spread_bps)
                        
                        price_buffer.append((ts, mid))
                        cutoff = ts - 180_000
                        while price_buffer and price_buffer[0][0] < cutoff:
                            price_buffer.pop(0)
                        
                        if len(price_buffer) >= 15:
                            p_min = min(p for _, p in price_buffer)
                            p_max = max(p for _, p in price_buffer)
                            vol = ((p_max - p_min) / mid) * 10000.0 if mid > 0 else 0
                            rolling_vol_3m.append(vol)
                            
                elif ch == "trades":
                    trades.process_raw_trades(dt)
                    if isinstance(dt, list):
                        trade_counts += len(dt)
                        for t in dt:
                            trade_sizes.append(float(t.get("sz", 0)))
                
                # Sample alpha computation once in a while
                if len(prices) % 200 == 0 and book.is_valid:
                    res = alpha_model.compute(book, trades, ts)
                    subs = res.metadata.get("sub_signals", {})
                    for k in scores:
                        if k in subs:
                            scores[k].append(subs[k].score)
                            
    if prices:
        print(f"Mid Price Range: ${min(prices):,.2f} - ${max(prices):,.2f}")
        print(f"Average Spread: {sum(spreads_bps)/len(spreads_bps):.2f} bps (Max: {max(spreads_bps):.2f} bps)")
    if rolling_vol_3m:
        sorted_v = sorted(rolling_vol_3m)
        p10 = sorted_v[int(len(sorted_v)*0.10)]
        p25 = sorted_v[int(len(sorted_v)*0.25)]
        p50 = sorted_v[int(len(sorted_v)*0.50)]
        p75 = sorted_v[int(len(sorted_v)*0.75)]
        p90 = sorted_v[int(len(sorted_v)*0.90)]
        print(f"Rolling 3-min Volatility (bps):")
        print(f"  Min: {min(sorted_v):.2f} | 10%: {p10:.2f} | Median: {p50:.2f} | 75%: {p75:.2f} | 90%: {p90:.2f} | Max: {max(sorted_v):.2f}")
        print(f"  % of time Volatility >= 4.5 bps (current gate): {sum(1 for v in rolling_vol_3m if v >= 4.5)/len(rolling_vol_3m)*100:.1f}%")
        print(f"  % of time Volatility >= 3.0 bps: {sum(1 for v in rolling_vol_3m if v >= 3.0)/len(rolling_vol_3m)*100:.1f}%")
        print(f"  % of time Volatility >= 2.0 bps: {sum(1 for v in rolling_vol_3m if v >= 2.0)/len(rolling_vol_3m)*100:.1f}%")
        
    print(f"Trades processed: {trade_counts}")
    if trade_sizes:
        print(f"Trade size: avg={sum(trade_sizes)/len(trade_sizes):.3f}, min={min(trade_sizes):.3f}, max={max(trade_sizes):.3f}")
        
    print("\nAlpha Score Percentiles:")
    for k, v in scores.items():
        if v:
            v_abs = [abs(x) for x in v]
            v_abs.sort()
            print(f"  {k} (|score|): max={max(v_abs):.3f}, 99%={v_abs[int(len(v_abs)*0.99)]:.3f}, 95%={v_abs[int(len(v_abs)*0.95)]:.3f}, median={v_abs[len(v_abs)//2]:.3f}")
            print(f"    % >= 0.80 (current entry threshold): {sum(1 for x in v_abs if x >= 0.80)/len(v_abs)*100:.2f}%")
            print(f"    % >= 0.60: {sum(1 for x in v_abs if x >= 0.60)/len(v_abs)*100:.2f}%")
            print(f"    % >= 0.50: {sum(1 for x in v_abs if x >= 0.50)/len(v_abs)*100:.2f}%")

if __name__ == "__main__":
    analyze_coin("btc", "data/btc/hl_btc_l2_2026100*.jsonl")
    analyze_coin("hype", "data/hype/hl_hype_l2_2026100*.jsonl")
