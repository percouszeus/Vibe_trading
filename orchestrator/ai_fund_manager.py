"""
orchestrator/ai_fund_manager.py
────────────────────────────────
AI SELF-IMPROVEMENT FUND MANAGER

Manages the 25% AI improvement allocation from profits.
Evaluates performance gaps and auto-purchases improvements.

Priorities: LLM Credits > Premium Data > Compute > Fine-tuning > Factor Data
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("orchestrator.ai_fund")

SPEND_LOG = Path.home() / ".trading_platform" / "ai_spend_log.jsonl"


@dataclass
class SpendingPriority:
    category: str
    description: str
    estimated_cost: float
    expected_impact: str
    urgency: float
    auto_approve: bool


@dataclass
class PerformanceGaps:
    rolling_win_rate: float = 0.0
    news_miss_rate: float = 0.0
    strategy_stagnation: bool = False
    llm_free_tier_exhausted: bool = False
    model_accuracy: float = 0.0
    data_staleness_issues: int = 0


def evaluate_spending_priorities(
    ai_fund_balance: float,
    gaps: PerformanceGaps,
    auto_approve_limit: float = 500.0,
) -> list[SpendingPriority]:
    """Evaluate what the AI fund should spend on based on performance gaps."""
    priorities = []

    if gaps.rolling_win_rate < 0.45 or gaps.llm_free_tier_exhausted:
        urgency = 0.9 if gaps.llm_free_tier_exhausted else 0.7
        cost = min(500.0, ai_fund_balance * 0.3)
        priorities.append(SpendingPriority(
            category="llm_credits",
            description=f"Buy LLM credits — win rate at {gaps.rolling_win_rate:.0%}",
            estimated_cost=cost, expected_impact="+5-10% win rate",
            urgency=urgency, auto_approve=cost <= auto_approve_limit,
        ))

    if gaps.news_miss_rate > 0.3:
        priorities.append(SpendingPriority(
            category="news_data",
            description=f"NewsAPI Pro — missing {gaps.news_miss_rate:.0%} news moves",
            estimated_cost=750.0, expected_impact="+3-5% event trade win rate",
            urgency=0.6, auto_approve=750.0 <= auto_approve_limit,
        ))

    if gaps.model_accuracy < 0.50:
        cost = min(2000.0, ai_fund_balance * 0.5)
        priorities.append(SpendingPriority(
            category="fine_tune",
            description=f"Fine-tune on trade journal — accuracy {gaps.model_accuracy:.0%}",
            estimated_cost=cost, expected_impact="+10-15% prediction accuracy",
            urgency=0.5, auto_approve=False,
        ))

    if gaps.strategy_stagnation:
        priorities.append(SpendingPriority(
            category="factor_data",
            description="NSE factor data — strategy improvement stalled",
            estimated_cost=min(1500.0, ai_fund_balance * 0.4),
            expected_impact="New alpha sources", urgency=0.4, auto_approve=False,
        ))

    if gaps.data_staleness_issues > 3:
        priorities.append(SpendingPriority(
            category="data_quality",
            description=f"{gaps.data_staleness_issues} stale data incidents",
            estimated_cost=300.0, expected_impact="Reliable signals",
            urgency=0.5, auto_approve=300.0 <= auto_approve_limit,
        ))

    priorities.sort(key=lambda p: p.urgency, reverse=True)
    return [p for p in priorities if p.estimated_cost <= ai_fund_balance]


def auto_spend(ai_fund_balance: float, gaps: PerformanceGaps,
               auto_approve_limit: float = 500.0) -> list[dict]:
    """Auto-execute spending on auto-approved priorities."""
    priorities = evaluate_spending_priorities(ai_fund_balance, gaps, auto_approve_limit)
    purchases = []

    for p in priorities:
        if not p.auto_approve or p.estimated_cost > ai_fund_balance:
            continue
        purchase = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "category": p.category, "description": p.description,
            "amount": p.estimated_cost, "auto_approved": True,
        }
        _log_purchase(purchase)
        purchases.append(purchase)
        ai_fund_balance -= p.estimated_cost
        log.info(f"🤖 Auto-purchased: {p.category} — ₹{p.estimated_cost:,.0f}")

    return purchases


def get_spending_history(days: int = 30) -> list[dict]:
    if not SPEND_LOG.exists():
        return []
    history = []
    with open(SPEND_LOG) as f:
        for line in f:
            try:
                history.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return history[-100:]


def get_spending_summary() -> dict:
    history = get_spending_history(days=365)
    summary = {"total_spent": 0.0, "by_category": {}, "purchase_count": len(history)}
    for entry in history:
        cat = entry.get("category", "unknown")
        amt = entry.get("amount", 0)
        summary["total_spent"] += amt
        summary["by_category"][cat] = summary["by_category"].get(cat, 0.0) + amt
    return summary


def detect_performance_gaps() -> PerformanceGaps:
    """Detect current performance gaps by analyzing recent trade history."""
    gaps = PerformanceGaps()
    journal_dir = Path.home() / ".trading_platform" / "journal"
    if not journal_dir.exists():
        return gaps

    import glob
    journal_files = sorted(glob.glob(str(journal_dir / "*.jsonl")))[-20:]
    total_trades, wins, stale = 0, 0, 0

    for jf in journal_files:
        try:
            with open(jf) as f:
                for line in f:
                    entry = json.loads(line)
                    if entry.get("phase") == "analysis":
                        for s in entry.get("signals", []):
                            total_trades += 1
                            if s.get("status") == "success":
                                wins += 1
                    if entry.get("phase") == "auto_heal":
                        for c in entry.get("checks", []):
                            if c.get("status") != "healthy":
                                stale += 1
        except Exception:
            continue

    gaps.rolling_win_rate = wins / max(total_trades, 1)
    gaps.data_staleness_issues = stale
    gaps.strategy_stagnation = total_trades > 20 and gaps.rolling_win_rate < 0.45
    return gaps


def _log_purchase(purchase: dict) -> None:
    SPEND_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SPEND_LOG, "a") as f:
        f.write(json.dumps(purchase, default=str) + "\n")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "evaluate":
        gaps = detect_performance_gaps()
        print(f"Win Rate: {gaps.rolling_win_rate:.1%}")
        print(f"Stale Data: {gaps.data_staleness_issues}")
        priorities = evaluate_spending_priorities(10000, gaps)
        for p in priorities:
            print(f"  [{p.urgency:.1f}] {p.category}: ₹{p.estimated_cost:,.0f}")
    else:
        print(json.dumps(get_spending_summary(), indent=2))
