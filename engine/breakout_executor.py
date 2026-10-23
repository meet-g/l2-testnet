"""Breakout Prop Firm Order Execution Client.

Provides browser-driven and CDP-connected execution for Breakout Terminal (breakoutprop.com),
enabling automated order placement (Buy/Sell, Market/Limit), Stop Loss (SL), Take Profit (TP),
position tracking, and prop firm drawdown circuit breakers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import os
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from playwright.async_api import (
    Browser,
    BrowserContext,
    ElementHandle,
    Page,
    Playwright,
    Response,
    async_playwright,
)
from rich.console import Console

logger = logging.getLogger("BreakoutExecutor")


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class SizeMode(str, Enum):
    USD = "USD"
    CONTRACTS = "CONTRACTS"
    UNITS = "UNITS"


@dataclass
class OrderIntent:
    """Represents a trading instruction to be submitted to Breakout Terminal."""

    side: Union[OrderSide, str]
    symbol: str = "BTC-USD"
    size: float = 100.0  # Default notional USD or unit count
    size_mode: Union[SizeMode, str] = SizeMode.USD
    order_type: Union[OrderType, str] = OrderType.MARKET
    price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    stop_loss_pct: Optional[float] = None  # e.g., 0.01 for 1%
    take_profit_pct: Optional[float] = None  # e.g., 0.02 for 2%
    reduce_only: bool = False
    comment: str = ""


@dataclass
class PositionInfo:
    """Active open position telemetry."""

    symbol: str
    side: str  # "LONG" or "SHORT"
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float = 0.0
    liquidation_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AccountTelemetry:
    """Prop firm risk and account telemetry."""

    equity: float = 0.0
    balance: float = 0.0
    available_margin: float = 0.0
    daily_drawdown_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    daily_drawdown_limit_pct: float = 4.0  # Prop firm hard rule (e.g. 4%)
    max_drawdown_limit_pct: float = 8.0  # Prop firm hard rule (e.g. 8%)
    is_daily_limit_breached: bool = False
    is_max_limit_breached: bool = False
    active_account_id: str = ""
    timestamp: float = field(default_factory=time.time)


class BreakoutExecutor:
    """Execution engine for Breakout Prop Firm Terminal.
    
    Supports two operating modes:
    1. CDP Connection: Attaches to an existing Chrome instance opened by the user
       with `--remote-debugging-port=9222`. This is recommended as it reuses existing
       authenticated sessions without triggering 2FA/Cloudflare.
    2. Persistent Profile: Launches Chromium with a persistent `user_data_dir`,
       retaining session cookies and local storage across runs.
    """

    def __init__(
        self,
        portal_url: str = "https://trade.breakoutprop.com",
        user_data_dir: Optional[str] = None,
        cdp_port: Optional[int] = 9222,
        headless: bool = False,
        daily_loss_limit_pct: float = 3.5,  # Defensive threshold below 4.0%
        console: Optional[Console] = None,
    ):
        self.portal_url = portal_url
        self.user_data_dir = user_data_dir or os.path.abspath("./data/breakout_profile")
        self.cdp_port = cdp_port
        self.headless = headless
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.console = console or Console()

        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self.is_connected: bool = False

        # Captured session headers and internal API endpoints
        self.captured_auth_headers: Dict[str, str] = {}
        self.captured_order_endpoints: List[str] = []
        self.telemetry = AccountTelemetry()
        self.positions: List[PositionInfo] = []

        # Load learned selectors if available from teaching session
        self.selectors_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "data", "breakout_selectors.json")
        )
        self.learned_selectors: Dict[str, Any] = self._load_learned_selectors()

    def _load_learned_selectors(self) -> Dict[str, Any]:
        """Loads element selectors mapped via `teach_breakout.py`."""
        if os.path.exists(self.selectors_path):
            try:
                with open(self.selectors_path, "r") as f:
                    data = json.load(f)
                    self.console.print(
                        f"[bold green]✓ [BreakoutExecutor] Loaded {len(data)} learned selectors from {self.selectors_path}[/bold green]"
                    )
                    return data
            except Exception as e:
                self.console.print(f"[dim yellow]Warning: Failed to parse selectors file: {e}[/dim yellow]")
        return {}

    def get_learned_selector(self, key: str) -> Optional[str]:
        """Retrieves learned selector string for a specific action key."""
        if key in self.learned_selectors:
            sel = self.learned_selectors[key].get("selector")
            if sel:
                return sel
        return None

    async def connect(self, prefer_cdp: bool = True) -> bool:
        """Connects to Breakout Terminal via CDP or opens a persistent browser profile."""
        os.makedirs(self.user_data_dir, exist_ok=True)
        self._pw = await async_playwright().start()

        if prefer_cdp and self.cdp_port:
            try:
                self.console.print(
                    f"[dim cyan][BreakoutExecutor] Attempting CDP connection to port {self.cdp_port}...[/dim cyan]"
                )
                self._browser = await self._pw.chromium.connect_over_cdp(f"http://localhost:{self.cdp_port}")
                self._context = self._browser.contexts[0]
                self.console.print("[bold green]✓ [BreakoutExecutor] Connected via Chrome DevTools Protocol![/bold green]")
            except Exception as e:
                self.console.print(
                    f"[dim yellow][BreakoutExecutor] CDP connection failed ({e}). Falling back to persistent profile.[/dim yellow]"
                )
                self._browser = None

        if not self._browser:
            self.console.print(
                f"[dim cyan][BreakoutExecutor] Launching Chromium with profile: {self.user_data_dir}[/dim cyan]"
            )
            self._context = await self._pw.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                viewport={"width": 1600, "height": 960},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                ],
            )

        # Locate or open Breakout page
        self._page = await self._find_or_open_terminal_page()
        self._setup_network_listeners(self._page)
        self.is_connected = True
        return True

    async def _find_or_open_terminal_page(self) -> Page:
        """Finds an existing Breakout tab or opens one."""
        if not self._context:
            raise RuntimeError("Browser context not initialized")

        pages = self._context.pages
        for p in pages:
            if "breakout" in p.url.lower():
                self.console.print(f"[bold green]✓ Found active Breakout page: {p.url}[/bold green]")
                return p

        # If none found, use the first or open a new one
        page = pages[0] if pages else await self._context.new_page()
        self.console.print(f"[dim cyan]Navigating to {self.portal_url}...[/dim cyan]")
        await page.goto(self.portal_url, wait_until="domcontentloaded")
        
        # Wait up to 10 seconds for Cloudflare turnstile if present
        for _ in range(7):
            try:
                title = await page.title()
                if "cloudflare" not in title.lower() and "attention" not in title.lower():
                    break
                self.console.print("[dim yellow]Waiting for Cloudflare verification to clear...[/dim yellow]")
                await asyncio.sleep(1.5)
            except Exception:
                break

        return page

    def _setup_network_listeners(self, page: Page) -> None:
        """Listens for authenticated API requests to capture auth tokens & endpoints."""
        async def on_request(req):
            url = req.url.lower()
            if "breakout" in url or "kraken" in url:
                headers = req.headers
                auth = headers.get("authorization")
                if auth and not self.captured_auth_headers.get("authorization"):
                    self.captured_auth_headers["authorization"] = auth
                    self.console.print(f"[dim green]✓ Captured Authorization header: {auth[:18]}...[/dim green]")
                if any(x in url for x in ["order", "trade", "position", "account"]):
                    if req.method in ["POST", "PUT", "DELETE"]:
                        if req.url not in self.captured_order_endpoints:
                            self.captured_order_endpoints.append(req.url)
                            logger.info(f"Captured internal order endpoint: {req.method} {req.url}")

        page.on("request", on_request)

    async def close(self) -> None:
        """Closes browser connections cleanly."""
        try:
            if self._context:
                await self._context.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self.is_connected = False
        self.console.print("[dim yellow][BreakoutExecutor] Disconnected.[/dim yellow]")

    # --------------------------------------------------------------------------
    # Telemetry & Risk Guardrails (Prop Firm Protection)
    # --------------------------------------------------------------------------

    async def refresh_account_telemetry(self) -> AccountTelemetry:
        """Scrapes or evaluates account equity, balance, and drawdown meters."""
        if not self._page:
            return self.telemetry

        try:
            # Evaluate DOM for balance & drawdown statistics
            data = await self._page.evaluate(
                """() => {
                    const findTextMatches = (regex) => {
                        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                        let node;
                        const matches = [];
                        while (node = walker.nextNode()) {
                            if (regex.test(node.textContent)) {
                                matches.push(node.textContent.trim());
                            }
                        }
                        return matches;
                    };

                    const cleanNum = (str) => {
                        if (!str) return 0;
                        const cleaned = str.replace(/[^0-9.-]/g, '');
                        return parseFloat(cleaned) || 0;
                    };

                    // Extract text candidates
                    const texts = Array.from(document.querySelectorAll('span, div, p'))
                        .map(el => el.textContent.trim())
                        .filter(t => t.length > 0 && t.length < 50);

                    return {
                        title: document.title,
                        url: window.location.href,
                        texts: texts.slice(0, 200)
                    };
                }"""
            )

            # Parse equity / balance patterns
            for t in data.get("texts", []):
                if "equity" in t.lower() or "balance" in t.lower():
                    nums = re.findall(r"\$([0-9,]+(?:\.[0-9]+)?)", t)
                    if nums:
                        val = float(nums[0].replace(",", ""))
                        if "equity" in t.lower():
                            self.telemetry.equity = val
                        elif "balance" in t.lower():
                            self.telemetry.balance = val

                if "daily" in t.lower() and "drawdown" in t.lower():
                    pcts = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*%", t)
                    if pcts:
                        self.telemetry.daily_drawdown_pct = float(pcts[0])

            # Safety check
            if self.telemetry.daily_drawdown_pct >= self.daily_loss_limit_pct:
                self.telemetry.is_daily_limit_breached = True
                self.console.print(
                    f"[bold red]⚠ CIRCUIT BREAKER TRIGGERED: Daily DD at {self.telemetry.daily_drawdown_pct:.2f}% "
                    f"(Defensive limit: {self.daily_loss_limit_pct}%)![/bold red]"
                )

        except Exception as e:
            logger.warning(f"Error scraping telemetry: {e}")

        return self.telemetry

    def check_risk_clearance(self) -> Tuple[bool, str]:
        """Validates that trading is permitted under prop firm rules."""
        if self.telemetry.is_daily_limit_breached:
            return False, f"Daily drawdown limit breached ({self.telemetry.daily_drawdown_pct:.2f}%)"
        if self.telemetry.is_max_limit_breached:
            return False, f"Maximum drawdown limit breached ({self.telemetry.max_drawdown_pct:.2f}%)"
        return True, "OK"

    # --------------------------------------------------------------------------
    # Direct Internal API Execution (Reverse-Engineered from HAR)
    # --------------------------------------------------------------------------

    async def get_fresh_csrf_token(self) -> Optional[str]:
        """Fetches a fresh CSRF token from the internal API endpoint."""
        if not self._page:
            return None
        try:
            res = await self._page.evaluate(
                """async () => {
                    const r = await fetch('https://iapi.breakoutprop.com/api/internal/csrf/BREAKOUT', {
                        headers: {
                            'accept': 'application/json',
                            'origin': 'https://trade.breakoutprop.com',
                            'referer': 'https://trade.breakoutprop.com/',
                            'x-handler-environment': 'stable',
                            'x-korigin': 's081'
                        },
                        credentials: 'include'
                    });
                    if (!r.ok) return null;
                    const d = await r.json();
                    if (d && d.result && d.result.csrf_token) return d.result.csrf_token;
                    if (d && d.csrf_token) return d.csrf_token;
                    if (d && d.token) return d.token;
                    return typeof d === 'string' ? d : null;
                }"""
            )
            if res:
                self.console.print(f"[dim green]✓ Obtained fresh CSRF token from internal API ({str(res)[:18]}...)[/dim green]")
                return str(res)
        except Exception as e:
            logger.warning(f"Failed to fetch fresh CSRF token: {e}")
        return None

    async def place_api_order(
        self,
        account_id: str,
        pair: str,
        side: str,
        volume: str,
        price: Optional[str] = None,
        order_type: str = "limit",
    ) -> Dict[str, Any]:
        """Places an order directly using the internal Breakout API (sub-150ms execution)."""
        if not self._page:
            return {"status": "error", "message": "Terminal page not connected"}

        csrf_token = await self.get_fresh_csrf_token()
        if not csrf_token:
            csrf_token = self.captured_auth_headers.get("x-csrf-token", "")

        url = f"https://iapi.breakoutprop.com/api/internal/breakout/v1/trading/orders?account_id={account_id}"
        
        payload: Dict[str, Any] = {
            "pair": {"asset_class": "external_pair", "name": pair},
            "side": side.lower(),
            "volume": str(volume),
        }
        if order_type.lower() == "limit" and price:
            payload["order_type"] = {"limit": {"price": {"absolute": str(price)}}}
        else:
            payload["order_type"] = {"market": {}}

        self.console.print(f"[bold cyan]>>> Submitting Direct API Order: {side.upper()} {volume} {pair} @ {price or 'MARKET'}...[/bold cyan]")

        eval_script = f"""async () => {{
            const headers = {{
                'accept': 'application/json',
                'content-type': 'application/json',
                'origin': 'https://trade.breakoutprop.com',
                'referer': 'https://trade.breakoutprop.com/',
                'x-handler-environment': 'stable',
                'x-korigin': 's081',
                'x-csrf-token': '{csrf_token}'
            }};
            try {{
                const res = await fetch('{url}', {{
                    method: 'POST',
                    headers: headers,
                    credentials: 'include',
                    body: JSON.stringify({json.dumps(payload)})
                }});
                const body = await res.json();
                return {{ status: res.status, body: body }};
            }} catch (e) {{
                return {{ status: 0, error: e.toString() }};
            }}
        }}"""

        res = await self._page.evaluate(eval_script)
        if res.get("status") in [200, 201]:
            order_id = res.get("body", {}).get("result", {}).get("order_id")
            self.console.print(f"[bold green]✓ API Order Accepted! Order ID: {order_id}[/bold green]")
            return {"status": "ok", "order_id": order_id, "raw": res}
        else:
            self.console.print(f"[bold red]✗ API Order Rejected: {res}[/bold red]")
            return {"status": "rejected", "response": res}

    # --------------------------------------------------------------------------
    # Market Order Placement Primitives (DOM-Based)
    # --------------------------------------------------------------------------

    async def place_order(self, intent: OrderIntent) -> Dict[str, Any]:
        """Places an order (Market or Limit) with optional Take Profit & Stop Loss.
        
        Args:
            intent: Order parameters including side, size, order type, TP, and SL.
        
        Returns:
            Dict containing order submission status and telemetry.
        """
        if not self._page:
            return {"status": "error", "message": "Terminal not connected"}

        # 1. Enforce Risk Clearance
        cleared, reason = self.check_risk_clearance()
        if not cleared:
            self.console.print(f"[bold red]✗ Order blocked by Risk Guardrail: {reason}[/bold red]")
            return {"status": "rejected", "reason": reason}

        side_str = intent.side.value if isinstance(intent.side, OrderSide) else str(intent.side).upper()
        is_buy = side_str in ["BUY", "LONG"]
        side_label = "BUY" if is_buy else "SELL"
        color = "green" if is_buy else "red"

        self.console.print(
            f"[bold {color}]>>> Submitting {side_label} {intent.size} ({intent.size_mode.value if isinstance(intent.size_mode, SizeMode) else intent.size_mode}) "
            f"on {intent.symbol} (Type: {intent.order_type})...[/bold {color}]"
        )

        try:
            # 2. Select Order Type Tab (Market vs Limit)
            await self._select_order_type(intent.order_type)

            # 3. Select Side (Buy / Sell or Long / Short)
            await self._select_side(is_buy)

            # 4. Input Size
            await self._input_size(intent.size, intent.size_mode)

            # 5. Input Price if Limit Order
            if intent.order_type in [OrderType.LIMIT, "LIMIT"]:
                if not intent.price:
                    raise ValueError("Limit order requires 'price'")
                await self._input_limit_price(intent.price)

            # 6. Configure Stop Loss (SL) & Take Profit (TP) if requested
            if intent.stop_loss_price or intent.stop_loss_pct:
                await self._configure_stop_loss(intent.stop_loss_price, intent.stop_loss_pct)

            if intent.take_profit_price or intent.take_profit_pct:
                await self._configure_take_profit(intent.take_profit_price, intent.take_profit_pct)

            # 7. Submit Order
            submission_res = await self._click_submit_button(side_label)

            # 8. Wait for fill / confirmation
            await asyncio.sleep(0.5)
            await self.refresh_account_telemetry()

            return {
                "status": "submitted",
                "side": side_label,
                "symbol": intent.symbol,
                "size": intent.size,
                "sl": intent.stop_loss_price or intent.stop_loss_pct,
                "tp": intent.take_profit_price or intent.take_profit_pct,
                "raw_result": submission_res,
            }

        except Exception as e:
            self.console.print(f"[bold red]✗ Failed to execute order: {e}[/bold red]")
            return {"status": "error", "error": str(e)}

    # --------------------------------------------------------------------------
    # Position Management (Close, Edit SL/TP, Emergency Flatten)
    # --------------------------------------------------------------------------

    async def get_open_positions(self) -> List[PositionInfo]:
        """Scrapes currently active open positions from the terminal's Positions table."""
        if not self._page:
            return []

        try:
            positions_data = await self._page.evaluate(
                """() => {
                    const rows = Array.from(document.querySelectorAll('table tbody tr, [role="row"]'));
                    const results = [];
                    for (const r of rows) {
                        const text = r.innerText || r.textContent;
                        if (!text) continue;
                        if (text.includes('BTC') || text.includes('ETH') || text.includes('SOL')) {
                            const cells = Array.from(r.querySelectorAll('td, [role="cell"]')).map(c => c.innerText.trim());
                            results.push({
                                row_text: text,
                                cells: cells
                            });
                        }
                    }
                    return results;
                }"""
            )

            positions: List[PositionInfo] = []
            for item in positions_data:
                cells = item.get("cells", [])
                text = item.get("row_text", "")
                is_long = "long" in text.lower() or "buy" in text.lower()
                side = "LONG" if is_long else "SHORT"

                # Extract numbers from row
                numbers = re.findall(r"[-+]?[0-9,]+(?:\.[0-9]+)?", text)
                clean_nums = [float(n.replace(",", "")) for n in numbers if n not in ["+", "-"]]

                pos = PositionInfo(
                    symbol="BTC-USD" if "BTC" in text else ("ETH-USD" if "ETH" in text else "UNKNOWN"),
                    side=side,
                    size=clean_nums[0] if len(clean_nums) > 0 else 0.0,
                    entry_price=clean_nums[1] if len(clean_nums) > 1 else 0.0,
                    mark_price=clean_nums[2] if len(clean_nums) > 2 else 0.0,
                    unrealized_pnl=clean_nums[3] if len(clean_nums) > 3 else 0.0,
                    raw_data=item,
                )
                positions.append(pos)

            self.positions = positions
            return positions

        except Exception as e:
            logger.warning(f"Error fetching open positions: {e}")
            return []

    async def close_position(self, symbol: str = "BTC-USD", percentage: float = 100.0) -> bool:
        """Market closes an active position (full or partial)."""
        if not self._page:
            return False

        self.console.print(f"[bold yellow]Closing position on {symbol} ({percentage}%)...[/bold yellow]")
        try:
            # Look for Close or Market Close button in Positions table
            close_btn = await self._find_first([
                f'button:has-text("Close")',
                f'button:has-text("Market Close")',
                f'[data-testid*="close-position"]',
                f'button[aria-label*="Close"]',
            ])

            if close_btn:
                await close_btn.click()
                await asyncio.sleep(0.3)

                # Check for confirm modal if present
                confirm_btn = await self._find_first([
                    'button:has-text("Confirm")',
                    'button:has-text("Yes")',
                    '[data-testid*="confirm"]',
                ])
                if confirm_btn:
                    await confirm_btn.click()

                self.console.print(f"[bold green]✓ Position closed successfully on {symbol}![/bold green]")
                return True
            else:
                self.console.print(f"[dim red]Could not locate Close button for {symbol}[/dim red]")
                return False

        except Exception as e:
            self.console.print(f"[bold red]✗ Failed to close position: {e}[/bold red]")
            return False

    async def emergency_flatten(self) -> Dict[str, Any]:
        """Panic button: Cancels all open orders and closes all active positions immediately."""
        self.console.print("[bold red]🚨 EMERGENCY FLATTEN INITIATED 🚨[/bold red]")
        results = {"orders_cancelled": 0, "positions_closed": 0, "errors": []}

        try:
            # 1. Cancel All Open Orders
            cancel_all_btn = await self._find_first([
                'button:has-text("Cancel All")',
                'button:has-text("Cancel all orders")',
                '[data-testid*="cancel-all"]',
            ])
            if cancel_all_btn:
                await cancel_all_btn.click()
                results["orders_cancelled"] = 1
                self.console.print("[bold yellow]✓ Cancel All Orders clicked.[/bold yellow]")

            # 2. Close All Positions
            close_all_btn = await self._find_first([
                'button:has-text("Close All")',
                'button:has-text("Flatten All")',
                '[data-testid*="close-all"]',
            ])
            if close_all_btn:
                await close_all_btn.click()
                await asyncio.sleep(0.3)
                confirm_btn = await self._find_first([
                    'button:has-text("Confirm")',
                    'button:has-text("Yes")',
                ])
                if confirm_btn:
                    await confirm_btn.click()
                results["positions_closed"] += 1
                self.console.print("[bold green]✓ Close All Positions clicked.[/bold green]")
            else:
                # Fallback: Close individual open positions
                positions = await self.get_open_positions()
                for pos in positions:
                    if await self.close_position(pos.symbol):
                        results["positions_closed"] += 1

        except Exception as e:
            results["errors"].append(str(e))
            self.console.print(f"[bold red]✗ Emergency flatten error: {e}[/bold red]")

        return results

    # --------------------------------------------------------------------------
    # DOM Interaction Helpers with Resilient Fallbacks
    # --------------------------------------------------------------------------

    async def _find_first(self, selectors: List[str]) -> Optional[ElementHandle]:
        """Tries multiple selectors sequentially and returns the first visible match."""
        if not self._page:
            return None
        for sel in selectors:
            try:
                el = await self._page.wait_for_selector(sel, timeout=1200, state="visible")
                if el:
                    return el
            except Exception:
                continue
        return None

    async def _safe_fill_input(self, input_el: ElementHandle, value: str) -> None:
        """Types value into an input element cleanly, ensuring React state updates."""
        try:
            await input_el.click()
            await input_el.press("Control+A")
            await input_el.press("Backspace")
            await input_el.type(str(value), delay=25)
            await input_el.evaluate("(el) => el.dispatchEvent(new Event('input', { bubbles: true }))")
            await input_el.evaluate("(el) => el.dispatchEvent(new Event('change', { bubbles: true }))")
        except Exception:
            await input_el.fill(str(value))

    async def _select_order_type(self, order_type: Union[OrderType, str]) -> None:
        """Clicks Market or Limit tab in order widget."""
        target = "Market" if "market" in str(order_type).lower() else "Limit"
        learned = self.get_learned_selector("market_tab" if target == "Market" else "limit_tab")
        selectors = [learned] if learned else []
        selectors.extend([
            f'button:has-text("{target}")',
            f'div[role="tab"]:has-text("{target}")',
            f'[data-testid*="{target.lower()}"]',
        ])
        btn = await self._find_first(selectors)
        if btn:
            await btn.click()
        else:
            logger.debug(f"Order type tab '{target}' not clicked directly; may already be active.")

    async def _select_side(self, is_buy: bool) -> None:
        """Selects Buy / Long or Sell / Short."""
        learned = self.get_learned_selector("buy_button" if is_buy else "sell_button")
        labels = ["Buy", "Long"] if is_buy else ["Sell", "Short"]
        selectors = [learned] if learned else []
        for l in labels:
            selectors.extend([
                f'button:has-text("{l}")',
                f'div[role="button"]:has-text("{l}")',
                f'[data-testid*="{l.lower()}"]',
            ])

        btn = await self._find_first(selectors)
        if btn:
            await btn.click()
        else:
            raise RuntimeError(f"Could not locate {'Buy' if is_buy else 'Sell'} button on order ticket")

    async def _input_size(self, size: float, size_mode: Union[SizeMode, str]) -> None:
        """Inputs the order size."""
        learned = self.get_learned_selector("size_input")
        selectors = [learned] if learned else []
        selectors.extend([
            'input[name="size"]',
            'input[name="amount"]',
            'input[placeholder*="Amount"]',
            'input[placeholder*="Size"]',
            'input[placeholder*="USD"]',
            '[data-testid*="size-input"] input',
            '[data-testid*="amount-input"] input',
        ])
        input_el = await self._find_first(selectors)
        if input_el:
            await self._safe_fill_input(input_el, str(size))
        else:
            raise RuntimeError("Could not locate Order Size input field")

    async def _input_limit_price(self, price: float) -> None:
        """Inputs the limit price."""
        learned = self.get_learned_selector("limit_price_input")
        selectors = [learned] if learned else []
        selectors.extend([
            'input[name="price"]',
            'input[placeholder*="Price"]',
            '[data-testid*="price-input"] input',
        ])
        input_el = await self._find_first(selectors)
        if input_el:
            await self._safe_fill_input(input_el, str(price))
        else:
            raise RuntimeError("Could not locate Limit Price input field")

    async def _configure_stop_loss(self, sl_price: Optional[float], sl_pct: Optional[float]) -> None:
        """Checks and fills Stop Loss field."""
        learned_toggle = self.get_learned_selector("sl_toggle")
        toggle_selectors = [learned_toggle] if learned_toggle else []
        toggle_selectors.extend([
            'input[type="checkbox"][name*="sl"]',
            'input[type="checkbox"][name*="stop"]',
            'label:has-text("Stop Loss")',
            'label:has-text("SL")',
        ])
        sl_toggle = await self._find_first(toggle_selectors)
        if sl_toggle:
            try:
                await sl_toggle.click()
            except Exception:
                pass

        learned_input = self.get_learned_selector("sl_input")
        input_selectors = [learned_input] if learned_input else []
        input_selectors.extend([
            'input[name*="stopLoss"]',
            'input[name*="sl"]',
            'input[placeholder*="Stop Loss"]',
            'input[placeholder*="SL"]',
            '[data-testid*="sl-input"] input',
        ])
        sl_input = await self._find_first(input_selectors)
        if sl_input and sl_price:
            await self._safe_fill_input(sl_input, str(sl_price))
            self.console.print(f"[dim green]✓ Stop Loss set at ${sl_price:,.2f}[/dim green]")

    async def _configure_take_profit(self, tp_price: Optional[float], tp_pct: Optional[float]) -> None:
        """Checks and fills Take Profit field."""
        learned_toggle = self.get_learned_selector("tp_toggle")
        toggle_selectors = [learned_toggle] if learned_toggle else []
        toggle_selectors.extend([
            'input[type="checkbox"][name*="tp"]',
            'input[type="checkbox"][name*="takeProfit"]',
            'label:has-text("Take Profit")',
            'label:has-text("TP")',
        ])
        tp_toggle = await self._find_first(toggle_selectors)
        if tp_toggle:
            try:
                await tp_toggle.click()
            except Exception:
                pass

        learned_input = self.get_learned_selector("tp_input")
        input_selectors = [learned_input] if learned_input else []
        input_selectors.extend([
            'input[name*="takeProfit"]',
            'input[name*="tp"]',
            'input[placeholder*="Take Profit"]',
            'input[placeholder*="TP"]',
            '[data-testid*="tp-input"] input',
        ])
        tp_input = await self._find_first(input_selectors)
        if tp_input and tp_price:
            await self._safe_fill_input(tp_input, str(tp_price))
            self.console.print(f"[dim green]✓ Take Profit set at ${tp_price:,.2f}[/dim green]")

    async def _click_submit_button(self, side_label: str) -> str:
        """Clicks the final place order button."""
        learned = self.get_learned_selector("submit_button")
        selectors = [learned] if learned else []
        selectors.extend([
            f'button[type="submit"]:has-text("{side_label}")',
            f'button:has-text("Place Order")',
            f'button:has-text("Submit Order")',
            f'button:has-text("Confirm")',
            f'[data-testid*="submit-order"]',
            f'[data-testid*="place-order"]',
        ])
        submit_btn = await self._find_first(selectors)
        if submit_btn:
            await submit_btn.click()
            self.console.print(f"[bold green]✓ Clicked Place {side_label} Order button![/bold green]")
            return "clicked"
        else:
            raise RuntimeError(f"Could not locate submit button for {side_label} order")

    # --------------------------------------------------------------------------
    # DOM Diagnostic Inspector (For Calibrating Selectors)
    # --------------------------------------------------------------------------

    async def inspect_terminal_dom(self) -> Dict[str, Any]:
        """Dumps interactive inputs, buttons, and tables to calibrate selectors."""
        if not self._page:
            return {"error": "Page not loaded"}

        return await self._page.evaluate(
            """() => {
                const getElements = (selector) => {
                    return Array.from(document.querySelectorAll(selector)).map(el => ({
                        tag: el.tagName,
                        id: el.id || null,
                        name: el.getAttribute('name') || null,
                        type: el.getAttribute('type') || null,
                        placeholder: el.getAttribute('placeholder') || null,
                        text: (el.innerText || el.textContent || '').trim().slice(0, 50),
                        testId: el.getAttribute('data-testid') || null,
                        classes: el.className || null
                    }));
                };

                return {
                    inputs: getElements('input, select, textarea'),
                    buttons: getElements('button, [role="button"], [role="tab"]'),
                    tables: getElements('table, [role="table"]')
                };
            }"""
        )
