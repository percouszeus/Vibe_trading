"""
app/main.py
───────────
Entry point for the trading platform.

Run with:
    python -m app.main
    # or after pip install -e .:
    trade
"""

from __future__ import annotations

import os
import sys
import socket
from pathlib import Path

# ── Force IPv4 — SEBI requires registered static IP for API orders ──
# Many ISPs assign both IPv4 and IPv6; Python may pick IPv6 by default,
# which won't match the registered IP on broker developer consoles.
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _ipv4_getaddrinfo

# ── Load .env before anything else ───────────────────────────
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ── Pull keychain credentials into env (after .env so .env wins) ─
from config.credentials import load_all as _load_keychain

_load_keychain()

from rich.console import Console

from brokers.session import login

console = Console()

BANNER = """
[bold cyan]
 ████████╗██████╗  █████╗ ██████╗ ███████╗
    ██╔══╝██╔══██╗██╔══██╗██╔══██╗██╔════╝
    ██║   ██████╔╝███████║██║  ██║█████╗
    ██║   ██╔══██╗██╔══██║██║  ██║██╔══╝
    ██║   ██║  ██║██║  ██║██████╔╝███████╗
    ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚══════╝
[/bold cyan]
[dim]  Vibe Trading  |  Indian stock & options platform[/dim]
"""


def main() -> None:
    console.print(BANNER)

    use_tui = "--tui" in sys.argv
    no_broker = "--no-broker" in sys.argv

    # Filter out --no-broker and --tui from the arguments to build the initial command
    cmd_args = [arg for arg in sys.argv[1:] if arg not in ("--no-broker", "--tui")]
    initial_command = cmd_args if cmd_args else None

    is_headless = (initial_command is not None) or (not sys.stdin.isatty())
    if is_headless:
        os.environ["_CLI_BATCH_MODE"] = "1"

    # ── Login ─────────────────────────────────────────────────
    if no_broker:
        # Register a mock broker with passthrough_market_data=True
        # so market data methods raise → fallback chain goes to yfinance
        # Account methods (funds, holdings) still return demo data
        console.print(
            "[dim]  Running without broker (--no-broker). Using yfinance for market data.[/dim]"
        )
        console.print("[dim]  To connect a real broker later, run 'login' in the REPL.[/dim]\n")
        from brokers.mock import MockBrokerAPI
        from brokers.session import register_broker

        mock = MockBrokerAPI(passthrough_market_data=True)
        mock.complete_login()
        register_broker("mock", mock, primary=True)
        broker = mock
    elif is_headless:
        # Headless mode: avoid interactive prompts at all costs
        from pathlib import Path
        from brokers.session import register_broker
        from brokers.mock import MockBrokerAPI

        home_dir = Path.home()
        zerodha_token = home_dir / ".trading_platform" / "zerodha.json"
        fyers_token = home_dir / ".trading_platform" / "fyers.json"

        broker = None
        if zerodha_token.exists():
            try:
                broker = login(choice="1")
            except Exception as e:
                console.print(f"[dim]  Failed to resume Zerodha: {e}[/dim]")
        elif fyers_token.exists():
            try:
                broker = login(choice="5")
            except Exception as e:
                console.print(f"[dim]  Failed to resume Fyers: {e}[/dim]")

        if broker is None or not broker.is_authenticated():
            console.print("[dim]  No active broker session found. Falling back to MockBroker (paper mode).[/dim]")
            mock = MockBrokerAPI(passthrough_market_data=True)
            mock.complete_login()
            register_broker("mock", mock, primary=True)
            broker = mock
    else:
        try:
            broker = login()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Login cancelled.[/yellow]")
            sys.exit(0)
        except Exception as e:
            console.print(f"\n[red]Login failed: {e}[/red]")
            console.print(
                "[yellow]Dropping into REPL with mock broker so you can fix credentials.[/yellow]"
            )
            console.print("[dim]  Run 'credentials list' to see saved credentials[/dim]")
            console.print("[dim]  Run 'credentials clear' to wipe all and start fresh[/dim]")
            console.print("[dim]  Run 'login' to try again[/dim]\n")
            from brokers.mock import MockBrokerAPI
            from brokers.session import register_broker

            mock = MockBrokerAPI(passthrough_market_data=True)
            mock.complete_login()
            register_broker("mock", mock, primary=True)
            broker = mock

    # ── AI provider setup (runs once if not yet configured) ──────
    from agent.core import ensure_ai_provider_configured

    ensure_ai_provider_configured()



    if use_tui:
        # Launch Textual TUI
        from ui.app import run_tui

        run_tui()
    else:
        # Drop into REPL (default)
        from app.repl import run_repl

        run_repl(broker, initial_command=initial_command)


if __name__ == "__main__":
    exit_code = 0
    try:
        main()
    except Exception as e:
        console.print(f"[red]Fatal error: {e}[/red]")
        import traceback

        traceback.print_exc()
        exit_code = 1
    finally:
        # Give daemon threads 2 seconds to finish, then force exit
        # if they don't (WebSocket SDK can hold non-daemon threads)
        import threading

        non_daemon = [
            t
            for t in threading.enumerate()
            if t.is_alive() and not t.daemon and t != threading.main_thread()
        ]
        if non_daemon:
            # Non-daemon threads exist (e.g. WebSocket SDK) — wait up to
            # 2 seconds for them to finish, then force exit.
            for t in non_daemon:
                t.join(timeout=2)
            # If any are still alive after the wait, force kill
            still_alive = [t for t in non_daemon if t.is_alive()]
            if still_alive:
                os._exit(exit_code)
            else:
                sys.exit(exit_code)
        else:
            sys.exit(exit_code)
