"""Comprehensive Trade Audit & Session Tracking Module for Hyperliquid L2 Engine.

Ensures all trades placed for each individual strategy (simulated paper trading or real
exchange orders) are individually auditable per trading session, with persistent
per-strategy CSVs, master session CSVs, JSONL event streams, and detailed audit reports.
"""

from dataclasses import asdict, dataclass, field
import atexit
import csv
import json
import logging
import os
import shutil
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("SessionAuditor")


@dataclass
class AuditableTrade:
    """Individual auditable trade record for a strategy."""
    trade_id: str
    session_id: str
    strategy_name: str
    coin: str = "BTC"
    network: str = "Testnet"
    is_live: bool = False
    side: str = "LONG"  # 'LONG' or 'SHORT'
    execution_type: str = "MAKER"  # 'MAKER' or 'SMART_TAKER'
    
    # Timing
    entry_time_iso: str = ""
    entry_time_ms: int = 0
    exit_time_iso: str = ""
    exit_time_ms: int = 0
    holding_time_secs: float = 0.0
    
    # Sizing & Pricing
    size_btc: float = 0.0
    notional_usd: float = 0.0
    entry_price: float = 0.0
    exit_price: float = 0.0
    
    # Signals
    entry_signal_score: float = 0.0
    exit_signal_score: float = 0.0
    
    # PnL & Fees
    gross_pnl_usd: float = 0.0
    fee_entry_usd: float = 0.0
    fee_exit_usd: float = 0.0
    total_fees_usd: float = 0.0
    net_pnl_usd: float = 0.0
    return_bps: float = 0.0
    
    # Execution & Risk metrics
    exit_reason: str = "TIME_LIMIT"
    peak_unrealized_bps: float = 0.0
    trough_unrealized_bps: float = 0.0
    strategy_equity_after: float = 10_000.0
    strategy_drawdown_after: float = 0.0
    order_id: Optional[int] = None
    notes: str = ""

    def to_csv_row(self) -> Dict[str, Any]:
        """Returns ordered dict suitable for CSV output."""
        return {
            "trade_id": self.trade_id,
            "session_id": self.session_id,
            "strategy_name": self.strategy_name,
            "coin": self.coin,
            "network": self.network,
            "is_live": "YES" if self.is_live else "NO",
            "side": self.side,
            "execution_type": self.execution_type,
            "entry_time": self.entry_time_iso,
            "entry_price": f"{self.entry_price:.2f}",
            "size_btc": f"{self.size_btc:.4f}",
            "notional_usd": f"{self.notional_usd:.2f}",
            "entry_signal": f"{self.entry_signal_score:+.3f}",
            "exit_time": self.exit_time_iso,
            "exit_price": f"{self.exit_price:.2f}",
            "exit_signal": f"{self.exit_signal_score:+.3f}",
            "holding_secs": f"{self.holding_time_secs:.2f}",
            "gross_pnl_usd": f"{self.gross_pnl_usd:+.2f}",
            "entry_fee_usd": f"{self.fee_entry_usd:+.4f}",
            "exit_fee_usd": f"{self.fee_exit_usd:+.4f}",
            "total_fees_usd": f"{self.total_fees_usd:+.4f}",
            "net_pnl_usd": f"{self.net_pnl_usd:+.2f}",
            "return_bps": f"{self.return_bps:+.2f}",
            "exit_reason": self.exit_reason,
            "peak_mfe_bps": f"{self.peak_unrealized_bps:+.2f}",
            "trough_mae_bps": f"{self.trough_unrealized_bps:+.2f}",
            "strategy_equity_after": f"{self.strategy_equity_after:.2f}",
            "order_id": str(self.order_id or ""),
            "notes": self.notes,
        }


@dataclass
class LiveOrderAuditRecord:
    """Record of real order submitted to Hyperliquid exchange."""
    event_id: str
    session_id: str
    timestamp_iso: str
    timestamp_ms: int
    strategy_name: str
    coin: str
    network: str
    event_type: str  # 'SUBMIT', 'RESTING', 'FILLED', 'CANCEL', 'REJECTED'
    side: str  # 'BUY' or 'SELL'
    size_btc: float
    price: float
    notional_usd: float
    tif: str  # 'Alo' or 'Gtc'
    order_id: Optional[int] = None
    response_status: str = "ok"
    fill_price: Optional[float] = None
    fill_size: Optional[float] = None
    error_message: str = ""
    signal_score: float = 0.0

    def to_csv_row(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp_iso,
            "strategy_name": self.strategy_name,
            "coin": self.coin,
            "network": self.network,
            "event_type": self.event_type,
            "side": self.side,
            "size_btc": f"{self.size_btc:.4f}",
            "price": f"{self.price:.2f}",
            "notional_usd": f"{self.notional_usd:.2f}",
            "tif": self.tif,
            "order_id": str(self.order_id or ""),
            "status": self.response_status,
            "fill_price": f"{self.fill_price:.2f}" if self.fill_price is not None else "",
            "fill_size": f"{self.fill_size:.4f}" if self.fill_size is not None else "",
            "error": self.error_message,
            "signal_score": f"{self.signal_score:+.3f}",
        }


CSV_TRADE_FIELDNAMES = [
    "trade_id", "session_id", "strategy_name", "coin", "network", "is_live",
    "side", "execution_type", "entry_time", "entry_price", "size_btc",
    "notional_usd", "entry_signal", "exit_time", "exit_price", "exit_signal",
    "holding_secs", "gross_pnl_usd", "entry_fee_usd", "exit_fee_usd",
    "total_fees_usd", "net_pnl_usd", "return_bps", "exit_reason",
    "peak_mfe_bps", "trough_mae_bps", "strategy_equity_after", "order_id", "notes"
]

CSV_LIVE_ORDER_FIELDNAMES = [
    "event_id", "session_id", "timestamp", "strategy_name", "coin", "network",
    "event_type", "side", "size_btc", "price", "notional_usd", "tif",
    "order_id", "status", "fill_price", "fill_size", "error", "signal_score"
]


class SessionAuditor:
    """Manages immutable, structured session trade logs and per-strategy audits."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        audit_dir: str = "audits",
        coin: str = "BTC",
        network: str = "Testnet",
        is_live_mode: bool = False,
        enabled_strategies: Optional[List[str]] = None,
        lazy_init: Optional[bool] = None,
    ):
        self.audit_dir = audit_dir
        self.coin = coin
        self.network = network
        self.is_live_mode = is_live_mode
        self.enabled_strategies = enabled_strategies or []
        # In live mode, initialize eagerly so live monitoring can observe it immediately.
        # In simulation / replay mode, initialize lazily upon first trade recorded.
        self.lazy_init = (not is_live_mode) if lazy_init is None else lazy_init

        # Generate unique collision-proof session timestamp and ID (includes ms + uuid nonce)
        now = time.time()
        time_tag = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
        millis = int((now % 1) * 1000)
        nonce = uuid.uuid4().hex[:4]
        self.start_time_unix = now
        self.start_time_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
        self.session_id = session_id or f"session_{time_tag}_{millis:03d}_{nonce}"

        # Session directories
        self.session_path = os.path.join(self.audit_dir, self.session_id)
        self.strategies_path = os.path.join(self.session_path, "strategies")

        # File paths
        self.manifest_file = os.path.join(self.session_path, "session_manifest.json")
        self.master_csv_file = os.path.join(self.session_path, "all_trades.csv")
        self.audit_jsonl_file = os.path.join(self.session_path, "trades_audit.jsonl")
        self.live_orders_csv_file = os.path.join(self.session_path, "live_orders.csv")
        self.report_markdown_file = os.path.join(self.session_path, "session_audit_report.md")

        # In-memory tracking
        self.trade_counter = 0
        self.event_counter = 0
        self.trades: List[AuditableTrade] = []
        self.trades_by_strategy: Dict[str, List[AuditableTrade]] = {}
        self.live_order_events: List[LiveOrderAuditRecord] = []
        self.live_exchange_reconciliation: Optional[Dict[str, Any]] = None

        # Track per-strategy CSV file handles to avoid reopening
        self._strategy_csv_initialized: set = set()
        self._initialized: bool = False
        self._status: str = "RUNNING"

        # Register cleanup on abnormal/normal process exit
        try:
            atexit.register(self._atexit_handler)
        except Exception:
            pass

        if not self.lazy_init:
            self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """Lazily creates session directories and master files on disk upon first write."""
        if self._initialized:
            return
        os.makedirs(self.strategies_path, exist_ok=True)
        self._init_master_files()
        self._update_latest_pointer()
        self._initialized = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_session()

    def _atexit_handler(self) -> None:
        """Flushes and finalizes session on process termination if not already closed."""
        if self._initialized and self._status != "CLOSED":
            try:
                self.close_session()
            except Exception:
                pass

    def _init_master_files(self) -> None:
        """Initializes master CSV headers if not already present."""
        if not os.path.exists(self.master_csv_file):
            try:
                with open(self.master_csv_file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=CSV_TRADE_FIELDNAMES)
                    writer.writeheader()
            except Exception as e:
                logger.error(f"Failed to create master CSV {self.master_csv_file}: {e}")

        if self.is_live_mode and not os.path.exists(self.live_orders_csv_file):
            try:
                with open(self.live_orders_csv_file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=CSV_LIVE_ORDER_FIELDNAMES)
                    writer.writeheader()
            except Exception as e:
                logger.error(f"Failed to create live orders CSV {self.live_orders_csv_file}: {e}")

        # Write initial session manifest
        self._save_manifest(status="RUNNING")

    def _get_strategy_csv_file(self, strategy_name: str) -> str:
        """Returns path to the strategy's dedicated CSV file."""
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in strategy_name)
        return os.path.join(self.strategies_path, f"{safe_name}.csv")

    def _init_strategy_csv(self, strategy_name: str) -> str:
        """Initializes strategy-specific CSV with headers."""
        self._ensure_initialized()
        filepath = self._get_strategy_csv_file(strategy_name)
        if strategy_name not in self._strategy_csv_initialized:
            if not os.path.exists(filepath):
                try:
                    with open(filepath, "w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=CSV_TRADE_FIELDNAMES)
                        writer.writeheader()
                except Exception as e:
                    logger.error(f"Failed to init strategy CSV {filepath}: {e}")
            self._strategy_csv_initialized.add(strategy_name)
        return filepath

    def _update_latest_pointer(self) -> None:
        """Saves a pointer text file to quickly locate the latest active session."""
        try:
            latest_ptr = os.path.join(self.audit_dir, "latest_session_id.txt")
            with open(latest_ptr, "w", encoding="utf-8") as f:
                f.write(self.session_id)
        except Exception as e:
            logger.debug(f"Could not update latest_session_id.txt: {e}")

    def generate_trade_id(self, strategy_name: str) -> str:
        """Generates a human-auditable trade ID."""
        self.trade_counter += 1
        prefix = "".join(c for c in strategy_name if c.isupper()) or "TRD"
        return f"{prefix}-{self.trade_counter:04d}"

    def record_trade(
        self,
        strategy_name: str,
        side: str,
        execution_type: str,
        entry_time_ms: int,
        exit_time_ms: int,
        entry_price: float,
        exit_price: float,
        size_btc: float,
        gross_pnl_usd: float,
        entry_fee_usd: float,
        exit_fee_usd: float,
        net_pnl_usd: float,
        return_bps: float,
        exit_reason: str,
        entry_signal_score: float = 0.0,
        exit_signal_score: float = 0.0,
        peak_unrealized_bps: float = 0.0,
        trough_unrealized_bps: float = 0.0,
        strategy_equity_after: float = 10_000.0,
        strategy_drawdown_after: float = 0.0,
        order_id: Optional[int] = None,
        notes: str = "",
    ) -> AuditableTrade:
        """Records a completed trade into the session audit system.
        
        Appends immediately to:
        1. Master session CSV (`all_trades.csv`)
        2. Per-strategy dedicated CSV (`strategies/{strategy_name}.csv`)
        3. Detailed JSONL event stream (`trades_audit.jsonl`)
        """
        trade_id = self.generate_trade_id(strategy_name)
        self._ensure_initialized()
        entry_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(entry_time_ms / 1000.0))
        exit_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(exit_time_ms / 1000.0))
        hold_secs = max(0.001, (exit_time_ms - entry_time_ms) / 1000.0)
        notional = size_btc * entry_price
        total_fees = entry_fee_usd + exit_fee_usd

        trade = AuditableTrade(
            trade_id=trade_id,
            session_id=self.session_id,
            strategy_name=strategy_name,
            coin=self.coin,
            network=self.network,
            is_live=self.is_live_mode,
            side=side,
            execution_type=execution_type,
            entry_time_iso=entry_iso,
            entry_time_ms=entry_time_ms,
            exit_time_iso=exit_iso,
            exit_time_ms=exit_time_ms,
            holding_time_secs=hold_secs,
            size_btc=size_btc,
            notional_usd=notional,
            entry_price=entry_price,
            exit_price=exit_price,
            entry_signal_score=entry_signal_score,
            exit_signal_score=exit_signal_score,
            gross_pnl_usd=gross_pnl_usd,
            fee_entry_usd=entry_fee_usd,
            fee_exit_usd=exit_fee_usd,
            total_fees_usd=total_fees,
            net_pnl_usd=net_pnl_usd,
            return_bps=return_bps,
            exit_reason=exit_reason,
            peak_unrealized_bps=peak_unrealized_bps,
            trough_unrealized_bps=trough_unrealized_bps,
            strategy_equity_after=strategy_equity_after,
            strategy_drawdown_after=strategy_drawdown_after,
            order_id=order_id,
            notes=notes,
        )

        # In-memory store
        self.trades.append(trade)
        if strategy_name not in self.trades_by_strategy:
            self.trades_by_strategy[strategy_name] = []
        self.trades_by_strategy[strategy_name].append(trade)

        csv_row = trade.to_csv_row()

        # 1. Append to Master CSV
        try:
            with open(self.master_csv_file, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_TRADE_FIELDNAMES)
                writer.writerow(csv_row)
        except Exception as e:
            logger.error(f"Failed to append trade to {self.master_csv_file}: {e}")

        # 2. Append to Strategy-Specific CSV
        try:
            strat_csv = self._init_strategy_csv(strategy_name)
            with open(strat_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_TRADE_FIELDNAMES)
                writer.writerow(csv_row)
        except Exception as e:
            logger.error(f"Failed to append trade to strategy CSV: {e}")

        # 3. Append to JSONL Audit Log
        try:
            with open(self.audit_jsonl_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(trade)) + "\n")
        except Exception as e:
            logger.error(f"Failed to append to JSONL {self.audit_jsonl_file}: {e}")

        # Note: Master CSV mirroring to latest_session_all_trades.csv is executed at session close
        # to prevent O(N) file-copy thrashing and Windows file locking across high-frequency trades.

        return trade

    def record_live_order_event(
        self,
        strategy_name: str,
        event_type: str,
        side: str,
        size_btc: float,
        price: float,
        tif: str = "Alo",
        order_id: Optional[int] = None,
        status: str = "ok",
        fill_price: Optional[float] = None,
        fill_size: Optional[float] = None,
        error_message: str = "",
        signal_score: float = 0.0,
    ) -> LiveOrderAuditRecord:
        """Records an individual live Hyperliquid exchange order event."""
        self._ensure_initialized()
        self.event_counter += 1
        now = time.time()
        event_id = f"EVT-{self.event_counter:04d}"
        iso_str = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
        notional = size_btc * price

        rec = LiveOrderAuditRecord(
            event_id=event_id,
            session_id=self.session_id,
            timestamp_iso=iso_str,
            timestamp_ms=int(now * 1000),
            strategy_name=strategy_name,
            coin=self.coin,
            network=self.network,
            event_type=event_type,
            side=side,
            size_btc=size_btc,
            price=price,
            notional_usd=notional,
            tif=tif,
            order_id=order_id,
            response_status=status,
            fill_price=fill_price,
            fill_size=fill_size,
            error_message=error_message,
            signal_score=signal_score,
        )

        self.live_order_events.append(rec)

        # Append to live orders CSV
        try:
            with open(self.live_orders_csv_file, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_LIVE_ORDER_FIELDNAMES)
                writer.writerow(rec.to_csv_row())
        except Exception as e:
            logger.error(f"Failed to append to live orders CSV: {e}")

    def reconcile_live_exchange_fills(self, fills: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Reconciles real on-chain fills from Hyperliquid clearinghouse API with this session."""
        self._ensure_initialized()
        session_start_ms = int(self.start_time_unix * 1000)
        # Filter fills that occurred on or after this session's start
        sess_fills = [
            f for f in fills
            if f.get("coin") == self.coin and f.get("time", 0) >= session_start_ms
        ]

        # Calculate exact on-chain accounting numbers
        tot_closed_pnl = sum(float(f.get("closedPnl", 0.0)) for f in sess_fills)
        tot_fees = sum(float(f.get("fee", 0.0)) for f in sess_fills)
        net_realized = tot_closed_pnl - tot_fees
        tot_vol = sum(float(f.get("sz", 0.0)) for f in sess_fills)
        maker_count = sum(1 for f in sess_fills if not f.get("crossed", False))
        taker_count = sum(1 for f in sess_fills if f.get("crossed", False))

        # Write real fills CSV
        csv_file = os.path.join(self.session_path, "live_exchange_fills.csv")
        fieldnames = [
            "tid", "time_iso", "time_ms", "coin", "dir", "side", "size_btc",
            "price", "notional_usd", "crossed", "fee_usd", "fee_token",
            "closed_pnl_usd", "oid", "hash"
        ]
        try:
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for f in sess_fills:
                    t_ms = f.get("time", 0)
                    t_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t_ms / 1000.0))
                    sz = float(f.get("sz", 0.0))
                    px = float(f.get("px", 0.0))
                    writer.writerow({
                        "tid": str(f.get("tid", "")),
                        "time_iso": t_iso,
                        "time_ms": str(t_ms),
                        "coin": str(f.get("coin", self.coin)),
                        "dir": str(f.get("dir", "")),
                        "side": "BUY" if f.get("side") == "B" else "SELL",
                        "size_btc": f"{sz:.4f}",
                        "price": f"{px:.2f}",
                        "notional_usd": f"{sz * px:.2f}",
                        "crossed": "TAKER" if f.get("crossed") else "MAKER",
                        "fee_usd": f"{float(f.get('fee', 0.0)):.6f}",
                        "fee_token": str(f.get("feeToken", "USDC")),
                        "closed_pnl_usd": f"{float(f.get('closedPnl', 0.0)):+.4f}",
                        "oid": str(f.get("oid", "")),
                        "hash": str(f.get("hash", "")),
                    })
        except Exception:
            pass

        self.live_exchange_reconciliation = {
            "reconciled": True,
            "total_fills": len(sess_fills),
            "maker_fills": maker_count,
            "taker_fills": taker_count,
            "total_volume_btc": round(tot_vol, 4),
            "real_closed_pnl_usd": round(tot_closed_pnl, 4),
            "real_fees_paid_usd": round(tot_fees, 4),
            "real_net_realized_usd": round(net_realized, 4),
            "fills_csv": "live_exchange_fills.csv",
        }

        # Update manifest and audit report with real on-chain reconciliation
        self._save_manifest(status="CLOSED")
        self.generate_audit_report()

        return self.live_exchange_reconciliation

    def get_strategy_trades(self, strategy_name: str) -> List[AuditableTrade]:
        """Returns all trades executed for a specific strategy."""
        return self.trades_by_strategy.get(strategy_name, [])

    def calculate_strategy_stats(self, strategy_name: str) -> Dict[str, Any]:
        """Calculates audit summary statistics for a given strategy."""
        trades = self.trades_by_strategy.get(strategy_name, [])
        if not trades:
            return {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate_pct": 0.0,
                "gross_pnl_usd": 0.0,
                "total_fees_usd": 0.0,
                "net_pnl_usd": 0.0,
                "profit_factor": 0.0,
                "avg_trade_pnl": 0.0,
                "avg_return_bps": 0.0,
                "max_drawdown_usd": 0.0,
                "total_volume_btc": 0.0,
            }

        wins = [t for t in trades if t.net_pnl_usd > 0]
        losses = [t for t in trades if t.net_pnl_usd < 0]
        gross_win = sum(t.net_pnl_usd for t in wins)
        gross_loss = abs(sum(t.net_pnl_usd for t in losses))
        profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99.9 if gross_win > 0 else 0.0)

        net_pnl = sum(t.net_pnl_usd for t in trades)
        gross_pnl = sum(t.gross_pnl_usd for t in trades)
        total_fees = sum(t.total_fees_usd for t in trades)
        total_vol = sum(t.size_btc for t in trades)
        avg_ret = sum(t.return_bps for t in trades) / len(trades)

        return {
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": (len(wins) / len(trades)) * 100.0,
            "gross_pnl_usd": gross_pnl,
            "total_fees_usd": total_fees,
            "net_pnl_usd": net_pnl,
            "profit_factor": profit_factor,
            "avg_trade_pnl": net_pnl / len(trades),
            "avg_return_bps": avg_ret,
            "max_drawdown_usd": max((t.strategy_drawdown_after for t in trades), default=0.0),
            "total_volume_btc": total_vol,
        }

    def _save_manifest(self, status: str = "CLOSED") -> None:
        """Saves session metadata manifest to JSON."""
        now = time.time()
        end_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
        duration = now - self.start_time_unix

        wins = [t for t in self.trades if t.net_pnl_usd > 0]
        losses = [t for t in self.trades if t.net_pnl_usd < 0]
        gross_win = sum(t.net_pnl_usd for t in wins)
        gross_loss = abs(sum(t.net_pnl_usd for t in losses))
        profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99.9 if gross_win > 0 else 0.0)

        total_net_pnl = sum(t.net_pnl_usd for t in self.trades)
        total_fees = sum(t.total_fees_usd for t in self.trades)

        # Per-strategy audit metrics
        strat_metrics = {}
        all_strat_names = set(self.enabled_strategies).union(self.trades_by_strategy.keys())
        for s_name in all_strat_names:
            st = self.calculate_strategy_stats(s_name)
            st["csv_file"] = f"strategies/{s_name}.csv"
            strat_metrics[s_name] = st

        manifest = {
            "session_id": self.session_id,
            "status": status,
            "start_time_iso": self.start_time_iso,
            "end_time_iso": end_iso,
            "duration_secs": round(duration, 1),
            "coin": self.coin,
            "network": self.network,
            "is_live_mode": self.is_live_mode,
            "enabled_strategies": self.enabled_strategies,
            "session_summary": {
                "total_trades": len(self.trades),
                "winning_trades": len(wins),
                "losing_trades": len(losses),
                "win_rate_pct": round((len(wins) / len(self.trades)) * 100.0, 1) if self.trades else 0.0,
                "gross_pnl_usd": round(sum(t.gross_pnl_usd for t in self.trades), 2),
                "total_fees_usd": round(total_fees, 4),
                "net_pnl_usd": round(total_net_pnl, 2),
                "profit_factor": round(profit_factor, 2),
                "total_volume_btc": round(sum(t.size_btc for t in self.trades), 4),
            },
            "strategies": strat_metrics,
            "files": {
                "master_csv": "all_trades.csv",
                "audit_jsonl": "trades_audit.jsonl",
                "session_report": "session_audit_report.md",
                "live_orders_csv": "live_orders.csv" if self.is_live_mode else None,
                "live_exchange_fills_csv": "live_exchange_fills.csv" if self.live_exchange_reconciliation else None,
            },
        }

        if self.live_exchange_reconciliation:
            manifest["live_exchange_reconciliation"] = self.live_exchange_reconciliation

        with open(self.manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    def generate_audit_report(self) -> str:
        """Generates comprehensive Markdown session audit report breaking down every strategy."""
        now = time.time()
        end_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        duration = now - self.start_time_unix

        lines = [
            f"# Trading Session Audit Report: `{self.session_id}`\n\n",
            f"- **Session ID**: `{self.session_id}`\n",
            f"- **Target Asset**: `{self.coin}-PERP`\n",
            f"- **Network**: Hyperliquid `{self.network}`\n",
            f"- **Execution Mode**: {'REAL EXCHANGE ORDERS (LIVE)' if self.is_live_mode else 'PAPER TRADING SIMULATION'}\n",
            f"- **Session Start**: {self.start_time_iso}\n",
            f"- **Session End**: {end_iso}\n",
            f"- **Duration**: {int(duration // 60)}m {int(duration % 60)}s ({duration:.1f}s)\n",
            f"- **Master CSV**: [`all_trades.csv`](all_trades.csv)\n",
            f"- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)\n\n",
            "---\n\n",
        ]

        if self.live_exchange_reconciliation:
            rec = self.live_exchange_reconciliation
            real_pnl_str = f"+${rec['real_net_realized_usd']:.4f}" if rec['real_net_realized_usd'] >= 0 else f"-${abs(rec['real_net_realized_usd']):.4f}"
            lines.extend([
                "## 1. Real On-Chain Hyperliquid Execution (Exchange Reconciled)\n\n",
                "> [!IMPORTANT]\n",
                "> The figures below represent **actual on-chain fills and cash settlements** verified directly against the Hyperliquid clearinghouse API for this trading session.\n\n",
                "| Metric | Real Value (Exchange Settled) |\n",
                "| :--- | :---: |\n",
                f"| **Total Real Fills** | {rec['total_fills']} ({rec['maker_fills']} Maker / {rec['taker_fills']} Taker) |\n",
                f"| **Real Executed Volume** | {rec['total_volume_btc']:.4f} {self.coin} |\n",
                f"| **Real Closed PnL** | ${rec['real_closed_pnl_usd']:+.4f} USDC |\n",
                f"| **Real Fees Paid to Hyperliquid** | ${rec['real_fees_paid_usd']:.4f} USDC |\n",
                f"| **Real Net Realized PnL** | **{real_pnl_str} USDC** |\n",
                "| **On-Chain Fills CSV** | [`live_exchange_fills.csv`](live_exchange_fills.csv) |\n\n",
                "---\n\n",
                "## 2. Theoretical Paper-Simulation Benchmark\n\n",
            ])
        else:
            lines.append("## 1. Executive Strategy Performance Audit\n\n")

        coin = (self.coin or "BTC").upper()
        lines.extend([
            f"| Strategy | Trades | Win Rate | Volume ({coin}) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |\n",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |\n",
        ])

        all_strat_names = sorted(set(self.enabled_strategies).union(self.trades_by_strategy.keys()))
        for s_name in all_strat_names:
            st = self.calculate_strategy_stats(s_name)
            pnl_sign = "+" if st["net_pnl_usd"] >= 0 else ""
            fee_sign = "+" if st["total_fees_usd"] <= 0 else "-"
            csv_rel = f"strategies/{s_name}.csv"
            lines.append(
                f"| **{s_name}** | {st['trades']} | {st['win_rate_pct']:.1f}% | {st['total_volume_btc']:.4f} | "
                f"{fee_sign}${abs(st['total_fees_usd']):.2f} | **{pnl_sign}${st['net_pnl_usd']:.2f}** | "
                f"{st['avg_return_bps']:+.1f} bps | {st['profit_factor']:.2f} | [`{s_name}.csv`]({csv_rel}) |\n"
            )

        # 2. Individual Strategy Trade Breakdown
        lines.append("\n---\n\n## 2. Individual Trade Logs per Strategy\n\n")

        for s_name in all_strat_names:
            trades = self.trades_by_strategy.get(s_name, [])
            st = self.calculate_strategy_stats(s_name)
            lines.append(f"### Strategy: `{s_name}`\n\n")
            lines.append(
                f"- **Total Executed Trades**: {len(trades)} | **Wins**: {st['wins']} | **Losses**: {st['losses']} | "
                f"**Win Rate**: {st['win_rate_pct']:.1f}% | **Net PnL**: ${st['net_pnl_usd']:+.2f}\n"
                f"- **Audit CSV**: [`strategies/{s_name}.csv`](strategies/{s_name}.csv)\n\n"
            )

            if not trades:
                lines.append(f"_No trades were opened/closed for {s_name} during this session._\n\n")
                continue

            lines.append(
                f"| # | Trade ID | Side | Size ({coin}) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |\n"
            )
            lines.append(
                "| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |\n"
            )

            for idx, t in enumerate(trades, 1):
                pnl_str = f"+${t.net_pnl_usd:.2f}" if t.net_pnl_usd >= 0 else f"-${abs(t.net_pnl_usd):.2f}"
                fee_str = f"+${abs(t.total_fees_usd):.2f}" if t.total_fees_usd <= 0 else f"-${t.total_fees_usd:.2f}"
                lines.append(
                    f"| {idx} | `{t.trade_id}` | {t.side} | {t.size_btc:.4f} | {t.entry_time_iso[11:]} | "
                    f"${t.entry_price:,.1f} | {t.exit_time_iso[11:]} | ${t.exit_price:,.1f} | "
                    f"{t.holding_time_secs:.1f}s | `{t.exit_reason}` | {fee_str} | **{pnl_str}** | {t.return_bps:+.1f} bps |\n"
                )
            lines.append("\n")

        # 3. Live Exchange Orders (if applicable)
        if self.live_order_events:
            lines.append("\n---\n\n## 3. Real Exchange Order Audit Log (Hyperliquid API)\n\n")
            lines.append(
                f"| Event ID | Time | Event | Side | Size ({coin}) | Price | TIF | OID | Status | Signal Score | Error |\n"
            )
            lines.append(
                "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |\n"
            )
            for ev in self.live_order_events:
                oid_str = f"`{ev.order_id}`" if ev.order_id else "-"
                err_str = ev.error_message or "-"
                lines.append(
                    f"| `{ev.event_id}` | {ev.timestamp_iso[11:]} | **{ev.event_type}** | {ev.side} | "
                    f"{ev.size_btc:.4f} | ${ev.price:,.1f} | `{ev.tif}` | {oid_str} | `{ev.response_status}` | "
                    f"{ev.signal_score:+.3f} | {err_str} |\n"
                )
            lines.append("\n")

        report_content = "".join(lines)
        with open(self.report_markdown_file, "w", encoding="utf-8") as f:
            f.write(report_content)

        # Mirror latest report
        try:
            latest_md = os.path.join(self.audit_dir, "latest_session_report.md")
            with open(latest_md, "w", encoding="utf-8") as f:
                f.write(report_content)
        except Exception:
            pass

        return self.report_markdown_file

    def close_session(self) -> Optional[str]:
        """Closes session, generates final audit report, and finalizes manifest."""
        if not self._initialized and not self.trades and not self.live_order_events:
            return None
        self._ensure_initialized()
        self._status = "CLOSED"
        self._save_manifest(status="CLOSED")
        report_file = self.generate_audit_report()

        # Update latest master CSV once at session close
        try:
            latest_csv = os.path.join(self.audit_dir, "latest_session_all_trades.csv")
            if os.path.exists(self.master_csv_file):
                shutil.copyfile(self.master_csv_file, latest_csv)
        except Exception as e:
            logger.debug(f"Could not mirror latest master CSV: {e}")

        return report_file

    # -------------------------------------------------------------------------
    # Static Query & Inspection Helpers
    # -------------------------------------------------------------------------
    @staticmethod
    def list_all_sessions(
        audit_dir: str = "audits",
        include_empty: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Returns list of all recorded sessions sorted newest to oldest."""
        if not os.path.exists(audit_dir):
            return []

        sessions = []
        for item in os.listdir(audit_dir):
            item_path = os.path.join(audit_dir, item)
            if not os.path.isdir(item_path):
                continue

            manifest_file = os.path.join(item_path, "session_manifest.json")
            data = None
            if os.path.exists(manifest_file):
                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    pass

            master_csv = os.path.join(item_path, "all_trades.csv")
            csv_trades_count = 0
            if os.path.exists(master_csv):
                try:
                    with open(master_csv, "r", encoding="utf-8", errors="ignore") as f:
                        lines = [l for l in f if l.strip()]
                        csv_trades_count = max(0, len(lines) - 1)
                except Exception:
                    pass

            if data is None:
                if csv_trades_count == 0 and not include_empty:
                    continue
                data = {
                    "session_id": item,
                    "status": "CLOSED" if csv_trades_count > 0 else "UNKNOWN",
                    "start_time_iso": item.replace("session_", "") if item.startswith("session_") else "",
                    "duration_secs": 0.0,
                    "session_summary": {"total_trades": csv_trades_count, "win_rate_pct": 0.0, "net_pnl_usd": 0.0, "total_volume_btc": 0.0},
                    "enabled_strategies": [],
                }
            else:
                m_trades = data.get("session_summary", {}).get("total_trades", 0)
                if m_trades == 0 and csv_trades_count > 0:
                    data.setdefault("session_summary", {})["total_trades"] = csv_trades_count

            m_trades = data.get("session_summary", {}).get("total_trades", 0)
            is_live = data.get("is_live_mode", False)
            if not include_empty and m_trades == 0 and not is_live:
                continue

            sessions.append(data)

        # Sort newest first by start time
        sessions.sort(key=lambda s: s.get("start_time_iso", ""), reverse=True)
        if limit and limit > 0:
            return sessions[:limit]
        return sessions

    @staticmethod
    def get_latest_session_id(audit_dir: str = "audits") -> Optional[str]:
        """Returns the ID of the latest trading session."""
        latest_ptr = os.path.join(audit_dir, "latest_session_id.txt")
        if os.path.exists(latest_ptr):
            try:
                with open(latest_ptr, "r", encoding="utf-8") as f:
                    sid = f.read().strip()
                if sid and os.path.isdir(os.path.join(audit_dir, sid)):
                    return sid
            except Exception:
                pass

        all_sess = SessionAuditor.list_all_sessions(audit_dir, include_empty=True)
        return all_sess[0].get("session_id") if all_sess else None

    @staticmethod
    def load_session_trades(
        session_id: str,
        strategy_name: Optional[str] = None,
        audit_dir: str = "audits",
    ) -> List[Dict[str, Any]]:
        """Reads auditable trades from CSV for a given session and optional strategy filter."""
        session_path = os.path.join(audit_dir, session_id)
        if not os.path.exists(session_path):
            return []

        csv_file = (
            os.path.join(session_path, "strategies", f"{strategy_name}.csv")
            if strategy_name
            else os.path.join(session_path, "all_trades.csv")
        )

        if not os.path.exists(csv_file):
            return []

        trades = []
        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    trades.append(row)
        except Exception:
            pass

        return trades

    @staticmethod
    def load_session_manifest(
        session_id: str,
        audit_dir: str = "audits",
    ) -> Optional[Dict[str, Any]]:
        """Loads the session_manifest.json dictionary for a given session."""
        session_path = os.path.join(audit_dir, session_id)
        manifest_file = os.path.join(session_path, "session_manifest.json")
        if not os.path.exists(manifest_file):
            return None
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    @staticmethod
    def prune_empty_sessions(audit_dir: str = "audits") -> int:
        """Removes orphaned session directories that have 0 trades and no live order events.
        
        Returns the number of deleted directories.
        """
        if not os.path.exists(audit_dir):
            return 0

        pruned_count = 0
        for item in os.listdir(audit_dir):
            if not item.startswith("session_"):
                continue
            item_path = os.path.join(audit_dir, item)
            if not os.path.isdir(item_path):
                continue

            csv_file = os.path.join(item_path, "all_trades.csv")
            live_file = os.path.join(item_path, "live_orders.csv")

            has_trades = False
            if os.path.exists(csv_file):
                try:
                    with open(csv_file, "r", encoding="utf-8", errors="ignore") as f:
                        lines = [l for l in f if l.strip()]
                        if len(lines) > 1:
                            has_trades = True
                except Exception:
                    pass

            has_live_orders = False
            if os.path.exists(live_file):
                try:
                    with open(live_file, "r", encoding="utf-8", errors="ignore") as f:
                        lines = [l for l in f if l.strip()]
                        if len(lines) > 1:
                            has_live_orders = True
                except Exception:
                    pass

            if not has_trades and not has_live_orders:
                try:
                    shutil.rmtree(item_path)
                    pruned_count += 1
                except Exception as e:
                    logger.warning(f"Could not remove empty session {item_path}: {e}")

        return pruned_count

    @staticmethod
    def repair_stalled_manifests(audit_dir: str = "audits") -> int:
        """Repairs and backfills session manifests for sessions that have recorded trades
        in all_trades.csv but are stuck in status RUNNING or with total_trades 0.
        
        Returns the number of repaired sessions.
        """
        if not os.path.exists(audit_dir):
            return 0

        repaired_count = 0
        for item in os.listdir(audit_dir):
            if not item.startswith("session_"):
                continue
            item_path = os.path.join(audit_dir, item)
            if not os.path.isdir(item_path):
                continue

            csv_file = os.path.join(item_path, "all_trades.csv")
            if not os.path.exists(csv_file):
                continue

            rows = []
            try:
                with open(csv_file, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
            except Exception:
                continue

            if not rows:
                continue

            manifest_file = os.path.join(item_path, "session_manifest.json")
            manifest_data = {}
            needs_repair = True
            if os.path.exists(manifest_file):
                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        manifest_data = json.load(f)
                    if manifest_data.get("status") == "CLOSED" and manifest_data.get("session_summary", {}).get("total_trades", 0) > 0:
                        needs_repair = False
                except Exception:
                    pass

            if not needs_repair:
                continue

            # Compute stats from CSV rows
            wins = [r for r in rows if float(r.get("net_pnl_usd", 0.0) or 0.0) > 0]
            losses = [r for r in rows if float(r.get("net_pnl_usd", 0.0) or 0.0) < 0]
            gross_win = sum(float(r.get("net_pnl_usd", 0.0) or 0.0) for r in wins)
            gross_loss = abs(sum(float(r.get("net_pnl_usd", 0.0) or 0.0) for r in losses))
            profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99.9 if gross_win > 0 else 0.0)

            total_gross = sum(float(r.get("gross_pnl_usd", 0.0) or 0.0) for r in rows)
            total_fees = sum(float(r.get("total_fees_usd", 0.0) or 0.0) for r in rows)
            total_net = sum(float(r.get("net_pnl_usd", 0.0) or 0.0) for r in rows)
            total_vol = sum(float(r.get("size_btc", 0.0) or 0.0) for r in rows)

            # Strategy breakdown
            strat_map: Dict[str, List[Dict[str, Any]]] = {}
            for r in rows:
                s_name = r.get("strategy_name", "Unknown")
                strat_map.setdefault(s_name, []).append(r)

            strat_metrics = {}
            for s_name, s_rows in strat_map.items():
                s_wins = [r for r in s_rows if float(r.get("net_pnl_usd", 0.0) or 0.0) > 0]
                s_losses = [r for r in s_rows if float(r.get("net_pnl_usd", 0.0) or 0.0) < 0]
                s_gwin = sum(float(r.get("net_pnl_usd", 0.0) or 0.0) for r in s_wins)
                s_gloss = abs(sum(float(r.get("net_pnl_usd", 0.0) or 0.0) for r in s_losses))
                s_pf = (s_gwin / s_gloss) if s_gloss > 0 else (99.9 if s_gwin > 0 else 0.0)
                s_net = sum(float(r.get("net_pnl_usd", 0.0) or 0.0) for r in s_rows)
                s_ret = sum(float(r.get("return_bps", 0.0) or 0.0) for r in s_rows) / len(s_rows)

                strat_metrics[s_name] = {
                    "trades": len(s_rows),
                    "wins": len(s_wins),
                    "losses": len(s_losses),
                    "win_rate_pct": round((len(s_wins) / len(s_rows)) * 100.0, 1),
                    "gross_pnl_usd": round(sum(float(r.get("gross_pnl_usd", 0.0) or 0.0) for r in s_rows), 2),
                    "total_fees_usd": round(sum(float(r.get("total_fees_usd", 0.0) or 0.0) for r in s_rows), 4),
                    "net_pnl_usd": round(s_net, 2),
                    "profit_factor": round(s_pf, 2),
                    "avg_trade_pnl": round(s_net / len(s_rows), 4),
                    "avg_return_bps": round(s_ret, 2),
                    "max_drawdown_usd": 0.0,
                    "total_volume_btc": round(sum(float(r.get("size_btc", 0.0) or 0.0) for r in s_rows), 4),
                    "csv_file": f"strategies/{s_name}.csv",
                }

            start_iso = rows[0].get("entry_time", "") or manifest_data.get("start_time_iso", "")
            end_iso = rows[-1].get("exit_time", "") or manifest_data.get("end_time_iso", "")

            duration_secs = 0.0
            try:
                t0 = time.mktime(time.strptime(start_iso[:19], "%Y-%m-%dT%H:%M:%S"))
                t1 = time.mktime(time.strptime(end_iso[:19], "%Y-%m-%dT%H:%M:%S"))
                duration_secs = max(0.0, t1 - t0)
            except Exception:
                duration_secs = manifest_data.get("duration_secs", 0.0)

            manifest = {
                "session_id": item,
                "status": "CLOSED",
                "start_time_iso": start_iso,
                "end_time_iso": end_iso,
                "duration_secs": round(duration_secs, 1),
                "coin": rows[0].get("coin", manifest_data.get("coin", "BTC")),
                "network": rows[0].get("network", manifest_data.get("network", "Testnet")),
                "is_live_mode": manifest_data.get("is_live_mode", False),
                "enabled_strategies": list(strat_map.keys()),
                "session_summary": {
                    "total_trades": len(rows),
                    "winning_trades": len(wins),
                    "losing_trades": len(losses),
                    "win_rate_pct": round((len(wins) / len(rows)) * 100.0, 1),
                    "gross_pnl_usd": round(total_gross, 2),
                    "total_fees_usd": round(total_fees, 4),
                    "net_pnl_usd": round(total_net, 2),
                    "profit_factor": round(profit_factor, 2),
                    "total_volume_btc": round(total_vol, 4),
                },
                "strategies": strat_metrics,
                "files": {
                    "master_csv": "all_trades.csv",
                    "audit_jsonl": "trades_audit.jsonl" if os.path.exists(os.path.join(item_path, "trades_audit.jsonl")) else None,
                    "session_report": "session_audit_report.md",
                    "live_orders_csv": "live_orders.csv" if os.path.exists(os.path.join(item_path, "live_orders.csv")) else None,
                    "live_exchange_fills_csv": "live_exchange_fills.csv" if os.path.exists(os.path.join(item_path, "live_exchange_fills.csv")) else None,
                },
            }

            try:
                with open(manifest_file, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2)
                repaired_count += 1
            except Exception as e:
                logger.warning(f"Could not save repaired manifest for {item}: {e}")

        return repaired_count
