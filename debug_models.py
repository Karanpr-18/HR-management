
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
print(f"API Key present: {bool(api_key)}")

try:
    client = genai.Client(api_key=api_key)
    print("Listing models...")
    # The new SDK list_models returns an iterator of Model objects
    # We need to check how to iterate correctly or print them
    # Based on docs for google-genai v1.0
    for model in client.models.list(config={'page_size': 100}):
        print(f"- {model.name}")
except Exception as e:
    print(f"Error listing models: {e}")

print("-" * 20)
print("Testing generation with 'gemini-2.5-flash-lite'...")
try:
    response = client.models.generate_content(
        model='gemini-2.5-flash-lite',
        contents='Hello, are you working?'
    )
    print("Success!")
    print(response.text)
except Exception as e:
    print(f"Generation failed: {e}")
    
print("-" * 20)
from groq import Groq
groq_key = os.getenv("GROQ_API_KEY")
print(f"Groq API Key present: {bool(groq_key)}")
if groq_key:
    try:
        g_client = Groq(api_key=groq_key)
        print("Testing Groq 'llama-3.1-8b-instant'...")
        chat_completion = g_client.chat.completions.create(
            messages=[{"role": "user", "content": "Hello"}],
            model="llama-3.1-8b-instant",
        )
        print("Success!")
        print(chat_completion.choices[0].message.content)
    except Exception as e:
         print(f"Groq failed: {e}")
