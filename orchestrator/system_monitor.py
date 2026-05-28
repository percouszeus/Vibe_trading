"""
orchestrator/system_monitor.py
─────────────────────────────
A utility to monitor the daily logs, track API usage/failures, and provide 
a summary of "what went wrong when and where".
"""

import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import re

LOG_DIR = Path(__file__).resolve().parent / "logs"
JOURNAL_DIR = Path.home() / ".trading_platform" / "journals"

def analyze_today_logs():
    # Force UTF-8 for Windows console
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
        
    today = datetime.now(ZoneInfo('Asia/Kolkata')).strftime("%Y%m%d")
    log_file = LOG_DIR / f"daily_{today}.log"
    
    if not log_file.exists():
        print(f"No logs found for today: {log_file}")
        return
        
    print(f"=== Vibe Trading Daily Monitor Report ({today}) ===")
    
    errors = []
    warnings = []
    api_calls = 0
    llm_calls = 0
    
    error_pattern = re.compile(r"\[ERROR\]")
    warning_pattern = re.compile(r"\[WARNING\]")
    
    with open(log_file, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if "LLM query" in line or "LLM generation" in line or "Recommending strategy" in line:
                llm_calls += 1
            if "fetch" in line.lower() or "request" in line.lower() or "api" in line.lower():
                api_calls += 1
                
            if error_pattern.search(line) or " ❌ " in line:
                errors.append(f"Line {i+1}: {line.strip()}")
            elif warning_pattern.search(line) or " ⚠️ " in line:
                warnings.append(f"Line {i+1}: {line.strip()}")
                
    print(f"\n[Usage Stats]")
    print(f"- Estimated LLM Requests: {llm_calls}")
    print(f"- Estimated API Operations: {api_calls}")
    
    print(f"\n[Errors Encountered: {len(errors)}]")
    for e in errors[-10:]:  # show last 10
        print(f"  {e}")
        
    print(f"\n[Warnings Encountered: {len(warnings)}]")
    for w in warnings[-10:]: # show last 10
        print(f"  {w}")
        
    if not errors and not warnings:
        print("\nAll systems operating nominally with zero errors/warnings.")
        
if __name__ == "__main__":
    analyze_today_logs()
