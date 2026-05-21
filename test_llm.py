# test_llm.py
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env
load_dotenv(Path(__file__).parent / ".env")

sys.path.append(str(Path(__file__).parent / "india-trade-cli"))

from agent.core import get_provider
try:
    p = get_provider()
    print("Provider constructed:", p.provider_name)
    response = p.chat([{"role": "user", "content": "hi"}], stream=False)
    print("Response:", response)
except Exception as e:
    print("Error:", e)
