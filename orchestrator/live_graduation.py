"""
orchestrator/live_graduation.py
────────────────────────────────
PAPER → LIVE TRADING GRADUATION ENGINE

Transition modes:
  PAPER      → All trades simulated
  SHADOW     → Live data, simulated execution, side-by-side
  MICRO_LIVE → 10% capital live, 90% paper
  FULL_LIVE  → Graduated, full capital, all safety rails active

Graduation requires ALL criteria to pass over 60+ trading days.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum

log = logging.getLogger("orchestrator.graduation")

GRAD_STATE_FILE = Path.home() / ".trading_platform" / "graduation_state.json"


class TradingMode(str, Enum):
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    MICRO_LIVE = "MICRO_LIVE"
    FULL_LIVE = "FULL_LIVE"


@dataclass
class GraduationCriteria:
    """All criteria that must pass for graduation."""
    min_trading_days: int = 60
    min_win_rate: float = 0.50
    min_sharpe: float = 1.0
    max_drawdown_pct: float = 10.0
    min_profit_factor: float = 1.5
    max_consecutive_losses: int = 5
    min_model_accuracy: float = 0.55


@dataclass
class LiveSafetyConfig:
    """Circuit breakers for live trading."""
    daily_loss_limit_pct: float = 0.03      # Stop if -3% day
    weekly_loss_limit_pct: float = 0.05     # Stop if -5% week
    max_position_size_pct: float = 0.10     # 10% per position
    live_start_fraction: float = 0.10       # Start with 10% live
    scale_up_after_days: int = 20           # Add 10% every 20 profitable days
    max_live_fraction: float = 1.0
    emergency_stop_drawdown: float = 0.15   # 15% = close everything
    human_approval_above: float = 100_000   # Orders > ₹1L need approval


@dataclass
class GraduationState:
    """Current graduation progress."""
    current_mode: str = "PAPER"
    trading_days: int = 0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float = 0.0
    max_consecutive_losses: int = 0
    model_accuracy: float = 0.0
    live_fraction: float = 0.0           # Current % of capital in live
    live_profitable_days: int = 0
    criteria_met: dict = field(default_factory=dict)
    last_evaluated: str = ""
    graduation_date: str = ""            # When graduated to current mode


def load_graduation_state() -> GraduationState:
    """Load graduation state from disk."""
    if GRAD_STATE_FILE.exists():
        try:
            data = json.loads(GRAD_STATE_FILE.read_text())
            state = GraduationState()
            for k, v in data.items():
                if hasattr(state, k):
                    setattr(state, k, v)
            return state
        except Exception as e:
            log.error(f"Failed to load graduation state: {e}")
    return GraduationState()


def save_graduation_state(state: GraduationState) -> None:
    """Persist graduation state."""
    GRAD_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    from dataclasses import asdict
    GRAD_STATE_FILE.write_text(json.dumps(asdict(state), indent=2, default=str))


def evaluate_graduation(
    state: GraduationState,
    criteria: GraduationCriteria = GraduationCriteria(),
) -> dict:
    """
    Evaluate whether the system meets graduation criteria.
    Returns a detailed report of which criteria pass/fail.
    """
    state.last_evaluated = datetime.now().isoformat(timespec="seconds")

    checks = {
        "trading_days": {
            "required": criteria.min_trading_days,
            "actual": state.trading_days,
            "passed": state.trading_days >= criteria.min_trading_days,
            "label": f"{state.trading_days}/{criteria.min_trading_days} days",
        },
        "win_rate": {
            "required": criteria.min_win_rate,
            "actual": state.win_rate,
            "passed": state.win_rate >= criteria.min_win_rate,
            "label": f"{state.win_rate:.0%} (need {criteria.min_win_rate:.0%})",
        },
        "sharpe_ratio": {
            "required": criteria.min_sharpe,
            "actual": state.sharpe_ratio,
            "passed": state.sharpe_ratio >= criteria.min_sharpe,
            "label": f"{state.sharpe_ratio:.2f} (need {criteria.min_sharpe:.1f})",
        },
        "max_drawdown": {
            "required": criteria.max_drawdown_pct,
            "actual": state.max_drawdown_pct,
            "passed": state.max_drawdown_pct <= criteria.max_drawdown_pct,
            "label": f"{state.max_drawdown_pct:.1f}% (max {criteria.max_drawdown_pct:.0f}%)",
        },
        "profit_factor": {
            "required": criteria.min_profit_factor,
            "actual": state.profit_factor,
            "passed": state.profit_factor >= criteria.min_profit_factor,
            "label": f"{state.profit_factor:.1f} (need {criteria.min_profit_factor:.1f})",
        },
        "consecutive_losses": {
            "required": criteria.max_consecutive_losses,
            "actual": state.max_consecutive_losses,
            "passed": state.max_consecutive_losses <= criteria.max_consecutive_losses,
            "label": f"{state.max_consecutive_losses} (max {criteria.max_consecutive_losses})",
        },
        "model_accuracy": {
            "required": criteria.min_model_accuracy,
            "actual": state.model_accuracy,
            "passed": state.model_accuracy >= criteria.min_model_accuracy,
            "label": f"{state.model_accuracy:.0%} (need {criteria.min_model_accuracy:.0%})",
        },
    }

    all_passed = all(c["passed"] for c in checks.values())
    state.criteria_met = {k: v["passed"] for k, v in checks.items()}

    result = {
        "all_passed": all_passed,
        "current_mode": state.current_mode,
        "recommended_mode": _recommend_mode(state, all_passed),
        "checks": checks,
        "progress_pct": sum(1 for c in checks.values() if c["passed"]) / len(checks) * 100,
    }

    save_graduation_state(state)
    return result


def _recommend_mode(state: GraduationState, all_passed: bool) -> str:
    """Recommend the next trading mode based on criteria."""
    if state.current_mode == "PAPER" and all_passed:
        return "SHADOW"
    elif state.current_mode == "SHADOW" and all_passed:
        return "MICRO_LIVE"
    elif state.current_mode == "MICRO_LIVE" and state.live_profitable_days >= 20:
        return "FULL_LIVE"
    return state.current_mode


def promote_mode(state: GraduationState, new_mode: str) -> bool:
    """Promote to a new trading mode. Only allows forward transitions."""
    valid_transitions = {
        "PAPER": ["SHADOW"],
        "SHADOW": ["MICRO_LIVE", "PAPER"],
        "MICRO_LIVE": ["FULL_LIVE", "SHADOW", "PAPER"],
        "FULL_LIVE": ["MICRO_LIVE", "PAPER"],
    }

    current = state.current_mode
    if new_mode not in valid_transitions.get(current, []):
        log.error(f"Invalid transition: {current} → {new_mode}")
        return False

    state.current_mode = new_mode
    state.graduation_date = datetime.now().isoformat(timespec="seconds")

    if new_mode == "MICRO_LIVE":
        state.live_fraction = 0.10  # Start with 10%
    elif new_mode == "FULL_LIVE":
        state.live_fraction = 1.0

    save_graduation_state(state)
    log.info(f"🎓 MODE PROMOTED: {current} → {new_mode}")
    return True


def check_circuit_breakers(
    daily_pnl_pct: float,
    weekly_pnl_pct: float,
    current_drawdown_pct: float,
    safety: LiveSafetyConfig = LiveSafetyConfig(),
) -> tuple[bool, str]:
    """Check if circuit breakers should halt live trading."""
    if daily_pnl_pct <= -safety.daily_loss_limit_pct:
        return True, f"Daily loss limit: {daily_pnl_pct:.1%} <= -{safety.daily_loss_limit_pct:.0%}"

    if weekly_pnl_pct <= -safety.weekly_loss_limit_pct:
        return True, f"Weekly loss limit: {weekly_pnl_pct:.1%}"

    if current_drawdown_pct >= safety.emergency_stop_drawdown * 100:
        return True, f"Emergency drawdown: {current_drawdown_pct:.1f}%"

    return False, "OK"


def get_graduation_progress_text(state: GraduationState) -> str:
    """Generate human-readable graduation progress."""
    criteria = GraduationCriteria()
    result = evaluate_graduation(state, criteria)

    lines = [
        f"🎓 Graduation Progress ({result['progress_pct']:.0f}%)",
        f"   Current Mode: {state.current_mode}",
        "",
    ]

    for name, check in result["checks"].items():
        icon = "✅" if check["passed"] else "⚠️"
        lines.append(f"   {icon} {name}: {check['label']}")

    if result["all_passed"]:
        lines.append(f"\n   ✨ Ready to promote to: {result['recommended_mode']}")

    return "\n".join(lines)


if __name__ == "__main__":
    state = load_graduation_state()
    print(get_graduation_progress_text(state))
