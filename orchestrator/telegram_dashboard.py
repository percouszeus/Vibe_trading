"""
orchestrator/telegram_dashboard.py
────────────────────────────────────
TELEGRAM TRADING DASHBOARD

Full trading dashboard via Telegram bot:
  - Daily P&L reports with 50/25/25 split
  - Strategy performance breakdown
  - Withdrawal requests
  - Graduation progress
  - Emergency stop
  - Monthly reports

Commands:
  /status     — Current portfolio + P&L
  /withdraw   — Request owner payout
  /aifund     — AI fund balance + history
  /strategies — Strategy performance
  /graduate   — Graduation progress
  /emergency  — Emergency stop
  /report     — Monthly report
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("orchestrator.telegram")


def send_message(token: str, chat_id: str, text: str,
                 parse_mode: str = "HTML") -> bool:
    """Send a message via Telegram Bot API."""
    if not token or not chat_id:
        log.warning("Telegram not configured — skipping message")
        return False

    try:
        import httpx
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        # Split long messages (Telegram limit: 4096 chars)
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]

        for chunk in chunks:
            resp = httpx.post(url, json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
            }, timeout=15)

            if resp.status_code != 200:
                log.error(f"Telegram send failed: {resp.status_code}")
                return False

        return True
    except Exception as e:
        log.error(f"Telegram send error: {e}")
        return False


# ── Report Generators ────────────────────────────────────────


def format_daily_report(
    date_str: str,
    daily_pnl: float,
    principal: float,
    split: dict,
    strategy_summary: str,
    ai_fund_balance: float,
    ai_fund_spent_today: float,
    graduation_progress: float,
    graduation_details: dict,
) -> str:
    """Format the daily trading report for Telegram."""
    pnl_emoji = "📈" if daily_pnl > 0 else ("📉" if daily_pnl < 0 else "➖")
    pnl_sign = "+" if daily_pnl > 0 else ""
    pnl_pct = daily_pnl / max(principal - daily_pnl, 1) * 100

    report = f"""<b>📊 VIBE TRADING — Daily Report</b>
<i>{date_str}</i>

{pnl_emoji} <b>Today's P&amp;L:</b> {pnl_sign}₹{daily_pnl:,.0f} ({pnl_sign}{pnl_pct:.2f}%)
💰 <b>Portfolio:</b> ₹{principal:,.0f}
"""

    if daily_pnl > 0:
        report += f"""
<b>💸 Split Applied:</b>
   → 50% Reinvested: ₹{split.get('reinvest_amount', 0):,.0f}
   → 25% AI Fund: ₹{split.get('ai_fund_amount', 0):,.0f}
   → 25% Your Payout: ₹{split.get('owner_amount', 0):,.0f}
"""

    report += f"""
<b>🤖 AI Fund:</b>
   Balance: ₹{ai_fund_balance:,.0f}
   Spent Today: ₹{ai_fund_spent_today:,.0f}
"""

    if strategy_summary:
        report += f"\n<b>📊 Strategies:</b>\n<pre>{strategy_summary}</pre>\n"

    # Graduation progress
    grad_pct = graduation_progress
    bar_len = 10
    filled = int(grad_pct / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    report += f"\n<b>🎓 Live Graduation:</b> [{bar}] {grad_pct:.0f}%\n"

    if graduation_details:
        for name, check in graduation_details.get("checks", {}).items():
            icon = "✅" if check.get("passed") else "⚠️"
            report += f"   {icon} {name}: {check.get('label', '')}\n"

    return report


def format_capital_status(summary: dict) -> str:
    """Format capital status for /status command."""
    return f"""<b>💰 Capital Status</b>

<b>Principal:</b> ₹{summary.get('principal', 0):,.0f}
<b>Cumulative P&amp;L:</b> ₹{summary.get('cumulative_pnl', 0):,.0f}
<b>ROI:</b> {summary.get('roi_pct', 0):+.1f}%
<b>Win Rate:</b> {summary.get('win_rate', 0):.1f}%
<b>Max Drawdown:</b> {summary.get('max_drawdown_pct', 0):.1f}%

<b>💸 Distribution:</b>
  Reinvested: ₹{summary.get('reinvested_total', 0):,.0f}
  AI Fund Available: ₹{summary.get('ai_fund_balance', 0):,.0f}
  AI Fund Spent: ₹{summary.get('ai_fund_spent', 0):,.0f}
  Your Pending: ₹{summary.get('owner_pending', 0):,.0f}
  Your Withdrawn: ₹{summary.get('owner_withdrawn', 0):,.0f}

<b>📅 Stats:</b>
  Trading Days: {summary.get('trading_days', 0)}
  Profitable: {summary.get('profitable_days', 0)}
  Loss: {summary.get('loss_days', 0)}
  Best Day: ₹{summary.get('best_day', 0):,.0f}
  Worst Day: ₹{summary.get('worst_day', 0):,.0f}
"""


def format_ai_fund_report(balance: float, spending_summary: dict) -> str:
    """Format AI fund report for /aifund command."""
    report = f"""<b>🤖 AI Improvement Fund</b>

<b>Balance:</b> ₹{balance:,.0f}
<b>Total Spent:</b> ₹{spending_summary.get('total_spent', 0):,.0f}
<b>Purchases:</b> {spending_summary.get('purchase_count', 0)}

<b>By Category:</b>
"""
    for cat, amount in spending_summary.get("by_category", {}).items():
        report += f"  • {cat}: ₹{amount:,.0f}\n"

    return report


def format_emergency_stop() -> str:
    """Format emergency stop confirmation."""
    return """<b>🚨 EMERGENCY STOP ACTIVATED</b>

All trading has been halted.
Open positions will NOT be auto-closed.
Manual intervention required.

To resume: restart the orchestrator service.
"""


def format_withdrawal_confirm(amount: float, pending: float) -> str:
    """Format withdrawal confirmation."""
    return f"""<b>💸 Withdrawal Recorded</b>

Amount: ₹{amount:,.0f}
Remaining Pending: ₹{pending:,.0f}

Transfer to your bank account as configured.
"""


# ── Daily Report Sender ──────────────────────────────────────


def send_daily_report(
    token: str, chat_id: str,
    capital_summary: dict,
    split: dict,
    strategy_summary: str = "",
    ai_fund_balance: float = 0,
    ai_fund_spent_today: float = 0,
    graduation_result: dict = None,
) -> bool:
    """Send the complete daily report via Telegram."""
    today = datetime.now().strftime("%Y-%m-%d")
    daily_pnl = split.get("daily_pnl", 0)
    principal = capital_summary.get("principal", 0)

    report = format_daily_report(
        date_str=today,
        daily_pnl=daily_pnl,
        principal=principal,
        split=split,
        strategy_summary=strategy_summary,
        ai_fund_balance=ai_fund_balance,
        ai_fund_spent_today=ai_fund_spent_today,
        graduation_progress=graduation_result.get("progress_pct", 0) if graduation_result else 0,
        graduation_details=graduation_result or {},
    )

    return send_message(token, chat_id, report)


def send_alert(token: str, chat_id: str, alert_type: str, message: str) -> bool:
    """Send a trading alert."""
    emoji_map = {
        "trade": "📋",
        "risk": "⚠️",
        "circuit_breaker": "🚨",
        "graduation": "🎓",
        "ai_purchase": "🤖",
        "withdrawal": "💸",
    }
    emoji = emoji_map.get(alert_type, "📢")
    text = f"{emoji} <b>{alert_type.upper()}</b>\n\n{message}"
    return send_message(token, chat_id, text)


if __name__ == "__main__":
    # Demo format
    split = {"daily_pnl": 12450, "reinvest_amount": 6225,
             "ai_fund_amount": 3112, "owner_amount": 3112}
    report = format_daily_report(
        "2026-05-14", 12450, 1012450, split,
        "Momentum: +₹8200 | Reversion: -₹1800",
        15780, 0, 57, {},
    )
    print(report)
