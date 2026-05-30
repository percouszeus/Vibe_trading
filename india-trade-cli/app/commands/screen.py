"""
app/commands/screen.py
──────────────────────
Market screening command.
Uses MarketScanner to filter stocks from a given universe.
"""

from __future__ import annotations
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from engine.scanner import MarketScanner
from market.symbols import NIFTY_50

console = Console()

def run(universe: str = "NIFTY50", strategy: str = "momentum") -> None:
    """
    Scans the market and prints a table of candidates.
    """
    symbols = NIFTY_50 if universe == "NIFTY50" else universe.split(",")
    scanner = MarketScanner(symbols)
    
    console.print(f"\n[bold cyan]🔍 Scanning {universe} using {strategy} strategy...[/bold cyan]")
    
    if strategy == "momentum":
        results = scanner.scan_for_momentum()
        _print_momentum_table(results)
    elif strategy == "mean_reversion":
        results = scanner.scan_for_mean_reversion()
        _print_mean_reversion_table(results)
    else:
        console.print(f"[red]Unknown strategy: {strategy}[/red]")

def _print_momentum_table(results: list[dict]) -> None:
    if not results:
        console.print("[yellow]No candidates found.[/yellow]")
        return
        
    table = Table(title="Momentum Candidates")
    table.add_column("Symbol", style="cyan")
    table.add_column("Price", justify="right")
    table.add_column("RSI", justify="right")
    table.add_column("Vol Ratio", justify="right")
    table.add_column("Score", justify="right", style="bold green")
    
    for r in results:
        table.add_row(
            r['symbol'],
            f"₹{r['close']:.2f}",
            f"{r['rsi']:.1f}",
            f"{r['vol_ratio']:.2f}x",
            f"{r['score']:.2f}"
        )
    
    console.print(table)

def _print_mean_reversion_table(results: list[dict]) -> None:
    if not results:
        console.print("[yellow]No candidates found.[/yellow]")
        return
        
    table = Table(title="Mean Reversion Candidates")
    table.add_column("Symbol", style="cyan")
    table.add_column("Price", justify="right")
    table.add_column("RSI", justify="right", style="bold red")
    table.add_column("BB Lower %", justify="right")
    
    for r in results:
        table.add_row(
            r['symbol'],
            f"₹{r['close']:.2f}",
            f"{r['rsi']:.1f}",
            f"{r['bb_diff']:.2f}%"
        )
    
    console.print(table)
