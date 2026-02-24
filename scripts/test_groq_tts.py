import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_TOOL_API_KEY")
print(f"API Key present: {bool(api_key)}")

url = "https://api.groq.com/openai/v1/audio/speech"
headers = {"Authorization": f"Bearer {api_key}"}
data = {
    "model": "canopylabs/orpheus-v1-english",
    "input": "This is a test of the Groq Orpheus text to speech system.",
    "voice": "Orpheus"
}

try:
    print("Send request to Groq...")
    resp = requests.post(url, headers=headers, json=data)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        print("Success! Audio content received.")
        print(f"Size: {len(resp.content)} bytes")
    else:
        print(f"Error: {resp.text}")
except Exception as e:
    print(f"Exception: {e}")
