"""
market/websocket.py
───────────────────
Real-time market data via Fyers WebSocket.

Connects once at login → all subscribed symbols stream live ticks.
Much faster than REST API polling (~instant vs 1-3s per call).

Features:
  - Auto-subscribe to NIFTY, BANKNIFTY, VIX on connect
  - Subscribe to any stock on demand
  - Cache latest tick for instant quote retrieval
  - Callbacks for price change events (used by alerts)
  - Auto-reconnect on disconnect

Usage:
    from market.websocket import ws_manager

    # Start (called automatically at broker login)
    ws_manager.start(access_token, app_id)

    # Subscribe to symbols
    ws_manager.subscribe(["NSE:RELIANCE-EQ", "NSE:TCS-EQ"])

    # Get latest cached tick (instant, no API call)
    tick = ws_manager.get_tick("NSE:RELIANCE-EQ")
    print(tick["ltp"])

    # Register a callback for real-time alerts
    ws_manager.on_tick(my_callback)  # called on every tick
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ── Default symbols to subscribe ─────────────────────────────

DEFAULT_SYMBOLS = [
    "NSE:NIFTY50-INDEX",
    "NSE:NIFTYBANK-INDEX",
    "NSE:INDIAVIX-INDEX",
]

# Map our instrument format to Fyers WebSocket format
_SYMBOL_MAP = {
    "NSE:NIFTY 50": "NSE:NIFTY50-INDEX",
    "NSE:NIFTY BANK": "NSE:NIFTYBANK-INDEX",
    "NSE:INDIA VIX": "NSE:INDIAVIX-INDEX",
    "BSE:SENSEX": "BSE:SENSEX-INDEX",
    "NSE:NIFTY FIN SERVICE": "NSE:FINNIFTY-INDEX",
    "NSE:NIFTY MIDCAP 100": "NSE:MIDCAP100-INDEX",
    "NSE:NIFTY IT": "NSE:NIFTYIT-INDEX",
    "NSE:NIFTY PHARMA": "NSE:CNXPHARMA-INDEX",
    "NSE:NIFTY AUTO": "NSE:CNXAUTO-INDEX",
    "NSE:NIFTY FMCG": "NSE:CNXFMCG-INDEX",
    "NSE:NIFTY REALTY": "NSE:CNXREALTY-INDEX",
    "NSE:NIFTY METAL": "NSE:CNXMETAL-INDEX",
    "NSE:NIFTY ENERGY": "NSE:CNXENERGY-INDEX",
}

# Known index patterns — anything with these keywords is an INDEX, not EQ
_INDEX_KEYWORDS = {
    "NIFTY",
    "SENSEX",
    "VIX",
    "MIDCAP",
    "FINNIFTY",
    "BANKNIFTY",
    "PHARMA",
    "AUTO",
    "FMCG",
    "REALTY",
    "METAL",
    "ENERGY",
    "IT",
    "FIN SERVICE",
    "BANK",
    "INDEX",
}


def _to_ws_symbol(instrument: str) -> str:
    """Convert our instrument format to Fyers WebSocket format."""
    # Direct map lookup
    if instrument in _SYMBOL_MAP:
        return _SYMBOL_MAP[instrument]

    # Try uppercase version
    if instrument.upper() in _SYMBOL_MAP:
        return _SYMBOL_MAP[instrument.upper()]

    if ":" in instrument:
        exch, sym = instrument.split(":", 1)
        # Already in Fyers format (has -EQ, -INDEX, etc.)
        if "-" in sym:
            return instrument

        sym_upper = sym.upper().strip()

        # Check full map with constructed key
        map_key = f"{exch.upper()}:{sym_upper}"
        if map_key in _SYMBOL_MAP:
            return _SYMBOL_MAP[map_key]

        # Check if it's an index (contains NIFTY, SENSEX, VIX, etc.)
        if any(kw in sym_upper for kw in _INDEX_KEYWORDS):
            clean = sym_upper.replace(" ", "")
            return f"{exch}:{clean}-INDEX"

        return f"{exch}:{sym}-EQ"
    return f"NSE:{instrument}-EQ"


@dataclass
class Tick:
    """A single price tick from WebSocket."""

    symbol: str
    ltp: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0  # prev close
    volume: int = 0
    change: float = 0.0
    change_pct: float = 0.0
    timestamp: float = 0.0  # epoch
    bid: float = 0.0
    ask: float = 0.0

    def to_dict(self) -> dict:
        """Convert tick to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "ltp": self.ltp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "change": self.change,
            "change_pct": self.change_pct,
            "timestamp": self.timestamp,
            "bid": self.bid,
            "ask": self.ask,
        }


class WebSocketManager:
    """
    Manages the Fyers WebSocket connection for real-time market data.

    Singleton — one connection per session, shared across all modules.
    """

    def __init__(self) -> None:
        self._ws = None
        self._connected = False
        self._access_token = ""
        self._app_id = ""
        self._ticks: dict[str, Tick] = {}  # symbol → latest tick
        self._callbacks: list[Callable] = []
        self._subscribed: set[str] = set()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._broker_type = ""  # "fyers" or "zerodha"
        self._token_map: dict[int, str] = {}  # token -> symbol (for Zerodha)

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self, access_token: str, app_id: str = "", broker_type: str = "fyers") -> None:
        """
        Start the WebSocket connection in a background thread.
        Call this after successful broker login.
        """
        if self._connected:
            logger.info(f"WebSocket ({self._broker_type}) already connected")
            return

        self._access_token = access_token
        self._app_id = app_id
        self._broker_type = broker_type

        self._thread = threading.Thread(target=self._connect, daemon=True)
        self._thread.start()

        # Wait briefly for connection
        for _ in range(20):
            if self._connected:
                break
            time.sleep(0.25)

        if self._connected:
            logger.info("WebSocket connected")
            # Auto-subscribe to default symbols
            self.subscribe(DEFAULT_SYMBOLS)
        else:
            logger.warning("WebSocket connection timed out — will use REST fallback")

    def stop(self) -> None:
        """Disconnect the WebSocket."""
        if self._ws:
            try:
                self._ws.close_connection()
            except Exception:
                pass
        self._connected = False
        self._ws = None

    def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to symbols for real-time ticks."""
        if not self._ws or not self._connected:
            return

        if self._broker_type == "fyers":
            ws_symbols = [_to_ws_symbol(s) for s in symbols]
        else:
            # Zerodha needs instrument tokens
            ws_symbols = self._get_kite_tokens(symbols)

        new_symbols = [s for s in ws_symbols if s not in self._subscribed]

        if not new_symbols:
            return

        try:
            if self._broker_type == "fyers":
                self._ws.subscribe(new_symbols)
            else:
                self._ws.subscribe(new_symbols)
                self._ws.set_mode(self._ws.MODE_FULL, new_symbols)
            
            self._subscribed.update(new_symbols)
            logger.info(f"Subscribed to {len(new_symbols)} symbols")
        except Exception as e:
            logger.error(f"Subscribe failed: {e}")

    def unsubscribe(self, symbols: list[str]) -> None:
        """Unsubscribe from symbols."""
        if not self._ws or not self._connected:
            return
        ws_symbols = [_to_ws_symbol(s) for s in symbols]
        try:
            self._ws.unsubscribe(ws_symbols)
            self._subscribed -= set(ws_symbols)
        except Exception:
            pass

    def get_tick(self, instrument: str) -> Optional[Tick]:
        """
        Get the latest cached tick for a symbol (instant, no API call).
        Returns None if no tick received yet.
        """
        ws_sym = _to_ws_symbol(instrument)
        with self._lock:
            return self._ticks.get(ws_sym)

    def get_ltp(self, instrument: str) -> Optional[float]:
        """Get cached LTP for a symbol. Returns None if not available."""
        tick = self.get_tick(instrument)
        return tick.ltp if tick else None

    def on_tick(self, callback: Callable[[Tick], None]) -> None:
        """Register a callback that fires on every tick. Used by alerts."""
        self._callbacks.append(callback)

    def get_all_ticks(self) -> dict[str, Tick]:
        """Get all cached ticks."""
        with self._lock:
            return dict(self._ticks)

    def get_all_ticks_serializable(self) -> list[dict]:
        """Get all cached ticks as a list of serializable dicts."""
        with self._lock:
            return [t.to_dict() for t in self._ticks.values()]

    # ── Private ──────────────────────────────────────────────

    def _get_kite_tokens(self, symbols: list[str]) -> list[int]:
        """Convert symbols to Kite instrument tokens using cached mapping."""
        from brokers.zerodha import INSTRUMENT_FILE
        if not INSTRUMENT_FILE.exists():
            return []
        
        try:
            mapping = json.loads(INSTRUMENT_FILE.read_text())
            tokens = []
            for s in symbols:
                # Remove exchange prefix if present
                clean_s = s.split(":")[-1] if ":" in s else s
                token = mapping.get(clean_s)
                if token:
                    tokens.append(int(token))
                    self._token_map[int(token)] = s
            return tokens
        except Exception:
            return []

    def _connect(self) -> None:
        """Establish WebSocket connection."""
        if self._broker_type == "fyers":
            self._connect_fyers()
        elif self._broker_type == "zerodha":
            self._connect_kite()

    def _connect_fyers(self) -> None:
        """Establish Fyers WebSocket connection."""
        try:
            from fyers_apiv3.FyersWebsocket import data_ws

            self._ws = data_ws.FyersDataSocket(
                access_token=f"{self._app_id}:{self._access_token}",
                log_path="",
                litemode=False,
                write_to_file=False,
                reconnect=True,
                on_connect=self._on_connect,
                on_close=self._on_close,
                on_error=self._on_error,
                on_message=self._on_message,
            )
            self._ws.connect()
        except ImportError:
            logger.error("fyers-apiv3 not installed — WebSocket unavailable")
        except Exception as e:
            logger.error(f"Fyers WebSocket connection failed: {e}")

    def _connect_kite(self) -> None:
        """Establish Zerodha Kite WebSocket connection."""
        try:
            from kiteconnect import KiteTicker

            self._ws = KiteTicker(api_key=self._app_id, access_token=self._access_token)
            self._ws.on_connect = self._on_kite_connect
            self._ws.on_ticks = self._on_kite_ticks
            self._ws.on_close = self._on_close
            self._ws.on_error = self._on_error
            
            # This is blocking, but we are in a background thread
            self._ws.connect(threaded=False) 
        except ImportError:
            logger.error("kiteconnect not installed — WebSocket unavailable")
        except Exception as e:
            logger.error(f"Kite WebSocket connection failed: {e}")

    def _on_kite_connect(self, ws, response):
        self._on_connect()
        # Resubscribe to existing symbols if reconnecting
        if self._subscribed:
            ws.subscribe(list(self._subscribed))
            ws.set_mode(ws.MODE_FULL, list(self._subscribed))

    def _on_kite_ticks(self, ws, ticks):
        """Process incoming Kite ticks."""
        for data in ticks:
            token = data.get("instrument_token")
            symbol = self._token_map.get(token, f"TOKEN:{token}")
            
            # Map Kite tick to our standard Tick format
            tick = Tick(
                symbol=symbol,
                ltp=float(data.get("last_price", 0)),
                open=float(data.get("ohlc", {}).get("open", 0)),
                high=float(data.get("ohlc", {}).get("high", 0)),
                low=float(data.get("ohlc", {}).get("low", 0)),
                close=float(data.get("ohlc", {}).get("close", 0)),
                volume=int(data.get("volume", 0)),
                change=float(data.get("change", 0)),
                timestamp=float(time.time()),
                bid=float(data.get("depth", {}).get("buy", [{}])[0].get("price", 0)),
                ask=float(data.get("depth", {}).get("sell", [{}])[0].get("price", 0)),
            )
            
            # Calc change_pct if missing
            if tick.close > 0:
                tick.change_pct = (tick.change / tick.close) * 100

            with self._lock:
                self._ticks[symbol] = tick

            # Fire callbacks
            for cb in self._callbacks:
                try:
                    cb(tick)
                except Exception:
                    pass

    def _on_connect(self) -> None:
        self._connected = True
        logger.info("WebSocket: connected")

    def _on_close(self, *args, **kwargs) -> None:
        self._connected = False
        logger.info("WebSocket: disconnected")

    def _on_error(self, *args, **kwargs) -> None:
        if args:
            logger.debug(f"WebSocket error: {args[0]}")

    def _on_message(self, message) -> None:
        """Process incoming tick data."""
        try:
            if isinstance(message, str):
                data_list = json.loads(message)
                if not isinstance(data_list, list):
                    data_list = [data_list]
            elif isinstance(message, list):
                data_list = message
            elif isinstance(message, dict):
                data_list = [message]
            else:
                return

            for data in data_list:
                if not isinstance(data, dict):
                    continue

                symbol = data.get("symbol", data.get("n", ""))
                if not symbol:
                    continue

                tick = Tick(
                    symbol=symbol,
                    ltp=float(data.get("ltp", data.get("lp", 0))),
                    open=float(data.get("open_price", data.get("open", 0))),
                    high=float(data.get("high_price", data.get("high", 0))),
                    low=float(data.get("low_price", data.get("low", 0))),
                    close=float(data.get("prev_close_price", data.get("close", 0))),
                    volume=int(data.get("vol_traded_today", data.get("volume", 0))),
                    change=float(data.get("ch", 0)),
                    change_pct=float(data.get("chp", 0)),
                    timestamp=float(data.get("exch_feed_time", time.time())),
                    bid=float(data.get("bid", 0)),
                    ask=float(data.get("ask", 0)),
                )

                with self._lock:
                    self._ticks[symbol] = tick

                # Fire callbacks
                for cb in self._callbacks:
                    try:
                        cb(tick)
                    except Exception:
                        pass

        except Exception as e:
            logger.debug(f"Tick parse error: {e}")


# ── Singleton ────────────────────────────────────────────────

ws_manager = WebSocketManager()
