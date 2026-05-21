import requests

name_options = [
    "VibeTradingIndia_Zeus",
    "vibe_india_agent@vibe.local"
]
password = "vibe_secure_password_123"
login_url = "https://ai4trade.ai/api/claw/agents/login"

for name in name_options:
    print(f"Testing login with name='{name}'...")
    try:
        resp = requests.post(login_url, json={"name": name, "password": password}, timeout=10)
        print("Status:", resp.status_code)
        print("Response:", resp.text)
    except Exception as e:
        print("Error:", e)
