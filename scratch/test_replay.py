import os
import sys
import glob
import time
import argparse
import pandas as pd
from rich.console import Console
from rich.table import Table

# Add root directory to python path
sys.path.insert(0, os.path.abspath("."))

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner

def run_replay(replay_pattern: str, strategies_config: str = "strategies.json"):
    console = Console()
    cfg = AppConfig()
    # Load custom strategies config if provided
    if strategies_config and os.path.exists(strategies_config):
        cfg.strategies = StrategiesConfig.load(strategies_config)

    runner = L2EngineRunner(config=cfg, record_data=False, enable_audit=True)
    replay = L2ReplayEngine(replay_pattern, speed_multiplier=1000.0)
    
    last_eval_ms = 0
    eval_interval_ms = int(1000 / max(cfg.sample_rate_hz, 1))
    t0 = time.time()
    events_count = 0

    for event in replay.stream_events():
        events_count += 1
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
        now_ms = runner.book.last_update_time_ms or int(time.time() * 1000)
        runner.evaluator.close_open_positions(runner.book.mid_price, now_ms, reason="SESSION_SHUTDOWN")
    
    elapsed = time.time() - t0
    if runner.auditor:
        runner.auditor.close_session()

    # Summarize results
    table = Table(title=f"Replay Results ({replay_pattern}) - {elapsed:.1f}s, {events_count:,} events")
    table.add_column("Strategy", justify="left")
    table.add_column("Trades", justify="right")
    table.add_column("Win%", justify="right")
    table.add_column("Gross PnL ($)", justify="right")
    table.add_column("Net Fees ($)", justify="right")
    table.add_column("Net PnL ($)", justify="right", style="bold")
    table.add_column("Profit Factor", justify="right")

    total_gross = 0.0
    total_fees = 0.0
    total_net = 0.0
    total_trades = 0
    total_wins = 0

    for s_name in runner.evaluator.strategy_names:
        perf = runner.evaluator.get_strategy_performance(s_name, runner.book.mid_price)
        trades = perf.get("trades", 0)
        if trades == 0:
            continue
        gross = perf.get("gross_pnl_usd", 0.0)
        fees = perf.get("fees_paid_usd", 0.0)
        net = perf.get("net_pnl_usd", 0.0)
        win_rate = perf.get("win_rate_pct", 0.0)
        pf = perf.get("profit_factor", 0.0)
        
        total_gross += gross
        total_fees += fees
        total_net += net
        total_trades += trades
        total_wins += int(trades * win_rate / 100.0)

        net_c = "green" if net >= 0 else "red"
        gross_c = "green" if gross >= 0 else "red"
        table.add_row(
            s_name,
            str(trades),
            f"{win_rate:.1f}%",
            f"[{gross_c}]${gross:+.2f}[/{gross_c}]",
            f"-${fees:.2f}",
            f"[{net_c}]${net:+.2f}[/{net_c}]",
            f"{pf:.2f}",
        )

    tot_win_pct = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0
    tot_pf = (total_gross / total_fees) if total_fees > 0 else 0.0
    net_c = "green" if total_net >= 0 else "red"
    gross_c = "green" if total_gross >= 0 else "red"
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_trades}[/bold]",
        f"[bold]{tot_win_pct:.1f}%[/bold]",
        f"[bold {gross_c}]${total_gross:+.2f}[/bold {gross_c}]",
        f"[bold]-${total_fees:.2f}[/bold]",
        f"[bold {net_c}]${total_net:+.2f}[/bold {net_c}]",
        f"[bold]{tot_pf:.2f}[/bold]",
    )
    console.print(table)

    # Detailed Exit Reason Breakdown Table
    exit_table = Table(title="Exit Reason Breakdown")
    exit_table.add_column("Strategy", justify="left")
    exit_table.add_column("Exit Reason", justify="left")
    exit_table.add_column("Count", justify="right")
    exit_table.add_column("Win%", justify="right")
    exit_table.add_column("Net PnL ($)", justify="right")
    exit_table.add_column("Avg Bps", justify="right")

    for s_name in runner.evaluator.strategy_names:
        state = runner.evaluator.strategies.get(s_name)
        if not state or not state.trades:
            continue
        by_reason = {}
        for t in state.trades:
            r = t.exit_reason
            if r not in by_reason:
                by_reason[r] = []
            by_reason[r].append(t)

        for r, trs in sorted(by_reason.items()):
            cnt = len(trs)
            wins = sum(1 for tr in trs if tr.net_pnl_usd > 0)
            net_r = sum(tr.net_pnl_usd for tr in trs)
            avg_bps = sum(tr.return_bps for tr in trs) / cnt if cnt > 0 else 0.0
            r_c = "green" if net_r >= 0 else "red"
            exit_table.add_row(
                s_name,
                r,
                str(cnt),
                f"{wins/cnt*100.0:.1f}%",
                f"[{r_c}]${net_r:+.2f}[/{r_c}]",
                f"{avg_bps:+.1f}",
            )

    console.print(exit_table)
    return {
        "trades": total_trades,
        "gross": total_gross,
        "fees": total_fees,
        "net": total_net,
        "win_rate": tot_win_pct,
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pattern", type=str, default="data/btc/hl_btc_l2_20261001_0[1-2]*.jsonl")
    parser.add_argument("--config", type=str, default="strategies.json")
    args = parser.parse_args()
    run_replay(args.pattern, args.config)
