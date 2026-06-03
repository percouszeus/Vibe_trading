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


from orchestrator.vibe_logger import exhaustive_log
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("orchestrator.telegram")


@exhaustive_log
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


@exhaustive_log
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


@exhaustive_log
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


@exhaustive_log
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


@exhaustive_log
def format_emergency_stop() -> str:
    """Format emergency stop confirmation."""
    return """<b>🚨 EMERGENCY STOP ACTIVATED</b>

All trading has been halted.
Open positions will NOT be auto-closed.
Manual intervention required.

To resume: restart the orchestrator service.
"""


@exhaustive_log
def format_withdrawal_confirm(amount: float, pending: float) -> str:
    """Format withdrawal confirmation."""
    return f"""<b>💸 Withdrawal Recorded</b>

Amount: ₹{amount:,.0f}
Remaining Pending: ₹{pending:,.0f}

Transfer to your bank account as configured.
"""


# ── Daily Report Sender ──────────────────────────────────────


@exhaustive_log
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


@exhaustive_log
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


@exhaustive_log
def _get_ai_fund_spending_summary() -> dict:
    from orchestrator.capital_manager import AI_SPEND_LOG
    summary = {
        "total_spent": 0.0,
        "purchase_count": 0,
        "by_category": {}
    }
    if not AI_SPEND_LOG.exists():
        return summary

    try:
        with open(AI_SPEND_LOG, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    amount = float(entry.get("amount", 0.0))
                    category = entry.get("category", "llm_credits")
                    summary["total_spent"] += amount
                    summary["purchase_count"] += 1
                    summary["by_category"][category] = summary["by_category"].get(category, 0.0) + amount
                except Exception:
                    continue
    except Exception as e:
        log.error(f"Failed to read AI spend log: {e}")

    return summary


@exhaustive_log
def _listener_loop(cfg: Config, token: str, chat_id: str) -> None:
    import httpx
    from orchestrator.capital_manager import load_state, record_owner_withdrawal, generate_daily_summary, STATE_DIR
    from orchestrator.live_graduation import load_graduation_state, evaluate_graduation

    offset = 0
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    log.info("Telegram command listener polling loop started...")

    while True:
        try:
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset

            resp = httpx.get(url, params=params, timeout=35)
            if resp.status_code != 200:
                time.sleep(5)
                continue

            data = resp.json()
            if not data.get("ok"):
                time.sleep(5)
                continue

            for update in data.get("result", []):
                update_id = update["update_id"]
                offset = update_id + 1

                message = update.get("message")
                if not message:
                    continue

                from_chat = message.get("chat", {})
                if str(from_chat.get("id")) != str(chat_id):
                    log.warning(f"Ignored message from unauthorized chat_id: {from_chat.get('id')}")
                    continue

                text = message.get("text", "").strip()
                if not text.startswith("/"):
                    continue

                log.info(f"Received Telegram command: {text}")
                parts = text.split()
                cmd = parts[0].lower()

                if cmd == "/status":
                    state = load_state()
                    summary = generate_daily_summary(state)
                    report = format_capital_status(summary)
                    send_message(token, chat_id, report)

                elif cmd == "/aifund":
                    state = load_state()
                    spending_summary = _get_ai_fund_spending_summary()
                    report = format_ai_fund_report(state.ai_fund_balance, spending_summary)
                    send_message(token, chat_id, report)

                elif cmd == "/graduate":
                    state = load_state()
                    grad_state = load_graduation_state()
                    eval_res = evaluate_graduation(state, grad_state)
                    report = format_daily_report(
                        date_str=datetime.now().strftime("%Y-%m-%d"),
                        daily_pnl=state.realized_pnl_today,
                        principal=state.principal,
                        split={},
                        strategy_summary="",
                        ai_fund_balance=state.ai_fund_balance,
                        ai_fund_spent_today=0,
                        graduation_progress=eval_res.get("progress_pct", 0),
                        graduation_details=eval_res,
                    )
                    send_message(token, chat_id, report)

                elif cmd == "/emergency":
                    emergency_file = STATE_DIR / "emergency_stop.flag"
                    emergency_file.touch()
                    report = format_emergency_stop()
                    send_message(token, chat_id, report)
                    log.critical("🚨 EMERGENCY STOP ACTIVATED VIA TELEGRAM!")

                elif cmd == "/resume":
                    emergency_file = STATE_DIR / "emergency_stop.flag"
                    if emergency_file.exists():
                        emergency_file.unlink()
                        send_message(token, chat_id, "<b>✅ EMERGENCY RESUME ACTIVATED</b>\n\nTrading has been unhalted.")
                        log.info("Telegram: emergency stop flag cleared.")
                    else:
                        send_message(token, chat_id, "System is not in halted state.")

                elif cmd == "/withdraw":
                    if len(parts) < 2:
                        send_message(token, chat_id, "Usage: `/withdraw <amount>`")
                        continue
                    try:
                        amount = float(parts[1])
                        state = load_state()
                        success = record_owner_withdrawal(state, amount)
                        if success:
                            send_message(token, chat_id, format_withdrawal_confirm(amount, state.owner_pending))
                        else:
                            send_message(token, chat_id, f"❌ Withdrawal failed: Insufficient pending balance (₹{state.owner_pending:,.0f}).")
                    except ValueError:
                        send_message(token, chat_id, "Invalid amount. Usage: `/withdraw <amount>`")

                elif cmd == "/strategies":
                    try:
                        from orchestrator.strategy_portfolio import load_strategy_performance, get_strategy_summary
                        perf = load_strategy_performance()
                        strat_summary = get_strategy_summary(perf)
                        send_message(token, chat_id, f"<b>📊 Active Strategies:</b>\n<pre>{strat_summary}</pre>")
                    except Exception as e:
                        send_message(token, chat_id, f"Error loading strategies: {e}")

                elif cmd == "/help" or cmd == "/start":
                    help_text = (
                        "<b>🤖 Vibe Trading Assistant Bot</b>\n\n"
                        "<b>Commands:</b>\n"
                        "• /status — Current capital state & metrics\n"
                        "• /aifund — AI Fund balance & spending summary\n"
                        "• /strategies — Active strategies performance\n"
                        "• /graduate — Live trading graduation progress\n"
                        "• /withdraw &lt;amount&gt; — Withdraw payout\n"
                        "• /emergency — Trigger an immediate trading halt\n"
                        "• /resume — Clear emergency halt and resume\n"
                    )
                    send_message(token, chat_id, help_text)

        except Exception as e:
            log.error(f"Error in Telegram listener loop: {e}")
            time.sleep(10)


@exhaustive_log
def start_telegram_listener(cfg: Config) -> None:
    """Start the Telegram interactive listener in a background thread."""
    token = cfg.telegram.bot_token
    chat_id = cfg.telegram.chat_id
    if not token or not chat_id:
        log.warning("Telegram listener not configured — skipping listener thread")
        return

    thread = threading.Thread(target=_listener_loop, args=(cfg, token, chat_id), daemon=True)
    thread.start()
    log.info("🤖 Telegram command listener thread started.")


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
