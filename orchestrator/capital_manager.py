"""
orchestrator/capital_manager.py
────────────────────────────────
CAPITAL MANAGEMENT ENGINE

The financial brain of the trading system.

Profit Distribution Rule:
  50%  → Reinvest to principal (compounding)
  25%  → AI improvement fund (buy better models/data)
  25%  → Owner payout (your money)

Loss Handling:
  100% of losses absorbed by principal only.
  AI fund and owner payout are NEVER debited on loss days.

Persistence:
  State saved to ~/.trading_platform/capital_state.json
  Daily snapshots in ~/.trading_platform/capital_history.jsonl
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Optional

log = logging.getLogger("orchestrator.capital")

# ── Paths ────────────────────────────────────────────────────

STATE_DIR = Path.home() / ".trading_platform"
STATE_FILE = STATE_DIR / "capital_state.json"
HISTORY_FILE = STATE_DIR / "capital_history.jsonl"
AI_SPEND_LOG = STATE_DIR / "ai_spend_log.jsonl"
WITHDRAWAL_LOG = STATE_DIR / "withdrawal_log.jsonl"


@dataclass
class CapitalState:
    """Complete capital state of the trading system."""

    # ── Core Capital ──────────────────────────────────────────
    principal: float = 1_000_000.0       # Current trading capital
    unrealized_pnl: float = 0.0          # Open positions P&L
    realized_pnl_today: float = 0.0      # Today's closed P&L
    cumulative_pnl: float = 0.0          # All-time net P&L

    # ── 50/25/25 Split Tracking ───────────────────────────────
    reinvested_total: float = 0.0        # Total added back to principal
    ai_fund_total: float = 0.0           # Total allocated to AI fund
    ai_fund_balance: float = 0.0         # Unspent AI fund balance
    ai_fund_spent: float = 0.0           # Total spent from AI fund
    owner_withdrawn: float = 0.0         # Total paid out to owner
    owner_pending: float = 0.0           # Awaiting withdrawal

    # ── Ratios (configurable) ─────────────────────────────────
    reinvest_pct: float = 0.50           # 50% back to principal
    ai_fund_pct: float = 0.25            # 25% for AI improvements
    owner_pct: float = 0.25              # 25% for owner

    # ── Metrics ───────────────────────────────────────────────
    initial_capital: float = 1_000_000.0
    trading_days: int = 0
    profitable_days: int = 0
    loss_days: int = 0
    max_principal: float = 1_000_000.0   # High-water mark
    max_drawdown_pct: float = 0.0        # Worst drawdown from peak
    best_day_pnl: float = 0.0
    worst_day_pnl: float = 0.0
    consecutive_loss_days: int = 0
    max_consecutive_loss_days: int = 0

    # ── Metadata ──────────────────────────────────────────────
    last_updated: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> CapitalState:
        # Handle extra keys gracefully
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


# ── Core Functions ───────────────────────────────────────────


def load_state() -> CapitalState:
    """Load capital state from disk, or create fresh."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            state = CapitalState.from_dict(data)
            log.info(f"Loaded capital state: principal=₹{state.principal:,.0f}, "
                     f"AI fund=₹{state.ai_fund_balance:,.0f}, "
                     f"owner pending=₹{state.owner_pending:,.0f}")
            return state
        except Exception as e:
            log.error(f"Failed to load capital state: {e}")

    # Fresh state
    state = CapitalState()
    state.created_at = datetime.now().isoformat(timespec="seconds")
    state.last_updated = state.created_at
    save_state(state)
    log.info(f"Created fresh capital state: ₹{state.principal:,.0f}")
    return state


def save_state(state: CapitalState) -> None:
    """Persist capital state to disk."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state.last_updated = datetime.now().isoformat(timespec="seconds")
    STATE_FILE.write_text(json.dumps(state.to_dict(), indent=2, default=str))


def _append_history(snapshot: dict) -> None:
    """Append a daily snapshot to the history log."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(snapshot, default=str) + "\n")


# ── Profit Split Engine ──────────────────────────────────────


def process_daily_pnl(state: CapitalState, daily_pnl: float) -> dict:
    """
    Process end-of-day P&L through the 50/25/25 split engine.

    On PROFIT days:
      50% → added to principal (compounding)
      25% → added to AI fund balance
      25% → added to owner pending withdrawal

    On LOSS days:
      100% absorbed by principal only.
      AI fund and owner pending are NEVER reduced.

    Returns a dict with the split details for journaling.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    state.trading_days += 1
    state.realized_pnl_today = daily_pnl
    state.cumulative_pnl += daily_pnl

    split = {
        "date": today,
        "daily_pnl": daily_pnl,
        "type": "profit" if daily_pnl > 0 else ("loss" if daily_pnl < 0 else "flat"),
        "reinvest_amount": 0.0,
        "ai_fund_amount": 0.0,
        "owner_amount": 0.0,
        "principal_before": state.principal,
        "principal_after": 0.0,
    }

    if daily_pnl > 0:
        # ── Profitable Day — Apply 50/25/25 Split ──────────
        reinvest = daily_pnl * state.reinvest_pct
        ai_fund = daily_pnl * state.ai_fund_pct
        owner = daily_pnl * state.owner_pct

        state.principal += reinvest
        state.reinvested_total += reinvest

        state.ai_fund_balance += ai_fund
        state.ai_fund_total += ai_fund

        state.owner_pending += owner

        state.profitable_days += 1
        state.consecutive_loss_days = 0
        state.best_day_pnl = max(state.best_day_pnl, daily_pnl)

        split["reinvest_amount"] = round(reinvest, 2)
        split["ai_fund_amount"] = round(ai_fund, 2)
        split["owner_amount"] = round(owner, 2)

        log.info(f"💰 PROFIT DAY: +₹{daily_pnl:,.0f} → "
                 f"Reinvest ₹{reinvest:,.0f} | AI ₹{ai_fund:,.0f} | "
                 f"Owner ₹{owner:,.0f}")

    elif daily_pnl < 0:
        # ── Loss Day — Full loss from principal only ───────
        state.principal += daily_pnl  # daily_pnl is negative
        state.loss_days += 1
        state.consecutive_loss_days += 1
        state.max_consecutive_loss_days = max(
            state.max_consecutive_loss_days, state.consecutive_loss_days
        )
        state.worst_day_pnl = min(state.worst_day_pnl, daily_pnl)

        log.warning(f"📉 LOSS DAY: ₹{daily_pnl:,.0f} absorbed from principal. "
                    f"Consecutive losses: {state.consecutive_loss_days}")

    else:
        log.info("➖ FLAT DAY: No P&L to split.")

    # Update high-water mark and drawdown
    state.max_principal = max(state.max_principal, state.principal)
    if state.max_principal > 0:
        current_drawdown = (state.max_principal - state.principal) / state.max_principal * 100
        state.max_drawdown_pct = max(state.max_drawdown_pct, current_drawdown)

    split["principal_after"] = round(state.principal, 2)
    split["ai_fund_balance"] = round(state.ai_fund_balance, 2)
    split["owner_pending"] = round(state.owner_pending, 2)
    split["cumulative_pnl"] = round(state.cumulative_pnl, 2)
    split["drawdown_pct"] = round(state.max_drawdown_pct, 2)

    # Persist
    save_state(state)
    _append_history(split)

    return split


# ── Capital Queries ──────────────────────────────────────────


def get_position_budget(state: CapitalState, risk_pct: float = 2.0) -> float:
    """Get maximum capital available for new positions."""
    return state.principal * (risk_pct / 100.0)


def get_total_portfolio_value(state: CapitalState) -> float:
    """Get total portfolio value including unrealized P&L."""
    return state.principal + state.unrealized_pnl


def get_current_drawdown_pct(state: CapitalState) -> float:
    """Get current drawdown from high-water mark."""
    if state.max_principal <= 0:
        return 0.0
    return (state.max_principal - state.principal) / state.max_principal * 100


def should_halt_trading(state: CapitalState, max_drawdown_pct: float = 15.0,
                        min_capital: float = 50_000.0) -> tuple[bool, str]:
    """
    Check if trading should be halted due to safety constraints.
    Returns (should_halt, reason).
    """
    dd = get_current_drawdown_pct(state)
    if dd >= max_drawdown_pct:
        return True, f"Max drawdown breached: {dd:.1f}% >= {max_drawdown_pct}%"

    if state.principal < min_capital:
        return True, f"Principal below minimum: ₹{state.principal:,.0f} < ₹{min_capital:,.0f}"

    if state.consecutive_loss_days >= 7:
        return True, f"7 consecutive loss days — cooling off"

    return False, "OK"


# ── AI Fund Operations ───────────────────────────────────────


def get_ai_fund_balance(state: CapitalState) -> float:
    """Get current unspent AI fund balance."""
    return state.ai_fund_balance


def spend_ai_fund(state: CapitalState, amount: float, description: str,
                  category: str = "llm_credits") -> bool:
    """
    Spend from the AI improvement fund.
    Returns True if sufficient balance, False otherwise.
    """
    if amount > state.ai_fund_balance:
        log.warning(f"Insufficient AI fund: need ₹{amount:,.0f}, "
                    f"have ₹{state.ai_fund_balance:,.0f}")
        return False

    state.ai_fund_balance -= amount
    state.ai_fund_spent += amount

    # Log the purchase
    purchase = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "amount": amount,
        "description": description,
        "category": category,
        "balance_after": state.ai_fund_balance,
    }
    AI_SPEND_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AI_SPEND_LOG, "a") as f:
        f.write(json.dumps(purchase, default=str) + "\n")

    save_state(state)
    log.info(f"🤖 AI Fund spent ₹{amount:,.0f} on {category}: {description}. "
             f"Balance: ₹{state.ai_fund_balance:,.0f}")
    return True


# ── Owner Withdrawal ─────────────────────────────────────────


def record_owner_withdrawal(state: CapitalState, amount: float,
                            method: str = "bank_transfer") -> bool:
    """
    Record a withdrawal from owner's pending balance.
    Returns True if sufficient pending balance.
    """
    if amount > state.owner_pending:
        log.warning(f"Insufficient owner balance: need ₹{amount:,.0f}, "
                    f"pending ₹{state.owner_pending:,.0f}")
        return False

    state.owner_pending -= amount
    state.owner_withdrawn += amount

    withdrawal = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "amount": amount,
        "method": method,
        "pending_after": state.owner_pending,
        "total_withdrawn": state.owner_withdrawn,
    }
    WITHDRAWAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(WITHDRAWAL_LOG, "a") as f:
        f.write(json.dumps(withdrawal, default=str) + "\n")

    save_state(state)
    log.info(f"💸 Owner withdrawal: ₹{amount:,.0f} via {method}. "
             f"Pending: ₹{state.owner_pending:,.0f}")
    return True


# ── Reporting ────────────────────────────────────────────────


def generate_daily_summary(state: CapitalState) -> dict:
    """Generate a summary dict for the daily report."""
    win_rate = (
        state.profitable_days / state.trading_days * 100
        if state.trading_days > 0 else 0.0
    )
    roi = (
        state.cumulative_pnl / state.initial_capital * 100
        if state.initial_capital > 0 else 0.0
    )
    compounding_gain = (
        (state.principal - state.initial_capital) / state.initial_capital * 100
        if state.initial_capital > 0 else 0.0
    )

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "principal": round(state.principal, 2),
        "portfolio_value": round(get_total_portfolio_value(state), 2),
        "today_pnl": round(state.realized_pnl_today, 2),
        "cumulative_pnl": round(state.cumulative_pnl, 2),
        "roi_pct": round(roi, 2),
        "compounding_gain_pct": round(compounding_gain, 2),
        "win_rate": round(win_rate, 1),
        "trading_days": state.trading_days,
        "profitable_days": state.profitable_days,
        "loss_days": state.loss_days,
        "max_drawdown_pct": round(state.max_drawdown_pct, 2),
        "current_drawdown_pct": round(get_current_drawdown_pct(state), 2),
        "consecutive_losses": state.consecutive_loss_days,
        "ai_fund_balance": round(state.ai_fund_balance, 2),
        "ai_fund_spent": round(state.ai_fund_spent, 2),
        "owner_pending": round(state.owner_pending, 2),
        "owner_withdrawn": round(state.owner_withdrawn, 2),
        "reinvested_total": round(state.reinvested_total, 2),
        "best_day": round(state.best_day_pnl, 2),
        "worst_day": round(state.worst_day_pnl, 2),
    }


def generate_monthly_report(state: CapitalState) -> str:
    """Generate a formatted monthly report string."""
    summary = generate_daily_summary(state)

    report = f"""
╔══════════════════════════════════════════════════════════╗
║           VIBE TRADING — MONTHLY REPORT                  ║
║           {summary['date']}                              ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  💰 CAPITAL                                              ║
║  ───────────                                             ║
║  Initial Capital:    ₹{state.initial_capital:>12,.0f}    ║
║  Current Principal:  ₹{state.principal:>12,.0f}          ║
║  Compounding Gain:    {summary['compounding_gain_pct']:>+10.1f}%        ║
║                                                          ║
║  📊 PERFORMANCE                                          ║
║  ───────────                                             ║
║  Cumulative P&L:     ₹{state.cumulative_pnl:>12,.0f}    ║
║  ROI:                 {summary['roi_pct']:>+10.1f}%      ║
║  Win Rate:            {summary['win_rate']:>10.1f}%      ║
║  Max Drawdown:        {summary['max_drawdown_pct']:>10.1f}%║
║  Trading Days:        {state.trading_days:>10d}           ║
║  Best Day:           ₹{state.best_day_pnl:>12,.0f}      ║
║  Worst Day:          ₹{state.worst_day_pnl:>12,.0f}     ║
║                                                          ║
║  💸 DISTRIBUTION (50/25/25)                              ║
║  ───────────                                             ║
║  Reinvested (50%):   ₹{state.reinvested_total:>12,.0f}  ║
║  AI Fund (25%):      ₹{state.ai_fund_total:>12,.0f}     ║
║    └─ Spent:         ₹{state.ai_fund_spent:>12,.0f}     ║
║    └─ Available:     ₹{state.ai_fund_balance:>12,.0f}   ║
║  Owner (25%):        ₹{state.owner_pending + state.owner_withdrawn:>12,.0f}║
║    └─ Withdrawn:     ₹{state.owner_withdrawn:>12,.0f}   ║
║    └─ Pending:       ₹{state.owner_pending:>12,.0f}     ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""
    return report.strip()


# ── CLI Entry Point ──────────────────────────────────────────

if __name__ == "__main__":
    import sys

    state = load_state()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            summary = generate_daily_summary(state)
            print(json.dumps(summary, indent=2))
        elif cmd == "report":
            print(generate_monthly_report(state))
        elif cmd == "simulate":
            # Simulate a profitable day for testing
            pnl = float(sys.argv[2]) if len(sys.argv) > 2 else 12450.0
            split = process_daily_pnl(state, pnl)
            print(json.dumps(split, indent=2))
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python -m orchestrator.capital_manager [status|report|simulate <pnl>]")
    else:
        print(generate_monthly_report(state))
