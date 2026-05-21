import os
import openai

print("Configuring client...")
client = openai.OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

print("Calling chat completions...")
try:
    completion = client.chat.completions.create(
        model="llama3.1:8b",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.5,
        max_tokens=1024,
    )
    print("Response:")
    print(completion.choices[0].message.content)
except Exception as e:
    print("Error:", e)
