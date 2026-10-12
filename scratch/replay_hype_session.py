import glob
import os
import sys

sys.path.insert(0, ".")

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner

def replay_hype():
    all_files = sorted(glob.glob("data/hype/hl_hype_l2_2026100*.jsonl"))
    print(f"Replaying {len(all_files)} files for HYPE...")
    
    cfg = AppConfig()
    cfg.market.coin = "HYPE"
    cfg.strategies = StrategiesConfig.load("strategies.json")
    
    total_trades = []
    strat_trades = {}
    
    eval_interval_ms = int(1000 / max(cfg.sample_rate_hz, 1))
    
    for fpath in all_files:
        runner = L2EngineRunner(config=cfg, record_data=False)
        replay = L2ReplayEngine(fpath, speed_multiplier=10000.0)
        
        last_eval_ms = 0
        for event in replay.stream_events():
            ch = event.get("channel")
            dt = event.get("data")
            now_ms = event.get("recv_ts", 0)
            
            if ch == "l2Book":
                runner.book.update_from_raw(dt)
            elif ch == "trades":
                runner.trades.process_raw_trades(dt)
            elif ch == "activeAssetCtx":
                runner.book.update_asset_ctx(dt)
                
            if runner.book.is_valid and (now_ms - last_eval_ms >= eval_interval_ms):
                last_eval_ms = now_ms
                res = runner.alpha_model.compute(runner.book, runner.trades, now_ms)
                sub_sigs = {name: sig.score for name, sig in res.metadata.get("sub_signals", {}).items()}
                sub_sigs["CompositeAlpha"] = res.score
                runner.evaluator.record_step(
                    now_ms,
                    runner.book.mid_price,
                    runner.book.best_bid,
                    runner.book.best_ask,
                    sub_sigs,
                )
        
        if runner.book.is_valid:
            now_ms = runner.book.last_update_time_ms or 0
            runner.evaluator.close_open_positions(runner.book.mid_price, now_ms, reason="SESSION_SHUTDOWN")
            
        for s_name in cfg.strategies.execution_strategies:
            st = runner.evaluator.strategies.get(s_name)
            if st and st.trades:
                for t in st.trades:
                    total_trades.append(t)
                    strat_trades.setdefault(s_name, []).append(t)
                    
    print(f"\n--- RESULTS FOR HYPE ---")
    print(f"Total Trades: {len(total_trades)}")
    wins = sum(1 for t in total_trades if t.net_pnl_usd > 0)
    gross = sum(t.gross_pnl_usd for t in total_trades)
    fees = sum(t.fees_usd for t in total_trades)
    net = sum(t.net_pnl_usd for t in total_trades)
    print(f"Wins: {wins}/{len(total_trades)}" if total_trades else "No trades")
    print(f"Gross: ${gross:+.4f} | Fees: ${fees:.4f} | Net: ${net:+.4f}")
    for s_name, trs in strat_trades.items():
        s_wins = sum(1 for t in trs if t.net_pnl_usd > 0)
        s_net = sum(t.net_pnl_usd for t in trs)
        print(f"  {s_name}: {len(trs)} trades | {s_wins} wins | Net: ${s_net:+.4f}")
        for t in trs:
            print(f"    {t.side} @ ${t.entry_price:.3f} -> ${t.exit_price:.3f} | Net: ${t.net_pnl_usd:+.4f} ({t.return_bps:+.1f} bps) | Exit: {t.exit_reason}")

if __name__ == "__main__":
    replay_hype()
