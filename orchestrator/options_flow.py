"""
orchestrator/options_flow.py
─────────────────────────────
OPTIONS INTELLIGENCE LAYER

Analyzes options market data for trading signals:
  - PCR (Put/Call Ratio) for NIFTY
  - Max Pain calculation for expiry week
  - OI Buildup detection at specific strikes
  - IV Percentile for cheap/expensive options
  - Straddle premium for range estimation
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("orchestrator.options")


@dataclass
class OptionsSnapshot:
    """Snapshot of options market data."""
    symbol: str
    spot_price: float
    pcr: float                    # Put/Call ratio
    max_pain: float               # Max pain strike
    iv_percentile: float          # 0-100 (where current IV sits vs 1yr)
    atm_iv: float                 # At-the-money implied volatility
    straddle_premium_pct: float   # ATM straddle as % of spot
    total_call_oi: int
    total_put_oi: int
    top_call_oi_strike: float     # Strike with highest call OI (resistance)
    top_put_oi_strike: float      # Strike with highest put OI (support)
    oi_buildup_signals: list      # Unusual OI changes
    timestamp: str = ""


@dataclass
class OptionsSignal:
    """Trading signal from options analysis."""
    signal_type: str              # pcr_extreme, oi_buildup, iv_cheap, max_pain_magnet
    direction: str                # BULLISH, BEARISH, NEUTRAL
    confidence: float
    description: str
    strike: float = 0
    expiry: str = ""


# ── PCR Analysis ─────────────────────────────────────────────


def analyze_pcr(pcr: float) -> OptionsSignal:
    """
    Analyze Put/Call Ratio.
    PCR > 1.3: Extreme put buying → contrarian bullish
    PCR < 0.7: Extreme call buying → contrarian bearish
    0.8-1.2: Neutral zone
    """
    if pcr > 1.5:
        return OptionsSignal(
            signal_type="pcr_extreme", direction="BULLISH",
            confidence=0.8, description=f"PCR {pcr:.2f} — extreme fear, contrarian BUY signal",
        )
    elif pcr > 1.3:
        return OptionsSignal(
            signal_type="pcr_extreme", direction="BULLISH",
            confidence=0.6, description=f"PCR {pcr:.2f} — elevated fear, mildly bullish",
        )
    elif pcr < 0.5:
        return OptionsSignal(
            signal_type="pcr_extreme", direction="BEARISH",
            confidence=0.8, description=f"PCR {pcr:.2f} — extreme greed, contrarian SELL signal",
        )
    elif pcr < 0.7:
        return OptionsSignal(
            signal_type="pcr_extreme", direction="BEARISH",
            confidence=0.6, description=f"PCR {pcr:.2f} — elevated greed, mildly bearish",
        )
    else:
        return OptionsSignal(
            signal_type="pcr_neutral", direction="NEUTRAL",
            confidence=0.3, description=f"PCR {pcr:.2f} — neutral zone",
        )


# ── Max Pain Analysis ───────────────────────────────────────


def calculate_max_pain(option_chain: list[dict], spot: float) -> float:
    """
    Calculate max pain — the strike price where total loss for
    option buyers is maximum (i.e., where price tends to pin at expiry).
    """
    if not option_chain:
        return spot

    strikes = set()
    for opt in option_chain:
        strikes.add(opt.get("strike", 0))

    if not strikes:
        return spot

    min_pain = float('inf')
    max_pain_strike = spot

    for test_strike in sorted(strikes):
        total_pain = 0
        for opt in option_chain:
            strike = opt.get("strike", 0)
            call_oi = opt.get("call_oi", 0)
            put_oi = opt.get("put_oi", 0)

            # Call buyer pain: max(0, test_strike - strike) * call_oi
            if test_strike > strike:
                total_pain += (test_strike - strike) * call_oi

            # Put buyer pain: max(0, strike - test_strike) * put_oi
            if strike > test_strike:
                total_pain += (strike - test_strike) * put_oi

        if total_pain < min_pain:
            min_pain = total_pain
            max_pain_strike = test_strike

    return max_pain_strike


def analyze_max_pain(spot: float, max_pain: float) -> OptionsSignal:
    """Analyze max pain relative to spot price."""
    diff_pct = (max_pain - spot) / spot * 100

    if abs(diff_pct) < 0.5:
        return OptionsSignal(
            signal_type="max_pain_magnet", direction="NEUTRAL",
            confidence=0.7, description=f"Max pain at {max_pain:.0f} (spot {spot:.0f}) — at pin level",
            strike=max_pain,
        )
    elif diff_pct > 1.0:
        return OptionsSignal(
            signal_type="max_pain_magnet", direction="BULLISH",
            confidence=0.5, description=f"Max pain {max_pain:.0f} above spot by {diff_pct:.1f}% — upward pull",
            strike=max_pain,
        )
    elif diff_pct < -1.0:
        return OptionsSignal(
            signal_type="max_pain_magnet", direction="BEARISH",
            confidence=0.5, description=f"Max pain {max_pain:.0f} below spot by {abs(diff_pct):.1f}% — downward pull",
            strike=max_pain,
        )
    else:
        return OptionsSignal(
            signal_type="max_pain_magnet", direction="NEUTRAL",
            confidence=0.4, description=f"Max pain {max_pain:.0f} near spot",
            strike=max_pain,
        )


# ── OI Buildup Detection ────────────────────────────────────


def detect_oi_buildup(option_chain: list[dict], prev_chain: list[dict],
                      threshold_pct: float = 20.0) -> list[OptionsSignal]:
    """
    Detect unusual open interest buildup.
    OI increase > threshold% at a strike = significant positioning.
    """
    signals = []
    if not option_chain or not prev_chain:
        return signals

    prev_map = {}
    for opt in prev_chain:
        prev_map[opt.get("strike", 0)] = opt

    for opt in option_chain:
        strike = opt.get("strike", 0)
        prev = prev_map.get(strike, {})

        # Check call OI buildup
        call_oi = opt.get("call_oi", 0)
        prev_call_oi = prev.get("call_oi", 0)
        if prev_call_oi > 0:
            call_change_pct = (call_oi - prev_call_oi) / prev_call_oi * 100
            if call_change_pct > threshold_pct and call_oi > 10000:
                signals.append(OptionsSignal(
                    signal_type="oi_buildup", direction="BEARISH",
                    confidence=min(call_change_pct / 100, 0.9),
                    description=f"Call OI buildup {call_change_pct:.0f}% at {strike} — resistance",
                    strike=strike,
                ))

        # Check put OI buildup
        put_oi = opt.get("put_oi", 0)
        prev_put_oi = prev.get("put_oi", 0)
        if prev_put_oi > 0:
            put_change_pct = (put_oi - prev_put_oi) / prev_put_oi * 100
            if put_change_pct > threshold_pct and put_oi > 10000:
                signals.append(OptionsSignal(
                    signal_type="oi_buildup", direction="BULLISH",
                    confidence=min(put_change_pct / 100, 0.9),
                    description=f"Put OI buildup {put_change_pct:.0f}% at {strike} — support",
                    strike=strike,
                ))

    return signals


# ── IV Analysis ──────────────────────────────────────────────


def analyze_iv_percentile(iv_percentile: float) -> OptionsSignal:
    """
    Analyze IV percentile for options trading signals.
    Low IV = cheap options (buy strategies)
    High IV = expensive options (sell strategies)
    """
    if iv_percentile < 20:
        return OptionsSignal(
            signal_type="iv_cheap", direction="NEUTRAL",
            confidence=0.7,
            description=f"IV percentile {iv_percentile:.0f}% — options CHEAP, buy straddles/strangles",
        )
    elif iv_percentile > 80:
        return OptionsSignal(
            signal_type="iv_expensive", direction="NEUTRAL",
            confidence=0.7,
            description=f"IV percentile {iv_percentile:.0f}% — options EXPENSIVE, sell premium",
        )
    else:
        return OptionsSignal(
            signal_type="iv_normal", direction="NEUTRAL",
            confidence=0.3,
            description=f"IV percentile {iv_percentile:.0f}% — normal range",
        )


# ── Straddle Range Estimation ────────────────────────────────


def estimate_expected_range(spot: float, straddle_premium_pct: float) -> dict:
    """
    Use ATM straddle premium to estimate expected move range.
    Market expects spot ± straddle_premium by expiry.
    """
    move = spot * straddle_premium_pct / 100
    return {
        "spot": spot,
        "expected_high": round(spot + move, 2),
        "expected_low": round(spot - move, 2),
        "expected_range_pct": round(straddle_premium_pct, 2),
        "breakeven_up": round(spot + move, 2),
        "breakeven_down": round(spot - move, 2),
    }


# ── Combined Options Intelligence ───────────────────────────


def get_options_intelligence(
    spot: float, pcr: float, iv_percentile: float,
    max_pain: float, straddle_prem_pct: float,
    option_chain: list[dict] = None,
    prev_chain: list[dict] = None,
) -> dict:
    """Run all options analysis and return combined intelligence."""
    signals = []

    signals.append(analyze_pcr(pcr))
    signals.append(analyze_max_pain(spot, max_pain))
    signals.append(analyze_iv_percentile(iv_percentile))

    if option_chain and prev_chain:
        signals.extend(detect_oi_buildup(option_chain, prev_chain))

    range_est = estimate_expected_range(spot, straddle_prem_pct)

    # Determine overall bias
    bullish = sum(1 for s in signals if s.direction == "BULLISH")
    bearish = sum(1 for s in signals if s.direction == "BEARISH")

    if bullish > bearish + 1:
        overall = "BULLISH"
    elif bearish > bullish + 1:
        overall = "BEARISH"
    else:
        overall = "NEUTRAL"

    return {
        "overall_bias": overall,
        "signals": [
            {"type": s.signal_type, "direction": s.direction,
             "confidence": s.confidence, "description": s.description}
            for s in signals
        ],
        "expected_range": range_est,
        "pcr": pcr,
        "max_pain": max_pain,
        "iv_percentile": iv_percentile,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    # Demo with sample data
    result = get_options_intelligence(
        spot=24500, pcr=1.35, iv_percentile=25,
        max_pain=24400, straddle_prem_pct=2.5,
    )
    print(json.dumps(result, indent=2))
