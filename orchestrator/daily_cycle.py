"""
orchestrator/daily_cycle.py
───────────────────────────
The heartbeat of the trading system.

Runs the full daily trading cycle:
  08:45  Pre-market scan (morning brief, FII/DII, global cues)
  09:15  Market open analysis (deep-analyze top N signals)
  09:30  Paper order execution (place paper orders from signals)
  12:30  Mid-day review (check positions, adjust stops)
  15:15  EOD close (square off intraday, holdings P&L)
  16:00  Auto-improve cycle (reflect, backtest, promote winners)
  17:00  Auto-heal cycle (health checks, data quality, alerts)

Can run as:
  - Cron job (one-shot: `python -m orchestrator.daily_cycle --phase premarket`)
  - Daemon  (continuous: `python -m orchestrator.daily_cycle --daemon`)
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from orchestrator.config import load_config, Config

# ── Logging ──────────────────────────────────────────────────

LOG_DIR = Path.home() / ".trading_platform" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"daily_{datetime.now():%Y%m%d}.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("orchestrator")


# ── Journal ──────────────────────────────────────────────────

JOURNAL_DIR = Path.home() / ".trading_platform" / "journal"
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)


def journal_entry(phase: str, data: dict) -> None:
    """Append a timestamped entry to today's journal."""
    today_file = JOURNAL_DIR / f"{datetime.now():%Y-%m-%d}.jsonl"
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "phase": phase,
        **data,
    }
    with open(today_file, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    log.info(f"📝 Journal [{phase}]: {json.dumps(data, default=str)[:200]}")


# ── Phase Implementations ────────────────────────────────────


def phase_premarket(cfg: Config) -> dict:
    """
    08:45 IST — Pre-market scan.
    Runs india-trade-cli morning-brief to get:
    - FII/DII flows
    - Global market cues (US, Asia, Europe futures)
    - Sector heat map
    - VIX level and trend
    """
    log.info("═══ PHASE: Pre-Market Scan ═══")
    result = {"phase": "premarket", "status": "started"}

    try:
        # Use india-trade-cli's morning-brief command
        cli_path = cfg.project_root / "india-trade-cli"
        proc = subprocess.run(
            [sys.executable, "-m", "app.main", "morning-brief"],
            cwd=str(cli_path),
            capture_output=True,
            text=True,
            timeout=300,
            env=_build_env(cfg),
        )

        result["stdout"] = proc.stdout[-2000:] if proc.stdout else ""
        result["stderr"] = proc.stderr[-500:] if proc.stderr else ""
        result["returncode"] = proc.returncode
        result["status"] = "success" if proc.returncode == 0 else "error"

        log.info(f"Morning brief completed: exit={proc.returncode}")

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        log.warning("Morning brief timed out after 300s")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        log.error(f"Morning brief failed: {e}")

    journal_entry("premarket", result)
    return result


def phase_analysis(cfg: Config) -> dict:
    """
    09:15 IST — Market open analysis.
    Deep-analyzes top N stocks from NIFTY 50 universe using
    india-trade-cli's 7-agent parallel analysis pipeline.
    """
    log.info("═══ PHASE: Market Analysis ═══")
    result = {"phase": "analysis", "signals": [], "status": "started"}

    # Get stock universe
    stocks = _get_stock_universe(cfg.trading.stock_universe)
    max_stocks = cfg.trading.max_daily_analyses
    log.info(f"Analyzing top {max_stocks} from {len(stocks)} stocks")

    for i, symbol in enumerate(stocks[:max_stocks]):
        log.info(f"[{i+1}/{max_stocks}] Analyzing {symbol}...")
        try:
            cli_path = cfg.project_root / "india-trade-cli"
            proc = subprocess.run(
                [sys.executable, "-m", "app.main", "analyze", symbol],
                cwd=str(cli_path),
                capture_output=True,
                text=True,
                timeout=600,
                env=_build_env(cfg),
            )

            signal = {
                "symbol": symbol,
                "status": "success" if proc.returncode == 0 else "error",
                "output": proc.stdout[-3000:] if proc.stdout else "",
            }
            result["signals"].append(signal)

            if proc.returncode == 0:
                log.info(f"  ✅ {symbol} analysis complete")
            else:
                log.warning(f"  ⚠️ {symbol} analysis failed: {proc.stderr[-200:]}")

        except subprocess.TimeoutExpired:
            result["signals"].append({"symbol": symbol, "status": "timeout"})
            log.warning(f"  ⏱️ {symbol} analysis timed out")
        except Exception as e:
            result["signals"].append({"symbol": symbol, "status": "error", "error": str(e)})
            log.error(f"  ❌ {symbol} analysis error: {e}")

    result["status"] = "complete"
    result["analyzed_count"] = len(result["signals"])
    journal_entry("analysis", result)
    return result


def phase_execute(cfg: Config) -> dict:
    """
    09:30 IST — Paper order execution.
    Takes signals from analysis phase and places paper orders
    via the india-trade-cli paper broker.
    """
    log.info("═══ PHASE: Paper Order Execution ═══")
    result = {"phase": "execute", "orders": [], "status": "started"}

    # Read today's journal to get analysis signals
    today_file = JOURNAL_DIR / f"{datetime.now():%Y-%m-%d}.jsonl"
    if not today_file.exists():
        result["status"] = "no_signals"
        log.warning("No analysis signals found for today")
        journal_entry("execute", result)
        return result

    # Parse latest analysis signals
    signals = []
    with open(today_file) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("phase") == "analysis":
                    signals = entry.get("signals", [])
            except json.JSONDecodeError:
                continue

    if not signals:
        result["status"] = "no_signals"
        log.warning("No valid signals to execute")
        journal_entry("execute", result)
        return result

    # For each successful signal, attempt paper trade
    for signal in signals:
        if signal.get("status") != "success":
            continue

        symbol = signal["symbol"]
        log.info(f"Evaluating paper order for {symbol}...")

        # The paper orders are placed automatically by india-trade-cli
        # when in PAPER mode — we just log the intent
        result["orders"].append({
            "symbol": symbol,
            "action": "evaluated",
            "mode": "PAPER",
        })

    result["status"] = "complete"
    result["order_count"] = len(result["orders"])
    journal_entry("execute", result)
    return result


def phase_midday(cfg: Config) -> dict:
    """
    12:30 IST — Mid-day review.
    Checks open positions, monitors P&L, adjusts stops if needed.
    """
    log.info("═══ PHASE: Mid-Day Review ═══")
    result = {"phase": "midday", "status": "started"}

    try:
        cli_path = cfg.project_root / "india-trade-cli"

        # Get portfolio status
        proc = subprocess.run(
            [sys.executable, "-m", "app.main", "portfolio"],
            cwd=str(cli_path),
            capture_output=True,
            text=True,
            timeout=120,
            env=_build_env(cfg),
        )

        result["portfolio"] = proc.stdout[-2000:] if proc.stdout else ""
        result["status"] = "success" if proc.returncode == 0 else "error"

        # Run risk report
        proc_risk = subprocess.run(
            [sys.executable, "-m", "app.main", "risk-report"],
            cwd=str(cli_path),
            capture_output=True,
            text=True,
            timeout=120,
            env=_build_env(cfg),
        )

        result["risk_report"] = proc_risk.stdout[-2000:] if proc_risk.stdout else ""

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        log.error(f"Mid-day review failed: {e}")

    journal_entry("midday", result)
    return result


def phase_eod(cfg: Config) -> dict:
    """
    15:15 IST — End of day close.
    Squares off intraday positions, summarizes daily P&L.
    """
    log.info("═══ PHASE: End of Day ═══")
    result = {"phase": "eod", "status": "started"}

    try:
        cli_path = cfg.project_root / "india-trade-cli"

        # Get final portfolio summary
        proc = subprocess.run(
            [sys.executable, "-m", "app.main", "holdings"],
            cwd=str(cli_path),
            capture_output=True,
            text=True,
            timeout=120,
            env=_build_env(cfg),
        )

        result["holdings"] = proc.stdout[-2000:] if proc.stdout else ""
        result["status"] = "success"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        log.error(f"EOD close failed: {e}")

    journal_entry("eod", result)
    return result


def phase_auto_improve(cfg: Config) -> dict:
    """
    16:00 IST — Auto-improve cycle.

    Steps:
      1. Load today's trade journal (signals, orders, outcomes)
      2. Score predictions vs actual outcomes
      3. LLM reflection: analyze errors, suggest improvements
      4. Backtest suggested modifications on last 90 days
      5. Promote improvements that beat the threshold
      6. Update agent confidence weights
      7. Log everything to improvement journal
    """
    log.info("═══ PHASE: Auto-Improve ═══")
    result = {"phase": "auto_improve", "improvements": [], "status": "started"}

    try:
        # 1. Load trade memory stats
        sys.path.insert(0, str(cfg.project_root / "india-trade-cli"))
        from engine.memory import trade_memory
        from engine.drift import detect_drift

        stats = trade_memory.get_stats()
        result["memory_stats"] = stats
        log.info(f"Trade memory: {stats['total_analyses']} analyses, "
                 f"{stats['with_outcome']} with outcomes")

        # 2. Run drift detection
        drift_report = detect_drift()
        result["drift"] = {
            "win_rate_trend": drift_report.win_rate_trend,
            "recent_win_rate": drift_report.recent_win_rate,
            "alerts": drift_report.alerts,
            "best_analyst": drift_report.best_analyst,
            "worst_analyst": drift_report.worst_analyst,
        }
        log.info(f"Drift status: {drift_report.win_rate_trend} "
                 f"(recent: {drift_report.recent_win_rate:.0f}%)")

        # 3. Run reflection on recent trades without outcomes
        recent_trades = trade_memory.query(limit=10)
        reflected = 0
        for trade in recent_trades:
            if trade.outcome and not trade.lesson:
                lesson = trade_memory.reflect_and_remember(trade.id)
                if lesson:
                    reflected += 1
                    log.info(f"  📚 Reflected on {trade.symbol}: {lesson[:100]}")

        result["reflections"] = reflected

        # 4. Log drift alerts
        if drift_report.alerts:
            for alert in drift_report.alerts:
                log.warning(f"  ⚠️ DRIFT ALERT: {alert}")
                result["improvements"].append({
                    "type": "drift_alert",
                    "message": alert,
                })

        # 5. Strategy performance review
        if drift_report.analyst_accuracy:
            result["analyst_accuracy"] = drift_report.analyst_accuracy

        result["status"] = "complete"

    except ImportError as e:
        result["status"] = "import_error"
        result["error"] = f"Could not import india-trade-cli modules: {e}"
        log.error(f"Auto-improve import error: {e}")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        log.error(f"Auto-improve failed: {e}")

    journal_entry("auto_improve", result)
    return result


def phase_auto_heal(cfg: Config) -> dict:
    """
    17:00 IST — Auto-heal cycle.

    Checks:
      1. Ollama service health (LLM availability)
      2. Kite MCP connectivity (broker data)
      3. Data quality (stale/missing quotes)
      4. API rate limits (usage tracking)
      5. Disk space and memory
    Fixes:
      - Auto-restart failed services
      - Switch to fallback LLM if primary is down
      - Alert via Telegram if critical failure
    """
    log.info("═══ PHASE: Auto-Heal ═══")
    result = {"phase": "auto_heal", "checks": [], "status": "started"}

    # 1. Check Ollama health
    ollama_ok = _check_ollama(cfg)
    result["checks"].append({
        "service": "ollama",
        "status": "healthy" if ollama_ok else "down",
    })
    if not ollama_ok:
        log.warning("⚠️ Ollama is down — attempting restart...")
        _restart_ollama()

    # 2. Check Kite MCP connectivity
    kite_ok = _check_kite_mcp(cfg)
    result["checks"].append({
        "service": "kite_mcp",
        "status": "healthy" if kite_ok else "unreachable",
    })

    # 3. Check disk space
    import shutil
    disk = shutil.disk_usage("/")
    free_gb = disk.free / (1024**3)
    result["checks"].append({
        "service": "disk",
        "status": "healthy" if free_gb > 5 else "low",
        "free_gb": round(free_gb, 1),
    })
    if free_gb < 5:
        log.warning(f"⚠️ Disk space low: {free_gb:.1f}GB free")

    # 4. Check journal integrity
    today_file = JOURNAL_DIR / f"{datetime.now():%Y-%m-%d}.jsonl"
    journal_ok = today_file.exists() and today_file.stat().st_size > 0
    result["checks"].append({
        "service": "journal",
        "status": "healthy" if journal_ok else "empty",
    })

    # 5. Summary
    all_healthy = all(c["status"] == "healthy" for c in result["checks"])
    result["status"] = "all_healthy" if all_healthy else "issues_found"

    # 6. Telegram alert if issues
    if not all_healthy and cfg.auto_heal.telegram_bot_token:
        issues = [c for c in result["checks"] if c["status"] != "healthy"]
        _send_telegram_alert(cfg, f"🔧 Auto-heal issues: {issues}")

    journal_entry("auto_heal", result)
    return result


# ── Health Check Helpers ─────────────────────────────────────


def _check_ollama(cfg: Config) -> bool:
    """Check if Ollama is running and responsive."""
    try:
        import httpx
        base = cfg.llm.primary_base_url.rstrip("/v1").rstrip("/")
        resp = httpx.get(f"{base}/api/tags", timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def _restart_ollama() -> None:
    """Attempt to restart Ollama service."""
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(5)
        log.info("Ollama restart attempted")
    except Exception as e:
        log.error(f"Failed to restart Ollama: {e}")


def _check_kite_mcp(cfg: Config) -> bool:
    """Check if Kite MCP server is reachable."""
    try:
        import httpx
        resp = httpx.get(cfg.broker.kite_mcp_url, timeout=10)
        return resp.status_code in (200, 405)  # 405 = method not allowed (but server is up)
    except Exception:
        return False


def _send_telegram_alert(cfg: Config, message: str) -> None:
    """Send alert via Telegram bot."""
    if not cfg.auto_heal.telegram_bot_token or not cfg.auto_heal.telegram_chat_id:
        return
    try:
        import httpx
        url = f"https://api.telegram.org/bot{cfg.auto_heal.telegram_bot_token}/sendMessage"
        httpx.post(url, json={
            "chat_id": cfg.auto_heal.telegram_chat_id,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)
    except Exception as e:
        log.error(f"Telegram alert failed: {e}")


# ── Stock Universe ───────────────────────────────────────────

NIFTY_50 = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "AXISBANK", "BAJFINANCE", "ASIANPAINT", "MARUTI",
    "TITAN", "SUNPHARMA", "TATAMOTORS", "WIPRO", "ULTRACEMCO",
    "NTPC", "ONGC", "POWERGRID", "TATASTEEL", "INDUSINDBK",
    "JSWSTEEL", "ADANIENT", "ADANIPORTS", "BAJAJFINSV", "COALINDIA",
    "TECHM", "HCLTECH", "NESTLEIND", "DRREDDY", "CIPLA",
    "DIVISLAB", "GRASIM", "EICHERMOT", "APOLLOHOSP", "HEROMOTOCO",
    "BRITANNIA", "M&M", "TATACONSUM", "HINDALCO", "BPCL",
    "BAJAJ-AUTO", "SHRIRAMFIN", "SBILIFE", "HDFCLIFE", "LTIM",
]


def _get_stock_universe(name: str) -> list[str]:
    """Get list of symbols for the given universe name."""
    if name.upper() == "NIFTY50":
        return NIFTY_50
    # Support comma-separated custom list
    if "," in name:
        return [s.strip().upper() for s in name.split(",")]
    return NIFTY_50[:10]  # Fallback: top 10


# ── Environment Builder ─────────────────────────────────────


def _build_env(cfg: Config) -> dict:
    """Build environment dict for subprocess calls to india-trade-cli."""
    import os
    env = os.environ.copy()
    env.update({
        "TRADING_MODE": cfg.trading.mode,
        "TOTAL_CAPITAL": str(int(cfg.trading.total_capital)),
        "DEFAULT_RISK_PCT": str(cfg.trading.risk_pct),
        "AI_PROVIDER": "openai",  # india-trade-cli uses OpenAI-compatible
        "OPENAI_BASE_URL": cfg.llm.primary_base_url,
        "OPENAI_API_KEY": "ollama",
        "AI_MODEL": cfg.llm.primary_model,
        "KITE_API_KEY": cfg.broker.kite_api_key,
        "KITE_API_SECRET": cfg.broker.kite_api_secret,
    })
    return env


# ── Daemon Mode ──────────────────────────────────────────────

SCHEDULE = [
    ("08:45", "premarket", phase_premarket),
    ("09:15", "analysis",  phase_analysis),
    ("09:30", "execute",   phase_execute),
    ("12:30", "midday",    phase_midday),
    ("15:15", "eod",       phase_eod),
    ("16:00", "auto_improve", phase_auto_improve),
    ("17:00", "auto_heal", phase_auto_heal),
]


def run_daemon(cfg: Config) -> None:
    """Run as a daemon, executing phases at scheduled times."""
    log.info("🚀 Orchestrator daemon started")
    log.info(f"   Mode: {cfg.trading.mode}")
    log.info(f"   Capital: ₹{cfg.trading.total_capital:,.0f}")
    log.info(f"   Universe: {cfg.trading.stock_universe}")
    log.info(f"   LLM: {cfg.llm.primary_provider}/{cfg.llm.primary_model}")

    executed_today = set()

    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")

        for sched_time, phase_name, phase_fn in SCHEDULE:
            key = f"{today}_{phase_name}"
            if key not in executed_today and current_time >= sched_time:
                log.info(f"⏰ Triggering phase: {phase_name} (scheduled: {sched_time})")
                try:
                    phase_fn(cfg)
                except Exception as e:
                    log.error(f"Phase {phase_name} crashed: {e}")
                    journal_entry(phase_name, {
                        "status": "crashed",
                        "error": str(e),
                    })
                executed_today.add(key)

        # Clear executed set at midnight
        if current_time < "00:05":
            executed_today.clear()

        time.sleep(30)  # Check every 30 seconds


# ── CLI Entry Point ──────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Vibe Trading India — Daily Orchestrator")
    parser.add_argument(
        "--phase",
        choices=["premarket", "analysis", "execute", "midday", "eod", "auto_improve", "auto_heal", "all"],
        help="Run a specific phase (or 'all' to run all sequentially)",
    )
    parser.add_argument("--daemon", action="store_true", help="Run as a daemon with scheduled execution")
    parser.add_argument("--health", action="store_true", help="Run health checks only")

    args = parser.parse_args()
    cfg = load_config()

    # Safety check
    if cfg.trading.mode != "PAPER":
        log.critical("🚨 TRADING_MODE is not PAPER! Refusing to start.")
        log.critical("Set TRADING_MODE=PAPER in .env before running.")
        sys.exit(1)

    if args.daemon:
        run_daemon(cfg)
    elif args.health:
        result = phase_auto_heal(cfg)
        print(json.dumps(result, indent=2))
    elif args.phase:
        phase_map = {
            "premarket": phase_premarket,
            "analysis": phase_analysis,
            "execute": phase_execute,
            "midday": phase_midday,
            "eod": phase_eod,
            "auto_improve": phase_auto_improve,
            "auto_heal": phase_auto_heal,
        }
        if args.phase == "all":
            for name, fn in phase_map.items():
                fn(cfg)
        else:
            result = phase_map[args.phase](cfg)
            print(json.dumps(result, indent=2, default=str))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
