"""High-Throughput Parallel Evaluation across ALL recorded datasets (BTC, HYPE, ETH, SOL).

Runs multi-process parallel replay across all historical L2 JSONL files in data/
evaluating core alpha strategies (Hedged_Convexity, Convexity_Cascade, Momentum_Expansion)
and optional standalone factor strategies.
"""

import argparse
import bisect
import glob
import json
import operator
import os
import sys
import time
import multiprocessing

# Configure OpenMP & BLAS threading runtimes to eliminate CPU spin-waiting loops
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

from typing import Any, Dict, List, Optional
from collections import Counter

from rich.console import Console
from rich.table import Table

try:
    import orjson
except ImportError:
    import json as orjson

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner

_GLOBAL_STRATEGIES_CFG: Optional[StrategiesConfig] = None


def _init_worker(strategies_path: str = "strategies.json", active_strats: Optional[List[str]] = None) -> None:
    """One-time worker process initialization for multiprocessing.Pool (F13)."""
    global _GLOBAL_STRATEGIES_CFG
    _GLOBAL_STRATEGIES_CFG = StrategiesConfig.load(strategies_path)
    if active_strats:
        for s_name in _GLOBAL_STRATEGIES_CFG.execution_strategies:
            _GLOBAL_STRATEGIES_CFG.execution_strategies[s_name].enabled = (s_name in active_strats)

    # Determine which alpha signals are directly required by active execution strategies
    needed_sigs = set()
    for s_name, s_cfg in _GLOBAL_STRATEGIES_CFG.execution_strategies.items():
        if s_cfg.enabled and s_cfg.signal_key:
            needed_sigs.add(s_cfg.signal_key)

    # Disable unused heavy sub-signals (AdaptiveML, Absorption, VOI, WOBI, etc.) if not needed
    if "CompositeAlpha" not in needed_sigs:
        for sig_name in _GLOBAL_STRATEGIES_CFG.alpha_signals:
            if sig_name not in needed_sigs:
                _GLOBAL_STRATEGIES_CFG.alpha_signals[sig_name].enabled = False
    elif "AdaptiveML" in _GLOBAL_STRATEGIES_CFG.alpha_signals:
        _GLOBAL_STRATEGIES_CFG.alpha_signals["AdaptiveML"].enabled = False

    # Avoid redundant UI dashboard and rich console initializations inside replay worker processes
    import main
    main.TerminalDashboard = lambda *args, **kwargs: None
    main.Console = lambda *args, **kwargs: None

    # Install C-level level sorting and observation allocation bypass
    _install_worker_accelerators()


_px_key = operator.attrgetter("px")


def _install_worker_accelerators() -> None:
    """Installs C-level attribute sorting and observation allocation bypass in replay workers."""
    from core.orderbook import OrderBook, L2Level
    from engine.backtester import EdgeEvaluator, SignalObservation

    if getattr(OrderBook, "_is_accelerated", False):
        return

    def _fast_update_from_raw(self, raw_data: Dict[str, Any], is_macro: Optional[bool] = None) -> None:
        levels = raw_data.get("levels", [[], []])
        if len(levels) < 2:
            return

        raw_bids, raw_asks = levels[0], levels[1]
        timestamp = raw_data.get("time", int(time.time() * 1000))

        parsed_bids = [
            L2Level(float(l["px"]), float(l["sz"]), int(l.get("n", 1)))
            for l in raw_bids
        ]
        parsed_bids.sort(key=_px_key, reverse=True)

        parsed_asks = [
            L2Level(float(l["px"]), float(l["sz"]), int(l.get("n", 1)))
            for l in raw_asks
        ]
        parsed_asks.sort(key=_px_key)

        if is_macro:
            self.macro_bids = parsed_bids
            self.macro_asks = parsed_asks
            self.last_macro_update_time_ms = timestamp
            self.macro_update_count += 1
            if not self.bids:
                self.bids = parsed_bids
                self.asks = parsed_asks
                self.last_update_time_ms = timestamp
                self.update_count += 1
            return

        self.bids = parsed_bids
        self.asks = parsed_asks
        self.last_update_time_ms = timestamp
        self.update_count += 1

    OrderBook.update_from_raw = _fast_update_from_raw
    OrderBook._is_accelerated = True

    def _fast_record_step(self, timestamp_ms: int, mid_price: float, best_bid: float, best_ask: float, signals: Dict[str, float]) -> None:
        if mid_price <= 0:
            return

        if self.bt_cfg.horizons_seconds:
            obs = SignalObservation(
                timestamp_ms=timestamp_ms,
                price=mid_price,
                signals=signals.copy(),
            )
            self.observations.append(obs)
            self._update_forward_returns(timestamp_ms, mid_price)

        self.rolling_prices.append((timestamp_ms, mid_price))
        while self._min_price_deque and self._min_price_deque[-1][1] >= mid_price:
            self._min_price_deque.pop()
        self._min_price_deque.append((timestamp_ms, mid_price))

        while self._max_price_deque and self._max_price_deque[-1][1] <= mid_price:
            self._max_price_deque.pop()
        self._max_price_deque.append((timestamp_ms, mid_price))

        cutoff_ms = timestamp_ms - 180_000
        while self.rolling_prices and self.rolling_prices[0][0] < cutoff_ms:
            self.rolling_prices.popleft()
        while self._min_price_deque and self._min_price_deque[0][0] < cutoff_ms:
            self._min_price_deque.popleft()
        while self._max_price_deque and self._max_price_deque[0][0] < cutoff_ms:
            self._max_price_deque.popleft()

        if len(self.rolling_prices) >= 15:
            if not hasattr(self, "_last_vol_calc_ms") or (timestamp_ms - self._last_vol_calc_ms) >= 1000:
                self._last_vol_calc_ms = timestamp_ms
                p_min = self._min_price_deque[0][1]
                p_max = self._max_price_deque[0][1]
                self.current_volatility_bps = ((p_max - p_min) / mid_price) * 10_000.0 if mid_price > 0 else 0.0
        else:
            self.current_volatility_bps = 99.0

        self._update_paper_trading(timestamp_ms, mid_price, best_bid, best_ask, signals)

    EdgeEvaluator.record_step = _fast_record_step

    from core.trade_stream import TradeManager, Trade
    from collections import deque

    _orig_tm_init = TradeManager.__init__
    _orig_add_trade = TradeManager._add_trade

    def _fast_tm_init(self, *args, **kwargs):
        _orig_tm_init(self, *args, **kwargs)
        self._cvd_history = deque(maxlen=self.max_trades)

    def _fast_add_trade(self, trade):
        _orig_add_trade(self, trade)
        if not hasattr(self, "_cvd_history"):
            self._cvd_history = deque(maxlen=self.max_trades)
        self._cvd_history.append((trade.timestamp_ms, trade.side == "B", trade.size))

    def _fast_get_cvd_in_window(self, window_secs: float):
        if window_secs in self._cvd_cache:
            return self._cvd_cache[window_secs]
        now_ms = self.last_trade_time_ms or int(time.time() * 1000)
        cutoff_ms = now_ms - int(window_secs * 1000)
        cvd = 0.0
        buy_vol = 0.0
        sell_vol = 0.0
        for ts, is_b, sz in reversed(self._cvd_history):
            if ts < cutoff_ms:
                break
            if is_b:
                buy_vol += sz
                cvd += sz
            else:
                sell_vol += sz
                cvd -= sz
        res = (cvd, buy_vol, sell_vol)
        self._cvd_cache[window_secs] = res
        return res

    def _fast_process_raw_trades(self, raw_trades: List[Dict[str, Any]]) -> List[Trade]:
        new_trades: List[Trade] = []
        for r in raw_trades:
            try:
                t = Trade(
                    timestamp_ms=int(r.get("time") or int(time.time() * 1000)),
                    price=float(r["px"]),
                    size=float(r["sz"]),
                    side=str(r["side"]).upper(),
                    tid=int(r.get("tid", 0)),
                    hash=str(r.get("hash", "")),
                )
                self._add_trade(t)
                new_trades.append(t)
            except (ValueError, KeyError):
                continue
        return new_trades

    TradeManager.__init__ = _fast_tm_init
    TradeManager._add_trade = _fast_add_trade
    TradeManager.get_cvd_in_window = _fast_get_cvd_in_window
    TradeManager.process_raw_trades = _fast_process_raw_trades



def detect_coin(filepath: str) -> str:
    """Detects coin from filepath."""
    fpath_lower = filepath.lower().replace("\\", "/")
    for c in ["btc", "hype", "sol", "eth"]:
        if f"hl_{c}_" in fpath_lower or f"/{c}/" in fpath_lower:
            return c.upper()
    return "BTC"


def get_coin_order_size(coin: str) -> float:
    """Returns calibrated order size to approximate ~$8,500 - $9,500 USD notional."""
    c = coin.upper()
    if c == "HYPE":
        return 95.0
    elif c == "SOL":
        return 50.0
    elif c == "ETH":
        return 3.0
    else:  # BTC
        return 0.1


def replay_single_dataset(arg: Any) -> Dict[str, Any]:
    """Top-level worker function for multiprocessing.Pool (Windows spawn-compatible)."""
    global _GLOBAL_STRATEGIES_CFG
    if isinstance(arg, tuple):
        filepath = arg[0]
        size_mb = float(arg[1]) if len(arg) > 1 and isinstance(arg[1], (int, float)) else os.path.getsize(filepath) / (1024.0 * 1024.0)
        enabled_strategies_list = arg[2] if len(arg) > 2 else None
    else:
        filepath = arg
        size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)
        enabled_strategies_list = None

    if _GLOBAL_STRATEGIES_CFG is None:
        _init_worker("strategies.json", enabled_strategies_list)

    filename = os.path.basename(filepath)
    coin = detect_coin(filepath)

    cfg = AppConfig(strategies=_GLOBAL_STRATEGIES_CFG)
    cfg.market.coin = coin
    cfg.backtest.order_size_btc = get_coin_order_size(coin)
    cfg.backtest.horizons_seconds = []  # Bypass unused forward return IC computation (F13)

    if enabled_strategies_list:
        for s_name in cfg.strategies.execution_strategies:
            cfg.strategies.execution_strategies[s_name].enabled = (s_name in enabled_strategies_list)

    runner = L2EngineRunner(config=cfg, record_data=False, enable_audit=False)
    # Explicit OrderBook History Bypass (F11)
    runner.book.enable_history = False
    runner.book.history = None

    book = runner.book
    trades = runner.trades
    evaluator = runner.evaluator
    book_update_from_raw = book.update_from_raw
    trades_process_raw = trades.process_raw_trades
    book_update_asset_ctx = book.update_asset_ctx
    evaluator_record_step = evaluator.record_step

    active_sig_callers = {}
    if hasattr(runner.alpha_model, "signal_hedged") and runner.alpha_model.signal_hedged:
        active_sig_callers["HedgedConvexity"] = runner.alpha_model.signal_hedged.compute
    if hasattr(runner.alpha_model, "signal_convexity") and runner.alpha_model.signal_convexity:
        active_sig_callers["ConvexityCascade"] = runner.alpha_model.signal_convexity.compute
    if hasattr(runner.alpha_model, "signal_mom") and runner.alpha_model.signal_mom:
        active_sig_callers["MomentumExpansion"] = runner.alpha_model.signal_mom.compute

    call_hedged = active_sig_callers.get("HedgedConvexity")
    call_convexity = active_sig_callers.get("ConvexityCascade")
    call_mom = active_sig_callers.get("MomentumExpansion")
    other_callers = [(k, fn) for k, fn in active_sig_callers.items() if k not in ("HedgedConvexity", "ConvexityCascade", "MomentumExpansion")]

    last_eval_ms = 0
    eval_interval_ms = int(1000 / max(cfg.sample_rate_hz, 1))

    sub_sigs = {
        "HedgedConvexity": 0.0,
        "ConvexityCascade": 0.0,
        "MomentumExpansion": 0.0,
        "CompositeAlpha": 0.0,
    }

    t0 = time.time()
    events_count = 0
    loads = orjson.loads

    try:
        with open(filepath, "rb", buffering=1024 * 1024) as f:
            for line in f:
                if len(line) <= 2:
                    continue
                try:
                    event = loads(line)
                    ch = event["channel"]
                    dt = event["data"]
                    now_ms = event["recv_ts"]
                except Exception:
                    continue

                events_count += 1

                if ch == "l2Book":
                    book_update_from_raw(dt)
                elif ch == "trades":
                    trades_process_raw(dt)
                elif ch == "activeAssetCtx":
                    book_update_asset_ctx(dt)
                else:
                    continue

                if now_ms - last_eval_ms >= eval_interval_ms:
                    bids = book.bids
                    asks = book.asks
                    if bids and asks:
                        bb = bids[0].px
                        ba = asks[0].px
                        if bb < ba:
                            last_eval_ms = now_ms
                            mid_px = (bb + ba) * 0.5
                            if call_hedged:
                                sub_sigs["HedgedConvexity"] = call_hedged(book, trades, now_ms).score
                            if call_convexity:
                                sub_sigs["ConvexityCascade"] = call_convexity(book, trades, now_ms).score
                            if call_mom:
                                sub_sigs["MomentumExpansion"] = call_mom(book, trades, now_ms).score
                            if other_callers:
                                for k, fn in other_callers:
                                    sub_sigs[k] = fn(book, trades, now_ms).score

                            evaluator_record_step(
                                now_ms,
                                mid_px,
                                bb,
                                ba,
                                sub_sigs,
                            )

        if book.is_valid:
            now_ms = book.last_update_time_ms or int(time.time() * 1000)
            evaluator.close_open_positions(book.mid_price, now_ms, reason="SESSION_SHUTDOWN")

    except Exception as e:
        return {
            "filename": filename,
            "filepath": filepath,
            "coin": coin,
            "size_mb": size_mb,
            "events_count": events_count,
            "elapsed_s": time.time() - t0,
            "file_net": 0.0,
            "file_trades": 0,
            "error": str(e),
            "strategies": {},
            "exit_stats": {},
            "all_trades": [],
        }

    elapsed_s = time.time() - t0
    strat_results = {}
    exit_stats: Dict[str, List[float]] = {}  # exit_reason -> [count, net_pnl_usd, sum_return_bps]

    active_strats = [s for s, st in cfg.strategies.execution_strategies.items() if st.enabled]
    file_total_net = 0.0
    file_total_trades = 0

    for s_name in active_strats:
        st = runner.evaluator.strategies.get(s_name)
        trades_list = st.trades if st else []
        n = len(trades_list)
        file_total_trades += n

        num_wins = 0
        num_losses = 0
        num_stops = 0
        num_hedges = 0
        num_tps = 0
        num_trails = 0
        gross_pnl = 0.0
        fees = 0.0
        net_pnl = 0.0
        gross_wins = 0.0
        loss_gross_sum = 0.0

        for t in trades_list:
            g = t.gross_pnl_usd
            gross_pnl += g
            fees += t.fees_usd
            net = t.net_pnl_usd
            net_pnl += net
            if net > 0:
                num_wins += 1
                gross_wins += g
            else:
                num_losses += 1
                loss_gross_sum += g

            reason = t.exit_reason or "UNKNOWN"
            if reason == "STOP_LOSS":
                num_stops += 1
            elif reason == "DEFENSIVE_MAKER_HEDGE":
                num_hedges += 1
            elif reason == "TAKE_PROFIT":
                num_tps += 1
            elif reason == "TRAILING_STOP":
                num_trails += 1

            if reason not in exit_stats:
                exit_stats[reason] = [1.0, float(net), float(t.return_bps)]
            else:
                e = exit_stats[reason]
                e[0] += 1.0
                e[1] += float(net)
                e[2] += float(t.return_bps)

        file_total_net += net_pnl
        gross_losses = abs(loss_gross_sum)

        strat_results[s_name] = {
            "trades": n,
            "wins": num_wins,
            "losses": num_losses,
            "stops": num_stops,
            "hedges": num_hedges,
            "tps": num_tps,
            "trails": num_trails,
            "gross_pnl": gross_pnl,
            "fees": fees,
            "net_pnl": net_pnl,
            "gross_wins": gross_wins,
            "gross_losses": gross_losses,
            "profit_factor": (gross_wins / gross_losses) if gross_losses > 0 else (99.0 if gross_wins > 0 else 0.0),
        }

    return {
        "filename": filename,
        "filepath": filepath,
        "coin": coin,
        "size_mb": size_mb,
        "events_count": events_count,
        "elapsed_s": elapsed_s,
        "file_net": file_total_net,
        "file_trades": file_total_trades,
        "pid": os.getpid(),
        "error": None,
        "strategies": strat_results,
        "exit_stats": exit_stats,
        "all_trades": [],
    }


def run_full_backtest(
    coins: Optional[List[str]] = None,
    max_files_per_coin: int = 0,
    workers: Optional[int] = None,
    strategies_filter: Optional[List[str]] = None,
    verify_baseline: bool = False,
    baseline_path: Optional[str] = "audits/hype_76_sessions_benchmark.json",
) -> Dict[str, Any]:
    console = Console(highlight=False)

    if verify_baseline:
        target_coins = coins or ["hype"]
        if max_files_per_coin <= 0:
            max_files_per_coin = 76
    else:
        target_coins = coins or ["btc", "hype", "eth", "sol"]

    all_files = []
    for c in target_coins:
        cdir = os.path.join("data", c.lower())
        if os.path.isdir(cdir):
            c_files = sorted(glob.glob(os.path.join(cdir, "*.jsonl")), key=os.path.getsize, reverse=True)
            if verify_baseline:
                # Exclude live recording files created after the benchmark capture date (2026-10-24)
                c_files = [f for f in c_files if os.path.basename(f)[11:19] <= "20261024"]
            if max_files_per_coin > 0:
                c_files = c_files[:max_files_per_coin]
            all_files.extend(c_files)

    if not all_files:
        console.print("[bold red]No recording files found across target coins![/bold red]")
        return {}

    # LPT (Longest Processing Time First) bin packing: sort globally descending by file size
    all_files.sort(key=os.path.getsize, reverse=True)

    total_mb = sum(os.path.getsize(f) for f in all_files) / (1024.0 * 1024.0)
    # Multi-Core Saturation (F12): default to all available host CPU cores
    if not workers or workers <= 0:
        num_workers = os.cpu_count() or 4
    else:
        num_workers = min(workers, os.cpu_count() or 4)

    console.print("\n[bold cyan]===============================================================================[/bold cyan]")
    console.print("[bold green]CROSS-ASSET FULL L2 MICROSTRUCTURE BACKTEST: ALL STRATEGIES & ALL DATA[/bold green]")
    console.print("[bold cyan]===============================================================================[/bold cyan]")
    console.print(f"Target Datasets:  [bold yellow]{len(all_files)} recording sessions[/bold yellow] across {', '.join(c.upper() for c in target_coins)} ({total_mb:.1f} MB)")
    console.print(f"Parallel Workers: [bold yellow]{num_workers} processes[/bold yellow] (CPU: {os.cpu_count()} cores)")

    cfg_sample = StrategiesConfig.load("strategies.json")
    active_strats = [s for s, st in cfg_sample.execution_strategies.items() if st.enabled]
    if strategies_filter:
        active_strats = strategies_filter
    console.print(f"Active Strategies:[bold yellow] {', '.join(active_strats)}[/bold yellow]\n")

    tasks = [(f, os.path.getsize(f) / (1024.0 * 1024.0)) for f in all_files]
    results = []

    # Multiprocessing Pool with greedy work-stealing and one-time worker init
    with multiprocessing.Pool(
        processes=num_workers,
        initializer=_init_worker,
        initargs=("strategies.json", active_strats),
    ) as pool:
        start_time = time.time()
        completed = 0
        running_net = 0.0
        running_trades = 0

        for res in pool.imap_unordered(replay_single_dataset, tasks, chunksize=1):
            completed += 1
            results.append(res)

            if res.get("error"):
                console.print(f"[{completed:3d}/{len(all_files):3d}] [bold red]Error in {res['filename']}: {res['error']}[/bold red]")
            else:
                file_net = res.get("file_net", sum(s["net_pnl"] for s in res["strategies"].values()))
                file_trd = res.get("file_trades", sum(s["trades"] for s in res["strategies"].values()))
                running_net += file_net
                running_trades += file_trd
                c_style = "green" if file_net > 0 else ("red" if file_net < 0 else "dim")
                console.print(
                    f"[{completed:3d}/{len(all_files):3d}] ✓ [{res['coin']:4s}] {res['filename']:<34} "
                    f"({res['size_mb']:4.1f} MB) | Trd: {file_trd:2d} | Net: [{c_style}]${file_net:+6.2f}[/{c_style}] | "
                    f"Running Net: [bold {'green' if running_net >= 0 else 'red'}]${running_net:+8.2f}[/bold {'green' if running_net >= 0 else 'red'}]"
                )

        total_duration = time.time() - start_time

    # Group by Coin
    coin_totals = {}
    strat_totals = {}
    for s_name in active_strats:
        strat_totals[s_name] = {
            "trades": 0, "wins": 0, "losses": 0, "stops": 0, "hedges": 0,
            "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "gw": 0.0, "gl": 0.0
        }

    exit_totals: Dict[str, List[float]] = {}

    for r in results:
        if r.get("error"):
            continue
        c = r["coin"]
        coin_totals.setdefault(c, {"trades": 0, "wins": 0, "losses": 0, "stops": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0})
        
        for s_name, s_data in r["strategies"].items():
            if s_name not in strat_totals:
                strat_totals[s_name] = {"trades": 0, "wins": 0, "losses": 0, "stops": 0, "hedges": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "gw": 0.0, "gl": 0.0}
            st = strat_totals[s_name]
            st["trades"] += s_data["trades"]
            st["wins"] += s_data["wins"]
            st["losses"] += s_data["losses"]
            st["stops"] += s_data["stops"]
            st["hedges"] += s_data["hedges"]
            st["gross_pnl"] += s_data["gross_pnl"]
            st["fees"] += s_data["fees"]
            st["net_pnl"] += s_data["net_pnl"]
            st["gw"] += s_data["gross_wins"]
            st["gl"] += s_data["gross_losses"]

            coin_totals[c]["trades"] += s_data["trades"]
            coin_totals[c]["wins"] += s_data["wins"]
            coin_totals[c]["losses"] += s_data["losses"]
            coin_totals[c]["stops"] += s_data["stops"]
            coin_totals[c]["gross_pnl"] += s_data["gross_pnl"]
            coin_totals[c]["fees"] += s_data["fees"]
            coin_totals[c]["net_pnl"] += s_data["net_pnl"]

        for reason, vals in r.get("exit_stats", {}).items():
            if reason not in exit_totals:
                exit_totals[reason] = [vals[0], vals[1], vals[2]]
            else:
                exit_totals[reason][0] += vals[0]
                exit_totals[reason][1] += vals[1]
                exit_totals[reason][2] += vals[2]

    # 1. Strategy Summary Table
    console.print("\n")
    summary_table = Table(
        title=f"Grand Strategy Performance Matrix Across All Datasets ({len(all_files)} Sessions, {total_duration:.1f}s Replay)",
        header_style="bold magenta",
        show_header=True,
    )
    summary_table.add_column("Strategy", justify="left")
    summary_table.add_column("Trades", justify="right")
    summary_table.add_column("Win Rate", justify="right")
    summary_table.add_column("Gross PnL ($)", justify="right")
    summary_table.add_column("Fees ($)", justify="right")
    summary_table.add_column("Net PnL ($)", justify="right", style="bold")
    summary_table.add_column("Profit Factor", justify="right")
    summary_table.add_column("Stop Losses", justify="right")
    summary_table.add_column("Maker Hedges", justify="right")

    comb_trades = 0
    comb_wins = 0
    comb_gross = 0.0
    comb_fees = 0.0
    comb_net = 0.0
    comb_stops = 0
    comb_hedges = 0
    comb_gw = 0.0
    comb_gl = 0.0

    for s_name, st in strat_totals.items():
        if st["trades"] == 0:
            continue
        wr = (st["wins"] / st["trades"]) * 100.0
        pf = (st["gw"] / max(st["gl"], 1e-4)) if st["gl"] > 0 else (99.0 if st["gw"] > 0 else 0.0)
        c = "green" if st["net_pnl"] > 0 else "red"

        summary_table.add_row(
            s_name,
            str(st["trades"]),
            f"{wr:.1f}%",
            f"${st['gross_pnl']:+8.2f}",
            f"${st['fees']:8.2f}",
            f"[{c}]${st['net_pnl']:+8.2f}[/{c}]",
            f"{pf:.2f}",
            str(st["stops"]),
            str(st["hedges"]),
        )
        comb_trades += st["trades"]
        comb_wins += st["wins"]
        comb_gross += st["gross_pnl"]
        comb_fees += st["fees"]
        comb_net += st["net_pnl"]
        comb_stops += st["stops"]
        comb_hedges += st["hedges"]
        comb_gw += st["gw"]
        comb_gl += st["gl"]

    comb_wr = (comb_wins / comb_trades * 100.0) if comb_trades > 0 else 0.0
    comb_pf = (comb_gw / max(comb_gl, 1e-4)) if comb_gl > 0 else 0.0
    summary_table.add_row(
        "[bold cyan]PORTFOLIO TOTAL[/bold cyan]",
        f"[bold]{comb_trades}[/bold]",
        f"[bold]{comb_wr:.1f}%[/bold]",
        f"[bold]${comb_gross:+8.2f}[/bold]",
        f"[bold]${comb_fees:8.2f}[/bold]",
        f"[bold {'green' if comb_net >= 0 else 'red'}]${comb_net:+8.2f}[/bold {'green' if comb_net >= 0 else 'red'}]",
        f"[bold]{comb_pf:.2f}[/bold]",
        f"[bold]{comb_stops}[/bold]",
        f"[bold]{comb_hedges}[/bold]",
    )
    console.print(summary_table)

    # 2. Coin Breakdown Table
    console.print("\n")
    coin_table = Table(
        title="Asset Breakdown Performance Matrix",
        header_style="bold cyan",
        show_header=True,
    )
    coin_table.add_column("Asset", justify="left")
    coin_table.add_column("Datasets", justify="right")
    coin_table.add_column("Trades", justify="right")
    coin_table.add_column("Win Rate", justify="right")
    coin_table.add_column("Gross PnL ($)", justify="right")
    coin_table.add_column("Fees ($)", justify="right")
    coin_table.add_column("Net PnL ($)", justify="right", style="bold")
    coin_table.add_column("Stop Losses", justify="right")

    for coin_name, c_data in sorted(coin_totals.items()):
        c_files_count = len([r for r in results if r.get("coin") == coin_name and not r.get("error")])
        if c_data["trades"] == 0:
            coin_table.add_row(coin_name, str(c_files_count), "0", "0.0%", "$0.00", "$0.00", "$0.00", "0")
            continue
        c_wr = (c_data["wins"] / c_data["trades"]) * 100.0
        c_style = "green" if c_data["net_pnl"] > 0 else "red"
        coin_table.add_row(
            f"[bold yellow]{coin_name}[/bold yellow]",
            str(c_files_count),
            str(c_data["trades"]),
            f"{c_wr:.1f}%",
            f"${c_data['gross_pnl']:+8.2f}",
            f"${c_data['fees']:8.2f}",
            f"[{c_style}]${c_data['net_pnl']:+8.2f}[/{c_style}]",
            str(c_data["stops"]),
        )
    console.print(coin_table)

    # 3. Exit Distribution Breakdown
    console.print("\n[bold yellow]Trade Exit Reason Distribution:[/bold yellow]")
    for reason, (count_f, r_net, bps_sum) in sorted(exit_totals.items(), key=lambda x: x[1][0], reverse=True):
        count = int(count_f)
        pct = (count / max(comb_trades, 1)) * 100.0
        r_avg = bps_sum / count if count > 0 else 0.0
        console.print(f"  - {reason:<24}: {count:4d} trades ({pct:4.1f}%) | Avg Return: {r_avg:+5.1f} bps | Net PnL: ${r_net:+8.2f}")

    worker_pids = {}
    for r in results:
        p = r.get("pid", 0)
        worker_pids[p] = worker_pids.get(p, 0.0) + r.get("elapsed_s", 0.0)
    max_w = max(worker_pids.values()) if worker_pids else 0.0
    min_w = min(worker_pids.values()) if worker_pids else 0.0
    console.print(f"[dim]Worker compute spread: min={min_w:.2f}s, max={max_w:.2f}s across {len(worker_pids)} workers[/dim]")

    console.print(f"\n[bold green]Cross-Asset Replay Completed in {total_duration:.1f} seconds across {len(all_files)} datasets![/bold green]\n")

    summary_result = {
        "total_duration": total_duration,
        "sessions_count": len(all_files),
        "comb_trades": comb_trades,
        "comb_wins": comb_wins,
        "comb_losses": comb_trades - comb_wins,
        "comb_wr": comb_wr,
        "comb_gross": comb_gross,
        "comb_fees": comb_fees,
        "comb_net": comb_net,
        "comb_pf": comb_pf,
        "comb_stops": comb_stops,
        "comb_hedges": comb_hedges,
        "strat_totals": strat_totals,
        "coin_totals": coin_totals,
        "exit_totals": exit_totals,
        "results": results,
    }

    if verify_baseline:
        console.print("[bold cyan]===============================================================================[/bold cyan]")
        console.print("[bold yellow]VERIFYING DETERMINISTIC MATHEMATICAL BASELINE PARITY...[/bold yellow]")

        baseline_file = baseline_path or "audits/hype_76_sessions_benchmark.json"
        if os.path.exists(baseline_file):
            with open(baseline_file, "r") as f:
                baseline_data = json.load(f)
            p_base = baseline_data["strategy_performance"]["Portfolio_Total"]
            expected_trades = p_base["trades"]
            expected_net = p_base["net_pnl_usd"]
            expected_pf = p_base["profit_factor"]
            expected_stops = p_base["stop_losses"]
            expected_hedges = p_base["maker_hedges"]
        else:
            expected_trades = 873
            expected_net = 1103.18
            expected_pf = 3.10
            expected_stops = 16
            expected_hedges = 290

        console.print(f"Target Trades:       [bold]{expected_trades}[/bold] | Actual: [bold]{comb_trades}[/bold]")
        console.print(f"Target Net PnL:      [bold]${expected_net:+.2f}[/bold] | Actual: [bold]${comb_net:+.2f}[/bold]")
        console.print(f"Target Profit Factor:[bold]{expected_pf:.2f}[/bold] | Actual: [bold]{comb_pf:.2f}[/bold]")
        console.print(f"Target Stop Losses:  [bold]{expected_stops}[/bold] | Actual: [bold]{comb_stops}[/bold]")
        console.print(f"Target Maker Hedges: [bold]{expected_hedges}[/bold] | Actual: [bold]{comb_hedges}[/bold]")

        assert comb_trades == expected_trades, f"Parity Violation: Trades mismatch {comb_trades} != {expected_trades}"
        assert abs(comb_net - expected_net) < 0.05, f"Parity Violation: Net PnL mismatch {comb_net:.2f} != {expected_net:.2f}"
        assert abs(comb_pf - expected_pf) < 0.05, f"Parity Violation: Profit Factor mismatch {comb_pf:.2f} != {expected_pf:.2f}"
        assert comb_stops == expected_stops, f"Parity Violation: Stop losses mismatch {comb_stops} != {expected_stops}"
        assert comb_hedges == expected_hedges, f"Parity Violation: Maker hedges mismatch {comb_hedges} != {expected_hedges}"

        if os.path.exists(baseline_file) and "strategy_performance" in baseline_data:
            for s_name, expected_s in baseline_data["strategy_performance"].items():
                if s_name == "Portfolio_Total" or s_name not in strat_totals:
                    continue
                actual_s = strat_totals[s_name]
                assert actual_s["trades"] == expected_s["trades"], f"Parity Violation in {s_name}: trades {actual_s['trades']} != {expected_s['trades']}"
                assert abs(actual_s["net_pnl"] - expected_s["net_pnl_usd"]) < 1.0, f"Parity Violation in {s_name}: net_pnl {actual_s['net_pnl']:.2f} != {expected_s['net_pnl_usd']:.2f}"
                assert actual_s["stops"] == expected_s["stop_losses"], f"Parity Violation in {s_name}: stops {actual_s['stops']} != {expected_s['stop_losses']}"
                assert actual_s["hedges"] == expected_s["maker_hedges"], f"Parity Violation in {s_name}: hedges {actual_s['hedges']} != {expected_s['maker_hedges']}"

        if os.path.exists(baseline_file) and "exit_distribution" in baseline_data:
            for reason, expected_e in baseline_data["exit_distribution"].items():
                if reason in exit_totals:
                    actual_cnt = int(exit_totals[reason][0])
                    assert actual_cnt == expected_e["trades"], f"Exit Count Mismatch for {reason}: {actual_cnt} != {expected_e['trades']}"
                    actual_pnl = exit_totals[reason][1]
                    assert abs(actual_pnl - expected_e["net_pnl_usd"]) < 1.0, f"Exit PnL Mismatch for {reason}: {actual_pnl:.2f} != {expected_e['net_pnl_usd']:.2f}"

        console.print("\n[bold green]✓ 100% DETERMINISTIC MATHEMATICAL BASELINE PARITY VERIFIED![/bold green]")
        console.print("[bold cyan]===============================================================================[/bold cyan]\n")

    return summary_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Asset L2 Microstructure Backtest")
    parser.add_argument("--coins", type=str, default=None, help="Comma-separated coins to test (default: hype if --verify-baseline else btc,hype,eth,sol)")
    parser.add_argument("--max-files", type=int, default=0, help="Max files per coin (0 = all, or 76 if --verify-baseline)")
    parser.add_argument("--workers", type=int, default=0, help="Multiprocessing workers (0 = auto-detect all host CPU cores)")
    parser.add_argument("--verify-baseline", action="store_true", help="Assert deterministic parity against 76-session HYPE baseline")
    parser.add_argument("--baseline-file", type=str, default="audits/hype_76_sessions_benchmark.json", help="Path to baseline benchmark JSON")
    args = parser.parse_args()

    if args.verify_baseline:
        target_coins = [c.strip().lower() for c in args.coins.split(",") if c.strip()] if args.coins else ["hype"]
        max_files = args.max_files if args.max_files > 0 else 76
    else:
        target_coins = [c.strip().lower() for c in args.coins.split(",") if c.strip()] if args.coins else ["btc", "hype", "eth", "sol"]
        max_files = args.max_files

    summary = run_full_backtest(
        coins=target_coins,
        max_files_per_coin=max_files,
        workers=args.workers,
        verify_baseline=args.verify_baseline,
        baseline_path=args.baseline_file,
    )

    if args.verify_baseline:
        if summary and summary.get("comb_trades") == 873 and abs(summary.get("comb_net", 0.0) - 1103.18) < 0.05:
            sys.exit(0)
        else:
            sys.exit(1)
