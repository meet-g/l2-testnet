"""Robust, high-throughput L2 data recorder with hourly rotation and continuous gathering daemon."""

import asyncio
import json
import os
import time
from typing import Any, Callable, Dict, Generator, List, Optional
import websockets


class L2DataRecorder:
    """High-throughput L2 data recorder with automatic hourly file rotation and buffered disk writes."""

    def __init__(self, output_dir: str = "data", coin: str = "BTC", rotate_hourly: bool = True):
        self.coin = coin
        self.rotate_hourly = rotate_hourly
        
        # Ensure coin data is stored in its own folder: e.g. data/btc/
        base_name = os.path.basename(os.path.normpath(output_dir)).lower()
        if base_name == coin.lower():
            self.output_dir = output_dir
        else:
            self.output_dir = os.path.join(output_dir, coin.lower())

        os.makedirs(self.output_dir, exist_ok=True)

        self.current_hour_str = ""
        self.file_handle = None
        self.filepath = ""
        self.record_count = 0
        self.total_records = 0
        self.bytes_written = 0
        self.trades_count = 0
        self.book_count = 0

        self._rotate_if_needed()

    def _get_filename_for_now(self) -> str:
        if self.rotate_hourly:
            hour_str = time.strftime("%Y%m%d_%H00")
            return os.path.join(self.output_dir, f"hl_{self.coin.lower()}_l2_{hour_str}.jsonl")
        else:
            session_str = time.strftime("%Y%m%d_%H%M%S")
            return os.path.join(self.output_dir, f"hl_{self.coin.lower()}_l2_{session_str}.jsonl")

    def _rotate_if_needed(self) -> None:
        now_hour = time.strftime("%Y%m%d_%H")
        if self.rotate_hourly and now_hour != self.current_hour_str:
            self.close()
            self.current_hour_str = now_hour
            self.filepath = self._get_filename_for_now()
            self.file_handle = open(self.filepath, "a", encoding="utf-8", buffering=64 * 1024)
            self.record_count = 0

    def record_event(self, channel: str, data: dict) -> None:
        """Appends an incoming WS event with local receipt timestamp."""
        self._rotate_if_needed()

        payload = {
            "recv_ts": int(time.time() * 1000),
            "channel": channel,
            "data": data,
        }
        line = json.dumps(payload) + "\n"
        self.file_handle.write(line)
        self.record_count += 1
        self.total_records += 1
        self.bytes_written += len(line.encode("utf-8"))

        if channel == "trades":
            self.trades_count += len(data) if isinstance(data, list) else 1
        elif channel == "l2Book":
            self.book_count += 1

        if self.record_count % 100 == 0:
            self.file_handle.flush()

    def flush(self) -> None:
        if self.file_handle and not self.file_handle.closed:
            self.file_handle.flush()

    def close(self) -> None:
        if self.file_handle and not self.file_handle.closed:
            self.file_handle.flush()
            self.file_handle.close()
            # Quarantine aborted/incomplete snippets (< 200 records or < 50 KB) to protect dataset hygiene
            if os.path.exists(self.filepath) and (self.record_count < 200 or os.path.getsize(self.filepath) < 50 * 1024):
                snippets_dir = os.path.join(self.output_dir, "snippets")
                os.makedirs(snippets_dir, exist_ok=True)
                target = os.path.join(snippets_dir, os.path.basename(self.filepath))
                try:
                    os.replace(self.filepath, target)
                except Exception:
                    pass


class ContinuousCollectorDaemon:
    """Robust background data collection daemon with automatic reconnection and live telemetry."""

    def __init__(self, ws_url: str = "wss://api.hyperliquid.xyz/ws", coin: str = "BTC", output_dir: str = "data"):
        self.ws_url = ws_url
        self.coin = coin
        self.recorder = L2DataRecorder(output_dir=output_dir, coin=coin, rotate_hourly=True)
        self.is_running = False

    async def run(self, max_duration_hours: float = 0.0) -> None:
        """Runs the continuous gathering loop until stopped or duration expires."""
        self.is_running = True
        start_time = time.time()
        max_secs = max_duration_hours * 3600.0 if max_duration_hours > 0 else float("inf")

        reconnect_delay = 1.0

        async def _ping_heartbeat(ws):
            """Sends Hyperliquid application-level JSON ping heartbeat every 20 seconds."""
            while self.is_running:
                try:
                    await asyncio.sleep(20.0)
                    if hasattr(ws, "closed") and ws.closed:
                        break
                    await ws.send(json.dumps({"method": "ping"}))
                except (asyncio.CancelledError, Exception):
                    break

        while self.is_running and (time.time() - start_time) < max_secs:
            try:
                print(f"[Collector] Connecting to {self.ws_url} for {self.coin}...")
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=20_000_000,
                ) as ws:
                    reconnect_delay = 1.0
                    sub_l2 = {"method": "subscribe", "subscription": {"type": "l2Book", "coin": self.coin}}
                    sub_trades = {"method": "subscribe", "subscription": {"type": "trades", "coin": self.coin}}
                    sub_ctx = {"method": "subscribe", "subscription": {"type": "activeAssetCtx", "coin": self.coin}}
                    # Deep macro aggregated book subscription (nSigFigs=4 / $10 buckets)
                    sub_macro = {"method": "subscribe", "subscription": {"type": "l2Book", "coin": self.coin, "nSigFigs": 4}}

                    await ws.send(json.dumps(sub_l2))
                    await ws.send(json.dumps(sub_trades))
                    await ws.send(json.dumps(sub_ctx))
                    await ws.send(json.dumps(sub_macro))
                    print(f"[Collector] Subscribed to {self.coin} L2 Book, Trades, ActiveAssetCtx, and Deep Macro Book. Logging to {self.recorder.output_dir}/")

                    ping_task = asyncio.create_task(_ping_heartbeat(ws))
                    last_telemetry = time.time()

                    try:
                        while self.is_running and (time.time() - start_time) < max_secs:
                            try:
                                msg_str = await asyncio.wait_for(ws.recv(), timeout=2.0)
                                msg = json.loads(msg_str)
                                ch = msg.get("channel")
                                if ch == "pong":
                                    continue
                                dt = msg.get("data")
                                if ch in ("l2Book", "trades", "activeAssetCtx") and dt:
                                    self.recorder.record_event(ch, dt)
                            except asyncio.TimeoutError:
                                pass

                            # Print periodic telemetry
                            if time.time() - last_telemetry >= 10.0:
                                elapsed = time.time() - start_time
                                mb = self.recorder.bytes_written / (1024 * 1024)
                                hrs = int(elapsed // 3600)
                                mins = int((elapsed % 3600) // 60)
                                secs = int(elapsed % 60)
                                print(
                                    f"[Collector Telemetry] Uptime: {hrs:02d}h {mins:02d}m {secs:02d}s | "
                                    f"Total Events: {self.recorder.total_records:,} (Books: {self.recorder.book_count:,}, Trades: {self.recorder.trades_count:,}) | "
                                    f"Storage: {mb:.2f} MB | File: {os.path.basename(self.recorder.filepath)}"
                                )
                                last_telemetry = time.time()
                    finally:
                        ping_task.cancel()

            except (asyncio.CancelledError, KeyboardInterrupt):
                self.is_running = False
                break
            except (ConnectionResetError, websockets.ConnectionClosed, OSError, Exception) as e:
                if not self.is_running:
                    break
                print(f"[Collector Warning] WebSocket disconnected ({type(e).__name__}: {e}). Reconnecting in {reconnect_delay:.1f}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(30.0, reconnect_delay * 1.5)

        self.recorder.close()
        print(f"[Collector] Data collection finished. Total events: {self.recorder.total_records:,}")


class L2ReplayEngine:
    """Replays recorded L2 book snapshots and trade streams at adjustable playback speed.
    
    Supports:
    1. Standard JSONL session logs (e.g. data/btc/hl_btc_l2_*.jsonl)
    2. TickFoundry / Hyperliquid Parquet archives (directories containing hl_l2, hl_trades)
    """

    def __init__(self, filepath: str, speed_multiplier: float = 1.0):
        self.filepath = filepath
        self.speed_multiplier = speed_multiplier
        self._resolve_filepath()

    def _resolve_filepath(self) -> None:
        """Resolves filepath if moved into coin-specific subdirectories."""
        if "*" in self.filepath or "?" in self.filepath:
            return
        if os.path.exists(self.filepath):
            return
        
        # If single file doesn't exist at given path, check coin subdirectory
        # e.g. data/hl_btc_l2_... -> data/btc/hl_btc_l2_...
        dirname = os.path.dirname(self.filepath) or "."
        basename = os.path.basename(self.filepath)
        if basename.startswith("hl_") and "_" in basename:
            coin = basename.split("_")[1].lower()
            candidate = os.path.join(dirname, coin, basename)
            if os.path.exists(candidate):
                self.filepath = candidate
                return
            candidate_upper = os.path.join(dirname, coin.upper(), basename)
            if os.path.exists(candidate_upper):
                self.filepath = candidate_upper
                return
        
        # Also check immediate subdirectories under dirname
        if os.path.isdir(dirname):
            for sub in os.listdir(dirname):
                candidate = os.path.join(dirname, sub, basename)
                if os.path.isfile(candidate):
                    self.filepath = candidate
                    return

    def stream_events(self) -> Generator[dict, None, None]:
        """Yields recorded events maintaining relative time offsets."""
        import glob
        # 1. Multi-file glob pattern match (e.g. data/btc/hl_btc_l2_20261001_*.jsonl or data/hl_btc_l2_*.jsonl)
        if "*" in self.filepath or "?" in self.filepath:
            matched_files = sorted(glob.glob(self.filepath))
            if not matched_files:
                # If no match at original path, try coin subfolder
                dirname = os.path.dirname(self.filepath) or "."
                basename = os.path.basename(self.filepath)
                if basename.startswith("hl_") and "_" in basename:
                    coin = basename.split("_")[1].lower()
                    matched_files = sorted(glob.glob(os.path.join(dirname, coin, basename)))
                    if not matched_files:
                        matched_files = sorted(glob.glob(os.path.join(dirname, coin.upper(), basename)))
                if not matched_files:
                    # Recursive search under dirname
                    matched_files = sorted(glob.glob(os.path.join(dirname, "**", basename), recursive=True))
                    matched_files = [f for f in matched_files if "snippets" not in f.replace("\\", "/").split("/")]

            if not matched_files:
                raise FileNotFoundError(f"No recording files matching pattern: {self.filepath}")
            prev_ts = None
            for fpath in matched_files:
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        event = json.loads(line)
                        ts = event.get("recv_ts", 0)
                        if prev_ts is not None and 0 < self.speed_multiplier < 1000:
                            delay_ms = (ts - prev_ts) / self.speed_multiplier
                            if 10.0 <= delay_ms < 5000:
                                time.sleep(delay_ms / 1000.0)
                        prev_ts = ts
                        yield event
            return

        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Recording file not found: {self.filepath}")

        # 2. Directory containing jsonl files
        if os.path.isdir(self.filepath):
            jsonl_files = sorted(glob.glob(os.path.join(self.filepath, "*.jsonl")))
            if not jsonl_files:
                # Also check immediate subdirectories (e.g. data/btc/*.jsonl)
                jsonl_files = sorted(glob.glob(os.path.join(self.filepath, "*", "*.jsonl")))
                jsonl_files = [f for f in jsonl_files if "snippets" not in f.replace("\\", "/").split("/")]

            has_parquet = any(f.endswith(".parquet") for root, _, files in os.walk(self.filepath) for f in files)
            if jsonl_files and not has_parquet:
                prev_ts = None
                for fpath in jsonl_files:
                    with open(fpath, "r", encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            event = json.loads(line)
                            ts = event.get("recv_ts", 0)
                            if prev_ts is not None and 0 < self.speed_multiplier < 1000:
                                delay_ms = (ts - prev_ts) / self.speed_multiplier
                                if 10.0 <= delay_ms < 5000:
                                    time.sleep(delay_ms / 1000.0)
                            prev_ts = ts
                            yield event
                return

        # 3. Parquet archives
        if os.path.isdir(self.filepath) or self.filepath.endswith(".parquet"):
            yield from self._stream_parquet_bundle()
            return

        # 4. Single JSONL file
        prev_ts = None
        with open(self.filepath, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                event = json.loads(line)
                ts = event.get("recv_ts", 0)

                if prev_ts is not None and 0 < self.speed_multiplier < 1000:
                    delay_ms = (ts - prev_ts) / self.speed_multiplier
                    if 10.0 <= delay_ms < 5000:
                        time.sleep(delay_ms / 1000.0)

                prev_ts = ts
                yield event

    def _stream_parquet_bundle(self) -> Generator[dict, None, None]:
        """Streams events from parquet archives (e.g. hyperliquid-2026-08-12)."""
        import pyarrow.parquet as pq
        import pandas as pd

        l2_file = None
        tr_file = None

        if os.path.isdir(self.filepath):
            for root, _, files in os.walk(self.filepath):
                for f in files:
                    if f == "l2.parquet" and not l2_file:
                        l2_file = os.path.join(root, f)
                    elif f == "trades.parquet" and not tr_file:
                        tr_file = os.path.join(root, f)
        elif self.filepath.endswith("l2.parquet"):
            l2_file = self.filepath
            sibling_tr = self.filepath.replace("hl_l2", "hl_trades").replace("l2.parquet", "trades.parquet")
            if os.path.exists(sibling_tr):
                tr_file = sibling_tr

        if not l2_file and not tr_file:
            raise FileNotFoundError(f"No l2.parquet or trades.parquet found in {self.filepath}")

        if l2_file:
            schema = pq.read_schema(l2_file)
            avail_cols = set(schema.names)
            cols = ["ts_src_ms", "best_bid", "best_ask"]
            for k in range(1, 26):
                for pfx in ["px", "sz", "n"]:
                    for side in ["bid", "ask"]:
                        c = f"{side}_{pfx}_{k}"
                        if c in avail_cols:
                            cols.append(c)

            l2_reader = pq.ParquetFile(l2_file)
        else:
            l2_reader = None

        if tr_file:
            tr_table = pq.read_table(tr_file, columns=["ts_src_ms", "price", "size", "side"])
            tr_ts = tr_table["ts_src_ms"].to_numpy()
            tr_px = tr_table["price"].to_numpy()
            tr_sz = tr_table["size"].to_numpy()
            tr_side = tr_table["side"].to_numpy()
            n_tr = len(tr_ts)
        else:
            tr_ts, tr_px, tr_sz, tr_side = np.array([]), np.array([]), np.array([]), np.array([])
            n_tr = 0

        tr_idx = 0
        prev_ts = None

        if l2_reader:
            for batch in l2_reader.iter_batches(batch_size=1000, columns=cols):
                batch_df = batch.to_pandas()
                for _, r in batch_df.iterrows():
                    now_ms = int(r["ts_src_ms"])

                    # Interleave trades that occurred before or at now_ms
                    while tr_idx < n_tr and tr_ts[tr_idx] <= now_ms:
                        t_ms = int(tr_ts[tr_idx])
                        side_val = "B" if tr_side[tr_idx] == "BUY" else "A"
                        tr_data = [{
                            "coin": "BTC",
                            "side": side_val,
                            "px": str(tr_px[tr_idx]),
                            "sz": str(tr_sz[tr_idx]),
                            "time": t_ms,
                            "hash": "",
                            "tid": tr_idx,
                        }]
                        tr_idx += 1
                        if prev_ts is not None and 0 < self.speed_multiplier < 1000:
                            delay = (t_ms - prev_ts) / self.speed_multiplier
                            if 10.0 <= delay < 5000:
                                time.sleep(delay / 1000.0)
                        prev_ts = t_ms
                        yield {"channel": "trades", "data": tr_data, "recv_ts": t_ms}

                    # Parse L2 levels
                    bids = [
                        {"px": str(r[f"bid_px_{k}"]), "sz": str(r[f"bid_sz_{k}"]), "n": int(r.get(f"bid_n_{k}", 1))}
                        for k in range(1, 26)
                        if f"bid_px_{k}" in r and pd.notna(r[f"bid_px_{k}"])
                    ]
                    asks = [
                        {"px": str(r[f"ask_px_{k}"]), "sz": str(r[f"ask_sz_{k}"]), "n": int(r.get(f"ask_n_{k}", 1))}
                        for k in range(1, 26)
                        if f"ask_px_{k}" in r and pd.notna(r[f"ask_px_{k}"])
                    ]

                    if prev_ts is not None and 0 < self.speed_multiplier < 1000:
                        delay = (now_ms - prev_ts) / self.speed_multiplier
                        if 10.0 <= delay < 5000:
                            time.sleep(delay / 1000.0)

                    prev_ts = now_ms
                    yield {"channel": "l2Book", "data": {"coin": "BTC", "time": now_ms, "levels": [bids, asks]}, "recv_ts": now_ms}

        # Any remaining trades
        while tr_idx < n_tr:
            t_ms = int(tr_ts[tr_idx])
            side_val = "B" if tr_side[tr_idx] == "BUY" else "A"
            tr_data = [{
                "coin": "BTC",
                "side": side_val,
                "px": str(tr_px[tr_idx]),
                "sz": str(tr_sz[tr_idx]),
                "time": t_ms,
                "hash": "",
                "tid": tr_idx,
            }]
            tr_idx += 1
            yield {"channel": "trades", "data": tr_data, "recv_ts": t_ms}
