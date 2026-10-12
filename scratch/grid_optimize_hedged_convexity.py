import glob
import math
import os
import sys
from collections import defaultdict, deque
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, List, Optional

sys.path.insert(0, ".")

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner
from signals.base import BaseSignal, SignalResult
from signals.vpin import VPINSignal


class RefinedHedgedConvexitySignal(BaseSignal):
    """Refined Hedged Convexity Signal with directional toxicity shielding,
    properly normalized multi-tier book convexity, and responsive defensive hedging.
    """

    def __init__(
        self,
        name: str = "HedgedConvexity",
        gamma_qr: float = 0.40,
        cvd_window_secs: float = 15.0,
        cvd_scale_btc: float = 2.5,
        hole_min_depth_btc: float = 6.0,
        w_touch: float = 0.35,
        w_d5: float = 0.30,
        w_slope: float = 0.20,
        w_n: float = 0.15,
        w_hole_bonus: float = 0.15,
        absorption_hurdle: float = 0.25,
    ):
        super().__init__(name)
        self.gamma_qr = gamma_qr
        self.cvd_window_secs = cvd_window_secs
        self.cvd_scale_btc = cvd_scale_btc
        self.hole_min_depth_btc = hole_min_depth_btc
        self.w_touch = w_touch
        self.w_d5 = w_d5
        self.w_slope = w_slope
        self.w_n = w_n
        self.w_hole_bonus = w_hole_bonus
        self.absorption_hurdle = absorption_hurdle

        self.vpin_signal = VPINSignal()
        self.depth_history = deque(maxlen=60)
        self.price_history = deque(maxlen=600)

    def compute(
        self,
        book,
        trades,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        now_ms = timestamp_ms or book.last_update_time_ms

        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0, timestamp_ms=now_ms)

        bids = book.bids
        asks = book.asks
        n_b = len(bids)
        n_a = len(asks)

        if n_b < 5 or n_a < 5:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0, timestamp_ms=now_ms)

        mid = book.mid_price
        scale = getattr(book, "notional_scale", 1.0)
        is_btc = (book.coin.upper() == "BTC")

        # 1. Touch Queue Depletion Ratio
        q_b1 = bids[0].sz
        q_a1 = asks[0].sz
        qr = math.log(max(q_b1, 0.005 * scale) / max(q_a1, 0.005 * scale))
        s_touch = math.tanh(self.gamma_qr * qr)

        # 2. Multi-Tier Resting Depth Imbalance (Levels 1-5)
        k_levels = min(5, n_b, n_a)
        d5_b = sum(bids[j].sz for j in range(k_levels))
        d5_a = sum(asks[j].sz for j in range(k_levels))
        denom_d5 = d5_b + d5_a
        s_d5 = (d5_b - d5_a) / max(denom_d5, 1e-6)

        # 3. Order Book Depth Slope / Convexity
        slope_b = (d5_b - q_b1) / max(k_levels - 1, 1)
        slope_a = (d5_a - q_a1) / max(k_levels - 1, 1)
        denom_slope = slope_b + slope_a
        s_slope = (slope_b - slope_a) / max(denom_slope, 1e-6)

        # 4. Order Count Dispersion Imbalance
        n5_b = sum(bids[j].n for j in range(k_levels))
        n5_a = sum(asks[j].n for j in range(k_levels))
        s_n = (n5_b - n5_a) / max(n5_b + n5_a, 1)

        # 5. Liquidity Hole Vacuum (Relative Depth Asymmetry + Opposing Depletion)
        ratio_b = d5_b / max(denom_d5, 1e-6)
        ratio_a = d5_a / max(denom_d5, 1e-6)
        min_depth = self.hole_min_depth_btc if is_btc else 0.5 * scale
        thin_thresh = 1.0 if is_btc else 0.4 * scale

        hole_ask = (ratio_b >= 0.72 and d5_b >= min_depth and d5_a < thin_thresh)
        hole_bid = (ratio_a >= 0.72 and d5_a >= min_depth and d5_b < thin_thresh)
        s_hole = 1.0 if hole_ask else (-1.0 if hole_bid else 0.0)

        # 6. Dual-Horizon Trade Flow Impulse (CVD)
        cvd_fast, _, _ = trades.get_cvd_in_window(self.cvd_window_secs)
        cvd_slow, _, _ = trades.get_cvd_in_window(60.0)
        s_cvd_fast = math.tanh(cvd_fast / max(self.cvd_scale_btc * scale, 0.1 * scale))
        s_cvd_slow = math.tanh(cvd_slow / max(4.0 * scale, 0.5 * scale))
        s_cvd = 0.65 * s_cvd_fast + 0.35 * s_cvd_slow

        # 7. Directional VPIN Toxicity & Hedge Risk Alert
        vpin_res = self.vpin_signal.compute(book, trades, now_ms)
        vpin_score = vpin_res.score  # Directional signed: [-1.0, +1.0]
        vpin_raw = vpin_res.raw_value  # Absolute toxicity ratio: [0.0, 1.0]

        # 8. Depth Fragility Tracking (Phantom Wall / Spoof Detection)
        self.depth_history.append((now_ms, d5_b, d5_a))
        wall_drop_b = False
        wall_drop_a = False
        if len(self.depth_history) >= 10:
            past_b = self.depth_history[0][1]
            past_a = self.depth_history[0][2]
            if past_b > 2.0 * scale and d5_b < past_b * 0.45:
                wall_drop_b = True
            if past_a > 2.0 * scale and d5_a < past_a * 0.45:
                wall_drop_a = True

        # Macro Trend Alignment (2-minute price drift)
        self.price_history.append((now_ms, mid))
        cutoff_ms = now_ms - 600_000
        while self.price_history and self.price_history[0][0] < cutoff_ms:
            self.price_history.popleft()

        trend_cutoff = now_ms - 120_000
        past_p = next((p for t, p in self.price_history if t >= trend_cutoff), self.price_history[0][1])
        trend_bps = ((mid - past_p) / past_p) * 10_000.0 if past_p > 0 else 0.0
        trend_score = math.tanh(trend_bps / 6.0)

        # 9. Composite Alpha Calculation
        is_bull_trap = (s_cvd > 0.20 and s_d5 < -self.absorption_hurdle)
        is_bear_trap = (s_cvd < -0.20 and s_d5 > self.absorption_hurdle)

        book_score = (
            self.w_touch * s_touch
            + self.w_d5 * s_d5
            + self.w_slope * s_slope
            + self.w_n * s_n
        )
        if s_hole != 0.0:
            book_score = max(-1.0, min(1.0, book_score + self.w_hole_bonus * s_hole))

        has_active_flow = abs(s_cvd) >= 0.18
        trend_aligned = (s_cvd > 0 and trend_score >= -0.10) or (s_cvd < 0 and trend_score <= 0.10)
        direction_agree = (book_score * s_cvd > 0) and has_active_flow and trend_aligned

        if is_bull_trap:
            raw_alpha = -0.40
            regime_flag = "BULL_ABSORPTION_TRAP"
            confidence = 0.75
        elif is_bear_trap:
            raw_alpha = 0.40
            regime_flag = "BEAR_ABSORPTION_TRAP"
            confidence = 0.75
        elif direction_agree:
            raw_alpha = 0.50 * book_score + 0.35 * s_cvd + 0.15 * trend_score
            confidence = 0.40 * abs(book_score) + 0.35 * abs(s_cvd) + 0.25 * abs(trend_score)
            regime_flag = "HEDGED_CONVEXITY"
        else:
            raw_alpha = max(-0.40, min(0.40, 0.25 * (book_score + s_cvd)))
            confidence = 0.20
            regime_flag = "WEAK_FLOW_DAMPENED"

        # 10. Intelligent Directional Toxicity Shield & Defensive Hedge Alert:
        # A. Adverse Toxic Flow: Protect passive maker entries from adverse selection
        if raw_alpha > 0 and vpin_score < -0.20:
            # Informed selling threatens maker buy order
            adverse_drag = min(1.0, abs(vpin_score) / 0.50)
            raw_alpha *= (1.0 - 0.50 * adverse_drag)
            # If adverse selling is acute, flip negative to arm defensive hedge
            if vpin_score < -0.45:
                raw_alpha = min(raw_alpha, vpin_score)
        elif raw_alpha < 0 and vpin_score > 0.20:
            # Informed buying threatens maker sell order
            adverse_drag = min(1.0, abs(vpin_score) / 0.50)
            raw_alpha *= (1.0 - 0.50 * adverse_drag)
            if vpin_score > 0.45:
                raw_alpha = max(raw_alpha, vpin_score)

        # B. Extreme Choppy Toxicity: When raw VPIN is extreme (>= 0.88 on BTC, >= 0.75 on altcoins)
        # without clear directional alignment, market orders are chaotic. Dampen alpha.
        toxic_ceiling = 0.88 if is_btc else 0.75
        if vpin_raw >= toxic_ceiling and abs(vpin_score) < 0.25:
            raw_alpha *= 0.65

        # C. Depth Fragility Shield: if resting wall was rapidly pulled (spoof decay), dampen alpha
        if (raw_alpha > 0 and wall_drop_b) or (raw_alpha < 0 and wall_drop_a):
            raw_alpha = max(-0.30, min(0.30, raw_alpha * 0.20))

        score = max(-1.0, min(1.0, raw_alpha))

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=raw_alpha,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={
                "s_touch": s_touch,
                "s_d5": s_d5,
                "s_slope": s_slope,
                "s_n": s_n,
                "s_hole": s_hole,
                "s_cvd": s_cvd,
                "vpin_score": vpin_score,
                "vpin_raw": vpin_raw,
                "wall_drop_b": wall_drop_b,
                "wall_drop_a": wall_drop_a,
                "regime_flag": regime_flag,
            },
        )


def replay_file_sim(args):
    fpath, coin, p = args
    cfg = AppConfig()
    cfg.market.coin = coin.upper()
    cfg.sample_rate_hz = 10.0
    cfg.strategies = StrategiesConfig.load("strategies.json")
    if "AdaptiveML" in cfg.strategies.alpha_signals:
        cfg.strategies.alpha_signals["AdaptiveML"].enabled = False

    st = cfg.strategies.execution_strategies["Hedged_Convexity"]
    st.enabled = True
    st.entry_threshold = p["entry_threshold"]
    st.min_volatility_bps = p["min_volatility_bps"]
    st.hedge_trigger_loss_bps = p["hedge_trigger_loss_bps"]
    st.hedge_reversal_threshold = p["hedge_reversal_threshold"]
    st.trailing_stop_activation_bps = p["trailing_stop_activation_bps"]
    st.trailing_stop_distance_bps = p["trailing_stop_distance_bps"]
    st.max_holding_time_secs = p["max_holding_time_secs"]
    st.take_profit_bps = p["take_profit_bps"]

    for s_name in cfg.strategies.execution_strategies:
        if s_name != "Hedged_Convexity":
            cfg.strategies.execution_strategies[s_name].enabled = False

    runner = L2EngineRunner(config=cfg, record_data=False, enable_audit=False)
    runner.alpha_model.signal_hedged = RefinedHedgedConvexitySignal()

    replay = L2ReplayEngine(fpath, speed_multiplier=20000.0)

    eval_interval_ms = 100
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
            runner.evaluator.record_step(now_ms, runner.book.mid_price, runner.book.best_bid, runner.book.best_ask, sub_sigs)

    if runner.book.is_valid:
        runner.evaluator.close_open_positions(runner.book.mid_price, runner.book.last_update_time_ms or 0, reason="SESSION_SHUTDOWN")

    st = runner.evaluator.strategies.get("Hedged_Convexity")
    trades = []
    if st and st.trades:
        for t in st.trades:
            trades.append({
                "side": t.side,
                "gross_pnl": t.gross_pnl_usd,
                "fees": t.fees_usd,
                "net_pnl": t.net_pnl_usd,
                "return_bps": t.return_bps,
                "exit_reason": t.exit_reason,
            })
    return trades


def run_param_eval(files, coin, params, max_workers=2):
    args_list = [(f, coin, params) for f in files]
    all_trades = []
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        for res in ex.map(replay_file_sim, args_list):
            all_trades.extend(res)

    total = len(all_trades)
    wins = sum(1 for t in all_trades if t["net_pnl"] > 0)
    gross = sum(t["gross_pnl"] for t in all_trades)
    fees = sum(t["fees"] for t in all_trades)
    net = sum(t["net_pnl"] for t in all_trades)
    wr = (wins / total * 100.0) if total else 0.0
    trails = sum(1 for t in all_trades if t["exit_reason"] == "TRAILING_STOP")
    hedges = sum(1 for t in all_trades if t["exit_reason"] == "DEFENSIVE_MAKER_HEDGE")
    stops = sum(1 for t in all_trades if t["exit_reason"] == "STOP_LOSS")
    tlimits = sum(1 for t in all_trades if t["exit_reason"] == "TIME_LIMIT")
    tp = sum(1 for t in all_trades if t["exit_reason"] == "TAKE_PROFIT")

    return {
        "total": total,
        "wins": wins,
        "wr": wr,
        "gross": gross,
        "fees": fees,
        "net": net,
        "trails": trails,
        "hedges": hedges,
        "stops": stops,
        "tlimits": tlimits,
        "tp": tp,
    }


if __name__ == "__main__":
    # Test on a representative subset of 12 files from BTC and 12 files from HYPE
    btc_files = sorted([f for f in glob.glob("data/btc/hl_btc_l2_*.jsonl") if "20261005" in f or "20261006" in f])[:14]
    hype_files = sorted([f for f in glob.glob("data/hype/hl_hype_l2_*.jsonl") if "20261005" in f or "20261006" in f])[:14]

    print("=" * 85)
    print(f"PARAM GRID TEST ON BTC ({len(btc_files)} files)")
    print("=" * 85)

    base_p = {
        "entry_threshold": 0.80,
        "min_volatility_bps": 3.8,
        "hedge_trigger_loss_bps": -8.5,
        "hedge_reversal_threshold": -0.60,
        "trailing_stop_activation_bps": 2.5,
        "trailing_stop_distance_bps": 1.0,
        "max_holding_time_secs": 180,
        "take_profit_bps": 18.0,
    }

    # Sweep entry threshold
    for eth in [0.80, 0.82, 0.85]:
        p = dict(base_p, entry_threshold=eth)
        res = run_param_eval(btc_files, "btc", p)
        print(f"BTC eth={eth:.2f}: {res['total']:3d} trs | Win: {res['wr']:5.1f}% | Gross: ${res['gross']:>+7.2f} | Fees: ${res['fees']:>6.2f} | Net: ${res['net']:>+7.2f} | Trails: {res['trails']} | Hedges: {res['hedges']} | Stops: {res['stops']} | TL: {res['tlimits']}")

    # Sweep volatility hurdle
    for vol in [3.8, 4.5, 5.0]:
        p = dict(base_p, entry_threshold=0.82, min_volatility_bps=vol)
        res = run_param_eval(btc_files, "btc", p)
        print(f"BTC vol={vol:.1f}: {res['total']:3d} trs | Win: {res['wr']:5.1f}% | Gross: ${res['gross']:>+7.2f} | Fees: ${res['fees']:>6.2f} | Net: ${res['net']:>+7.2f} | Trails: {res['trails']} | Hedges: {res['hedges']} | Stops: {res['stops']} | TL: {res['tlimits']}")

    # Sweep hedge trigger loss
    for h_loss, h_rev in [(-6.5, -0.50), (-7.5, -0.55), (-8.5, -0.60)]:
        p = dict(base_p, entry_threshold=0.82, min_volatility_bps=4.5, hedge_trigger_loss_bps=h_loss, hedge_reversal_threshold=h_rev)
        res = run_param_eval(btc_files, "btc", p)
        print(f"BTC hedge({h_loss}b, {h_rev}): {res['total']:3d} trs | Win: {res['wr']:5.1f}% | Gross: ${res['gross']:>+7.2f} | Fees: ${res['fees']:>6.2f} | Net: ${res['net']:>+7.2f} | Trails: {res['trails']} | Hedges: {res['hedges']} | Stops: {res['stops']} | TL: {res['tlimits']}")

    print("\n" + "=" * 85)
    print(f"PARAM GRID TEST ON HYPE ({len(hype_files)} files)")
    print("=" * 85)

    for eth in [0.80, 0.82, 0.85]:
        p = dict(base_p, entry_threshold=eth)
        res = run_param_eval(hype_files, "hype", p)
        print(f"HYPE eth={eth:.2f}: {res['total']:3d} trs | Win: {res['wr']:5.1f}% | Gross: ${res['gross']:>+7.2f} | Fees: ${res['fees']:>6.2f} | Net: ${res['net']:>+7.2f} | Trails: {res['trails']} | Hedges: {res['hedges']} | Stops: {res['stops']} | TL: {res['tlimits']}")

    for vol in [3.8, 4.5, 5.0]:
        p = dict(base_p, entry_threshold=0.82, min_volatility_bps=vol)
        res = run_param_eval(hype_files, "hype", p)
        print(f"HYPE vol={vol:.1f}: {res['total']:3d} trs | Win: {res['wr']:5.1f}% | Gross: ${res['gross']:>+7.2f} | Fees: ${res['fees']:>6.2f} | Net: ${res['net']:>+7.2f} | Trails: {res['trails']} | Hedges: {res['hedges']} | Stops: {res['stops']} | TL: {res['tlimits']}")
