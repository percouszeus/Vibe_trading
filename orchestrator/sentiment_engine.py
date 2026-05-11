"""
orchestrator/sentiment_engine.py
─────────────────────────────────
SENTIMENT ATTRIBUTION ENGINE

Answers the question: "What moved the candle?"

For every significant price move, this module attributes causality
across 6 dimensions:

  1. INSTITUTIONAL  - FII/DII net buying/selling
  2. OPTIONS FLOW   - PCR shift, OI buildup, unusual activity
  3. NEWS/MACRO     - Breaking news, earnings, policy changes
  4. VOLUME         - Unusual volume, buyer/seller aggression
  5. SECTOR         - Sector-wide rotation vs stock-specific move
  6. GLOBAL CUES    - Correlation with US/Asia/Europe markets

Each dimension gets a score from -100 (extreme bearish) to +100
(extreme bullish), and a confidence weight. The highest-weighted
dimension is the "primary mover".
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("orchestrator.sentiment")


@dataclass
class SentimentDimension:
    """A single sentiment dimension score."""
    name: str
    score: float        # -100 to +100
    confidence: float   # 0.0 to 1.0
    evidence: str       # Human-readable explanation
    raw_data: dict = field(default_factory=dict)


@dataclass
class SentimentAttribution:
    """Full sentiment attribution for a price move."""
    symbol: str
    timestamp: str
    price_change_pct: float
    dimensions: list[SentimentDimension]
    primary_mover: str          # Name of highest-impact dimension
    primary_score: float
    narrative: str              # LLM-generated explanation

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "price_change_pct": self.price_change_pct,
            "primary_mover": self.primary_mover,
            "primary_score": self.primary_score,
            "narrative": self.narrative,
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.score,
                    "confidence": d.confidence,
                    "evidence": d.evidence,
                }
                for d in self.dimensions
            ],
        }


# ── Dimension Analyzers ──────────────────────────────────────

def analyze_institutional(symbol: str) -> SentimentDimension:
    """
    FII/DII flow analysis.
    - Net FII buying > 500cr = bullish signal
    - Net DII buying when FII selling = support signal
    """
    from orchestrator.market_data import get_nse_fii_dii_data

    fii_dii = get_nse_fii_dii_data()
    score = 0.0
    confidence = 0.3
    evidence = "FII/DII data unavailable"

    if fii_dii.get("status") == "ok":
        data = fii_dii.get("data", [])
        if data:
            confidence = 0.7

            # Parse FII and DII net values
            fii_net = 0
            dii_net = 0
            for entry in data if isinstance(data, list) else [data]:
                cat = entry.get("category", "")
                net_val = float(entry.get("netValue", 0))
                if "FII" in cat.upper() or "FPI" in cat.upper():
                    fii_net = net_val
                elif "DII" in cat.upper():
                    dii_net = net_val

            # Score: FII buying is strongest signal
            if fii_net > 1000:
                score = 80
            elif fii_net > 500:
                score = 50
            elif fii_net > 0:
                score = 20
            elif fii_net > -500:
                score = -20
            elif fii_net > -1000:
                score = -50
            else:
                score = -80

            # DII as counter-signal
            if fii_net < -500 and dii_net > 500:
                score = max(score, -30)  # DII support limits downside
                evidence = f"FII selling ({fii_net:.0f}cr) but DII buying ({dii_net:.0f}cr) - support"
            else:
                evidence = f"FII: {fii_net:+.0f}cr, DII: {dii_net:+.0f}cr"

    return SentimentDimension(
        name="INSTITUTIONAL",
        score=score,
        confidence=confidence,
        evidence=evidence,
        raw_data=fii_dii,
    )


def analyze_volume(symbol: str) -> SentimentDimension:
    """
    Volume analysis - unusual volume indicates institutional interest.
    Volume > 2x 20-day avg = significant.
    """
    from orchestrator.market_data import get_historical_ohlcv

    history = get_historical_ohlcv(symbol, days=30)
    score = 0.0
    confidence = 0.4
    evidence = "Volume data unavailable"

    if len(history) >= 5:
        volumes = [d["volume"] for d in history]
        avg_vol = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 1
        today_vol = volumes[-1]
        vol_ratio = today_vol / max(avg_vol, 1)

        # Price direction determines sign
        if len(history) >= 2:
            price_change = history[-1]["close"] - history[-2]["close"]
            direction = 1 if price_change > 0 else -1
        else:
            direction = 0

        if vol_ratio > 3.0:
            score = 90 * direction
            confidence = 0.9
            evidence = f"Volume {vol_ratio:.1f}x avg ({today_vol:,.0f} vs avg {avg_vol:,.0f}) - EXTREME"
        elif vol_ratio > 2.0:
            score = 60 * direction
            confidence = 0.7
            evidence = f"Volume {vol_ratio:.1f}x avg - HIGH ACTIVITY"
        elif vol_ratio > 1.5:
            score = 30 * direction
            confidence = 0.5
            evidence = f"Volume {vol_ratio:.1f}x avg - above normal"
        else:
            score = 10 * direction
            confidence = 0.3
            evidence = f"Volume {vol_ratio:.1f}x avg - normal"

    return SentimentDimension(
        name="VOLUME",
        score=score,
        confidence=confidence,
        evidence=evidence,
    )


def analyze_sector(symbol: str) -> SentimentDimension:
    """
    Sector rotation - is this a sector-wide move or stock-specific?
    Compares stock's move with NIFTY and sector peers.
    """
    from orchestrator.market_data import get_stock_data_yfinance

    score = 0.0
    confidence = 0.3
    evidence = "Sector data unavailable"

    try:
        stock = get_stock_data_yfinance(symbol, period="5d")
        nifty = get_stock_data_yfinance("^NSEI", period="5d")

        if stock.get("status") == "ok" and nifty.get("status") == "ok":
            stock_chg = stock.get("change_pct", 0)
            nifty_chg = nifty.get("change_pct", 0)
            diff = stock_chg - nifty_chg

            if abs(diff) < 0.5:
                score = nifty_chg * 10  # Market-driven move
                confidence = 0.6
                evidence = f"Market-wide move (stock {stock_chg:+.1f}% vs NIFTY {nifty_chg:+.1f}%)"
            elif abs(diff) > 2.0:
                score = stock_chg * 15  # Stock-specific
                confidence = 0.8
                evidence = f"Stock-SPECIFIC move ({stock_chg:+.1f}% vs NIFTY {nifty_chg:+.1f}%, diff={diff:+.1f}%)"
            else:
                score = stock_chg * 10
                confidence = 0.5
                evidence = f"Partial sector correlation ({stock_chg:+.1f}% vs NIFTY {nifty_chg:+.1f}%)"

    except Exception as e:
        log.warning(f"Sector analysis failed: {e}")

    return SentimentDimension(
        name="SECTOR",
        score=max(-100, min(100, score)),
        confidence=confidence,
        evidence=evidence,
    )


def analyze_vix_regime() -> SentimentDimension:
    """
    India VIX analysis - fear/greed gauge.
    VIX < 12 = complacency, VIX > 20 = fear, VIX > 30 = panic
    """
    from orchestrator.market_data import get_india_vix

    vix = get_india_vix()
    if vix <= 0:
        return SentimentDimension("VIX_REGIME", 0, 0.1, "VIX unavailable")

    if vix < 12:
        score = 40
        evidence = f"VIX {vix:.1f} - LOW FEAR (complacency zone, potential reversal risk)"
    elif vix < 16:
        score = 20
        evidence = f"VIX {vix:.1f} - normal/calm market"
    elif vix < 20:
        score = -10
        evidence = f"VIX {vix:.1f} - elevated caution"
    elif vix < 25:
        score = -40
        evidence = f"VIX {vix:.1f} - HIGH FEAR"
    else:
        score = -70
        evidence = f"VIX {vix:.1f} - PANIC zone"

    return SentimentDimension(
        name="VIX_REGIME",
        score=score,
        confidence=0.6,
        evidence=evidence,
        raw_data={"vix": vix},
    )


def analyze_global_cues() -> SentimentDimension:
    """
    Check correlation with global markets.
    S&P 500, Nasdaq, Hang Seng, Nikkei, European futures.
    """
    from orchestrator.market_data import get_stock_data_yfinance

    global_indices = {
        "^GSPC": "S&P 500",
        "^IXIC": "Nasdaq",
        "^HSI": "Hang Seng",
        "^N225": "Nikkei",
    }

    moves = {}
    for ticker, name in global_indices.items():
        data = get_stock_data_yfinance(ticker, period="5d")
        if data.get("status") == "ok":
            moves[name] = data.get("change_pct", 0)

    if not moves:
        return SentimentDimension("GLOBAL", 0, 0.1, "Global data unavailable")

    avg_global = sum(moves.values()) / len(moves)
    score = avg_global * 20  # Amplify

    parts = [f"{name}: {chg:+.1f}%" for name, chg in moves.items()]
    evidence = f"Global cues: {', '.join(parts)}"

    return SentimentDimension(
        name="GLOBAL",
        score=max(-100, min(100, score)),
        confidence=0.5,
        evidence=evidence,
        raw_data=moves,
    )


# ── Main Attribution Function ────────────────────────────────

def attribute_sentiment(symbol: str) -> SentimentAttribution:
    """
    Run full sentiment attribution for a stock.
    Returns which factor most likely moved the candle.
    """
    log.info(f"Running sentiment attribution for {symbol}...")

    # Get current price change
    from orchestrator.market_data import get_stock_data_yfinance
    stock_data = get_stock_data_yfinance(symbol, period="5d")
    price_change = stock_data.get("change_pct", 0.0) if stock_data.get("status") == "ok" else 0.0

    # Run all dimension analyzers
    dimensions = [
        analyze_institutional(symbol),
        analyze_volume(symbol),
        analyze_sector(symbol),
        analyze_vix_regime(),
        analyze_global_cues(),
    ]

    # Find primary mover (highest |score * confidence|)
    weighted = [(d, abs(d.score * d.confidence)) for d in dimensions]
    weighted.sort(key=lambda x: x[1], reverse=True)
    primary = weighted[0][0] if weighted else dimensions[0]

    # Build narrative
    narrative_parts = []
    for d in dimensions:
        if abs(d.score) > 20:
            direction = "bullish" if d.score > 0 else "bearish"
            narrative_parts.append(f"{d.name}: {direction} ({d.evidence})")

    narrative = f"{symbol} moved {price_change:+.1f}%. "
    if narrative_parts:
        narrative += f"Primary driver: {primary.name}. " + "; ".join(narrative_parts)
    else:
        narrative += "No strong single driver identified."

    attribution = SentimentAttribution(
        symbol=symbol,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        price_change_pct=price_change,
        dimensions=dimensions,
        primary_mover=primary.name,
        primary_score=primary.score,
        narrative=narrative,
    )

    # Persist to journal
    _save_attribution(attribution)

    log.info(f"  -> Primary mover: {primary.name} (score={primary.score:.0f})")
    return attribution


def _save_attribution(attr: SentimentAttribution) -> None:
    """Save attribution to daily journal."""
    journal_dir = Path.home() / ".trading_platform" / "sentiment"
    journal_dir.mkdir(parents=True, exist_ok=True)
    today_file = journal_dir / f"{datetime.now():%Y-%m-%d}.jsonl"
    with open(today_file, "a") as f:
        f.write(json.dumps(attr.to_dict(), default=str) + "\n")


# ── CLI helper ───────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    result = attribute_sentiment(symbol)
    print(json.dumps(result.to_dict(), indent=2, default=str))
