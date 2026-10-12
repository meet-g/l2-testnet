import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path when running ui/dashboard.py directly
ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from engine.backtester import EdgeEvaluator


class TerminalDashboard:
    """Rich interactive dashboard displaying live Hyperliquid L2 microstructure and alpha telemetry."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def make_header(self, book: OrderBook, trades: TradeManager, network: str = "Testnet") -> Panel:
        mid = book.mid_price
        spread = book.spread
        spread_bps = book.spread_bps
        bid_vol_5, ask_vol_5 = book.get_depth_volume(5)
        vpin = trades.calculate_vpin(20)
        vpin_str = f"{vpin:.2f}" if vpin is not None else "Init"

        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=2)
        grid.add_column(justify="center", ratio=3)
        grid.add_column(justify="right", ratio=2)

        coin = (getattr(book, "coin", None) or getattr(trades, "coin", None) or "BTC").upper()
        net_badge = f"[bold magenta][{network.upper()}][/bold magenta]"
        left_text = Text.from_markup(
            f"[bold cyan]HYPERLIQUID L2 ENGINE[/bold cyan] {net_badge} | Coin: [bold yellow]{coin}[/bold yellow] | "
            f"Updates: [green]{book.update_count}[/green]"
        )

        ctx_suffix = ""
        if book.oracle_price > 0:
            basis_c = "green" if abs(book.basis_bps) < 3.0 else ("yellow" if abs(book.basis_bps) < 7.0 else "red")
            ctx_suffix += f" | Basis: [{basis_c}]{book.basis_bps:+.1f}b[/{basis_c}]"
        if book.open_interest > 0:
            ctx_suffix += f" | OI: [bold yellow]{book.open_interest:,.0f}b[/bold yellow]"

        mid_str = f"${mid:,.4f}" if mid < 10 else (f"${mid:,.2f}" if mid < 1000 else f"${mid:,.1f}")
        mid_text = Text.from_markup(
            f"Mid: [bold white]{mid_str}[/bold white] | Sprd: [yellow]{spread_bps:.2f}b[/yellow] | "
            f"Depth5: [green]{bid_vol_5:.1f}[/green]/[red]{ask_vol_5:.1f}[/red] {coin}{ctx_suffix}"
        )

        right_text = Text.from_markup(
            f"CVD: [{'green' if trades.total_cvd >= 0 else 'red'}]{trades.total_cvd:+.2f} {coin}[/] | "
            f"VPIN: [bold magenta]{vpin_str}[/bold magenta]"
            + (f" | Fund: [{ 'green' if book.funding_rate >= 0 else 'red'}]{book.funding_rate * 100:+.4f}%[/]" if book.funding_rate != 0 else "")
        )

        grid.add_row(left_text, mid_text, right_text)
        return Panel(grid, style="bold white on blue", height=3)

    def make_orderbook_panel(self, book: OrderBook, levels_to_show: int = 8) -> Panel:
        table = Table(box=None, expand=True, padding=(0, 1))
        table.add_column("Bids (sz)", justify="right", style="green")
        table.add_column("n", justify="right", style="dim green")
        table.add_column("Bid Px", justify="right", style="bold green")
        table.add_column("|", justify="center", style="dim white")
        table.add_column("Ask Px", justify="left", style="bold red")
        table.add_column("n", justify="left", style="dim red")
        table.add_column("Asks (sz)", justify="left", style="red")

        max_sz = 1.0
        for l in book.bids[:levels_to_show] + book.asks[:levels_to_show]:
            if l.sz > max_sz:
                max_sz = l.sz

        n_rows = min(levels_to_show, len(book.bids), len(book.asks))
        if n_rows == 0:
            table.add_row("[dim]Awaiting L2 order book...[/dim]", "-", "-", "|", "-", "-", "-")
        else:
            for i in range(n_rows):
                b = book.bids[i]
                a = book.asks[i]

                b_bars = "█" * int(min(12, (b.sz / max_sz) * 12))
                a_bars = "█" * int(min(12, (a.sz / max_sz) * 12))

                b_whale = " ★" if b.sz >= 5.0 and b.n <= 2 else ""
                a_whale = " ★" if a.sz >= 5.0 and a.n <= 2 else ""

                px_fmt = "{:,.4f}" if book.mid_price < 10 else ("{:,.2f}" if book.mid_price < 1000 else "{:,.1f}")
                table.add_row(
                    f"{b.sz:.3f} {b_bars}{b_whale}",
                    f"{b.n}",
                    f"{px_fmt.format(b.px)}",
                    "|",
                    f"{px_fmt.format(a.px)}",
                    f"{a.n}",
                    f"{a_whale}{a_bars} {a.sz:.3f}",
                )

        return Panel(table, title="[bold]L2 Depth (Top 8 Levels)[/bold]", border_style="cyan")

    def make_signals_panel(self, signals_dict: Dict[str, Any]) -> Panel:
        table = Table(box=None, expand=True, padding=(0, 1))
        table.add_column("Signal", justify="left", style="bold white")
        table.add_column("Score Gauge", justify="center")
        table.add_column("Score", justify="right")
        table.add_column("Conf", justify="right", style="dim")

        if not signals_dict:
            table.add_row("[dim]Awaiting order book / alpha computation...[/dim]", "-", "-", "-")
            return Panel(table, title="[bold]Microstructure Alpha Telemetry[/bold]", border_style="magenta")

        for name, sig in signals_dict.items():
            if name == "Sweep":
                continue
            is_enabled = sig.metadata.get("enabled", True) if sig.metadata else True
            if not is_enabled:
                table.add_row(
                    f"[dim]{name}[/dim]",
                    "[dim]    [DISABLED]    [/dim]",
                    "[dim]OFF[/dim]",
                    "[dim]-[/dim]",
                )
                continue

            val = sig.score
            # Make visual bar gauge: [-1.0 ... 0 ... +1.0]
            # 10 chars each side
            if val >= 0:
                bar = " " * 8 + "[white]|[/white]" + "[green]" + "█" * int(val * 8) + "[/green]" + " " * (8 - int(val * 8))
            else:
                bar = " " * (8 - int(abs(val) * 8)) + "[red]" + "█" * int(abs(val) * 8) + "[/red]" + "[white]|[/white]" + " " * 8

            score_color = "green" if val > 0.15 else ("red" if val < -0.15 else "white")
            table.add_row(
                name,
                bar,
                f"[{score_color}]{val:+.2f}[/{score_color}]",
                f"{int(sig.confidence * 100)}%",
            )

        return Panel(table, title="[bold]Microstructure Alpha Signals[/bold]", border_style="magenta")

    def make_performance_panel(self, evaluator: EdgeEvaluator, current_price: float) -> Panel:
        table = Table(box=None, expand=True, padding=(0, 1))
        table.add_column("Strategy", justify="left", style="bold")
        table.add_column("Type", justify="center", style="dim cyan")
        table.add_column("Pos", justify="center")
        table.add_column("Trades", justify="right")
        table.add_column("Win%", justify="right")
        table.add_column("Gross ($)", justify="right")
        table.add_column("Fees ($)", justify="right")
        table.add_column("Net ($)", justify="right", style="bold")
        table.add_column("IC (5s)", justify="right")

        if not evaluator.strategy_names:
            table.add_row("[dim]No strategies enabled (check strategies.json)[/dim]", "-", "-", "-", "-", "-", "-", "-", "-")
            return Panel(table, title="[bold]Live Edge & Paper Performance[/bold]", border_style="green")

        for s_name in evaluator.strategy_names:
            perf = evaluator.get_strategy_performance(s_name, current_price)
            ic_data = evaluator.get_signal_metrics(s_name, horizon_secs=5)

            gross = perf.get("gross_pnl_usd", 0.0)
            gross_color = "green" if gross >= 0 else "red"
            fees = perf.get("fees_paid_usd", 0.0)
            fees_str = f"[red]-${fees:.2f}[/red]" if fees > 0 else (f"[green]+${abs(fees):.2f}[/green]" if fees < 0 else "$0.00")
            pnl = perf.get("total_pnl_usd", 0.0)
            pnl_color = "green" if pnl >= 0 else "red"

            pos_val = perf.get("position_btc", 0.0)
            pos_str = f"[bold green]+{pos_val:.2f}[/]" if pos_val > 0 else (f"[bold red]{pos_val:.2f}[/]" if pos_val < 0 else "[dim]-[/]")

            ic_val = ic_data.get("ic", 0.0)
            ic_color = "green" if ic_val > 0.02 else ("red" if ic_val < -0.02 else "white")
            exec_type = perf.get("type", "MAKER")

            table.add_row(
                s_name,
                exec_type,
                pos_str,
                f"{perf.get('trades', 0)}",
                f"{perf.get('win_rate_pct', 0.0):.1f}%",
                f"[{gross_color}]${gross:+.2f}[/{gross_color}]",
                fees_str,
                f"[{pnl_color}]${pnl:+.2f}[/{pnl_color}]",
                f"[{ic_color}]{ic_val:+.3f}[/{ic_color}]",
            )

        return Panel(table, title="[bold]Live Edge & Paper Performance[/bold]", border_style="green")

    def make_trades_panel(self, trades: TradeManager, count: int = 5) -> Panel:
        recent = list(trades.trades)[-count:]
        coin = (getattr(trades, "coin", None) or "BTC").upper()
        table = Table(box=None, expand=True, padding=(0, 1))
        table.add_column("Time", justify="left", style="dim")
        table.add_column("Side", justify="center")
        table.add_column("Price", justify="right")
        table.add_column(f"Size ({coin})", justify="right")
        table.add_column("Type", justify="right")

        if not recent:
            table.add_row("[dim]Awaiting taker trades...[/dim]", "-", "-", "-", "-")
        else:
            for t in reversed(recent):
                time_str = time.strftime("%H:%M:%S", time.localtime(t.timestamp_ms / 1000))
                side_str = "[bold green]BUY[/bold green]" if t.is_buy else "[bold red]SELL[/bold red]"
                tag = "[bold magenta]LARGE[/bold magenta]" if t.size >= 1.0 else "retail"
                px_str = f"${t.price:,.4f}" if t.price < 10 else (f"${t.price:,.2f}" if t.price < 1000 else f"${t.price:,.1f}")
                table.add_row(
                    time_str,
                    side_str,
                    px_str,
                    f"{t.size:.4f}",
                    tag,
                )

        return Panel(table, title="[bold]Recent Taker Trades[/bold]", border_style="yellow")

    def make_strategy_activity_panel(self, evaluator: EdgeEvaluator, current_price: float, count: int = 4) -> Panel:
        """Renders currently open positions and real-time position open/close activity log."""
        active = evaluator.get_active_positions(current_price)
        events = evaluator.get_recent_position_events(limit=count)

        elements = []

        # 1. Active Open Positions Section
        if active:
            pos_table = Table(box=None, expand=True, padding=(0, 1))
            pos_table.add_column("Active Position", justify="left", style="bold cyan")
            pos_table.add_column("Side/Sz", justify="center")
            pos_table.add_column("Entry Px", justify="right")
            pos_table.add_column("Unrealized PnL", justify="right")
            pos_table.add_column("Stop", justify="right", style="dim")
            pos_table.add_column("Hold", justify="right", style="dim")

            for p in active:
                side_style = "bold green" if p["side"] == "LONG" else "bold red"
                pnl = p["unrealized_pnl_usd"]
                pnl_c = "green" if pnl >= 0 else "red"
                trail_star = " ★" if p["trailing_active"] else ""
                pos_table.add_row(
                    f"● {p['strategy']}",
                    f"[{side_style}]{p['side']} {p['size_btc']:.2f}[/{side_style}]",
                    f"${p['entry_price']:,.1f}",
                    f"[{pnl_c}]${pnl:+.2f} ({p['unrealized_bps']:+.1f}b)[/{pnl_c}]",
                    f"${p['stop_price']:,.1f}{trail_star}",
                    f"{p['hold_secs']:.1f}s",
                )
            elements.append(pos_table)
        else:
            elements.append(
                Text.from_markup(
                    "[dim green]● No open positions[/dim green] [dim]| All capital liquid | Quoting & scanning order book...[/dim]"
                )
            )

        # 2. Recent Position Actions (Open / Close lifecycle)
        if events:
            ev_table = Table(box=None, expand=True, padding=(0, 1))
            ev_table.add_column("Time", justify="left", style="dim")
            ev_table.add_column("Action", justify="center")
            ev_table.add_column("Strategy", justify="left")
            ev_table.add_column("Side/Sz", justify="center")
            ev_table.add_column("Price", justify="right")
            ev_table.add_column("Exec", justify="center", style="dim")
            ev_table.add_column("PnL / Reason", justify="right")

            for ev in reversed(events):
                time_str = time.strftime("%H:%M:%S", time.localtime(ev["time_ms"] / 1000))
                is_open = (ev["event"] == "OPEN")
                action_str = "[bold green]OPEN[/bold green]" if is_open else "[bold yellow]CLOSE[/bold yellow]"
                side_str = f"[green]{ev['side']}[/green]" if ev["side"] == "LONG" else f"[red]{ev['side']}[/red]"
                side_sz = f"{side_str} {ev['size_btc']:.2f}"

                if is_open:
                    pnl_reason = f"[dim]Stop: ${ev.get('stop_price', 0.0):,.0f} | {ev.get('reason', '')}[/dim]"
                else:
                    pnl = ev.get("net_pnl", 0.0)
                    bps = ev.get("return_bps", 0.0)
                    pnl_c = "green" if pnl >= 0 else "red"
                    reason = ev.get("reason", "")
                    pnl_reason = f"[{pnl_c}]${pnl:+.2f} ({bps:+.1f}b)[/{pnl_c}] [dim]{reason}[/dim]"

                ev_table.add_row(
                    time_str,
                    action_str,
                    ev["strategy"],
                    side_sz,
                    f"${ev['price']:,.1f}",
                    ev.get("exec", "MAKER"),
                    pnl_reason,
                )
            elements.append(ev_table)
        else:
            elements.append(
                Text.from_markup("[dim]Awaiting signal conviction triggers to execute initial positions...[/dim]")
            )

        return Panel(
            Group(*elements),
            title="[bold]Strategy Positions & Order Activity (Open / Closed)[/bold]",
            border_style="cyan",
        )

    def render(
        self,
        book: OrderBook,
        trades: TradeManager,
        signals_dict: Dict[str, Any],
        evaluator: EdgeEvaluator,
        network: str = "Testnet",
    ) -> Layout:
        """Constructs full dashboard grid layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=10),
        )

        layout["main"].split_row(
            Layout(name="book", ratio=3),
            Layout(name="signals", ratio=3),
            Layout(name="perf", ratio=3),
        )

        layout["footer"].split_row(
            Layout(name="market_trades", ratio=4),
            Layout(name="strategy_activity", ratio=6),
        )

        layout["header"].update(self.make_header(book, trades, network=network))
        layout["book"].update(self.make_orderbook_panel(book))
        layout["signals"].update(self.make_signals_panel(signals_dict))
        layout["perf"].update(self.make_performance_panel(evaluator, book.mid_price))
        layout["market_trades"].update(self.make_trades_panel(trades, count=5))
        layout["strategy_activity"].update(
            self.make_strategy_activity_panel(evaluator, book.mid_price, count=4)
        )

        return layout


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Hyperliquid L2 Microstructure Alpha Dashboard")
    parser.add_argument("--testnet", action="store_true", help="Connect to Hyperliquid Testnet")
    parser.add_argument("--mainnet", action="store_true", help="Connect to Hyperliquid Mainnet")
    parser.add_argument("--duration", type=int, default=0, help="Run duration in seconds (0 = indefinite)")
    parser.add_argument("--coin", type=str, default="BTC", help="Target coin (default: BTC)")
    args = parser.parse_args()

    from config import AppConfig
    from main import L2EngineRunner

    cfg = AppConfig()
    cfg.market.coin = args.coin.upper()
    if args.testnet:
        cfg.hyperliquid.use_testnet = True
    elif args.mainnet:
        cfg.hyperliquid.use_testnet = False

    net = cfg.hyperliquid.network_name.upper()
    print(f"Launching Hyperliquid L2 Dashboard directly on {net} ({cfg.market.coin})...")
    runner = L2EngineRunner(config=cfg, record_data=False)
    try:
        asyncio.run(runner.run_live(duration_secs=args.duration if args.duration > 0 else None, show_ui=True))
    except KeyboardInterrupt:
        pass
