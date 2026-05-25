import os
import sys
import json
import time
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# Setup sys.path so we can import india-trade-cli modules
project_root = Path(__file__).parent.parent
cli_path = project_root / "india-trade-cli"
sys.path.insert(0, str(cli_path))

# Patch environment for headless execution
os.environ["TRADING_MODE"] = "PAPER"
os.environ["_CLI_BATCH_MODE"] = "1"

# Load .env and keychain credentials
from dotenv import load_dotenv
load_dotenv(project_root / "Vibe_trading" / ".env")
try:
    load_dotenv(project_root / ".env")
except:
    pass

from config.credentials import load_all as _load_keychain
try:
    _load_keychain()
except Exception:
    pass

# Import required modules
from brokers.mock import MockBrokerAPI
from brokers.session import register_broker
from agent.multi_agent import MultiAgentAnalyzer
from market.history import get_ohlcv

# Initialize SQLite Cache for LLM responses
CACHE_DB = project_root / "scratch" / "backtest_llm_cache.db"

def init_cache():
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS llm_cache (
                prompt_hash TEXT PRIMARY KEY,
                response TEXT
            )
        ''')

def get_cached_response(prompt_hash: str):
    with sqlite3.connect(CACHE_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT response FROM llm_cache WHERE prompt_hash = ?", (prompt_hash,))
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None

def set_cached_response(prompt_hash: str, response: dict):
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO llm_cache (prompt_hash, response) VALUES (?, ?)",
            (prompt_hash, json.dumps(response))
        )

# --- Monkey-Patch OpenAI Provider to intercept LLM calls ---
from agent.core import OpenAIProvider
import hashlib
import threading

rate_limit_lock = threading.Lock()
last_api_call_time = 0.0
MIN_INTERVAL = 1.6  # ensures <= 37.5 req/min, safely under NIM 40 req/min limit

def rate_limited_api_call(original_func, self, messages, tools):
    global last_api_call_time
    
    # Generate robust cache key including model, system prompt, messages, and tools
    prompt_data = {
        "model": self.model,
        "system_prompt": self.system_prompt,
        "messages": messages,
        "tools": tools
    }
    prompt_str = json.dumps(prompt_data, sort_keys=True)
    prompt_hash = hashlib.sha256(prompt_str.encode()).hexdigest()
    
    # 1. Cache hit check (no lock, no wait, extremely fast)
    cached = get_cached_response(prompt_hash)
    if cached:
        # print(f"  [Cache Hit] Response loaded from DB.")
        return cached["content"], cached["tool_calls"]
    
    # 2. Cache miss: Serialize and throttle actual API calls
    with rate_limit_lock:
        now = time.time()
        elapsed = now - last_api_call_time
        if elapsed < MIN_INTERVAL:
            sleep_time = MIN_INTERVAL - elapsed
            # print(f"  [Rate Limiter] Throttling for {sleep_time:.2f}s...")
            time.sleep(sleep_time)
        
        # print(f"  [Cache Miss] Calling LLM API ({self.model})...")
        t0 = time.time()
        content, tcs = original_func(self, messages, tools)
        last_api_call_time = time.time()
        # print(f"  [API Call Success] Completed in {last_api_call_time - t0:.2f}s")
        
        # Save response to cache
        set_cached_response(prompt_hash, {"content": content, "tool_calls": tcs})
        return content, tcs

original_call_round = OpenAIProvider._call_round
original_stream_round = OpenAIProvider._stream_round

def patched_call_round(self, messages, tools):
    return rate_limited_api_call(original_call_round, self, messages, tools)

def patched_stream_round(self, messages, tools):
    return rate_limited_api_call(original_stream_round, self, messages, tools)

OpenAIProvider._call_round = patched_call_round
OpenAIProvider._stream_round = patched_stream_round


def run_historical_backtest(symbol: str, days: int = 30):
    init_cache()
    
    print(f"=== Starting Historical LLM Backtest for {symbol} ({days} days) ===")
    
    # Register mock broker
    mock = MockBrokerAPI(passthrough_market_data=True)
    mock.complete_login()
    register_broker("mock", mock, primary=True)
    
    # Fetch historical data to find trading days
    try:
        df = get_ohlcv(symbol, days=days + 10)
    except Exception as e:
        print(f"Failed to fetch data for {symbol}: {e}")
        return
        
    if df.empty:
        print("No historical data found.")
        return
        
    trading_dates = df.index[-days:]
    
    results = []
    
    for target_date in trading_dates:
        date_str = target_date.strftime("%Y-%m-%d")
        print(f"\n--- Simulating Date: {date_str} ---")
        
        # NOTE: In a true backtest, we would mock datetime.now() inside the CLI 
        # so `get_ohlcv` only returns data up to target_date.
        # For simplicity in this v1 script, we'll let the AI analyse it 
        # (It will see the full data up to today due to how get_ohlcv works globally,
        # but this script serves as the rate-limit testing wrapper).
        
        try:
            from agent.tools import build_registry
            from agent.core import get_provider
            registry = build_registry()
            llm_provider = get_provider(registry=registry)
            
            # Run the actual multi-agent analysis!
            analyzer = MultiAgentAnalyzer(registry=registry, llm_provider=llm_provider, verbose=False)
            output = analyzer.analyze(symbol, "NSE")
            
            # Parse final verdict from the synthesis output text
            from agent.schema_parser import parse_synthesis_output
            parsed = parse_synthesis_output(output)
            
            raw_verdict = parsed.verdict
            if raw_verdict in ("STRONG_BUY", "BUY"):
                verdict = "BULLISH"
            elif raw_verdict in ("STRONG_SELL", "SELL"):
                verdict = "BEARISH"
            else:
                verdict = "NEUTRAL"
                
            score = parsed.confidence
            
            print(f"  Verdict: {verdict} (Confidence: {score}%)")
            results.append({"date": date_str, "verdict": verdict, "score": score})
            
        except Exception as e:
            print(f"  Error analyzing {symbol} on {date_str}: {e}")

    # Summary
    print("\n=== Backtest Complete ===")
    df_results = pd.DataFrame(results)
    print(df_results)
    
    win_rate = len(df_results[df_results['verdict'] == 'BULLISH']) / len(df_results) if not df_results.empty else 0
    print(f"Bullish Rate: {win_rate:.1%}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        symbol = sys.argv[1]
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        run_historical_backtest(symbol, days)
    else:
        print("Usage: python run_historical_backtest.py <SYMBOL> <DAYS>")
