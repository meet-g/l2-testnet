"""Breakout Prop Firm CLI Test & Execution Harness.

Allows testing, calibrating, and manually triggering orders, stop loss, take profit,
and risk checks against the Breakout Prop Terminal before integrating into main.py.

Usage examples:
  # 1. First-time setup: Open browser to log in and save session cookies
  python scripts/breakout_cli.py --login

  # 2. Check account balance, drawdown, and open positions
  python scripts/breakout_cli.py --status

  # 3. Test Buy Order with Take Profit and Stop Loss
  python scripts/breakout_cli.py --buy --size 100 --tp 69500 --sl 67500

  # 4. Test Sell Order with Take Profit and Stop Loss
  python scripts/breakout_cli.py --sell --size 100 --tp 66000 --sl 68500

  # 5. Market Close active position
  python scripts/breakout_cli.py --close

  # 6. Emergency Flatten (Panic Button)
  python scripts/breakout_cli.py --panic

  # 7. Inspect Terminal DOM Elements (for selector diagnostics)
  python scripts/breakout_cli.py --inspect
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

from rich.console import Console
from rich.table import Table

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.breakout_executor import BreakoutExecutor, OrderIntent, OrderSide, OrderType, SizeMode

console = Console()


async def run_cli():
    parser = argparse.ArgumentParser(description="Breakout Prop Firm Execution CLI")
    parser.add_argument("--login", action="store_true", help="Launch visible browser to log in and persist profile")
    parser.add_argument("--status", action="store_true", help="Display account balance, drawdown, and active positions")
    parser.add_argument("--inspect", action="store_true", help="Inspect and dump DOM elements for selector debugging")
    parser.add_argument("--buy", action="store_true", help="Submit a Buy / Long order")
    parser.add_argument("--sell", action="store_true", help="Submit a Sell / Short order")
    parser.add_argument("--close", action="store_true", help="Market close active position")
    parser.add_argument("--panic", action="store_true", help="Cancel all orders and close all positions immediately")
    parser.add_argument("--api", action="store_true", help="Execute order directly via internal API (bypasses DOM clicking)")
    parser.add_argument("--account-id", type=str, default="WPYC-77BL-ULG8-F9AK", help="Breakout account ID for API orders")
    
    parser.add_argument("--symbol", type=str, default="BTC-USD", help="Target symbol (default: BTC-USD)")
    parser.add_argument("--size", type=float, default=100.0, help="Order size (USD notional or units)")
    parser.add_argument("--size-mode", choices=["USD", "UNITS", "CONTRACTS"], default="USD", help="Size mode (default: USD)")
    parser.add_argument("--limit", type=float, default=None, help="Limit price (if omitted, submits Market order)")
    parser.add_argument("--tp", type=float, default=None, help="Take Profit price")
    parser.add_argument("--sl", type=float, default=None, help="Stop Loss price")
    parser.add_argument("--cdp-port", type=int, default=9222, help="Chrome DevTools Protocol port (default: 9222)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")

    args = parser.parse_args()

    executor = BreakoutExecutor(
        cdp_port=args.cdp_port,
        headless=args.headless and not args.login,
        console=console,
    )

    console.rule("[bold cyan]Breakout Prop Firm Execution Client[/bold cyan]")

    try:
        await executor.connect()

        # Mode: Login / Setup
        if args.login:
            console.print("[bold yellow]Browser opened for authentication.[/bold yellow]")
            console.print("Please log into Breakout, solve 2FA, and navigate to the trading terminal.")
            console.print("[dim]Press Enter in this console when finished to save session and exit...[/dim]")
            await asyncio.to_thread(input)
            console.print("[bold green]✓ Session cookies saved to data/breakout_profile![/bold green]")
            return

        # Mode: DOM Inspection
        if args.inspect:
            console.print("[dim cyan]Inspecting Breakout Terminal DOM elements...[/dim cyan]")
            dom_data = await executor.inspect_terminal_dom()
            
            # Print Inputs
            input_table = Table(title="Detected Input Fields")
            input_table.add_column("Tag", style="cyan")
            input_table.add_column("Name", style="magenta")
            input_table.add_column("Placeholder", style="green")
            input_table.add_column("TestID", style="yellow")
            
            for inp in dom_data.get("inputs", [])[:15]:
                input_table.add_row(
                    inp.get("tag") or "",
                    inp.get("name") or "",
                    inp.get("placeholder") or "",
                    inp.get("testId") or "",
                )
            console.print(input_table)

            # Print Buttons
            btn_table = Table(title="Detected Buttons & Tabs")
            btn_table.add_column("Text", style="bold green")
            btn_table.add_column("Role/Type", style="cyan")
            btn_table.add_column("TestID", style="yellow")
            
            for btn in dom_data.get("buttons", [])[:20]:
                btn_table.add_row(
                    btn.get("text") or "",
                    btn.get("type") or "",
                    btn.get("testId") or "",
                )
            console.print(btn_table)
            return

        # Mode: Account Status
        if args.status:
            telemetry = await executor.refresh_account_telemetry()
            positions = await executor.get_open_positions()

            status_table = Table(title="Breakout Account Telemetry")
            status_table.add_column("Metric", style="cyan")
            status_table.add_column("Value", style="bold yellow")

            status_table.add_row("Balance", f"${telemetry.balance:,.2f}")
            status_table.add_row("Equity", f"${telemetry.equity:,.2f}")
            status_table.add_row("Daily Drawdown", f"{telemetry.daily_drawdown_pct:.2f}% (Limit: {telemetry.daily_drawdown_limit_pct}%)")
            status_table.add_row("Daily Limit Status", "[bold red]BREACHED[/bold red]" if telemetry.is_daily_limit_breached else "[bold green]SAFE[/bold green]")
            console.print(status_table)

            if positions:
                pos_table = Table(title="Open Positions")
                pos_table.add_column("Symbol", style="cyan")
                pos_table.add_column("Side", style="magenta")
                pos_table.add_column("Size", style="green")
                pos_table.add_column("Entry Px", style="yellow")
                pos_table.add_column("Mark Px", style="yellow")
                pos_table.add_column("Unrealized PnL", style="bold green")
                for p in positions:
                    pos_table.add_row(
                        p.symbol,
                        p.side,
                        f"{p.size:,.4f}",
                        f"${p.entry_price:,.2f}",
                        f"${p.mark_price:,.2f}",
                        f"${p.unrealized_pnl:+,.2f}",
                    )
                console.print(pos_table)
            else:
                console.print("[dim yellow]No active open positions detected.[/dim yellow]")
            return

        # Mode: Buy Order
        if args.buy:
            if args.api:
                res = await executor.place_api_order(
                    account_id=args.account_id,
                    pair=args.symbol,
                    side="buy",
                    volume=str(args.size),
                    price=str(args.limit) if args.limit else None,
                    order_type="limit" if args.limit else "market",
                )
                console.print(f"[bold]Direct API Buy Result:[/bold] {res}")
                return

            intent = OrderIntent(
                side=OrderSide.BUY,
                symbol=args.symbol,
                size=args.size,
                size_mode=SizeMode(args.size_mode),
                order_type=OrderType.LIMIT if args.limit else OrderType.MARKET,
                price=args.limit,
                take_profit_price=args.tp,
                stop_loss_price=args.sl,
            )
            res = await executor.place_order(intent)
            console.print(f"[bold]Order Result:[/bold] {res}")
            return

        # Mode: Sell Order
        if args.sell:
            if args.api:
                res = await executor.place_api_order(
                    account_id=args.account_id,
                    pair=args.symbol,
                    side="sell",
                    volume=str(args.size),
                    price=str(args.limit) if args.limit else None,
                    order_type="limit" if args.limit else "market",
                )
                console.print(f"[bold]Direct API Sell Result:[/bold] {res}")
                return

            intent = OrderIntent(
                side=OrderSide.SELL,
                symbol=args.symbol,
                size=args.size,
                size_mode=SizeMode(args.size_mode),
                order_type=OrderType.LIMIT if args.limit else OrderType.MARKET,
                price=args.limit,
                take_profit_price=args.tp,
                stop_loss_price=args.sl,
            )
            res = await executor.place_order(intent)
            console.print(f"[bold]Order Result:[/bold] {res}")
            return

        # Mode: Close Position
        if args.close:
            success = await executor.close_position(symbol=args.symbol)
            console.print(f"[bold]Close Result:[/bold] {'Success' if success else 'Failed'}")
            return

        # Mode: Emergency Flatten
        if args.panic:
            flatten_res = await executor.emergency_flatten()
            console.print(f"[bold red]Panic Flatten Complete:[/bold red] {flatten_res}")
            return

        # Default if no action specified: display help
        parser.print_help()

    finally:
        await executor.close()


def main():
    asyncio.run(run_cli())


if __name__ == "__main__":
    main()
