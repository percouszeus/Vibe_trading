"""
scripts/validate_setup.py
──────────────────────────
Pre-flight validation — checks that all components are properly
configured before attempting to run the trading system.

Run: python scripts/validate_setup.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

# ── Colors (ASCII-safe for Windows cp1252) ───────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}[OK]{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}[FAIL]{NC} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}[WARN]{NC} {msg}")


def info(msg: str) -> None:
    print(f"  {CYAN}[INFO]{NC} {msg}")


def header(msg: str) -> None:
    print(f"\n{BOLD}=== {msg} ==={NC}")


# ── Checks ───────────────────────────────────────────────────

def check_python() -> bool:
    """Verify Python version >= 3.11."""
    header("Python Environment")
    v = sys.version_info
    if v.major >= 3 and v.minor >= 11:
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    else:
        fail(f"Python {v.major}.{v.minor} — need >= 3.11")
        return False


def check_repos() -> bool:
    """Verify all required repos are cloned."""
    header("Repository Structure")
    root = Path(__file__).resolve().parent.parent
    all_ok = True

    repos = {
        "core-engine": "HKUDS/Vibe-Trading",
        "india-trade-cli": "hopit-ai/india-trade-cli",
        "kite-mcp": "zerodha/kite-mcp-server",
    }

    for dirname, repo_name in repos.items():
        repo_path = root / dirname
        if repo_path.exists() and (repo_path / ".git").exists():
            ok(f"{dirname}/ ({repo_name})")
        else:
            fail(f"{dirname}/ missing — run: git clone https://github.com/{repo_name}.git {dirname}")
            all_ok = False

    return all_ok


def check_env() -> bool:
    """Verify .env file exists and has critical settings."""
    header("Environment Configuration")
    root = Path(__file__).resolve().parent.parent
    env_file = root / ".env"

    if not env_file.exists():
        fail(".env file not found - copy from .env.example")
        return False

    ok(".env file exists")

    # Read and check critical keys
    env_vars = {}
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()

    # Trading mode MUST be PAPER
    mode = env_vars.get("TRADING_MODE", "")
    if mode == "PAPER":
        ok(f"TRADING_MODE = PAPER (safe)")
    elif mode == "LIVE":
        # Replace em-dash with ASCII
        fail("TRADING_MODE = LIVE - this is DANGEROUS! Change to PAPER!")
        return False
    else:
        warn(f"TRADING_MODE = '{mode}' - should be PAPER")

    # Capital
    capital = env_vars.get("TOTAL_CAPITAL", "0")
    ok(f"TOTAL_CAPITAL = INR {int(capital):,}")

    # LLM provider
    provider = env_vars.get("LANGCHAIN_PROVIDER", "")
    model = env_vars.get("LANGCHAIN_MODEL_NAME", "")
    ok(f"Primary LLM: {provider}/{model}")

    # Broker keys
    kite_key = env_vars.get("KITE_API_KEY", "")
    if kite_key and kite_key != "your_kite_api_key_here":
        ok("Kite API key configured")
    else:
        warn("Kite API key not set - paper trading with local simulation only")

    # OpenRouter fallback
    or_key = env_vars.get("OPENROUTER_API_KEY", "")
    if or_key and or_key != "sk-or-v1-YOUR_KEY_HERE":
        ok("OpenRouter fallback configured")
    else:
        info("OpenRouter fallback not configured (optional)")

    # Telegram
    tg_token = env_vars.get("TELEGRAM_BOT_TOKEN", "")
    if tg_token and tg_token != "your_bot_token_here":
        ok("Telegram alerts configured")
    else:
        info("Telegram alerts not configured (optional)")

    return True


def check_ollama() -> bool:
    """Check if Ollama is installed and running."""
    header("Ollama (LLM Server)")

    # Check installation
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            ok(f"Ollama installed: {result.stdout.strip()}")
        else:
            fail("Ollama not responding")
            return False
    except FileNotFoundError:
        warn("Ollama not installed - install from https://ollama.com")
        info("Local LLM will not work, but OpenRouter/NIM fallbacks can be used")
        return False
    except Exception as e:
        warn(f"Ollama check failed: {e}")
        return False

    # Check if server is running
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            model_names = [m["name"] for m in models]
            ok(f"Ollama server running — {len(models)} models available")
            for m in model_names[:5]:
                info(f"  Model: {m}")
            if not any("llama3" in m for m in model_names):
                warn("llama3.1:8b not found - run: ollama pull llama3.1:8b")
        else:
            warn("Ollama server responded but with unexpected status")
    except ImportError:
        warn("httpx not installed — skipping Ollama connectivity test")
        info("Install with: pip install httpx")
    except Exception:
        warn("Ollama server not running - start with: ollama serve")
        info("You can still use OpenRouter/NIM as LLM backends")

    return True


def check_india_trade_cli() -> bool:
    """Check if india-trade-cli can be imported."""
    header("india-trade-cli (Analysis Engine)")
    root = Path(__file__).resolve().parent.parent
    cli_path = root / "india-trade-cli"

    if not cli_path.exists():
        fail("india-trade-cli directory not found")
        return False

    # Check if key modules exist
    modules = [
        ("engine/paper.py", "PaperBroker"),
        ("engine/memory.py", "TradeMemory"),
        ("engine/drift.py", "DriftDetection"),
        ("engine/strategy_builder.py", "StrategyBuilder"),
        ("engine/backtest.py", "Backtester"),
        ("agent/__init__.py", "Agent framework"),
        ("brokers/base.py", "Broker abstraction"),
        ("market/quotes.py", "Market data"),
    ]

    all_ok = True
    for module_path, description in modules:
        full_path = cli_path / module_path
        if full_path.exists():
            ok(f"{module_path} ({description})")
        else:
            warn(f"{module_path} not found — {description} unavailable")

    return all_ok


def check_orchestrator() -> bool:
    """Check if the orchestrator module can be imported."""
    header("Orchestrator")
    root = Path(__file__).resolve().parent.parent

    # Add project root to path
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        from orchestrator.config import load_config
        cfg = load_config()
        ok(f"Config loaded: mode={cfg.trading.mode}, capital=INR {cfg.trading.total_capital:,.0f}")
        ok(f"LLM: {cfg.llm.primary_provider}/{cfg.llm.primary_model}")
        ok(f"Universe: {cfg.trading.stock_universe}")
        return True
    except ImportError as e:
        fail(f"Import error: {e}")
        info("Install deps: pip install python-dotenv httpx")
        return False
    except Exception as e:
        fail(f"Config load failed: {e}")
        return False


def check_disk_space() -> bool:
    """Check available disk space."""
    header("System Resources")
    import shutil

    # Check disk
    try:
        disk = shutil.disk_usage(Path.home())
        free_gb = disk.free / (1024**3)
        total_gb = disk.total / (1024**3)
        if free_gb > 10:
            ok(f"Disk: {free_gb:.1f}GB free / {total_gb:.1f}GB total")
        elif free_gb > 5:
            warn(f"Disk: {free_gb:.1f}GB free - getting low")
        else:
            fail(f"Disk: {free_gb:.1f}GB free - critically low!")
            return False
    except Exception:
        warn("Could not check disk space")

    # Check RAM (platform-dependent)
    try:
        import platform
        if platform.system() == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_kb = int(line.split()[1])
                        mem_gb = mem_kb / 1024 / 1024
                        ok(f"RAM: {mem_gb:.1f}GB total")
                        break
        else:
            info(f"Platform: {platform.system()} - RAM check skipped")
    except Exception:
        pass

    return True


# ── Main ─────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}{'='*60}")
    print("  Vibe Trading India — Pre-flight Validation")
    print(f"{'='*60}{NC}\n")

    checks = [
        ("Python", check_python),
        ("Repos", check_repos),
        ("Config", check_env),
        ("Ollama", check_ollama),
        ("india-trade-cli", check_india_trade_cli),
        ("Orchestrator", check_orchestrator),
        ("System", check_disk_space),
    ]

    results = {}
    for name, check_fn in checks:
        try:
            results[name] = check_fn()
        except Exception as e:
            fail(f"{name} check crashed: {e}")
            results[name] = False

    # Summary
    header("Summary")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    status = "READY" if passed == total else "PARTIAL" if passed > total // 2 else "NOT READY"

    status_color = GREEN if status == "READY" else YELLOW if status == "PARTIAL" else RED
    print(f"\n  {status_color}{BOLD}{status}{NC} — {passed}/{total} checks passed\n")

    if status != "READY":
        print(f"  {YELLOW}Fix the issues above, then run this script again.{NC}")
        print(f"  {CYAN}For OCI deployment, copy this project and run scripts/setup_oci.sh{NC}\n")

    return 0 if status == "READY" else 1


if __name__ == "__main__":
    sys.exit(main())
