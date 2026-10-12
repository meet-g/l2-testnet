"""Recursive Alpha Signal Auditor and Empirical Microstructure Validator.

Recursively evaluates signal correctness across multiple hierarchical levels:
Level 0: Microstructure primitives (OrderBook, TradeStream, CVD, VPIN)
Level 1: Atomic Alpha Signals (WOBI, VOI, MicroPrice, Absorption, VPIN, Sweep, QDAP)
Level 2: Composite & Strategy Signals (ConvexityCascade, HedgedConvexity, MomentumExpansion, CompositeAlpha, AdaptiveML)

Computes Pearson IC, Spearman Rank IC, Directional Hit Rates (Total & Active Move),
t-statistics, and quintile return monotonicity across [1s, 3s, 5s, 10s, 30s, 60s] horizons.
"""

import glob
import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from rich.console import Console
from rich.table import Table
from scipy import stats

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import AppConfig
from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.absorption import AbsorptionSignal
from signals.adaptive_alpha import AdaptiveAlphaSignal
from signals.composite_alpha import CompositeAlphaSignal
from signals.convexity_cascade import ConvexityCascadeSignal
from signals.hedged_convexity import HedgedConvexitySignal
from signals.microprice import MicroPriceSignal
from signals.momentum_expansion import MomentumExpansionSignal
from signals.qdap import QDAPSignal
from signals.sweep import SweepSignal
from signals.voi import VOISignal
from signals.vpin import VPINSignal
from signals.wobi import WOBISignal


def evaluate_signals_on_files(
    filepaths: List[str],
    sample_interval_ms: int = 250,
    horizons_secs: List[float] = [1.0, 3.0, 5.0, 10.0, 30.0, 60.0],
    max_samples: int = 50_000,
) -> Dict[str, Any]:
    console = Console()
    console.print(f"[bold cyan]Initializing Recursive Signal Audit across {len(filepaths)} files...[/bold cyan]")

    # Initialize all signals
    wobi_sig = WOBISignal()
    voi_sig = VOISignal()
    micro_sig = MicroPriceSignal()
    vpin_sig = VPINSignal()
    abs_sig = AbsorptionSignal()
    sweep_sig = SweepSignal()
    qdap_sig = QDAPSignal()
    adaptive_sig = AdaptiveAlphaSignal(mode="HYBRID")
    composite_sig = CompositeAlphaSignal()
    convexity_sig = ConvexityCascadeSignal()
    hedged_sig = HedgedConvexitySignal()
    mom_sig = MomentumExpansionSignal()

    all_signals = {
        "WOBI": wobi_sig,
        "VOI": voi_sig,
        "MicroPrice": micro_sig,
        "VPIN": vpin_sig,
        "Absorption": abs_sig,
        "Sweep": sweep_sig,
        "QDAP": qdap_sig,
        "AdaptiveML": adaptive_sig,
        "CompositeAlpha": composite_sig,
        "ConvexityCascade": convexity_sig,
        "HedgedConvexity": hedged_sig,
        "MomentumExpansion": mom_sig,
    }

    book = OrderBook()
    trades = TradeManager()

    raw_snapshots: List[Tuple[int, float, Dict[str, float]]] = []
    last_sample_ms = 0
    total_lines = 0

    for fpath in filepaths:
        console.print(f"  Streaming {os.path.basename(fpath)}...")
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                total_lines += 1
                try:
                    event = json.loads(line)
                except Exception:
                    continue

                ch = event.get("channel")
                dt = event.get("data")
                now_ms = event.get("recv_ts", int(time.time() * 1000))

                if ch == "l2Book":
                    book.update_from_raw(dt)
                elif ch == "trades":
                    trades.process_raw_trades(dt)
                elif ch == "activeAssetCtx":
                    book.update_asset_ctx(dt)

                if book.is_valid and (now_ms - last_sample_ms >= sample_interval_ms):
                    sig_scores = {}
                    for s_name, sig in all_signals.items():
                        res = sig.compute(book, trades, now_ms)
                        sig_scores[s_name] = float(res.score)

                    raw_snapshots.append((now_ms, book.mid_price, sig_scores))
                    last_sample_ms = now_ms

                    if len(raw_snapshots) >= max_samples:
                        break
        if len(raw_snapshots) >= max_samples:
            console.print(f"[yellow]Reached sample budget limit of {max_samples} snapshots.[/yellow]")
            break

    console.print(f"[bold green]Collected {len(raw_snapshots):,} synchronized snapshots. Aligning forward returns...[/bold green]")

    # Align snapshots with forward returns
    # For each horizon, build (signal_value, forward_return_bps)
    n_obs = len(raw_snapshots)
    signal_names = list(all_signals.keys())
    horizon_results: Dict[float, Dict[str, Any]] = {}

    for h_sec in horizons_secs:
        h_ms = int(h_sec * 1000)
        tolerance_ms = max(500, int(h_ms * 0.15))

        sig_arrays: Dict[str, List[float]] = {s: [] for s in signal_names}
        ret_list: List[float] = []

        j = 0
        for i in range(n_obs):
            t_i, p_i, sigs_i = raw_snapshots[i]
            target_t = t_i + h_ms

            while j < n_obs and raw_snapshots[j][0] < target_t:
                j += 1

            if j >= n_obs:
                break

            t_j, p_j, _ = raw_snapshots[j]
            if abs(t_j - target_t) <= tolerance_ms and p_i > 0:
                ret_bps = ((p_j - p_i) / p_i) * 10_000.0
                ret_list.append(ret_bps)
                for s in signal_names:
                    sig_arrays[s].append(sigs_i[s])

        rets = np.array(ret_list, dtype=np.float64)
        h_metrics: Dict[str, Any] = {}

        for s in signal_names:
            s_arr = np.array(sig_arrays[s], dtype=np.float64)
            n_pts = len(s_arr)
            if n_pts < 30 or np.std(s_arr) < 1e-7 or np.std(rets) < 1e-7:
                h_metrics[s] = {
                    "ic": 0.0,
                    "rank_ic": 0.0,
                    "t_stat": 0.0,
                    "p_val": 1.0,
                    "hit_rate_all": 50.0,
                    "hit_rate_active": 50.0,
                    "active_moves_pct": 0.0,
                    "long_spread_bps": 0.0,
                    "short_spread_bps": 0.0,
                    "decile_spread_bps": 0.0,
                }
                continue

            # Pearson IC & Spearman Rank IC
            ic, p_val = stats.pearsonr(s_arr, rets)
            rank_ic, _ = stats.spearmanr(s_arr, rets)
            t_stat = ic * math.sqrt((n_pts - 2) / max(1e-6, 1.0 - ic**2))

            # Hit rate calculations:
            # 1. Total hit rate (treating unchanged price as miss if sign != 0)
            hits_all = np.sign(s_arr) == np.sign(rets)
            hit_rate_all = float(np.mean(hits_all)) * 100.0

            # 2. Active hit rate: conditioned strictly on price actually moving
            active_mask = (np.abs(rets) > 0.01) & (np.abs(s_arr) > 0.05)
            if np.sum(active_mask) > 10:
                hits_active = np.sign(s_arr[active_mask]) == np.sign(rets[active_mask])
                hit_rate_active = float(np.mean(hits_active)) * 100.0
                active_pct = float(np.mean(np.abs(rets) > 0.01)) * 100.0
            else:
                hit_rate_active = 50.0
                active_pct = 0.0

            # Long conviction (score > 0.30) vs Short conviction (score < -0.30) average returns
            long_mask = s_arr > 0.30
            short_mask = s_arr < -0.30
            long_ret = float(np.mean(rets[long_mask])) if np.sum(long_mask) > 5 else 0.0
            short_ret = float(np.mean(rets[short_mask])) if np.sum(short_mask) > 5 else 0.0

            # Top decile (or top quintile) return minus bottom decile return
            q80 = np.percentile(s_arr, 80)
            q20 = np.percentile(s_arr, 20)
            top_ret = float(np.mean(rets[s_arr >= q80])) if np.sum(s_arr >= q80) > 5 else 0.0
            bot_ret = float(np.mean(rets[s_arr <= q20])) if np.sum(s_arr <= q20) > 5 else 0.0
            decile_spread = top_ret - bot_ret

            h_metrics[s] = {
                "samples": n_pts,
                "ic": float(ic),
                "rank_ic": float(rank_ic),
                "t_stat": float(t_stat),
                "p_val": float(p_val),
                "hit_rate_all": float(hit_rate_all),
                "hit_rate_active": float(hit_rate_active),
                "active_moves_pct": float(active_pct),
                "long_spread_bps": float(long_ret),
                "short_spread_bps": float(short_ret),
                "decile_spread_bps": float(decile_spread),
            }

        horizon_results[h_sec] = h_metrics

    # Cross-signal correlation matrix at snapshot level
    sig_matrix = np.zeros((len(raw_snapshots), len(signal_names)))
    for idx, (_, _, s_dict) in enumerate(raw_snapshots):
        for s_idx, s_name in enumerate(signal_names):
            sig_matrix[idx, s_idx] = s_dict[s_name]

    corr_matrix = np.corrcoef(sig_matrix.T)

    return {
        "sample_count": len(raw_snapshots),
        "total_lines": total_lines,
        "horizons": horizons_secs,
        "signal_names": signal_names,
        "horizon_results": horizon_results,
        "corr_matrix": corr_matrix.tolist(),
    }


def main():
    console = Console()
    data_dir = os.path.join("data", "btc") if os.path.isdir(os.path.join("data", "btc")) else "data"

    # Select representative files from the extended live session (02/10 and 03/10)
    # Pick a broad cross-section across different volatility regimes
    live_files = sorted(glob.glob(os.path.join(data_dir, "hl_btc_l2_20261002_*.jsonl")))
    live_files += sorted(glob.glob(os.path.join(data_dir, "hl_btc_l2_20261003_*.jsonl")))

    if not live_files:
        console.print("[bold red]No Oct 2/3 live session files found![/bold red]")
        sys.exit(1)

    # Sample 1 file every 3 hours to cover the entire 40+ hour span with high statistical power
    sample_files = live_files[::3]
    if live_files[-1] not in sample_files:
        sample_files.append(live_files[-1])

    console.print(f"[bold yellow]Analyzing {len(sample_files)} representative session files spanning the entire live period...[/bold yellow]")
    for f in sample_files:
        console.print(f"  - {os.path.basename(f)} ({os.path.getsize(f) / (1024*1024):.1f} MB)")

    res = evaluate_signals_on_files(
        sample_files,
        sample_interval_ms=300,
        horizons_secs=[1.0, 3.0, 5.0, 10.0, 30.0, 60.0],
        max_samples=40_000,
    )

    h_results = res["horizon_results"]
    sig_names = res["signal_names"]

    # Table 1: Information Coefficient (IC) across Horizons
    table_ic = Table(title="Recursive Alpha Evaluation: Information Coefficient (Pearson IC)", header_style="bold cyan")
    table_ic.add_column("Level / Signal Name", justify="left")
    for h in res["horizons"]:
        table_ic.add_column(f"{int(h)}s IC", justify="right")
    table_ic.add_column("Peak Horizon", justify="center", style="bold yellow")

    levels = {
        "WOBI": "L1 (Book)",
        "VOI": "L1 (Flow)",
        "MicroPrice": "L1 (FairVal)",
        "VPIN": "L1 (Toxicity)",
        "Absorption": "L1 (Iceberg)",
        "Sweep": "L1 (Impact)",
        "QDAP": "L1 (Queue)",
        "AdaptiveML": "L2 (ML Hybrid)",
        "ConvexityCascade": "L2 (Strategy)",
        "HedgedConvexity": "L2 (Strategy)",
        "MomentumExpansion": "L2 (Strategy)",
        "CompositeAlpha": "L2 (Ensemble)",
    }

    for s in sig_names:
        row = [f"{levels.get(s, '')} {s}"]
        peak_h = None
        peak_ic = -999.0
        for h in res["horizons"]:
            ic_val = h_results[h][s]["ic"]
            if ic_val > peak_ic:
                peak_ic = ic_val
                peak_h = f"{int(h)}s"
            color = "green" if ic_val > 0.05 else ("yellow" if ic_val > 0 else "red")
            row.append(f"[{color}]{ic_val:+.3f}[/{color}]")
        row.append(peak_h if peak_h else "-")
        table_ic.add_row(*row)

    console.print(table_ic)
    console.print("\n")

    # Table 2: Directional Hit Rate (Active Price Moves)
    table_hit = Table(title="Directional Predictive Edge: Active Hit Rate (% on Non-Zero Moves)", header_style="bold green")
    table_hit.add_column("Signal Name", justify="left")
    for h in res["horizons"]:
        table_hit.add_column(f"{int(h)}s Hit%", justify="right")
    table_hit.add_column("5s Decile Spread", justify="right", style="bold magenta")
    table_hit.add_column("Status / Edge Verdict", justify="left")

    for s in sig_names:
        row = [s]
        for h in res["horizons"]:
            hit_val = h_results[h][s]["hit_rate_active"]
            c = "bold green" if hit_val >= 55.0 else ("green" if hit_val >= 51.5 else "red")
            row.append(f"[{c}]{hit_val:.1f}%[/{c}]")

        d_spread = h_results[5.0][s]["decile_spread_bps"]
        spread_c = "green" if d_spread > 0.5 else ("yellow" if d_spread > 0 else "red")
        row.append(f"[{spread_c}]{d_spread:+.2f} bps[/{spread_c}]")

        # Verdict
        ic_5s = h_results[5.0][s]["ic"]
        t_5s = h_results[5.0][s]["t_stat"]
        if ic_5s > 0.10 and t_5s > 3.0:
            verdict = "[bold green]STRONG ALPHA (p<0.001)[/bold green]"
        elif ic_5s > 0.03:
            verdict = "[green]VALID POSITIVE EDGE[/green]"
        elif ic_5s < -0.02:
            verdict = "[bold red]INVERTED / COUNTER-PRODUCTIVE[/bold red]"
        else:
            verdict = "[yellow]WEAK / FLAT EDGE[/yellow]"
        row.append(verdict)
        table_hit.add_row(*row)

    console.print(table_hit)
    console.print("\n")

    # Save results to scratch json
    out_path = "scratch/recursive_signal_audit_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        # Convert float keys to string for JSON serialization
        serializable_h_results = {str(k): v for k, v in h_results.items()}
        json.dump(
            {
                "sample_count": res["sample_count"],
                "total_lines": res["total_lines"],
                "horizons": res["horizons"],
                "signal_names": sig_names,
                "horizon_results": serializable_h_results,
                "corr_matrix": res["corr_matrix"],
            },
            f,
            indent=2,
        )
    console.print(f"[bold green]Saved detailed audit JSON to: {out_path}[/bold green]")


if __name__ == "__main__":
    main()
