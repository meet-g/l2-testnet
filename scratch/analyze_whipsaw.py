import os, sys, glob, time
sys.path.insert(0, os.path.abspath("."))
from config import AppConfig, StrategiesConfig
from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.composite_alpha import CompositeAlphaSignal
from engine.data_collector import L2ReplayEngine

def test():
    cfg = AppConfig()
    cfg.strategies = StrategiesConfig.load("strategies.json")
    book = OrderBook(coin=cfg.market.coin)
    trades = TradeManager(coin=cfg.market.coin, vpin_bucket_size_btc=5.0, max_vpin_buckets=30)
    sig_weights = cfg.strategies.get_signal_weights()
    enabled_sigs = cfg.strategies.get_enabled_signals_map()
    alpha_model = CompositeAlphaSignal(
        w_wobi=sig_weights.get("WOBI", cfg.signals.weight_wobi),
        w_voi=sig_weights.get("VOI", cfg.signals.weight_voi),
        w_microprice=sig_weights.get("MicroPrice", cfg.signals.weight_microprice),
        w_absorption=sig_weights.get("Absorption", cfg.signals.weight_cvd_absorption),
        w_vpin=sig_weights.get("VPIN", cfg.signals.weight_vpin),
        w_qdap=sig_weights.get("QDAP", 0.20),
        enabled_signals=enabled_sigs,
    )
    replay = L2ReplayEngine("data/btc/hl_btc_l2_20261001_14*.jsonl", speed_multiplier=1000.0)
    for event in replay.stream_events():
        ch = event.get("channel")
        dt = event.get("data")
        now_ms = event.get("recv_ts", 0)
        if ch == "l2Book":
            book.update_from_raw(dt)
        elif ch == "trades":
            trades.process_raw_trades(dt)
        elif ch == "activeAssetCtx":
            book.update_asset_ctx(dt)
        if book.is_valid and abs(book.mid_price - 83851.0) < 5.0:
            res = alpha_model.compute(book, trades, now_ms)
            sub = res.metadata.get("sub_signals", {})
            print(f"Mid: {book.mid_price:.1f} | CC: {sub.get('ConvexityCascade', {}).score:.3f} | ME: {sub.get('MomentumExpansion', {}).score:.3f} | HC: {sub.get('HedgedConvexity', {}).score:.3f}")
            break

if __name__ == "__main__":
    test()
