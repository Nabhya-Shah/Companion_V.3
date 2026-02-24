"""Research tools — Wikipedia lookup."""
from __future__ import annotations

from companion_ai.tools.registry import tool

try:
    import requests
except ImportError:
    requests = None


@tool('wikipedia_lookup', schema={
    "type": "function",
    "function": {
        "name": "wikipedia_lookup",
        "description": "Look up factual information on Wikipedia. Returns a concise summary of the topic. Best for facts, definitions, historical info.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Topic or term to look up (e.g., 'Python programming', 'Albert Einstein', 'World War 2')"
                }
            },
            "required": ["query"]
        }
    }
})
def tool_wikipedia(query: str) -> str:
    """Look up information on Wikipedia."""
    if not requests:
        return "Wikipedia lookup unavailable (requests library not installed)"

    try:
        search_url = "https://en.wikipedia.org/w/api.php"
        headers = {
            'User-Agent': 'CompanionAI/1.0 (Educational Assistant)'
        }
        search_params = {
            'action': 'opensearch',
            'search': query,
            'limit': 1,
            'format': 'json'
        }

        search_resp = requests.get(search_url, params=search_params, headers=headers, timeout=5.0)
        search_data = search_resp.json()

        if not search_data[1]:
            return f"No Wikipedia article found for '{query}'"

        title = search_data[1][0]

        summary_params = {
            'action': 'query',
            'prop': 'extracts',
            'exintro': True,
            'explaintext': True,
            'titles': title,
            'format': 'json'
        }

        summary_resp = requests.get(search_url, params=summary_params, headers=headers, timeout=5.0)
        summary_data = summary_resp.json()

        pages = summary_data['query']['pages']
        page = next(iter(pages.values()))

        if 'extract' not in page:
            return f"Could not retrieve summary for '{title}'"

        extract = page['extract']
        if len(extract) > 500:
            extract = extract[:497] + '...'

        return f"📖 Wikipedia - {title}:\n\n{extract}"

    except requests.Timeout:
        return "Wikipedia lookup timeout. Try again."
    except Exception as e:
        return f"Wikipedia error: {str(e)[:100]}"
