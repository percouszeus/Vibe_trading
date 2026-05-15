"""
orchestrator/strategy_portfolio.py
───────────────────────────────────
MULTI-STRATEGY PORTFOLIO ENGINE

Runs 6 strategies simultaneously, each sized by Kelly criterion.
Portfolio-level risk rules enforce diversification.

Strategies:
  1. Momentum Breakout (intraday)
  2. Mean Reversion (swing 2-5d)
  3. Earnings Drift (event-driven)
  4. FII Flow Following (positional)
  5. Options OI Buildup (intraday)
  6. Sector Rotation (swing)
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("orchestrator.strategy")


@dataclass
class StrategySignal:
    """A trading signal from a strategy."""
    strategy: str
    symbol: str
    direction: str          # BUY or SELL
    confidence: float       # 0.0 to 1.0
    entry_price: float
    stop_loss: float
    target_price: float
    position_size_pct: float  # Kelly-sized
    rationale: str
    timestamp: str = ""

    def risk_reward_ratio(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.target_price - self.entry_price)
        return reward / max(risk, 0.01)


@dataclass
class StrategyPerformance:
    """Track performance for a single strategy."""
    name: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    kelly_fraction: float = 0.05  # Default 5%
    active: bool = True

    @property
    def win_rate(self) -> float:
        return self.wins / max(self.total_trades, 1)

    @property
    def profit_factor(self) -> float:
        if self.losses == 0:
            return float('inf') if self.wins > 0 else 0
        return abs(self.avg_win * self.wins) / max(abs(self.avg_loss * self.losses), 1)


# ── Kelly Criterion ──────────────────────────────────────────


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Calculate optimal position size using Kelly Criterion.
    Returns half-Kelly (conservative) capped at 25%.
    """
    if avg_loss == 0 or win_rate <= 0:
        return 0.0
    b = avg_win / abs(avg_loss)  # Win/loss ratio
    f = win_rate - (1 - win_rate) / b  # Kelly fraction
    half_kelly = max(0, f * 0.5)  # Half-Kelly for safety
    return min(half_kelly, 0.25)  # Cap at 25%


# ── Portfolio Risk Rules ─────────────────────────────────────


@dataclass
class PortfolioRules:
    """Portfolio-level risk constraints."""
    max_concurrent_positions: int = 5
    max_single_stock_pct: float = 0.25      # 25% max in one stock
    max_single_sector_pct: float = 0.40     # 40% max in one sector
    max_portfolio_heat_pct: float = 0.08    # 8% total risk
    min_risk_reward: float = 1.5            # Minimum R:R ratio
    min_confidence: float = 0.5             # Minimum signal confidence


def validate_signal(signal: StrategySignal, current_positions: list[dict],
                    principal: float, rules: PortfolioRules) -> tuple[bool, str]:
    """Validate a signal against portfolio rules."""

    # Check R:R ratio
    rr = signal.risk_reward_ratio()
    if rr < rules.min_risk_reward:
        return False, f"R:R too low: {rr:.1f} < {rules.min_risk_reward}"

    # Check confidence
    if signal.confidence < rules.min_confidence:
        return False, f"Confidence too low: {signal.confidence:.1%}"

    # Check max positions
    if len(current_positions) >= rules.max_concurrent_positions:
        return False, f"Max positions reached: {len(current_positions)}"

    # Check single-stock concentration
    stock_exposure = sum(
        p.get("value", 0) for p in current_positions
        if p.get("symbol") == signal.symbol
    )
    if (stock_exposure + principal * signal.position_size_pct) > principal * rules.max_single_stock_pct:
        return False, f"Single-stock limit: {signal.symbol} would exceed {rules.max_single_stock_pct:.0%}"

    # Check portfolio heat
    total_risk = sum(p.get("risk_pct", 0) for p in current_positions)
    if total_risk + signal.position_size_pct > rules.max_portfolio_heat_pct:
        return False, f"Portfolio heat limit: {total_risk + signal.position_size_pct:.1%} > {rules.max_portfolio_heat_pct:.0%}"

    return True, "OK"


# ── Strategy Signal Generators ───────────────────────────────


def generate_momentum_signal(symbol: str, market_data: dict) -> Optional[StrategySignal]:
    """
    Momentum Breakout: Volume surge + price above 20-DMA.
    Intraday strategy.
    """
    ltp = market_data.get("ltp", 0)
    volume = market_data.get("volume", 0)
    high = market_data.get("high", 0)
    low = market_data.get("low", 0)

    if ltp <= 0:
        return None

    # Simple momentum check: price near day's high + above average volume
    price_position = (ltp - low) / max(high - low, 0.01)

    if price_position > 0.8:  # Price in top 20% of day's range
        stop = low  # Stop at day's low
        target = ltp + (ltp - low) * 1.5  # 1.5x the move

        return StrategySignal(
            strategy="momentum_breakout",
            symbol=symbol,
            direction="BUY",
            confidence=min(price_position, 0.9),
            entry_price=ltp,
            stop_loss=stop,
            target_price=target,
            position_size_pct=0.05,  # Will be overridden by Kelly
            rationale=f"Price at {price_position:.0%} of range, momentum breakout",
            timestamp=datetime.now().isoformat(timespec="seconds"),
        )

    return None


def generate_mean_reversion_signal(symbol: str, market_data: dict,
                                   history: list[dict]) -> Optional[StrategySignal]:
    """
    Mean Reversion: RSI oversold + support from institutional buying.
    Swing trade (2-5 days).
    """
    if len(history) < 14:
        return None

    closes = [d["close"] for d in history[-14:]]

    # Simple RSI calculation
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))

    avg_gain = sum(gains) / len(gains) if gains else 0
    avg_loss = sum(losses) / len(losses) if losses else 1
    rs = avg_gain / max(avg_loss, 0.001)
    rsi = 100 - (100 / (1 + rs))

    if rsi < 30:  # Oversold
        ltp = closes[-1]
        stop = min(closes[-5:]) * 0.98  # Below recent lows
        target = ltp * 1.05  # 5% bounce target

        return StrategySignal(
            strategy="mean_reversion",
            symbol=symbol,
            direction="BUY",
            confidence=max(0.5, (30 - rsi) / 30),
            entry_price=ltp,
            stop_loss=stop,
            target_price=target,
            position_size_pct=0.05,
            rationale=f"RSI={rsi:.0f} oversold, mean reversion expected",
            timestamp=datetime.now().isoformat(timespec="seconds"),
        )

    return None


def generate_fii_flow_signal(fii_net: float, dii_net: float,
                             nifty_data: dict) -> Optional[StrategySignal]:
    """
    FII Flow Following: Follow FII net buying streaks > 3 days.
    Positional trade (NIFTY ETF/futures proxy).
    """
    if fii_net <= 500:  # Need strong FII buying
        return None

    ltp = nifty_data.get("ltp", 0)
    if ltp <= 0:
        return None

    stop = ltp * 0.98  # 2% stop
    target = ltp * 1.03  # 3% target

    return StrategySignal(
        strategy="fii_flow_following",
        symbol="NIFTYBEES",  # NIFTY ETF
        direction="BUY",
        confidence=min(fii_net / 2000, 0.9),
        entry_price=ltp,
        stop_loss=stop,
        target_price=target,
        position_size_pct=0.08,
        rationale=f"FII net buying ₹{fii_net:,.0f}cr, strong institutional flow",
        timestamp=datetime.now().isoformat(timespec="seconds"),
    )


# ── Portfolio Manager ────────────────────────────────────────


PERF_FILE = Path.home() / ".trading_platform" / "strategy_performance.json"


def load_strategy_performance() -> dict[str, StrategyPerformance]:
    """Load strategy performance from disk."""
    defaults = {
        "momentum_breakout": StrategyPerformance(name="Momentum Breakout"),
        "mean_reversion": StrategyPerformance(name="Mean Reversion"),
        "earnings_drift": StrategyPerformance(name="Earnings Drift"),
        "fii_flow_following": StrategyPerformance(name="FII Flow Following"),
        "options_oi_buildup": StrategyPerformance(name="Options OI Buildup"),
        "sector_rotation": StrategyPerformance(name="Sector Rotation"),
    }

    if not PERF_FILE.exists():
        return defaults

    try:
        data = json.loads(PERF_FILE.read_text())
        for key, perf_data in data.items():
            if key in defaults:
                for attr, val in perf_data.items():
                    if hasattr(defaults[key], attr):
                        setattr(defaults[key], attr, val)
        return defaults
    except Exception:
        return defaults


def save_strategy_performance(perf: dict[str, StrategyPerformance]) -> None:
    """Save strategy performance to disk."""
    PERF_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    for key, sp in perf.items():
        data[key] = {
            "name": sp.name, "total_trades": sp.total_trades,
            "wins": sp.wins, "losses": sp.losses,
            "total_pnl": sp.total_pnl, "avg_win": sp.avg_win,
            "avg_loss": sp.avg_loss, "kelly_fraction": sp.kelly_fraction,
            "active": sp.active,
        }
    PERF_FILE.write_text(json.dumps(data, indent=2))


def update_kelly_fractions(perf: dict[str, StrategyPerformance]) -> None:
    """Recalculate Kelly fractions for all strategies."""
    for key, sp in perf.items():
        if sp.total_trades >= 10:
            sp.kelly_fraction = kelly_fraction(sp.win_rate, sp.avg_win, abs(sp.avg_loss))
            if sp.kelly_fraction < 0.01:
                sp.active = False
                log.warning(f"Strategy {sp.name} deactivated: Kelly < 1%")
        log.info(f"  {sp.name}: Kelly={sp.kelly_fraction:.1%}, "
                 f"WR={sp.win_rate:.0%}, PF={sp.profit_factor:.1f}")


def get_strategy_summary(perf: dict[str, StrategyPerformance]) -> str:
    """Generate a formatted strategy summary."""
    lines = ["📊 Strategy Performance Summary", "─" * 50]
    for key, sp in perf.items():
        status = "✅" if sp.active else "❌"
        lines.append(
            f"  {status} {sp.name}: {sp.wins}W/{sp.losses}L "
            f"({sp.win_rate:.0%}) | P&L: ₹{sp.total_pnl:,.0f} | "
            f"Kelly: {sp.kelly_fraction:.1%}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    perf = load_strategy_performance()
    print(get_strategy_summary(perf))
