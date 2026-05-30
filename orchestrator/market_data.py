"""
orchestrator/market_data.py
────────────────────────────
Free market data layer - NO KYC, NO PAN required.

Data Sources (priority order):
  1. Zerodha Kite Connect (user already has API key)
  2. yfinance (free, no signup, already a dependency)
  3. nselib / nsepython (free, no signup, NSE-specific)

Replaces Fyers entirely.
"""

from __future__ import annotations


from orchestrator.vibe_logger import exhaustive_log
import logging
from datetime import datetime, timedelta
from typing import Optional, Any

# Bridge to india-trade-cli
import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
if str(root / "india-trade-cli") not in sys.path:
    sys.path.insert(0, str(root / "india-trade-cli"))

from market.quotes import get_quote as get_broker_quote

log = logging.getLogger("orchestrator.market_data")


# ── yfinance (always available, no auth) ─────────────────────

@exhaustive_log
def get_stock_data_yfinance(symbol: str, period: str = "1mo") -> dict:
    """
    Fetch stock data via yfinance. No API key needed.
    NSE stocks need .NS suffix, BSE need .BO suffix.
    """
    try:
        import yfinance as yf

        # Auto-add .NS suffix for NSE if not present
        ticker_symbol = symbol if "." in symbol else f"{symbol}.NS"
        ticker = yf.Ticker(ticker_symbol)

        hist = ticker.history(period=period)
        if hist.empty:
            return {"status": "error", "error": f"No data for {ticker_symbol}"}

        latest = hist.iloc[-1]
        info = {}
        try:
            info = ticker.info or {}
        except Exception:
            pass

        return {
            "status": "ok",
            "symbol": symbol,
            "source": "yfinance",
            "ltp": float(latest.get("Close", 0)),
            "open": float(latest.get("Open", 0)),
            "high": float(latest.get("High", 0)),
            "low": float(latest.get("Low", 0)),
            "volume": int(latest.get("Volume", 0)),
            "change_pct": float(
                ((latest["Close"] - hist.iloc[-2]["Close"]) / hist.iloc[-2]["Close"] * 100)
                if len(hist) > 1 else 0
            ),
            "52w_high": float(info.get("fiftyTwoWeekHigh", 0)),
            "52w_low": float(info.get("fiftyTwoWeekLow", 0)),
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE", 0),
            "sector": info.get("sector", ""),
            "history_days": len(hist),
        }
    except ImportError:
        return {"status": "error", "error": "yfinance not installed"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@exhaustive_log
def get_historical_ohlcv(symbol: str, days: int = 90) -> list[dict]:
    """Get historical OHLCV data via yfinance."""
    try:
        import yfinance as yf

        ticker_symbol = symbol if "." in symbol else f"{symbol}.NS"
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period=f"{days}d")

        rows = []
        for date, row in hist.iterrows():
            rows.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        return rows
    except Exception as e:
        log.error(f"Historical data fetch failed for {symbol}: {e}")
        return []


# ── NSE-specific data (options chain, FII/DII, indices) ──────

@exhaustive_log
def get_nse_fii_dii_data() -> dict:
    """
    Fetch FII/DII daily activity from NSE website.
    No API key needed - public data.
    """
    try:
        import httpx
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }
        # NSE FII/DII endpoint
        resp = httpx.get(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"status": "ok", "source": "nse", "data": data}
        return {"status": "error", "code": resp.status_code}
    except Exception as e:
        log.warning(f"NSE FII/DII fetch failed: {e}")
        return {"status": "error", "error": str(e)}


@exhaustive_log
def get_india_vix() -> float:
    """Get India VIX from yfinance."""
    try:
        import yfinance as yf
        vix = yf.Ticker("^INDIAVIX")
        hist = vix.history(period="1d")
        if not hist.empty:
            return float(hist.iloc[-1]["Close"])
    except Exception as e:
        log.warning(f"VIX fetch failed: {e}")
    return 0.0


@exhaustive_log
def get_nifty_level() -> dict:
    """Get current NIFTY 50 level."""
    return get_stock_data_yfinance("^NSEI")


# ── Multi-source fetcher ─────────────────────────────────────

@exhaustive_log
def fetch_quote(symbol: str, prefer: str = "kite") -> dict:
    """
    Fetch a quote with automatic fallback.
    prefer: 'kite' or 'yfinance'
    """
    # 1. Try Live Broker (Kite/Fyers) via india-trade-cli
    try:
        # Standardize symbol for broker: "NSE:RELIANCE"
        broker_sym = symbol if ":" in symbol else f"NSE:{symbol}"
        quotes = get_broker_quote([broker_sym])
        
        if broker_sym in quotes:
            q = quotes[broker_sym]
            return {
                "status": "ok",
                "symbol": symbol,
                "source": "broker",
                "ltp": q.last_price,
                "open": q.open,
                "high": q.high,
                "low": q.low,
                "volume": q.volume,
                "change_pct": q.change_pct,
            }
    except Exception as e:
        log.debug(f"Broker quote failed for {symbol}: {e}")

    # 2. Fallback to yfinance
    return get_stock_data_yfinance(symbol)
