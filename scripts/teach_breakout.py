"""Interactive Browser Teaching Session for Breakout Prop Firm Terminal.

Launches a browser session with a visual on-screen guide allowing you to teach
each action (Buy, Sell, Size, Stop Loss, Take Profit, Submit, Close) 1-by-1.
All captured selectors are automatically saved to `data/breakout_selectors.json`
and instantly used by `engine/breakout_executor.py`.

Usage:
  # 1. Connect to an already open Chrome instance with remote debugging
  python scripts/teach_breakout.py --cdp

  # 2. Or launch Chromium with saved login profile (default)
  python scripts/teach_breakout.py
"""

import argparse
import asyncio
import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from typing import Any, Dict, List, Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

SELECTORS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "breakout_selectors.json"))

# Teaching sequence
TEACH_STEPS = [
    {
        "key": "market_tab",
        "title": "Market Order Tab",
        "instruction": "Click the 'Market' tab or button on the order ticket",
        "optional": False,
    },
    {
        "key": "limit_tab",
        "title": "Limit Order Tab",
        "instruction": "Click the 'Limit' tab or button on the order ticket",
        "optional": True,
    },
    {
        "key": "buy_button",
        "title": "BUY / LONG Button",
        "instruction": "Click the Green 'Buy' or 'Long' button on the order form",
        "optional": False,
    },
    {
        "key": "sell_button",
        "title": "SELL / SHORT Button",
        "instruction": "Click the Red 'Sell' or 'Short' button on the order form",
        "optional": False,
    },
    {
        "key": "size_input",
        "title": "Order Size Input Field",
        "instruction": "Click inside the Size / Amount / Quantity input box",
        "optional": False,
    },
    {
        "key": "limit_price_input",
        "title": "Limit Price Input Field",
        "instruction": "Click inside the Limit Price input field (or Skip if not visible)",
        "optional": True,
    },
    {
        "key": "sl_toggle",
        "title": "Stop Loss Checkbox / Toggle",
        "instruction": "Click the Stop Loss checkbox or switch (or Skip if SL is always an input)",
        "optional": True,
    },
    {
        "key": "sl_input",
        "title": "Stop Loss Price Input",
        "instruction": "Click inside the Stop Loss (SL) price input field",
        "optional": False,
    },
    {
        "key": "tp_toggle",
        "title": "Take Profit Checkbox / Toggle",
        "instruction": "Click the Take Profit checkbox or switch (or Skip if TP is always an input)",
        "optional": True,
    },
    {
        "key": "tp_input",
        "title": "Take Profit Price Input",
        "instruction": "Click inside the Take Profit (TP) price input field",
        "optional": False,
    },
    {
        "key": "submit_button",
        "title": "Submit / Place Order Button",
        "instruction": "Click the main 'Place Order' / 'Submit' button",
        "optional": False,
    },
    {
        "key": "positions_tab",
        "title": "Positions Tab",
        "instruction": "Click the 'Positions' tab (at the bottom/side panel showing open trades)",
        "optional": True,
    },
    {
        "key": "close_position_button",
        "title": "Close Position Button",
        "instruction": "Click the 'Close' / 'Market Close' / 'X' button on a position row",
        "optional": True,
    },
    {
        "key": "confirm_modal_button",
        "title": "Confirm Modal Button",
        "instruction": "Click the 'Confirm' or 'Yes' button on any pop-up confirmation",
        "optional": True,
    },
]

INJECTED_TEACHER_JS = """
(() => {
    if (window.__breakoutTeacherActive) return;
    window.__breakoutTeacherActive = true;

    // Create banner UI overlay
    const banner = document.createElement('div');
    banner.id = '__breakout_teacher_banner';
    banner.style.cssText = `
        position: fixed;
        top: 12px;
        left: 50%;
        transform: translateX(-50%);
        background: #111827;
        color: #f9fafb;
        border: 2px solid #3b82f6;
        border-radius: 12px;
        padding: 14px 24px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 14px;
        z-index: 999999999;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.7);
        display: flex;
        align-items: center;
        gap: 16px;
        pointer-events: auto;
    `;

    banner.innerHTML = `
        <div style="display: flex; flex-direction: column;">
            <div id="__bt_title" style="font-weight: 700; font-size: 15px; color: #60a5fa;">🎯 TEACHING MODE</div>
            <div id="__bt_desc" style="font-size: 13px; color: #d1d5db; margin-top: 2px;">Waiting for instructions...</div>
        </div>
        <div style="display: flex; gap: 8px;">
            <button id="__bt_skip" style="background: #374151; color: #e5e7eb; border: 1px solid #4b5563; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600;">Skip Step</button>
            <button id="__bt_finish" style="background: #059669; color: #ffffff; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600;">Finish</button>
        </div>
    `;

    document.body.appendChild(banner);

    // Outline highlighter box
    const outline = document.createElement('div');
    outline.id = '__breakout_teacher_outline';
    outline.style.cssText = `
        position: absolute;
        border: 2px dashed #10b981;
        background: rgba(16, 185, 129, 0.15);
        pointer-events: none;
        z-index: 999999998;
        display: none;
        transition: all 0.05s ease-out;
    `;
    document.body.appendChild(outline);

    let currentTarget = null;

    // Helper: calculate best selector
    function computeSelector(el) {
        if (!el || el === document.body || el === document.documentElement) return '';

        // TestID attribute
        if (el.getAttribute('data-testid')) {
            return `[data-testid="${el.getAttribute('data-testid')}"]`;
        }
        if (el.id && !el.id.match(/[0-9]{4,}/)) {
            return `#${el.id}`;
        }
        if (el.getAttribute('name')) {
            return `${el.tagName.toLowerCase()}[name="${el.getAttribute('name')}"]`;
        }
        if (el.getAttribute('placeholder')) {
            return `${el.tagName.toLowerCase()}[placeholder="${el.getAttribute('placeholder')}"]`;
        }
        if (el.getAttribute('aria-label')) {
            return `[aria-label="${el.getAttribute('aria-label')}"]`;
        }

        const text = (el.innerText || el.textContent || '').trim();
        if (['BUTTON', 'A', 'SPAN', 'DIV'].includes(el.tagName) && text && text.length > 0 && text.length < 35 && !text.includes('\\n')) {
            return `${el.tagName.toLowerCase()}:has-text("${text.replace(/"/g, '\\"')}")`;
        }

        // Parent hierarchy
        let path = [];
        let curr = el;
        while (curr && curr.nodeType === Node.ELEMENT_NODE && curr !== document.body) {
            let seg = curr.tagName.toLowerCase();
            if (curr.getAttribute('data-testid')) {
                path.unshift(`[data-testid="${curr.getAttribute('data-testid')}"]`);
                break;
            }
            if (curr.className && typeof curr.className === 'string') {
                const classes = curr.className.trim().split(/\\s+/).filter(c => !c.includes(':') && !c.includes('/') && !c.match(/^[0-9]/) && c.length < 30);
                if (classes.length > 0) {
                    seg += '.' + classes.slice(0, 2).join('.');
                }
            }
            path.unshift(seg);
            curr = curr.parentNode;
            if (path.length >= 4) break;
        }
        return path.join(' > ');
    }

    // Hover listener
    document.addEventListener('mouseover', (e) => {
        if (banner.contains(e.target)) return;
        currentTarget = e.target;
        const rect = currentTarget.getBoundingClientRect();
        outline.style.display = 'block';
        outline.style.top = (rect.top + window.scrollY) + 'px';
        outline.style.left = (rect.left + window.scrollX) + 'px';
        outline.style.width = rect.width + 'px';
        outline.style.height = rect.height + 'px';
    }, true);

    // Click listener
    document.addEventListener('click', (e) => {
        if (banner.contains(e.target)) return;
        
        e.preventDefault();
        e.stopPropagation();

        const target = e.target;
        const selector = computeSelector(target);
        const text = (target.innerText || target.textContent || '').trim().slice(0, 60);

        outline.style.border = '2px solid #3b82f6';
        outline.style.background = 'rgba(59, 130, 246, 0.35)';

        if (window.__onTeachElementCaptured) {
            window.__onTeachElementCaptured({
                tag: target.tagName,
                id: target.id || null,
                name: target.getAttribute('name') || null,
                type: target.getAttribute('type') || null,
                placeholder: target.getAttribute('placeholder') || null,
                testId: target.getAttribute('data-testid') || null,
                ariaLabel: target.getAttribute('aria-label') || null,
                classes: target.className || null,
                text: text,
                selector: selector
            });
        }
    }, true);

    document.getElementById('__bt_skip').onclick = (e) => {
        e.stopPropagation();
        if (window.__onTeachElementSkipped) {
            window.__onTeachElementSkipped();
        }
    };

    document.getElementById('__bt_finish').onclick = (e) => {
        e.stopPropagation();
        if (window.__onTeachFinish) {
            window.__onTeachFinish();
        }
    };

    window.__updateTeacherBanner = (title, desc) => {
        const titleEl = document.getElementById('__bt_title');
        const descEl = document.getElementById('__bt_desc');
        if (titleEl) titleEl.innerText = title;
        if (descEl) descEl.innerText = desc;
        outline.style.border = '2px dashed #10b981';
        outline.style.background = 'rgba(16, 185, 129, 0.15)';
    };

    window.__removeTeacherUI = () => {
        banner.remove();
        outline.remove();
        window.__breakoutTeacherActive = false;
    };
})();
"""


class BreakoutTeacher:
    """Orchestrates step-by-step element learning for Breakout Terminal."""

    def __init__(self, cdp_port: int = 9222, user_data_dir: Optional[str] = None):
        self.cdp_port = cdp_port
        self.user_data_dir = user_data_dir or os.path.abspath("./data/breakout_profile")
        self.captured_selectors: Dict[str, Dict[str, Any]] = {}

        # Load existing selectors if available
        if os.path.exists(SELECTORS_FILE):
            try:
                with open(SELECTORS_FILE, "r") as f:
                    self.captured_selectors = json.load(f)
            except Exception:
                pass

        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._current_step_idx: int = 0
        self._step_future: Optional[asyncio.Future] = None
        self._is_finished: bool = False

    async def start(self, prefer_cdp: bool = True):
        console.rule("[bold cyan]Breakout Interactive Selector Teacher[/bold cyan]")
        console.print("[dim]This tool opens Breakout Terminal with an on-screen guide allowing you to click each element 1-by-1.[/dim]\n")

        self._pw = await async_playwright().start()

        if prefer_cdp and self.cdp_port:
            try:
                console.print(f"[cyan]Attempting connection to Chrome on port {self.cdp_port}...[/cyan]")
                self._browser = await self._pw.chromium.connect_over_cdp(f"http://localhost:{self.cdp_port}")
                self._context = self._browser.contexts[0]
                console.print("[bold green]✓ Attached to running Chrome via CDP![/bold green]")
            except Exception as e:
                console.print(f"[dim yellow]CDP not active ({e}). Launching persistent Chromium profile.[/dim yellow]")
                self._browser = None

        if not self._browser:
            os.makedirs(self.user_data_dir, exist_ok=True)
            self._context = await self._pw.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=False,
                viewport={"width": 1600, "height": 960},
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )

        # Locate Breakout page
        self._page = await self._locate_or_open_page()

        # Expose Python callbacks into the browser JavaScript runtime
        await self._page.expose_function("__onTeachElementCaptured", self._on_element_captured)
        await self._page.expose_function("__onTeachElementSkipped", self._on_element_skipped)
        await self._page.expose_function("__onTeachFinish", self._on_finish)

        # Inject teacher UI
        await self._page.evaluate(INJECTED_TEACHER_JS)

        console.print("[bold green]✓ Injected Teaching Overlay into Breakout Terminal![/bold green]")
        console.print("[yellow]Please ensure you are on the main Trading Terminal screen where the Order Ticket is visible.[/yellow]")
        console.print("[dim]Press Enter when you are ready on the Order Ticket...[/dim]")
        await asyncio.to_thread(input)

        # Re-inject in case of navigation
        await self._page.evaluate(INJECTED_TEACHER_JS)

        # Run the step-by-step loop
        await self._run_teaching_loop()

        # Save results
        self._save_selectors()
        await self._display_summary()

    async def _locate_or_open_page(self) -> Page:
        pages = self._context.pages
        for p in pages:
            if "breakout" in p.url.lower():
                console.print(f"[bold green]✓ Found active Breakout tab: {p.url}[/bold green]")
                return p
        page = pages[0] if pages else await self._context.new_page()
        await page.goto("https://portal.breakoutprop.com", wait_until="domcontentloaded")
        return page

    async def _run_teaching_loop(self):
        for idx, step in enumerate(TEACH_STEPS):
            if self._is_finished:
                break

            self._current_step_idx = idx
            key = step["key"]
            title = step["title"]
            instruction = step["instruction"]

            # Update on-screen banner
            try:
                await self._page.evaluate(
                    f"window.__updateTeacherBanner('Step {idx+1}/{len(TEACH_STEPS)}: {title}', '{instruction}')"
                )
            except Exception:
                pass

            console.print(
                Panel.fit(
                    f"[bold yellow]Step {idx + 1} of {len(TEACH_STEPS)}: {title}[/bold yellow]\n"
                    f"[white]{instruction}[/white]\n\n"
                    f"[dim](Click the element in your browser, or press 's' + Enter here to Skip, 'f' to Finish)[/dim]",
                    title=f"Target: {key}",
                )
            )

            # Wait for user click or console skip
            self._step_future = asyncio.get_running_loop().create_future()

            # Background task to also allow terminal input (s to skip, f to finish)
            console_task = asyncio.create_task(self._listen_terminal_input())

            try:
                action, data = await self._step_future
            finally:
                if not console_task.done():
                    console_task.cancel()

            if action == "captured":
                selector = data["selector"]
                self.captured_selectors[key] = {
                    "selector": selector,
                    "tag": data.get("tag"),
                    "text": data.get("text"),
                    "placeholder": data.get("placeholder"),
                    "testId": data.get("testId"),
                    "name": data.get("name"),
                }
                console.print(f"[bold green]✓ Captured '{title}':[/bold green] [cyan]{selector}[/cyan] (Text: '{data.get('text')}')\n")
            elif action == "skipped":
                console.print(f"[dim yellow]⤼ Skipped '{title}'.[/dim yellow]\n")
            elif action == "finish":
                console.print("[bold cyan]Finishing teaching session early as requested.[/bold cyan]")
                break

    async def _listen_terminal_input(self):
        """Allows user to skip/finish from the terminal as well as the browser."""
        loop = asyncio.get_running_loop()
        try:
            line = await loop.run_in_executor(None, input, "")
            line = line.strip().lower()
            if line == "s":
                if self._step_future and not self._step_future.done():
                    self._step_future.set_result(("skipped", None))
            elif line == "f":
                if self._step_future and not self._step_future.done():
                    self._step_future.set_result(("finish", None))
        except asyncio.CancelledError:
            pass

    def _on_element_captured(self, data: Dict[str, Any]):
        if self._step_future and not self._step_future.done():
            self._step_future.set_result(("captured", data))

    def _on_element_skipped(self):
        if self._step_future and not self._step_future.done():
            self._step_future.set_result(("skipped", None))

    def _on_finish(self):
        self._is_finished = True
        if self._step_future and not self._step_future.done():
            self._step_future.set_result(("finish", None))

    def _save_selectors(self):
        os.makedirs(os.path.dirname(SELECTORS_FILE), exist_ok=True)
        with open(SELECTORS_FILE, "w") as f:
            json.dump(self.captured_selectors, f, indent=2)
        console.print(f"\n[bold green]✓ Saved {len(self.captured_selectors)} selectors to {SELECTORS_FILE}![/bold green]")

    async def _display_summary(self):
        table = Table(title="Captured Breakout Selectors")
        table.add_column("Action / Field", style="cyan")
        table.add_column("Primary Selector", style="bold green")
        table.add_column("Element Text", style="yellow")

        for key, val in self.captured_selectors.items():
            table.add_row(key, val.get("selector", ""), val.get("text", ""))

        console.print(table)
        console.print(
            "\n[bold green]🎉 All actions successfully mapped![/bold green] "
            "You can now test placing an order using:\n"
            "[cyan]python scripts/breakout_cli.py --buy --size 100 --tp 70000 --sl 67000[/cyan]\n"
        )

        try:
            await self._page.evaluate("window.__removeTeacherUI()")
        except Exception:
            pass

        if self._context:
            await self._context.close()
        if self._pw:
            await self._pw.stop()


def main():
    parser = argparse.ArgumentParser(description="Breakout Selector Teacher")
    parser.add_argument("--cdp", action="store_true", help="Connect to running Chrome on port 9222")
    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP port (default 9222)")
    args = parser.parse_args()

    teacher = BreakoutTeacher(cdp_port=args.cdp_port)
    asyncio.run(teacher.start(prefer_cdp=args.cdp))


if __name__ == "__main__":
    main()
