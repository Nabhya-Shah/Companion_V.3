#!/usr/bin/env python3
"""Quick smoke test for Ollama OpenAI-compatible tool calling.

Runs two tests:
1) Plain chat completion
2) Tool calling with a trivial tool schema

This helps diagnose 500s coming from /v1/chat/completions.
"""

import os
import sys

# Ensure project root is on sys.path when run from tools/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from companion_ai.local_llm import OllamaClientWrapper


def main():
    client = OllamaClientWrapper()
    model = "qwen2.5-coder:7b"

    print("--- no-tools ---")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "Reply with OK only."},
        ],
        temperature=0.0,
        max_tokens=16,
    )
    print(resp.choices[0].message.content)

    print("--- tools ---")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "Get current time in ISO format",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
    ]

    resp2 = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "If user asks for time, call get_current_time."},
            {"role": "user", "content": "what time is it?"},
        ],
        tools=tools,
        tool_choice="auto",
        temperature=0.0,
        max_tokens=128,
    )

    choice = resp2.choices[0]
    msg = choice.message
    tool_calls = getattr(msg, "tool_calls", None)

    print("finish_reason:", getattr(choice, "finish_reason", None))
    print("tool_calls:", tool_calls)
    print("content:", getattr(msg, "content", None))


if __name__ == "__main__":
    main()
