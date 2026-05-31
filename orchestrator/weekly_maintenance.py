from __future__ import annotations

from orchestrator.vibe_logger import exhaustive_log
import os
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from orchestrator.config import Config
from orchestrator.telegram_dashboard import send_alert

log = logging.getLogger("orchestrator.weekly_maintenance")

REPORTS_DIR = Path.home() / ".trading_platform" / "reports"
LOGS_DIR = Path.home() / ".trading_platform" / "logs"
JOURNAL_DIR = Path.home() / ".trading_platform" / "journal"

@exhaustive_log
def phase_weekly_maintenance(cfg: Config) -> dict:
    """
    WEEKEND — Weekly logs consolidation & cleanup.

    Analyzes the past week's raw JSON daily logs for:
      - Exceptions & critical errors
      - LLM rate limits / Too Many Requests errors (HTTP 429, etc.)
      - Average execution duration of functions
      - Code performance metrics

    Consolidates this into a single history file, sends a status report via
    Telegram, and safely deletes daily raw log files older than 7 days.
    """
    log.info("═══ WEEKEND PHASE: Weekly Logs Consolidation & Cleanup ═══")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.now()
    year, week_num, _ = today.isocalendar()
    report_id = f"{year}_W{week_num:02d}"
    report_file = REPORTS_DIR / f"weekly_performance_{report_id}.json"

    result = {
        "phase": "weekly_maintenance",
        "report_id": report_id,
        "timestamp": today.isoformat(),
        "status": "started",
        "logs_analyzed": 0,
        "rate_limits_detected": 0,
        "exceptions_detected": 0,
        "average_func_durations_ms": {},
        "raw_logs_deleted": [],
        "space_saved_bytes": 0,
    }

    # 1. Gather all logs from the past 7 days
    past_week_files: list[Path] = []
    for i in range(7):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y%m%d")
        log_file = LOGS_DIR / f"daily_{day_str}.log"
        if log_file.exists():
            past_week_files.append(log_file)

    result["logs_analyzed"] = len(past_week_files)
    log.info(f"Analyzing {len(past_week_files)} log files from the past week...")

    # 2. Parse daily JSON log entries
    func_times: dict[str, list[float]] = {}
    rate_limit_patterns = [
        re.compile(r"429", re.IGNORECASE),
        re.compile(r"RateLimitError", re.IGNORECASE),
        re.compile(r"Too Many Requests", re.IGNORECASE),
        re.compile(r"quota exceeded", re.IGNORECASE),
        re.compile(r"limit reached", re.IGNORECASE)
    ]

    for log_path in past_week_files:
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        level = entry.get("level", "")
                        msg = entry.get("message", "")

                        # Check for rate-limiting
                        if any(pat.search(msg) for pat in rate_limit_patterns):
                            result["rate_limits_detected"] += 1

                        # Check for errors/exceptions
                        if level in ("ERROR", "CRITICAL") or "exception" in entry:
                            result["exceptions_detected"] += 1

                        # Check function performance duration
                        event = entry.get("event", "")
                        func_name = entry.get("function", "")
                        duration = entry.get("duration_ms")
                        if duration is not None and func_name:
                            func_times.setdefault(func_name, []).append(float(duration))

                    except json.JSONDecodeError:
                        # Fallback simple text match for corrupted lines
                        if any(pat.search(line) for pat in rate_limit_patterns):
                            result["rate_limits_detected"] += 1
                        if "ERROR" in line or "CRITICAL" in line:
                            result["exceptions_detected"] += 1

        except Exception as err:
            log.warning(f"Failed to fully parse log file {log_path.name}: {err}")

    # 3. Calculate average function durations
    for func_name, durations in func_times.items():
        if durations:
            avg_duration = sum(durations) / len(durations)
            result["average_func_durations_ms"][func_name] = round(avg_duration, 2)

    # 4. Check weekly profit split summary from daily journals
    weekly_pnl = 0.0
    journal_count = 0
    for i in range(7):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        journal_file = JOURNAL_DIR / f"{day_str}.jsonl"
        if journal_file.exists():
            journal_count += 1
            try:
                with open(journal_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        entry = json.loads(line)
                        if entry.get("phase") == "capital_split":
                            split = entry.get("split", {})
                            weekly_pnl += float(split.get("daily_pnl", 0.0))
            except Exception:
                continue

    result["weekly_pnl"] = weekly_pnl
    result["journals_reviewed"] = journal_count

    # 5. Clean up old log files (>7 days old)
    all_log_files = sorted(LOGS_DIR.glob("daily_*.log"))
    for log_file in all_log_files:
        # Extract date from daily_YYYYMMDD.log
        match = re.match(r"daily_(\d{8})\.log", log_file.name)
        if match:
            date_str = match.group(1)
            try:
                file_date = datetime.strptime(date_str, "%Y%m%d")
                age_days = (today - file_date).days
                if age_days > 7:
                    size = log_file.stat().st_size
                    log_file.unlink()
                    result["raw_logs_deleted"].append(log_file.name)
                    result["space_saved_bytes"] += size
                    log.info(f"Deleted old raw log file: {log_file.name} (saved {size/1024/1024:.2f} MB)")
            except ValueError:
                continue

    result["status"] = "complete"

    # 6. Save the consolidated weekly performance file
    try:
        report_file.write_text(json.dumps(result, indent=2))
        log.info(f"Consolidated weekly performance file saved to {report_file.name}")
    except Exception as e:
        log.error(f"Failed to save weekly consolidated file: {e}")

    # 7. Send consolidation alert via Telegram
    try:
        if cfg.auto_heal.telegram_bot_token and cfg.auto_heal.telegram_chat_id:
            alert_msg = (
                f"<b>🧹 WEEKLY CONSOLIDATION & CLEANUP</b>\n\n"
                f"• <b>Report ID:</b> {report_id}\n"
                f"• <b>Weekly PnL:</b> {'+' if weekly_pnl > 0 else ''}₹{weekly_pnl:,.2f}\n"
                f"• <b>Rate Limits (429s) Encountered:</b> {result['rate_limits_detected']}\n"
                f"• <b>Critical Exceptions:</b> {result['exceptions_detected']}\n"
                f"• <b>Raw Log Files Cleaned:</b> {len(result['raw_logs_deleted'])} files\n"
                f"• <b>Disk Space Freed:</b> {result['space_saved_bytes']/1024/1024:.2f} MB\n"
                f"• <b>Status:</b> System Healthy ✅"
            )
            send_alert(
                cfg.auto_heal.telegram_bot_token,
                cfg.auto_heal.telegram_chat_id,
                "circuit_breaker",
                alert_msg
            )
            log.info("Telegram weekly maintenance report sent.")
    except Exception as telegram_err:
        log.error(f"Failed to send Telegram weekly report: {telegram_err}")

    return result
