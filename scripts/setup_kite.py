"""
scripts/setup_kite.py
─────────────────────
Helper script to perform the initial Zerodha Kite Connect login.
Works in headless environments (OCI VM) by printing the URL and 
accepting the request_token via prompt.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to sys.path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "india-trade-cli"))

from brokers.zerodha import ZerodhaAPI

def main():
    load_dotenv(root / ".env")
    
    api_key = os.getenv("KITE_API_KEY")
    api_secret = os.getenv("KITE_API_SECRET")
    
    if not api_key or api_key == "your_kite_api_key_here":
        print("Error: KITE_API_KEY not set in .env")
        return
    
    if not api_secret or api_secret == "your_kite_api_secret_here":
        print("Error: KITE_API_SECRET not set in .env")
        # We'll continue anyway to show the login URL
    
    print(f"\n--- Zerodha Kite Login Setup ---")
    broker = ZerodhaAPI(api_key=api_key, api_secret=api_secret or "")
    
    if broker.is_authenticated():
        print("✓ Already authenticated! Token is valid.")
        profile = broker.get_profile()
        print(f"  User: {profile.name} ({profile.user_id})")
        return

    login_url = broker.get_login_url()
    print(f"\n1. Open this URL in your browser:\n")
    print(f"   {login_url}")
    print(f"\n2. After logging in, you will be redirected to a URL like:")
    print(f"   http://localhost:8765/zerodha/callback?request_token=XXXXXX&status=success")
    print(f"\n3. Copy the 'request_token' value (the XXXXXX part) and paste it below.")
    
    try:
        request_token = input("\nEnter request_token: ").strip()
        if not request_token:
            print("Aborted.")
            return
        
        print("\nConnecting...")
        profile = broker.complete_login(request_token)
        print(f"\n✓ Login successful!")
        print(f"  Welcome, {profile.name}!")
        print(f"  Token saved to: ~/.trading_platform/zerodha.json")
        
    except Exception as e:
        print(f"\nError during login: {e}")

if __name__ == "__main__":
    main()
