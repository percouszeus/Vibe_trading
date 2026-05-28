import os
import sys
from dotenv import load_dotenv

def test_openrouter():
    # Load environment variables from .env
    load_dotenv()
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY is not set in .env")
        sys.exit(1)
        
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v3.2")
    
    print(f"Testing OpenRouter API...")
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
        print("Success! Response from OpenRouter:")
        print(response.choices[0].message.content)
        
    except ImportError:
        print("openai package not found. Install it via: pip install openai")
    except Exception as e:
        print(f"Failed to connect to OpenRouter API: {e}")

if __name__ == "__main__":
    test_openrouter()
