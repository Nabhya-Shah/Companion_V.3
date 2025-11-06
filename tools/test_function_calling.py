#!/usr/bin/env python3
"""Test Groq function calling directly."""

import os
from dotenv import load_dotenv
from groq import Groq
import json

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Simple test function schema
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather in a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name"
                }
            },
            "required": ["location"]
        }
    }
}]

# Test message
messages = [
    {"role": "system", "content": "You are a helpful assistant with access to tools."},
    {"role": "user", "content": "What's the weather in Tokyo?"}
]

print("Testing function calling with llama-3.3-70b-versatile...")
print()

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=messages,
    tools=tools,
    tool_choice="auto",
    temperature=0.7,
    max_tokens=1024
)

message = response.choices[0].message
print(f"Finish reason: {response.choices[0].finish_reason}")
print(f"Has tool_calls: {bool(message.tool_calls)}")
print()

if message.tool_calls:
    tool_call = message.tool_calls[0]
    print(f"Tool called: {tool_call.function.name}")
    print(f"Arguments: {tool_call.function.arguments}")
    print("✅ Function calling WORKS!")
else:
    print(f"No tool call. Response: {message.content}")
    print("❌ Function calling NOT working")
