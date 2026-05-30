"""
engine/scanner.py
─────────────────
Market scanner for NSE stocks.
Filters symbols based on technical and volume criteria.
"""

from orchestrator.vibe_logger import exhaustive_log
import pandas as pd
import numpy as np
from typing import List, Dict
from market.history import get_ohlcv

class MarketScanner:
    """
    Scans a universe of stocks for specific trade setups.
    """

    @exhaustive_log
    def __init__(self, symbols: List[str]):
        self.symbols = symbols

    @exhaustive_log
    def scan_for_momentum(self) -> List[Dict]:
        """
        Scans for momentum setups:
        1. Price > 50 SMA > 200 SMA
        2. RSI between 50 and 70
        3. Volume > 1.5x 20-day average
        """
        results = []
        for symbol in self.symbols:
            try:
                df = get_ohlcv(symbol=symbol, interval="day", days=250)
                if df.empty or len(df) < 200:
                    continue
                
                # Indicators
                df['sma_50'] = df['Close'].rolling(50).mean()
                df['sma_200'] = df['Close'].rolling(200).mean()
                df['vol_sma_20'] = df['Volume'].rolling(20).mean()
                
                # RSI
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs)).iloc[-1]
                
                last_close = df['Close'].iloc[-1]
                last_vol = df['Volume'].iloc[-1]
                avg_vol = df['vol_sma_20'].iloc[-1]
                sma_50 = df['sma_50'].iloc[-1]
                sma_200 = df['sma_200'].iloc[-1]
                
                # Criteria
                is_uptrend = last_close > sma_50 > sma_200
                is_momentum = 50 < rsi < 75
                is_vol_spike = last_vol > (avg_vol * 1.5)
                
                if is_uptrend and is_momentum and is_vol_spike:
                    results.append({
                        "symbol": symbol,
                        "close": last_close,
                        "rsi": rsi,
                        "vol_ratio": last_vol / avg_vol,
                        "score": (rsi / 100) + (last_vol / avg_vol / 10)
                    })
            except Exception:
                continue
                
        # Sort by score
        return sorted(results, key=lambda x: x['score'], reverse=True)

    @exhaustive_log
    def scan_for_mean_reversion(self) -> List[Dict]:
        """
        Scans for oversold conditions:
        1. RSI < 30
        2. Price below lower Bollinger Band
        """
        results = []
        for symbol in self.symbols:
            try:
                df = get_ohlcv(symbol=symbol, interval="day", days=50)
                if df.empty or len(df) < 20:
                    continue
                
                # Indicators
                df['sma_20'] = df['Close'].rolling(20).mean()
                df['std_20'] = df['Close'].rolling(20).std()
                df['bb_lower'] = df['sma_20'] - (df['std_20'] * 2)
                
                # RSI
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs)).iloc[-1]
                
                last_close = df['Close'].iloc[-1]
                bb_lower = df['bb_lower'].iloc[-1]
                
                if rsi < 30 and last_close < bb_lower:
                    results.append({
                        "symbol": symbol,
                        "close": last_close,
                        "rsi": rsi,
                        "bb_diff": (bb_lower - last_close) / bb_lower * 100
                    })
            except Exception:
                continue
                
        return sorted(results, key=lambda x: x['rsi'])
