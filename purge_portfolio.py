#!/usr/bin/env python3
"""
purge_portfolio.py
------------------
Purge expired options positions from ~/.trading_platform/paper_portfolio.json.

Identifies any position key matching the pattern like TCS25MAR2300PE where
the embedded month/year is in the past, removes them, and saves the file.
Cash and holdings are NOT touched.
"""

import json
import re
import os
import shutil
from datetime import datetime
from pathlib import Path

PORTFOLIO_PATH = Path.home() / ".trading_platform" / "paper_portfolio.json"

# Months mapping
MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

OPTION_KEY_RE = re.compile(
    r'[A-Z]+(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d+)(CE|PE)',
    re.IGNORECASE,
)


def is_expired(key: str) -> bool:
    """Return True if the option key encodes a month/year that is in the past."""
    m = OPTION_KEY_RE.search(key.upper())
    if not m:
        return False
    year_2d = int(m.group(1))   # e.g. 25 → 2025
    month_str = m.group(2).upper()
    full_year = 2000 + year_2d
    month_num = MONTHS.get(month_str, 0)
    if month_num == 0:
        return False
    # A position is expired if its expiry month/year is strictly before the current month
    now = datetime.now()
    expiry_date = datetime(full_year, month_num, 1)
    # Options typically expire on the last Thursday of the month;
    # we consider any position whose month < current month as expired.
    current_month_start = datetime(now.year, now.month, 1)
    return expiry_date < current_month_start


def main():
    if not PORTFOLIO_PATH.exists():
        print(f"ERROR: Portfolio file not found at {PORTFOLIO_PATH}")
        return

    # Backup first
    backup_path = PORTFOLIO_PATH.with_suffix(".json.bak")
    shutil.copy2(PORTFOLIO_PATH, backup_path)
    print(f"✅ Backup saved to {backup_path}")

    with open(PORTFOLIO_PATH) as f:
        portfolio = json.load(f)

    positions: dict = portfolio.get("positions", {})
    original_count = len(positions)

    print(f"\n📋 Total positions before purge: {original_count}")
    print(f"   Cash: ₹{portfolio.get('cash', 0):,.2f}")

    expired_keys = [k for k in positions if is_expired(k)]

    if not expired_keys:
        print("✅ No expired option positions found. Nothing to purge.")
    else:
        print(f"\n🗑️  Removing {len(expired_keys)} expired positions:")
        for key in sorted(expired_keys):
            pos = positions[key]
            qty = pos.get("quantity", pos.get("qty", "?"))
            avg = pos.get("avg_price", pos.get("average_price", "?"))
            print(f"   - {key}  qty={qty}  avg_price={avg}")
            del positions[key]

    # Fix realized_pnl if None
    if portfolio.get("realized_pnl") is None:
        print("\n🔧 Resetting realized_pnl from None → 0.0")
        portfolio["realized_pnl"] = 0.0

    portfolio["positions"] = positions

    with open(PORTFOLIO_PATH, "w") as f:
        json.dump(portfolio, f, indent=2, default=str)

    remaining = len(portfolio["positions"])
    print(f"\n✅ Purge complete!")
    print(f"   Removed : {len(expired_keys)} expired option positions")
    print(f"   Remaining positions: {remaining}")
    print(f"   Cash (unchanged): ₹{portfolio.get('cash', 0):,.2f}")
    print(f"   Portfolio saved to: {PORTFOLIO_PATH}")


if __name__ == "__main__":
    main()
