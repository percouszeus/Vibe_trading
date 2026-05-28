import os
import sys
from dotenv import load_dotenv

def test_nim_api():
    # Load environment variables from .env
    load_dotenv()
    
    api_key = os.getenv("NIM_API_KEY")
    if not api_key:
        print("Error: NIM_API_KEY is not set in .env")
        sys.exit(1)
        
    base_url = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
    model = os.getenv("NIM_MODEL", "meta/llama-3.1-70b-instruct")
    
    print(f"Testing NIM API...")
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")
    
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )
        
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with a simple 'Hello, World!'"}]
        )
        print("Success! Response from NIM:")
        print(response.choices[0].message.content)
        
    except ImportError:
        print("openai package not found. Install it via: pip install openai")
    except Exception as e:
        print(f"Failed to connect to NIM API: {e}")

if __name__ == "__main__":
    test_nim_api()
