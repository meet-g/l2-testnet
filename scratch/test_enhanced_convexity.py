import glob
import math
import os
import re
import sys
from collections import defaultdict, deque
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, ".")

from config import AppConfig, StrategiesConfig
from engine.data_collector import L2ReplayEngine
from main import L2EngineRunner
from signals.base import BaseSignal, SignalResult
from signals.vpin import VPINSignal


class EnhancedConvexityCascadeSignal(BaseSignal):
    def __init__(self, name: str = "EnhancedConvexity"):
        super().__init__(name)
        self.vpin_signal = VPINSignal()
        self.depth_history = deque(maxlen=60)
        self.price_history = deque()

    def compute(self, book, trades, timestamp_ms=None):
        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        now_ms = timestamp_ms or book.last_update_time_ms
        mid = book.mid_price
        scale = getattr(book, "notional_scale", 1.0)
        self.price_history.append((now_ms, mid))
        cutoff_ms = now_ms - 600_000
        while self.price_history and self.price_history[0][0] < cutoff_ms:
            self.price_history.popleft()

        bids = book.bids
        asks = book.asks
        n_b = len(bids)
        n_a = len(asks)

        q_b1 = bids[0].sz if n_b > 0 else 0.01 * scale
        q_a1 = asks[0].sz if n_a > 0 else 0.01 * scale
        qr = math.log(max(q_b1, 0.005 * scale) / max(q_a1, 0.005 * scale))
        s_touch = math.tanh(0.40 * qr)

        k_levels = min(5, n_b, n_a)
        d5_b = sum(bids[j].sz for j in range(k_levels))
        d5_a = sum(asks[j].sz for j in range(k_levels))
        denom_d5 = d5_b + d5_a
        s_d5 = (d5_b - d5_a) / max(denom_d5, 1e-6)

        slope_b = (d5_b - q_b1) / max(k_levels - 1, 1)
        slope_a = (d5_a - q_a1) / max(k_levels - 1, 1)
        denom_slope = slope_b + slope_a
        s_slope = (slope_b - slope_a) / max(denom_slope, 1e-6)

        n5_b = sum(bids[j].n for j in range(k_levels))
        n5_a = sum(asks[j].n for j in range(k_levels))
        s_n = (n5_b - n5_a) / max(n5_b + n5_a, 1)

        hole_ask = (d5_a < 1.0 * scale and d5_b >= 6.0 * scale)
        hole_bid = (d5_b < 1.0 * scale and d5_a >= 6.0 * scale)
        s_hole = 1.0 if hole_ask else (-1.0 if hole_bid else 0.0)

        # Dual-Horizon CVD
        cvd_fast, _, _ = trades.get_cvd_in_window(15.0)
        cvd_slow, _, _ = trades.get_cvd_in_window(60.0)
        flow_fast = math.tanh(cvd_fast / max(1.5 * scale, 0.1 * scale))
        flow_slow = math.tanh(cvd_slow / max(4.0 * scale, 0.5 * scale))
        flow_score = 0.65 * flow_fast + 0.35 * flow_slow

        # 2-min Trend Alignment
        trend_cutoff = now_ms - 120_000
        past_price = next((p for t, p in self.price_history if t >= trend_cutoff), self.price_history[0][1])
        trend_score = math.tanh(((mid - past_price) / past_price * 10_000.0) / 6.0) if past_price > 0 else 0.0

        # Depth tracking & wall pull
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

        # Absorption check
        is_bull_trap = (flow_score > 0.15 and s_d5 < -0.20)
        is_bear_trap = (flow_score < -0.15 and s_d5 > 0.20)

        book_score = 0.35 * s_touch + 0.30 * s_d5 + 0.20 * s_slope + 0.15 * s_n + (0.25 * s_hole)

        has_active_flow = abs(flow_score) >= 0.18
        trend_aligned = (flow_score > 0 and trend_score >= -0.10) or (flow_score < 0 and trend_score <= 0.10)
        direction_agree = (book_score * flow_score > 0) and has_active_flow and trend_aligned

        if is_bull_trap:
            raw_alpha = -0.35
            confidence = 0.70
        elif is_bear_trap:
            raw_alpha = 0.35
            confidence = 0.70
        elif direction_agree:
            raw_alpha = 0.45 * book_score + 0.35 * flow_score + 0.20 * trend_score
            confidence = 0.40 * abs(book_score) + 0.35 * abs(flow_score) + 0.25 * abs(trend_score)
        else:
            raw_alpha = max(-0.40, min(0.40, 0.25 * (book_score + flow_score)))
            confidence = 0.20

        vpin_res = self.vpin_signal.compute(book, trades, now_ms)
        if vpin_res.metadata.get("is_toxic", False):
            raw_alpha = max(-0.30, min(0.30, raw_alpha * 0.15))

        if (raw_alpha > 0 and wall_drop_b) or (raw_alpha < 0 and wall_drop_a):
            raw_alpha = max(-0.30, min(0.30, raw_alpha * 0.20))

        score = max(-1.0, min(1.0, raw_alpha))
        return SignalResult(name=self.name, score=score, raw_value=raw_alpha, confidence=confidence, timestamp_ms=now_ms)


def replay_single_enhanced(fpath):
    cfg = AppConfig()
    cfg.market.coin = "BTC"
    cfg.sample_rate_hz = 10.0
    cfg.strategies = StrategiesConfig.load("strategies.json")
    for st in cfg.strategies.execution_strategies.values():
        st.enabled = False

    # Create dummy strategy for enhanced signal
    st_enh = cfg.strategies.execution_strategies["Convexity_Cascade"]
    st_enh.enabled = True
    st_enh.signal_key = "EnhancedConvexity"
    st_enh.entry_threshold = 0.80
    st_enh.min_volatility_bps = 3.8
    st_enh.trailing_stop_activation_bps = 2.5
    st_enh.trailing_stop_distance_bps = 1.0
    st_enh.max_holding_time_secs = 180

    runner = L2EngineRunner(config=cfg, record_data=False, enable_audit=False)
    runner.alpha_model.signals["EnhancedConvexity"] = EnhancedConvexityCascadeSignal()
    runner.evaluator.strategy_defs["Convexity_Cascade"] = ("EnhancedConvexity", "HEDGED_MAKER")
    runner.evaluator.strategies["Convexity_Cascade"].signal_key = "EnhancedConvexity"

    replay = L2ReplayEngine(fpath, speed_multiplier=10000.0)

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
            enh_res = runner.alpha_model.signals["EnhancedConvexity"].compute(runner.book, runner.trades, now_ms)
            sub_sigs = {"EnhancedConvexity": enh_res.score}
            runner.evaluator.record_step(now_ms, runner.book.mid_price, runner.book.best_bid, runner.book.best_ask, sub_sigs)

    if runner.book.is_valid:
        runner.evaluator.close_open_positions(runner.book.mid_price, runner.book.last_update_time_ms or 0, reason="SESSION_SHUTDOWN")

    trades = []
    st = runner.evaluator.strategies.get("Convexity_Cascade")
    if st and st.trades:
        for t in st.trades:
            trades.append({
                "gross_pnl": t.gross_pnl_usd,
                "fees": t.fees_usd,
                "net_pnl": t.net_pnl_usd,
                "exit_reason": t.exit_reason,
            })
    return trades


def main():
    files = sorted(glob.glob("data/btc/hl_btc_l2_20261002_*.jsonl") + glob.glob("data/btc/hl_btc_l2_20261004_*.jsonl"))
    print(f"Testing Enhanced Dual-Horizon Confluence Signal across {len(files)} files...")

    all_trades = []
    with ProcessPoolExecutor(max_workers=6) as ex:
        for res in ex.map(replay_single_enhanced, files):
            all_trades.extend(res)

    total = len(all_trades)
    wins = sum(1 for t in all_trades if t["net_pnl"] > 0)
    gross = sum(t["gross_pnl"] for t in all_trades)
    fees = sum(t["fees"] for t in all_trades)
    net = sum(t["net_pnl"] for t in all_trades)
    wr = (wins / total * 100.0) if total else 0.0
    trails = sum(1 for t in all_trades if t["exit_reason"] == "TRAILING_STOP")
    stops = sum(1 for t in all_trades if t["exit_reason"] == "STOP_LOSS")
    tlimits = sum(1 for t in all_trades if t["exit_reason"] == "TIME_LIMIT")

    print("\n" + "=" * 80)
    print(f"ENHANCED DUAL-HORIZON CONVEXITY RESULTS:")
    print(f"  Trades: {total:3d} | Win Rate: {wr:5.1f}% | Gross: ${gross:>+8.2f} | Fees: -${fees:>7.2f} | Net: ${net:>+8.2f} | Trails: {trails:2d} | Stops: {stops:2d} | TL: {tlimits:2d}")
    print("=" * 80)


if __name__ == "__main__":
    main()
