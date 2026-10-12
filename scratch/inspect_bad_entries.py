import os, sys, glob, time
sys.path.insert(0, os.path.abspath("."))
from config import AppConfig, StrategiesConfig
from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.composite_alpha import CompositeAlphaSignal
from engine.backtester import EdgeEvaluator
from engine.data_collector import L2ReplayEngine

def run():
    cfg = AppConfig()
    cfg.strategies = StrategiesConfig.load("strategies.json")
    enabled_defs = cfg.strategies.get_enabled_strategy_defs()
    params = cfg.strategies.get_strategy_params()

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
    evaluator = EdgeEvaluator(
        market_cfg=cfg.market,
        bt_cfg=cfg.backtest,
        strategy_defs=enabled_defs,
        strategy_params=params,
    )

    replay = L2ReplayEngine("data/btc/hl_btc_l2_20261001_1[4-5]*.jsonl", speed_multiplier=1000.0)
    last_eval_ms = 0
    eval_interval_ms = int(1000 / max(cfg.sample_rate_hz, 1))

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

        if book.is_valid and (now_ms - last_eval_ms >= eval_interval_ms):
            last_eval_ms = now_ms
            res = alpha_model.compute(book, trades, now_ms)
            sub_sigs = {name: sig.score for name, sig in res.metadata.get("sub_signals", {}).items()}
            sub_sigs["CompositeAlpha"] = res.score
            
            # Print state right before entry if entering bad trade
            for s_name in evaluator.strategy_names:
                st = evaluator.strategies[s_name]
                if not st.is_in_position:
                    sc = sub_sigs.get(st.signal_key, 0.0)
                    ethr = params.get(s_name, {}).get("entry_threshold", 0.75)
                    if abs(sc) >= ethr and (abs(book.mid_price - 83680.0) < 5.0 or abs(book.mid_price - 84159.0) < 5.0):
                        cvd_val, _, _ = trades.get_cvd_in_window(30.0)
                        vpin_val = trades.calculate_vpin(30) or 0.0
                        print(f"[{s_name}] Entry trigger at mid={book.mid_price:.1f}, score={sc:.3f}, cvd={cvd_val:.2f}, vpin={vpin_val:.2f}")
            
            evaluator.record_step(now_ms, book.mid_price, book.best_bid, book.best_ask, sub_sigs)

if __name__ == "__main__":
    run()
