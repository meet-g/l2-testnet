"""Ensemble Composite Alpha Signal combining multi-factor L2 microstructure predictors."""

from typing import Dict, List, Optional

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.absorption import AbsorptionSignal
from signals.adaptive_alpha import AdaptiveAlphaSignal
from signals.base import BaseSignal, SignalResult
from signals.microprice import MicroPriceSignal
from signals.momentum_expansion import MomentumExpansionSignal
from signals.convexity_cascade import ConvexityCascadeSignal
from signals.hedged_convexity import HedgedConvexitySignal
from signals.qdap import QDAPSignal
from signals.sweep import SweepSignal
from signals.voi import VOISignal
from signals.wobi import WOBISignal
from signals.vpin import VPINSignal


class CompositeAlphaSignal(BaseSignal):
    """Ensemble Alpha Model combining all L2 microstructure indicators.
    
    Dynamically conditions factor weights based on the volatility and toxicity regime:
    1. Low-Volatility / Normal Regime:
       - Higher weight on static book imbalance (WOBI) and MicroPrice.
    2. High-Toxicity Regime (Surging VPIN):
       - Shifts weight to VOI, CVD Absorption, and aggressive flow direction.
    """

    def __init__(
        self,
        name: str = "CompositeAlpha",
        w_wobi: float = 0.25,
        w_voi: float = 0.25,
        w_microprice: float = 0.20,
        w_absorption: float = 0.15,
        w_vpin: float = 0.15,
        w_qdap: float = 0.20,
        enabled_signals: Optional[Dict[str, bool]] = None,
    ):
        super().__init__(name)
        self.w_wobi = w_wobi
        self.w_voi = w_voi
        self.w_microprice = w_microprice
        self.w_absorption = w_absorption
        self.w_vpin = w_vpin
        self.w_qdap = w_qdap
        self.enabled_signals = enabled_signals or {}

        # Sub-signal components
        self.signal_wobi = WOBISignal()
        self.signal_voi = VOISignal()
        self.signal_microprice = MicroPriceSignal()
        self.signal_vpin = VPINSignal()
        self.signal_absorption = AbsorptionSignal()
        self.signal_sweep = SweepSignal()
        self.signal_adaptive = AdaptiveAlphaSignal() if self.is_enabled("AdaptiveML") else None
        self.signal_qdap = QDAPSignal()
        self.signal_mom = MomentumExpansionSignal()
        self.signal_convexity = ConvexityCascadeSignal()
        self.signal_hedged = HedgedConvexitySignal()

    def is_enabled(self, sig_name: str) -> bool:
        """Returns True if the signal is enabled in configuration."""
        return self.enabled_signals.get(sig_name, True)

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        now_ms = timestamp_ms or book.last_update_time_ms

        res_wobi = self.signal_wobi.compute(book, trades, now_ms) if self.is_enabled("WOBI") else SignalResult("WOBI", 0.0, 0.0, {"enabled": False})
        res_voi = self.signal_voi.compute(book, trades, now_ms) if self.is_enabled("VOI") else SignalResult("VOI", 0.0, 0.0, {"enabled": False})
        res_mp = self.signal_microprice.compute(book, trades, now_ms) if self.is_enabled("MicroPrice") else SignalResult("MicroPrice", 0.0, 0.0, {"enabled": False})
        res_vpin = self.signal_vpin.compute(book, trades, now_ms) if self.is_enabled("VPIN") else SignalResult("VPIN", 0.0, 0.0, {"enabled": False})
        res_abs = self.signal_absorption.compute(book, trades, now_ms) if self.is_enabled("Absorption") else SignalResult("Absorption", 0.0, 0.0, {"enabled": False})
        res_sweep = self.signal_sweep.compute(book, trades, now_ms) if self.is_enabled("Sweep") else SignalResult("Sweep", 0.0, 0.0, {"enabled": False})
        if self.is_enabled("AdaptiveML"):
            if self.signal_adaptive is None:
                self.signal_adaptive = AdaptiveAlphaSignal()
            res_adaptive = self.signal_adaptive.compute(book, trades, now_ms)
        else:
            res_adaptive = SignalResult("AdaptiveML", 0.0, 0.0, {"enabled": False})
        res_qdap = self.signal_qdap.compute(book, trades, now_ms) if self.is_enabled("QDAP") else SignalResult("QDAP", 0.0, 0.0, {"enabled": False})
        res_mom = self.signal_mom.compute(book, trades, now_ms) if self.is_enabled("MomentumExpansion") else SignalResult("MomentumExpansion", 0.0, 0.0, {"enabled": False})
        res_convexity = self.signal_convexity.compute(book, trades, now_ms) if self.is_enabled("ConvexityCascade") else SignalResult("ConvexityCascade", 0.0, 0.0, {"enabled": False})
        res_hedged = self.signal_hedged.compute(book, trades, now_ms) if self.is_enabled("HedgedConvexity") else SignalResult("HedgedConvexity", 0.0, 0.0, {"enabled": False})

        # Attach enabled state to sub-signal metadata
        res_wobi.metadata["enabled"] = self.is_enabled("WOBI")
        res_voi.metadata["enabled"] = self.is_enabled("VOI")
        res_mp.metadata["enabled"] = self.is_enabled("MicroPrice")
        res_vpin.metadata["enabled"] = self.is_enabled("VPIN")
        res_abs.metadata["enabled"] = self.is_enabled("Absorption")
        res_sweep.metadata["enabled"] = self.is_enabled("Sweep")
        res_adaptive.metadata["enabled"] = self.is_enabled("AdaptiveML")
        res_qdap.metadata["enabled"] = self.is_enabled("QDAP")
        res_mom.metadata["enabled"] = self.is_enabled("MomentumExpansion")
        res_convexity.metadata["enabled"] = self.is_enabled("ConvexityCascade")
        res_hedged.metadata["enabled"] = self.is_enabled("HedgedConvexity")

        # Detect regime
        is_toxic = res_vpin.metadata.get("is_toxic", False) and self.is_enabled("VPIN")
        regime = "NORMAL"

        if is_toxic:
            regime = "TOXIC_EXPANSION"
            # In toxic flow, static book quotes are unreliable
            # Shift weight toward VOI, VPIN direction, and Absorption
            adj_wobi = 0.10 if self.is_enabled("WOBI") else 0.0
            adj_voi = 0.30 if self.is_enabled("VOI") else 0.0
            adj_mp = 0.10 if self.is_enabled("MicroPrice") else 0.0
            adj_abs = 0.25 if self.is_enabled("Absorption") else 0.0
            adj_vpin = 0.15 if self.is_enabled("VPIN") else 0.0
            adj_qdap = 0.10 if self.is_enabled("QDAP") else 0.0
        else:
            adj_wobi = self.w_wobi if self.is_enabled("WOBI") else 0.0
            adj_voi = self.w_voi if self.is_enabled("VOI") else 0.0
            adj_mp = self.w_microprice if self.is_enabled("MicroPrice") else 0.0
            adj_abs = self.w_absorption if self.is_enabled("Absorption") else 0.0
            adj_vpin = self.w_vpin if self.is_enabled("VPIN") else 0.0
            adj_qdap = self.w_qdap if self.is_enabled("QDAP") else 0.0

        total_weight = adj_wobi + adj_voi + adj_mp + adj_abs + adj_vpin + adj_qdap

        if total_weight > 0:
            composite_score = (
                adj_wobi * res_wobi.score
                + adj_voi * res_voi.score
                + adj_mp * res_mp.score
                + adj_abs * res_abs.score
                + adj_vpin * res_vpin.score
                + adj_qdap * res_qdap.score
            ) / total_weight
        else:
            composite_score = 0.0

        # Overlay sweep kick if active and enabled
        if self.is_enabled("Sweep") and abs(res_sweep.score) > 0.3:
            composite_score = 0.7 * composite_score + 0.3 * res_sweep.score

        # Bound [-1.0, 1.0]
        composite_score = max(-1.0, min(1.0, composite_score))

        # Overall confidence across enabled signals
        enabled_confs = [
            res.confidence for name, res in [
                ("WOBI", res_wobi),
                ("VOI", res_voi),
                ("MicroPrice", res_mp),
                ("Absorption", res_abs),
                ("VPIN", res_vpin),
                ("QDAP", res_qdap),
            ] if self.is_enabled(name)
        ]
        avg_confidence = (sum(enabled_confs) / len(enabled_confs)) if enabled_confs else 0.5

        return SignalResult(
            name=self.name,
            score=composite_score,
            raw_value=composite_score,
            confidence=avg_confidence,
            timestamp_ms=now_ms,
            metadata={
                "regime": regime,
                "sub_signals": {
                    "WOBI": res_wobi,
                    "VOI": res_voi,
                    "MicroPrice": res_mp,
                    "VPIN": res_vpin,
                    "Absorption": res_abs,
                    "Sweep": res_sweep,
                    "AdaptiveML": res_adaptive,
                    "QDAP": res_qdap,
                    "MomentumExpansion": res_mom,
                    "ConvexityCascade": res_convexity,
                    "HedgedConvexity": res_hedged,
                },
            },
        )
